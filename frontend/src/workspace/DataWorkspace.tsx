import { useCallback, useEffect, useRef, useState } from 'react';
import { createUniver, type FUniver } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import sheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US';
import { CommandType, LocaleType, type Univer } from '@univerjs/core';
import {
  getDataWorkspace,
  saveDataWorkspace,
  saveProject,
  type WorkbookDocument,
} from '../api/client';
import type { ProjectModel } from '../model/types';
import { fromUniverWorkbook, toUniverWorkbook } from './UniverWorkbookAdapter';
import { updateProjectDrawingsFromWorkbook } from './workspaceProject';

type WorkspaceStatus = 'loading' | 'saved' | 'dirty' | 'saving' | 'conflict' | 'error';

export default function DataWorkspace({ project }: { project: ProjectModel }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<Univer | null>(null);
  const apiRef = useRef<FUniver | null>(null);
  const baseRef = useRef<WorkbookDocument | null>(null);
  const projectRef = useRef(project);
  const readyRef = useRef(false);
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
    if (!document || !base) return null;
    setStatus('saving');
    setMessage('Saving the project-local Data Workspace…');
    try {
      const saved = await saveDataWorkspace(project.id, document, base.revision);
      baseRef.current = saved;
      setStatus('saved');
      setMessage(`Project-local revision ${saved.revision} saved. Excel was not written.`);
      return saved;
    } catch (reason) {
      setStatus(String(reason).toLowerCase().includes('conflict') ? 'conflict' : 'error');
      setMessage(String(reason));
      return null;
    }
  }, [project.id, snapshot]);

  const updateDrawings = useCallback(async () => {
    const document = await save();
    if (!document) return;
    setStatus('saving');
    setMessage('Regenerating app drawing pages from the saved project-local workbook…');
    try {
      const next = updateProjectDrawingsFromWorkbook(projectRef.current, document);
      projectRef.current = await saveProject(next);
      setStatus('saved');
      setMessage('App drawing pages updated. The linked Excel workbook was not written.');
    } catch (reason) {
      setStatus('error');
      setMessage(String(reason));
    }
  }, [save]);

  useEffect(() => {
    projectRef.current = project;
  }, [project]);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    let dirtySubscription: { dispose(): void } | null = null;
    let readyTimer = 0;
    readyRef.current = false;
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
      dirtySubscription = univerAPI.addEvent(univerAPI.Event.CommandExecuted, (event) => {
        if (!readyRef.current || event.type === CommandType.OPERATION) return;
        setStatus((current) => (current === 'loading' || current === 'saving' ? current : 'dirty'));
      });
      readyTimer = window.setTimeout(() => {
        readyRef.current = true;
        setStatus('saved');
      }, 750);
      setStatus('saved');
      setMessage(`${document.sheets.length} schedule sheet${document.sheets.length === 1 ? '' : 's'} loaded from this project.`);
    }).catch((reason) => {
      setMessage(String(reason));
      setStatus('error');
    });
    return () => {
      disposed = true;
      readyRef.current = false;
      window.clearTimeout(readyTimer);
      dirtySubscription?.dispose();
      univerRef.current?.dispose();
      univerRef.current = null;
      apiRef.current = null;
    };
  }, [project.id, project.metadata.projectName]);

  return <div className="data-workspace">
    <header className="data-toolbar">
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}`)}>Project Home</button>
      <strong>Data Workspace</strong>
      <span className={`workspace-status ${status}`}>{status}</span>
      <div />
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&view=files`)}>Project Files</button>
      <button type="button" className="primary" disabled={status === 'loading' || status === 'saving'} onClick={() => void save()}>Save Data Workspace</button>
      <button type="button" disabled={status === 'loading' || status === 'saving'} onClick={() => void updateDrawings()}>Update Drawings</button>
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&mode=editor`)}>Page Editor</button>
    </header>
    <div className="data-message">{message}</div>
    <div ref={containerRef} className="univer-host" aria-label="Project schedule workbook" />
  </div>;
}
