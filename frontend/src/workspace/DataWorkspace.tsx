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
import { fromUniverWorkbook, letters, toUniverWorkbook } from './UniverWorkbookAdapter';
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
  | 'conflict'
  | 'error';

type NavigationRequest = { url: string; historyBack?: boolean } | null;
type WorkspaceValidationError = {
  sheetName: string;
  row: number;
  column: number;
  ruleId: string;
  inputValue: string | number | boolean | null;
};

const SOURCE_COLOR = '#7F8C8D';
const EXCLUDED_COLOR = '#9AA3AB';
const STATUS_COLORS: Record<string, string> = {
  draft: '#F28C28',
  draft_confirmed: '#76B852',
  public: '#2D7DD2',
  public_confirmed: '#14845A',
};
const TAB_COLOR_COMMAND_IDS = new Set([
  'sheet.command.set-tab-color',
  'sheet.mutation.set-tab-color',
]);

function workspaceContentSignature(document: WorkbookDocument | null): string {
  if (!document) return '';
  return JSON.stringify(document.sheets);
}

function validationAddress(error: WorkspaceValidationError): string {
  return `${letters(error.column)}${error.row + 1}`;
}

function validationErrorKey(error: WorkspaceValidationError): string {
  return [
    error.sheetName,
    validationAddress(error),
    error.ruleId,
    JSON.stringify(error.inputValue),
  ].join('|');
}

function strictValidationDetail(
  document: WorkbookDocument,
  error: WorkspaceValidationError,
): string | null {
  const sheet = document.sheets.find((item) => item.name === error.sheetName);
  if (!sheet) return null;
  const address = validationAddress(error);
  const rule = sheet.dataValidations.find((item) => {
    if (item.strict === false) return false;
    return item.ranges.some((range) => {
      const bounds = rangeBounds(range);
      return Boolean(bounds
        && error.row >= bounds.startRow
        && error.row <= bounds.endRow
        && error.column >= bounds.startColumn
        && error.column <= bounds.endColumn);
    });
  });
  if (!rule) return null;
  const ranges = rule.ranges.map((range) => `${error.sheetName}!${range}`).join(', ');
  const allowed = validationValues(rule);
  return `${error.sheetName}!${address} (range ${ranges}; value ${JSON.stringify(error.inputValue)}`
    + `${allowed.length ? `; choose ${allowed.join(', ')}` : ''})`;
}

function sharedStateFor(status: WorkspaceStatus): Parameters<typeof publishWorkspaceState>[1] {
  if (status === 'dirty' || status === 'error') return 'DIRTY';
  if (status === 'conflict') return 'CONFLICT';
  return 'CLEAN';
}

