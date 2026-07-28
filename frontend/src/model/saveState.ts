import type { ProjectModel } from './types';

export type SaveState =
  | 'cleanLocal'
  | 'dirtyLocal'
  | 'dirtyWorkspace'
  | 'savingLocal'
  | 'localSavedSyncPending'
  | 'writingWorkbook'
  | 'savedAndSynced'
  | 'saveFailed'
  | 'syncFailed'
  | 'conflict';

export type DirtyDomain =
  | 'Data Workspace cells'
  | 'page metadata'
  | 'page order'
  | 'canvas objects'
  | 'Excel Layout tables'
  | 'title block or project metadata'
  | 'component/legend placement';

export const SAVE_STATE_LABELS: Record<SaveState, string> = {
  cleanLocal: 'PROJECT SAVED',
  dirtyLocal: 'UNSAVED PROJECT EDITS',
  dirtyWorkspace: 'UNSAVED WORKSPACE EDITS',
  savingLocal: 'SAVING PROJECT…',
  localSavedSyncPending: 'PROJECT SAVED · WORKBOOK SYNC PENDING',
  writingWorkbook: 'SAVING PROJECT + WRITING EXCEL…',
  savedAndSynced: 'PROJECT SAVED · WORKBOOK SYNCED',
  saveFailed: 'SAVE FAILED',
  syncFailed: 'WORKBOOK SYNC FAILED',
  conflict: 'PROJECT / WORKBOOK CONFLICT',
};

export function isWorkbookConflict(project: ProjectModel | null | undefined): boolean {
  const state = project?.workbookSync?.status || project?.workbookSync?.state || '';
  return state === 'conflict';
}

export function isWorkbookSynced(project: ProjectModel | null | undefined): boolean {
  const state = project?.workbookSync?.status || project?.workbookSync?.state || '';
  return state === 'in_sync';
}

export function confirmedProjectSaveState(project: ProjectModel | null | undefined): SaveState {
  if (isWorkbookConflict(project)) return 'conflict';
  if (isWorkbookSynced(project)) return 'savedAndSynced';
  const sync = project?.workbookSync;
  if (
    sync?.status === 'app_changed'
    || sync?.status === 'pending'
    || Boolean(sync?.warning)
  ) return 'localSavedSyncPending';
  return 'cleanLocal';
}

export function hasUnconfirmedLocalEdits(state: SaveState): boolean {
  return state === 'dirtyLocal'
    || state === 'dirtyWorkspace'
    || state === 'savingLocal'
    || state === 'saveFailed';
}

export function isSaveBusy(state: SaveState): boolean {
  return state === 'savingLocal' || state === 'writingWorkbook';
}

export function saveStateHelpId(state: SaveState): string {
  if (state === 'dirtyWorkspace') return 'status.unsavedWorkspace';
  if (state === 'dirtyLocal') return 'status.unsavedProject';
  if (state === 'localSavedSyncPending' || state === 'syncFailed') return 'status.syncPending';
  if (state === 'conflict') return 'status.conflict';
  if (state === 'saveFailed') return 'save.retry';
  return 'status.localSaved';
}

function stable(value: unknown): string {
  return JSON.stringify(value ?? null);
}

export function classifyProjectChanges(
  saved: ProjectModel | null | undefined,
  current: ProjectModel | null | undefined,
): DirtyDomain[] {
  if (!saved || !current) return [];
  const domains = new Set<DirtyDomain>();
  if (stable(saved.metadata) !== stable(current.metadata)) domains.add('title block or project metadata');
  const savedPages = saved.pages || [];
  const currentPages = current.pages || [];
  if (
    stable(savedPages.map((page) => page.id))
    !== stable(currentPages.map((page) => page.id))
    || stable(savedPages.map((page) => page.order))
      !== stable(currentPages.map((page) => page.order))
  ) domains.add('page order');

  const savedById = new Map(savedPages.map((page) => [page.id, page]));
  currentPages.forEach((page) => {
    const before = savedById.get(page.id);
    if (!before) {
      domains.add('page metadata');
      if ((page.canvasObjects || []).length) domains.add('canvas objects');
      return;
    }
    if (stable(before.canvasObjects) !== stable(page.canvasObjects)) {
      domains.add('canvas objects');
      const objectText = stable(page.canvasObjects).toLowerCase();
      if (objectText.includes('component') || objectText.includes('legend') || objectText.includes('symbol')) {
        domains.add('component/legend placement');
      }
    }
    const beforeRecord = before as unknown as Record<string, unknown>;
    const pageRecord = page as unknown as Record<string, unknown>;
    const excelKeys = Object.keys(pageRecord).filter((key) => /excel.*layout|layout.*table|table.*layout/i.test(key));
    if (excelKeys.some((key) => stable(beforeRecord[key]) !== stable(pageRecord[key]))) {
      domains.add('Excel Layout tables');
    }
    const withoutContent = (record: Record<string, unknown>) => Object.fromEntries(
      Object.entries(record).filter(([key]) => key !== 'canvasObjects' && !excelKeys.includes(key)),
    );
    if (stable(withoutContent(beforeRecord)) !== stable(withoutContent(pageRecord))) {
      domains.add('page metadata');
    }
  });
  return [...domains];
}
