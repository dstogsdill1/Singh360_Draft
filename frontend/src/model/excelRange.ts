// Client mirror of the Python excel_exact pipeline (core/workbook_importer.py +
// core/page_composer.py). Used to keep the Normalized view in sync when the
// Source grid is edited: value/fill/border edits refresh each page's block in
// place (split-safe via srcRows), and structural row/column edits regenerate the
// whole continuation group. Keep these constants in parity with the backend.

import type { ExcelCellStyle, MergedCell, PageBlock, PageModel, ProjectModel, Worksheet } from './types';

const BODY_W = 1600;
const BODY_BUDGET = 720;
const MIN_SCALE = 0.5;
const MIN_ORPHAN_DATA_ROWS = 4;
const DEFAULT_COL = 64;
const DEFAULT_ROW = 20;

function blockMinScale(block: PageBlock): number {
  const v = Number(block.minScale ?? MIN_SCALE);
  if (!Number.isFinite(v)) return MIN_SCALE;
  return Math.min(1, Math.max(0.2, v));
}

function blockAllowsContinuation(block: PageBlock): boolean {
  if (block.allowContinuation === false) return false;
  return (block.splitMode ?? 'auto_rows') !== 'none';
}

function excelBestScale(block: PageBlock): number {
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
  const src = ws.grid ?? [];
  const nRows0 = src.length;
  const nCols0 = Math.max(0, ...src.map((r) => r.length));
  const grid0 = src.map((r) => {
    const row = r.map(cellText);
    while (row.length < nCols0) row.push('');
    return row;
  });

  const stylesRc0: Record<string, ExcelCellStyle> = {};
  for (const [key, val] of Object.entries(ws.styles ?? {})) {
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

  const merges0 = (ws.mergedCells ?? []).map((m) => ({ ...m }));
  const trimmed = trimTrailingBlankRanges(grid0, stylesRc0, merges0, headerRows);
  const grid = trimmed.grid;
  const stylesRc = trimmed.styles;
  const nRows = grid.length;
  const nCols = Math.max(0, ...grid.map((r) => r.length));

  const colWidths = Array.from({ length: nCols }, (_, c) => ws.colWidthsPx?.[c] ?? DEFAULT_COL);
  const rowHeights = Array.from({ length: nRows }, (_, r) => ws.rowHeightsPx?.[r] ?? DEFAULT_ROW);

  return {
    id: blockId,
    type: 'excelRange',
    sourceWorksheetId: ws.id,
    sourceSheet: ws.sourceSheet || ws.name,
    sourceRange: ws.sourceRange || '',
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

/** Refresh a single page's block from the worksheet using its srcRows (values /
 *  fills / borders reflected, split pages stay non-duplicated). */
export function refreshBlockFromWorksheet(block: PageBlock, ws: Worksheet): PageBlock {
  const full = buildExcelRangeBlock(ws, `${ws.id}_xr`);
  const nRows = (full.grid ?? []).length;
  const rows = (block.srcRows ?? full.srcRows ?? []).filter((r) => r >= 0 && r < nRows);
  if (!rows.length) return full;
  return sliceBlock(full, rows, { keepId: block.id });
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

  const groupId = base.pageGroupId ?? base.id;
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
    displaySheetCode: base.sheetCode,
    repeatRows: parts[0].repeatRows,
  });

  for (let i = 1; i < parts.length; i += 1) {
    const contId = `${groupId}_c${i}`;
    const prev = byId.get(contId);
    const code = continuationCode(base.sheetCode, i);
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
