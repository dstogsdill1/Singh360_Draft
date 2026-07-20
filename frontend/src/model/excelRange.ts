// Client mirror of the Python excel_exact pipeline (core/workbook_importer.py +
// core/page_composer.py). Used to keep the Normalized view in sync when the
// Source grid is edited: value/fill/border edits refresh each page's block in
// place (split-safe via srcRows), and structural row/column edits regenerate the
// whole continuation group. Keep these constants in parity with the backend.

import type { ExcelCellStyle, MergedCell, PageBlock, PageModel, ProjectModel, Worksheet } from './types';
import { buildIdfNetworkBlock, idfHeaderRow, isIdfNetworkPage } from './idfNetworkTable';
import { inferMetadataFromWorksheet, isCoverWorksheet, mergeCoverMetadata } from './metadataInference';

export const PAGE_BODY_WIDTH = 1600;
export const PAGE_BODY_BUDGET = 720;
const BODY_W = PAGE_BODY_WIDTH;
const BODY_BUDGET = PAGE_BODY_BUDGET;
const MIN_SCALE = 0.5;
const MIN_ORPHAN_DATA_ROWS = 4;
const DEFAULT_COL = 64;
const DEFAULT_ROW = 20;

export function blockMinScale(block: PageBlock): number {
  const v = Number(block.minScale ?? MIN_SCALE);
  if (!Number.isFinite(v)) return MIN_SCALE;
  return Math.min(1, Math.max(0.2, v));
}

export function blockAllowsContinuation(block: PageBlock): boolean {
  if (block.allowContinuation === false) return false;
  return (block.splitMode ?? 'auto_rows') !== 'none';
}

export function excelBestScale(block: PageBlock): number {
  const w = Math.max(1, (block.colWidths ?? []).reduce((a, b) => a + b, 0));
  const h = Math.max(1, (block.rowHeights ?? []).reduce((a, b) => a + b, 0));
  return Math.min(Math.min(1, BODY_W / w), BODY_BUDGET / h);
}

