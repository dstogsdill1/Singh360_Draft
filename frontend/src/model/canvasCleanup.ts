import type { PageModel } from './types';

type AnyObject = Record<string, unknown>;

function numeric(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function visibleSize(object: AnyObject): { width: number; height: number } {
  const type = String(object.type ?? '').toLowerCase();
  const scaleX = Math.abs(numeric(object.scaleX, 1));
  const scaleY = Math.abs(numeric(object.scaleY, 1));
  if (type === 'line') {
    return {
      width: Math.abs(numeric(object.x2) - numeric(object.x1)) * scaleX,
      height: Math.abs(numeric(object.y2) - numeric(object.y1)) * scaleY,
    };
  }
  if (type === 'circle') {
    const diameter = Math.abs(numeric(object.radius)) * 2;
    return { width: diameter * scaleX, height: diameter * scaleY };
  }
  return {
    width: Math.abs(numeric(object.width)) * scaleX,
    height: Math.abs(numeric(object.height)) * scaleY,
  };
}

function protectedObject(object: AnyObject): boolean {
  const type = String(object.type ?? '').toLowerCase();
  if (['text', 'i-text', 'textbox', 'image', 'group'].includes(type)) return true;
  return ['text', 'label', 'componentId', 's360ComponentId', 'pdfSource', 'assetId']
    .some((key) => String(object[key] ?? '').trim().length > 0);
}

export function isCoverMicroArtifact(object: AnyObject): boolean {
  if (protectedObject(object)) return false;
  const { width, height } = visibleSize(object);
  const maxDimension = Math.max(width, height);
  const area = width * height;
  if (!Number.isFinite(maxDimension) || !Number.isFinite(area)) return true;
  return maxDimension <= 10 && area <= 70;
}

export function sanitizeCanvasObjectsForPage(
  page: Pick<PageModel, 'pageType' | 'sheetCode' | 'displaySheetCode'>,
  objects: AnyObject[],
): AnyObject[] {
  const code = String(page.displaySheetCode || page.sheetCode || '').toLowerCase();
  const cover = page.pageType === 'cover' || code === 'ems 1.0' || code.endsWith(' 1.0');
  if (!cover || !objects.length) return objects;
  const cleaned = objects.filter((object) => !isCoverMicroArtifact(object));
  return cleaned.length === objects.length ? objects : cleaned;
}
