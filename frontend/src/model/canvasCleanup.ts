import type { PageModel } from './types';

type CanvasObject = Record<string, unknown>;

const PRIMITIVE_TYPES = new Set([
  'circle', 'ellipse', 'line', 'path', 'polygon', 'polyline', 'rect', 'triangle',
]);

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function objectSize(object: CanvasObject): { width: number; height: number } {
  const type = String(object.type ?? '').toLowerCase();
  const scaleX = Math.abs(numberValue(object.scaleX, 1));
  const scaleY = Math.abs(numberValue(object.scaleY, 1));
  if (type === 'line') {
    return {
      width: Math.abs(numberValue(object.x2) - numberValue(object.x1)) * scaleX,
      height: Math.abs(numberValue(object.y2) - numberValue(object.y1)) * scaleY,
    };
  }
  if (type === 'circle') {
    const diameter = Math.abs(numberValue(object.radius)) * 2;
    return { width: diameter * scaleX, height: diameter * scaleY };
  }
  return {
    width: Math.abs(numberValue(object.width)) * scaleX,
    height: Math.abs(numberValue(object.height)) * scaleY,
  };
}

function hasRealPayload(object: CanvasObject): boolean {
  const type = String(object.type ?? '').toLowerCase();
  const text = String(object.text ?? object.label ?? '').trim();
  if (text) return true;
  if (type.includes('image') || object.src || object.assetPath || object.componentId || object.pdfSource) return true;
  if (object.s360Role || object.libraryComponentId || object.legendId) return true;
  return false;
}

function isCover(page: Pick<PageModel, 'pageType' | 'sheetTitle' | 'sheetCode' | 'displaySheetCode'>): boolean {
  if (page.pageType === 'cover') return true;
  const label = `${page.sheetTitle ?? ''} ${page.displaySheetCode ?? page.sheetCode ?? ''}`.toLowerCase();
  return /\bcover\b/.test(label) || /\bproject info\b/.test(label);
}

/** Tiny primitive overlay objects on a cover are never workbook content. */
export function isCoverArtifact(object: CanvasObject): boolean {
  if (hasRealPayload(object)) return false;
  const type = String(object.type ?? '').toLowerCase();
  const opacity = numberValue(object.opacity, 1);
  if (object.visible === false || opacity <= 0.001) return true;
  if (!PRIMITIVE_TYPES.has(type)) return false;

  const { width, height } = objectSize(object);
  const maxDimension = Math.max(width, height);
  const minDimension = Math.min(width, height);
  const area = width * height;
  if (!Number.isFinite(maxDimension) || !Number.isFinite(area)) return true;
  if (maxDimension <= 44) return true;
  if (area <= 1_100 && maxDimension <= 80) return true;
  if (minDimension <= 2 && maxDimension <= 80) return true;
  return false;
}

/**
 * Automatically removes the persisted cover-page dot/micro-artifact. Legitimate
 * images, components, labels and full-size drawing objects are always retained.
 */
export function sanitizeCanvasObjectsForPage(
  page: Pick<PageModel, 'pageType' | 'sheetTitle' | 'sheetCode' | 'displaySheetCode'>,
  objects: CanvasObject[],
): CanvasObject[] {
  if (!isCover(page) || !objects.length) return objects;
  const cleaned = objects.filter((object) => !isCoverArtifact(object));
  return cleaned.length === objects.length ? objects : cleaned;
}
