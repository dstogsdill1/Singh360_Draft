import type { WorkbookDocument } from '../api/client';
import {
  applyCoverSourceTruth,
  buildExcelRangeBlock,
  refreshPageFromSource,
  regenerateExcelGroup,
  splitExcelRangeBlock,
} from '../model/excelRange';
import {
  DEFAULT_COLUMN_WIDTH_UNITS,
  DEFAULT_ROW_HEIGHT_POINTS,
  excelColumnWidthToPixels,
  rowHeightPointsToPixels,
} from '../model/workbookGeometry';
import type { MergedCell, PageModel, ProjectModel, Worksheet } from '../model/types';
import { columnIndex, letters, parseCoordinate } from './UniverWorkbookAdapter';
import { rangeBounds } from './workspaceContract';

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
    role: sheet.role,
    sourceSetup: sheet.sourceSetup ? { ...sheet.sourceSetup } : undefined,
    protectedRanges: [...sheet.protectedRanges],
    dataValidations: sheet.dataValidations.map((item) => ({ ...item })),
    conditionalFormats: sheet.conditionalFormats.map((item) => ({ ...item })),
    tableRegions: sheet.tableRegions.map((item) => ({ ...item })),
    tableLayout: sheet.tableLayout,
    annotations: sheet.annotations.map((item) => ({ ...item })),
  } as Worksheet;
}

interface IndexEntry {
  sheetTab: string;
  title: string;
  code: string;
  publishStatus: '' | 'YES' | 'NO' | 'VERIFY';
  issueStatus: PageModel['issueStatus'];
  pageType: string;
  order: number;
}

function normalizePublish(value: unknown): IndexEntry['publishStatus'] {
  const raw = String(value || '').trim().toUpperCase();
  return raw === 'YES' || raw === 'NO' || raw === 'VERIFY' ? raw : '';
}

function normalizeIssue(value: unknown): PageModel['issueStatus'] {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  return ['draft', 'draft_confirmed', 'public', 'public_confirmed'].includes(raw)
    ? raw as PageModel['issueStatus']
    : 'draft';
}

function indexEntries(document: WorkbookDocument): IndexEntry[] {
  const sheet = document.sheets.find((item) => item.name.trim().toUpperCase() === '00_INDEX');
  if (!sheet) return [];
  const rows = new Map<number, Map<number, string>>();
  Object.entries(sheet.cells).forEach(([coordinate, cell]) => {
    const [row, column] = parseCoordinate(coordinate);
    const value = String(cell.v ?? '').trim();
    if (!value) return;
    const values = rows.get(row) || new Map<number, string>();
    values.set(column, value);
    rows.set(row, values);
  });
  let headerRow = -1;
  let header = new Map<number, string>();
  rows.forEach((values, row) => {
    const labels = [...values.values()].map((value) => value.toLowerCase());
    if (labels.some((value) => ['sheet tab', 'sheet name', 'tab'].includes(value))
      && labels.some((value) => ['page title', 'sheet title', 'title'].includes(value))) {
      headerRow = row;
      header = new Map([...values.entries()].map(([column, value]) => [column, value.toLowerCase()]));
    }
  });
  if (headerRow < 0) return [];
  const column = (...aliases: string[]) =>
    [...header.entries()].find(([, value]) => aliases.includes(value))?.[0] ?? -1;
  const tab = column('sheet tab', 'sheet name', 'tab');
  const title = column('page title', 'sheet title', 'title');
  const code = column('sheet code', 'sheet no.', 'sheet no', 'code');
  const include = column('include', 'include / publish', 'publish');
  const lifecycle = column('lifecycle', 'issue status');
  const type = column('page type', 'type');
  const order = column('order', 'page order');
  const result: IndexEntry[] = [];
  rows.forEach((values, row) => {
    if (row <= headerRow || !values.get(tab)) return;
    result.push({
      sheetTab: values.get(tab) || '',
      title: values.get(title) || values.get(tab) || '',
      code: values.get(code) || '',
      publishStatus: normalizePublish(values.get(include)),
      issueStatus: normalizeIssue(values.get(lifecycle)),
      pageType: values.get(type) || '',
      order: Number(values.get(order)) || result.length + 1,
    });
  });
  return result.sort((left, right) => left.order - right.order);
}

