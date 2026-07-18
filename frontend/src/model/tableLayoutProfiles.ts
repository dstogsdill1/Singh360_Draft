import type { ExcelCellStyle, MergedCell, PageBlock, PageModel } from './types';

const BODY_W = 1600;
const AUTO_TARGET = Math.round(BODY_W * 0.92);
const DENSE_TARGET = Math.round(BODY_W * 0.94);

type LayoutBlock = PageBlock & {
  layoutProfile?: string;
  bodyFontPt?: number;
  minFontPt?: number;
  layoutReflowed?: boolean;
  manualLayout?: boolean;
};

const MANAGED = new Set([
  'guideline_table',
  'instruction_table',
  'project_scope_table',
  'workflow_milestone_table',
  'contact_directory_table',
  'equipment_supply_schedule',
  'cable_termination_schedule',
  'bill_of_materials_schedule',
  'responsibility_matrix',
]);

const NARROW = ['qty', 'quantity', 'no', 'number', '#', 'id', 'type', 'status', 'marker', 'step', 'ro#', 'di#', 'aio#'];
const WIDE = ['description', 'instruction', 'scope', 'use', 'purpose', 'device', 'location', 'destination', 'notes', 'remarks', 'language', 'responsibility', 'guideline', 'deliverable', 'email'];

