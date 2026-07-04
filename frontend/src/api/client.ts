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
}

export interface LibraryData {
  components: LibraryComponent[];
  categories: Array<{ id: string; count: number }>;
  connectorStyles: Array<Record<string, unknown>>;
  symbols: Array<Record<string, unknown>>;
  statusCounts?: Record<string, number>;
  paths?: { root: string; inbox: string; components: string; referencePages: string; thumbnails: string };
}

export function libraryAssetUrl(path: string): string {
  return `/api/library/assets/${path.replace(/^\/+/, '')}`;
}

export async function getLibrary(): Promise<LibraryData> {
  const res = await fetch('/api/library');
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rescanLibraryInbox(): Promise<{ ok: boolean; added: number; duplicates: number }> {
  const res = await fetch('/api/library/rescan-inbox', { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function rescanLibraryAssets(): Promise<{ ok: boolean; added: number }> {
  const res = await fetch('/api/library/rescan-library', { method: 'POST' });
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

export async function deleteLibraryComponent(id: string): Promise<void> {
  const res = await fetch(`/api/library/components/${id}?confirm=1`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
}

