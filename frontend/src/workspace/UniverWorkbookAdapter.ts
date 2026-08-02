import type { IStyleData, IWorkbookData, IWorksheetData } from '@univerjs/core';
import { LocaleType } from '@univerjs/core';
import type { WorkbookDocument } from '../api/client';
import {
  DEFAULT_COLUMN_WIDTH_UNITS,
  DEFAULT_ROW_HEIGHT_POINTS,
  excelColumnWidthToPixels,
  rowHeightPointsToPixels,
  unchangedExcelWidthOrConverted,
  unchangedRowHeightOrConverted,
} from '../model/workbookGeometry';

export function columnIndex(letters: string): number {
  let value = 0;
  for (const char of letters.toUpperCase()) value = value * 26 + char.charCodeAt(0) - 64;
  return value - 1;
}

export function parseCoordinate(value: string): [number, number] {
  const match = /^([A-Z]+)(\d+)$/i.exec(value);
  return match ? [Number(match[2]) - 1, columnIndex(match[1])] : [0, 0];
}

function parseRange(value: string) {
  const [start, end = start] = value.split(':');
  const [startRow, startColumn] = parseCoordinate(start);
  const [endRow, endColumn] = parseCoordinate(end);
  return { startRow, startColumn, endRow, endColumn };
}

export function letters(index: number): string {
  let current = index + 1;
  let output = '';
  while (current) {
    current -= 1;
    output = String.fromCharCode(65 + current % 26) + output;
    current = Math.floor(current / 26);
  }
  return output;
}

const horizontalToUniver: Record<string, number> = {
  left: 1,
  center: 2,
  right: 3,
  justify: 4,
  both: 5,
  distributed: 6,
};
const horizontalFromUniver: Record<number, string> = {
  1: 'left',
  2: 'center',
  3: 'right',
  4: 'justify',
  5: 'both',
  6: 'distributed',
};
const verticalToUniver: Record<string, number> = { top: 1, center: 2, middle: 2, bottom: 3 };
const verticalFromUniver: Record<number, string> = { 1: 'top', 2: 'center', 3: 'bottom' };
const borderToUniver: Record<string, number> = {
  thin: 1,
  hair: 2,
  dotted: 3,
  dashed: 4,
  dashDot: 5,
  dashDotDot: 6,
  double: 7,
  medium: 8,
  mediumDashed: 9,
  mediumDashDot: 10,
  mediumDashDotDot: 11,
  slantDashDot: 12,
  thick: 13,
};
const borderFromUniver = Object.fromEntries(
  Object.entries(borderToUniver).map(([key, value]) => [value, key]),
) as Record<number, string>;

function color(value: unknown): string | undefined {
  if (typeof value === 'string') return value.replace(/^#/, '').toUpperCase();
  if (value && typeof value === 'object') {
    const rgb = (value as { rgb?: unknown }).rgb;
    if (typeof rgb === 'string') return rgb.replace(/^#/, '').toUpperCase();
  }
  return undefined;
}

function univerColor(value: unknown, fallback?: string): { rgb: string } | undefined {
  const resolved = color(value) || fallback;
  return resolved ? { rgb: `#${resolved}` } : undefined;
}

function toUniverBorder(raw: unknown): { s: number; cl: { rgb: string } } | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const border = raw as { style?: unknown; color?: unknown };
  const style = borderToUniver[String(border.style || '')];
  if (!style) return undefined;
  return { s: style, cl: univerColor(border.color, '000000')! };
}

function toUniverStyle(raw: Record<string, unknown>): IStyleData {
  if (
    'bl' in raw || 'it' in raw || 'ff' in raw || 'fs' in raw || 'bg' in raw
    || 'ht' in raw || 'vt' in raw || 'tb' in raw || 'bd' in raw
  ) {
    return raw as IStyleData;
  }
  const style: IStyleData = {};
  if ('bold' in raw) style.bl = raw.bold ? 1 : 0;
  if ('italic' in raw) style.it = raw.italic ? 1 : 0;
  if (raw.underline) style.ul = { s: 1 };
  if (raw.fontName) style.ff = String(raw.fontName);
  if (Number(raw.fontSize) > 0) style.fs = Number(raw.fontSize);
  const fontColor = univerColor(raw.fontColor);
  if (fontColor) style.cl = fontColor;
  const fill = univerColor(raw.fill);
  if (fill) style.bg = fill;
  if (raw.hAlign) style.ht = horizontalToUniver[String(raw.hAlign)] ?? 0;
  if (raw.vAlign) style.vt = verticalToUniver[String(raw.vAlign)] ?? 0;
  if ('wrap' in raw) style.tb = raw.wrap ? 3 : 2;
  if (Number.isFinite(Number(raw.rotation))) style.tr = { a: Number(raw.rotation) };
  if (Number(raw.indent) > 0) style.pd = { l: Number(raw.indent) * 8 };
  if (raw.borders && typeof raw.borders === 'object') {
    const source = raw.borders as Record<string, unknown>;
    const bd = {
      t: toUniverBorder(source.top),
      r: toUniverBorder(source.right),
      b: toUniverBorder(source.bottom),
      l: toUniverBorder(source.left),
    };
    if (bd.t || bd.r || bd.b || bd.l) style.bd = bd;
  }
  return style;
}

function fromUniverBorder(raw: unknown): Record<string, unknown> | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const border = raw as { s?: unknown; cl?: unknown };
  const style = borderFromUniver[Number(border.s)];
  if (!style) return undefined;
  return { style, color: `#${color(border.cl) || '000000'}` };
}

