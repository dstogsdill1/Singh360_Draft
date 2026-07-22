import type { SymbolMapperPattern } from '../api/client';
import type { PageBlock, PageModel } from './types';

export interface SymbolMapperCountPageRow {
  code: string;
  glyph?: string;
  label: string;
  paletteLabel: string;
  color: string;
  color2: string;
  pattern: SymbolMapperPattern;
  shape?: 'auto' | 'circle' | 'square' | 'none';
  found: number;
  included: number;
  check: number;
  ignored: number;
}

export interface SymbolMapperCountPageRequest {
  enabled: boolean;
  sheetCode: string;
  pageTitle: string;
  rows: SymbolMapperCountPageRow[];
}

export interface SymbolMapperCountSummaryArtifacts {
  page: PageModel;
  totalIncluded: number;
  listedRows: number;
  legendSvg: string;
  legendDataUrl: string;
}

function xml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function clean(value: unknown, limit = 120): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit);
}

function validColor(value: string | undefined, fallback = '#808080'): string {
  return /^#[0-9a-f]{6}$/i.test(value ?? '') ? String(value).toUpperCase() : fallback;
}

function resolvedShape(row: SymbolMapperCountPageRow): 'circle' | 'square' | 'none' {
  if (row.shape === 'circle' || row.shape === 'square' || row.shape === 'none') return row.shape;
  return row.code.trim().toUpperCase() === 'CC' ? 'square' : 'circle';
}

function markerDefs(row: SymbolMapperCountPageRow, index: number): string {
  const c1 = validColor(row.color);
  const c2 = validColor(row.color2, c1);
  if (row.pattern === 'split-horizontal') {
    return `<linearGradient id="g${index}" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="${c1}"/><stop offset="50%" stop-color="${c1}"/><stop offset="50%" stop-color="${c2}"/><stop offset="100%" stop-color="${c2}"/></linearGradient>`;
  }
  if (row.pattern === 'diagonal') {
    return `<linearGradient id="g${index}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="${c1}"/><stop offset="49.5%" stop-color="${c1}"/><stop offset="50.5%" stop-color="${c2}"/><stop offset="100%" stop-color="${c2}"/></linearGradient>`;
  }
  if (row.pattern === 'crosshatch') {
    return `<pattern id="g${index}" width="10" height="10" patternUnits="userSpaceOnUse"><rect width="10" height="10" fill="${c1}" fill-opacity="0.24"/><path d="M-2 2 L2 -2 M0 10 L10 0 M8 12 L12 8" stroke="${c2}" stroke-width="2"/></pattern>`;
  }
  return `<linearGradient id="g${index}" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="${c1}"/><stop offset="50%" stop-color="${c1}"/><stop offset="50%" stop-color="${c2}"/><stop offset="100%" stop-color="${c2}"/></linearGradient>`;
}

