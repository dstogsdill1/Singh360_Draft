// Client mirror of core/workbook_importer.py RDM/IDF network table builder.
// Used when rebuilding network_48_port pages from source — never raw excelRange.
// S360_HEB_IDF_SWITCH_MATRIX_V1: H-E-B seven-column switch-pair profile.

import type { PageBlock, Worksheet } from './types';

const BODY_W = 1600;
const BODY_BUDGET = 720;
const IDF_TARGET_FONT = 7.0;
const IDF_PREFERRED_FONT = 7.5;
const IDF_MIN_FONT = 6.5;
const IDF_ROW_H = 20;
const IDF_HEADER_H = 24;
const IDF_SCALE_TARGET_MIN = 0.65;
const IDF_SCALE_TARGET_MAX = 0.75;

const HEB_TABLE_PROFILE = 'heb_idf_switch_matrix';
const HEB_HEADERS = ['Label #', 'Description', 'Controller ID', 'IP Address', 'IDF#', 'Switch#', 'Port#'];
const HEB_COL_WIDTHS = [98, 354, 98, 86, 38, 62, 46];
const HEB_FONT_SIZE = 8.0;
const HEB_HEADER_HEIGHT = 20;
const HEB_BODY_BUDGET = 690;

const IDF_COL_W: Record<string, number> = {
  Port: 40,
  Label: 64,
  'Device / Drop': 130,
  'Controller ID': 70,
  'IP Address': 82,
  Network: 62,
  From: 60,
  To: 60,
  Path: 170,
  Cable: 66,
  Notes: 117,
  'Terminated By': 70,
};

const IDF_REQUIRED_COLS = [
  'Port',
  'Label',
  'Device / Drop',
  'Controller ID',
  'IP Address',
  'Network',
  'From',
  'To',
  'Cable',
  'Notes',
] as const;

const DEVICE_ABBREVIATIONS: Record<string, string> = {
  controller: 'Ctrl',
  connection: 'Conn',
  connector: 'Conn',
  distribution: 'Dist',
  management: 'Mgmt',
  network: 'Net',
  wireless: 'WiFi',
  equipment: 'Eqp',
};