export function colLetter(c: number): string {
  let s = '';
  let n = c + 1;
  while (n > 0) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

export function colIndex(letters: string): number {
  let n = 0;
  for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}

export function a1(r: number, c: number): string {
  return `${colLetter(c)}${r + 1}`;
}

function parseA1(key: string): { r: number; c: number } | null {
  const m = /^([A-Z]+)(\d+)$/.exec(key);
  if (!m) return null;
  return { c: colIndex(m[1]), r: Number(m[2]) - 1 };
}

/** Apply Singh360 app-only row/column/cell visibility before normalized render.
 * The underlying Worksheet grid remains intact and Excel export stays unchanged.
 */
function applySourceVisibility(ws: Worksheet): Worksheet {
  const sourceGrid = ws.grid ?? [];
  const nRows = sourceGrid.length;
  const nCols = Math.max(0, ...sourceGrid.map((row) => row.length));
  const hiddenRows = new Set(
    (ws.hiddenRows ?? []).filter((row) => Number.isInteger(row) && row >= 0 && row < nRows),
  );
  const hiddenColumns = new Set(
    (ws.hiddenColumns ?? []).filter((col) => Number.isInteger(col) && col >= 0 && col < nCols),
  );
  const hiddenCells = new Set(ws.hiddenCells ?? []);

  let visibleRows = Array.from({ length: nRows }, (_, row) => row).filter((row) => !hiddenRows.has(row));
  let visibleColumns = Array.from({ length: nCols }, (_, col) => col).filter((col) => !hiddenColumns.has(col));

  if (!visibleRows.length && nRows) visibleRows = [0];
  if (!visibleColumns.length && nCols) visibleColumns = [0];

  const rowMap = new Map(visibleRows.map((row, index) => [row, index]));
  const colMap = new Map(visibleColumns.map((col, index) => [col, index]));

  const grid = visibleRows.map((row) =>
    visibleColumns.map((col) => (
      hiddenCells.has(`${row}:${col}`) ? '' : cellText(sourceGrid[row]?.[col])
    )),
  );

  const styles: Record<string, ExcelCellStyle> = {};
  for (const [key, value] of Object.entries(ws.styles ?? {})) {
    const parsed = parseA1(key);
    if (!parsed) continue;
    const nextRow = rowMap.get(parsed.r);
    const nextCol = colMap.get(parsed.c);
    if (nextRow === undefined || nextCol === undefined) continue;
    if (hiddenCells.has(`${parsed.r}:${parsed.c}`)) continue;
    styles[a1(nextRow, nextCol)] = value;
  }

  const mergedCells: MergedCell[] = [];
  for (const merge of ws.mergedCells ?? []) {
    const rows = Array.from(
      { length: merge.endRow - merge.startRow + 1 },
      (_, index) => merge.startRow + index,
    );
    const columns = Array.from(
      { length: merge.endCol - merge.startCol + 1 },
      (_, index) => merge.startCol + index,
    );
    if (!rows.every((row) => rowMap.has(row)) || !columns.every((col) => colMap.has(col))) {
      continue;
    }
    mergedCells.push({
      startRow: rowMap.get(merge.startRow) as number,
      startCol: colMap.get(merge.startCol) as number,
      endRow: rowMap.get(merge.endRow) as number,
      endCol: colMap.get(merge.endCol) as number,
    });
  }

  return {
    ...ws,
    grid,
    styles,
    mergedCells,
    colWidthsPx: visibleColumns.map((col) => ws.colWidthsPx?.[col] ?? DEFAULT_COL),
    rowHeightsPx: visibleRows.map((row) => ws.rowHeightsPx?.[row] ?? DEFAULT_ROW),
  };
}

function cellText(v: unknown): string {
  return v == null ? '' : String(v);
}

function meaningfulStyle(st: ExcelCellStyle | undefined): boolean {
  if (!st) return false;
  if (st.fill) return true;
  const b = st.borders;
  return !!(b && (b.top || b.right || b.bottom || b.left));
}

/** Trim trailing blank worksheet columns/rows from a freshly-built excelRange
 *  block (Normalized/export only — mirrors
 *  core/workbook_importer.py::_trim_trailing_blank_ranges, FINAL RENDER
 *  POLISH 4G, Phase B). Never trims into a real merge or below the header
 *  band; leaves single-row/col grids alone. */
function trimTrailingBlankRanges(
  grid: string[][],
  stylesRc: Record<string, ExcelCellStyle>,
  merges: MergedCell[],
  headerRows: number,
): { grid: string[][]; styles: Record<string, ExcelCellStyle>; merges: MergedCell[]; rowsBefore: number; colsBefore: number } {
  let nRows = grid.length;
  let nCols = Math.max(0, ...grid.map((r) => r.length));
  const rowsBefore = nRows;
  const colsBefore = nCols;
  if (!nRows || !nCols) return { grid, styles: stylesRc, merges, rowsBefore, colsBefore };

  // A merge continuation cell never carries its own text/style (the anchor
  // top-left cell holds both), so a decorative full-width title-band merge
  // does not by itself make its trailing columns non-blank. Surviving merges
  // simply have endRow/endCol clamped below.
  const colBlank = (c: number): boolean => {
    for (let r = 0; r < nRows; r += 1) {
      if ((grid[r]?.[c] ?? '').trim()) return false;
      if (meaningfulStyle(stylesRc[`${r}:${c}`])) return false;
    }
    return true;
  };
  const rowBlank = (r: number): boolean => {
    const row = grid[r] ?? [];
    if (row.some((v) => (v ?? '').trim())) return false;
    for (let c = 0; c < nCols; c += 1) {
      if (meaningfulStyle(stylesRc[`${r}:${c}`])) return false;
    }
    return true;
  };

  let c = nCols - 1;
  while (c > 0 && colBlank(c)) c -= 1;
  nCols = c + 1;

  const floor = Math.max(0, headerRows - 1);
  let r = nRows - 1;
  while (r > floor && rowBlank(r)) r -= 1;
  nRows = r + 1;

  if (nRows === rowsBefore && nCols === colsBefore) {
    return { grid, styles: stylesRc, merges, rowsBefore, colsBefore };
  }

  const newGrid = grid.slice(0, nRows).map((row) => row.slice(0, nCols));
  const newStyles: Record<string, ExcelCellStyle> = {};
  for (const [key, val] of Object.entries(stylesRc)) {
    const [rs, cs] = key.split(':');
    if (Number(rs) < nRows && Number(cs) < nCols) newStyles[key] = val;
  }
  const newMerges = merges
    .filter((m) => m.startRow < nRows && m.startCol < nCols)
    .map((m) => ({ ...m, endRow: Math.min(m.endRow, nRows - 1), endCol: Math.min(m.endCol, nCols - 1) }));

  return { grid: newGrid, styles: newStyles, merges: newMerges, rowsBefore, colsBefore };
}

/** Build a full (unsplit) excelRange block from a worksheet. Mirrors
 *  core/workbook_importer.py::_excel_range_block. */
export function buildExcelRangeBlock(ws: Worksheet, blockId: string): PageBlock {
  const visibleWs = applySourceVisibility(ws);
  const src = visibleWs.grid ?? [];
  const nRows0 = src.length;
  const nCols0 = Math.max(0, ...src.map((r) => r.length));
  const grid0 = src.map((r) => {
    const row = r.map(cellText);
    while (row.length < nCols0) row.push('');
    return row;
  });

  const stylesRc0: Record<string, ExcelCellStyle> = {};
  for (const [key, val] of Object.entries(visibleWs.styles ?? {})) {
    const p = parseA1(key);
    if (p && p.r >= 0 && p.r < nRows0 && p.c >= 0 && p.c < nCols0) {
      stylesRc0[`${p.r}:${p.c}`] = val;
    }
  }

  let headerRows = 0;
  for (let r = 0; r < Math.min(nRows0, 4); r += 1) {
    let styled = false;
    let hasText = false;
    for (let c = 0; c < nCols0; c += 1) {
      const st = stylesRc0[`${r}:${c}`];
      if (st && (st.bold || st.fill)) styled = true;
      if ((grid0[r][c] ?? '').trim()) hasText = true;
    }
    if (styled && hasText) headerRows = r + 1;
    else break;
  }
  if (headerRows === 0 && nRows0) headerRows = 1;

  const merges0 = (visibleWs.mergedCells ?? []).map((m) => ({ ...m }));
  const trimmed = trimTrailingBlankRanges(grid0, stylesRc0, merges0, headerRows);
  const grid = trimmed.grid;
  const stylesRc = trimmed.styles;
  const nRows = grid.length;
  const nCols = Math.max(0, ...grid.map((r) => r.length));

  const colWidths = Array.from({ length: nCols }, (_, c) => visibleWs.colWidthsPx?.[c] ?? DEFAULT_COL);
  const rowHeights = Array.from({ length: nRows }, (_, r) => visibleWs.rowHeightsPx?.[r] ?? DEFAULT_ROW);

  return {
    id: blockId,
    type: 'excelRange',
    sourceWorksheetId: ws.id,
    sourceSheet: visibleWs.sourceSheet || visibleWs.name,
    sourceRange: visibleWs.sourceRange || '',
    renderMode: 'excel_exact',
    grid,
    styles: stylesRc,
    mergedCells: trimmed.merges,
    colWidths,
    rowHeights,
    srcRows: Array.from({ length: nRows }, (_, r) => r),
    headerRowCount: headerRows,
    repeatRows: Array.from({ length: headerRows }, (_, i) => i),
    splitMode: 'auto_rows',
    minScale: 0.5,
    allowContinuation: true,
    scaleMode: 'fit_body',
    orientation: 'landscape',
    styleRole: 'excel-exact',
    bodyRowFillMode: 'none',
    gridLines: true,
    editable: true,
    rowsBeforeTrim: trimmed.rowsBefore,
    colsBeforeTrim: trimmed.colsBefore,
    rowsAfterTrim: nRows,
    colsAfterTrim: nCols,
  };
}

/** Slice a full block down to `rowIndices` (absolute rows of the full block),
 *  remapping styles/merges/srcRows. Mirrors _slice_excel_block. */
function sliceBlock(
  full: PageBlock,
  rowIndices: number[],
  opts: { keepId?: string; partIndex?: number },
): PageBlock {
  const grid = full.grid ?? [];
  const rowH = full.rowHeights ?? [];
  const styles = full.styles ?? {};
  const merges = full.mergedCells ?? [];
  const srcRows = full.srcRows ?? grid.map((_, i) => i);
  const origRepeat = new Set(full.repeatRows ?? []);

  const remap = new Map<number, number>();
  rowIndices.forEach((old, i) => remap.set(old, i));

  const newGrid = rowIndices.map((r) => [...(grid[r] ?? [])]);
  const newRowH = rowIndices.map((r) => rowH[r] ?? DEFAULT_ROW);

  const newStyles: Record<string, ExcelCellStyle> = {};
  for (const [key, val] of Object.entries(styles)) {
    const [rs, cs] = key.split(':');
    const r = Number(rs);
    if (remap.has(r)) newStyles[`${remap.get(r)}:${cs}`] = val;
  }

  const newMerges: MergedCell[] = [];
  for (const m of merges) {
    const rows: number[] = [];
    for (let r = m.startRow; r <= m.endRow; r += 1) rows.push(r);
    if (rows.length && rows.every((r) => remap.has(r))) {
      const ns = rows.map((r) => remap.get(r) as number);
      newMerges.push({ ...m, startRow: Math.min(...ns), endRow: Math.max(...ns) });
    }
  }

  const headerPresent = rowIndices.filter((r) => origRepeat.has(r)).length;
  return {
    ...full,
    id: opts.keepId ?? `${full.id}_p${opts.partIndex ?? 0}`,
    grid: newGrid,
    rowHeights: newRowH,
    styles: newStyles,
    mergedCells: newMerges,
    srcRows: rowIndices.map((r) => srcRows[r] ?? r),
    repeatRows: Array.from({ length: headerPresent }, (_, i) => i),
  };
}

function naturalWidth(block: PageBlock): number {
  return Math.max(1, (block.colWidths ?? []).reduce((a, b) => a + b, 0));
}

/** Split only when continuation is allowed AND range cannot fit at minScale. */
function excelNeedsSplit(block: PageBlock): boolean {
  if (!blockAllowsContinuation(block)) return false;
  return excelBestScale(block) < blockMinScale(block);
}

function excelDataChunks(block: PageBlock, dataRows: number[], headerH: number): number[][] {
  const rowH = block.rowHeights ?? [];
  const scaleW = Math.min(1, BODY_W / naturalWidth(block));
  const budget = BODY_BUDGET / Math.max(scaleW, blockMinScale(block));

  const chunks: number[][] = [];
  let i = 0;
  while (i < dataRows.length) {
    let used = headerH;
    const chunk: number[] = [];
    while (i < dataRows.length) {
      const r = dataRows[i];
      const h = rowH[r] ?? DEFAULT_ROW;
      if (chunk.length && used + h > budget) break;
      chunk.push(r);
      used += h;
      i += 1;
    }
    if (!chunk.length) {
      chunk.push(dataRows[i]);
      i += 1;
    }
    chunks.push(chunk);
  }

  // Orphan avoidance: merge small tail chunks onto the prior page when legal.
  if (chunks.length >= 2 && chunks[chunks.length - 1].length < MIN_ORPHAN_DATA_ROWS) {
    while (
      chunks[chunks.length - 1].length < MIN_ORPHAN_DATA_ROWS &&
      chunks.length >= 2 &&
      chunks[chunks.length - 2].length > MIN_ORPHAN_DATA_ROWS
    ) {
      const moved = chunks[chunks.length - 2].pop();
      if (moved !== undefined) chunks[chunks.length - 1].unshift(moved);
    }
    if (chunks.length >= 2 && chunks[chunks.length - 1].length < MIN_ORPHAN_DATA_ROWS && chunks[chunks.length - 2].length >= 2) {
      const moved = chunks[chunks.length - 2].pop();
      if (moved !== undefined) chunks[chunks.length - 1].unshift(moved);
    }
  }
  return chunks.filter((c) => c.length);
}

/** Split a full block along real rows. Mirrors _split_excel_range_block. */
export function splitExcelRangeBlock(full: PageBlock): PageBlock[] {
  const grid = full.grid ?? [];
  const nRows = grid.length;
  if (nRows === 0) return [full];

  if (!excelNeedsSplit(full)) {
    if (!blockAllowsContinuation(full) && excelBestScale(full) < blockMinScale(full)) {
      const warn = [...(full.layoutWarnings ?? []), 'Range exceeds one page; scaled/cropped (continuation disabled).'];
      return [{ ...full, layoutWarnings: warn }];
    }
    return [full];
  }

  const repeat = [...new Set((full.repeatRows ?? []).filter((r) => r >= 0 && r < nRows))].sort((a, b) => a - b);
  const headerH = repeat.reduce((a, r) => a + ((full.rowHeights ?? [])[r] ?? DEFAULT_ROW), 0);
  const repeatSet = new Set(repeat);

  let chunks: number[][];
  if (full.splitMode === 'manual_ranges' && full.manualRanges?.length) {
    chunks = [];
    for (const rng of full.manualRanges) {
      const s = Number(rng[0]);
      const e = Number(rng[1]);
      if (!Number.isFinite(s) || !Number.isFinite(e)) continue;
      const rows = [];
      for (let r = Math.max(0, s); r <= Math.min(nRows - 1, e); r += 1) {
        if (!repeatSet.has(r)) rows.push(r);
      }
      if (rows.length) chunks.push(rows);
    }
  } else {
    const dataRows = grid.map((_, i) => i).filter((r) => !repeatSet.has(r));
    chunks = excelDataChunks(full, dataRows, headerH);
  }

  if (chunks.length <= 1) return [full];

  return chunks.map((chunk, ci) => {
    const rowIndices = [...new Set([...repeat, ...chunk])].sort((a, b) => a - b);
    return sliceBlock(full, rowIndices, { partIndex: ci });
  });
}

/** Preview page count for a block (mirrors plan_excel_range). */
export function planExcelRange(block: PageBlock): { pages: number; willSplit: boolean; bestScale: number; minScale: number } {
  const parts = splitExcelRangeBlock({ ...block });
  return {
    pages: parts.length,
    willSplit: parts.length > 1,
    bestScale: Math.round(excelBestScale(block) * 10000) / 10000,
    minScale: blockMinScale(block),
  };
}

/** Keep import-time layout/render tuning when only cell values changed. */
function preserveBlockPresentationMeta(prev: PageBlock, next: PageBlock): PageBlock {
  const out: PageBlock = { ...next };
  if (prev.renderProfile !== undefined) out.renderProfile = prev.renderProfile;
  if (prev.nowrapColumns !== undefined) out.nowrapColumns = prev.nowrapColumns;
  if (prev.noGrow !== undefined) out.noGrow = prev.noGrow;
  if (prev.layoutWarnings !== undefined) out.layoutWarnings = prev.layoutWarnings;
  if (prev.splitMode !== undefined) out.splitMode = prev.splitMode;
  if (prev.minScale !== undefined) out.minScale = prev.minScale;
  if (prev.allowContinuation !== undefined) out.allowContinuation = prev.allowContinuation;
  if (prev.scaleMode !== undefined) out.scaleMode = prev.scaleMode;
  if (prev.repeatRows !== undefined) out.repeatRows = prev.repeatRows;
  if (prev.headerRowCount !== undefined) out.headerRowCount = prev.headerRowCount;
  if (prev.bodyRowFillMode !== undefined) out.bodyRowFillMode = prev.bodyRowFillMode;
  if (prev.gridLines !== undefined) out.gridLines = prev.gridLines;
  if (prev.editable !== undefined) out.editable = prev.editable;
  if (prev.styleRole !== undefined) out.styleRole = prev.styleRole;
  if (prev.orientation !== undefined) out.orientation = prev.orientation;
  if (prev.bodyFontPx !== undefined) out.bodyFontPx = prev.bodyFontPx;
  if (prev.renderProfile || (prev as PageBlock & { layoutProfile?: string }).layoutProfile) {
    if (prev.colWidths?.length) out.colWidths = prev.colWidths;
    if (prev.rowHeights?.length) out.rowHeights = prev.rowHeights;
  }
  const prevExt = prev as PageBlock & { layoutProfile?: string; columnPriorities?: number[] };
  const outExt = out as PageBlock & { layoutProfile?: string; columnPriorities?: number[] };
  if (prevExt.layoutProfile !== undefined) outExt.layoutProfile = prevExt.layoutProfile;
  if (prevExt.columnPriorities !== undefined) outExt.columnPriorities = prevExt.columnPriorities;
  return out;
}

function trimTrailingEmptyColumns(grid: string[][]): string[][] {
  const maxCol = grid.reduce((m, row) => {
    let last = -1;
    for (let i = 0; i < row.length; i += 1) {
      if ((row[i] ?? '').trim() !== '') last = i;
    }
    return Math.max(m, last + 1);
  }, 0);
  const cols = Math.max(1, maxCol);
  return grid.map((row) => {
    const out = row.slice(0, cols);
    while (out.length < cols) out.push('');
    return out;
  });
}

/** Refresh a single page's block from the worksheet using its srcRows (values /
 *  fills / borders reflected, split pages stay non-duplicated). */
export function refreshBlockFromWorksheet(block: PageBlock, ws: Worksheet): PageBlock {
  const full = buildExcelRangeBlock(ws, `${ws.id}_xr`);
  const nRows = (full.grid ?? []).length;
  const rows = (block.srcRows ?? full.srcRows ?? []).filter((r) => r >= 0 && r < nRows);
  if (!rows.length) return preserveBlockPresentationMeta(block, full);
  return preserveBlockPresentationMeta(block, sliceBlock(full, rows, { keepId: block.id }));
}

function rowLine(row: string[]): string {
  const parts = (row ?? []).map((c) => (c ?? '').trim()).filter(Boolean);
  return parts.join('  ');
}

function refreshCoverBlockFromWorksheet(block: PageBlock, ws: Worksheet): PageBlock {
  const grid = ws.grid ?? [];
  const lines = grid.map((r) => rowLine(r)).filter(Boolean);
  return {
    ...block,
    rows: lines.map((ln) => [ln]),
  };
}

/** Rebuild normalized blocks for one page from its linked worksheet source grid. */
export function refreshPageFromSource(page: PageModel, ws: Worksheet): PageModel {
  const visibleWs = applySourceVisibility(ws);
  const blocks = page.blocks ?? [];
  let nextBlocks: PageBlock[];
  if (page.renderMode === 'excel_exact') {
    nextBlocks = blocks.map((b) => (b.type === 'excelRange' ? refreshBlockFromWorksheet(b, ws) : b));
  } else {
    const coverIdx = blocks.findIndex((b) => b.type === 'cover');
    if (coverIdx >= 0 || page.pageType === 'cover') {
      if (coverIdx >= 0) {
        nextBlocks = blocks.map((b) => (b.type === 'cover' ? refreshCoverBlockFromWorksheet(b, ws) : b));
      } else {
        const lines = (visibleWs.grid ?? []).map((r) => rowLine(r)).filter(Boolean);
        nextBlocks = [
          ...blocks,
          {
            id: `${ws.id}_cover`,
            type: 'cover' as const,
            sourceWorksheetId: ws.id,
            text: page.sheetTitle ?? 'Cover',
            rows: lines.map((ln) => [ln]),
            styleRole: 'page-title',
            editable: true,
          },
        ];
      }
    } else {
      const tableIdx = blocks.findIndex((b) => b.type === 'matrix' || b.type === 'table');
      if (tableIdx < 0) {
        nextBlocks = blocks;
      } else {
        const normalized = trimTrailingEmptyColumns(visibleWs.grid ?? []);
        const headers = (normalized[0] ?? []).map((x) => x ?? '');
        const rows = normalized.slice(1).map((r) => r.map((x) => x ?? ''));
        nextBlocks = blocks.map((b, i) => (i === tableIdx ? { ...b, headers, rows } : b));
      }
    }
  }
  return {
    ...page,
    blocks: nextBlocks,
    sourceRevision: (page.sourceRevision ?? 0) + 1,
  };
}

/** For cover pages: rebuild normalized blocks and overwrite project metadata from source. */
export function applyCoverSourceTruth(project: ProjectModel, wsId: string): ProjectModel {
  const ws = project.worksheets.find((w) => w.id === wsId);
  if (!ws || !isCoverWorksheet(project, wsId)) return project;
  const pages = project.pages.map((pg) =>
    pg.linkedWorksheetId === wsId ? refreshPageFromSource(pg, ws) : pg,
  );
  const metadata = mergeCoverMetadata(project.metadata, inferMetadataFromWorksheet(ws));
  return { ...project, pages, metadata };
}

function continuationTitle(baseTitle: string): string {
  const low = (baseTitle || '').toLowerCase();
  if (low.includes('continued')) return baseTitle;
  return `${baseTitle} — CONTINUED`;
}

function continuationCode(base: string, index: number): string {
  const b = (base || '').trim();
  const letter = String.fromCharCode(96 + index);
  if (/^\d+$/.test(b)) return `${b}.${index}`;
  if (/^\d+\.\d+$/.test(b)) return `${b}${letter}`;
  if (b) return `${b}${letter}`;
  return `cont-${index}`;
}

function resequence(pages: PageModel[]): PageModel[] {
  const total = pages.filter((p) => p.include !== false).length;
  let n = 0;
  return pages.map((p, i) => {
    const order = i + 1;
    if (p.include !== false) {
      n += 1;
      return { ...p, order, pageNumber: n, pageTotal: total };
    }
    return { ...p, order, pageNumber: null, pageTotal: total };
  });
}

/** Regenerate the base + continuation pages for an excel_exact worksheet after a
 *  structural (row/column count) edit. Preserves deterministic continuation ids
 *  so overlay annotations keyed by page id survive. */
export function regenerateExcelGroup(project: ProjectModel, wsId: string): PageModel[] {
  const ws = project.worksheets.find((w) => w.id === wsId);
  const base = project.pages.find(
    (p) => p.linkedWorksheetId === wsId && !p.generatedContinuation && p.renderMode === 'excel_exact',
  );
  if (!ws || !base) return project.pages;

  if (isIdfNetworkPage(base)) {
    const headerRow = idfHeaderRow(ws.grid ?? []);
    if (headerRow != null) {
      const block = buildIdfNetworkBlock(ws, headerRow, `${ws.id}_idf`, {
        showTerminatedBy: base.showTerminatedBy ?? false,
      });
      return project.pages.map((p) => {
        if (p.id !== base.id && p.pageGroupId !== (base.pageGroupId ?? base.id)) return p;
        if (p.generatedContinuation) return p;
        return {
          ...p,
          blocks: [block],
          layoutProfile: 'network_48_port',
          twoUp: block.layoutMode === 'two_up',
          splitMode: 'none',
          allowContinuation: false,
          minScale: 1.0,
          scaleMode: 'fit_body',
          layoutWarnings: block.layoutWarnings ?? [],
        };
      });
    }
  }

  const groupId = base.pageGroupId ?? base.id;
  const canonicalBaseCode = (base.displaySheetCode || base.sheetCode || '').trim();
  const full = buildExcelRangeBlock(ws, `${ws.id}_xr`);
  full.splitMode = base.splitMode ?? full.splitMode;
  full.minScale = base.minScale ?? full.minScale;
  full.allowContinuation = base.allowContinuation ?? full.allowContinuation;
  full.repeatRows = base.repeatRows ?? full.repeatRows;
  full.scaleMode = base.scaleMode ?? full.scaleMode;
  const parts = splitExcelRangeBlock(full);

  const byId = new Map(project.pages.map((p) => [p.id, p]));
  const inGroup = (p: PageModel) =>
    p.id === base.id || p.pageGroupId === groupId || p.continuationOf === groupId;

  const newGroup: PageModel[] = [];
  newGroup.push({
    ...base,
    blocks: [parts[0]],
    pageGroupId: groupId,
    continuationOf: null,
    continuationIndex: 0,
    generatedContinuation: false,
    displaySheetCode: canonicalBaseCode || base.sheetCode,
    sheetCode: canonicalBaseCode || base.sheetCode,
    repeatRows: parts[0].repeatRows,
  });

  for (let i = 1; i < parts.length; i += 1) {
    const contId = `${groupId}_c${i}`;
    const prev = byId.get(contId);
    const code = continuationCode(canonicalBaseCode || base.sheetCode, i);
    newGroup.push({
      ...(prev ?? ({} as PageModel)),
      id: contId,
      order: base.order,
      include: base.include,
      sheetCode: code,
      displaySheetCode: code,
      sheetTitle: continuationTitle(base.sheetTitle ?? ''),
      sheetTab: base.sheetTab,
      pageType: base.pageType,
      pageFamily: base.pageFamily,
      renderMode: 'excel_exact',
      sourceSheet: base.sourceSheet,
      scaleMode: base.scaleMode,
      orientation: base.orientation,
      splitMode: base.splitMode,
      minScale: base.minScale,
      allowContinuation: base.allowContinuation,
      repeatRows: parts[i].repeatRows,
      templateId: base.templateId,
      linkedWorksheetId: base.linkedWorksheetId,
      blocks: [parts[i]],
      canvasObjects: prev?.canvasObjects ?? [],
      assets: prev?.assets ?? [],
      notes: '',
      pageGroupId: groupId,
      continuationOf: groupId,
      continuationIndex: i,
      generatedContinuation: true,
      layoutWarnings: [],
    });
  }

  const result: PageModel[] = [];
  let inserted = false;
  for (const p of project.pages) {
    if (inGroup(p)) {
      if (!inserted) {
        result.push(...newGroup);
        inserted = true;
      }
      continue;
    }
    result.push(p);
  }
  if (!inserted) result.push(...newGroup);
  return resequence(result);
}

// ── Worksheet edit helpers (Source view) ────────────────────────────────────

function cloneGrid(grid: string[][]): string[][] {
  return grid.map((r) => [...r]);
}

/** Set a cell value, growing the grid as needed. */
export function wsSetCell(ws: Worksheet, r: number, c: number, value: string): Partial<Worksheet> {
  const grid = cloneGrid(ws.grid ?? []);
  while (grid.length <= r) grid.push([]);
  while (grid[r].length <= c) grid[r].push('');
  grid[r][c] = value;
  return { grid };
}

/** Apply/clear a fill (highlight) on a set of cells. */
export function wsSetFill(
  ws: Worksheet,
  cells: Array<{ r: number; c: number }>,
  color: string | null,
): Partial<Worksheet> {
  const styles: Record<string, ExcelCellStyle> = { ...(ws.styles ?? {}) };
  for (const { r, c } of cells) {
    const key = a1(r, c);
    const cur = { ...(styles[key] ?? {}) };
    if (color) cur.fill = color;
    else delete cur.fill;
    styles[key] = cur;
  }
  return { styles };
}

/** Toggle thin black borders on all four sides for a set of cells. */
export function wsSetBorders(
  ws: Worksheet,
  cells: Array<{ r: number; c: number }>,
  on: boolean,
): Partial<Worksheet> {
  const styles: Record<string, ExcelCellStyle> = { ...(ws.styles ?? {}) };
  const side = { style: 'thin', color: '#000000' };
  for (const { r, c } of cells) {
    const key = a1(r, c);
    const cur = { ...(styles[key] ?? {}) };
    if (on) cur.borders = { top: side, right: side, bottom: side, left: side };
    else delete cur.borders;
    styles[key] = cur;
  }
  return { styles };
}

function shiftStyles(
  styles: Record<string, ExcelCellStyle>,
  axis: 'row' | 'col',
  at: number,
  delta: number,
): Record<string, ExcelCellStyle> {
  const out: Record<string, ExcelCellStyle> = {};
  for (const [key, val] of Object.entries(styles)) {
    const p = parseA1(key);
    if (!p) continue;
    let { r, c } = p;
    if (axis === 'row') {
      if (delta < 0 && r === at) continue; // deleted row's styles dropped
      if (r >= at) r += delta;
    } else {
      if (delta < 0 && c === at) continue;
      if (c >= at) c += delta;
    }
    if (r >= 0 && c >= 0) out[a1(r, c)] = val;
  }
  return out;
}

function shiftMerges(merges: MergedCell[], axis: 'row' | 'col', at: number, delta: number): MergedCell[] {
  const out: MergedCell[] = [];
  for (const m of merges) {
    const nm = { ...m };
    if (axis === 'row') {
      if (delta < 0 && at >= m.startRow && at <= m.endRow && m.startRow === m.endRow) continue;
      if (m.startRow >= at) nm.startRow += delta;
      if (m.endRow >= at) nm.endRow += delta;
    } else {
      if (delta < 0 && at >= m.startCol && at <= m.endCol && m.startCol === m.endCol) continue;
      if (m.startCol >= at) nm.startCol += delta;
      if (m.endCol >= at) nm.endCol += delta;
    }
    if (nm.endRow >= nm.startRow && nm.endCol >= nm.startCol) out.push(nm);
  }
  return out;
}

export function wsInsertRow(ws: Worksheet, at: number): Partial<Worksheet> {
  const grid = cloneGrid(ws.grid ?? []);
  const nCols = Math.max(0, ...grid.map((r) => r.length));
  grid.splice(at, 0, Array.from({ length: nCols }, () => ''));
  const rowHeightsPx = [...(ws.rowHeightsPx ?? [])];
  rowHeightsPx.splice(at, 0, DEFAULT_ROW);
  return {
    grid,
    rowHeightsPx,
    styles: shiftStyles(ws.styles ?? {}, 'row', at, 1),
    mergedCells: shiftMerges(ws.mergedCells ?? [], 'row', at, 1),
  };
}

export function wsDeleteRow(ws: Worksheet, at: number): Partial<Worksheet> {
  const grid = cloneGrid(ws.grid ?? []);
  if (at < 0 || at >= grid.length) return {};
  grid.splice(at, 1);
  const rowHeightsPx = [...(ws.rowHeightsPx ?? [])];
  rowHeightsPx.splice(at, 1);
  return {
    grid,
    rowHeightsPx,
    styles: shiftStyles(ws.styles ?? {}, 'row', at, -1),
    mergedCells: shiftMerges(ws.mergedCells ?? [], 'row', at, -1),
  };
}

export function wsInsertCol(ws: Worksheet, at: number): Partial<Worksheet> {
  const grid = (ws.grid ?? []).map((r) => {
    const row = [...r];
    while (row.length < at) row.push('');
    row.splice(at, 0, '');
    return row;
  });
  const colWidthsPx = [...(ws.colWidthsPx ?? [])];
  colWidthsPx.splice(at, 0, DEFAULT_COL);
  return {
    grid,
    colWidthsPx,
    styles: shiftStyles(ws.styles ?? {}, 'col', at, 1),
    mergedCells: shiftMerges(ws.mergedCells ?? [], 'col', at, 1),
  };
}

export function wsDeleteCol(ws: Worksheet, at: number): Partial<Worksheet> {
  const grid = (ws.grid ?? []).map((r) => {
    const row = [...r];
    if (at < row.length) row.splice(at, 1);
    return row;
  });
  const colWidthsPx = [...(ws.colWidthsPx ?? [])];
  if (at < colWidthsPx.length) colWidthsPx.splice(at, 1);
  return {
    grid,
    colWidthsPx,
    styles: shiftStyles(ws.styles ?? {}, 'col', at, -1),
    mergedCells: shiftMerges(ws.mergedCells ?? [], 'col', at, -1),
  };
}

// ── Source grid sizing / merge / style helpers ──────────────────────────────

export const WS_MIN_COL_W = 45;
export const WS_MAX_COL_W = 280;
export const WS_MIN_ROW_H = 18;
export const WS_MAX_ROW_H = 120;

function clampColW(w: number): number {
  return Math.min(WS_MAX_COL_W, Math.max(WS_MIN_COL_W, Math.round(w)));
}

function clampRowH(h: number): number {
  return Math.min(WS_MAX_ROW_H, Math.max(WS_MIN_ROW_H, Math.round(h)));
}

function mergeOverlaps(
  a: MergedCell,
  b: { r0: number; c0: number; r1: number; c1: number },
): boolean {
  return !(
    a.endRow < b.r0
    || a.startRow > b.r1
    || a.endCol < b.c0
    || a.startCol > b.c1
  );
}

/** Merge a rectangular selection; keeps top-left value and style. */
export function wsMergeCells(
  ws: Worksheet,
  rect: { r0: number; c0: number; r1: number; c1: number },
): Partial<Worksheet> {
  const r0 = Math.min(rect.r0, rect.r1);
  const r1 = Math.max(rect.r0, rect.r1);
  const c0 = Math.min(rect.c0, rect.c1);
  const c1 = Math.max(rect.c0, rect.c1);
  if (r0 === r1 && c0 === c1) return {};

  const grid = cloneGrid(ws.grid ?? []);
  const topLeft = grid[r0]?.[c0] ?? '';
  for (let r = r0; r <= r1; r += 1) {
    while (grid.length <= r) grid.push([]);
    for (let c = c0; c <= c1; c += 1) {
      while (grid[r].length <= c) grid[r].push('');
      if (r === r0 && c === c0) grid[r][c] = topLeft;
      else grid[r][c] = '';
    }
  }

  const box = { r0, c0, r1, c1 };
  const merges = (ws.mergedCells ?? []).filter((m) => !mergeOverlaps(m, box));
  merges.push({ startRow: r0, startCol: c0, endRow: r1, endCol: c1 });

  const styles = { ...(ws.styles ?? {}) };
  const anchorKey = a1(r0, c0);
  const anchorStyle = { ...(styles[anchorKey] ?? {}) };
  styles[anchorKey] = anchorStyle;
  for (let r = r0; r <= r1; r += 1) {
    for (let c = c0; c <= c1; c += 1) {
      if (r === r0 && c === c0) continue;
      delete styles[a1(r, c)];
    }
  }

  return { grid, mergedCells: merges, styles };
}

/** Unmerge any merged region overlapping the selection anchor. */
export function wsUnmergeCells(
  ws: Worksheet,
  rect: { r0: number; c0: number; r1: number; c1: number },
): Partial<Worksheet> {
  const r0 = Math.min(rect.r0, rect.r1);
  const c0 = Math.min(rect.c0, rect.c1);
  const r1 = Math.max(rect.r0, rect.r1);
  const c1 = Math.max(rect.c0, rect.c1);
  const box = { r0, c0, r1, c1 };
  const merges = (ws.mergedCells ?? []).filter((m) => !mergeOverlaps(m, box));
  if (merges.length === (ws.mergedCells ?? []).length) return {};
  return { mergedCells: merges };
}

/** Patch per-cell style properties on selected cells. */
export function wsSetStyle(
  ws: Worksheet,
  cells: Array<{ r: number; c: number }>,
  patch: Partial<ExcelCellStyle>,
): Partial<Worksheet> {
  const styles: Record<string, ExcelCellStyle> = { ...(ws.styles ?? {}) };
  for (const { r, c } of cells) {
    const key = a1(r, c);
    const cur = { ...(styles[key] ?? {}) };
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === undefined) delete (cur as Record<string, unknown>)[k];
      else (cur as Record<string, unknown>)[k] = v;
    }
    styles[key] = cur;
  }
  return { styles };
}