function cropWorksheet(worksheet: Worksheet, range: string): Worksheet | null {
  const bounds = rangeBounds(range);
  if (!bounds) return null;
  const rowOffset = bounds.startRow;
  const columnOffset = bounds.startColumn;
  const rowCount = bounds.endRow - rowOffset + 1;
  const columnCount = bounds.endColumn - columnOffset + 1;
  const grid = Array.from({ length: rowCount }, (_, row) =>
    Array.from({ length: columnCount }, (_, column) =>
      worksheet.grid[row + rowOffset]?.[column + columnOffset] ?? '',
    ),
  );
  const styles: NonNullable<Worksheet['styles']> = {};
  const formulas: NonNullable<Worksheet['formulas']> = {};
  Object.entries(worksheet.styles || {}).forEach(([coordinate, style]) => {
    const [row, column] = parseCoordinate(coordinate);
    if (row < rowOffset || row > bounds.endRow || column < columnOffset || column > bounds.endColumn) return;
    styles[`${letters(column - columnOffset)}${row - rowOffset + 1}`] = style;
  });
  Object.entries(worksheet.formulas || {}).forEach(([coordinate, formula]) => {
    const [row, column] = parseCoordinate(coordinate);
    if (row < rowOffset || row > bounds.endRow || column < columnOffset || column > bounds.endColumn) return;
    formulas[`${letters(column - columnOffset)}${row - rowOffset + 1}`] = formula;
  });
  const mergedCells = (worksheet.mergedCells || [])
    .filter((merge) => merge.startRow >= rowOffset && merge.endRow <= bounds.endRow
      && merge.startCol >= columnOffset && merge.endCol <= bounds.endColumn)
    .map((merge) => ({
      startRow: merge.startRow - rowOffset,
      endRow: merge.endRow - rowOffset,
      startCol: merge.startCol - columnOffset,
      endCol: merge.endCol - columnOffset,
    }));
  return {
    ...worksheet,
    id: `${worksheet.id}:${range}`,
    grid,
    styles,
    formulas,
    mergedCells,
    sourceRange: range,
    colWidthsPx: worksheet.colWidthsPx?.slice(columnOffset, columnOffset + columnCount),
    rowHeightsPx: worksheet.rowHeightsPx?.slice(rowOffset, rowOffset + rowCount),
    hiddenRows: (worksheet.hiddenRows || [])
      .filter((row) => row >= rowOffset && row <= bounds.endRow)
      .map((row) => row - rowOffset),
    hiddenColumns: (worksheet.hiddenColumns || [])
      .filter((column) => column >= columnOffset && column <= bounds.endColumn)
      .map((column) => column - columnOffset),
  };
}

function tableBlocks(worksheet: Worksheet): PageModel['blocks'] {
  const regions = worksheet.tableRegions || [];
  const blocks: NonNullable<PageModel['blocks']> = [];
  regions.forEach((region) => {
    const cropped = cropWorksheet(worksheet, region.range);
    if (!cropped) return;
    const block = buildExcelRangeBlock(cropped, `${worksheet.id}_${region.id}`);
    blocks.push({
      ...block,
      sourceWorksheetId: worksheet.id,
      sourceSheet: worksheet.name,
      sourceRange: region.range,
      noGrow: true,
    });
  });
  return blocks;
}

function tableBlockPages(worksheet: Worksheet): NonNullable<PageModel['blocks']>[] {
  const groups = (tableBlocks(worksheet) || []).map((block) => splitExcelRangeBlock(block));
  const pageCount = Math.max(1, ...groups.map((parts) => parts.length));
  return Array.from({ length: pageCount }, (_, pageIndex) =>
    groups.flatMap((parts) => parts[pageIndex] ? [parts[pageIndex]] : []),
  );
}

