import type { PageBlock, PageModel, ProjectModel, Worksheet } from './types';
import { applyCoverSourceTruth, buildExcelRangeBlock, splitExcelRangeBlock } from './excelRange';
import { isCoverWorksheet } from './metadataInference';
import { rebuildSinglePageFromSource } from './pageRebuild';
import { isIdfNetworkPage } from './idfNetworkTable';

function validRows(rows: number[] | undefined, rowCount: number): number[] {
  if (!rows?.length) return [];
  return [...new Set(rows.filter((row) => Number.isInteger(row) && row >= 0 && row < rowCount))]
    .sort((a, b) => a - b);
}

function applySourceFirstSettings(full: PageBlock, page: PageModel, previous?: PageBlock): PageBlock {
  const rowCount = full.grid?.length ?? 0;
  const previousRepeat = validRows(previous?.repeatRows, rowCount);
  return {
    ...full,
    id: previous?.id ?? full.id,
    renderProfile: page.renderProfile ?? previous?.renderProfile ?? full.renderProfile,
    normalizedHeaderStyle: page.normalizedHeaderStyle ?? previous?.normalizedHeaderStyle ?? full.normalizedHeaderStyle,
    splitMode: page.splitMode ?? previous?.splitMode ?? full.splitMode,
    minScale: page.minScale ?? previous?.minScale ?? full.minScale,
    allowContinuation: page.allowContinuation ?? previous?.allowContinuation ?? full.allowContinuation,
    scaleMode: page.scaleMode ?? previous?.scaleMode ?? full.scaleMode,
    orientation: page.orientation ?? previous?.orientation ?? full.orientation,
    repeatRows: previousRepeat.length ? previousRepeat : full.repeatRows,
    headerRowCount: previousRepeat.length
      ? Math.max(...previousRepeat) + 1
      : full.headerRowCount,
    bodyRowFillMode: previous?.bodyRowFillMode ?? full.bodyRowFillMode,
    gridLines: previous?.gridLines ?? full.gridLines,
    editable: previous?.editable ?? full.editable,
    styleRole: previous?.styleRole ?? full.styleRole,
    // Deliberately NOT copied from the old normalized block:
    // colWidths, rowHeights, bodyFontPx, nowrapColumns and noGrow.
    // The editable worksheet is the authority for those properties.
  };
}

/**
 * Build the page shown in Normalized/PDF directly from the current Worksheet.
 * Stored normalized blocks are treated as a cache, never as the authority for
 * cell geometry. This is what makes Source -> Normalized deterministic.
 */
export function projectPageFromWorksheet(page: PageModel, worksheet?: Worksheet): PageModel {
  if (!worksheet) return page;
  if (page.renderMode !== 'excel_exact' || isIdfNetworkPage(page)) {
    return rebuildSinglePageFromSource(page, worksheet);
  }

  const previous = (page.blocks ?? []).find((block) => block.type === 'excelRange');
  if (!previous) return rebuildSinglePageFromSource(page, worksheet);

  const full = applySourceFirstSettings(
    buildExcelRangeBlock(worksheet, `${worksheet.id}_xr_render`),
    page,
    previous,
  );
  const parts = splitExcelRangeBlock(full);
  const partIndex = Math.max(0, page.continuationIndex ?? 0);
  const selected = parts[partIndex] ?? parts[0] ?? full;
  const projectedBlock: PageBlock = { ...selected, id: previous.id };

  return {
    ...page,
    blocks: (page.blocks ?? []).map((block) => (
      block.type === 'excelRange' ? projectedBlock : block
    )),
  };
}

/** Cover metadata is also projected from Source while rendering. */
export function projectForWorksheetRender(
  project: ProjectModel,
  page: PageModel,
  worksheet?: Worksheet,
): { project: ProjectModel; page: PageModel } {
  if (!worksheet) return { project, page };
  if (isCoverWorksheet(project, worksheet.id)) {
    const projectedProject = applyCoverSourceTruth(project, worksheet.id);
    return {
      project: projectedProject,
      page: projectedProject.pages.find((candidate) => candidate.id === page.id) ?? page,
    };
  }
  return { project, page: projectPageFromWorksheet(page, worksheet) };
}