function fromUniverStyle(raw: Record<string, unknown>): Record<string, unknown> {
  if (
    'bold' in raw || 'italic' in raw || 'fontName' in raw || 'fontSize' in raw
    || 'fill' in raw || 'hAlign' in raw || 'vAlign' in raw || 'wrap' in raw
  ) {
    return { ...raw };
  }
  const style: Record<string, unknown> = {};
  if ('bl' in raw) style.bold = Boolean(raw.bl);
  if ('it' in raw) style.italic = Boolean(raw.it);
  if (raw.ul && typeof raw.ul === 'object') style.underline = Boolean((raw.ul as { s?: unknown }).s);
  if (raw.ff) style.fontName = String(raw.ff);
  if (Number(raw.fs) > 0) style.fontSize = Number(raw.fs);
  const fontColor = color(raw.cl);
  if (fontColor) style.fontColor = `#${fontColor}`;
  const fill = color(raw.bg);
  if (fill) style.fill = `#${fill}`;
  if (Number(raw.ht) in horizontalFromUniver) style.hAlign = horizontalFromUniver[Number(raw.ht)];
  if (Number(raw.vt) in verticalFromUniver) style.vAlign = verticalFromUniver[Number(raw.vt)];
  if ('tb' in raw) style.wrap = Number(raw.tb) === 3;
  if (raw.tr && typeof raw.tr === 'object') style.rotation = Number((raw.tr as { a?: unknown }).a) || 0;
  if (raw.pd && typeof raw.pd === 'object' && Number((raw.pd as { l?: unknown }).l) > 0) {
    style.indent = Math.round(Number((raw.pd as { l?: unknown }).l) / 8);
  }
  if (raw.bd && typeof raw.bd === 'object') {
    const bd = raw.bd as Record<string, unknown>;
    const borders = {
      top: fromUniverBorder(bd.t),
      right: fromUniverBorder(bd.r),
      bottom: fromUniverBorder(bd.b),
      left: fromUniverBorder(bd.l),
    };
    if (borders.top || borders.right || borders.bottom || borders.left) {
      style.borders = borders;
    }
  }
  return style;
}

function maxCoordinate(
  values: Iterable<string>,
  index: 0 | 1,
  minimum: number,
): number {
  let max = minimum;
  for (const value of values) max = Math.max(max, parseCoordinate(value)[index] + 1);
  return max;
}

export function toUniverWorkbook(
  document: WorkbookDocument,
  projectName: string,
  projectId: string,
): IWorkbookData {
  const sheets: Record<string, Partial<IWorksheetData>> = {};
  for (const sheet of document.sheets) {
    const cellData: Record<number, Record<number, Record<string, unknown>>> = {};
    const coordinates = new Set([...Object.keys(sheet.cells), ...Object.keys(sheet.styles)]);
    for (const coordinate of coordinates) {
      const [row, column] = parseCoordinate(coordinate);
      cellData[row] ||= {};
      const value = sheet.cells[coordinate] || {};
      const style = sheet.styles[coordinate];
      cellData[row][column] = {
        ...value,
        ...(style ? { s: toUniverStyle(style) } : {}),
      };
    }
    const rowData: Record<number, { h?: number; hd?: number }> = {};
    Object.entries(sheet.rowHeights).forEach(([row, height]) => {
      rowData[Number(row) - 1] = { h: rowHeightPointsToPixels(height) };
    });
    sheet.hiddenRows.forEach((row) => {
      rowData[row - 1] = { ...(rowData[row - 1] || {}), hd: 1 };
    });
    const columnData: Record<number, { w?: number; hd?: number }> = {};
    Object.entries(sheet.columnWidths).forEach(([column, width]) => {
      columnData[columnIndex(column)] = { w: excelColumnWidthToPixels(width) };
    });
    sheet.hiddenColumns.forEach((column) => {
      const index = columnIndex(column);
      columnData[index] = { ...(columnData[index] || {}), hd: 1 };
    });
    const rowCount = Math.max(
      200,
      maxCoordinate(coordinates, 0, 0) + 20,
      ...Object.keys(rowData).map((value) => Number(value) + 1),
    );
    const columnCount = Math.max(
      50,
      maxCoordinate(coordinates, 1, 0) + 10,
      ...Object.keys(columnData).map((value) => Number(value) + 1),
    );
    sheets[sheet.id] = {
      id: sheet.id,
      name: sheet.name,
      hidden: sheet.archived ? 1 : 0,
      tabColor: sheet.tabColor || undefined,
      rowCount,
      columnCount,
      defaultColumnWidth: excelColumnWidthToPixels(
        sheet.defaultColumnWidth || DEFAULT_COLUMN_WIDTH_UNITS,
      ),
      defaultRowHeight: rowHeightPointsToPixels(
        sheet.defaultRowHeight || DEFAULT_ROW_HEIGHT_POINTS,
      ),
      cellData,
      rowData,
      columnData,
      mergeData: sheet.merges.map(parseRange),
      showGridlines: 1,
      custom: {
        role: sheet.role,
        sourceSetup: sheet.sourceSetup,
        protectedRanges: sheet.protectedRanges,
        tableRegions: sheet.tableRegions,
        tableLayout: sheet.tableLayout,
        annotations: sheet.annotations,
        pageLayouts: sheet.pageLayouts,
      },
    } as Partial<IWorksheetData>;
  }
  return {
    id: `workbook-${projectId}`,
    name: projectName,
    appVersion: '0.10.14',
    locale: LocaleType.EN_US,
    styles: {},
    sheetOrder: document.sheets.map((sheet) => sheet.id),
    sheets,
  };
}