const WORKSPACE_STATUS_LABELS: Record<WorkspaceStatus, string> = {
  loading: 'LOADING WORKSPACE…',
  clean: 'PROJECT SAVED',
  dirty: 'UNSAVED WORKSPACE EDITS',
  saving: 'SAVING PROJECT…',
  conflict: 'WORKSPACE EDIT CONFLICT',
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

function tabColorKey(value: string | undefined): string {
  return String(value || '').trim().replace(/^#/, '').slice(-6).toUpperCase();
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
    // setTabColor emits CommandExecuted. Reapplying an unchanged color from
    // that event creates an unbounded command/snapshot loop and freezes the UI.
    if (tabColorKey(worksheet.getTabColor()) !== tabColorKey(color)) {
      worksheet.setTabColor(color);
    }
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
  const baselineValidationErrorsRef = useRef<Set<string>>(new Set());
  const [status, setStatusState] = useState<WorkspaceStatus>('loading');
  const [message, setMessage] = useState('Loading project schedules…');
  const [activeSheetId, setActiveSheetId] = useState('');
  const [activeRange, setActiveRange] = useState<IRange | null>(null);
  const [navigation, setNavigation] = useState<NavigationRequest>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [workspaceView, setWorkspaceView] = useState<'drawing' | 'all'>('drawing');
  const [documentSheets, setDocumentSheets] = useState<WorkbookDocument['sheets']>([]);
  const [workspaceReady, setWorkspaceReady] = useState(false);

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
  const drawingSheets = useMemo(
    () => documentSheets
      .filter((sheet) => sheet.workspaceSection === 'drawing')
      .sort((left, right) => (left.drawingOrder || 0) - (right.drawingOrder || 0)),
    [documentSheets],
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

  const restoreDocument = useCallback(async (
    document: WorkbookDocument,
    nextStatus: WorkspaceStatus,
  ) => {
    const api = apiRef.current;
    if (!api) return;
    readyRef.current = false;
    setWorkspaceReady(false);
    const current = api.getActiveWorkbook();
    if (current) api.disposeUnit(current.getId());
    api.createWorkbook(toUniverWorkbook(
      document,
      project.metadata.projectName,
      project.id,
    ));
    applyWorkbookRules(api, document);
    baseRef.current = document;
    setDocumentSheets(document.sheets);
    const signature = workspaceContentSignature(document);
    confirmedSignatureRef.current = signature;
    currentSignatureRef.current = signature;
    editRevisionRef.current = 0;
    const active = api.getActiveWorkbook()?.getActiveSheet();
    setActiveSheetId(active?.getSheetId() || document.sheets[0]?.id || '');
    setActiveRange(active?.getActiveRange()?.getRange() || null);
    const errors = await api.getActiveWorkbook()?.getAllDataValidationErrorAsync() || [];
    baselineValidationErrorsRef.current = new Set(
      (errors as WorkspaceValidationError[]).map(validationErrorKey),
    );
    confirmedStatusRef.current = nextStatus;
    setStatus(nextStatus);
    signal(sharedStateFor(nextStatus));
    readyRef.current = true;
    setWorkspaceReady(true);
  }, [
    applyWorkbookRules,
    project.id,
    project.metadata.projectName,
    setStatus,
    signal,
  ]);

  const save = useCallback(async () => {
    const document = snapshot();
    const base = baseRef.current;
    const workbook = apiRef.current?.getActiveWorkbook();
    if (!document || !base || !workbook) return null;
    const validationErrors = (
      await workbook.getAllDataValidationErrorAsync()
    ) as WorkspaceValidationError[];
    const newlyInvalid = validationErrors
      .filter((error) => !baselineValidationErrorsRef.current.has(validationErrorKey(error)))
      .map((error) => strictValidationDetail(document, error))
      .filter((detail): detail is string => Boolean(detail));
    if (newlyInvalid.length) {
      setStatus('dirty');
      setMessage(
        `Save blocked by newly introduced strict-dropdown values: ${newlyInvalid.join('; ')}. `
        + 'Choose an allowed value or revert the listed cell.',
      );
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
      await restoreDocument(saved, 'clean');
      setMessage(`Project-local revision ${saved.revision} saved.`);
      return saved;
    } catch (reason) {
      const conflict = String(reason).toLowerCase().includes('conflict');
      setStatus(conflict ? 'conflict' : 'error');
      setMessage(`Save failed; your grid is still in memory. ${String(reason)}`);
      signal(conflict ? 'CONFLICT' : 'DIRTY');
      return null;
    }
  }, [project.id, restoreDocument, setStatus, signal, snapshot]);

  const updateDrawings = useCallback(async () => {
    let document = snapshot();
    if (!document) return;
    if (statusRef.current === 'dirty' || statusRef.current === 'conflict' || statusRef.current === 'error') {
      document = await save();
      if (!document) return;
    }
    if (statusRef.current !== 'clean') {
      setMessage('Save the local Data Workspace before updating drawings.');
      return;
    }
    setStatus('saving');
    setMessage('Regenerating drawing pages from saved project-local table data…');
    try {
      const next = updateProjectDrawingsFromWorkbook(projectRef.current, document);
      next.dataWorkspace = {
        ...(next.dataWorkspace || {}),
        revision: document.revision,
        appliedRevision: document.revision,
      };
      projectRef.current = await saveProject(next);
      setStatus('clean');
      setMessage('Drawing pages updated and saved inside the Singh360 project.');
      signal('CLEAN');
    } catch (reason) {
      setStatus('error');
      setMessage(`Drawing update failed. Project-local table data remains saved. ${String(reason)}`);
      signal('DIRTY');
    }
  }, [save, setStatus, signal, snapshot]);

  const finishNavigation = useCallback((request: NavigationRequest) => {
    if (!request) return;
    const current = statusRef.current;
    const published = current === 'dirty' || current === 'conflict' || current === 'error'
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
    setWorkspaceReady(false);
    getDataWorkspace(project.id).then((document) => {
      if (disposed || !containerRef.current) return;
      baseRef.current = document;
      setDocumentSheets(document.sheets);
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
          if (
            !readyRef.current
            // One user edit dispatches a top-level command plus many internal
            // mutations. Tracking every mutation queues redundant snapshots
            // that can overwrite a later, more specific save error message.
            || event.type !== CommandType.COMMAND
            || TAB_COLOR_COMMAND_IDS.has(event.id)
          ) return;
          window.setTimeout(() => {
            markDirty();
            const current = snapshot();
            if (current) applyTabColors(univerAPI, current);
          }, 0);
        }),
      ];
      readyTimer = window.setTimeout(async () => {
        const validationErrors = (
          await univerAPI.getActiveWorkbook()?.getAllDataValidationErrorAsync()
          || []
        ) as WorkspaceValidationError[];
        baselineValidationErrorsRef.current = new Set(
          validationErrors.map(validationErrorKey),
        );
        readyRef.current = true;
        setWorkspaceReady(true);
        const shared = readWorkspaceState(project.id);
        if (shared?.state === 'DIRTY' && shared.instanceId !== instanceIdRef.current) {
          setStatus('conflict');
          setMessage('Another Data Workspace instance reports unsaved edits. Resolve that instance before saving here.');
          signal('CONFLICT');
        } else {
          confirmedStatusRef.current = 'clean';
          setStatus('clean');
          setMessage(`${document.sheets.length} project-local table sheet${document.sheets.length === 1 ? '' : 's'} loaded.`);
          signal('CLEAN');
        }
      }, 750);
    }).catch((reason) => {
      setWorkspaceReady(false);
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

  const activateWorkspaceSheet = (sheetId: string) => {
    const worksheet = apiRef.current?.getActiveWorkbook()?.getSheetBySheetId(sheetId);
    worksheet?.activate();
  };

  const discardAndNavigate = async () => {
    const request = navigation;
    const confirmed = baseRef.current;
    if (!request || !confirmed) return;
    setNavigation(null);
    await restoreDocument(confirmed, confirmedStatusRef.current);
    setMessage('In-memory Data Workspace edits were discarded. The last confirmed snapshot was restored.');
    finishNavigation(request);
  };

  const statusLabel = WORKSPACE_STATUS_LABELS[status];
  const setup = activeDocumentSheet?.sourceSetup;

  return <div
    className="data-workspace"
    data-testid="data-workspace-shell"
    data-workspace-state={status === 'error' ? 'error' : workspaceReady ? 'ready' : 'loading'}
  >
    <header className="data-toolbar">
      <button type="button" data-help-id="nav.projectHome" onClick={() => requestNavigation('/app')}>Project Home</button>
      <strong>Data Workspace</strong>
      <span
        className={`workspace-status ${status}`}
        data-help-id={status === 'dirty' ? 'workspace.unsavedBadge' : status === 'error' ? 'save.retry' : status === 'conflict' ? 'status.conflict' : 'workspace.savedBadge'}
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
    <nav className="workspace-sheet-view" aria-label="Data Workspace sheet view">
      <label>
        View
        <select
          data-help-id="workspace.sheetSelector"
          value={workspaceView}
          onChange={(event) => setWorkspaceView(event.target.value as 'drawing' | 'all')}
        >
          <option value="drawing">Drawing Pages</option>
          <option value="all">All Imported Tables</option>
        </select>
      </label>
      {workspaceView === 'drawing' && <div
        className="workspace-drawing-tabs"
        role="tablist"
        aria-label="Drawing Pages"
        data-testid="drawing-pages-strip"
        data-ready={workspaceReady ? 'true' : 'false'}
        data-base-page-count={drawingSheets.length}
      >
        {drawingSheets.map((sheet) => <button
          type="button"
          role="tab"
          key={sheet.id}
          data-testid="drawing-page-tab"
          data-page-id={sheet.drawingPageId}
          data-sheet-code={sheet.drawingSheetCode}
          data-sheet-tab={sheet.name}
          data-drawing-order={sheet.drawingOrder}
          data-help-id="workspace.sheetSelector"
          aria-selected={sheet.id === activeSheetId}
          onClick={() => activateWorkspaceSheet(sheet.id)}
        >
          <span>{sheet.drawingOrder}. {sheet.drawingSheetCode || sheet.name}</span>
          <small>{sheet.drawingTitle || sheet.name}</small>
        </button>)}
      </div>}
      {workspaceView === 'all' && <span className="workspace-view-note">
        Drawing tables remain first; additional project-local imported or source tables follow.
      </span>}
    </nav>
    <main className={`data-workspace-main ${activeIsSource ? 'with-setup' : ''}`}>
      <div
        ref={containerRef}
        className="univer-host"
        aria-label="Project-local imported table workspace"
      />
      {activeIsSource && activeDocumentSheet && <aside className="sheet-setup-panel" aria-label="Sheet Setup">
        <h2>Sheet Setup <span className="lock-indicator">Locked</span></h2>
        <p className="sheet-authority">Imported metadata: {setup?.authority || 'Project-local table setup'}</p>
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
          <button type="button" data-help-id="workspace.save" className="primary" onClick={() => void save().then((saved) => {
            if (saved) finishNavigation(navigation);
          })}>Save</button>
          <button type="button" data-help-id="workspace.discard" onClick={() => void discardAndNavigate()}>Discard</button>
          <button type="button" data-help-id="dialog.cancel" onClick={() => setNavigation(null)}>Cancel</button>
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
