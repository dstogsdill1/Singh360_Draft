import type { ExcelCellStyle, MergedCell, PageBlock, PageModel } from './types';

const BODY_W = 1600;
const TARGET_W = Math.round(BODY_W * 0.92);
const DENSE_TARGET_W = Math.round(BODY_W * 0.94);

type LayoutBlock = PageBlock & {
  layoutProfile?: string;
  pageFamily?: string;
  bodyFontPt?: number;
  minFontPt?: number;
  wordWrapColumns?: number[];
  layoutReflowed?: boolean;
};

const NARROW = ['qty', 'quantity', 'no', 'number', '#', 'id', 'type', 'status', 'marker', 'step', 'ro#', 'di#', 'aio#'];
const WIDE = ['description', 'instruction', 'scope', 'use', 'purpose', 'device', 'location', 'destination', 'notes', 'remarks', 'language', 'responsibility'];

function norm(value: unknown): string {
  return String(value ?? '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function uniq(values: number[]): number[] {
  return Array.from(new Set(values)).sort((a, b) => a - b);
}

function meaningfulStyle(style?: ExcelCellStyle): boolean {
  if (!style) return false;
  if (style.fill) return true;
  const b = style.borders;
  return !!(b && (b.top || b.right || b.bottom || b.left));
}

export function inferLayoutProfile(
  page: Pick<PageModel, 'sheetTitle' | 'sheetTab' | 'pageFamily' | 'layoutProfile'>,
): string {
  const blob = norm(`${page.sheetTitle ?? ''} ${page.sheetTab ?? ''} ${page.pageFamily ?? ''}`);
  if (page.pageFamily === 'companyInfo') return 'company_info';
  if (page.pageFamily === 'idfTable') return 'network_48_port';
  if (blob.includes('equipment supply')) return 'equipment_supply_schedule';
  if (blob.includes('cable pull') || blob.includes('termination schedule')) return 'cable_termination_schedule';
  if (blob.includes('responsibility')) return 'responsibility_matrix';
  if (blob.includes('bill of material') || /\bbom\b/.test(blob)) return 'bill_of_materials_schedule';
  if (blob.includes('instruction')) return 'instruction_table';
  if (blob.includes('project scope') || blob.includes('workflow') || blob.includes('milestone')) {
    return 'front_matter_narrative_table';
  }
  if (page.layoutProfile) return page.layoutProfile;
  if (page.pageFamily === 'matrix') return 'responsibility_matrix';
  if (['ioSchedule', 'panelDetail', 'rackLayout'].includes(page.pageFamily ?? '')) return 'io_table';
  return 'front_matter_table';
}

function findHeaderRow(grid: string[][]): number {
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  if (!nCols) return 0;
  for (let r = 0; r < Math.min(grid.length, 12); r += 1) {
    const nonEmpty = (grid[r] ?? []).map((cell) => String(cell ?? '').trim()).filter(Boolean);
    if (nonEmpty.length < Math.max(2, Math.min(nCols, nCols - 1))) continue;
    if (nonEmpty.some((value) => value.length > 70)) continue;
    return r;
  }
  return 0;
}

function headerClass(value: string): 'narrow' | 'wide' | 'notes' | 'other' {
  const h = norm(value);
  if (h.includes('notes') || h.includes('remark') || h.includes('comment')) return 'notes';
  if (NARROW.some((token) => h.includes(token))) return 'narrow';
  if (WIDE.some((token) => h.includes(token))) return 'wide';
  return 'other';
}

function dropBlankColumns(block: LayoutBlock): LayoutBlock {
  const grid = (block.grid ?? []).map((row) => [...row]);
  const styles = { ...(block.styles ?? {}) };
  const merges = (block.mergedCells ?? []).map((merge) => ({ ...merge }));
  const nRows = grid.length;
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  if (nCols <= 1) return block;

  const keep: number[] = [];
  for (let c = 0; c < nCols; c += 1) {
    const hasValue = grid.some((row) => (row[c] ?? '').trim() !== '');
    const hasStyle = Array.from({ length: nRows }, (_, r) => styles[`${r}:${c}`]).some(meaningfulStyle);
    if (hasValue || hasStyle) keep.push(c);
  }
  if (!keep.length || keep.length === nCols) return block;

  const map = new Map<number, number>();
  keep.forEach((old, index) => map.set(old, index));
  const newGrid = grid.map((row) => keep.map((column) => row[column] ?? ''));
  const newStyles: Record<string, ExcelCellStyle> = {};
  Object.entries(styles).forEach(([key, style]) => {
    const [rs, cs] = key.split(':');
    const r = Number(rs);
    const c = Number(cs);
    if (map.has(c)) newStyles[`${r}:${map.get(c)}`] = style;
  });
  const newMerges: MergedCell[] = [];
  merges.forEach((merge) => {
    if (!map.has(merge.startCol) || !map.has(merge.endCol)) return;
    newMerges.push({
      ...merge,
      startCol: map.get(merge.startCol) as number,
      endCol: map.get(merge.endCol) as number,
    });
  });
  return {
    ...block,
    grid: newGrid,
    styles: newStyles,
    mergedCells: newMerges,
    colWidths: keep.map((column) => block.colWidths?.[column] ?? 64),
  };
}

function columnHasContent(grid: string[][], column: number): boolean {
  return grid.some((row) => (row[column] ?? '').trim() !== '');
}

function roleShare(profile: string, header: string, index: number, nCols: number): number {
  const h = norm(header);

  if (profile === 'equipment_supply_schedule') {
    if (h.includes('qty') || h.includes('quantity')) return 0.055;
    if (h.includes('item') || h.includes('part')) return 0.125;
    if (h.includes('description')) return 0.18;
    if (h.includes('scope') || h.includes('use')) return 0.21;
    if (h.includes('supplied')) return 0.095;
    if (h.includes('installed')) return 0.095;
    if (h.includes('destination') || h.includes('location')) return 0.14;
    if (h.includes('notes') || h.includes('remarks')) return 0.10;
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

  if (profile === 'responsibility_matrix') {
    return index === 0 ? 0.34 : 0.66 / Math.max(1, nCols - 1);
  }

  if (profile === 'bill_of_materials_schedule') {
    if (h.includes('qty') || h.includes('quantity')) return 0.06;
    if (h.includes('part') || h.includes('item') || h.includes('model')) return 0.17;
    if (h.includes('description')) return 0.30;
    if (h.includes('manufacturer')) return 0.16;
    if (h.includes('notes') || h.includes('remarks')) return 0.20;
  }

  const cls = headerClass(h);
  if (cls === 'narrow') return 0.07;
  if (cls === 'wide' || cls === 'notes') return 0.22;
  return 1 / Math.max(1, nCols);
}

function fitWidths(shares: number[], target: number, minimums: number[]): number[] {
  const total = shares.reduce((sum, value) => sum + value, 0) || 1;
  const widths = shares.map((share, index) => Math.max(minimums[index], Math.round(target * share / total)));
  let delta = target - widths.reduce((sum, value) => sum + value, 0);

  if (delta > 0) {
    const order = widths.map((_, index) => index).sort((a, b) => shares[b] - shares[a]);
    let cursor = 0;
    while (delta > 0 && order.length) {
      widths[order[cursor % order.length]] += 1;
      delta -= 1;
      cursor += 1;
    }
  } else if (delta < 0) {
    const order = widths.map((_, index) => index).sort(
      (a, b) => (widths[b] - minimums[b]) - (widths[a] - minimums[a]),
    );
    let cursor = 0;
    let guard = 0;
    while (delta < 0 && order.length && guard < 100000) {
      const index = order[cursor % order.length];
      if (widths[index] > minimums[index]) {
        widths[index] -= 1;
        delta += 1;
      }
      cursor += 1;
      guard += 1;
      if (order.every((item) => widths[item] <= minimums[item])) break;
    }
  }
  return widths;
}

function genericContentWidths(grid: string[][], headerRow: number, target: number): number[] {
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  const header = grid[headerRow] ?? [];
  const shares: number[] = [];
  const minimums: number[] = [];

  for (let c = 0; c < nCols; c += 1) {
    if (!columnHasContent(grid, c)) {
      shares.push(0.012);
      minimums.push(18);
      continue;
    }
    const cls = headerClass(String(header[c] ?? ''));
    const values = grid.map((row) => String(row[c] ?? ''));
    const longest = Math.max(1, ...values.map((value) => value.length));
    let weight = Math.max(5, Math.min(50, longest));
    if (cls === 'wide' || cls === 'notes') weight *= 1.9;
    if (cls === 'narrow') weight *= 0.55;
    shares.push(weight);
    minimums.push(cls === 'narrow' ? 46 : cls === 'wide' || cls === 'notes' ? 92 : 60);
  }
  return fitWidths(shares, target, minimums);
}

function preferredWidths(grid: string[][], profile: string): number[] {
  const nCols = Math.max(0, ...grid.map((row) => row.length));
  if (!nCols) return [];
  const headerRow = findHeaderRow(grid);
  const header = grid[headerRow] ?? [];

  if (profile === 'instruction_table' && nCols === 2) {
    return [Math.round(TARGET_W * 0.20), Math.round(TARGET_W * 0.80)];
  }

  if (profile === 'front_matter_narrative_table') {
    const shares = Array.from({ length: nCols }, (_, c) => {
      const cls = headerClass(String(header[c] ?? ''));
      if (cls === 'narrow') return 0.20;
      if (cls === 'wide') return 0.58;
      if (cls === 'notes') return 0.10;
      return 0.12;
    });
    const mins = shares.map((_, c) => headerClass(String(header[c] ?? '')) === 'narrow' ? 64 : 80);
    return fitWidths(shares, TARGET_W, mins);
  }

  const named = new Set([
    'equipment_supply_schedule',
    'cable_termination_schedule',
    'responsibility_matrix',
    'bill_of_materials_schedule',
  ]);
  if (named.has(profile)) {
    const target = profile === 'responsibility_matrix' ? DENSE_TARGET_W : TARGET_W;
    const shares: number[] = [];
    const minimums: number[] = [];
    for (let c = 0; c < nCols; c += 1) {
      if (!columnHasContent(grid, c)) {
        shares.push(0.012);
        minimums.push(18);
        continue;
      }
      const head = String(header[c] ?? '');
      shares.push(Math.max(0.015, roleShare(profile, head, c, nCols)));
      const cls = headerClass(head);
      minimums.push(cls === 'narrow' ? 46 : cls === 'wide' || cls === 'notes' ? 92 : 60);
    }
    return fitWidths(shares, target, minimums);
  }

  return genericContentWidths(grid, headerRow, profile === 'io_table' ? DENSE_TARGET_W : TARGET_W);
}

function wrapLines(text: string, width: number, fontPx: number): number {
  const clean = norm(text);
  if (!clean) return 1;
  const chars = Math.max(7, Math.floor(Math.max(36, width - 8) / Math.max(5.2, fontPx * 0.49)));
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
  const longest = Math.max(...words.map((word) => word.length), 1);
  return Math.max(lines, Math.ceil(longest / chars));
}

function estimatedRowHeights(
  grid: string[][],
  widths: number[],
  headerRows: number,
  profile: string,
): number[] {
  const dense = ['io_table', 'responsibility_matrix'].includes(profile);
  const fontPx = ['instruction_table', 'front_matter_narrative_table'].includes(profile) ? 12 : dense ? 10 : 11;
  const lineH = Math.round(fontPx * 1.23);

  return grid.map((row, r) => {
    let lines = 1;
    row.forEach((value, c) => {
      const maxLines = profile.includes('narrative') || profile === 'instruction_table' ? 12 : 8;
      lines = Math.max(lines, Math.min(wrapLines(String(value ?? ''), widths[c] ?? 64, fontPx), maxLines));
    });
    const base = r < headerRows ? 28 : dense ? 22 : 24;
    return Math.max(base, lineH * lines + 8);
  });
}

function nowrapColumns(grid: string[][], profile: string): number[] {
  const headerRow = findHeaderRow(grid);
  const header = grid[headerRow] ?? [];
  const result: number[] = [];
  header.forEach((value, index) => {
    const h = norm(value);
    const cls = headerClass(h);
    if (cls === 'narrow') result.push(index);
    if (profile === 'cable_termination_schedule' && ['circuit', 'tag', 'cable type', 'installed'].some((x) => h.includes(x))) {
      result.push(index);
    }
    if (profile === 'equipment_supply_schedule' && ['item', 'part', 'supplied', 'installed'].some((x) => h.includes(x))) {
      result.push(index);
    }
  });
  return uniq(result);
}

export function reflowExcelRangeBlock(page: PageModel, input: PageBlock): PageBlock {
  if (input.type !== 'excelRange') return input;
  const profile = inferLayoutProfile(page);
  let block = dropBlankColumns({ ...input } as LayoutBlock);
  const grid = block.grid ?? [];
  if (!grid.length) return block;

  const widths = preferredWidths(grid, profile);
  const headerRows = Math.max(Number(block.headerRowCount ?? 1), 1);
  const heights = estimatedRowHeights(grid, widths, headerRows, profile);
  const bodyFontPx = ['instruction_table', 'front_matter_narrative_table'].includes(profile) ? 12
    : ['equipment_supply_schedule', 'cable_termination_schedule', 'bill_of_materials_schedule', 'responsibility_matrix'].includes(profile) ? 11
      : undefined;
  const minScale = ['instruction_table', 'front_matter_narrative_table'].includes(profile)
    ? Math.max(Number(block.minScale ?? 0), 7.5 / 9)
    : ['equipment_supply_schedule', 'cable_termination_schedule', 'bill_of_materials_schedule', 'responsibility_matrix'].includes(profile)
      ? Math.max(Number(block.minScale ?? 0), 0.75)
      : Number(block.minScale ?? 0.5);

  block = {
    ...block,
    colWidths: widths,
    rowHeights: heights,
    minScale,
    scaleMode: 'fit_body',
    noGrow: false,
    nowrapColumns: nowrapColumns(grid, profile),
    bodyFontPx: bodyFontPx ?? block.bodyFontPx,
    gridLines: true,
    bodyRowFillMode: 'none',
  } as LayoutBlock;

  const ext = block as LayoutBlock;
  ext.layoutProfile = profile;
  ext.pageFamily = page.pageFamily;
  ext.layoutReflowed = true;
  if (bodyFontPx) {
    ext.bodyFontPt = bodyFontPx === 12 ? 8.5 : 8.0;
    ext.minFontPt = profile === 'instruction_table' || profile === 'front_matter_narrative_table' ? 7.5 : 7.0;
  }
  return block;
}