function norm(value: unknown): string {
  return String(value ?? '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function uniq(values: number[]): number[] {
  return Array.from(new Set(values)).sort((a, b) => a - b);
}

export function isManagedLayoutProfile(profile: string): boolean {
  return MANAGED.has(profile);
}

export function inferLayoutProfile(
  page: Pick<PageModel, 'sheetTitle' | 'sheetTab' | 'pageFamily' | 'layoutProfile'>,
): string {
  const text = norm(`${page.sheetTitle ?? ''} ${page.sheetTab ?? ''} ${page.pageFamily ?? ''}`);
  if (page.pageFamily === 'companyInfo') return 'company_info';
  if (page.pageFamily === 'idfTable') return 'network_48_port';
  if (text.includes('guideline')) return 'guideline_table';
  if (text.includes('field instruction') || text.includes('instruction')) return 'instruction_table';
  if (text.includes('project directory') || text.includes('contact')) return 'contact_directory_table';
  if (text.includes('project scope')) return 'project_scope_table';
  if (text.includes('workflow') || text.includes('milestone')) return 'workflow_milestone_table';
  if (text.includes('equipment supply')) return 'equipment_supply_schedule';
  if (text.includes('cable pull') || text.includes('termination schedule')) return 'cable_termination_schedule';
  if (text.includes('responsibility')) return 'responsibility_matrix';
  if (text.includes('bill of material') || /\bbom\b/.test(text)) return 'bill_of_materials_schedule';
  if (page.layoutProfile) return page.layoutProfile;
  if (['matrix', 'ioSchedule', 'panelDetail', 'rackLayout'].includes(page.pageFamily ?? '')) return 'io_table';
  return 'front_matter_table';
}

function findHeaderRow(grid: string[][]): number {
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  if (!nCols) return 0;
  for (let r = 0; r < Math.min(grid.length, 14); r += 1) {
    const values = (grid[r] ?? []).map((value) => String(value ?? '').trim());
    const nonEmpty = values.filter(Boolean);
    if (nonEmpty.length >= Math.max(2, nCols - 1) && !nonEmpty.some((value) => value.length > 80)) return r;
    const joined = nonEmpty.map(norm).join(' | ');
    if ((joined.includes('step') && joined.includes('instruction')) || (joined.includes('topic') && joined.includes('guideline'))) return r;
  }
  return 0;
}

function compactSemanticBlock(block: LayoutBlock, profile: string): LayoutBlock {
  if (!['guideline_table', 'instruction_table', 'project_scope_table', 'workflow_milestone_table', 'contact_directory_table'].includes(profile)) return block;

  const grid = (block.grid ?? []).map((row) => [...row]);
  if (!grid.length) return block;
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  const padded = grid.map((row) => [...row, ...Array(Math.max(0, nCols - row.length)).fill('')]);
  const keepCols = Array.from({ length: nCols }, (_, c) => c).filter((c) => padded.some((row) => (row[c] ?? '').trim()));
  const keepRows = padded.map((row, r) => ({ row, r })).filter(({ row }) => row.some((value) => (value ?? '').trim())).map(({ r }) => r);
  if (!keepCols.length || !keepRows.length) return block;

  const colMap = new Map(keepCols.map((old, index) => [old, index]));
  const rowMap = new Map(keepRows.map((old, index) => [old, index]));
  const styles: Record<string, ExcelCellStyle> = {};
  Object.entries(block.styles ?? {}).forEach(([key, value]) => {
    const [rs, cs] = key.split(':');
    const r = Number(rs);
    const c = Number(cs);
    if (rowMap.has(r) && colMap.has(c)) styles[`${rowMap.get(r)}:${colMap.get(c)}`] = value;
  });

  const merges: MergedCell[] = [];
  (block.mergedCells ?? []).forEach((merge) => {
    const rows = keepRows.filter((r) => r >= merge.startRow && r <= merge.endRow);
    const cols = keepCols.filter((c) => c >= merge.startCol && c <= merge.endCol);
    if (!rows.length || !cols.length) return;
    merges.push({
      startRow: Math.min(...rows.map((r) => rowMap.get(r) as number)),
      endRow: Math.max(...rows.map((r) => rowMap.get(r) as number)),
      startCol: Math.min(...cols.map((c) => colMap.get(c) as number)),
      endCol: Math.max(...cols.map((c) => colMap.get(c) as number)),
    });
  });

  const oldRepeat = block.repeatRows ?? [];
  const mappedRepeat = oldRepeat.filter((r) => rowMap.has(r)).map((r) => rowMap.get(r) as number);
  const oldHeaderCount = Number(block.headerRowCount ?? 1);
  const mappedHeaders = keepRows.filter((r) => r < oldHeaderCount).map((r) => rowMap.get(r) as number);

  return {
    ...block,
    grid: keepRows.map((r) => keepCols.map((c) => padded[r][c] ?? '')),
    styles,
    mergedCells: merges,
    colWidths: keepCols.map((c) => block.colWidths?.[c] ?? 64),
    rowHeights: keepRows.map((r) => block.rowHeights?.[r] ?? 20),
    srcRows: keepRows.map((r) => block.srcRows?.[r] ?? r),
    repeatRows: uniq(mappedRepeat),
    headerRowCount: mappedHeaders.length ? Math.max(...mappedHeaders) + 1 : Math.min(keepRows.length, findHeaderRow(keepRows.map((r) => keepCols.map((c) => padded[r][c] ?? ''))) + 1),
  };
}

function fitWidths(shares: number[], target: number, minimums: number[]): number[] {
  const total = shares.reduce((sum, value) => sum + value, 0) || 1;
  const widths = shares.map((share, index) => Math.max(minimums[index], Math.round(target * share / total)));
  let delta = target - widths.reduce((sum, value) => sum + value, 0);
  if (delta > 0) {
    const order = widths.map((_, i) => i).sort((a, b) => shares[b] - shares[a]);
    let cursor = 0;
    while (delta > 0 && order.length) {
      widths[order[cursor % order.length]] += 1;
      cursor += 1;
      delta -= 1;
    }
  } else if (delta < 0) {
    const order = widths.map((_, i) => i).sort((a, b) => (widths[b] - minimums[b]) - (widths[a] - minimums[a]));
    let cursor = 0;
    let guard = 0;
    while (delta < 0 && order.length && guard < 200000) {
      const index = order[cursor % order.length];
      if (widths[index] > minimums[index]) {
        widths[index] -= 1;
        delta += 1;
      }
      cursor += 1;
      guard += 1;
      if (order.every((i) => widths[i] <= minimums[i])) break;
    }
  }
  return widths;
}

function normalizeManualWidths(widths: number[]): number[] {
  if (!widths.length) return [];
  const clean = widths.map((value) => Math.max(36, Math.round(Number(value || 64))));
  const total = clean.reduce((sum, value) => sum + value, 0) || 1;
  return fitWidths(clean.map((value) => value / total), AUTO_TARGET, clean.map(() => 36));
}

function roleShare(profile: string, header: string, index: number, nCols: number): number {
  const h = norm(header);
  if (['guideline_table', 'instruction_table'].includes(profile)) {
    if (['step', 'topic', 'section'].some((x) => h.includes(x))) return 0.20;
    if (['instruction', 'guideline', 'description'].some((x) => h.includes(x))) return 0.80;
  }
  if (profile === 'project_scope_table') {
    if (h.includes('section')) return 0.22;
    if (h.includes('scope') || h.includes('language')) return 0.58;
    if (h.includes('status')) return 0.08;
    if (h.includes('notes')) return 0.12;
  }
  if (profile === 'workflow_milestone_table') {
    if (h.includes('step')) return 0.06;
    if (h.includes('milestone')) return 0.18;
    if (h.includes('task') || h.includes('deliverable')) return 0.38;
    if (h.includes('owner')) return 0.13;
    if (h.includes('status')) return 0.08;
    if (h.includes('notes')) return 0.17;
  }
  if (profile === 'contact_directory_table') {
    if (h.includes('trade') || h.includes('code')) return 0.08;
    if (h.includes('role') || h.includes('responsibility')) return 0.21;
    if (h.includes('firm')) return 0.18;
    if (h.includes('contact')) return 0.15;
    if (h.includes('phone')) return 0.15;
    if (h.includes('email')) return 0.23;
  }
  if (profile === 'equipment_supply_schedule') {
    if (h.includes('qty') || h.includes('quantity')) return 0.055;
    if (h.includes('item') || h.includes('part')) return 0.125;
    if (h.includes('description')) return 0.18;
    if (h.includes('scope') || h.includes('use')) return 0.20;
    if (h.includes('supplied')) return 0.09;
    if (h.includes('installed')) return 0.09;
    if (h.includes('destination') || h.includes('location')) return 0.14;
    if (h.includes('notes') || h.includes('remarks')) return 0.12;
  }
  if (profile === 'cable_termination_schedule') {
    if (h.includes('marker')) return 0.05;
    if (h.includes('circuit') || h.includes('tag')) return 0.085;
    if (h.includes('cable type')) return 0.145;
    if (h === 'from') return 0.12;
    if (h === 'to') return 0.12;
    if (h.includes('purpose') || h.includes('device')) return 0.18;
    if (h.includes('cable standard')) return 0.13;
    if (h.includes('installed')) return 0.075;
    if (h.includes('notes')) return 0.095;
  }
  if (profile === 'bill_of_materials_schedule') {
    if (h.includes('qty') || h.includes('quantity')) return 0.06;
    if (h.includes('part') || h.includes('item') || h.includes('model')) return 0.16;
    if (h.includes('description')) return 0.27;
    if (h.includes('comment')) return 0.21;
    if (h.includes('installed')) return 0.13;
    if (h.includes('status') || h.includes('notes')) return 0.17;
  }
  if (profile === 'responsibility_matrix') {
    if (nCols <= 5) {
      if (h.includes('section')) return 0.14;
      if (h.includes('item')) return 0.28;
      if (h.includes('responsibility')) return 0.18;
      if (h.includes('notes')) return 0.40;
    } else {
      if (h.includes('task') || h.includes('component')) return 0.28;
      if (h.includes('notes')) return 0.22;
      return 0.50 / Math.max(1, nCols - 2);
    }
  }
  if (NARROW.some((x) => h.includes(x))) return 0.07;
  if (WIDE.some((x) => h.includes(x))) return 0.22;
  return 1 / Math.max(1, nCols);
}

function preferredWidths(grid: string[][], profile: string): number[] {
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  if (!nCols) return [];
  const header = grid[findHeaderRow(grid)] ?? [];
  const target = profile === 'responsibility_matrix' && nCols > 5 ? DENSE_TARGET : AUTO_TARGET;
  const shares: number[] = [];
  const minimums: number[] = [];
  for (let c = 0; c < nCols; c += 1) {
    const h = String(header[c] ?? '');
    const hasText = grid.some((row) => (row[c] ?? '').trim());
    if (!hasText) {
      shares.push(0.012);
      minimums.push(18);
      continue;
    }
    shares.push(Math.max(0.015, roleShare(profile, h, c, nCols)));
    const low = norm(h);
    minimums.push(NARROW.some((x) => low.includes(x)) ? 46 : WIDE.some((x) => low.includes(x)) ? 92 : 60);
  }
  return fitWidths(shares, target, minimums);
}

function bodyFontPx(profile: string, nCols: number): number | undefined {
  if (['guideline_table', 'instruction_table'].includes(profile)) return 14;
  if (['project_scope_table', 'workflow_milestone_table', 'contact_directory_table'].includes(profile)) return 13;
  if (['equipment_supply_schedule', 'cable_termination_schedule', 'bill_of_materials_schedule'].includes(profile)) return 12;
  if (profile === 'responsibility_matrix') return nCols <= 5 ? 13 : 11;
  return undefined;
}

function minScale(profile: string, nCols: number): number | undefined {
  if (['guideline_table', 'instruction_table'].includes(profile)) return 0.90;
  if (['project_scope_table', 'workflow_milestone_table', 'contact_directory_table'].includes(profile)) return 0.84;
  if (['equipment_supply_schedule', 'cable_termination_schedule', 'bill_of_materials_schedule'].includes(profile)) return 0.80;
  if (profile === 'responsibility_matrix') return nCols <= 5 ? 0.82 : 0.72;
  return undefined;
}

function mergeMaps(merges: MergedCell[]): { covered: Set<string>; spans: Map<string, number> } {
  const covered = new Set<string>();
  const spans = new Map<string, number>();
  merges.forEach((merge) => {
    spans.set(`${merge.startRow}:${merge.startCol}`, merge.endCol - merge.startCol + 1);
    for (let r = merge.startRow; r <= merge.endRow; r += 1) {
      for (let c = merge.startCol; c <= merge.endCol; c += 1) {
        if (r === merge.startRow && c === merge.startCol) continue;
        covered.add(`${r}:${c}`);
      }
    }
  });
  return { covered, spans };
}

function wrappedLines(text: string, width: number, fontPx: number): number {
  const clean = norm(text);
  if (!clean) return 1;
  const chars = Math.max(8, Math.floor(Math.max(36, width - 10) / Math.max(5.4, fontPx * 0.50)));
  const words = clean.split(' ');
  let lines = 1;
  let used = 0;
  words.forEach((word) => {
    if (used && used + 1 + word.length > chars) {
      lines += 1;
      used = word.length;
    } else {
      used += (used ? 1 : 0) + word.length;
    }
  });
  return Math.max(lines, Math.ceil(Math.max(...words.map((word) => word.length), 1) / chars));
}

function rowHeights(grid: string[][], widths: number[], merges: MergedCell[], profile: string, headerRows: number, fontPx: number, manual: boolean, source?: number[]): number[] {
  if (manual && source?.length) return source.slice(0, grid.length).map((value) => Math.max(18, Math.min(180, Math.round(value || 20))));
  const { covered, spans } = mergeMaps(merges);
  const realHeader = findHeaderRow(grid);
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  const dense = profile === 'responsibility_matrix' && nCols > 5;
  const lineH = Math.max(13, Math.round(fontPx * 1.25));
  return grid.map((row, r) => {
    const values = row.map((value) => String(value ?? '').trim());
    const nonEmpty = values.filter(Boolean);
    if (!nonEmpty.length) return 14;
    let lines = 1;
    let full = false;
    values.forEach((value, c) => {
      if (!value || covered.has(`${r}:${c}`)) return;
      const span = spans.get(`${r}:${c}`) ?? 1;
      const width = Array.from({ length: span }, (_, i) => widths[c + i] ?? 64).reduce((sum, value2) => sum + value2, 0);
      if (span >= Math.max(1, nCols - 1)) full = true;
      lines = Math.max(lines, Math.min(wrappedLines(value, width, fontPx), ['guideline_table', 'instruction_table', 'project_scope_table'].includes(profile) ? 14 : 9));
    });
    const base = r < realHeader && full ? (r === 0 ? 30 : 32) : r === realHeader ? 30 : full && nonEmpty.length === 1 ? 28 : dense ? 22 : 25;
    return Math.max(base, lineH * lines + 8);
  });
}

function nowrapColumns(grid: string[][], profile: string): number[] {
  const header = grid[findHeaderRow(grid)] ?? [];
  const out: number[] = [];
  header.forEach((value, index) => {
    const h = norm(value);
    if (NARROW.some((x) => h.includes(x))) out.push(index);
    if (profile === 'cable_termination_schedule' && ['circuit', 'tag', 'cable type', 'installed'].some((x) => h.includes(x))) out.push(index);
    if (profile === 'equipment_supply_schedule' && ['item', 'part', 'supplied', 'installed'].some((x) => h.includes(x))) out.push(index);
    if (profile === 'contact_directory_table' && ['trade', 'phone', 'email'].some((x) => h.includes(x))) out.push(index);
  });
  return uniq(out);
}

export function reflowExcelRangeBlock(page: PageModel, input: PageBlock): PageBlock {
  if (input.type !== 'excelRange') return input;
  const profile = inferLayoutProfile(page);
  let block = compactSemanticBlock({ ...input } as LayoutBlock, profile);
  const grid = block.grid ?? [];
  if (!grid.length) return block;

  const manual = !!block.manualLayout;
  const widths = manual ? normalizeManualWidths(block.colWidths ?? []) : (isManagedLayoutProfile(profile) ? preferredWidths(grid, profile) : block.colWidths ?? []);
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  const font = manual ? undefined : bodyFontPx(profile, nCols);
  const headerRows = Math.max(Number(block.headerRowCount ?? 1), 1);
  const heights = rowHeights(grid, widths, block.mergedCells ?? [], profile, headerRows, font ?? 12, manual, block.rowHeights);
  const floor = manual ? Number(block.minScale ?? 0.5) : (minScale(profile, nCols) ?? Number(block.minScale ?? 0.5));

  block = {
    ...block,
    colWidths: widths,
    rowHeights: heights,
    minScale: floor,
    scaleMode: 'fit_body',
    noGrow: false,
    nowrapColumns: nowrapColumns(grid, profile),
    bodyFontPx: font ?? block.bodyFontPx,
    gridLines: true,
    bodyRowFillMode: 'none',
  } as LayoutBlock;

  const ext = block as LayoutBlock;
  ext.layoutProfile = profile;
  ext.layoutReflowed = true;
  if (font) {
    ext.bodyFontPt = Number((font * 0.75).toFixed(2));
    ext.minFontPt = profile === 'responsibility_matrix' && nCols > 5 ? 7 : ['guideline_table', 'instruction_table'].includes(profile) ? 9 : 8;
  }
  return block;
}
