import type { PageModel } from './types';

const DEFAULT_INDEX_ROWS_PER_PAGE = 46;
const MIN_INDEX_ROWS_PER_PAGE = 2;
const MAX_INDEX_ROWS_PER_PAGE = 250;
const RETIRED_INDEX_REASON = 'App-managed Sheet Index continuation no longer required.';

export interface PackageNormalizationOptions {
  /** Stable timestamp supplied by the caller for archive/restore metadata. */
  now?: string;
  /** Project indexSettings.rowsPerPage, when it has changed in the same edit. */
  indexRowsPerPage?: number;
  /** Project coverSettings.include, when it has changed in the same edit. */
  coverIncluded?: boolean;
  /** Project managedPagePolicy authority when the caller has the full project. */
  automaticManagedPages?: boolean;
}

export interface NormalizedPackageManifest {
  pages: PageModel[];
  archivedPages: PageModel[];
}

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
  const pageType = cleanText(page.pageType).replace(/[^a-z0-9]+/gi, '').toLowerCase();
  return page.managedPage === 'index' || pageType === 'index' || pageType === 'sheetindex';
}

export function isCoverPage(page: PageModel): boolean {
  return page.managedPage === 'cover' || page.pageType === 'cover';
}

function currentCode(page: PageModel | undefined): string {
  return cleanText(page?.displaySheetCode || page?.sheetCode || '');
}

function isGeneratedIndexContinuation(page: PageModel): boolean {
  return Boolean(
    page.generatedIndexContinuation
    || page.indexContinuation
    || (
      page.generatedContinuation
      && (page.continuationOf || page.pageGroupId)
      && isSheetIndexPage(page)
    ),
  );
}

function validatedRowsPerPage(value: unknown, fallback: unknown): number {
  for (const candidate of [value, fallback, DEFAULT_INDEX_ROWS_PER_PAGE]) {
    const rows = Number(candidate);
    if (
      Number.isInteger(rows)
      && rows >= MIN_INDEX_ROWS_PER_PAGE
      && rows <= MAX_INDEX_ROWS_PER_PAGE
    ) return rows;
  }
  return DEFAULT_INDEX_ROWS_PER_PAGE;
}

function requiredIndexPageCount(baseIncludedCount: number, rowsPerPage: number): number {
  let count = 1;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const physicalPageCount = baseIncludedCount + count - 1;
    const required = Math.max(1, Math.ceil(physicalPageCount / rowsPerPage));
    if (required === count) return count;
    count = required;
  }
  throw new Error('Sheet Index page count did not converge');
}

