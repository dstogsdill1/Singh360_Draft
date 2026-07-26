import type { IWorkbookData, IWorksheetData } from '@univerjs/core';
import { LocaleType } from '@univerjs/core';
import type { WorkbookDocument } from '../api/client';

function columnIndex(letters: string): number {
  let value = 0;
  for (const char of letters.toUpperCase()) value = value * 26 + char.charCodeAt(0) - 64;
  return value - 1;
}

function parseCoordinate(value: string): [number, number] {
  const match = /^([A-Z]+)(\d+)$/i.exec(value);
  return match ? [Number(match[2]) - 1, columnIndex(match[1])] : [0, 0];
}

function parseRange(value: string) {
  const [start, end = start] = value.split(':');
  const [startRow, startColumn] = parseCoordinate(start);
  const [endRow, endColumn] = parseCoordinate(end);
  return { startRow, startColumn, endRow, endColumn };
}

function letters(index: number): string {
  let current = index + 1;
  let output = '';
  while (current) {
    current -= 1;
    output = String.fromCharCode(65 + current % 26) + output;
    current = Math.floor(current / 26);
  }
  return output;
}

export function toUniverWorkbook(document: WorkbookDocument, projectName: string, projectId: string): IWorkbookData {
  const sheets: Record<string, Partial<IWorksheetData>> = {};
  for (const sheet of document.sheets) {
    const cellData: Record<number, Record<number, Record<string, unknown>>> = {};
    for (const [coordinate, value] of Object.entries(sheet.cells)) {
      const [row, column] = parseCoordinate(coordinate);
      cellData[row] ||= {};
      cellData[row][column] = value;
    }
    const rowData: Record<number, { h: number }> = {};
    Object.entries(sheet.rowHeights).forEach(([row, height]) => { rowData[Number(row) - 1] = { h: height }; });
    const columnData: Record<number, { w: number }> = {};
    Object.entries(sheet.columnWidths).forEach(([column, width]) => { columnData[columnIndex(column)] = { w: width * 7 }; });
    sheets[sheet.id] = {
      id: sheet.id, name: sheet.name, hidden: sheet.archived ? 1 : 0,
      rowCount: Math.max(200, ...Object.keys(cellData).map(Number).map((value) => value + 20)),
      columnCount: 50, cellData, rowData, columnData,
      mergeData: sheet.merges.map(parseRange), showGridlines: 1,
    };
  }
  return {
    id: `workbook-${projectId}`, name: projectName, appVersion: '0.10.10',
    locale: LocaleType.EN_US, styles: {}, sheetOrder: document.sheets.map((sheet) => sheet.id), sheets,
  };
}

export function fromUniverWorkbook(snapshot: IWorkbookData, previous: WorkbookDocument): WorkbookDocument {
  const sheets = snapshot.sheetOrder.map((id) => {
    const sheet = snapshot.sheets[id] || {};
    const cells: Record<string, { v?: unknown; f?: string }> = {};
    const styles: Record<string, Record<string, unknown>> = {};
    Object.entries(sheet.cellData || {}).forEach(([row, columns]) => Object.entries(columns || {}).forEach(([column, rawCell]) => {
      const cell = rawCell as { f?: string; v?: string | number | boolean | null; s?: string | Record<string, unknown> };
      const coordinate = `${letters(Number(column))}${Number(row) + 1}`;
      cells[coordinate] = { ...(cell.f ? { f: cell.f } : {}), ...(cell.v !== undefined ? { v: cell.v } : {}) };
      const style = typeof cell.s === 'string' ? snapshot.styles[cell.s] : cell.s;
      if (style && typeof style === 'object') styles[coordinate] = style as Record<string, unknown>;
    }));
    const rowHeights: Record<string, number> = {};
    Object.entries(sheet.rowData || {}).forEach(([row, data]) => { if (data?.h) rowHeights[String(Number(row) + 1)] = data.h; });
    const columnWidths: Record<string, number> = {};
    Object.entries(sheet.columnData || {}).forEach(([column, data]) => { if (data?.w) columnWidths[letters(Number(column))] = data.w / 7; });
    return {
      id, name: sheet.name || id, cells, styles,
      merges: (sheet.mergeData || []).map((range) => `${letters(range.startColumn)}${range.startRow + 1}:${letters(range.endColumn)}${range.endRow + 1}`),
      rowHeights, columnWidths, archived: Boolean(sheet.hidden),
    };
  });
  return { ...previous, sheets };
}
