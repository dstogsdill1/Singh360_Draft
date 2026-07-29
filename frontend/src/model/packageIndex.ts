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
  // Published index notes must match the title block. Only truly blank/dash
  // placeholders are suppressed; NTS and real page notes are preserved.
  if (!note || note === '—' || note === '-') return '';
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

function keepContinuationsWithBase(pages: PageModel[]): PageModel[] {
  const continuations = new Map<string, PageModel[]>();
  for (const page of pages) {
    if (!page.continuationOf) continue;
    const group = continuations.get(page.continuationOf) ?? [];
    group.push(page);
    continuations.set(page.continuationOf, group);
  }
  for (const group of continuations.values()) {
    group.sort((a, b) => (a.continuationIndex ?? 1) - (b.continuationIndex ?? 1));
  }
  const result: PageModel[] = [];
  const emitted = new Set<string>();
  for (const page of pages) {
    if (page.continuationOf) continue;
    result.push(page);
    emitted.add(page.id);
    result.push(...(continuations.get(page.id) ?? []));
  }
  // Preserve malformed/orphaned continuations visibly; validation can then
  // report them rather than silently dropping user work.
  result.push(...pages.filter((page) => page.continuationOf && !emitted.has(page.continuationOf)));
  return result;
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
  const ordered = keepContinuationsWithBase(stableOrder(input ?? []));
  const cover = ordered.find(isCoverPage);
  const index = ordered.find(isSheetIndexPage);
  const reserved = new Set([cover?.id, index?.id].filter(Boolean) as string[]);
  const remaining = ordered.filter((page) => !reserved.has(page.id));
  // S360 EXCLUDED PAGES STAY IN POSITION: Include/Exclude affects export and
  // Page X of Y, not editor visibility or the user's chosen workbook/app order.
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
  arranged.push(...remaining);

  if (!cover && !index) arranged = [...remaining];

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