function alphaSuffix(ordinal: number): string {
  let result = '';
  let value = Math.max(1, ordinal);
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(97 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function nextIndexCode(baseCode: string, ordinal: number, used: Set<string>): string {
  const base = cleanText(baseCode) || 'EMS 2.0';
  let candidateOrdinal = Math.max(1, ordinal);
  while (true) {
    const candidate = `${base}${alphaSuffix(candidateOrdinal)}`;
    const key = candidate.toLowerCase();
    if (!used.has(key)) {
      used.add(key);
      return candidate;
    }
    candidateOrdinal += 1;
  }
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
  if (page.pageType === 'pdf') return 'PDF / Layout';
  if (hay.includes('schematic') || hay.includes('wiring diagram')) return 'PDF / Layout';
  if (
    page.pageType === 'canvas'
    || page.pageType === 'image'
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
 * Canonical package arrangement plus the automatic managed Sheet Index.
 *
 * The project-level result is deliberately explicit about archived pages. A
 * Sheet Index continuation can contain historical overlays, so a threshold
 * decrease must move it to recovery data rather than silently discarding it.
 * When the threshold grows again, the same continuation ordinal is revived
 * with its stable page ID and content. This mirrors core/standalone_project.py
 * before the debounced server save has a chance to respond.
 */
export function normalizePackageManifest(
  input: PageModel[],
  archivedInput: PageModel[] = [],
  options: PackageNormalizationOptions = {},
): NormalizedPackageManifest {
  const timestamp = cleanText(options.now) || new Date().toISOString();
  const ordered = keepContinuationsWithBase(stableOrder(input ?? []));
  const coverSource = ordered.find(isCoverPage);
  const indexSource = ordered.find(
    (page) => isSheetIndexPage(page) && !isGeneratedIndexContinuation(page),
  );
  // With no valid base index, keep malformed/orphan continuations visible so
  // validation can report them; never silently consume user data.
  const existingIndexContinuations = indexSource
    ? ordered.filter(isGeneratedIndexContinuation)
    : [];
  const reserved = new Set([
    coverSource?.id,
    indexSource?.id,
    ...existingIndexContinuations.map((page) => page.id),
  ].filter(Boolean) as string[]);
  const remaining = ordered.filter((page) => !reserved.has(page.id));
  const cover = coverSource
    ? {
      ...coverSource,
      include: options.coverIncluded ?? coverSource.include,
    }
    : undefined;

  let index = indexSource;
  if (index) {
    const code = inferIndexCode(cover, index);
    index = {
      ...index,
      include: true,
      pageType: 'index',
      renderMode: 'generated_index',
      normalizedHeaderStyle: 'orange',
      sheetCode: code,
      displaySheetCode: code,
      sheetTitle: cleanText(index.sheetTitle).replace(/\s*[—-]\s*CONTINUED\s*$/i, '') || 'Sheet Index / TOC',
      sheetTab: cleanText(index.sheetTab) || 'Sheet Index',
    };
  }

  let archivedPages = (archivedInput ?? []).map((page) => ({ ...page }));
  let managedContinuations: PageModel[] = existingIndexContinuations;
  const automaticIndex = Boolean(index && (
    options.automaticManagedPages
    ?? (index.managedPage === 'index' && index.appManaged !== false)
  ));

  if (index && automaticIndex) {
    const rowsPerPage = validatedRowsPerPage(options.indexRowsPerPage, index.indexRowsPerPage);
    const baseIncludedCount = [cover, index, ...remaining]
      .filter((page): page is PageModel => Boolean(page))
      .filter((page) => page.include !== false)
      .length;
    const requiredCount = requiredIndexPageCount(baseIncludedCount, rowsPerPage);
    const requiredContinuationCount = requiredCount - 1;
    const usedCodes = new Set(
      [cover, index, ...remaining]
        .filter((page): page is PageModel => Boolean(page))
        .map((page) => currentCode(page).toLowerCase())
        .filter(Boolean),
    );
    const usedIds = new Set(
      [cover, index, ...remaining, ...archivedPages]
        .filter((page): page is PageModel => Boolean(page))
        .map((page) => cleanText(page.id))
        .filter(Boolean),
    );
    const baseId = index.id;
    const baseCode = currentCode(index) || 'EMS 2.0';
    const nextContinuations: PageModel[] = [];

    for (let ordinal = 1; ordinal <= requiredContinuationCount; ordinal += 1) {
      let revived = false;
      let page = existingIndexContinuations[ordinal - 1];
      if (!page) {
        const archivedPosition = archivedPages.findIndex(
          (candidate) => isGeneratedIndexContinuation(candidate)
            && cleanText(candidate.continuationOf || candidate.pageGroupId) === baseId
            && Number(candidate.continuationIndex || 0) === ordinal,
        );
        if (archivedPosition >= 0) {
          [page] = archivedPages.splice(archivedPosition, 1);
          usedIds.delete(cleanText(page.id));
          revived = true;
        }
      }

      let pageId = cleanText(page?.id);
      if (!pageId || usedIds.has(pageId)) {
        pageId = `${baseId}__index_cont_${ordinal}`;
        let discriminator = 2;
        while (usedIds.has(pageId)) {
          pageId = `${baseId}__index_cont_${ordinal}_${discriminator}`;
          discriminator += 1;
        }
      }
      usedIds.add(pageId);

      const existingCode = currentCode(page);
      const code = existingCode && !usedCodes.has(existingCode.toLowerCase())
        ? existingCode
        : nextIndexCode(baseCode, ordinal, usedCodes);
      usedCodes.add(code.toLowerCase());

      const continuation: PageModel = {
        ...(page ?? {
          id: pageId,
          order: 0,
          include: true,
          sheetCode: code,
          sheetTitle: '',
          sheetTab: index.sheetTab,
          pageType: 'index',
          templateId: index.templateId,
          canvasObjects: [],
          blocks: [],
          notes: 'Generated automatically from the current included drawing set.',
          createdAt: timestamp,
        }),
        id: pageId,
        include: true,
        sheetCode: code,
        displaySheetCode: code,
        sheetTitle: `${index.sheetTitle} — CONTINUED`,
        sheetTab: index.sheetTab,
        pageType: 'index',
        pageFamily: 'index',
        renderMode: 'generated_index',
        normalizedHeaderStyle: 'orange',
        templateId: index.templateId,
        managedPage: 'index',
        appManaged: true,
        standaloneIndex: true,
        pageGroupId: baseId,
        continuationOf: baseId,
        continuationIndex: ordinal,
        generatedContinuation: true,
        indexContinuation: true,
        generatedIndexContinuation: true,
        indexRowsPerPage: rowsPerPage,
        indexPageCount: requiredCount,
      };
      if (revived) {
        continuation.lastArchivedAt = continuation.archivedAt;
        continuation.lastArchivedReason = continuation.archivedReason;
        continuation.lastArchivedFromIndex = continuation.archivedFromIndex;
        delete continuation.archivedAt;
        delete continuation.archivedReason;
        delete continuation.archivedFromIndex;
        continuation.restoredAt = timestamp;
      }
      nextContinuations.push(continuation);
    }

    const archivedIds = new Set(archivedPages.map((page) => cleanText(page.id)));
    for (const surplus of existingIndexContinuations.slice(requiredContinuationCount)) {
      if (archivedIds.has(cleanText(surplus.id))) continue;
      archivedPages.push({
        ...surplus,
        include: false,
        archivedAt: timestamp,
        archivedReason: RETIRED_INDEX_REASON,
        archivedFromIndex: Number.isFinite(surplus.archivedFromIndex)
          ? surplus.archivedFromIndex
          : Number(surplus.order || 0) - 1,
      });
      archivedIds.add(cleanText(surplus.id));
    }

    managedContinuations = nextContinuations;
    const totalIncluded = [cover, index, ...managedContinuations, ...remaining]
      .filter((page): page is PageModel => Boolean(page))
      .filter((page) => page.include !== false)
      .length;
    [index, ...managedContinuations].forEach((page, continuationIndex) => {
      const start = continuationIndex * rowsPerPage;
      page.indexRowsPerPage = rowsPerPage;
      page.indexRowsOnPage = Math.max(0, Math.min(rowsPerPage, totalIncluded - start));
      page.indexPageCount = requiredCount;
    });
  }

  let arranged: PageModel[] = [];
  // A hidden Cover remains first in editor order, but is absent from Page X of
  // Y, generated index rows, and export until explicitly included again.
  if (cover) arranged.push(cover);
  if (index) arranged.push(index, ...managedContinuations);
  arranged.push(...remaining);
  if (!cover && !index) arranged = [...remaining];

  const total = arranged.filter((page) => page.include !== false).length;
  let pageNumber = 0;
  const pages = arranged.map((page, indexPosition) => {
    if (page.include === false) {
      return { ...page, order: indexPosition + 1, pageNumber: null, pageTotal: total };
    }
    pageNumber += 1;
    return { ...page, order: indexPosition + 1, pageNumber, pageTotal: total };
  });
  return { pages, archivedPages };
}

/**
 * Backward-compatible pages-only package normalizer.
 *
 * A pages-only caller has nowhere recoverable to put a retired continuation.
 * Keep that transition page excluded at the tail until the project-level
 * normalizer receives it; this prevents older `withPageNumbers(...)` call
 * sites from dropping overlays before `setProjectSync` can move the page into
 * archivedPages. The project-level result never exposes this staging state.
 */
export function normalizePackagePages(input: PageModel[]): PageModel[] {
  const normalized = normalizePackageManifest(input);
  if (!normalized.archivedPages.length) return normalized.pages;
  const total = normalized.pages.filter((page) => page.include !== false).length;
  return [
    ...normalized.pages,
    ...normalized.archivedPages.map((page, position) => ({
      ...page,
      include: false,
      archivedAt: undefined,
      archivedReason: undefined,
      order: normalized.pages.length + position + 1,
      pageNumber: null,
      pageTotal: total,
    })),
  ];
}
