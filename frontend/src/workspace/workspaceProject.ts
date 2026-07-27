import type { WorkbookDocument } from '../api/client';
import {
  applyCoverSourceTruth,
  refreshPageFromSource,
  regenerateExcelGroup,
} from '../model/excelRange';
import {
  DEFAULT_COLUMN_WIDTH_UNITS,
  DEFAULT_ROW_HEIGHT_POINTS,
  excelColumnWidthToPixels,
  rowHeightPointsToPixels,
} from '../model/workbookGeometry';
import type { MergedCell, ProjectModel, Worksheet } from '../model/types';
import { columnIndex, letters, parseCoordinate } from './UniverWorkbookAdapter';

function parseMerge(value: string): MergedCell | null {
  const [start, end = start] = value.split(':');
  if (!start || !end) return null;
  const [startRow, startCol] = parseCoordinate(start);
  const [endRow, endCol] = parseCoordinate(end);
  return { startRow, startCol, endRow, endCol };
}

function sheetToWorksheet(
  sheet: WorkbookDocument['sheets'][number],
  previous?: Worksheet,
): Worksheet {
  const merges = sheet.merges.map(parseMerge).filter((item): item is MergedCell => Boolean(item));
  let rowCount = 1;
  let columnCount = 1;
  const coordinates = new Set([...Object.keys(sheet.cells), ...Object.keys(sheet.styles)]);
  coordinates.forEach((coordinate) => {
    const [row, column] = parseCoordinate(coordinate);
    rowCount = Math.max(rowCount, row + 1);
    columnCount = Math.max(columnCount, column + 1);
  });
  Object.keys(sheet.rowHeights).forEach((row) => { rowCount = Math.max(rowCount, Number(row)); });
  Object.keys(sheet.columnWidths).forEach((column) => {
    columnCount = Math.max(columnCount, columnIndex(column) + 1);
  });
  merges.forEach((merge) => {
    rowCount = Math.max(rowCount, merge.endRow + 1);
    columnCount = Math.max(columnCount, merge.endCol + 1);
  });

  const grid = Array.from({ length: rowCount }, () =>
    Array.from({ length: columnCount }, () => ''),
  );
  const formulas: Record<string, string> = {};
  Object.entries(sheet.cells).forEach(([coordinate, cell]) => {
    const [row, column] = parseCoordinate(coordinate);
    if (cell.f) formulas[coordinate] = cell.f;
    const previousValue = previous?.grid?.[row]?.[column];
    grid[row][column] = String(cell.v ?? previousValue ?? '');
  });

  const defaultColumnWidth = sheet.defaultColumnWidth || DEFAULT_COLUMN_WIDTH_UNITS;
  const defaultRowHeight = sheet.defaultRowHeight || DEFAULT_ROW_HEIGHT_POINTS;
  const colWidthsPx = Array.from({ length: columnCount }, (_, column) =>
    excelColumnWidthToPixels(
      sheet.columnWidths[letters(column)] ?? defaultColumnWidth,
    ),
  );
  const rowHeightsPx = Array.from({ length: rowCount }, (_, row) =>
    rowHeightPointsToPixels(
      sheet.rowHeights[String(row + 1)] ?? defaultRowHeight,
    ),
  );

  return {
    ...(previous || {}),
    id: sheet.id,
    name: sheet.name,
    sourceSheet: previous?.sourceSheet || sheet.name,
    grid,
    formulas,
    styles: { ...sheet.styles },
    mergedCells: merges,
    rowHeights: { ...sheet.rowHeights },
    columnWidths: { ...sheet.columnWidths },
    defaultColumnWidth,
    defaultRowHeight,
    geometryAuthority: 'workbook-v1',
    colWidthsPx,
    rowHeightsPx,
    hiddenRows: sheet.hiddenRows.map((row) => row - 1),
    hiddenColumns: sheet.hiddenColumns.map(columnIndex),
    visible: !sheet.archived,
    tabColor: sheet.tabColor,
  } as Worksheet;
}

/**
 * Apply the project-local workbook mirror to app worksheets and regenerate only
 * source-linked drawing blocks/pages. Manual pages and every page/canvas field
 * outside the generated block payload remain untouched.
 */
export function updateProjectDrawingsFromWorkbook(
  project: ProjectModel,
  document: WorkbookDocument,
): ProjectModel {
  const previousById = new Map(project.worksheets.map((worksheet) => [worksheet.id, worksheet]));
  const updated = document.sheets.map((sheet) =>
    sheetToWorksheet(sheet, previousById.get(sheet.id)),
  );
  const updatedIds = new Set(updated.map((worksheet) => worksheet.id));
  const worksheets = [
    ...updated,
    ...project.worksheets.filter((worksheet) => !updatedIds.has(worksheet.id)),
  ];
  let next: ProjectModel = { ...project, worksheets };

  for (const worksheet of updated) {
    const linkedPages = next.pages.filter((page) => page.linkedWorksheetId === worksheet.id);
    if (!linkedPages.length) continue;
    if (linkedPages.some((page) => page.renderMode === 'excel_exact')) {
      next = { ...next, pages: regenerateExcelGroup(next, worksheet.id) };
    } else {
      next = {
        ...next,
        pages: next.pages.map((page) =>
          page.linkedWorksheetId === worksheet.id
            ? refreshPageFromSource(page, worksheet)
            : page),
      };
    }
    next = applyCoverSourceTruth(next, worksheet.id);
  }
  return next;
}
