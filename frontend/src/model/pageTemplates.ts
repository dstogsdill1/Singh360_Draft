import type { PageModel, PageType } from './types';

/**
 * User-facing page templates. These are friendly names shown in the UI.
 * Internal engine types (data-grid, canvas, index) are never shown directly.
 */
export type PageTemplate =
  | 'Cover'
  | 'Sheet Index'
  | 'Text / Instructions'
  | 'Table / Schedule'
  | 'Matrix'
  | 'Image / Layout'
  | 'Hybrid Sheet'
  | 'Underlay / Reference';

export const PAGE_TEMPLATES: PageTemplate[] = [
  'Cover',
  'Sheet Index',
  'Text / Instructions',
  'Table / Schedule',
  'Matrix',
  'Image / Layout',
  'Hybrid Sheet',
  'Underlay / Reference',
];

/** Internal engine pageType for each friendly template. */
function pageTypeForTemplate(t: PageTemplate): PageType {
  switch (t) {
    case 'Cover':
      return 'cover';
    case 'Sheet Index':
      return 'index';
    case 'Image / Layout':
      return 'canvas';
    case 'Hybrid Sheet':
      return 'hybrid';
    case 'Underlay / Reference':
      return 'underlay';
    case 'Text / Instructions':
    case 'Table / Schedule':
    case 'Matrix':
    default:
      return 'data-grid';
  }
}

/** Derive the friendly template label for a page from its stored fields. */
export function templateForPage(page: PageModel): PageTemplate {
  // Explicit stored template wins (so text/table/matrix stay distinct).
  const stored = (page as { template?: PageTemplate }).template;
  if (stored && PAGE_TEMPLATES.includes(stored)) return stored;

  switch (page.pageType) {
    case 'cover':
      return 'Cover';
    case 'index':
      return 'Sheet Index';
    case 'canvas':
      return 'Image / Layout';
    case 'hybrid':
      return 'Hybrid Sheet';
    case 'underlay':
      return 'Underlay / Reference';
    case 'data-grid':
    default: {
      const blocks = page.blocks ?? [];
      if (blocks.some((b) => b.type === 'matrix')) return 'Matrix';
      if (blocks.some((b) => b.type === 'table')) return 'Table / Schedule';
      return 'Text / Instructions';
    }
  }
}

/**
 * Apply a friendly template to a page WITHOUT destroying content. Sets the
 * internal engine pageType and records the friendly template for round-tripping.
 */
export function applyTemplate(page: PageModel, template: PageTemplate): PageModel {
  return {
    ...page,
    template,
    pageType: pageTypeForTemplate(template),
  } as PageModel;
}
