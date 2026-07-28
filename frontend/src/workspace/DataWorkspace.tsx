import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createUniver, type FUniver } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import sheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US';
import { UniverSheetsDataValidationPreset } from '@univerjs/preset-sheets-data-validation';
import dataValidationEnUS from '@univerjs/preset-sheets-data-validation/locales/en-US';
import { UniverSheetsConditionalFormattingPreset } from '@univerjs/preset-sheets-conditional-formatting';
import conditionalFormattingEnUS from '@univerjs/preset-sheets-conditional-formatting/locales/en-US';
import {
  CommandType,
  DataValidationErrorStyle,
  LocaleType,
  type IRange,
  type Univer,
} from '@univerjs/core';
import {
  getDataWorkspace,
  saveDataWorkspace,
  saveProject,
  type WorkbookDocument,
} from '../api/client';
import type { ProjectModel } from '../model/types';
import { fromUniverWorkbook, toUniverWorkbook } from './UniverWorkbookAdapter';
import {
  activeRangeA1,
  detectTableRegions,
  pasteTargetRange,
  protectedOverlap,
  rangeBounds,
} from './workspaceContract';
import { updateProjectDrawingsFromWorkbook } from './workspaceProject';
import { publishWorkspaceState, readWorkspaceState } from './workspaceState';

type WorkspaceStatus =
  | 'loading'
  | 'clean'
  | 'dirty'
  | 'saving'
  | 'project_saved_workbook_sync_pending'
  | 'project_and_workbook_match'
  | 'conflict'
  | 'error';

type NavigationRequest = { url: string; historyBack?: boolean } | null;

const SOURCE_COLOR = '#7F8C8D';
const EXCLUDED_COLOR = '#9AA3AB';
const STATUS_COLORS: Record<string, string> = {
  draft: '#F28C28',
  draft_confirmed: '#76B852',
  public: '#2D7DD2',
  public_confirmed: '#14845A',
};

function workspaceContentSignature(document: WorkbookDocument | null): string {
  if (!document) return '';
  return JSON.stringify(document.sheets);
}

function sharedStateFor(status: WorkspaceStatus): Parameters<typeof publishWorkspaceState>[1] {
  if (status === 'dirty' || status === 'error') return 'DIRTY';
  if (status === 'conflict') return 'CONFLICT';
  if (status === 'project_saved_workbook_sync_pending') return 'PROJECT_SAVED_WORKBOOK_SYNC_PENDING';
  if (status === 'project_and_workbook_match') return 'PROJECT_AND_WORKBOOK_MATCH';
  return 'CLEAN';
}

const WORKSPACE_STATUS_LABELS: Record<WorkspaceStatus, string> = {
  loading: 'LOADING WORKSPACE…',
  clean: 'PROJECT SAVED',
  dirty: 'UNSAVED WORKSPACE EDITS',
  saving: 'SAVING PROJECT…',
  project_saved_workbook_sync_pending: 'PROJECT SAVED · WORKBOOK SYNC PENDING',
  project_and_workbook_match: 'PROJECT SAVED · WORKBOOK SYNCED',
  conflict: 'PROJECT / WORKBOOK CONFLICT',
  error: 'SAVE FAILED',
};

function lifecycleKey(value: unknown): string {
  return String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
}

function isSourceSheet(sheet: WorkbookDocument['sheets'][number] | undefined): boolean {
  return Boolean(sheet && (
    sheet.name.trim().toLowerCase().startsWith('src')
    || String(sheet.role || '').toLowerCase() === 'source'
  ));
}

function validationValues(rule: WorkbookDocument['sheets'][number]['dataValidations'][number]): string[] {
  if (rule.values?.length) return rule.values;
  const formula = String(rule.formula1 || '');
  return formula.startsWith('"') && formula.endsWith('"')
    ? formula.slice(1, -1).split(',').map((item) => item.trim())
    : [];
}

