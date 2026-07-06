import type { ProjectModel, PageModel } from '../model/types';

export interface ProjectListItem {
  id: string;
  projectName: string;
  modified?: string;
  lastSavedAt?: string;
  folder?: string;
  packageFile?: string;
  sourceWorkbook?: string;
  duplicateFolders?: number;
}

export async function listProjects(): Promise<ProjectListItem[]> {
  const res = await fetch('/api/projects');
  const json = await res.json();
  return json.projects ?? [];
}

export async function getDuplicateFolders(id: string): Promise<{ canonicalFolder: string; duplicateFolders: string[] }> {
  const res = await fetch(`/api/projects/${id}/duplicate-folders`);
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return { canonicalFolder: json.canonicalFolder ?? '', duplicateFolders: json.duplicateFolders ?? [] };
}

export async function archiveDuplicateFolders(id: string): Promise<string[]> {
  const res = await fetch(`/api/projects/${id}/archive-duplicate-folders`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.archived ?? [];
}

export async function archiveProject(id: string): Promise<{ archivedTo: string }> {
  const res = await fetch(`/api/projects/${id}/archive`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface WorkspaceResetOptions {
  archiveProjects?: boolean;
  archiveExports?: boolean;
  archiveTmp?: boolean;
  includeLegacyFlatJson?: boolean;
  resetLibrary?: boolean;
  confirmResetLibrary?: boolean;
  dryRun?: boolean;
}

export interface WorkspaceResetResult {
  dryRun: boolean;
  archiveDir: string;
  moved: string[];
  kept: string[];
  notes: string[];
  movedCount: number;
}

export async function resetWorkspace(opts: WorkspaceResetOptions): Promise<WorkspaceResetResult> {
  const res = await fetch('/api/workspace/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createProjectFromWorkbook(file: File): Promise<{ id: string }> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/projects/new', { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface WorksheetPreview {
  sheetName: string;
  rowEstimate: number;
  colEstimate: number;
  detectedPageType: string;
}

export async function previewImportWorksheets(
  projectId: string,
  file: File,
): Promise<{ sheets: WorksheetPreview[]; filename: string }> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`/api/projects/${projectId}/import/workbook-sheet/preview`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function importWorksheets(
  projectId: string,
  file: File,
  sheetNames: string[],
  opts: { insertAfterPageId?: string; templateOverride?: string } = {},
): Promise<{ pagesAdded: number; pageIds: string[]; renumberSuggested: boolean }> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('sheetNames', JSON.stringify(sheetNames));
  if (opts.insertAfterPageId) fd.append('insertAfterPageId', opts.insertAfterPageId);
  if (opts.templateOverride) fd.append('templateOverride', opts.templateOverride);
  const res = await fetch(`/api/projects/${projectId}/import/workbook-sheet`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getProject(id: string): Promise<ProjectModel> {
  const res = await fetch(`/api/projects/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function saveProject(project: ProjectModel): Promise<void> {
  const res = await fetch(`/api/projects/${project.id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(project),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function savePages(projectId: string, pages: PageModel[]): Promise<void> {
  const res = await fetch(`/api/projects/${projectId}/pages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pages }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function exportPdf(projectId: string, paper?: { width: number; height: number }): Promise<Blob> {
  const res = await fetch(`/api/projects/${projectId}/export/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(paper ?? {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export async function uploadAssetDataUrl(
  projectId: string,
  dataUrl: string,
  name: string,
): Promise<{ id: string; name: string; url: string }> {
  const res = await fetch(`/api/projects/${projectId}/assets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataUrl, name }),
  });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.asset;
}

export async function uploadAssetFile(
  projectId: string,
  file: File,
): Promise<{ id: string; name: string; url: string }> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`/api/projects/${projectId}/assets`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.asset;
}

export async function attachCsv(projectId: string, file: File): Promise<void> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`/api/projects/${projectId}/import/csv`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
}

export async function renameProject(projectId: string, name: string): Promise<{ projectFolder?: string; projectDisplayName?: string }> {
  const res = await fetch(`/api/projects/${projectId}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportPackage(projectId: string): Promise<Blob> {
  const res = await fetch(`/api/projects/${projectId}/export/package`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

// ── Backups / recovery ──
export interface ProjectBackup {
  name: string;
  savedAt: string;
  sizeBytes: number;
}

export interface PageSnapshot {
  name: string;
  pageId: string;
  savedAt: string;
  sheetTitle: string;
  sheetCode: string;
  sizeBytes: number;
  counts: {
    canvasObjects?: number;
    connectors?: number;
    tableBlocks?: number;
    tableCells?: number;
  };
}

export async function listProjectBackups(projectId: string): Promise<ProjectBackup[]> {
  const res = await fetch(`/api/projects/${projectId}/backups`);
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.backups ?? [];
}

export async function restoreProjectBackup(projectId: string, name: string): Promise<ProjectModel> {
  const res = await fetch(`/api/projects/${projectId}/restore-backup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.project;
}

export async function listPageSnapshots(projectId: string): Promise<PageSnapshot[]> {
  const res = await fetch(`/api/projects/${projectId}/page-snapshots`);
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.snapshots ?? [];
}

export async function restorePageSnapshot(projectId: string, pageId: string, name: string): Promise<ProjectModel> {
  const res = await fetch(`/api/projects/${projectId}/restore-page-snapshot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pageId, name }),
  });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.project;
}

// ── PDF Page Renderer ──
export interface PdfPageInfo {
  page: number;
  width: number;
  height: number;
  thumbnailDataUrl: string;
}

export async function uploadPdfForThumbnails(
  projectId: string,
  file: File,
): Promise<{ ok: boolean; pdfFile: string; pageCount: number; pages: PdfPageInfo[] }> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`/api/projects/${projectId}/pdf-thumbnails`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function renderPdfPage(
  projectId: string,
  opts: { pdfFile: string; pageIndex: number; quality: string; crop?: { x: number; y: number; w: number; h: number } | null },
): Promise<{ ok: boolean; asset: { id: string; name: string; url: string }; meta: Record<string, unknown> }> {
  const res = await fetch(`/api/projects/${projectId}/render-pdf-page`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── PDF Crop importer (point-accurate, high DPI) ──
export interface PdfPreviewPage {
  page: number;
  widthPt: number;
  heightPt: number;
  widthIn: number;
  heightIn: number;
  rotation: number;
  previewDpi: number;
  previewWidth: number;
  previewHeight: number;
  previewDataUrl: string;
}

export interface PdfCropMeta {
  sourcePdf: string;
  page: number;
  dpi: number;
  cropPoints?: { x0: number; y0: number; x1: number; y1: number };
  cropWidthIn?: number;
  cropHeightIn?: number;
  autocropped?: boolean;
  outputWidth: number;
  outputHeight: number;
}

export async function uploadPdfPreview(
  projectId: string,
  file: File,
): Promise<{ ok: boolean; pdfFile: string; pageCount: number; pages: PdfPreviewPage[] }> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`/api/projects/${projectId}/pdf/upload-preview`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function renderPdfFullPage(
  projectId: string,
  opts: { pdfFile: string; page: number; dpi: number },
): Promise<{ ok: boolean; asset: { id: string; name: string; url: string }; meta: PdfCropMeta }> {
  const res = await fetch(`/api/projects/${projectId}/pdf/render-page`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function renderPdfCrop(
  projectId: string,
  opts: {
    pdfFile: string;
    page: number;
    dpi: number;
    clip: { x0: number; y0: number; x1: number; y1: number };
    autocrop?: boolean;
  },
): Promise<{ ok: boolean; asset: { id: string; name: string; url: string }; meta: PdfCropMeta }> {
  const res = await fetch(`/api/projects/${projectId}/pdf/render-crop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── Component Library ──
export interface LibraryComponent {
  id: string;
  displayName: string;
  shortName?: string;
  category?: string;
  family?: string;
  partNumber?: string;
  aliases?: string[];
  tags?: string[];
  assetKind?: string;
  assetPath?: string;
  thumbnailPath?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  status?: string;
  defaultLabel?: string;
  insertWithLabel?: boolean;
  notes?: string;
  duplicateGroupId?: string;
  isDuplicateCanonical?: boolean;
  sha256?: string;
  perceptualHash?: string;
  width?: number;
  height?: number;
  aspectRatio?: number;
  fileSize?: number;
  sourceQuality?: string;
  missing?: boolean;
  renameAssetFile?: boolean;
  source?: {
    sourceType?: string;
    sourceFile?: string;
    sourceLocation?: string;
    sourceName?: string;
  };
}

export interface LibraryData {
  components: LibraryComponent[];
  categories: Array<{ id: string; count: number }>;
  connectorStyles: Array<Record<string, unknown>>;
  symbols: Array<Record<string, unknown>>;
  statusCounts?: Record<string, number>;
  paths?: { root: string; libraryRoot?: string; inbox: string; components: string; referencePages: string; thumbnails: string };
}

export function libraryAssetUrl(path: string): string {
  return `/api/library/assets/${path.replace(/^\/+/, '')}`;
}

export function libraryComponentAssetUrl(id: string): string {
  return `/api/library/asset/${encodeURIComponent(id)}`;
}

export function libraryComponentThumbnailUrl(id: string): string {
  return `/api/library/thumbnail/${encodeURIComponent(id)}`;
}

export async function getLibrary(): Promise<LibraryData> {
  const res = await fetch('/api/library');
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getLibraryRoot(): Promise<{ ok: boolean; path: string }> {
  const res = await fetch('/api/library/root');
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function setLibraryRoot(path: string): Promise<{ ok: boolean; path: string; mode?: string }> {
  const res = await fetch('/api/library/root', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function refreshLibraryFromRoot(opts?: { dryRun?: boolean; resetClean?: boolean }): Promise<{
  ok: boolean;
  scanned: number;
  added: number;
  updated: number;
  skippedDuplicates: number;
  pdfConverted: number;
  needsReview: number;
  archivedOldEntries: number;
}> {
  const res = await fetch('/api/library/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rescanLibraryInbox(): Promise<{ ok: boolean; added: number; duplicates: number }> {
  const res = await fetch('/api/library/rescan-inbox', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rescanLibraryAssets(): Promise<{ ok: boolean; added: number; updated?: number; missing?: number }> {
  const res = await fetch('/api/library/rescan-library', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function importLocalLibraryFolder(opts: {
  path: string;
  dryRun?: boolean;
  resetClean?: boolean;
  sourceName?: string;
}): Promise<{
  ok: boolean;
  scanned: number;
  added: number;
  updated: number;
  skippedDuplicates: number;
  pdfConverted: number;
  needsReview: number;
  archivedOldEntries: number;
  categories: Record<string, number>;
  errors: string[];
  dryRun?: boolean;
}> {
  const res = await fetch('/api/library/import-local-folder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function syncLibraryNamesFromFiles(): Promise<{ ok: boolean; changed: number }> {
  const res = await fetch('/api/library/sync-names', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rebuildLibraryThumbnails(): Promise<{ ok: boolean; rebuilt: number; missingBefore: number }> {
  const res = await fetch('/api/library/rebuild-thumbnails', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cleanupLibraryDuplicates(opts?: {
  dryRun?: boolean;
  archiveDuplicates?: boolean;
  dedupeCategory?: string;
  dedupeAll?: boolean;
}): Promise<{
  ok: boolean;
  groups: number;
  nearGroups: number;
  kept: number;
  archived: number;
  archivePath?: string;
}> {
  const res = await fetch('/api/library/cleanup-duplicates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function archiveDirtyExtractedAssets(): Promise<{ ok: boolean; archived: number }> {
  const res = await fetch('/api/library/archive-dirty', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function importLibrarySeed(): Promise<{ ok: boolean; componentCount?: number; filesCopied?: number; error?: string }> {
  const res = await fetch('/api/library/import-seed', { method: 'POST' });
  return res.json();
}

export async function autoCategorizeLibrary(): Promise<{ ok: boolean; changed: number; total: number }> {
  const res = await fetch('/api/library/auto-categorize', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface RdmImportResult {
  ok: boolean;
  scanned: number;
  added: number;
  skippedDuplicates: number;
  updated: number;
  needsReview: number;
  categories: Record<string, number>;
  errors: string[];
  dryRun?: boolean;
  preview?: Array<{ file: string; category: string; displayName: string; action: string }>;
}

export async function importRdmLibraryFolder(opts: {
  path: string;
  dryRun?: boolean;
  sourceName?: string;
  resetRdmImport?: boolean;
  noAutoApprove?: boolean;
}): Promise<RdmImportResult> {
  const res = await fetch('/api/library/import-rdm-folder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function retireLibraryComponent(id: string): Promise<void> {
  const res = await fetch(`/api/library/components/${id}/retire`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
}

export async function restoreLibraryComponent(id: string): Promise<void> {
  const res = await fetch(`/api/library/components/${id}/restore`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
}

export async function updateLibraryComponent(id: string, patch: Partial<LibraryComponent>): Promise<LibraryComponent> {
  const res = await fetch(`/api/library/components/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()).component;
}

export async function bulkUpdateLibraryComponents(ids: string[], patch: Partial<LibraryComponent>): Promise<{ ok: boolean; updated: number }> {
  const res = await fetch('/api/library/components/bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, patch }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function addLibraryComponentFile(
  file: File,
  options: { displayName: string; category: string; partNumber?: string; approve?: boolean },
): Promise<{ ok: boolean; created: boolean; component: LibraryComponent }> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('displayName', options.displayName);
  fd.append('category', options.category);
  if (options.partNumber) fd.append('partNumber', options.partNumber);
  if (options.approve) fd.append('approve', '1');
  const res = await fetch('/api/library/add-component', { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function addLibraryFileToRoot(file: File, category: string, conflictMode: string = 'rename'): Promise<{ ok: boolean; savedTo?: string; duplicate?: boolean; message?: string }> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('category', category);
  fd.append('conflictMode', conflictMode);
  const res = await fetch('/api/library/add-file', { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteLibraryComponent(id: string): Promise<void> {
  const res = await fetch(`/api/library/components/${id}?confirm=1`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
}

// ---------------------------------------------------------------------------
// Component Library V2 (Milestone 4A) — manifest-backed clean library.
// ---------------------------------------------------------------------------
export interface LibV2Port { id: string; x: number; y: number; kind: string }

export interface LibV2Component {
  id: string;
  displayName: string;
  shortName?: string;
  category: string;
  subcategory?: string;
  manufacturer?: string;
  partNumber?: string;
  aliases?: string[];
  searchTerms?: string[];
  sourceFile: string;
  edgeFile?: string;
  bwFile?: string;
  thumbnailFile?: string;
  symbolFile?: string;
  sourceUrl?: string;
  edgeUrl?: string;
  bwUrl?: string;
  symbolUrl?: string;
  thumbnailUrl?: string;
  type?: string;
  defaultLabel?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  labelPosition?: string;
  ports?: LibV2Port[];
  approved?: boolean;
  needsReview?: boolean;
  favorite?: boolean;
  notes?: string;
  hasSource?: boolean;
  hasEdge?: boolean;
  hasBw?: boolean;
  canBwFallback?: boolean;
  hasSymbol?: boolean;
  hasProcedural?: boolean;
  status?: string;
  preferredEdgeVariant?: string;
  edgeVariantOptions?: string[];
  chosenVariant?: string;
  retired?: boolean;
}

export interface LibV2Category { id: string; label: string; count: number }

export interface LibV2Data {
  ok: boolean;
  version: number;
  components: LibV2Component[];
  categories: LibV2Category[];
  hasLegacy?: boolean;
  legacyCount?: number;
  libraryRoot?: string;
  counts: { total: number; favorites: number; needsReview: number; withSymbol?: number; withEdge?: number };
}

export const libV2AssetUrl = (rel: string) => `/api/lib/asset/${rel}`;

export async function getLibV2(includeLegacy: boolean = false): Promise<LibV2Data> {
  const q = includeLegacy ? '?includeLegacy=1' : '';
  const res = await fetch(`/api/lib${q}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function refreshLibV2(): Promise<{ ok: boolean; scanned: number; added: number; skipped: number; duplicates: number }> {
  const res = await fetch('/api/lib/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rebuildLibV2Thumbnails(): Promise<{ ok: boolean; rebuilt: number; missingSource: number }> {
  const res = await fetch('/api/lib/rebuild-thumbnails', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cleanLibV2Duplicates(dryRun: boolean): Promise<{ ok: boolean; duplicates?: number; archived?: number; duplicateGroups?: number }> {
  const res = await fetch('/api/lib/clean-duplicates', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dryRun }) });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function addLibV2File(category: string, file: File): Promise<{ ok: boolean; saved: string }> {
  const fd = new FormData();
  fd.append('category', category);
  fd.append('file', file);
  const res = await fetch('/api/lib/add-file', { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateLibV2Component(id: string, patch: Partial<LibV2Component>): Promise<{ ok: boolean; component: LibV2Component }> {
  const res = await fetch(`/api/lib/components/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function duplicateLibV2Component(id: string): Promise<{ ok: boolean; component: LibV2Component; error?: string }> {
  const res = await fetch(`/api/lib/components/${id}/duplicate`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function replaceLibV2Asset(
  id: string,
  target: 'source' | 'edge' | 'bw',
  file: File,
): Promise<{ ok: boolean; component?: LibV2Component; error?: string }> {
  const fd = new FormData();
  fd.append('target', target);
  fd.append('file', file);
  const res = await fetch(`/api/lib/components/${id}/replace-asset`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function renameLibV2File(id: string): Promise<{ ok: boolean; component?: LibV2Component; error?: string }> {
  const res = await fetch(`/api/lib/components/${id}/rename-file`, { method: 'POST' });
  return res.json();
}

export async function generateLibV2Symbol(id: string): Promise<{ ok: boolean; symbolFile?: string }> {
  const res = await fetch(`/api/lib/components/${id}/symbol`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface MigrateLegacyPreview {
  ok: boolean;
  dryRun?: boolean;
  legacyFound?: number;
  legacyCategories?: Record<string, number>;
  willCopy?: number;
  willSkipDuplicates?: number;
  targetCategories?: Record<string, number>;
  copied?: number;
  note?: string;
}

export async function migrateLegacyLibV2(dryRun: boolean): Promise<MigrateLegacyPreview> {
  const res = await fetch('/api/lib/migrate-legacy', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dryRun, rebuildThumbnails: true, generateSymbols: false }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function generateAllLibV2Symbols(): Promise<{ ok: boolean; generated: number; skipped: number }> {
  const res = await fetch('/api/lib/generate-symbols', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cleanLibV2PhysicalDuplicates(dryRun: boolean): Promise<{ ok: boolean; duplicates?: number; archived?: number; duplicateGroups?: number }> {
  const res = await fetch('/api/lib/clean-physical-duplicates', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dryRun }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