function markerSvg(row: SymbolMapperCountPageRow, index: number, x: number, y: number, size: number): string {
  const shape = resolvedShape(row);
  const c1 = validColor(row.color);
  const c2 = validColor(row.color2, c1);
  const splitV = row.pattern === 'split-vertical';
  const splitH = row.pattern === 'split-horizontal';
  const diagonal = row.pattern === 'diagonal';
  const split = splitV || splitH || diagonal;
  const fill = row.pattern === 'outline' || row.pattern === 'double-outline'
    ? '#ffffff'
    : row.pattern === 'crosshatch'
      ? `url(#g${index})`
      : c1;
  const cx = x + size / 2;
  const cy = y + size / 2;
  const r = size / 2 - 2;
  const parts: string[] = [];
  const clipId = `clip${index}`;

  const splitFill = (rectX: number, rectY: number, rectW: number, rectH: number, clip = ''): string => {
    const clipAttr = clip ? ` clip-path="url(#${clip})"` : '';
    if (splitV) {
      return `<g${clipAttr}><rect x="${rectX}" y="${rectY}" width="${rectW / 2}" height="${rectH}" fill="${c1}"/><rect x="${rectX + rectW / 2}" y="${rectY}" width="${rectW / 2}" height="${rectH}" fill="${c2}"/></g>`;
    }
    if (splitH) {
      return `<g${clipAttr}><rect x="${rectX}" y="${rectY}" width="${rectW}" height="${rectH / 2}" fill="${c1}"/><rect x="${rectX}" y="${rectY + rectH / 2}" width="${rectW}" height="${rectH / 2}" fill="${c2}"/></g>`;
    }
    return `<g${clipAttr}><polygon points="${rectX},${rectY} ${rectX + rectW},${rectY} ${rectX},${rectY + rectH}" fill="${c1}"/><polygon points="${rectX + rectW},${rectY} ${rectX + rectW},${rectY + rectH} ${rectX},${rectY + rectH}" fill="${c2}"/></g>`;
  };

  if (shape === 'none') {
    parts.push(split ? splitFill(x, y, size, size) : `<rect x="${x}" y="${y}" width="${size}" height="${size}" rx="4" fill="${fill}"/>`);
  } else if (shape === 'square') {
    const sx = x + 2;
    const sy = y + 2;
    const sw = size - 4;
    const sh = size - 4;
    parts.push(split ? splitFill(sx, sy, sw, sh) : `<rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" rx="2" fill="${fill}"/>`);
    if (splitV) {
      const mid = x + size / 2;
      parts.push(`<path d="M ${mid} ${y + 2} H ${x + 2} V ${y + size - 2} H ${mid}" fill="none" stroke="${c1}" stroke-width="3"/>`);
      parts.push(`<path d="M ${mid} ${y + 2} H ${x + size - 2} V ${y + size - 2} H ${mid}" fill="none" stroke="${c2}" stroke-width="3"/>`);
      parts.push(`<line x1="${mid}" y1="${y + 3}" x2="${mid}" y2="${y + size - 3}" stroke="#ffffff" stroke-width="1.3"/>`);
    } else if (splitH) {
      const mid = y + size / 2;
      parts.push(`<path d="M ${x + 2} ${mid} V ${y + 2} H ${x + size - 2} V ${mid}" fill="none" stroke="${c1}" stroke-width="3"/>`);
      parts.push(`<path d="M ${x + 2} ${mid} V ${y + size - 2} H ${x + size - 2} V ${mid}" fill="none" stroke="${c2}" stroke-width="3"/>`);
    } else {
      parts.push(`<rect x="${sx}" y="${sy}" width="${sw}" height="${sh}" rx="2" fill="none" stroke="${c1}" stroke-width="3"/>`);
      if (row.pattern === 'double-outline') {
        parts.push(`<rect x="${x + 6}" y="${y + 6}" width="${size - 12}" height="${size - 12}" rx="1" fill="none" stroke="${c1}" stroke-width="1.5"/>`);
      }
    }
  } else {
    if (splitV) {
      parts.push(`<path d="M ${cx} ${cy - r} A ${r} ${r} 0 0 0 ${cx} ${cy + r} L ${cx} ${cy - r} Z" fill="${c1}"/>`);
      parts.push(`<path d="M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx} ${cy + r} L ${cx} ${cy - r} Z" fill="${c2}"/>`);
    } else if (splitH) {
      parts.push(`<path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy} L ${cx - r} ${cy} Z" fill="${c1}"/>`);
      parts.push(`<path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx + r} ${cy} L ${cx - r} ${cy} Z" fill="${c2}"/>`);
    } else if (diagonal) {
      parts.push(`<defs><clipPath id="${clipId}"><circle cx="${cx}" cy="${cy}" r="${r}"/></clipPath></defs>`);
      parts.push(splitFill(x + 2, y + 2, size - 4, size - 4, clipId));
    } else {
      parts.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}"/>`);
    }
    if (splitV) {
      parts.push(`<path d="M ${cx} ${cy - r} A ${r} ${r} 0 0 0 ${cx} ${cy + r}" fill="none" stroke="${c1}" stroke-width="3"/>`);
      parts.push(`<path d="M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx} ${cy + r}" fill="none" stroke="${c2}" stroke-width="3"/>`);
      parts.push(`<line x1="${cx}" y1="${cy - r + 1}" x2="${cx}" y2="${cy + r - 1}" stroke="#ffffff" stroke-width="1.3"/>`);
    } else if (splitH) {
      parts.push(`<path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}" fill="none" stroke="${c1}" stroke-width="3"/>`);
      parts.push(`<path d="M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx + r} ${cy}" fill="none" stroke="${c2}" stroke-width="3"/>`);
    } else {
      parts.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${c1}" stroke-width="3"/>`);
      if (row.pattern === 'double-outline') {
        parts.push(`<circle cx="${cx}" cy="${cy}" r="${Math.max(1, r - 4)}" fill="none" stroke="${c1}" stroke-width="1.5"/>`);
      }
    }
  }

  const glyph = clean(row.glyph || (/CLEAN SWITCH/i.test(row.label) ? '$' : row.code), 8);
  parts.push(`<text x="${cx}" y="${cy + size * 0.12}" text-anchor="middle" font-family="Arial, sans-serif" font-size="${size * 0.31}" font-weight="700" fill="#111111">${xml(glyph)}</text>`);
  return parts.join('');
}


