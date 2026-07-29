import type { PageBlock, PageModel } from './types';

type ExtensiblePage = PageModel & Record<string, unknown>;

function detachBlockFromWorksheet(block: PageBlock): PageBlock {
  const detached = structuredClone(block);
  delete detached.sourceWorksheetId;
  delete detached.sourceSheet;
  delete detached.sourceRange;
  return detached;
}

/**
 * Clone a drawing page without cloning its workbook identity.
 *
 * The server assigns a unique local worksheet/tab and 00_INDEX row when this
 * app-managed page is next saved. Canvas objects and other drawing content are
 * deliberately retained verbatim.
 */
export function duplicateAsAppManagedPage(source: PageModel, newId: string): PageModel {
  const detached = structuredClone(source) as ExtensiblePage;

  delete detached.linkedWorksheetId;
  delete detached.parentPageId;
  delete detached.continuationIndex;
  delete detached.recipeWorksheetId;
  delete detached.indexContinuation;
  delete detached.generatedIndexContinuation;

  return {
    ...detached,
    id: newId,
    order: source.order + 0.5,
    sheetTitle: `${source.sheetTitle} Copy`,
    sheetTab: '',
    sourceMode: 'app',
    syncDirection: 'app_to_workbook',
    sourceSheet: '',
    sourceRange: '',
    printArea: null,
    blocks: detached.blocks?.map(detachBlockFromWorksheet),
    pageGroupId: newId,
    continuationOf: null,
    generatedContinuation: false,
    recipeOnly: false,
  } as PageModel;
}
