/** Keep asset paths origin-relative so local export works after external preview editing. */
import type { PageModel, ProjectModel } from './types';

const ASSET_PATH_RE = /^\/(?:api|static)\//;

/** Convert an absolute or origin-prefixed asset URL to a root-relative path. */
export function normalizeAssetUrl(url: string | undefined | null): string {
  const raw = (url ?? '').trim();
  if (!raw) return '';
  if (raw.startsWith('/') && !raw.startsWith('//')) return raw;
  try {
    const parsed = new URL(raw, 'http://local.invalid');
    if (ASSET_PATH_RE.test(parsed.pathname)) {
      return parsed.pathname + parsed.search;
    }
  } catch {
    /* keep raw below */
  }
  return raw;
}

function normalizeCanvasObject(obj: Record<string, unknown>): Record<string, unknown> {
  const next: Record<string, unknown> = { ...obj };
  if (typeof next.src === 'string') next.src = normalizeAssetUrl(next.src);
  if (Array.isArray(next.objects)) {
    next.objects = next.objects.map((child) =>
      child && typeof child === 'object'
        ? normalizeCanvasObject(child as Record<string, unknown>)
        : child,
    );
  }
  return next;
}

export function normalizeCanvasObjects(objects: Record<string, unknown>[] | undefined): Record<string, unknown>[] {
  return (objects ?? []).map((obj) => normalizeCanvasObject(obj));
}

function normalizePageBlocks(page: PageModel): PageModel {
  const blocks = (page.blocks ?? []).map((block) => {
    if (typeof block.url !== 'string') return block;
    const url = normalizeAssetUrl(block.url);
    return url === block.url ? block : { ...block, url };
  });
  const canvasObjects = normalizeCanvasObjects(page.canvasObjects);
  const sameBlocks = blocks === page.blocks;
  const sameCanvas = canvasObjects === page.canvasObjects;
  if (sameBlocks && sameCanvas) return page;
  return { ...page, blocks, canvasObjects };
}

/** Rewrite persisted absolute local or preview asset URLs to root-relative paths. */
export function normalizeProjectAssetUrls(project: ProjectModel): ProjectModel {
  const pages = project.pages.map(normalizePageBlocks);
  const changed = pages.some((p, i) => p !== project.pages[i]);
  return changed ? { ...project, pages } : project;
}

/** Local origin Playwright should use when rewriting export asset requests. */
export function localAssetOriginFromUrl(pageUrl: string): string {
  try {
    const parsed = new URL(pageUrl);
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return 'http://127.0.0.1:8766';
  }
}

/** Rewrite any /api or /static request to the local export origin. */
export function rewriteAssetRequestUrl(requestUrl: string, localOrigin: string): string {
  try {
    const parsed = new URL(requestUrl);
    if (!ASSET_PATH_RE.test(parsed.pathname)) return requestUrl;
    return localOrigin + parsed.pathname + parsed.search;
  } catch {
    return requestUrl;
  }
}