export function buildSymbolCountLegendSvg(
  rowsInput: SymbolMapperCountPageRow[],
  titleInput: string,
  sourceNameInput: string,
): string {
  const rows = rowsInput.filter((row) => Number(row.included) > 0);
  const title = clean(titleInput || 'SYMBOL COUNT SUMMARY', 100);
  const sourceName = clean(sourceNameInput || 'Reviewed Symbol Mapper drawing', 140);
  const columns = rows.length <= 10 ? 1 : 2;
  const rowsPerColumn = Math.max(1, Math.ceil(rows.length / columns));
  const width = columns === 1 ? 760 : 1320;
  const pad = 24;
  const headerH = 82;
  const sourceH = 34;
  const rowH = 58;
  const footerH = 22;
  const height = headerH + sourceH + rowsPerColumn * rowH + footerH + pad;
  const gap = columns === 2 ? 20 : 0;
  const colW = (width - pad * 2 - gap) / columns;
  const total = rows.reduce((sum, row) => sum + Number(row.included || 0), 0);
  const defs = rows.map(markerDefs).join('');
  const svg: string[] = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<defs>${defs}<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.20"/></filter></defs>`,
    `<rect x="4" y="4" width="${width - 8}" height="${height - 8}" rx="10" fill="#ffffff" stroke="#38424d" stroke-width="2" filter="url(#shadow)"/>`,
    `<rect x="4" y="4" width="${width - 8}" height="${headerH}" rx="10" fill="#23272f"/>`,
    `<rect x="4" y="${headerH - 8}" width="${width - 8}" height="8" fill="#23272f"/>`,
    `<text x="${pad}" y="38" font-family="Arial, sans-serif" font-size="25" font-weight="800" fill="#ffffff">${xml(title)}</text>`,
    `<text x="${width - pad}" y="38" text-anchor="end" font-family="Arial, sans-serif" font-size="17" font-weight="700" fill="#ffffff">TOTAL ${total}</text>`,
    `<text x="${pad}" y="64" font-family="Arial, sans-serif" font-size="12" fill="#dbe2ea">Final reviewed Included counts only</text>`,
    `<rect x="${pad}" y="${headerH + 10}" width="${width - pad * 2}" height="${sourceH - 8}" rx="4" fill="#eef1f4"/>`,
    `<text x="${pad + 10}" y="${headerH + 30}" font-family="Arial, sans-serif" font-size="11" font-weight="700" fill="#3c4651">SOURCE</text>`,
    `<text x="${pad + 70}" y="${headerH + 30}" font-family="Arial, sans-serif" font-size="11" fill="#23272f">${xml(sourceName)}</text>`,
  ];

  if (!rows.length) {
    svg.push(`<text x="${width / 2}" y="${headerH + sourceH + 72}" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" fill="#555">No included symbols were confirmed.</text>`);
  }

  rows.forEach((row, index) => {
    const column = Math.floor(index / rowsPerColumn);
    const rowIndex = index % rowsPerColumn;
    const x = pad + column * (colW + gap);
    const y = headerH + sourceH + rowIndex * rowH + 8;
    svg.push(`<rect x="${x}" y="${y}" width="${colW}" height="${rowH - 6}" rx="5" fill="#ffffff" stroke="#c9d0d7" stroke-width="1"/>`);
    svg.push(markerSvg(row, index, x + 9, y + 7, 38));
    svg.push(`<text x="${x + 58}" y="${y + 21}" font-family="Arial, sans-serif" font-size="14" font-weight="800" fill="#111111">${xml(clean(row.code, 16))}</text>`);
    svg.push(`<text x="${x + 58}" y="${y + 40}" font-family="Arial, sans-serif" font-size="11" fill="#313942">${xml(clean(row.label, 120))}</text>`);
    const badgeW = 52;
    const bx = x + colW - badgeW - 10;
    svg.push(`<rect x="${bx}" y="${y + 8}" width="${badgeW}" height="${rowH - 22}" rx="16" fill="#23272f"/>`);
    svg.push(`<text x="${bx + badgeW / 2}" y="${y + 31}" text-anchor="middle" font-family="Arial, sans-serif" font-size="17" font-weight="800" fill="#ffffff">${Number(row.included)}</text>`);
  });

  svg.push(`<text x="${pad}" y="${height - 12}" font-family="Arial, sans-serif" font-size="10" fill="#66717d">Zero-count, ignored, and unresolved symbols are omitted.</text>`);
  svg.push('</svg>');
  return svg.join('');
}

