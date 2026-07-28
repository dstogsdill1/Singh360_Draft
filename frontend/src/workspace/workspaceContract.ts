import type { IRange } from '@univerjs/core';
import type { WorkbookDocument } from '../api/client';
import { columnIndex, letters, parseCoordinate } from './UniverWorkbookAdapter';

export interface TableRegion {
  id: string;
  range: string;
  label: string;
}

export function rangeBounds(value: string): IRange | null {
  const raw = String(value || '').replace(/\$/g, '').split('!').pop() || '';
  const [start, end = start] = raw.split(':');
  if (!start || !end || !/^[A-Z]+\d+$/i.test(start) || !/^[A-Z]+\d+$/i.test(end)) return null;
  const [startRow, startColumn] = parseCoordinate(start);
  const [endRow, endColumn] = parseCoordinate(end);
  return {
    startRow: Math.min(startRow, endRow),
    startColumn: Math.min(startColumn, endColumn),
    endRow: Math.max(startRow, endRow),
    endColumn: Math.max(startColumn, endColumn),
  };
}

export function rangesOverlap(left: IRange, right: IRange): boolean {
  return !(
    left.endRow < right.startRow
    || right.endRow < left.startRow
    || left.endColumn < right.startColumn
    || right.endColumn < left.startColumn
  );
}

export function protectedOverlap(
  target: IRange,
  protectedRanges: string[],
): string | null {
  return protectedRanges.find((value) => {
    const protectedRange = rangeBounds(value);
    return protectedRange ? rangesOverlap(target, protectedRange) : false;
  }) || null;
}

export function pasteTargetRange(selection: IRange, text = ''): IRange {
  const rows = String(text || '').replace(/\r/g, '').split('\n');
  if (rows.length > 1 && rows[rows.length - 1] === '') rows.pop();
  const height = Math.max(1, rows.length);
  const width = Math.max(1, ...rows.map((row) => row.split('\t').length));
  return {
    startRow: selection.startRow,
    startColumn: selection.startColumn,
    endRow: selection.startRow + height - 1,
    endColumn: selection.startColumn + width - 1,
  };
}

function cellHasData(cell: { v?: unknown; f?: string } | undefined): boolean {
  return Boolean(cell && (cell.v !== undefined && cell.v !== null && cell.v !== '' || cell.f));
}

function segments(values: Set<number>, first: number, last: number): Array<[number, number]> {
  const result: Array<[number, number]> = [];
  let start: number | null = null;
  for (let value = first; value <= last; value += 1) {
    if (values.has(value) && start === null) start = value;
    if (!values.has(value) && start !== null) {
      result.push([start, value - 1]);
      start = null;
    }
  }
  if (start !== null) result.push([start, last]);
  return result;
}

/**
 * Detect tables separated by at least one wholly blank row or column. Formatting
 * inside a table is preserved because the returned regions reference the exact
 * original source range rather than copying or normalizing cells.
 */
export function detectTableRegions(
  sheet: WorkbookDocument['sheets'][number],
  startRow = 3,
): TableRegion[] {
  const occupied = Object.entries(sheet.cells)
    .filter(([coordinate, cell]) => parseCoordinate(coordinate)[0] + 1 >= startRow && cellHasData(cell))
    .map(([coordinate]) => {
      const [row, column] = parseCoordinate(coordinate);
      return { row, column };
    });
  if (!occupied.length) return [];
  const rowSet = new Set(occupied.map((item) => item.row));
  const columnSet = new Set(occupied.map((item) => item.column));
  const rowSegments = segments(rowSet, Math.min(...rowSet), Math.max(...rowSet));
  const columnSegments = segments(columnSet, Math.min(...columnSet), Math.max(...columnSet));
  const regions: TableRegion[] = [];
  rowSegments.forEach(([rowStart, rowEnd]) => {
    columnSegments.forEach(([columnStart, columnEnd]) => {
      const island = occupied.filter((item) =>
        item.row >= rowStart && item.row <= rowEnd
        && item.column >= columnStart && item.column <= columnEnd);
      if (!island.length) return;
      const firstRow = Math.min(...island.map((item) => item.row));
      const lastRow = Math.max(...island.map((item) => item.row));
      const firstColumn = Math.min(...island.map((item) => item.column));
      const lastColumn = Math.max(...island.map((item) => item.column));
      const index = regions.length + 1;
      regions.push({
        id: `table-${index}`,
        label: `Table ${index}`,
        range: `${letters(firstColumn)}${firstRow + 1}:${letters(lastColumn)}${lastRow + 1}`,
      });
    });
  });
  return regions;
}

export function activeRangeA1(range: IRange): string {
  return `${letters(range.startColumn)}${range.startRow + 1}:${letters(range.endColumn)}${range.endRow + 1}`;
}

export function columnRange(column: string, firstRow: number, lastRow: number): IRange {
  const index = columnIndex(column);
  return { startRow: firstRow - 1, endRow: lastRow - 1, startColumn: index, endColumn: index };
}