export function wsSetColWidth(ws: Worksheet, col: number, width: number): Partial<Worksheet> {
  const colWidthsPx = [...(ws.colWidthsPx ?? [])];
  while (colWidthsPx.length <= col) colWidthsPx.push(DEFAULT_COL);
  colWidthsPx[col] = clampColW(width);
  return { colWidthsPx };
}

export function wsSetRowHeight(ws: Worksheet, row: number, height: number): Partial<Worksheet> {
  const rowHeightsPx = [...(ws.rowHeightsPx ?? [])];
  while (rowHeightsPx.length <= row) rowHeightsPx.push(DEFAULT_ROW);
  rowHeightsPx[row] = clampRowH(height);
  return { rowHeightsPx };
}

function estimateColWidth(text: string, wrap: boolean, fontSize = 12): number {
  const t = (text ?? '').trim();
  if (!t) return WS_MIN_COL_W;
  if (wrap && t.length > 24) return Math.min(WS_MAX_COL_W, 140);
  const pxPerChar = fontSize >= 11 ? 8 : 7;
  return clampColW(t.length * pxPerChar + 16);
}

function estimateRowHeight(text: string, colWidth: number, wrap: boolean, fontSize = 12): number {
  const t = (text ?? '').trim();
  if (!t || !wrap) return WS_MIN_ROW_H;
  const charsPerLine = Math.max(8, Math.floor(colWidth / (fontSize >= 11 ? 7.5 : 6.5)));
  const lines = Math.ceil(t.length / charsPerLine);
  return clampRowH(Math.max(WS_MIN_ROW_H, lines * (fontSize + 6) + 4));
}

