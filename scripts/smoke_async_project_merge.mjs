#!/usr/bin/env node
/** Runtime proof that delayed server results cannot erase newer editor state. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const typescriptPath = path.join(root, 'frontend', 'node_modules', 'typescript', 'lib', 'typescript.js');
const ts = await import(pathToFileURL(typescriptPath).href);

function loadTypescriptModule(sourcePath) {
  const transpiled = ts.transpileModule(fs.readFileSync(sourcePath, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: sourcePath,
    reportDiagnostics: true,
  });
  const errors = (transpiled.diagnostics ?? []).filter(
    (diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error,
  );
  if (errors.length) throw new Error(errors.map((diagnostic) => ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n')).join('\n'));
  const loaded = { exports: {} };
  new Function('exports', 'module', transpiled.outputText)(loaded.exports, loaded);
  return loaded.exports;
}

const { reconcileLayoutRebuildResult, reconcilePdfImportResult } = loadTypescriptModule(
  path.join(root, 'frontend', 'src', 'model', 'asyncProjectMerge.ts'),
);
const { pdfImportRequestSelection } = loadTypescriptModule(
  path.join(root, 'frontend', 'src', 'model', 'pdfImportSelection.ts'),
);
const { waitForBrowserPaint } = loadTypescriptModule(
  path.join(root, 'frontend', 'src', 'model', 'browserPaint.ts'),
);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function page(id, patch = {}) {
  return {
    id,
    order: 1,
    include: true,
    sheetCode: 'EMS 3.0',
    displaySheetCode: 'EMS 3.0',
    sheetTitle: id,
    sheetTab: id,
    pageType: 'canvas',
    templateId: 'ansi-b-standard',
    blocks: [],
    canvasObjects: [],
    notes: '',
    ...patch,
  };
}

function project(pages, patch = {}) {
  return {
    id: '0123456789abcdef',
    projectMode: 'standalone_layout',
    managedPagePolicy: 'automatic',
    metadata: { projectName: 'Async Merge Fixture' },
    worksheets: [],
    pages,
    archivedPages: [],
    sources: [],
    ...patch,
  };
}

const oldBase = { objectId: 'stable-pdf-base', pdfBase: true, pdfImportGroupId: 'group-1', src: '/old.png' };
const newBase = { ...oldBase, src: '/new.png', pdfSourceId: 'revision-2' };
const overlay = { objectId: 'new-overlay', type: 'textbox', text: 'Edit made during PDF import' };
const latestPdf = project([
  page('pdf-page', {
    order: 3,
    pageType: 'pdf',
    sheetTitle: 'User Renamed Sheet',
    notes: 'Newest notes',
    canvasObjects: [oldBase, overlay],
  }),
  page('concurrent-page', { order: 4, sheetTitle: 'Created During Import' }),
], { sources: [{ id: 'existing-source' }] });
const importedPdf = project([
  page('pdf-page', {
    order: 3,
    pageType: 'pdf',
    sheetTitle: 'Old Saved Sheet',
    sourceImport: { type: 'pdf', sourceId: 'revision-2' },
    canvasObjects: [newBase],
  }),
], {
  sources: [{ id: 'existing-source' }, { id: 'revision-2' }],
  assets: [{ id: 'new-render' }],
  lastSavedAt: '2026-08-01T12:00:00Z',
});
const pdfMerged = reconcilePdfImportResult(latestPdf, importedPdf, ['pdf-page']);
const pdfPage = pdfMerged.pages.find((candidate) => candidate.id === 'pdf-page');
assert(pdfPage.sheetTitle === 'User Renamed Sheet' && pdfPage.notes === 'Newest notes', 'PDF reconciliation lost newer metadata');
assert(pdfPage.canvasObjects.some((object) => object.objectId === 'new-overlay'), 'PDF reconciliation lost the newer overlay');
assert(pdfPage.canvasObjects.find((object) => object.pdfBase)?.src === '/new.png', 'PDF reconciliation did not install the revised base');
assert(pdfMerged.pages.some((candidate) => candidate.id === 'concurrent-page'), 'PDF reconciliation lost a page created during import');
assert(pdfMerged.sources.some((source) => source.id === 'revision-2'), 'PDF reconciliation lost the project-local revised source');

const partialReplacementMapping = [
  { existingPageId: 'existing-1', pageIndex: 0 },
  { existingPageId: 'existing-2', pageIndex: 1 },
];
assert(
  pdfImportRequestSelection('replace', [0, 1, 2], partialReplacementMapping).join(',') === '0,1',
  'partial PDF replacement sent an unmatched selected page instead of only the mapped revised pages',
);
assert(
  pdfImportRequestSelection('add', [0, 1, 2], partialReplacementMapping).join(',') === '0,1,2',
  'Add as New Pages did not retain the complete selected page list',
);

const scheduledFrames = [];
let painted = false;
const paintPromise = waitForBrowserPaint((callback) => {
  scheduledFrames.push(callback);
  return scheduledFrames.length;
}).then(() => { painted = true; });
assert(scheduledFrames.length === 1 && !painted, 'progress paint helper did not wait for its first render frame');
scheduledFrames.shift()(0);
assert(scheduledFrames.length === 1 && !painted, 'progress paint helper resolved before the following paint frame');
scheduledFrames.shift()(16);
await paintPromise;
assert(painted, 'progress paint helper did not resolve after two animation frames');

const latestLayout = project([
  page('worksheet', {
    linkedWorksheetId: 'ws-1',
    pageGroupId: 'worksheet',
    sheetTitle: 'User Title',
    canvasObjects: [{ objectId: 'during-rebuild', type: 'note' }],
    blocks: [{ id: 'old-block', type: 'excelRange' }],
  }),
  page('unrelated', { order: 2, notes: 'Newest unrelated edit' }),
]);
const rebuiltLayout = project([
  page('worksheet', {
    linkedWorksheetId: 'ws-1',
    pageGroupId: 'worksheet',
    sheetTitle: 'Saved Title',
    layoutOverride: 'two_columns',
    blocks: [{ id: 'rebuilt-block', type: 'excelRange' }],
  }),
  page('worksheet-cont', {
    order: 2,
    linkedWorksheetId: 'ws-1',
    pageGroupId: 'worksheet',
    continuationOf: 'worksheet',
    generatedContinuation: true,
    blocks: [{ id: 'continued-block', type: 'excelRange' }],
  }),
  page('unrelated', { order: 3, notes: 'Older unrelated state' }),
]);
const layoutMerged = reconcileLayoutRebuildResult(
  latestLayout,
  rebuiltLayout,
  'worksheet',
  ['worksheet', 'worksheet-cont'],
);
const rebuiltBase = layoutMerged.pages.find((candidate) => candidate.id === 'worksheet');
assert(rebuiltBase.sheetTitle === 'User Title', 'layout reconciliation lost newer page metadata');
assert(rebuiltBase.canvasObjects.some((object) => object.objectId === 'during-rebuild'), 'layout reconciliation lost a concurrent canvas edit');
assert(rebuiltBase.blocks[0].id === 'rebuilt-block' && rebuiltBase.layoutOverride === 'two_columns', 'layout reconciliation lost rebuilt geometry');
assert(layoutMerged.pages.some((candidate) => candidate.id === 'worksheet-cont'), 'layout reconciliation lost the server continuation');
assert(layoutMerged.pages.find((candidate) => candidate.id === 'unrelated').notes === 'Newest unrelated edit', 'layout reconciliation replaced an unrelated edit');

console.log('PASS: delayed PDF imports and layout rebuilds preserve newer editor state; the two-frame progress gate waits for a browser paint');