export function symbolCountLegendDataUrl(rows: SymbolMapperCountPageRow[], title: string, sourceName: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(buildSymbolCountLegendSvg(rows, title, sourceName))}`;
}

export function buildSymbolCountSummaryArtifacts(
  request: SymbolMapperCountPageRequest,
  sourceName: string,
  pageId: string,
  _worksheetId: string,
): SymbolMapperCountSummaryArtifacts {
  const rows = request.rows.filter((row) => Number(row.included) > 0);
  const totalIncluded = rows.reduce((sum, row) => sum + Number(row.included || 0), 0);
  const title = request.pageTitle.trim() || 'SYMBOL COUNT SUMMARY';
  const code = request.sheetCode.trim() || 'NEW';
  const legendSvg = buildSymbolCountLegendSvg(rows, title, sourceName);
  const legendDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(legendSvg)}`;

  const legendBlock: PageBlock = {
    id: `${pageId}_symbol_count_legend`,
    type: 'imagePlaceholder',
    filename: 'symbol-count-legend.svg',
    text: 'Detected Symbol Counts',
    url: legendDataUrl,
    styleRole: 'symbol-count-legend',
    editable: false,
  };

  const page: PageModel = {
    id: pageId,
    order: 0,
    include: true,
    sheetCode: code,
    displaySheetCode: code,
    sheetTitle: title,
    sheetTab: title,
    pageType: 'data-grid',
    pageFamily: 'Image / Layout',
    layoutProfile: 'symbol_count_legend',
    renderMode: 'normalized',
    renderProfile: 'symbol_count_legend',
    normalizedHeaderStyle: 'none',
    template: 'Image / Layout',
    templateId: '',
    blocks: [legendBlock],
    canvasObjects: [],
    notes: `Final reviewed counts from ${sourceName || 'Symbol Mapper'}. Count equals Included; zero-count, ignored, and unresolved symbols are omitted.`,
    pageGroupId: pageId,
    continuationOf: null,
    continuationIndex: 0,
    generatedContinuation: false,
    splitMode: 'none',
    allowContinuation: false,
    minScale: 1,
    scaleMode: 'fit_body',
  };

  return { page, totalIncluded, listedRows: rows.length, legendSvg, legendDataUrl };
}
