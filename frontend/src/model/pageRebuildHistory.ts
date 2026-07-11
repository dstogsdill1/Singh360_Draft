import type { PageModel, ProjectModel } from './types';

const MAX_HISTORY = 10;

export interface PageRebuildSnapshot {
  page: PageModel;
  savedAt: string;
  /** Server-side snapshot name when persisted to project page_snapshots. */
  serverSnapshotName?: string;
}

interface PageStacks {
  undo: PageRebuildSnapshot[];
  redo: PageRebuildSnapshot[];
}

function clonePage(page: PageModel): PageModel {
  return structuredClone(page);
}

export class PageRebuildHistory {
  private stacks = new Map<string, PageStacks>();

  clear(): void {
    this.stacks.clear();
  }

  clearPage(pageId: string): void {
    this.stacks.delete(pageId);
  }

  pushBeforeRebuild(page: PageModel, serverSnapshotName?: string): void {
    let h = this.stacks.get(page.id);
    if (!h) {
      h = { undo: [], redo: [] };
      this.stacks.set(page.id, h);
    }
    h.undo.push({
      page: clonePage(page),
      savedAt: new Date().toISOString(),
      serverSnapshotName,
    });
    if (h.undo.length > MAX_HISTORY) h.undo.shift();
    h.redo = [];
  }

  canRestore(pageId: string | undefined | null): boolean {
    if (!pageId) return false;
    return (this.stacks.get(pageId)?.undo.length ?? 0) > 0;
  }

  canUndo(pageId: string | undefined | null): boolean {
    return this.canRestore(pageId);
  }

  canRedo(pageId: string | undefined | null): boolean {
    if (!pageId) return false;
    return (this.stacks.get(pageId)?.redo.length ?? 0) > 0;
  }

  lastSnapshot(pageId: string): PageRebuildSnapshot | null {
    const h = this.stacks.get(pageId);
    if (!h?.undo.length) return null;
    return h.undo[h.undo.length - 1];
  }

  private applyPage(project: ProjectModel, pageId: string, page: PageModel): ProjectModel {
    return {
      ...project,
      pages: project.pages.map((p) => (p.id === pageId ? clonePage(page) : p)),
    };
  }

  restoreLast(project: ProjectModel, pageId: string): ProjectModel | null {
    const h = this.stacks.get(pageId);
    if (!h?.undo.length) return null;
    const current = project.pages.find((p) => p.id === pageId);
    if (current) {
      h.redo.push({ page: clonePage(current), savedAt: new Date().toISOString() });
    }
    const snap = h.undo.pop()!;
    return this.applyPage(project, pageId, snap.page);
  }

  undo(project: ProjectModel, pageId: string): ProjectModel | null {
    return this.restoreLast(project, pageId);
  }

  redo(project: ProjectModel, pageId: string): ProjectModel | null {
    const h = this.stacks.get(pageId);
    if (!h?.redo.length) return null;
    const current = project.pages.find((p) => p.id === pageId);
    if (current) {
      h.undo.push({ page: clonePage(current), savedAt: new Date().toISOString() });
    }
    const snap = h.redo.pop()!;
    return this.applyPage(project, pageId, snap.page);
  }
}
