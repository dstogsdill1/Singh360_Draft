import type {
  ExcelCellStyle,
  MergedCell,
  PageBlock,
  SpreadsheetRegion,
  SpreadsheetPageRecipe,
  Worksheet,
} from './types';
import { DEFAULT_COLUMN_WIDTH_PX, DEFAULT_ROW_HEIGHT_PX } from './workbookGeometry';
import { rangeBounds } from '../workspace/workspaceContract';
import { letters, parseCoordinate } from '../workspace/UniverWorkbookAdapter';

export interface SpreadsheetPreflightWarning {
  code: 'blank-page' | 'clipped-text' | 'font-too-small' | 'merge-crosses-break'
    | 'duplicate-range' | 'overflow' | 'partial-merge';
  pageId: string;
  regionId?: string;
  message: string;
}

function intersects(
  a: { startRow: number; endRow: number; startColumn: number; endColumn: number },
  b: { startRow: number; endRow: number; startColumn: number; endColumn: number },
): boolean {
  return a.startRow <= b.endRow && a.endRow >= b.startRow
    && a.startColumn <= b.endColumn && a.endColumn >= b.startColumn;
}

function contains(
  outer: { startRow: number; endRow: number; startColumn: number; endColumn: number },
  inner: { startRow: number; endRow: number; startColumn: number; endColumn: number },
): boolean {
  return outer.startRow <= inner.startRow && outer.endRow >= inner.endRow
    && outer.startColumn <= inner.startColumn && outer.endColumn >= inner.endColumn;
}

export function regionScale(region: SpreadsheetRegion, block: PageBlock): number {
  const naturalWidth = Math.max(1, (block.colWidths || []).reduce((sum, value) => sum + value, 0));
  const naturalHeight = Math.max(1, (block.rowHeights || []).reduce((sum, value) => sum + value, 0));
  if (region.fitMode === 'exact_scale') return Math.max(0.01, Number(region.scale) || 1);
  const widthScale = Math.max(0.01, region.width / naturalWidth);
  return region.fitMode === 'fit_width'
    ? widthScale
    : Math.min(widthScale, Math.max(0.01, region.height / naturalHeight));
}

/** Build the exact visible worksheet geometry selected by a SpreadsheetRegion. */
export function spreadsheetRegionBlock(
  worksheet: Worksheet,
  region: SpreadsheetRegion,
): PageBlock | null {
  const bounds = rangeBounds(region.range);
  if (!bounds) return null;
  const hiddenRows = new Set(worksheet.hiddenRows || []);
  const hiddenColumns = new Set(worksheet.hiddenColumns || []);
  const selectedRows = Array.from(
    { length: bounds.endRow - bounds.startRow + 1 },
    (_, index) => bounds.startRow + index,
  ).filter((row) => !hiddenRows.has(row));
  const explicitHeaderRows = [...new Set(region.repeatRows)]
    .filter((row) => row >= 0 && row < worksheet.grid.length && !hiddenRows.has(row) && !selectedRows.includes(row))
    .sort((left, right) => left - right);
  const rows = [...explicitHeaderRows, ...selectedRows];
  const columns = Array.from(
    { length: bounds.endColumn - bounds.startColumn + 1 },
    (_, index) => bounds.startColumn + index,
  ).filter((column) => !hiddenColumns.has(column));
  const rowMap = new Map(rows.map((row, index) => [row, index]));
  const columnMap = new Map(columns.map((column, index) => [column, index]));

  const styles: Record<string, ExcelCellStyle> = {};
  Object.entries(worksheet.styles || {}).forEach(([coordinate, style]) => {
    const [row, column] = parseCoordinate(coordinate);
    const mappedRow = rowMap.get(row);
    const mappedColumn = columnMap.get(column);
    if (mappedRow !== undefined && mappedColumn !== undefined) {
      styles[`${mappedRow}:${mappedColumn}`] = style;
    }
  });

  const mergedCells: MergedCell[] = [];
  (worksheet.mergedCells || []).forEach((merge) => {
    const mergeBounds = {
      startRow: merge.startRow,
      endRow: merge.endRow,
      startColumn: merge.startCol,
      endColumn: merge.endCol,
    };
    const repeatedMerge = merge.startCol >= bounds.startColumn && merge.endCol <= bounds.endColumn
      && Array.from({ length: merge.endRow - merge.startRow + 1 }, (_, index) => merge.startRow + index)
        .every((row) => explicitHeaderRows.includes(row));
    if (!contains(bounds, mergeBounds) && !repeatedMerge) return;
    const mergeRows = rows.filter((row) => row >= merge.startRow && row <= merge.endRow);
    const mergeColumns = columns.filter((column) => column >= merge.startCol && column <= merge.endCol);
    if (!mergeRows.length || !mergeColumns.length) return;
    mergedCells.push({
      startRow: rowMap.get(mergeRows[0])!,
      endRow: rowMap.get(mergeRows[mergeRows.length - 1])!,
      startCol: columnMap.get(mergeColumns[0])!,
      endCol: columnMap.get(mergeColumns[mergeColumns.length - 1])!,
    });
  });

  const relativeRepeatRows = region.repeatRows
    .filter((row) => rowMap.has(row))
    .map((row) => rowMap.get(row)!);
  return {
    id: region.id,
    type: 'excelRange',
    sourceWorksheetId: worksheet.id,
    sourceSheet: worksheet.name,
    sourceRange: region.range,
    renderMode: 'spreadsheet_region',
    renderProfile: 'source_exact',
    grid: rows.map((row) => columns.map((column) => worksheet.grid[row]?.[column] ?? '')),
    styles,
    mergedCells,
    colWidths: columns.map((column) => worksheet.colWidthsPx?.[column] ?? DEFAULT_COLUMN_WIDTH_PX),
    rowHeights: rows.map((row) => worksheet.rowHeightsPx?.[row] ?? DEFAULT_ROW_HEIGHT_PX),
    srcRows: rows,
    repeatRows: relativeRepeatRows,
    headerRowCount: relativeRepeatRows.length,
    allowContinuation: false,
    splitMode: 'explicit_ranges',
    scaleMode: region.fitMode,
    noGrow: true,
    trimBlankRows: false,
    trimBlankColumns: false,
    preserveGeometry: region.preserveGeometry,
  } as PageBlock;
}

