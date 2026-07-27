import { useCallback, useEffect, useRef, useState } from 'react';
import { createUniver, type FUniver } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import sheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US';
import { LocaleType, type Univer } from '@univerjs/core';
import { getDataWorkspace, saveDataWorkspace, type WorkbookDocument } from '../api/client';
import type { ProjectModel } from '../model/types';
import { fromUniverWorkbook, toUniverWorkbook } from './UniverWorkbookAdapter';

type WorkspaceStatus = 'loading' | 'saved' | 'dirty' | 'saving' | 'conflict' | 'error';

export default function DataWorkspace({ project }: { project: ProjectModel }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<Univer | null>(null);
  const apiRef = useRef<FUniver | null>(null);
  const baseRef = useRef<WorkbookDocument | null>(null);
  const [status, setStatus] = useState<WorkspaceStatus>('loading');
  const [message, setMessage] = useState('Loading project schedules…');

  const snapshot = useCallback(() => {
    const base = baseRef.current;
    const workbook = apiRef.current?.getActiveWorkbook();
    return base && workbook ? fromUniverWorkbook(workbook.getSnapshot(), base) : null;
  }, []);

  const save = useCallback(async () => {
    const document = snapshot();
    const base = baseRef.current;
    if (!document || !base) return;
    setStatus('saving');
    setMessage('Saving the project-local Data Workspace…');
    try {
      const saved = await saveDataWorkspace(project.id, document, base.revision);
      baseRef.current = saved;
      setStatus('saved');
      setMessage(`Project-local revision ${saved.revision} saved. Excel was not written.`);
    } catch (reason) {
      setStatus(String(reason).toLowerCase().includes('conflict') ? 'conflict' : 'error');
      setMessage(String(reason));
    }
  }, [project.id, snapshot]);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    getDataWorkspace(project.id).then((document) => {
      if (disposed || !containerRef.current) return;
      baseRef.current = document;
      const { univer, univerAPI } = createUniver({
        locale: LocaleType.EN_US,
        locales: { [LocaleType.EN_US]: sheetsCoreEnUS },
        presets: [UniverSheetsCorePreset({
          container: containerRef.current,
          header: true,
          toolbar: true,
          formulaBar: true,
          footer: { sheetBar: true, statisticBar: true, menus: true, zoomSlider: true },
        })],
      });
      univerRef.current = univer;
      apiRef.current = univerAPI;
      univer.createUniverSheet(toUniverWorkbook(document, project.metadata.projectName, project.id));
      setStatus('saved');
      setMessage(`${document.sheets.length} schedule sheet${document.sheets.length === 1 ? '' : 's'} loaded from this project.`);
    }).catch((reason) => {
      setMessage(String(reason));
      setStatus('error');
    });
    return () => {
      disposed = true;
      univerRef.current?.dispose();
      univerRef.current = null;
      apiRef.current = null;
    };
  }, [project.id, project.metadata.projectName]);

  useEffect(() => {
    const markDirty = () => {
      if (status === 'saved') setStatus('dirty');
    };
    window.addEventListener('keydown', markDirty);
    window.addEventListener('paste', markDirty);
    return () => {
      window.removeEventListener('keydown', markDirty);
      window.removeEventListener('paste', markDirty);
    };
  }, [status]);

  return <div className="data-workspace">
    <header className="data-toolbar">
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}`)}>Project Home</button>
      <strong>Data Workspace</strong>
      <span className={`workspace-status ${status}`}>{status}</span>
      <div />
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&view=files`)}>Project Files</button>
      <button type="button" className="primary" onClick={() => void save()}>Save Data Workspace</button>
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&mode=editor`)}>Page Editor</button>
    </header>
    <div className="data-message">{message}</div>
    <div ref={containerRef} className="univer-host" aria-label="Project schedule workbook" />
  </div>;
}
