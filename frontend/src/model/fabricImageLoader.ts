import { FabricImage } from 'fabric';
import { normalizeAssetUrl } from './assetUrl';

type SerializedFabricObject = Record<string, unknown>;

export interface SerializedImageRepair {
  objects: SerializedFabricObject[];
  repaired: number;
}

function positiveNumber(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function isSvgAssetUrl(url: string): boolean {
  return /\.svg(?:$|[?#])/i.test(url.trim());
}

export function intrinsicFabricImageSize(img: FabricImage): { width: number; height: number } {
  const element = img.getElement() as HTMLImageElement;
  return {
    width: positiveNumber(element?.naturalWidth || element?.width || img.width, 1),
    height: positiveNumber(element?.naturalHeight || element?.height || img.height, 1),
  };
}

/**
 * Load a component image with one SVG geometry contract.
 *
 * Fresh component and legend loads must always start at the complete intrinsic
 * image: no inherited crop, no stale Fabric fallback size, and explicit bounds.
 */
export async function loadSafeFabricImage(url: string): Promise<FabricImage> {
  const assetUrl = normalizeAssetUrl(url) || url;
  const img = await FabricImage.fromURL(assetUrl, { crossOrigin: 'anonymous' });
  if (!isSvgAssetUrl(assetUrl)) return img;
  const intrinsic = intrinsicFabricImageSize(img);
  img.set({
    cropX: 0,
    cropY: 0,
    width: intrinsic.width,
    height: intrinsic.height,
    scaleX: 1,
    scaleY: 1,
    originX: 'left',
    originY: 'top',
  });
  img.setCoords();
  return img;
}

function componentSvgUrls(objects: SerializedFabricObject[]): string[] {
  const urls = new Set<string>();
  const visit = (items: SerializedFabricObject[]) => {
    items.forEach((item) => {
      const type = String(item.type || '').toLowerCase();
      const sourceUrl = String(item.sourceUrl || '').trim();
      if (type === 'image' && sourceUrl && isSvgAssetUrl(sourceUrl)) {
        urls.add(normalizeAssetUrl(sourceUrl) || sourceUrl);
      }
      if (Array.isArray(item.objects)) {
        visit(item.objects as SerializedFabricObject[]);
      }
    });
  };
  visit(objects);
  return [...urls];
}

/**
 * Repair saved SVG component records before Fabric groups calculate bounds.
 *
 * The old rendered width/height and left/top/origin are retained exactly.
 * Only intrinsic width/height, crop, and the compensating scale are normalized.
 * Doing this before load also keeps saved legend group bounds stable.
 */
export async function repairSerializedComponentSvgImages(
  objects: SerializedFabricObject[],
): Promise<SerializedImageRepair> {
  const dimensions = new Map<string, { width: number; height: number }>();
  await Promise.all(componentSvgUrls(objects).map(async (url) => {
    try {
      const img = await loadSafeFabricImage(url);
      dimensions.set(url, intrinsicFabricImageSize(img));
    } catch {
      // A missing asset must not prevent the rest of the saved canvas loading.
    }
  }));

  let repaired = 0;
  const visit = (items: SerializedFabricObject[]): SerializedFabricObject[] => items.map((item) => {
    let next: SerializedFabricObject = { ...item };
    if (Array.isArray(item.objects)) {
      next.objects = visit(item.objects as SerializedFabricObject[]);
    }

    const type = String(item.type || '').toLowerCase();
    const sourceUrl = String(item.sourceUrl || '').trim();
    if (type !== 'image' || !sourceUrl || !isSvgAssetUrl(sourceUrl)) return next;
    const normalizedUrl = normalizeAssetUrl(sourceUrl) || sourceUrl;
    const intrinsic = dimensions.get(normalizedUrl);
    if (!intrinsic) return next;

    const oldWidth = positiveNumber(item.width, intrinsic.width);
    const oldHeight = positiveNumber(item.height, intrinsic.height);
    const oldScaleX = positiveNumber(item.scaleX, 1);
    const oldScaleY = positiveNumber(item.scaleY, 1);
    const renderedWidth = oldWidth * oldScaleX;
    const renderedHeight = oldHeight * oldScaleY;
    const scaleX = renderedWidth / intrinsic.width;
    const scaleY = renderedHeight / intrinsic.height;
    const needsRepair = (
      Number(item.cropX || 0) !== 0
      || Number(item.cropY || 0) !== 0
      || oldWidth !== intrinsic.width
      || oldHeight !== intrinsic.height
      || Number(item.scaleX ?? 1) !== scaleX
      || Number(item.scaleY ?? 1) !== scaleY
    );
    if (!needsRepair) return next;

    repaired += 1;
    next = {
      ...next,
      cropX: 0,
      cropY: 0,
      width: intrinsic.width,
      height: intrinsic.height,
      scaleX,
      scaleY,
      sourceUrl: normalizedUrl,
      src: normalizedUrl,
    };
    return next;
  });

  return { objects: visit(objects), repaired };
}
