import type { PageBlock, PageModel } from './types';
import { assignFreshCanvasObjectIds } from './canvasObjectIdentity';
import { freshAnnotationObjects } from './annotations';

type ExtensiblePage = PageModel & Record<string, unknown>;

const TEMPLATE_PAGE_IDENTITY_KEYS = [
  'id',
  'order',
  'include',
  'sheetCode',
  'displaySheetCode',
  'sheetTab',
  'linkedWorksheetId',
  'pageGroupId',
  'continuationOf',
  'continuationIndex',
  'generatedContinuation',
  'parentPageId',
  'recipeWorksheetId',
  'indexContinuation',
  'generatedIndexContinuation',
  'pageNumber',
  'pageTotal',
  'sourceRevision',
  'sourceImport',
  'importedFrom',
  'layoutWarnings',
  'archivedAt',
  'archivedReason',
  'archivedFromIndex',
  'archivedPreviousPageId',
  'archivedNextPageId',
  'archivedInclude',
  'archivedGroupRootId',
  'lastArchivedAt',
  'lastArchivedReason',
  'lastArchivedFromIndex',
  'lastArchivedGroupRootId',
  'restoredAt',
  'managedPage',
  'renderMode',
  'sourceSheet',
  'sourceRange',
  'printArea',
  'createdAt',
  'modifiedAt',
] as const;

const NESTED_SOURCE_IDENTITY_KEYS = new Set([
  'sourceWorksheetId',
  'sourceSheet',
  'sourceRange',
  'linkedWorksheetId',
  'recipeWorksheetId',
  'pdfSource',
  'pdfSourceId',
  'pdfImportId',
  'pdfImportGroupId',
  'pdfPageFingerprint',
  'pdfBase',
]);

function detachNestedSourceIdentity(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(detachNestedSourceIdentity);
  if (!value || typeof value !== 'object') return value;

  const output: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (!NESTED_SOURCE_IDENTITY_KEYS.has(key)) {
      output[key] = detachNestedSourceIdentity(item);
    }
  }
  return output;
}

function freshCanvasObjects(objects: Record<string, unknown>[] | undefined): Record<string, unknown>[] {
  return (objects ?? []).map((object) => assignFreshCanvasObjectIds(object));
}

function detachBlockFromWorksheet(block: PageBlock): PageBlock {
  const detached = detachNestedSourceIdentity(structuredClone(block)) as PageBlock;
  delete detached.sourceWorksheetId;
  delete detached.sourceSheet;
  delete detached.sourceRange;
  return detached;
}

/**
 * Produce the project-independent payload stored by Save Page as Template.
 * The source page is never mutated. Visual content and stable component/library
 * IDs remain intact, while project/import/worksheet provenance is removed.
 */
export function preparePageTemplatePayload(source: PageModel): PageModel {
  const detached = structuredClone(source) as ExtensiblePage;
  for (const key of TEMPLATE_PAGE_IDENTITY_KEYS) delete detached[key];

  detached.blocks = (detached.blocks ?? []).map(detachBlockFromWorksheet);
  detached.canvasObjects = detachNestedSourceIdentity(
    detached.canvasObjects ?? [],
  ) as Array<Record<string, unknown>>;
  return detached as PageModel;
}

/** Create an independent page instance from a stored reusable template. */
export function instantiatePageTemplate(
  source: PageModel,
  newId: string,
  sheetTitle?: string,
): PageModel {
  const detached = preparePageTemplatePayload(source) as ExtensiblePage;
  const canvasObjects = freshCanvasObjects(detached.canvasObjects);
  const annotationObjects = freshAnnotationObjects(detached.annotationObjects);

  return {
    ...detached,
    id: newId,
    order: 0,
    include: true,
    sheetCode: 'NEW',
    displaySheetCode: 'NEW',
    sheetTitle: sheetTitle || detached.sheetTitle || 'From Template',
    sheetTab: '',
    sourceMode: 'app',
    syncDirection: 'none',
    blocks: (detached.blocks ?? []).map(detachBlockFromWorksheet),
    canvasObjects,
    annotationObjects,
    pageGroupId: newId,
    continuationOf: null,
    generatedContinuation: false,
  } as PageModel;
}

/**
 * Clone a drawing page without cloning its workbook identity.
 *
 * Drawing content is retained while workbook/source identity is detached and
 * every serialized Fabric object (including group children) receives a fresh
 * local objectId so edits to the copy cannot collide with the source page.
 */
export function duplicateAsAppManagedPage(source: PageModel, newId: string): PageModel {
  const detached = structuredClone(source) as ExtensiblePage;
  const duplicatedPdf = detached.pageType === 'pdf'
    || (detached.sourceImport as PageModel['sourceImport'] | undefined)?.type === 'pdf';

  delete detached.linkedWorksheetId;
  delete detached.parentPageId;
  delete detached.continuationIndex;
  delete detached.recipeWorksheetId;
  delete detached.indexContinuation;
  delete detached.generatedIndexContinuation;
  delete detached.archivedAt;
  delete detached.archivedReason;
  delete detached.archivedFromIndex;
  delete detached.archivedPreviousPageId;
  delete detached.archivedNextPageId;
  delete detached.archivedInclude;
  delete detached.archivedGroupRootId;
  delete detached.lastArchivedAt;
  delete detached.lastArchivedReason;
  delete detached.lastArchivedFromIndex;
  delete detached.lastArchivedGroupRootId;
  delete detached.restoredAt;
  // A duplicate is a new independent layout page, not another member of the
  // source PDF's managed reimport group. Keep the project-local raster/source
  // references needed to render it, but remove matching/replacement identity.
  delete detached.sourceImport;
  const detachedCanvasObjects = detachNestedSourceIdentity(
    detached.canvasObjects ?? [],
  ) as Array<Record<string, unknown>>;

  return {
    ...detached,
    id: newId,
    order: source.order + 0.5,
    sheetTitle: `${source.sheetTitle} Copy`,
    sheetTab: '',
    sourceMode: 'app',
    syncDirection: 'none',
    sourceSheet: '',
    sourceRange: '',
    printArea: null,
    blocks: detached.blocks?.map(detachBlockFromWorksheet),
    canvasObjects: freshCanvasObjects(detachedCanvasObjects),
    annotationObjects: freshAnnotationObjects(detached.annotationObjects),
    pageType: duplicatedPdf ? 'canvas' : detached.pageType,
    pageGroupId: newId,
    continuationOf: null,
    generatedContinuation: false,
    recipeOnly: false,
  } as PageModel;
}