/** Auto-fit column widths from cell text (clamped). */
export function wsAutoFitColumns(ws: Worksheet, cols: number[]): Partial<Worksheet> {
  const grid = ws.grid ?? [];
  const styles = ws.styles ?? {};
  const nCols = Math.max(cols.length ? Math.max(...cols) + 1 : 0, ...(grid.map((r) => r.length)));
  const colWidthsPx = [...(ws.colWidthsPx ?? [])];
  while (colWidthsPx.length < nCols) colWidthsPx.push(DEFAULT_COL);

  for (const c of cols) {
    let maxW = WS_MIN_COL_W;
    for (let r = 0; r < grid.length; r += 1) {
      const st = styles[a1(r, c)];
      const w = estimateColWidth(grid[r]?.[c] ?? '', !!st?.wrap, st?.fontSize ?? 12);
      maxW = Math.max(maxW, w);
    }
    colWidthsPx[c] = clampColW(maxW);
  }
  return { colWidthsPx };
}

/** Auto-fit row heights from wrapped text in selected rows. */
export function wsAutoFitRows(ws: Worksheet, rows: number[]): Partial<Worksheet> {
  const grid = ws.grid ?? [];
  const styles = ws.styles ?? {};
  const colWidthsPx = ws.colWidthsPx ?? [];
  const rowHeightsPx = [...(ws.rowHeightsPx ?? [])];
  const nRows = Math.max(rows.length ? Math.max(...rows) + 1 : 0, grid.length);
  while (rowHeightsPx.length < nRows) rowHeightsPx.push(DEFAULT_ROW);

  for (const r of rows) {
    let maxH = WS_MIN_ROW_H;
    const nCols = grid[r]?.length ?? 0;
    for (let c = 0; c < nCols; c += 1) {
      const st = styles[a1(r, c)];
      const colW = colWidthsPx[c] ?? DEFAULT_COL;
      const h = estimateRowHeight(grid[r]?.[c] ?? '', colW, !!st?.wrap, st?.fontSize ?? 12);
      maxH = Math.max(maxH, h);
    }
    rowHeightsPx[r] = clampRowH(maxH);
  }
  return { rowHeightsPx };
}

/** Auto-fit both dimensions for cells in a rectangular range. */
export function wsAutoFitRange(
  ws: Worksheet,
  rect: { r0: number; c0: number; r1: number; c1: number },
): Partial<Worksheet> {
  const r0 = Math.min(rect.r0, rect.r1);
  const r1 = Math.max(rect.r0, rect.r1);
  const c0 = Math.min(rect.c0, rect.c1);
  const c1 = Math.max(rect.c0, rect.c1);
  const cols = Array.from({ length: c1 - c0 + 1 }, (_, i) => c0 + i);
  const rows = Array.from({ length: r1 - r0 + 1 }, (_, i) => r0 + i);
  const colPatch = wsAutoFitColumns(ws, cols);
  const rowPatch = wsAutoFitRows({ ...ws, ...colPatch }, rows);
  return { ...colPatch, ...rowPatch };
}