function pageType(value: string): PageModel['pageType'] {
  const raw = value.toLowerCase();
  if (raw.includes('cover')) return 'cover';
  if (raw.includes('index')) return 'index';
  if (raw.includes('canvas') || raw.includes('drawing')) return 'canvas';
  return 'data-grid';
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
  const entries = indexEntries(document);
  const pageByTab = new Map(project.pages.map((page) => [page.sheetTab.toLowerCase(), page]));
  const worksheetByName = new Map(worksheets.map((worksheet) => [worksheet.name.toLowerCase(), worksheet]));
  const indexedPages = entries.flatMap((entry) => {
    const existing = pageByTab.get(entry.sheetTab.toLowerCase());
    const worksheet = worksheetByName.get(entry.sheetTab.toLowerCase());
    const blockPages = worksheet?.tableRegions?.length
      ? tableBlockPages(worksheet)
      : [existing?.blocks || []];
    return blockPages.map((blocks, continuationIndex) => ({
      ...(existing || {
        id: `page_${worksheet?.id || entry.sheetTab.replace(/\W+/g, '_').toLowerCase()}`,
        templateId: 'excel-range',
        canvasObjects: [],
        notes: '',
      }),
      ...(continuationIndex ? {
        id: `${existing?.id || `page_${worksheet?.id || 'source'}`}_table_${continuationIndex + 1}`,
        parentPageId: existing?.id,
        continuationOf: existing?.id,
        continuationIndex,
        generatedContinuation: true,
        canvasObjects: [],
      } : {}),
      order: 0,
      include: entry.publishStatus === 'YES',
      publishStatus: entry.publishStatus,
      issueStatus: entry.issueStatus,
      sheetCode: entry.code || existing?.sheetCode || '',
      displaySheetCode: entry.code || existing?.displaySheetCode || existing?.sheetCode || '',
      sheetTitle: continuationIndex ? `${entry.title} — Continued` : entry.title,
      sheetTab: entry.sheetTab,
      pageType: existing?.pageType || pageType(entry.pageType),
      linkedWorksheetId: worksheet?.id || existing?.linkedWorksheetId,
      sourceSheet: worksheet?.name || existing?.sourceSheet,
      renderMode: blocks.some((block) => block.type === 'excelRange') ? 'excel_exact' : existing?.renderMode,
      blocks,
      tableLayout: worksheet?.tableLayout || existing?.tableLayout || 'single',
      tableAnnotations: worksheet?.annotations || existing?.tableAnnotations || [],
    } as PageModel));
  });
  const indexedTabs = new Set(entries.map((entry) => entry.sheetTab.toLowerCase()));
  const pages = [
    ...indexedPages,
    ...project.pages.filter((page) => !indexedTabs.has(page.sheetTab.toLowerCase())),
  ].map((page, index) => ({ ...page, order: index + 1 }));
  let next: ProjectModel = { ...project, worksheets, pages };

  for (const worksheet of updated) {
    const linkedPages = next.pages.filter((page) => page.linkedWorksheetId === worksheet.id);
    if (!linkedPages.length) continue;
    if (worksheet.tableRegions?.length) {
      const blockPages = tableBlockPages(worksheet);
      next = {
        ...next,
        pages: next.pages.map((page) => page.linkedWorksheetId === worksheet.id
          ? {
            ...page,
            blocks: blockPages[page.continuationIndex || 0] || [],
            tableLayout: worksheet.tableLayout || 'single',
            tableAnnotations: worksheet.annotations || [],
            sourceRevision: (page.sourceRevision || 0) + 1,
          }
          : page),
      };
    } else if (linkedPages.some((page) => page.renderMode === 'excel_exact')) {
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
