#!/usr/bin/env node
/** Runtime contract for the TypeScript package-index normalizer.
 *
 * The frontend intentionally has no JavaScript test runner. Transpile the
 * actual production module with the repository's TypeScript dependency, then
 * exercise it directly so this test cannot drift into a second implementation.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourcePath = path.join(root, 'frontend', 'src', 'model', 'packageIndex.ts');
const pageTemplatesPath = path.join(root, 'frontend', 'src', 'model', 'pageTemplates.ts');
const typescriptPath = path.join(root, 'frontend', 'node_modules', 'typescript', 'lib', 'typescript.js');
const ts = await import(pathToFileURL(typescriptPath).href);

function loadTypescriptModule(modulePath) {
  const transpiled = ts.transpileModule(fs.readFileSync(modulePath, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: modulePath,
    reportDiagnostics: true,
  });
  const errors = (transpiled.diagnostics ?? []).filter(
    (diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error,
  );
  if (errors.length) {
    throw new Error(errors.map((diagnostic) => ts.flattenDiagnosticMessageText(
      diagnostic.messageText,
      '\n',
    )).join('\n'));
  }
  const loaded = { exports: {} };
  new Function('exports', 'module', transpiled.outputText)(loaded.exports, loaded);
  return loaded.exports;
}

const {
  indexPageTypeLabel,
  normalizePackageManifest,
  normalizePackagePages,
} = loadTypescriptModule(sourcePath);
const { templateForPage } = loadTypescriptModule(pageTemplatesPath);

if (process.argv.includes('--normalize-stdin')) {
  const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
  process.stdout.write(JSON.stringify(normalizePackageManifest(
    payload.pages ?? [],
    payload.archivedPages ?? [],
    payload.options ?? {},
  )));
  process.exit(0);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function page(id, code, patch = {}) {
  return {
    id,
    order: 0,
    include: true,
    sheetCode: code,
    displaySheetCode: code,
    sheetTitle: id,
    sheetTab: id,
    pageType: 'canvas',
    templateId: 'ansi-b-standard',
    canvasObjects: [],
    notes: '',
    ...patch,
  };
}

const cover = page('cover', 'EMS 1.0', {
  order: 1,
  include: false,
  pageType: 'cover',
  managedPage: 'cover',
  appManaged: true,
});
const index = page('index', 'EMS 2.0', {
  order: 2,
  pageType: 'index',
  managedPage: 'index',
  appManaged: true,
  renderMode: 'generated_index',
  indexRowsPerPage: 3,
});
const original = [
  cover,
  index,
  page('a', 'EMS 3.0', { order: 3 }),
  page('b', 'EMS 4.0', { order: 4 }),
  page('c', 'EMS 5.0', { order: 5 }),
];

const expanded = normalizePackageManifest(original, [], {
  now: '2026-08-01T12:00:00Z',
  indexRowsPerPage: 3,
});
assert(
  expanded.pages.map((candidate) => candidate.id).join(',') === 'cover,index,index__index_cont_1,a,b,c',
  'threshold growth must insert one deterministic managed continuation directly after the base index',
);
assert(expanded.pages[0].include === false && expanded.pages[0].pageNumber === null, 'an explicitly hidden Cover must remain hidden and unnumbered');
assert(expanded.pages[1].pageNumber === 1 && expanded.pages[2].pageNumber === 2, 'included index pages must participate in immediate Page X of Y');
assert(expanded.pages.every((candidate) => candidate.pageTotal === 5), 'Page X of Y total must exclude the hidden Cover');
assert(expanded.pages[1].indexRowsOnPage === 3, 'base index must receive the first exact row chunk');
assert(expanded.pages[2].indexRowsOnPage === 2, 'continuation index must receive the remaining exact rows');
assert(expanded.pages[2].sheetCode === 'EMS 2.0a', 'first managed continuation code must match server suffixing');

const withOverlay = expanded.pages.map((candidate) => candidate.id === 'index__index_cont_1'
  ? { ...candidate, canvasObjects: [{ id: 'preserved-overlay' }] }
  : candidate);
const shrunken = normalizePackageManifest(
  withOverlay.map((candidate) => ['b', 'c'].includes(candidate.id)
    ? { ...candidate, include: false }
    : candidate),
  [],
  { now: '2026-08-01T12:01:00Z', indexRowsPerPage: 3 },
);
assert(!shrunken.pages.some((candidate) => candidate.id === 'index__index_cont_1'), 'threshold shrink must remove the surplus continuation from active pages immediately');
assert(shrunken.archivedPages.length === 1, 'threshold shrink must recoverably archive exactly one continuation');
assert(shrunken.archivedPages[0].canvasObjects[0].id === 'preserved-overlay', 'archiving must preserve unexpected continuation overlays');
assert(shrunken.archivedPages[0].archivedReason === 'App-managed Sheet Index continuation no longer required.', 'archive reason must match the server contract');
const stagedPagesOnly = normalizePackagePages(
  withOverlay.map((candidate) => ['b', 'c'].includes(candidate.id)
    ? { ...candidate, include: false }
    : candidate),
);
const stagedRetirement = stagedPagesOnly.find((candidate) => candidate.id === 'index__index_cont_1');
assert(stagedRetirement?.include === false, 'pages-only compatibility must stage a surplus continuation as excluded');
assert(stagedRetirement?.canvasObjects?.[0]?.id === 'preserved-overlay', 'pages-only compatibility must not drop retirement content before project normalization');
const stagedProjectResult = normalizePackageManifest(stagedPagesOnly, [], {
  now: '2026-08-01T12:01:00Z',
  indexRowsPerPage: 3,
  automaticManagedPages: true,
});
assert(!stagedProjectResult.pages.some((candidate) => candidate.id === 'index__index_cont_1'), 'project normalization must consume the pages-only retirement staging state');
assert(stagedProjectResult.archivedPages[0].archivedFromIndex === 2, 'staging must preserve the continuation original package position');
assert(stagedProjectResult.archivedPages[0].archivedAt === '2026-08-01T12:01:00Z', 'project normalization must author the archive timestamp');

const revived = normalizePackageManifest(
  shrunken.pages.map((candidate) => ['b', 'c'].includes(candidate.id)
    ? { ...candidate, include: true }
    : candidate),
  shrunken.archivedPages,
  { now: '2026-08-01T12:02:00Z', indexRowsPerPage: 3 },
);
const revivedContinuation = revived.pages.find((candidate) => candidate.continuationIndex === 1);
assert(revived.archivedPages.length === 0, 'threshold growth must remove the revived continuation from recovery data');
assert(revivedContinuation?.id === 'index__index_cont_1', 'threshold growth must restore the stable continuation page ID');
assert(revivedContinuation?.canvasObjects?.[0]?.id === 'preserved-overlay', 'threshold growth must restore continuation content');
assert(revivedContinuation?.lastArchivedAt === '2026-08-01T12:01:00Z', 'revival must retain archive history');
assert(revivedContinuation?.restoredAt === '2026-08-01T12:02:00Z', 'revival must record the exact restore timestamp');

const manyUsers = Array.from({ length: 28 }, (_, indexPosition) => page(
  `user-${indexPosition + 1}`,
  `EMS ${indexPosition + 3}.0`,
  { order: indexPosition + 3 },
));
const many = normalizePackageManifest(
  [{ ...cover, include: false }, { ...index, indexRowsPerPage: 2 }, ...manyUsers],
  [],
  { now: '2026-08-01T12:03:00Z', indexRowsPerPage: 2 },
);
const ordinal27 = many.pages.find((candidate) => candidate.continuationIndex === 27);
assert(ordinal27?.sheetCode === 'EMS 2.0aa', 'continuation suffixes must remain deterministic beyond z');
assert(many.pages.filter((candidate) => candidate.managedPage === 'index').length === 28, 'fixed-point pagination must count index continuations as physical rows');

const legacy = normalizePackagePages([
  page('legacy-index', 'EMS 2.0', { order: 1, pageType: 'index' }),
  ...Array.from({ length: 60 }, (_, position) => page(`legacy-${position}`, `L ${position}`, { order: position + 2 })),
]);
assert(legacy.filter((candidate) => candidate.generatedIndexContinuation).length === 0, 'unmanaged legacy indexes must not gain a second component system');

const orphan = page('orphan-index-continuation', 'EMS 2.0a', {
  order: 1,
  pageType: 'index',
  generatedContinuation: true,
  generatedIndexContinuation: true,
  continuationOf: 'missing-index',
});
assert(normalizePackagePages([orphan])[0]?.id === orphan.id, 'orphaned continuation data must remain visible for validation');

const importedPdf = page('imported-pdf', 'PDF 1', { pageType: 'pdf' });
const importedImage = page('imported-image', 'IMG 1', { pageType: 'image' });
assert(indexPageTypeLabel(importedPdf) === 'PDF / Layout', 'an imported PDF page must be labeled PDF / Layout in the automatic Sheet Index');
assert(indexPageTypeLabel(importedImage) === 'Image / Layout', 'an imported image page must be labeled Image / Layout in the automatic Sheet Index');
assert(templateForPage(importedPdf) === 'Image / Layout', 'an imported PDF page must use the non-destructive Image / Layout editor classification');
assert(templateForPage(importedImage) === 'Image / Layout', 'an imported image page must use the Image / Layout editor classification');

console.log('PASS: client Sheet Index pagination, imported page labels, cover hide, archive/revive, stable IDs, suffixes, and Page X of Y');
