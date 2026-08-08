import type { PageModel, ProjectModel } from './types';

type ExtensibleProject = ProjectModel & {
  assets?: Record<string, unknown>[];
};

const USER_PAGE_FIELDS: Array<keyof PageModel> = [
  'order',
  'restorePackageIndex',
  'include',
  'publishStatus',
  'issueStatus',
  'statusUpdatedAt',
  'statusConfirmedAt',
  'sheetCode',
  'displaySheetCode',
  'sheetTitle',
  'sheetTab',
  'canvasObjects',
  'annotationObjects',
  'annotationSettings',
  'notes',
  'createdAt',
];

function mergeRecordsById(
  authoritative: Record<string, unknown>[] | undefined,
  latest: Record<string, unknown>[] | undefined,
): Record<string, unknown>[] {
  const merged = [...(authoritative ?? [])];
  const known = new Set(merged.map((item) => String(item.id ?? item.path ?? item.url ?? '')));
  for (const item of latest ?? []) {
    const key = String(item.id ?? item.path ?? item.url ?? '');
    if (!key || !known.has(key)) {
      merged.push(item);
      if (key) known.add(key);
    }
  }
  return merged;
}

function mergeUserPageFields(authoritative: PageModel, latest: PageModel): PageModel {
  const merged = { ...authoritative } as PageModel;
  const mergedRecord = merged as unknown as Record<string, unknown>;
  const latestRecord = latest as unknown as Record<string, unknown>;
  for (const field of USER_PAGE_FIELDS) {
    if (latestRecord[field] !== undefined) mergedRecord[field] = latestRecord[field];
  }
  return merged;
}

function mergeReplacedPdfPage(authoritative: PageModel, latest: PageModel): PageModel {
  const merged = mergeUserPageFields(authoritative, latest);
  const authoritativeBase = (authoritative.canvasObjects ?? []).find(
    (object) => object.pdfBase === true,
  );
  if (!authoritativeBase) return merged;

  let baseReplaced = false;
  const objects = (latest.canvasObjects ?? []).map((object) => {
    const sameObject = String(object.objectId ?? '') !== ''
      && object.objectId === authoritativeBase.objectId;
    const sameGroup = object.pdfBase === true
      && object.pdfImportGroupId === authoritativeBase.pdfImportGroupId;
    if (!sameObject && !sameGroup) return object;
    baseReplaced = true;
    return authoritativeBase;
  });
  if (!baseReplaced) objects.unshift(authoritativeBase);
  merged.canvasObjects = objects;
  return merged;
}

/**
 * Reconcile a completed server PDF job with the newest in-browser project.
 * The server owns installed PDF sources/assets and the revised PDF base object;
 * the browser owns edits made while the job was running. Stable page IDs,
 * metadata, overlays, components, and concurrent new pages are retained.
 */
export function reconcilePdfImportResult(
  latestProject: ProjectModel,
  importedProject: ProjectModel,
  affectedPageIds: string[],
): ProjectModel {
  if (latestProject.id !== importedProject.id) {
    throw new Error('The PDF import completed for a project that is no longer open.');
  }
  const affected = new Set(affectedPageIds);
  const latestById = new Map(latestProject.pages.map((page) => [page.id, page]));
  const importedIds = new Set(importedProject.pages.map((page) => page.id));
  const pages = importedProject.pages.map((page) => {
    const latest = latestById.get(page.id);
    if (!latest) return page;
    return affected.has(page.id) ? mergeReplacedPdfPage(page, latest) : latest;
  });
  for (const page of latestProject.pages) {
    if (!importedIds.has(page.id) && !affected.has(page.id)) pages.push(page);
  }

  const latest = latestProject as ExtensibleProject;
  const imported = importedProject as ExtensibleProject;
  return {
    ...latestProject,
    pages,
    archivedPages: importedProject.archivedPages ?? latestProject.archivedPages,
    sources: mergeRecordsById(importedProject.sources, latestProject.sources),
    assets: mergeRecordsById(imported.assets, latest.assets),
    modified: importedProject.modified ?? latestProject.modified,
    lastSavedAt: importedProject.lastSavedAt ?? latestProject.lastSavedAt,
  } as ProjectModel;
}

/**
 * Apply only the server-owned rebuilt worksheet group onto the newest project.
 * This prevents a slow auto-layout request from replacing unrelated edits.
 */
export function reconcileLayoutRebuildResult(
  latestProject: ProjectModel,
  rebuiltProject: ProjectModel,
  targetPageId: string,
  rebuiltPageIds: string[],
): ProjectModel {
  if (latestProject.id !== rebuiltProject.id) {
    throw new Error('The layout rebuild completed for a project that is no longer open.');
  }
  const target = latestProject.pages.find((page) => page.id === targetPageId)
    ?? rebuiltProject.pages.find((page) => page.id === targetPageId);
  const worksheetId = target?.linkedWorksheetId;
  const rootId = target?.pageGroupId || targetPageId;
  const explicit = new Set(rebuiltPageIds);
  const belongsToGroup = (page: PageModel) => (
    explicit.has(page.id)
    || page.id === targetPageId
    || page.continuationOf === targetPageId
    || page.pageGroupId === rootId
    || (!!worksheetId && page.linkedWorksheetId === worksheetId)
  );

  const latestById = new Map(latestProject.pages.map((page) => [page.id, page]));
  const rebuiltIds = new Set(rebuiltProject.pages.map((page) => page.id));
  const pages = rebuiltProject.pages.map((page) => {
    const latest = latestById.get(page.id);
    if (!latest) return page;
    return belongsToGroup(page) ? mergeUserPageFields(page, latest) : latest;
  });
  for (const page of latestProject.pages) {
    if (!rebuiltIds.has(page.id) && !belongsToGroup(page)) pages.push(page);
  }

  return {
    ...latestProject,
    pages,
    archivedPages: rebuiltProject.archivedPages ?? latestProject.archivedPages,
    modified: rebuiltProject.modified ?? latestProject.modified,
    lastSavedAt: rebuiltProject.lastSavedAt ?? latestProject.lastSavedAt,
  };
}
