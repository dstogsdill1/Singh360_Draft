import type { PageModel } from './types';

function cleanText(value: unknown): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function pageHaystack(page: PageModel): string {
  return cleanText([
    page.sheetTitle,
    page.sheetTab,
    page.sourceSheet,
    page.displaySheetCode,
    page.sheetCode,
  ].filter(Boolean).join(' ')).toLowerCase();
}

export function isSheetIndexPage(page: PageModel): boolean {
  if (page.pageType === 'index') return true;
  const hay = pageHaystack(page);
  return hay.includes('sheet index')
    || hay.includes('table of contents')
    || /(^|\s)toc($|\s|\/)/i.test(hay);
}

export function isCoverPage(page: PageModel): boolean {
  if (page.pageType === 'cover') return true;
  const hay = pageHaystack(page);
  return hay.includes('cover / project info')
    || hay.includes('cover project info')
    || hay.includes('title sheet');
}

function currentCode(page: PageModel | undefined): string {
  return cleanText(page?.displaySheetCode || page?.sheetCode || '');
}

function inferIndexCode(cover: PageModel | undefined, index: PageModel): string {
  const existing = currentCode(index);
  const coverCode = currentCode(cover);
  if (existing && existing.toLowerCase() !== coverCode.toLowerCase()) return existing;

  const match = coverCode.match(/^(.+?)\s+\d+(?:\.\d+)?[a-z]?$/i);
  const prefix = cleanText(match?.[1] || 'EMS');
  return `${prefix || 'EMS'} 2.0`;
}

/** User-facing type text for the generated index; no internal render/profile data. */
export function indexPageTypeLabel(page: PageModel): string {
  const hay = pageHaystack(page);
  if (isCoverPage(page)) return 'Cover';
  if (isSheetIndexPage(page)) return 'Sheet Index';
  if (hay.includes('company info')) return 'Company Info';
  if (hay.includes('schematic') || hay.includes('wiring diagram')) return 'PDF / Layout';
  if (
    page.pageType === 'canvas'
    || page.pageType === 'underlay'
    || page.pageType === 'hybrid'
    || hay.includes('device location')
    || hay.includes('overall layout')
  ) return 'Image / Layout';

  const blockTypes = new Set((page.blocks ?? []).map((block) => block.type));
  if (blockTypes.has('idfNetworkTable')) return 'Network Table';
  if (blockTypes.has('matrix')) return 'Matrix';
  if (blockTypes.has('table') || blockTypes.has('excelRange')) return 'Table / Schedule';
  return 'Text / Instructions';
}

/** Remove importer/internal boilerplate while preserving real user-entered notes. */
export function cleanIndexNote(page: PageModel): string {
  const note = cleanText(page.notes);
  if (!note || note === '—' || note === '-' || note.toLowerCase() === 'nts') return '';
  const low = note.toLowerCase();
  const boilerplate = [
    'internal build tracker',
    'not exported unless intentionally included',
    'insert/crop pdf schematic',
    'manual plan/device location page',
    'manual floor-plan/underlay work in app',
    'manual layout page for singh360 draft',
  ];
  if (boilerplate.some((phrase) => low.includes(phrase))) return '';
  return note;
}

function stableOrder(pages: PageModel[]): PageModel[] {
  return pages
    .map((page, index) => ({ page, index }))
    .sort((a, b) => {
      const ao = Number.isFinite(a.page.order) ? a.page.order : a.index + 1;
      const bo = Number.isFinite(b.page.order) ? b.page.order : b.index + 1;
      return ao - bo || a.index - b.index;
    })
    .map(({ page }) => ({ ...page }));
}

/**
 * Canonical package arrangement:
 *   1. Cover is the first included page.
 *   2. Sheet Index is the second included page and always included.
 *   3. Remaining included pages stay in their current relative order.
 *   4. Excluded/internal pages remain available, but move after package pages.
 *   5. Every included physical page (including continuations) gets a unique
 *      Page X of Y number. Therefore Order == Page for included pages.
 *
 * The linked worksheet is never changed, so Source view still shows every raw
 * index row and column.
 */
export function normalizePackagePages(input: PageModel[]): PageModel[] {
  const ordered = stableOrder(input ?? []);
  const cover = ordered.find(isCoverPage);
  const index = ordered.find(isSheetIndexPage);
  const reserved = new Set([cover?.id, index?.id].filter(Boolean) as string[]);
  const remaining = ordered.filter((page) => !reserved.has(page.id));
  const includedRest = remaining.filter((page) => page.include !== false);
  const excludedRest = remaining.filter((page) => page.include === false);

  let arranged: PageModel[] = [];
  if (cover) arranged.push({ ...cover, include: true });
  if (index) {
    const code = inferIndexCode(cover, index);
    arranged.push({
      ...index,
      include: true,
      pageType: 'index',
      renderMode: 'generated_index',
      normalizedHeaderStyle: 'orange',
      sheetCode: code,
      displaySheetCode: code,
      sheetTitle: cleanText(index.sheetTitle) || 'Sheet Index / TOC',
      sheetTab: cleanText(index.sheetTab) || 'Sheet Index',
    });
  }
  arranged.push(...includedRest, ...excludedRest);

  if (!cover && !index) arranged = [...includedRest, ...excludedRest];

  const total = arranged.filter((page) => page.include !== false).length;
  let pageNumber = 0;
  return arranged.map((page, indexPosition) => {
    if (page.include === false) {
      return { ...page, order: indexPosition + 1, pageNumber: null, pageTotal: total };
    }
    pageNumber += 1;
    return { ...page, order: indexPosition + 1, pageNumber, pageTotal: total };
  });
}