export function spreadsheetPreflight(
  pageId: string,
  regions: SpreadsheetRegion[],
  worksheets: Worksheet[],
): SpreadsheetPreflightWarning[] {
  const warnings: SpreadsheetPreflightWarning[] = [];
  const worksheetById = new Map(worksheets.map((item) => [item.id, item]));
  if (!regions.length) {
    warnings.push({ code: 'blank-page', pageId, message: 'Page has no spreadsheet regions.' });
    return warnings;
  }
  const seen: Array<{ region: SpreadsheetRegion; bounds: NonNullable<ReturnType<typeof rangeBounds>> }> = [];
  let pageHasContent = false;
  regions.forEach((region) => {
    const worksheet = worksheetById.get(region.sourceSheetId);
    const bounds = rangeBounds(region.range);
    if (!worksheet || !bounds) return;
    const block = spreadsheetRegionBlock(worksheet, region);
    if (!block) return;
    if ((block.grid || []).some((row) => row.some((value) => String(value || '').trim()))) pageHasContent = true;
    const scale = regionScale(region, block);
    const naturalWidth = (block.colWidths || []).reduce((sum, value) => sum + value, 0);
    const naturalHeight = (block.rowHeights || []).reduce((sum, value) => sum + value, 0);
    if (region.x < 0 || region.y < 0 || region.x + region.width > 1632 || region.y + region.height > 912
      || naturalWidth * scale > region.width + 0.5 || naturalHeight * scale > region.height + 0.5) {
      warnings.push({ code: 'overflow', pageId, regionId: region.id, message: `${region.range} overflows its page box.` });
    }
    const fonts = Object.values(block.styles || {})
      .map((style) => Number(style.fontSize || 11) * scale)
      .filter(Number.isFinite);
    if (fonts.length && Math.min(...fonts) < 6.5) {
      warnings.push({ code: 'font-too-small', pageId, regionId: region.id, message: `${region.range} renders below 6.5 pt.` });
    }
    (worksheet.mergedCells || []).forEach((merge) => {
      const mergeBounds = { startRow: merge.startRow, endRow: merge.endRow, startColumn: merge.startCol, endColumn: merge.endCol };
      if (intersects(bounds, mergeBounds) && !contains(bounds, mergeBounds)) {
        warnings.push({ code: 'partial-merge', pageId, regionId: region.id, message: `${region.range} cuts through a merged cell.` });
      }
      if (region.explicitBreaks.some((row) => row > merge.startRow && row <= merge.endRow)) {
        warnings.push({ code: 'merge-crosses-break', pageId, regionId: region.id, message: `A page break crosses merged rows ${merge.startRow + 1}-${merge.endRow + 1}.` });
      }
    });
    const widths = block.colWidths || [];
    (block.grid || []).forEach((row, rowIndex) => row.forEach((raw, columnIndex) => {
      const text = String(raw || '');
      const style = block.styles?.[`${rowIndex}:${columnIndex}`];
      if (!text || style?.wrap) return;
      const fontPx = Number(style?.fontSize || 11) * 4 / 3;
      if (text.length * fontPx * 0.52 > (widths[columnIndex] || DEFAULT_COLUMN_WIDTH_PX)) {
        warnings.push({ code: 'clipped-text', pageId, regionId: region.id, message: `${worksheet.name}!${letters(bounds.startColumn + columnIndex)}${bounds.startRow + rowIndex + 1} may clip.` });
      }
    }));
    seen.forEach((prior) => {
      if (prior.region.sourceSheetId === region.sourceSheetId && intersects(prior.bounds, bounds)) {
        warnings.push({ code: 'duplicate-range', pageId, regionId: region.id, message: `${region.range} overlaps ${prior.region.range}; source rows would repeat.` });
      }
    });
    seen.push({ region, bounds });
  });
  if (!pageHasContent) warnings.push({ code: 'blank-page', pageId, message: 'Page contains only blank selected cells.' });
  return warnings;
}

export function spreadsheetRecipePreflight(
  recipes: SpreadsheetPageRecipe[],
  worksheets: Worksheet[],
): SpreadsheetPreflightWarning[] {
  const warnings = recipes.flatMap((recipe) => spreadsheetPreflight(recipe.pageId, recipe.regions, worksheets));
  const prior: Array<{ pageId: string; region: SpreadsheetRegion; bounds: NonNullable<ReturnType<typeof rangeBounds>> }> = [];
  recipes.forEach((recipe) => recipe.regions.forEach((region) => {
    const bounds = rangeBounds(region.range);
    if (!bounds) return;
    prior.forEach((item) => {
      if (item.pageId !== recipe.pageId && item.region.sourceSheetId === region.sourceSheetId && intersects(item.bounds, bounds)) {
        warnings.push({
          code: 'duplicate-range',
          pageId: recipe.pageId,
          regionId: region.id,
          message: `${region.range} overlaps ${item.region.range} on page ${item.pageId}; source rows would repeat.`,
        });
      }
    });
    prior.push({ pageId: recipe.pageId, region, bounds });
  }));
  return warnings;
}
