import { useCallback, useEffect, useRef, useState } from 'react';
import { createUniver, type FUniver } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import sheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US';
import { LocaleType, type Univer } from '@univerjs/core';
import type { ProjectModel } from '../model/types';
import { applyDrawingCompile, getWorkbookDocument, previewDrawingCompile, putWorkbookDocument, writeWorkbookExcel, type WorkbookDocument } from '../api/client';
import { fromUniverWorkbook, toUniverWorkbook } from './UniverWorkbookAdapter';
import WorkspaceToolbar from './WorkspaceToolbar';
import type { WorkspaceStatus } from './workspaceTypes';
import { clipboardPayload, parseClipboard } from './ClipboardBridge';

export default function DataWorkspace({ project }: { project: ProjectModel }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<Univer | null>(null);
  const apiRef = useRef<FUniver | null>(null);
  const baseRef = useRef<WorkbookDocument | null>(null);
  const [status, setStatus] = useState<WorkspaceStatus>('loading');
  const [message, setMessage] = useState('');
  const snapshot = useCallback(() => {
    const base = baseRef.current;
    const workbook = apiRef.current?.getActiveWorkbook();
    return base && workbook ? fromUniverWorkbook(workbook.getSnapshot(), base) : null;
  }, [project.id]);
  const save = useCallback(async () => {
    const document = snapshot();
    if (!document || !baseRef.current) return;
    setStatus('saving');
    try {
      const saved = await putWorkbookDocument(project.id, document, baseRef.current.revision);
      baseRef.current = saved;
      setStatus('saved');
      setMessage(`Revision ${saved.revision} saved`);
    } catch (reason) {
      setStatus(String(reason).includes('conflict') ? 'conflict' : 'error');
      setMessage(String(reason));
    }
  }, [project.id, snapshot]);
  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    getWorkbookDocument(project.id).then((document) => {
      if (disposed || !containerRef.current) return;
      baseRef.current = document;
      const { univer, univerAPI } = createUniver({
        locale: LocaleType.EN_US,
        locales: { [LocaleType.EN_US]: sheetsCoreEnUS },
        presets: [UniverSheetsCorePreset({ container: containerRef.current, header: true, toolbar: true, formulaBar: true, footer: { sheetBar: true, statisticBar: true, menus: true, zoomSlider: true } })],
      });
      univerRef.current = univer;
      apiRef.current = univerAPI;
      univer.createUniverSheet(toUniverWorkbook(document, project.metadata.projectName, project.id));
      setStatus('saved');
    }).catch((reason) => { setMessage(String(reason)); setStatus('error'); });
    return () => { disposed = true; univerRef.current?.dispose(); univerRef.current = null; apiRef.current = null; };
  }, [project.id, project.metadata.projectName]);
  useEffect(() => {
    const timer = window.setInterval(() => { if (status === 'dirty') void save(); }, 3000);
    return () => window.clearInterval(timer);
  }, [save, status]);
  useEffect(() => {
    const listener = () => status === 'saved' && setStatus('dirty');
    window.addEventListener('keydown', listener);
    window.addEventListener('paste', listener);
    return () => { window.removeEventListener('keydown', listener); window.removeEventListener('paste', listener); };
  }, [status]);
  useEffect(() => {
    const paste = (event: ClipboardEvent) => {
      const workbook = apiRef.current?.getActiveWorkbook();
      const sheet = workbook?.getActiveSheet();
      const active = sheet?.getActiveRange();
      if (!sheet || !active || !event.clipboardData) return;
      const parsed = parseClipboard(event.clipboardData.getData('text/html'), event.clipboardData.getData('text/plain'));
      if (!parsed.length || !parsed[0]?.length) return;
      event.preventDefault();
      const row = active.getRow();
      const column = active.getColumn();
      const width = Math.max(...parsed.map((item) => item.length));
      const values = parsed.map((item) => Array.from({ length: width }, (_, index) => {
        const cell = item[index];
        return cell ? (cell.formula ? { f: cell.formula } : { v: cell.value }) : { v: '' };
      }));
      sheet.getRange(row, column, parsed.length, width).setValues(values);
      parsed.forEach((cells, rowOffset) => cells.forEach((cell, columnOffset) => {
        const target = sheet.getRange(row + rowOffset, column + columnOffset);
        if (cell.style?.fill) target.setBackgroundColor(String(cell.style.fill));
        if (cell.style?.color) target.setFontColor(String(cell.style.color));
        if (cell.style?.fontFamily) target.setFontFamily(String(cell.style.fontFamily));
        if (cell.style?.fontSize) target.setFontSize(Number.parseFloat(String(cell.style.fontSize)));
        if (cell.style?.bold) target.setFontWeight('bold');
        if (cell.style?.italic) target.setFontStyle('italic');
        if (cell.style?.underline) target.setFontLine('underline');
        if ((cell.rowSpan || 1) > 1 || (cell.colSpan || 1) > 1) {
          sheet.getRange(row + rowOffset, column + columnOffset, cell.rowSpan || 1, cell.colSpan || 1).merge();
        }
      }));
      setStatus('dirty');
    };
    const copy = (event: ClipboardEvent) => {
      const range = apiRef.current?.getActiveWorkbook()?.getActiveRange();
      if (!range || !event.clipboardData) return;
      const values = range.getValues() as unknown[][];
      const payload = clipboardPayload(values.map((row) => row.map((value) => ({ value: value == null ? '' : String(value) }))));
      event.preventDefault();
      event.clipboardData.setData('text/plain', payload.plain);
      event.clipboardData.setData('text/html', payload.html);
    };
    window.addEventListener('paste', paste);
    window.addEventListener('copy', copy);
    return () => { window.removeEventListener('paste', paste); window.removeEventListener('copy', copy); };
  }, []);
  const compile = async () => {
    await save();
    const preview = await previewDrawingCompile(project.id);
    const summary = preview.operations.filter((item) => item.action !== 'unchanged').map((item) => `${item.action}: ${item.family}`).join('\n');
    if (window.confirm(`Update generated drawing layers?\n\n${summary}\n\n${preview.warnings.join('\n')}`)) {
      const result = await applyDrawingCompile(project.id);
      setMessage(`Drawing compile applied. Backup: ${result.backupPath}`);
    }
  };
  const writeExcel = async () => {
    await save();
    const result = await writeWorkbookExcel(project.id);
    setMessage(`Workbook mirror updated. Backup: ${result.backupPath}`);
  };
  return <div className="data-workspace"><WorkspaceToolbar status={status} onSave={() => void save()} onCompile={() => void compile().catch((reason) => setMessage(String(reason)))} onWriteExcel={() => void writeExcel().catch((reason) => setMessage(String(reason)))} onHome={() => window.location.assign(`/app?project=${project.id}`)} onDrawings={() => window.location.assign(`/app?project=${project.id}&mode=editor`)} /><div className="data-message">{message}</div><div ref={containerRef} className="univer-host" /></div>;
}
