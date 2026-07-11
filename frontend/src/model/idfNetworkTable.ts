// Client mirror of core/workbook_importer.py RDM/IDF network table builder.
// Used when rebuilding network_48_port pages from source — never raw excelRange.

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
  return String(h ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
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

/** First row that looks like a Port/Label or Port/Controller-ID network header. */
export function idfHeaderRow(grid: string[][]): number | null {
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

/** Build the special RDM/IDF network table block (two-up 48-port by default). */
export function buildIdfNetworkBlock(
  ws: Worksheet,
  headerRow: number,
  blockId: string,
  opts?: { showTerminatedBy?: boolean },
): PageBlock {
  const showTerminatedBy = opts?.showTerminatedBy ?? false;
  const grid = ws.grid ?? [];
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
