/**
 * Frontend mirror of core/workbook_geometry.py.
 *
 * Excel widths are OOXML default-font character units, Excel row heights and
 * PDF geometry are points, and Univer/drawing geometry is CSS pixels. No
 * workbook consumer should use ad-hoc width/height multipliers.
 */
export const CSS_PIXELS_PER_INCH = 96;
export const PDF_POINTS_PER_INCH = 72;
export const EXCEL_MAX_DIGIT_WIDTH_PX = 7;
export const EXCEL_COLUMN_PADDING_PX = 5;
export const DEFAULT_COLUMN_WIDTH_UNITS = 8.43;
export const DEFAULT_ROW_HEIGHT_POINTS = 15;
export const DEFAULT_COLUMN_WIDTH_PX = 64;
export const DEFAULT_ROW_HEIGHT_PX = 20;

function positiveNumber(value: unknown, fallback: number): number {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : fallback;
}

export function excelColumnWidthToPixels(width: unknown): number {
  const units = positiveNumber(width, DEFAULT_COLUMN_WIDTH_UNITS);
  return Math.max(1, Math.floor(
    ((256 * units + Math.floor(128 / EXCEL_MAX_DIGIT_WIDTH_PX)) / 256)
    * EXCEL_MAX_DIGIT_WIDTH_PX,
  ) + EXCEL_COLUMN_PADDING_PX);
}

export function pixelsToExcelColumnWidth(pixels: unknown): number {
  const widthPx = positiveNumber(pixels, DEFAULT_COLUMN_WIDTH_PX);
  if (widthPx <= EXCEL_COLUMN_PADDING_PX) {
    return Math.round(
      widthPx / (EXCEL_MAX_DIGIT_WIDTH_PX + EXCEL_COLUMN_PADDING_PX) * 100,
    ) / 100;
  }
  return Math.round(
    (widthPx - EXCEL_COLUMN_PADDING_PX) / EXCEL_MAX_DIGIT_WIDTH_PX * 100,
  ) / 100;
}

export function rowHeightPointsToPixels(points: unknown): number {
  const value = positiveNumber(points, DEFAULT_ROW_HEIGHT_POINTS);
  return Math.round(value * CSS_PIXELS_PER_INCH / PDF_POINTS_PER_INCH * 10_000) / 10_000;
}

export function pixelsToRowHeightPoints(pixels: unknown): number {
  const value = positiveNumber(pixels, DEFAULT_ROW_HEIGHT_PX);
  return Math.round(value * PDF_POINTS_PER_INCH / CSS_PIXELS_PER_INCH * 10_000) / 10_000;
}

export function pixelsToPdfPoints(pixels: number): number {
  if (!Number.isFinite(pixels)) throw new Error('Pixel geometry must be finite.');
  return pixels * PDF_POINTS_PER_INCH / CSS_PIXELS_PER_INCH;
}

export function pdfPointsToPixels(points: number): number {
  if (!Number.isFinite(points)) throw new Error('PDF geometry must be finite.');
  return points * CSS_PIXELS_PER_INCH / PDF_POINTS_PER_INCH;
}

export function unchangedExcelWidthOrConverted(
  pixels: unknown,
  previousWidth?: unknown,
): number {
  const widthPx = Math.round(positiveNumber(pixels, DEFAULT_COLUMN_WIDTH_PX));
  if (previousWidth !== undefined) {
    const previous = positiveNumber(previousWidth, DEFAULT_COLUMN_WIDTH_UNITS);
    if (excelColumnWidthToPixels(previous) === widthPx) return previous;
  }
  return pixelsToExcelColumnWidth(widthPx);
}

export function unchangedRowHeightOrConverted(
  pixels: unknown,
  previousPoints?: unknown,
  tolerance = 0.01,
): number {
  const heightPx = positiveNumber(pixels, DEFAULT_ROW_HEIGHT_PX);
  if (previousPoints !== undefined) {
    const previous = positiveNumber(previousPoints, DEFAULT_ROW_HEIGHT_POINTS);
    if (Math.abs(rowHeightPointsToPixels(previous) - heightPx) <= tolerance) return previous;
  }
  return pixelsToRowHeightPoints(heightPx);
}