function indexTabStates(document: WorkbookDocument): Map<string, { publish: string; lifecycle: string }> {
  const index = document.sheets.find((sheet) => sheet.name.trim().toUpperCase() === '00_INDEX');
  const result = new Map<string, { publish: string; lifecycle: string }>();
  if (!index) return result;
  const rows = new Map<number, Map<number, string>>();
  Object.entries(index.cells).forEach(([coordinate, cell]) => {
    const bounds = rangeBounds(coordinate);
    if (!bounds) return;
    const value = String(cell.v ?? '').trim();
    if (value) (rows.get(bounds.startRow) || rows.set(bounds.startRow, new Map()).get(bounds.startRow)!)
      .set(bounds.startColumn, value);
  });
  let headerRow = -1;
  let headers = new Map<number, string>();
  rows.forEach((values, row) => {
    const labels = [...values.values()].map((value) => value.toLowerCase());
    if (labels.some((value) => value === 'sheet tab' || value === 'sheet name')
      && labels.some((value) => value.includes('include') || value === 'publish')) {
      headerRow = row;
      headers = new Map([...values.entries()].map(([column, value]) => [column, value.toLowerCase()]));
    }
  });
  if (headerRow < 0) return result;
  const columnFor = (...names: string[]) =>
    [...headers.entries()].find(([, value]) => names.includes(value))?.[0];
  const tabColumn = columnFor('sheet tab', 'sheet name', 'tab');
  const includeColumn = columnFor('include', 'include / publish', 'publish');
  const lifecycleColumn = columnFor('lifecycle', 'issue status');
  if (tabColumn === undefined || includeColumn === undefined) return result;
  rows.forEach((values, row) => {
    if (row <= headerRow) return;
    const tab = values.get(tabColumn);
    if (!tab) return;
    result.set(tab.toLowerCase(), {
      publish: String(values.get(includeColumn) || '').trim().toUpperCase(),
      lifecycle: lifecycleKey(values.get(lifecycleColumn ?? -1)),
    });
  });
  return result;
}

function mergeLocales() {
  return {
    ...sheetsCoreEnUS,
    ...dataValidationEnUS,
    ...conditionalFormattingEnUS,
  };
}

function applyTabColors(api: FUniver, document: WorkbookDocument): void {
  const workbook = api.getActiveWorkbook();
  if (!workbook) return;
  const tabStates = indexTabStates(document);
  document.sheets.forEach((sheet) => {
    const worksheet = workbook.getSheetBySheetId(sheet.id);
    if (!worksheet) return;
    const state = tabStates.get(sheet.name.toLowerCase());
    const publish = state?.publish || sheet.sourceSetup?.publish || 'YES';
    const color = publish !== 'YES'
      ? EXCLUDED_COLOR
      : isSourceSheet(sheet)
        ? SOURCE_COLOR
        : STATUS_COLORS[state?.lifecycle || 'draft'] || sheet.tabColor || STATUS_COLORS.draft;
    worksheet.setTabColor(color);
  });
}