function normalizeHeaderCell(h: unknown): string {
  return String(h ?? '').trim().replace(/#/g, ' # ').replace(/\s+/g, ' ').toLowerCase();
}

function compactHeaderCell(h: unknown): string {
  return normalizeHeaderCell(h).replace(/\s+/g, '');
}

interface HebHeaderMap {
  label: number | null;
  description: number | null;
  controller: number | null;
  ip: number | null;
  idf: number | null;
  switchNo: number | null;
  port: number | null;
}

function hebHeaderMap(row: unknown[]): HebHeaderMap {
  const low = row.map(normalizeHeaderCell);
  const compact = row.map(compactHeaderCell);

  const find = (kind: keyof HebHeaderMap): number | null => {
    for (let i = 0; i < low.length; i += 1) {
      const h = low[i];
      const c = compact[i];
      if (kind === 'label' && (c === 'label#' || c === 'label' || h.startsWith('label #'))) return i;
      if (kind === 'description' && h === 'description') return i;
      if (kind === 'controller' && (h.includes('controller id') || c === 'controllerid')) return i;
      if (kind === 'ip' && (h.includes('ip address') || c === 'ipaddress' || c === 'ipaddr')) return i;
      if (kind === 'idf' && (c === 'idf#' || c === 'idf' || h.startsWith('idf #'))) return i;
      if (kind === 'switchNo' && (c === 'switch#' || c === 'switch' || h.startsWith('switch #'))) return i;
      if (kind === 'port' && (c === 'port#' || c === 'port' || h.startsWith('port #'))) return i;
    }
    return null;
  };

  return {
    label: find('label'),
    description: find('description'),
    controller: find('controller'),
    ip: find('ip'),
    idf: find('idf'),
    switchNo: find('switchNo'),
    port: find('port'),
  };
}

function hebHeaderScore(mapping: HebHeaderMap): number {
  return Object.values(mapping).filter((value) => value != null).length;
}

export function hebIdfHeaderRow(grid: string[][]): number | null {
  let fallback: { score: number; row: number } | null = null;
  for (let r = 0; r < Math.min(grid.length, 24); r += 1) {
    const mapping = hebHeaderMap(grid[r] ?? []);
    const score = hebHeaderScore(mapping);
    if (score === 7) return r;
    if (score >= 6 && mapping.switchNo != null && mapping.port != null && mapping.label != null) {
      if (!fallback || score > fallback.score) fallback = { score, row: r };
    }
  }
  return fallback?.row ?? null;
}

function isHebIdfSwitchMatrix(grid: string[][], headerRow: number): boolean {
  if (headerRow < 0 || headerRow >= grid.length) return false;
  return hebHeaderScore(hebHeaderMap(grid[headerRow] ?? [])) === 7;
}

function looksLikeRepeatedHebHeader(row: string[]): boolean {
  return hebHeaderScore(hebHeaderMap(row ?? [])) >= 6;
}

function plainNumber(value: unknown): string {
  const text = String(value ?? '').trim();
  return /^[-+]?\d+\.0+$/.test(text) ? text.split('.', 1)[0] : text;
}

function sourceCell(row: string[], index: number | null, integerish = false): string {
  if (index == null || index < 0 || index >= row.length) return '';
  const value = String(row[index] ?? '').trim();
  return integerish ? plainNumber(value) : value;
}

interface HebSwitchGroup {
  idf: string;
  switchNo: string;
  rows: string[][];
}

function parseHebGroups(grid: string[][], headerRow: number): { groups: HebSwitchGroup[]; warnings: string[] } {
  const mapping = hebHeaderMap(grid[headerRow] ?? []);
  const specs = [
    mapping.label,
    mapping.description,
    mapping.controller,
    mapping.ip,
    mapping.idf,
    mapping.switchNo,
    mapping.port,
  ];
  const groups = new Map<string, HebSwitchGroup>();
  const warnings: string[] = [];
  let currentKey: string | null = null;

  for (let ri = headerRow + 1; ri < grid.length; ri += 1) {
    const sourceRow = grid[ri] ?? [];
    if (looksLikeRepeatedHebHeader(sourceRow)) continue;
    const values = specs.map((index, position) => sourceCell(sourceRow, index, [2, 4, 5, 6].includes(position)));
    if (!values.some(Boolean)) continue;

    const [label, description, controller, ip, idf, switchNo, port] = values;
    if (!port && ![label, description, controller, ip].some(Boolean)) continue;

    let key = `${idf}\u0000${switchNo}`;
    if (!idf && !switchNo && currentKey) {
      key = currentKey;
    } else if (idf || switchNo) {
      currentKey = key;
    }
    if (!switchNo) {
      warnings.push(`Source row ${ri + 1} has network data but no Switch#; row was kept in an unnumbered switch group.`);
    }
    const existing = groups.get(key) ?? { idf, switchNo, rows: [] };
    existing.rows.push(values);
    groups.set(key, existing);
  }

  return { groups: [...groups.values()], warnings };
}

function worksheetIdfNumber(sheetName: string, groups: HebSwitchGroup[]): string {
  const match = /\bIDF\s*#?\s*(\d+)\b/i.exec(sheetName ?? '');
  if (match) return match[1];
  const source = [...new Set(groups.map((group) => group.idf).filter(Boolean))];
  return source.length === 1 ? source[0] : '';
}

function switchText(value: string): string {
  return String(value || '?').trim() || '?';
}

function hebTitle(idf: string, switches: string[]): string {
  const base = idf ? `IDF #${idf}` : 'IDF';
  if (switches.length >= 2) return `${base} TABLE (SWITCH ${switches[0]} & ${switches[1]})`;
  if (switches.length === 1) return `${base} TABLE (SWITCH ${switches[0]})`;
  return `${base} TABLE`;
}

function hebRowHeight(maxRows: number): number {
  if (maxRows <= 0) return 13;
  const fitted = Math.floor((HEB_BODY_BUDGET - HEB_HEADER_HEIGHT) / maxRows);
  return Math.max(11, Math.min(14, fitted));
}

function buildHebIdfNetworkBlock(
  ws: Worksheet,
  headerRow: number,
  blockId: string,
  pairIndex = 0,
): PageBlock | null {
  const grid = ws.grid ?? [];
  if (!isHebIdfSwitchMatrix(grid, headerRow)) return null;

  const parsed = parseHebGroups(grid, headerRow);
  const groups = parsed.groups;
  if (!groups.length) return null;

  const pageCount = Math.ceil(groups.length / 2);
  const selectedPairIndex = Math.max(0, Math.min(Math.trunc(pairIndex || 0), pageCount - 1));
  const selected = groups.slice(selectedPairIndex * 2, selectedPairIndex * 2 + 2);
  const sheetName = ws.sourceSheet || ws.name || '';
  const idf = worksheetIdfNumber(sheetName, groups);
  const warnings = [...parsed.warnings];
  const sourceIdfs = [...new Set(groups.map((group) => group.idf).filter(Boolean))];
  if (idf && sourceIdfs.length && !(sourceIdfs.length === 1 && sourceIdfs[0] === idf)) {
    warnings.push(`Worksheet title identifies IDF #${idf}, but source IDF# values are ${sourceIdfs.join(', ')}; source values were preserved.`);
  }

  const switches = selected.map((group) => switchText(group.switchNo));
  const maxRows = Math.max(...selected.map((group) => group.rows.length), 0);
  const rowHeight = hebRowHeight(maxRows);
  const layoutMode: 'single' | 'two_up' = selected.length === 2 ? 'two_up' : 'single';
  const contentWidth = HEB_COL_WIDTHS.reduce((sum, width) => sum + width, 0) * (layoutMode === 'two_up' ? 2 : 1)
    + (layoutMode === 'two_up' ? 18 : 0);

  return {
    id: blockId,
    type: 'idfNetworkTable',
    sourceWorksheetId: ws.id,
    sourceSheet: sheetName,
    sourceRange: ws.sourceRange || '',
    renderMode: 'excel_exact',
    tableProfile: HEB_TABLE_PROFILE,
    layoutMode,
    sectionTitle: hebTitle(idf, switches),
    headers: [...HEB_HEADERS],
    rows: layoutMode === 'single' ? selected[0].rows : [],
    leftRows: layoutMode === 'two_up' ? selected[0].rows : [],
    rightRows: layoutMode === 'two_up' ? selected[1].rows : [],
    leftCaption: '',
    rightCaption: '',
    portRangeLeft: '',
    portRangeRight: '',
    colWidths: [...HEB_COL_WIDTHS],
    rowHeight,
    headerHeight: HEB_HEADER_HEIGHT,
    fontSize: HEB_FONT_SIZE,
    contentWidth,
    contentHeight: HEB_HEADER_HEIGHT + maxRows * rowHeight,
    sourceRowCount: groups.reduce((sum, group) => sum + group.rows.length, 0),
    bodyRowFillMode: 'none',
    gridLines: true,
    styleRole: 'network-two-up',
    splitMode: 'none',
    allowContinuation: false,
    minScale: 1.0,
    scaleMode: 'fit_body',
    orientation: 'landscape',
    editable: false,
    layoutWarnings: warnings,
    pageCount,
    pairIndex: selectedPairIndex,
    switchKeys: switches,
    scaledUp: false,
  };
}

function idfColIndex(headers: string[], ...keys: string[]): number | null {
  const low = headers.map(normalizeHeaderCell);
  for (let i = 0; i < low.length; i += 1) {
    const h = low[i];
    if (!h) continue;
    if (keys.some((k) => h.includes(k))) return i;
  }
  return null;
}

/** First row that looks like a real network header. H-E-B exact header wins. */
export function idfHeaderRow(grid: string[][]): number | null {
  const heb = hebIdfHeaderRow(grid);
  if (heb != null) return heb;

  for (let r = 0; r < Math.min(grid.length, 12); r += 1) {
    const low = (grid[r] ?? []).map(normalizeHeaderCell);
    const hasPort = low.some((c) => c && c.includes('port'));
    const hasLabel = low.some((c) => c && (c.includes('label') || c.includes('device') || c.includes('drop')));
    const hasCtrl = low.some((c) => c && (c.includes('controller') || c.includes('ip address') || c.includes('ip addr')));
    const hasNetwork = low.some((c) => c && c.includes('network'));
    if (hasPort && (hasLabel || hasCtrl || hasNetwork)) return r;
    if (hasCtrl && hasNetwork) return r;
  }
  return null;
}

type ColSpec = [string, number[]];

function idfColumns(headers: string[], showTerminatedBy: boolean): ColSpec[] {
  const idx = {
    port: idfColIndex(headers, 'port'),
    label: idfColIndex(headers, 'label'),
    device: idfColIndex(headers, 'device', 'drop', 'location'),
    controllerId: idfColIndex(headers, 'controller id', 'controller'),
    ip: idfColIndex(headers, 'ip address', 'ip addr', 'ip'),
    network: idfColIndex(headers, 'network', 'vlan'),
    from: idfColIndex(headers, 'from'),
    to: idfColIndex(headers, 'to'),
    cable: idfColIndex(headers, 'cable'),
    notes: idfColIndex(headers, 'notes', 'remark', 'comment'),
    terminated: idfColIndex(headers, 'terminated by', 'terminated'),
  };

  let cols: ColSpec[] = [
    ['Port', idx.port != null ? [idx.port] : []],
    ['Label', idx.label != null ? [idx.label] : []],
    ['Device / Drop', idx.device != null ? [idx.device] : []],
    ['Controller ID', idx.controllerId != null ? [idx.controllerId] : []],
    ['IP Address', idx.ip != null ? [idx.ip] : []],
    ['Network', idx.network != null ? [idx.network] : []],
    ['From', idx.from != null ? [idx.from] : []],
    ['To', idx.to != null ? [idx.to] : []],
    ['Cable', idx.cable != null ? [idx.cable] : []],
    ['Notes', idx.notes != null ? [idx.notes] : []],
  ];
  cols = cols.filter((c) => c[1].length > 0 || IDF_REQUIRED_COLS.includes(c[0] as typeof IDF_REQUIRED_COLS[number]));

  if (showTerminatedBy && idx.terminated != null) {
    cols.push(['Terminated By', [idx.terminated]]);
  }

  if (cols.length > 11 && idx.from != null && idx.to != null) {
    cols = cols.filter((c) => c[0] !== 'From' && c[0] !== 'To');
    const insertAt = Math.min(6, cols.length);
    cols.splice(insertAt, 0, ['Path', [idx.from, idx.to]]);
  }
  return cols;
}

function idfCellValue(row: string[], spec: number[]): string {
  const parts = spec
    .filter((i) => i < row.length)
    .map((i) => String(row[i] ?? '').trim())
    .filter(Boolean);
  return parts.join(' / ');
}

function abbreviateDeviceText(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  let out = text;
  for (const [longWord, short] of Object.entries(DEVICE_ABBREVIATIONS)) {
    out = out.replace(new RegExp(longWord, 'gi'), short);
    if (out.length <= maxChars) return out;
  }
  if (out.length > maxChars) return `${out.slice(0, Math.max(1, maxChars - 1))}…`;
  return out;
}

export function isIdfNetworkPage(page: { layoutProfile?: string; pageFamily?: string; blocks?: PageBlock[] }): boolean {
  if (page.layoutProfile === 'network_48_port') return true;
  if (page.pageFamily === 'idfTable') return true;
  const b = (page.blocks ?? [])[0];
  return b?.type === 'idfNetworkTable';
}

/** Build either the H-E-B switch-pair table or the legacy generic IDF table. */
export function buildIdfNetworkBlock(
  ws: Worksheet,
  headerRow: number,
  blockId: string,
  opts?: { showTerminatedBy?: boolean; pairIndex?: number },
): PageBlock {
  const grid = ws.grid ?? [];
  const hebHeader = hebIdfHeaderRow(grid);
  if (hebHeader != null) {
    const heb = buildHebIdfNetworkBlock(ws, hebHeader, blockId, opts?.pairIndex ?? 0);
    if (heb) return heb;
  }

  const showTerminatedBy = opts?.showTerminatedBy ?? false;
  const headersSrc = grid[headerRow] ?? [];

  const assemble = (
    terminatedBy: boolean,
    deviceMaxChars?: number | null,
  ): [string[], number[], string[][], number] => {
    const cols = idfColumns(headersSrc, terminatedBy);
    const hdrs = cols.map((c) => c[0]);
    const widths = hdrs.map((h) => IDF_COL_W[h] ?? 90);
    const deviceI = hdrs.indexOf('Device / Drop');
    const rowsAll: string[][] = [];
    for (let ri = headerRow + 1; ri < grid.length; ri += 1) {
      const row = grid[ri] ?? [];
      const vals = cols.map(([, spec]) => idfCellValue(row, spec));
      if (deviceI >= 0 && deviceMaxChars) {
        vals[deviceI] = abbreviateDeviceText(vals[deviceI], deviceMaxChars);
      }
      if (vals.some((v) => v)) rowsAll.push(vals);
    }
    return [hdrs, widths, rowsAll, widths.reduce((a, b) => a + b, 0)];
  };

  const usableW = BODY_W - 80;
  const twoUpUsable = Math.floor((usableW - 18) / 2);

  let [headers, colWidths, allDataRows, singleW] = assemble(showTerminatedBy);

  if (singleW > twoUpUsable && showTerminatedBy) {
    [headers, colWidths, allDataRows, singleW] = assemble(false);
  }

  if (singleW > twoUpUsable) {
    const baseDeviceW = IDF_COL_W['Device / Drop'] ?? 130;
    const overflow = singleW - twoUpUsable;
    const shrunkW = Math.max(70, baseDeviceW - overflow);
    const maxChars = Math.max(8, Math.floor(shrunkW / 7.2));
    [headers, colWidths, allDataRows, singleW] = assemble(false, maxChars);
    const di = headers.indexOf('Device / Drop');
    if (di >= 0) {
      colWidths[di] = shrunkW;
      singleW = colWidths.reduce((a, b) => a + b, 0);
    }
  }

  const titleLines: string[] = [];
  for (let r = 0; r < headerRow; r += 1) {
    const line = (grid[r] ?? []).map((c) => String(c ?? '').trim()).filter(Boolean).join(' ');
    if (line) titleLines.push(line);
  }
  const sectionTitle = titleLines.join(' — ');

  const dataRows = allDataRows;
  const n = dataRows.length;

  let rowH = IDF_ROW_H;
  const headerH = IDF_HEADER_H;
  const singleH = headerH + n * rowH;
  const half = n ? Math.floor((n + 1) / 2) : 0;
  const twoUpH = headerH + half * rowH;

  let layoutMode: 'single' | 'two_up' = 'two_up';
  let fontSize = IDF_PREFERRED_FONT;
  const needsHardSplit = twoUpH > BODY_BUDGET;

  if (singleW <= usableW && singleH <= BODY_BUDGET) {
    layoutMode = 'single';
    fontSize = IDF_PREFERRED_FONT;
  } else if (needsHardSplit) {
    layoutMode = 'two_up';
    fontSize = IDF_MIN_FONT;
  } else {
    layoutMode = 'two_up';
    fontSize = IDF_PREFERRED_FONT;
  }

  let contentH = layoutMode === 'single' || needsHardSplit ? singleH : twoUpH;
  const fillRatio = BODY_BUDGET ? contentH / BODY_BUDGET : 1;
  if (!needsHardSplit && fillRatio < 0.55 && n > 0) {
    const targetH = Math.floor(BODY_BUDGET * IDF_SCALE_TARGET_MIN);
    const rowsForH = layoutMode === 'single' ? n : Math.max(1, half);
    let grownRow = Math.max(rowH, Math.floor((targetH - headerH) / rowsForH));
    const maxH = Math.floor(BODY_BUDGET * IDF_SCALE_TARGET_MAX);
    while (headerH + grownRow * rowsForH > maxH && grownRow > rowH) grownRow -= 1;
    rowH = grownRow;
    contentH = layoutMode === 'single' ? headerH + n * rowH : headerH + half * rowH;
    fontSize = Math.max(IDF_MIN_FONT, Math.min(IDF_PREFERRED_FONT, fontSize));
  }

  const leftRows = layoutMode === 'two_up' && !needsHardSplit ? dataRows.slice(0, half) : [];
  const rightRows = layoutMode === 'two_up' && !needsHardSplit ? dataRows.slice(half) : [];
  const portLeft = half ? `1–${half}` : '';
  const portRight = n > half ? `${half + 1}–${n}` : '';

  return {
    id: blockId,
    type: 'idfNetworkTable',
    sourceWorksheetId: ws.id,
    sourceSheet: ws.sourceSheet || ws.name,
    sourceRange: ws.sourceRange || '',
    renderMode: 'excel_exact',
    layoutMode: needsHardSplit ? 'single' : layoutMode,
    sectionTitle,
    headers,
    rows: layoutMode === 'single' || needsHardSplit ? dataRows : [],
    leftRows,
    rightRows,
    portRangeLeft: needsHardSplit ? '' : portLeft,
    portRangeRight: needsHardSplit ? '' : portRight,
    colWidths,
    rowHeight: rowH,
    headerHeight: headerH,
    fontSize: needsHardSplit ? IDF_TARGET_FONT : fontSize,
    contentWidth: layoutMode === 'single' || needsHardSplit ? singleW : Math.min(usableW, singleW * 2 + 18),
    contentHeight: contentH,
    sourceRowCount: n,
    bodyRowFillMode: 'none',
    gridLines: true,
    styleRole: 'network-two-up',
    splitMode: 'none',
    allowContinuation: false,
    minScale: 1.0,
    scaleMode: 'fit_body',
    orientation: 'landscape',
    editable: false,
    layoutWarnings: [],
    scaledUp: rowH > IDF_ROW_H,
  };
}
