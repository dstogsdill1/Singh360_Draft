import type { PageModel, ProjectModel, Worksheet } from './types';

const MAX_HISTORY = 50;

export interface SourceWorksheetSnapshot {
  worksheet: Worksheet;
  /** All output pages linked to this worksheet, in document order. */
  pages: PageModel[];
}

interface WorksheetHistoryStacks {
  undo: SourceWorksheetSnapshot[];
  redo: SourceWorksheetSnapshot[];
}

function cloneWorksheet(ws: Worksheet): Worksheet {
  return structuredClone(ws);
}

function clonePage(page: PageModel): PageModel {
  return structuredClone(page);
}

/** Capture worksheet + linked pages for undo/redo. */
export function captureSourceSnapshot(project: ProjectModel, wsId: string): SourceWorksheetSnapshot | null {
  const worksheet = project.worksheets.find((w) => w.id === wsId);
  if (!worksheet) return null;
  const pages = project.pages.filter((p) => p.linkedWorksheetId === wsId);
  return {
    worksheet: cloneWorksheet(worksheet),
    pages: pages.map(clonePage),
  };
}

function replaceLinkedPages(project: ProjectModel, wsId: string, linked: PageModel[]): ProjectModel {
  const first = project.pages.findIndex((p) => p.linkedWorksheetId === wsId);
  if (first < 0) {
    return {
      ...project,
      pages: [...project.pages, ...linked.map(clonePage)],
    };
  }
  let last = first;
  while (last < project.pages.length && project.pages[last].linkedWorksheetId === wsId) last += 1;
  return {
    ...project,
    pages: [
      ...project.pages.slice(0, first),
      ...linked.map(clonePage),
      ...project.pages.slice(last),
    ],
  };
}

/** Apply a snapshot: restore worksheet payload and linked page blocks/layout. */
export function applySourceSnapshot(
  project: ProjectModel,
  wsId: string,
  snapshot: SourceWorksheetSnapshot,
): ProjectModel {
  const worksheets = project.worksheets.map((w) =>
    w.id === wsId ? cloneWorksheet(snapshot.worksheet) : w,
  );
  return replaceLinkedPages({ ...project, worksheets }, wsId, snapshot.pages);
}

export class SourceWorksheetHistory {
  private stacks = new Map<string, WorksheetHistoryStacks>();

  clear(): void {
    this.stacks.clear();
  }

  clearWorksheet(wsId: string): void {
    this.stacks.delete(wsId);
  }

  pushBeforeEdit(project: ProjectModel, wsId: string): void {
    const snap = captureSourceSnapshot(project, wsId);
    if (!snap) return;
    let h = this.stacks.get(wsId);
    if (!h) {
      h = { undo: [], redo: [] };
      this.stacks.set(wsId, h);
    }
    h.undo.push(snap);
    if (h.undo.length > MAX_HISTORY) h.undo.shift();
    h.redo = [];
  }

  canUndo(wsId: string | undefined | null): boolean {
    if (!wsId) return false;
    return (this.stacks.get(wsId)?.undo.length ?? 0) > 0;
  }

  canRedo(wsId: string | undefined | null): boolean {
    if (!wsId) return false;
    return (this.stacks.get(wsId)?.redo.length ?? 0) > 0;
  }

  undo(project: ProjectModel, wsId: string): ProjectModel | null {
    const h = this.stacks.get(wsId);
    if (!h?.undo.length) return null;
    const current = captureSourceSnapshot(project, wsId);
    if (current) h.redo.push(current);
    const restore = h.undo.pop()!;
    return applySourceSnapshot(project, wsId, restore);
  }

  redo(project: ProjectModel, wsId: string): ProjectModel | null {
    const h = this.stacks.get(wsId);
    if (!h?.redo.length) return null;
    const current = captureSourceSnapshot(project, wsId);
    if (current) h.undo.push(current);
    const restore = h.redo.pop()!;
    return applySourceSnapshot(project, wsId, restore);
  }
}