export default function DataWorkspace({ project }: { project: ProjectModel }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<Univer | null>(null);
  const apiRef = useRef<FUniver | null>(null);
  const baseRef = useRef<WorkbookDocument | null>(null);
  const projectRef = useRef(project);
  const readyRef = useRef(false);
  const statusRef = useRef<WorkspaceStatus>('loading');
  const instanceIdRef = useRef(crypto.randomUUID());
  const allowHistoryRef = useRef(false);
  const subscriptionsRef = useRef<Array<{ dispose(): void }>>([]);
  const confirmedSignatureRef = useRef('');
  const currentSignatureRef = useRef('');
  const editRevisionRef = useRef(0);
  const confirmedStatusRef = useRef<WorkspaceStatus>('clean');
  const [status, setStatusState] = useState<WorkspaceStatus>('loading');
  const [message, setMessage] = useState('Loading project schedules…');
  const [activeSheetId, setActiveSheetId] = useState('');
  const [activeRange, setActiveRange] = useState<IRange | null>(null);
  const [navigation, setNavigation] = useState<NavigationRequest>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const setStatus = useCallback((next: WorkspaceStatus) => {
    statusRef.current = next;
    setStatusState(next);
  }, []);

  const signal = useCallback((state: Parameters<typeof publishWorkspaceState>[1]) => {
    publishWorkspaceState(project.id, state, instanceIdRef.current, {
      revision: baseRef.current?.revision || 0,
      signature: currentSignatureRef.current,
      dirtyDomains: state === 'DIRTY' || state === 'CONFLICT' ? ['Data Workspace cells'] : [],
    });
  }, [project.id]);

  const activeDocumentSheet = useMemo(
    () => baseRef.current?.sheets.find((sheet) => sheet.id === activeSheetId),
    [activeSheetId, status, previewOpen],
  );
  const activeIsSource = isSourceSheet(activeDocumentSheet);

  const snapshot = useCallback(() => {
    const base = baseRef.current;
    const workbook = apiRef.current?.getActiveWorkbook();
    return base && workbook ? fromUniverWorkbook(workbook.getSnapshot(), base) : null;
  }, []);

  const markDirty = useCallback((reason = 'Unsaved Data Workspace edits.') => {
    if (!readyRef.current) return;
    const current = snapshot();
    const signature = workspaceContentSignature(current);
    currentSignatureRef.current = signature;
    if (signature === confirmedSignatureRef.current) {
      setStatus(confirmedStatusRef.current);
      setMessage('Current workspace content matches the last confirmed local save.');
      signal(sharedStateFor(confirmedStatusRef.current));
      return;
    }
    editRevisionRef.current += 1;
    setStatus('dirty');
    setMessage(reason);
    signal('DIRTY');
  }, [setStatus, signal, snapshot]);

  const updateSheetMetadata = useCallback((
    updater: (sheet: WorkbookDocument['sheets'][number]) => void,
  ) => {
    const base = baseRef.current;
    if (!base || !activeSheetId) return;
    const sheet = base.sheets.find((item) => item.id === activeSheetId);
    if (!sheet) return;
    updater(sheet);
    markDirty('Source-sheet layout settings changed. Save Data Workspace to keep them.');
    setPreviewOpen((current) => current);
  }, [activeSheetId, markDirty]);

  const applyWorkbookRules = useCallback((api: FUniver, document: WorkbookDocument) => {
    const workbook = api.getActiveWorkbook();
    if (!workbook) return;
    document.sheets.forEach((sheet) => {
      const worksheet = workbook.getSheetBySheetId(sheet.id);
      if (!worksheet) return;
      sheet.dataValidations.forEach((rule) => {
        if (String(rule.type).toLowerCase() !== 'list') return;
        const values = validationValues(rule);
        if (!values.length) return;
        const validation = api.newDataValidation()
          .requireValueInList(values, false, rule.showDropdown !== false)
          .setAllowBlank(rule.allowBlank !== false)
          .setOptions({
            showErrorMessage: rule.strict !== false,
            errorStyle: DataValidationErrorStyle.STOP,
            error: rule.error || `Choose one of: ${values.join(', ')}.`,
            errorTitle: rule.errorTitle || 'Invalid value',
          })
          .build();
        rule.ranges.forEach((range) => worksheet.getRange(range).setDataValidation(validation));
      });
      sheet.conditionalFormats.forEach((raw) => {
        const rule = raw as {
          ranges?: string[];
          type?: string;
          value?: string;
          formula?: string[];
          fill?: string;
          fontColor?: string;
        };
        const ranges = (rule.ranges || []).map((value) => worksheet.getRange(value).getRange());
        if (!ranges.length || !rule.fill) return;
        const rootBuilder = worksheet.newConditionalFormattingRule();
        let builder;
        if (rule.type === 'formula' && rule.formula?.[0]) {
          builder = rootBuilder.whenFormulaSatisfied(rule.formula[0]);
        } else if (rule.type === 'text' && rule.value !== undefined) {
          builder = rootBuilder.whenTextEqualTo(rule.value);
        } else {
          return;
        }
        builder.setRanges(ranges).setBackground(rule.fill);
        if (rule.fontColor) builder.setFontColor(rule.fontColor);
        worksheet.addConditionalFormattingRule(builder.build());
      });
    });
    applyTabColors(api, document);
  }, []);

  const save = useCallback(async () => {
    const document = snapshot();
    const base = baseRef.current;
    const workbook = apiRef.current?.getActiveWorkbook();
    if (!document || !base || !workbook) return null;
    const validationErrors = await workbook.getAllDataValidationErrorAsync();
    if (validationErrors.length) {
      setStatus('dirty');
      setMessage('Save blocked: one or more strict dropdown cells contain an invalid value.');
      signal('DIRTY');
      return null;
    }
    setStatus('saving');
    setMessage('Saving the project-local Data Workspace…');
    const submittedSignature = workspaceContentSignature(document);
    const submittedEditRevision = editRevisionRef.current;
    try {
      const saved = await saveDataWorkspace(project.id, document, base.revision);
      const current = snapshot();
      const currentSignature = workspaceContentSignature(current);
      currentSignatureRef.current = currentSignature;
      confirmedSignatureRef.current = submittedSignature;
      if (currentSignature !== submittedSignature || editRevisionRef.current !== submittedEditRevision) {
        baseRef.current = current
          ? { ...current, revision: saved.revision, updatedAt: saved.updatedAt }
          : saved;
        setStatus('dirty');
        setMessage(`Project-local revision ${saved.revision} saved, but newer Data Workspace edits are still unsaved.`);
        signal('DIRTY');
        return null;
      }
      baseRef.current = saved;
      confirmedStatusRef.current = 'project_saved_workbook_sync_pending';
      setStatus('project_saved_workbook_sync_pending');
      setMessage(`Project-local revision ${saved.revision} saved. Excel sync remains pending.`);
      signal('PROJECT_SAVED_WORKBOOK_SYNC_PENDING');
      return saved;
    } catch (reason) {
      const conflict = String(reason).toLowerCase().includes('conflict');
      setStatus(conflict ? 'conflict' : 'error');
      setMessage(`Save failed; your grid is still in memory. ${String(reason)}`);
      signal(conflict ? 'CONFLICT' : 'DIRTY');
      return null;
    }
  }, [project.id, setStatus, signal, snapshot]);

  const updateDrawings = useCallback(async () => {
    let document = snapshot();
    if (!document) return;
    if (statusRef.current === 'dirty' || statusRef.current === 'conflict' || statusRef.current === 'error') {
      document = await save();
      if (!document) return;
    }
    if (statusRef.current !== 'project_saved_workbook_sync_pending'
      && statusRef.current !== 'clean'
      && statusRef.current !== 'project_and_workbook_match') {
      setMessage('Save the local Data Workspace before updating drawings.');
      return;
    }
    setStatus('saving');
    setMessage('Regenerating drawing pages from the saved local workbook…');
    try {
      const next = updateProjectDrawingsFromWorkbook(projectRef.current, document);
      next.dataWorkspace = {
        ...(next.dataWorkspace || {}),
        revision: document.revision,
        appliedRevision: document.revision,
      };
      projectRef.current = await saveProject(next);
      setStatus('project_saved_workbook_sync_pending');
      setMessage('Drawing pages updated. The linked Excel workbook was not written.');
      signal('PROJECT_SAVED_WORKBOOK_SYNC_PENDING');
    } catch (reason) {
      setStatus('project_saved_workbook_sync_pending');
      setMessage(`Drawing update failed; Excel was not written. ${String(reason)}`);
      signal('PROJECT_SAVED_WORKBOOK_SYNC_PENDING');
    }
  }, [save, setStatus, signal, snapshot]);

  const finishNavigation = useCallback((request: NavigationRequest) => {
    if (!request) return;
    const current = statusRef.current;
    const published = current === 'dirty' || current === 'conflict'
      ? sharedStateFor(confirmedStatusRef.current)
      : sharedStateFor(current);
    signal(published);
    allowHistoryRef.current = true;
    if (request.historyBack) window.history.back();
    else window.location.assign(request.url);
  }, [signal]);

  const requestNavigation = useCallback((url: string, historyBack = false) => {
    if (statusRef.current === 'dirty' || statusRef.current === 'conflict' || statusRef.current === 'error') {
      setNavigation({ url, historyBack });
      return;
    }
    finishNavigation({ url, historyBack });
  }, [finishNavigation]);

  useEffect(() => {
    projectRef.current = project;
  }, [project]);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (statusRef.current !== 'dirty' && statusRef.current !== 'conflict' && statusRef.current !== 'error') return;
      event.preventDefault();
      event.returnValue = '';
    };
    const onPopState = () => {
      if (allowHistoryRef.current) return;
      if (statusRef.current === 'dirty' || statusRef.current === 'conflict' || statusRef.current === 'error') {
        window.history.pushState({ s360WorkspaceGuard: true }, '');
        setNavigation({ url: `/app?project=${project.id}`, historyBack: true });
      }
    };
    window.history.pushState({ s360WorkspaceGuard: true }, '');
    window.addEventListener('beforeunload', onBeforeUnload);
    window.addEventListener('popstate', onPopState);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      window.removeEventListener('popstate', onPopState);
    };
  }, [project.id]);

  useEffect(() => {
    const heartbeat = window.setInterval(() => {
      const state = statusRef.current;
      if (state === 'loading' || state === 'saving') return;
      signal(sharedStateFor(state));
    }, 5_000);
    return () => window.clearInterval(heartbeat);
  }, [signal]);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    let readyTimer = 0;
    readyRef.current = false;
    getDataWorkspace(project.id).then((document) => {
      if (disposed || !containerRef.current) return;
      baseRef.current = document;
      confirmedSignatureRef.current = workspaceContentSignature(document);
      currentSignatureRef.current = confirmedSignatureRef.current;
      editRevisionRef.current = 0;
      const { univer, univerAPI } = createUniver({
        locale: LocaleType.EN_US,
        locales: { [LocaleType.EN_US]: mergeLocales() },
        presets: [
          UniverSheetsCorePreset({
            container: containerRef.current,
            header: true,
            toolbar: true,
            formulaBar: true,
            footer: { sheetBar: true, statisticBar: true, menus: true, zoomSlider: true },
          }),
          UniverSheetsDataValidationPreset({ showEditOnDropdown: true }),
          UniverSheetsConditionalFormattingPreset(),
        ],
      });
      univerRef.current = univer;
      apiRef.current = univerAPI;
      univer.createUniverSheet(toUniverWorkbook(document, project.metadata.projectName, project.id));
      applyWorkbookRules(univerAPI, document);
      const active = univerAPI.getActiveWorkbook()?.getActiveSheet();
      setActiveSheetId(active?.getSheetId() || document.sheets[0]?.id || '');
      setActiveRange(active?.getActiveRange()?.getRange() || null);

      subscriptionsRef.current = [
        univerAPI.addEvent(univerAPI.Event.BeforeSheetEditStart, (event) => {
          const sheet = baseRef.current?.sheets.find((item) => item.id === event.worksheet.getSheetId());
          const target = {
            startRow: event.row,
            endRow: event.row,
            startColumn: event.column,
            endColumn: event.column,
          };
          const blocked = protectedOverlap(target, sheet?.protectedRanges || []);
          if (!blocked) return;
          event.cancel = true;
          setMessage(`Locked system cell (${blocked}) cannot be overwritten.`);
        }),
        univerAPI.addEvent(univerAPI.Event.BeforeClipboardPaste, (event) => {
          const sheet = baseRef.current?.sheets.find((item) => item.id === event.worksheet.getSheetId());
          const selection = event.worksheet.getActiveRange()?.getRange();
          if (!selection) return;
          const target = pasteTargetRange(selection, event.text || '');
          const blocked = protectedOverlap(target, sheet?.protectedRanges || []);
          if (!blocked) return;
          event.cancel = true;
          setMessage(`Paste rejected atomically: the target overlaps locked system cells (${blocked}).`);
        }),
        univerAPI.addEvent(univerAPI.Event.BeforeCommandExecute, (event) => {
          if (!readyRef.current) return;
          const id = event.id.toLowerCase();
          if (!/(insert|delete|remove).*(row|column)|(row|column).*(insert|delete|remove)/.test(id)) return;
          const worksheet = univerAPI.getActiveWorkbook()?.getActiveSheet();
          const sheet = baseRef.current?.sheets.find((item) => item.id === worksheet?.getSheetId());
          if (!isSourceSheet(sheet)) return;
          const activeCell = worksheet?.getActiveCell()?.getRange();
          if (activeCell && activeCell.startRow >= 2) return;
          event.cancel = true;
          setMessage('Rows or columns may be inserted or deleted only from the editable canvas beginning at A3.');
        }),
        univerAPI.addEvent(univerAPI.Event.ActiveSheetChanged, (event) => {
          setActiveSheetId(event.activeSheet.getSheetId());
          setActiveRange(event.activeSheet.getActiveRange()?.getRange() || null);
        }),
        univerAPI.addEvent(univerAPI.Event.SelectionChanged, (event) => {
          setActiveSheetId(event.worksheet.getSheetId());
          setActiveRange(event.selections[0] || null);
        }),
        univerAPI.addEvent(univerAPI.Event.CommandExecuted, (event) => {
          if (!readyRef.current || event.type === CommandType.OPERATION) return;
          window.setTimeout(() => {
            markDirty();
            const current = snapshot();
            if (current) applyTabColors(univerAPI, current);
          }, 0);
        }),
      ];
      readyTimer = window.setTimeout(() => {
        readyRef.current = true;
        const shared = readWorkspaceState(project.id);
        const workbookMatches = (project.workbookSync?.status || project.workbookSync?.state) === 'in_sync';
        if (shared?.state === 'DIRTY' && shared.instanceId !== instanceIdRef.current) {
          setStatus('conflict');
          setMessage('Another Data Workspace instance reports unsaved edits. Resolve that instance before saving here.');
          signal('CONFLICT');
        } else if (workbookMatches) {
          confirmedStatusRef.current = 'project_and_workbook_match';
          setStatus('project_and_workbook_match');
          setMessage(`${document.sheets.length} project sheet${document.sheets.length === 1 ? '' : 's'} loaded. Saved project and workbook signatures match.`);
          signal('PROJECT_AND_WORKBOOK_MATCH');
        } else {
          const syncPending = project.workbookSync?.status === 'app_changed'
            || project.workbookSync?.status === 'pending'
            || Boolean(project.workbookSync?.warning);
          confirmedStatusRef.current = syncPending ? 'project_saved_workbook_sync_pending' : 'clean';
          setStatus(confirmedStatusRef.current);
          setMessage(
            syncPending
              ? `${document.sheets.length} project sheets loaded. Local project is saved; Excel sync remains pending.`
              : `${document.sheets.length} project sheet${document.sheets.length === 1 ? '' : 's'} loaded. Excel was not written.`,
          );
          signal(sharedStateFor(confirmedStatusRef.current));
        }
      }, 750);
    }).catch((reason) => {
      setMessage(String(reason));
      setStatus('error');
    });
    return () => {
      disposed = true;
      readyRef.current = false;
      window.clearTimeout(readyTimer);
      subscriptionsRef.current.forEach((subscription) => subscription.dispose());
      subscriptionsRef.current = [];
      univerRef.current?.dispose();
      univerRef.current = null;
      apiRef.current = null;
    };
  }, [
    applyWorkbookRules,
    markDirty,
    project.id,
    project.metadata.projectName,
    project.workbookSync?.state,
    project.workbookSync?.status,
    setStatus,
    signal,
    snapshot,
  ]);

  const autoDetect = () => {
    const current = snapshot()?.sheets.find((sheet) => sheet.id === activeSheetId);
    if (!current) return;
    const regions = detectTableRegions(current);
    updateSheetMetadata((sheet) => { sheet.tableRegions = regions; });
    setMessage(`${regions.length} separate table region${regions.length === 1 ? '' : 's'} detected without changing source cells.`);
  };

  const addRegion = () => {
    if (!activeRange || activeRange.startRow < 2) {
      setMessage('Select a range in the editable source canvas beginning at A3.');
      return;
    }
    updateSheetMetadata((sheet) => {
      const index = sheet.tableRegions.length + 1;
      sheet.tableRegions.push({
        id: `table-${crypto.randomUUID().slice(0, 8)}`,
        range: activeRangeA1(activeRange),
        label: `Table ${index}`,
      });
    });
  };

  const removeRegion = (id?: string) => updateSheetMetadata((sheet) => {
    const target = id || sheet.tableRegions[sheet.tableRegions.length - 1]?.id;
    sheet.tableRegions = sheet.tableRegions.filter((region) => region.id !== target);
  });

  const statusLabel = WORKSPACE_STATUS_LABELS[status];
  const setup = activeDocumentSheet?.sourceSetup;

  return <div className="data-workspace">
    <header className="data-toolbar">
      <button type="button" data-help-id="nav.projectHome" onClick={() => requestNavigation(`/app?project=${project.id}`)}>Project Home</button>
      <strong>Data Workspace</strong>
      <span
        className={`workspace-status ${status}`}
        data-help-id={status === 'dirty' ? 'workspace.unsavedBadge' : status === 'error' ? 'save.retry' : status === 'conflict' ? 'status.conflict' : status === 'project_saved_workbook_sync_pending' ? 'status.syncPending' : 'workspace.savedBadge'}
        data-status-chip="true"
      >{statusLabel}</span>
      <div />
      <button type="button" data-help-id="project.openFolder" onClick={() => requestNavigation(`/app?project=${project.id}&view=files`)}>Project Files</button>
      <span
        className="s360-tooltip-disabled-wrapper"
        tabIndex={status === 'loading' || status === 'saving' ? 0 : -1}
        data-help-id="workspace.save"
        data-disabled-reason={status === 'loading' ? 'Wait for Data Workspace to finish loading.' : status === 'saving' ? 'The current local save is still in flight.' : undefined}
      >
        <button type="button" data-help-id="workspace.save" className="primary" disabled={status === 'loading' || status === 'saving'} onClick={() => void save()}>Save Workspace Edits</button>
      </span>
      <button type="button" data-help-id="save.workspace" disabled={status === 'loading' || status === 'saving'} onClick={() => void updateDrawings()}>Update Drawings</button>
      <button type="button" data-help-id="view.canvas" onClick={() => requestNavigation(`/app?project=${project.id}&mode=editor`)}>Page Editor</button>
    </header>
    <div className="data-message">{message}</div>
    <main className={`data-workspace-main ${activeIsSource ? 'with-setup' : ''}`}>
      <div
        ref={containerRef}
        className="univer-host"
        aria-label="Project schedule workbook"
        data-help-id="workspace.cell"
        data-tooltip-body={`Cell ${activeRange ? activeRangeA1(activeRange) : 'selection'}. Click to select; double-click or press Enter to edit. Current changes save to the local Singh360 project with Save Workspace Edits and reach Excel only through Save + Write Excel.`}
      />
      {activeIsSource && activeDocumentSheet && <aside className="sheet-setup-panel" aria-label="Sheet Setup">
        <h2>Sheet Setup <span className="lock-indicator">Locked</span></h2>
        <p className="sheet-authority">Authority: {setup?.authority || '00_INDEX'}</p>
        <dl>
          <dt>Sheet</dt><dd>{setup?.sheetCode || activeDocumentSheet.name}</dd>
          <dt>Title</dt><dd>{setup?.title || activeDocumentSheet.name}</dd>
          <dt>Purpose</dt><dd>{setup?.purpose}</dd>
          <dt>Editable canvas</dt><dd>A3 onward</dd>
        </dl>
        <div className="source-actions">
          <button type="button" onClick={autoDetect}>Auto-Detect Tables</button>
          <button type="button" onClick={addRegion}>Add Table Region</button>
          <button type="button" disabled={!activeDocumentSheet.tableRegions.length} onClick={() => removeRegion()}>Remove Table Region</button>
          <button type="button" onClick={() => setPreviewOpen(true)}>Preview Drawing Layout</button>
        </div>
        <label>Page layout
          <select value={activeDocumentSheet.tableLayout} onChange={(event) => updateSheetMetadata((sheet) => {
            sheet.tableLayout = event.target.value as typeof sheet.tableLayout;
          })}>
            <option value="single">Single full-width</option>
            <option value="side_by_side">Two tables side-by-side</option>
            <option value="stacked">Stacked</option>
          </select>
        </label>
        <h3>Table regions</h3>
        <ul className="table-region-list">
          {activeDocumentSheet.tableRegions.map((region) => <li key={region.id}>
            <span>{region.label}: {region.range}</span>
            <button type="button" aria-label={`Remove ${region.label}`} onClick={() => removeRegion(region.id)}>×</button>
          </li>)}
          {!activeDocumentSheet.tableRegions.length && <li>No regions defined.</li>}
        </ul>
        <h3>Page annotations</h3>
        {(['right', 'bottom'] as const).map((placement) => <label key={placement}>
          {placement === 'right' ? 'Right-side note' : 'Bottom note'}
          <textarea
            value={activeDocumentSheet.annotations.find((item) => item.placement === placement)?.text || ''}
            onChange={(event) => updateSheetMetadata((sheet) => {
              const other = sheet.annotations.filter((item) => item.placement !== placement);
              sheet.annotations = event.target.value
                ? [...other, { id: `note-${placement}`, placement, text: event.target.value }]
                : other;
            })}
          />
        </label>)}
        {!!setup?.metadata?.length && <>
          <h3>Template metadata</h3>
          <div className="setup-metadata">
            {setup.metadata.map((item) => <p key={`${item.field}-${item.value}`}><strong>{item.field}</strong><span>{item.value}</span></p>)}
          </div>
        </>}
      </aside>}
    </main>
    {navigation && <div className="workspace-modal-backdrop" role="presentation">
      <section className="workspace-modal" role="dialog" aria-modal="true" aria-labelledby="unsaved-title">
        <h2 id="unsaved-title">Unsaved Data Workspace edits</h2>
        <p>Save the project-local grid, discard these in-memory edits, or cancel navigation.</p>
        <div>
          <button type="button" className="primary" onClick={() => void save().then((saved) => {
            if (saved) finishNavigation(navigation);
          })}>Save</button>
          <button type="button" onClick={() => finishNavigation(navigation)}>Discard</button>
          <button type="button" onClick={() => setNavigation(null)}>Cancel</button>
        </div>
      </section>
    </div>}
    {previewOpen && activeDocumentSheet && <div className="workspace-modal-backdrop" role="presentation">
      <section className="workspace-modal layout-preview" role="dialog" aria-modal="true" aria-labelledby="preview-title">
        <h2 id="preview-title">Drawing layout preview</h2>
        <p>{setup?.title || activeDocumentSheet.name}</p>
        <div className={`layout-preview-canvas ${activeDocumentSheet.tableLayout}`}>
          <div className="layout-preview-tables">
            {activeDocumentSheet.tableRegions.map((region) => <div key={region.id} className="layout-preview-table">
              <strong>{region.label}</strong><span>{region.range}</span>
            </div>)}
          </div>
          {activeDocumentSheet.annotations.find((item) => item.placement === 'right')?.text && <aside>{activeDocumentSheet.annotations.find((item) => item.placement === 'right')?.text}</aside>}
          {activeDocumentSheet.annotations.find((item) => item.placement === 'bottom')?.text && <footer>{activeDocumentSheet.annotations.find((item) => item.placement === 'bottom')?.text}</footer>}
        </div>
        <button type="button" onClick={() => setPreviewOpen(false)}>Close Preview</button>
      </section>
    </div>}
  </div>;
}