export function fromUniverWorkbook(
  snapshot: IWorkbookData,
  previous: WorkbookDocument,
): WorkbookDocument {
  const sheets = snapshot.sheetOrder.map((id) => {
    const sheet = snapshot.sheets[id] || {};
    const prior = previous.sheets.find((item) => item.id === id);
    const cells: Record<string, { v?: unknown; f?: string }> = {};
    const styles: Record<string, Record<string, unknown>> = {};
    Object.entries(sheet.cellData || {}).forEach(([row, columns]) => {
      Object.entries(columns || {}).forEach(([column, rawCell]) => {
        const cell = rawCell as {
          f?: string;
          v?: string | number | boolean | null;
          s?: string | Record<string, unknown> | null;
        };
        const coordinate = `${letters(Number(column))}${Number(row) + 1}`;
        if (cell.f || cell.v !== undefined) {
          cells[coordinate] = {
            ...(cell.f ? { f: cell.f } : {}),
            ...(cell.v !== undefined ? { v: cell.v } : {}),
          };
        }
        const style = typeof cell.s === 'string'
          ? snapshot.styles[cell.s]
          : cell.s;
        if (style && typeof style === 'object') {
          styles[coordinate] = {
            ...fromUniverStyle(style as Record<string, unknown>),
            ...(prior?.styles[coordinate]?.numberFormat
              ? { numberFormat: prior.styles[coordinate].numberFormat }
              : {}),
          };
        } else if (cell.s === undefined && prior?.styles[coordinate]) {
          styles[coordinate] = prior.styles[coordinate];
        }
      });
    });
    const rowHeights: Record<string, number> = {};
    const hiddenRows: number[] = [];
    Object.entries(sheet.rowData || {}).forEach(([row, data]) => {
      const rowNumber = Number(row) + 1;
      if (Number(data?.h) > 0) {
        rowHeights[String(rowNumber)] = unchangedRowHeightOrConverted(
          data?.h,
          prior?.rowHeights[String(rowNumber)],
        );
      }
      if (data?.hd) hiddenRows.push(rowNumber);
    });
    const columnWidths: Record<string, number> = {};
    const hiddenColumns: string[] = [];
    Object.entries(sheet.columnData || {}).forEach(([column, data]) => {
      const columnLetter = letters(Number(column));
      if (Number(data?.w) > 0) {
        columnWidths[columnLetter] = unchangedExcelWidthOrConverted(
          data?.w,
          prior?.columnWidths[columnLetter],
        );
      }
      if (data?.hd) hiddenColumns.push(columnLetter);
    });
    return {
      id,
      name: sheet.name || id,
      cells,
      styles,
      merges: (sheet.mergeData || []).map((range) =>
        `${letters(range.startColumn)}${range.startRow + 1}:`
        + `${letters(range.endColumn)}${range.endRow + 1}`),
      rowHeights,
      columnWidths,
      defaultColumnWidth: unchangedExcelWidthOrConverted(
        sheet.defaultColumnWidth,
        prior?.defaultColumnWidth,
      ),
      defaultRowHeight: unchangedRowHeightOrConverted(
        sheet.defaultRowHeight,
        prior?.defaultRowHeight,
      ),
      hiddenRows: hiddenRows.sort((a, b) => a - b),
      hiddenColumns: hiddenColumns.sort((a, b) => columnIndex(a) - columnIndex(b)),
      archived: Boolean(sheet.hidden),
      tabColor: (sheet as { tabColor?: string }).tabColor || prior?.tabColor,
      role: prior?.role || (
        sheet.custom && typeof sheet.custom === 'object'
          ? String((sheet.custom as Record<string, unknown>).role || '') || null
          : null
      ),
      sourceSetup: prior?.sourceSetup || {},
      protectedRanges: [...(prior?.protectedRanges || [])],
      dataValidations: [...(prior?.dataValidations || [])],
      conditionalFormats: [...(prior?.conditionalFormats || [])],
      tableRegions: [...(prior?.tableRegions || [])],
      tableLayout: prior?.tableLayout || 'single',
      annotations: [...(prior?.annotations || [])],
      pageLayouts: structuredClone(prior?.pageLayouts || []),
    };
  });
  return { ...previous, sheets };
}
