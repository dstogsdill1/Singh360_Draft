import type { SymbolMapperPattern } from '../api/client';
import { rebuildSinglePageFromSource } from './pageRebuild';
import type { ExcelCellStyle, PageModel, Worksheet } from './types';

export interface SymbolMapperCountPageRow {
  code: string;
  label: string;
  paletteLabel: string;
  color: string;
  color2: string;
  pattern: SymbolMapperPattern;
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
  worksheet: Worksheet;
  page: PageModel;
  totalIncluded: number;
  listedRows: number;
}

const THIN_BORDER = {
  top: { style: 'thin', color: '#777777' },
  right: { style: 'thin', color: '#777777' },
  bottom: { style: 'thin', color: '#777777' },
  left: { style: 'thin', color: '#777777' },
};

function textColorFor(fill: string): string {
  const hex = fill.replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(hex)) return '#111111';
  const r = Number.parseInt(hex.slice(0, 2), 16);
  const g = Number.parseInt(hex.slice(2, 4), 16);
  const b = Number.parseInt(hex.slice(4, 6), 16);
  return (r * 299 + g * 587 + b * 114) / 1000 < 145 ? '#ffffff' : '#111111';
}

function style(fill: string, opts: Partial<ExcelCellStyle> = {}): ExcelCellStyle {
  return {
    fontName: 'Arial',
    fontSize: 11,
    fontColor: '#111111',
    vAlign: 'middle',
    borders: THIN_BORDER,
    fill,
    ...opts,
  };
}

export function buildSymbolCountSummaryArtifacts(
  request: SymbolMapperCountPageRequest,
  sourceName: string,
  pageId: string,
  worksheetId: string,
): SymbolMapperCountSummaryArtifacts {
  const rows = request.rows.filter((row) => Number(row.included) > 0);
  const totalIncluded = rows.reduce((sum, row) => sum + Number(row.included || 0), 0);
  const title = request.pageTitle.trim() || 'SYMBOL COUNT SUMMARY';
  const code = request.sheetCode.trim() || 'NEW';

  const grid: string[][] = [
    [title, '', '', ''],
    ['SOURCE DRAWING', sourceName || 'Reviewed Symbol Mapper page', 'TOTAL INCLUDED', String(totalIncluded)],
    ['', '', '', ''],
    ['SYMBOL', 'DESCRIPTION', 'COLOR', 'COUNT'],
  ];
  if (rows.length) {
    rows.forEach((row) => grid.push([
      row.code || '—',
      row.label || 'Unnamed symbol',
      row.paletteLabel || row.color,
      String(row.included),
    ]));
  } else {
    grid.push(['—', 'No included symbols were confirmed.', '', '0']);
  }

  const styles: Record<string, ExcelCellStyle> = {};
  styles.A1 = style('#23272f', { bold: true, fontSize: 18, fontColor: '#ffffff', hAlign: 'center' });
  styles.A2 = style('#eef1f4', { bold: true, fontSize: 9, fontColor: '#444444' });
  styles.B2 = style('#eef1f4', { fontSize: 10, fontColor: '#222222' });
  styles.C2 = style('#eef1f4', { bold: true, fontSize: 9, fontColor: '#444444', hAlign: 'right' });
  styles.D2 = style('#eef1f4', { bold: true, fontSize: 14, hAlign: 'center' });
  for (const column of ['A', 'B', 'C', 'D']) {
    styles[`${column}4`] = style('#f28c28', { bold: true, fontColor: '#ffffff', hAlign: column === 'B' ? 'left' : 'center' });
  }

  rows.forEach((row, index) => {
    const excelRow = index + 5;
    const zebra = index % 2 ? '#f4f5f6' : '#ffffff';
    styles[`A${excelRow}`] = style(row.color || '#ffffff', {
      bold: true,
      fontColor: textColorFor(row.color || '#ffffff'),
      hAlign: 'center',
    });
    styles[`B${excelRow}`] = style(zebra, { wrap: true });
    styles[`C${excelRow}`] = style(zebra, { hAlign: 'center' });
    styles[`D${excelRow}`] = style(zebra, { bold: true, fontSize: 14, hAlign: 'center' });
  });
  if (!rows.length) {
    for (const column of ['A', 'B', 'C', 'D']) {
      styles[`${column}5`] = style('#ffffff', { hAlign: column === 'B' ? 'left' : 'center' });
    }
  }

  const worksheet: Worksheet = {
    id: worksheetId,
    name: title,
    grid,
    styles,
    mergedCells: [{ startRow: 0, startCol: 0, endRow: 0, endCol: 3 }],
    rowHeights: {},
    columnWidths: {},
    colWidthsPx: [150, 790, 280, 120],
    rowHeightsPx: [46, 30, 12, 30, ...Array.from({ length: Math.max(1, rows.length) }, () => 32)],
    sourceSheet: title,
    sourceRange: `A1:D${grid.length}`,
    printArea: `A1:D${grid.length}`,
  };

  const basePage: PageModel = {
    id: pageId,
    order: 0,
    include: true,
    sheetCode: code,
    displaySheetCode: code,
    sheetTitle: title,
    sheetTab: title,
    pageType: 'data-grid',
    pageFamily: 'table',
    layoutProfile: 'symbol_count_summary',
    renderMode: 'excel_exact',
    renderProfile: 'symbol_count_summary',
    normalizedHeaderStyle: 'orange',
    template: 'Table / Schedule',
    templateId: '',
    linkedWorksheetId: worksheetId,
    blocks: [],
    canvasObjects: [],
    notes: `Final reviewed counts from ${sourceName || 'Symbol Mapper'}. Count equals Included; zero-count and ignored symbols are omitted.`,
    pageGroupId: pageId,
    continuationOf: null,
    continuationIndex: 0,
    generatedContinuation: false,
    splitMode: 'none',
    allowContinuation: false,
    minScale: 0.8,
    scaleMode: 'fit_body',
  };

  const page = rebuildSinglePageFromSource(basePage, worksheet);
  return { worksheet, page, totalIncluded, listedRows: rows.length };
}
