import {
  buildExcelRangeBlock,
  refreshPageFromSource,
  splitExcelRangeBlock,
} from './excelRange';
import { buildIdfNetworkBlock, idfHeaderRow, isIdfNetworkPage } from './idfNetworkTable';
import type { PageModel, ProjectModel, Worksheet } from './types';

/** Rebuild one normalized page from its linked worksheet (toolbar action). */
export function rebuildSinglePageFromSource(page: PageModel, ws: Worksheet): PageModel {
  if (isIdfNetworkPage(page)) {
    const headerRow = idfHeaderRow(ws.grid ?? []);
    if (headerRow == null) return page;
    const block = buildIdfNetworkBlock(ws, headerRow, `${ws.id}_idf`, {
      showTerminatedBy: page.showTerminatedBy ?? false,
    });
    return {
      ...page,
      blocks: [block],
      canvasObjects: page.canvasObjects ?? [],
      renderMode: 'excel_exact',
      layoutProfile: 'network_48_port',
      twoUp: block.layoutMode === 'two_up',
      splitMode: 'none',
      allowContinuation: false,
      minScale: 1.0,
      scaleMode: 'fit_body',
      layoutWarnings: block.layoutWarnings ?? [],
      sourceRevision: (page.sourceRevision ?? 0) + 1,
    };
  }

  if (page.renderMode === 'excel_exact') {
    const existing = (page.blocks ?? [])[0];
    if (existing?.type === 'excelRange' && existing.srcRows) {
      return refreshPageFromSource(page, ws);
    }
    const full = buildExcelRangeBlock(ws, `${ws.id}_xr`);
    full.splitMode = page.splitMode ?? full.splitMode;
    full.minScale = page.minScale ?? full.minScale;
    full.allowContinuation = page.allowContinuation ?? full.allowContinuation;
    full.repeatRows = page.repeatRows ?? full.repeatRows;
    full.scaleMode = page.scaleMode ?? full.scaleMode;
    const parts = splitExcelRangeBlock(full);
    const partIndex = page.continuationIndex ?? 0;
    const part = parts[partIndex] ?? parts[0];
    return {
      ...page,
      blocks: [part],
      canvasObjects: page.canvasObjects ?? [],
      layoutWarnings: part.layoutWarnings ?? [],
      sourceRevision: (page.sourceRevision ?? 0) + 1,
    };
  }

  return refreshPageFromSource(page, ws);
}

export function applyRebuiltPage(project: ProjectModel, pageId: string, rebuilt: PageModel): ProjectModel {
  return {
    ...project,
    pages: project.pages.map((p) => (p.id === pageId ? rebuilt : p)),
  };
}
