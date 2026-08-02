import type { ProjectModel, PageModel, SpreadsheetPageRecipe } from '../model/types';

export class Singh360ApiError extends Error {
  payload: Record<string, unknown>;
  status: number;

  constructor(message: string, status: number, payload: Record<string, unknown>) {
    super(message);
    this.name = 'Singh360ApiError';
    this.status = status;
    this.payload = payload;
  }
}

async function exactApiError(response: Response): Promise<Error> {
  const text = await response.text();
  try {
    const payload = JSON.parse(text) as Record<string, unknown> & { error?: string; detail?: string };
    const message = [payload.error, payload.detail].filter(Boolean).join(' ');
    return new Singh360ApiError(message || `${response.status} ${response.statusText}`, response.status, payload);
  } catch {
    return new Error(text || `${response.status} ${response.statusText}`);
  }
}

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

async function workspaceJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw await exactApiError(response);
  return response.json() as Promise<T>;
}

export interface ProjectFileRecord {
  id: string;
  originalFileName: string;
  storedFileName: string;
  mediaType: string;
  fileType: 'pdf' | 'images' | 'spreadsheets' | 'csv' | 'text' | 'documents' | 'other';
  size: number;
  sha256: string;
  dateAdded: string;
  modifiedAt?: string;
  version: number;
  status: 'active' | 'superseded' | 'archived';
  virtualPath: string;
  relativePath: string;
  localProjectPath: string;
  tags: string[];
  notes: string;
  linked?: boolean;
  physicalPath?: string;
}

export interface ProjectFilesPayload {
  mode?: 'linked' | 'legacy';
  linked?: boolean;
  rootPath?: string;
  rootName?: string;
  folders: string[];
  archivedFolders: Array<{ path: string; restorePath: string; archivedAt: string }>;
  files: ProjectFileRecord[];
  conversionQueue: Array<Record<string, unknown>>;
}

export interface WorkbookDocument {
  revision: number;
  updatedAt: string;
  sheets: Array<{
    id: string;
    name: string;
    cells: Record<string, { v?: unknown; f?: string }>;
    styles: Record<string, Record<string, unknown>>;
    merges: string[];
    /** Explicit Excel row heights in points, keyed by one-based row number. */
    rowHeights: Record<string, number>;
    /** Explicit Excel column widths in OOXML character units, keyed by letters. */
    columnWidths: Record<string, number>;
    defaultColumnWidth: number;
    defaultRowHeight: number;
    /** Workbook visibility uses one-based rows and Excel column letters. */
    hiddenRows: number[];
    hiddenColumns: string[];
    archived?: boolean;
    tabColor?: string | null;
    role?: string | null;
    sourceSetup?: {
      authority?: string;
      sheetCode?: string;
      title?: string;
      pageType?: string;
      publish?: '' | 'YES' | 'NO' | 'VERIFY';
      purpose?: string;
      instruction?: string;
      editableStartRow?: number;
      metadata?: Array<{ field: string; value: string; notes: string }>;
    };
    protectedRanges: string[];
    dataValidations: Array<{
      id: string;
      ranges: string[];
      type: string;
      operator?: string;
      formula1?: unknown;
      formula2?: unknown;
      values?: string[];
      allowBlank?: boolean;
      showDropdown?: boolean;
      showErrorMessage?: boolean;
      error?: string;
      errorTitle?: string;
      strict?: boolean;
      source?: string;
    }>;
    conditionalFormats: Array<Record<string, unknown>>;
    tableRegions: Array<{ id: string; range: string; label: string }>;
    tableLayout: 'single' | 'side_by_side' | 'stacked';
    annotations: Array<{
      id: string;
      text: string;
      placement: 'right' | 'bottom';
    }>;
    pageLayouts: SpreadsheetPageRecipe[];
    workspaceSection?: 'drawing' | 'control' | 'source';
    drawingPageId?: string;
    drawingSheetCode?: string;
    drawingOrder?: number;
    drawingTitle?: string;
    drawingInclude?: boolean;
    drawingPublishStatus?: '' | 'YES' | 'NO' | 'VERIFY';
  }>;
}

export async function listProjectFiles(projectId: string): Promise<ProjectFilesPayload> {
  return workspaceJson(await fetch(`/api/projects/${projectId}/project-files`));
}

export async function uploadProjectFiles(
  projectId: string,
  files: File[],
  virtualPath = '',
): Promise<ProjectFileRecord[]> {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  form.append('virtualPath', virtualPath);
  form.append('relativePaths', JSON.stringify(files.map((file) => file.webkitRelativePath || file.name)));
  form.append('modifiedTimes', JSON.stringify(files.map((file) => file.lastModified)));
  const data = await workspaceJson<{ files: ProjectFileRecord[] }>(
    await fetch(`/api/projects/${projectId}/project-files/upload`, { method: 'POST', body: form }),
  );
  return data.files;
}

export async function importProjectFilesZip(projectId: string, file: File, virtualPath = ''): Promise<void> {
  const form = new FormData();
  form.append('file', file);
  form.append('virtualPath', virtualPath);
  await workspaceJson(await fetch(`/api/projects/${projectId}/project-files/import-zip`, { method: 'POST', body: form }));
}

export async function createProjectFolder(projectId: string, path: string): Promise<void> {
  await workspaceJson(await fetch(`/api/projects/${projectId}/project-folders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  }));
}

export async function updateProjectFolder(
  projectId: string,
  action: 'rename' | 'move' | 'archive' | 'restore',
  path: string,
  value = '',
): Promise<string> {
  const data = await workspaceJson<{ folder: string }>(
    await fetch(`/api/projects/${projectId}/project-folders`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        path,
        ...(action === 'rename' ? { name: value } : {}),
        ...(action === 'move' ? { destination: value } : {}),
      }),
    }),
  );
  return data.folder;
}

export async function updateProjectFile(
  projectId: string,
  fileId: string,
  action: 'rename' | 'move' | 'archive' | 'restore',
  value = '',
): Promise<ProjectFileRecord> {
  const data = await workspaceJson<{ file: ProjectFileRecord }>(
    await fetch(`/api/projects/${projectId}/project-files/${fileId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        ...(action === 'rename' ? { name: value } : {}),
        ...(action === 'move' ? { destination: value } : {}),
      }),
    }),
  );
  return data.file;
}

export async function previewProjectFile(projectId: string, fileId: string): Promise<Record<string, unknown>> {
  return workspaceJson(await fetch(`/api/projects/${projectId}/project-files/${fileId}/preview`));
}

export async function sendProjectFileToData(projectId: string, fileId: string): Promise<WorkbookDocument> {
  const data = await workspaceJson<{ workbook: WorkbookDocument }>(
    await fetch(`/api/projects/${projectId}/project-files/${fileId}/send-to-data`, { method: 'POST' }),
  );
  return data.workbook;
}

export async function openProjectFile(projectId: string, fileId: string): Promise<string> {
  const data = await workspaceJson<{ path: string }>(
    await fetch(`/api/projects/${projectId}/project-files/${fileId}/open`, { method: 'POST' }),
  );
  return data.path;
}

export async function revealProjectFile(projectId: string, fileId: string): Promise<string> {
  const data = await workspaceJson<{ path: string }>(
    await fetch(`/api/projects/${projectId}/project-files/${fileId}/reveal`, { method: 'POST' }),
  );
  return data.path;
}

export async function revealProjectFolder(projectId: string, path: string): Promise<string> {
  const data = await workspaceJson<{ path: string }>(
    await fetch(`/api/projects/${projectId}/project-folders/reveal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }),
  );
  return data.path;
}

export async function getDataWorkspace(projectId: string): Promise<WorkbookDocument> {
  return workspaceJson(await fetch(`/api/projects/${projectId}/data-workspace`));
}

export async function saveDataWorkspace(
  projectId: string,
  document: WorkbookDocument,
  expectedRevision: number,
): Promise<WorkbookDocument> {
  return workspaceJson(await fetch(`/api/projects/${projectId}/data-workspace`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expectedRevision, document }),
  }));
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

export async function deleteProject(id: string): Promise<{ deleted: string[] }> {
  const res = await fetch(`/api/projects/${id}?confirm=true`, { method: 'DELETE' });
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

export interface ContinuationSheetSummary {
  sheetTab: string;
  sheetTitle: string;
  sheetCode: string;
  renderMode: string;
  splitMode: string;
  pages: number;
  message: string;
}

export interface ContinuationSummary {
  sheets: ContinuationSheetSummary[];
  totalPages: number;
  totalSheets: number;
  multiPageSheets: number;
  sourceWorkbookName?: string;
}

export type ProjectProfile = 'ems';

export async function previewWorkbookContinuation(
  file: File,
  profile: ProjectProfile = 'ems',
): Promise<ContinuationSummary> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('profile', profile);
  const res = await fetch('/api/projects/preview-continuation', { method: 'POST', body: fd });
  if (!res.ok) throw await exactApiError(res);
  const json = await res.json();
  return json.continuation as ContinuationSummary;
}

export async function createProjectFromWorkbook(
  file: File,
  projectRoot: string,
  profile: ProjectProfile = 'ems',
): Promise<{ id: string; continuation?: ContinuationSummary }> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('profile', profile);
  fd.append('projectRoot', projectRoot);
  const res = await fetch('/api/projects/new', { method: 'POST', body: fd });
  if (!res.ok) throw await exactApiError(res);
  return res.json();
}

export interface WorksheetPreview {
  sheetName: string;
  rowEstimate: number;
  colEstimate: number;
  detectedPageType: string;
  sheetCode?: string;
  pageTitle?: string;
  listedInIndex?: boolean;
  printArea?: string;
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
  opts: { insertAfterPageId?: string; templateOverride?: string; replacePageId?: string; preserveExact?: boolean } = {},
): Promise<{ pagesAdded: number; pageIds: string[]; renumberSuggested: boolean; replacedPageId?: string }> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('sheetNames', JSON.stringify(sheetNames));
  if (opts.insertAfterPageId) fd.append('insertAfterPageId', opts.insertAfterPageId);
  if (opts.templateOverride) fd.append('templateOverride', opts.templateOverride);
  if (opts.replacePageId) fd.append('replacePageId', opts.replacePageId);
  fd.append('preserveExact', opts.preserveExact === false ? '0' : '1'); // S360 SINGLE FORMATTED SHEET IMPORT V1
  const res = await fetch(`/api/projects/${projectId}/import/workbook-sheet`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface ReimportPlanEntry {
  existingPageId: string;
  candidatePageId: string;
  sheetCode: string;
  candidateSheetCode?: string;
  sheetTitle: string;
  matchedBy: 'sheetCode' | 'sheetTitle' | null;
  classification: 'manual' | 'source';
  hasCanvasObjects: boolean;
}

export interface ReimportPlanAddEntry {
  candidatePageId: string;
  sheetCode: string;
  sheetTitle: string;
}

export interface ReimportPlanArchiveEntry {
  existingPageId: string;
  sheetCode: string;
  sheetTitle: string;
  classification: 'manual' | 'source';
}

export interface ReimportPlan {
  toUpdate: ReimportPlanEntry[];
  toPreserve: ReimportPlanEntry[];
  toAdd: ReimportPlanAddEntry[];
  toArchive: ReimportPlanArchiveEntry[];
  candidateWorksheetCount: number;
}

export interface ReimportSummary {
  updated: string[];
  preserved: string[];
  replacedManual: string[];
  added: string[];
  archived: string[];
}

export async function previewReimportWorkbook(
  projectId: string,
  file: File,
): Promise<{ plan: ReimportPlan; filename: string }> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`/api/projects/${projectId}/reimport/preview`, { method: 'POST', body: fd });
  if (!res.ok) throw await exactApiError(res);
  return res.json();
}

export async function applyReimportWorkbook(
  projectId: string,
  file: File,
  replacePageIds: string[] = [],
): Promise<{ summary: ReimportSummary }> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('replacePageIds', JSON.stringify(replacePageIds));
  const res = await fetch(`/api/projects/${projectId}/reimport`, { method: 'POST', body: fd });
  if (!res.ok) throw await exactApiError(res);
  return res.json();
}

export async function getProject(id: string): Promise<ProjectModel> {
  const res = await fetch(`/api/projects/${id}`);
  if (!res.ok) throw await exactApiError(res);
  return res.json();
}

export async function saveProject(project: ProjectModel): Promise<ProjectModel> {
  const res = await fetch(`/api/projects/${project.id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(project),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<ProjectModel>;
}

export interface PdfDrawingPreviewPage {
  pageIndex: number;
  pageNumber: number;
  widthPoints: number;
  heightPoints: number;
  fingerprint: string;
  thumbnail: string;
}

export interface PdfDrawingPreview {
  previewId: string;
  pdfFile: string;
  originalName: string;
  sha256: string;
  pageCount: number;
  pages: PdfDrawingPreviewPage[];
  existingGroups: Array<{
    groupId: string;
    originalName: string;
    pageIds: string[];
    pageIndices: number[];
    pageFingerprints: string[];
    revision: number;
    sameName: boolean;
  }>;
}

export type PdfDrawingImportPhase = 'validate' | 'render' | 'install' | 'compose' | 'save' | 'complete';

export interface PdfDrawingImportProgress {
  phase: PdfDrawingImportPhase;
  completed: number;
  total: number;
  message: string;
  pageIndex?: number;
  pageNumber?: number;
}

export interface PdfDrawingImportResult {
  project: ProjectModel;
  pageIds: string[];
  replacedPageIds: string[];
  progress: PdfDrawingImportProgress;
}

export async function previewPdfDrawing(projectId: string, file: File): Promise<PdfDrawingPreview> {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(`/api/projects/${projectId}/pdf/import-preview`, { method: 'POST', body });
  if (!response.ok) throw await exactApiError(response);
  return response.json();
}

export async function commitPdfDrawingImport(
  projectId: string,
  options: {
    previewId: string;
    selectedPages: number[];
    placementMode: 'full_sheet' | 'fit_body';
    action: 'add' | 'replace';
    replaceGroupId?: string;
    mapping?: Array<{ existingPageId: string; pageIndex: number }>;
    titlePrefix?: string;
    firstSheetCode?: string;
  },
  onProgress?: (progress: PdfDrawingImportProgress) => void,
): Promise<PdfDrawingImportResult> {
  const initialProgress: PdfDrawingImportProgress = {
    phase: 'validate',
    completed: 0,
    total: options.selectedPages.length,
    message: 'Validating the staged PDF import',
  };
  onProgress?.(initialProgress);
  const response = await fetch(`/api/projects/${projectId}/pdf/import-commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...options, background: true }),
  });
  if (!response.ok) throw await exactApiError(response);
  const started = await response.json() as {
    jobId?: string;
    state?: 'queued' | 'running' | 'succeeded' | 'failed';
    progress?: PdfDrawingImportProgress;
  } & Partial<PdfDrawingImportResult>;
  if (response.status !== 202) return started as PdfDrawingImportResult;
  if (!started.jobId) {
    throw new Singh360ApiError(
      'The PDF import started without a job ID.',
      500,
      { ok: false, code: 'import_job_id_missing', phase: 'validate' },
    );
  }
  if (started.progress) onProgress?.(started.progress);

  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 125));
    const statusResponse = await fetch(`/api/projects/${projectId}/pdf/import-jobs/${started.jobId}`, {
      cache: 'no-store',
    });
    if (!statusResponse.ok) throw await exactApiError(statusResponse);
    const job = await statusResponse.json() as {
      state: 'queued' | 'running' | 'succeeded' | 'failed';
      progress?: PdfDrawingImportProgress;
      result?: PdfDrawingImportResult;
      error?: Record<string, unknown> & { error?: string; detail?: string };
      errorStatus?: number;
    };
    if (job.progress) onProgress?.(job.progress);
    if (job.state === 'succeeded' && job.result) return job.result;
    if (job.state === 'failed') {
      const payload = job.error ?? { ok: false, code: 'pdf_import_failed', phase: 'commit' };
      const message = [payload.error, payload.detail].filter(Boolean).join(' ');
      throw new Singh360ApiError(message || 'PDF import failed.', job.errorStatus || 500, payload);
    }
  }
  throw new Singh360ApiError(
    'The PDF import did not finish within 30 minutes.',
    408,
    { ok: false, code: 'pdf_import_timeout', phase: 'commit' },
  );
}

export async function restoreArchivedProject(projectId: string): Promise<ProjectModel> {
  const response = await fetch(`/api/projects/${projectId}/restore`, { method: 'POST' });
  if (!response.ok) throw await exactApiError(response);
  const payload = await response.json();
  return payload.project as ProjectModel;
}

export async function savePages(projectId: string, pages: PageModel[]): Promise<void> {
  const res = await fetch(`/api/projects/${projectId}/pages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pages }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function fetchExportWarnings(projectId: string, pageIds: string[] = []): Promise<ExportWarning[]> {
  const params = new URLSearchParams();
  pageIds.forEach((pageId) => params.append('pageId', pageId));
  const query = params.toString();
  const res = await fetch(`/api/projects/${projectId}/export/warnings${query ? `?${query}` : ''}`);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.warnings ?? [];
}

export async function exportPdf(
  projectId: string,
  options?: { width: number; height: number; pageIds?: string[]; confirmPreflight?: boolean },
): Promise<Blob> {
  const res = await fetch(`/api/projects/${projectId}/export/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options ?? {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export interface ExportWarning {
  code?: string;
  severity?: string;
  confirmationRequired?: boolean;
  pageCode: string;
  pageTitle: string;
  issue: string;
  suggestedFix: string;
}

export interface PageTemplateEntry {
  id: string;
  name: string;
  createdAt: string;
  pageType: string;
  layoutProfile?: string;
  hasThumbnail?: boolean;
  thumbnailUrl?: string | null;
}

export async function listPageTemplates(): Promise<PageTemplateEntry[]> {
  const res = await fetch('/api/lib/page-templates');
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.templates ?? [];
}

export async function savePageTemplate(
  page: PageModel,
  name: string,
  thumbnailDataUrl?: string,
): Promise<PageTemplateEntry> {
  const res = await fetch('/api/lib/page-templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ page, name, thumbnailDataUrl }),
  });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.template;
}

export async function getPageTemplatePayload(templateId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`/api/lib/page-templates/${templateId}`);
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.template;
}

export async function deletePageTemplate(templateId: string): Promise<void> {
  const res = await fetch(`/api/lib/page-templates/${templateId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
}

export async function renamePageTemplate(templateId: string, name: string): Promise<void> {
  const res = await fetch(`/api/lib/page-templates/${templateId}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export interface LegendTemplateEntry {
  id: string;
  name: string;
  category?: string;
  rowCount?: number;
  updatedAt?: string;
}

export interface LegendTemplatePayload extends LegendTemplateEntry {
  title?: string;
  rows: Record<string, unknown>[];
  columns?: 1 | 2;
  markerSize?: number;
  frame?: boolean;
  highlighted?: boolean;
  rendererVersion?: string;
  layout?: Record<string, unknown>;
}

export async function listLegendTemplates(): Promise<LegendTemplateEntry[]> {
  const res = await fetch('/api/lib/legend-templates');
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.templates ?? [];
}

export async function getLegendTemplate(templateId: string): Promise<LegendTemplatePayload> {
  const res = await fetch(`/api/lib/legend-templates/${encodeURIComponent(templateId)}`);
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.template;
}

export async function saveLegendTemplate(payload: {
  id?: string;
  name: string;
  category?: string;
  title: string;
  rows: Record<string, unknown>[];
}): Promise<LegendTemplateEntry> {
  const res = await fetch('/api/lib/legend-templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.template;
}

export async function deleteLegendTemplate(templateId: string): Promise<void> {
  const res = await fetch(`/api/lib/legend-templates/${templateId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
}

export async function uploadAssetDataUrl(
  projectId: string,
  dataUrl: string,
  name: string,
): Promise<{ id: string; name: string; storedFileName: string; projectLocalPath: string; sha256: string; url: string }> {
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
): Promise<{ id: string; name: string; storedFileName: string; projectLocalPath: string; sha256: string; url: string }> {
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

export async function exportPackage(projectId: string, confirmPreflight = false): Promise<Blob> {
  const res = await fetch(`/api/projects/${projectId}/export/package`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmPreflight }),
  });
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

export async function savePageRebuildBackup(
  projectId: string,
  pageId: string,
  page: PageModel,
): Promise<{ name: string }> {
  const res = await fetch(`/api/projects/${projectId}/page-rebuild-backup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pageId, page }),
  });
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return { name: json.name as string };
}

/** Download the active page's source worksheet as a standalone .xlsx file. */
export async function exportWorksheetXlsx(
  projectId: string,
  opts: { worksheetId?: string; pageId?: string },
): Promise<Blob> {
  const res = await fetch(`/api/projects/${projectId}/export/worksheet`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  });
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
  categories?: string[];
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
  collection?: string;
  tags?: string[];
  rendererVersion?: string;
  sortOrder?: number;
  source?: {
    standardKey?: string;
    rendererVersion?: string;
    [key: string]: unknown;
  };
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

async function requestLibraryJson<T>(path: string, init?: RequestInit, retries = 1): Promise<T> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    try {
      const res = await fetch(path, { ...init, signal: controller.signal });
      if (!res.ok) {
        const detail = await res.text();
        if (res.status >= 500 && attempt < retries) {
          await new Promise((resolve) => window.setTimeout(resolve, 250));
          continue;
        }
        throw new Error(detail || `Component library request failed (${res.status}).`);
      }
      return await res.json() as T;
    } catch (error) {
      lastError = error;
      if (attempt < retries && (!(error instanceof DOMException) || error.name !== 'AbortError')) {
        await new Promise((resolve) => window.setTimeout(resolve, 250));
        continue;
      }
    } finally {
      window.clearTimeout(timeout);
    }
  }
  const detail = lastError instanceof Error ? lastError.message : String(lastError || 'unknown error');
  throw new Error(`Component library server request failed after retry: ${detail}`);
}

export async function getLibV2(
  includeLegacy: boolean = true,
  includeRetired: boolean = false,
): Promise<LibV2Data> {
  const params = new URLSearchParams();
  if (includeLegacy) params.set('includeLegacy', '1');
  if (includeRetired) params.set('includeRetired', '1');
  const query = params.toString();
  return requestLibraryJson<LibV2Data>(`/api/lib${query ? `?${query}` : ''}`);
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

export interface LibV2HistoryEntry {
  name: string;
  savedAt: string;
  reason: string;
  componentCount: number;
}

export async function batchUpdateLibV2Components(
  updates: Array<{ id: string; patch: Partial<LibV2Component> }>,
  reason = 'dashboard-batch-edit',
): Promise<{ ok: boolean; updated: number; snapshot?: string; history?: LibV2HistoryEntry[] }> {
  const res = await fetch('/api/lib/components/batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates, reason }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listLibV2History(): Promise<LibV2HistoryEntry[]> {
  const res = await fetch('/api/lib/history');
  if (!res.ok) throw new Error(await res.text());
  const json = await res.json();
  return json.history || [];
}

export async function restoreLibV2History(name: string): Promise<{ ok: boolean; restored: string; backupOfCurrent?: string }> {
  const res = await fetch(`/api/lib/history/${encodeURIComponent(name)}/restore`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function restoreLibV2Component(id: string): Promise<{ ok: boolean; component?: LibV2Component; error?: string }> {
  return requestLibraryJson(`/api/lib/components/${encodeURIComponent(id)}/restore`, { method: 'POST' });
}

export async function duplicateLibV2Component(id: string): Promise<{ ok: boolean; component: LibV2Component; error?: string }> {
  const res = await fetch(`/api/lib/components/${id}/duplicate`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function archiveLibV2Component(id: string): Promise<{ ok: boolean; component?: LibV2Component; error?: string }> {
  return requestLibraryJson(`/api/lib/components/${encodeURIComponent(id)}/archive`, { method: 'POST' });
}

export async function createLibV2Component(
  file: File,
  metadata: Partial<LibV2Component>,
): Promise<{ ok: boolean; component: LibV2Component; snapshot?: string }> {
  const form = new FormData();
  form.append('file', file);
  form.append('metadata', JSON.stringify(metadata));
  return requestLibraryJson('/api/lib/components', { method: 'POST', body: form }, 0);
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

// S360 SYMBOL MAPPER START
export type SymbolMapperPattern =
  | 'solid'
  | 'outline'
  | 'double-outline'
  | 'split-vertical'
  | 'split-horizontal'
  | 'diagonal'
  | 'crosshatch';

export interface SymbolMapperClass {
  id: string;
  code: string;
  label: string;
  shape: 'auto' | 'circle' | 'square' | 'none';
  color: string;
  color2: string;
  pattern: SymbolMapperPattern;
  markerSizePt: number;
  templateBox?: { x0: number; y0: number; x1: number; y1: number };
  visualEnabled?: boolean;
}

export interface SymbolMapperLegendRow {
  id: string;
  code: string;
  label: string;
  shape: SymbolMapperClass['shape'];
  templateBox: { x0: number; y0: number; x1: number; y1: number };
  legendBox: { x0: number; y0: number; x1: number; y1: number };
  iconDataUrl: string;
  markerSizePt: number;
}

export interface SymbolMapperLegend {
  found: boolean;
  title?: string;
  message: string;
  box?: { x0: number; y0: number; x1: number; y1: number };
  previewDataUrl?: string;
  rows: SymbolMapperLegendRow[];
}

export interface SymbolMapperTemplateSymbol {
  key: string;
  code: string;
  glyph?: string;
  label: string;
  enabled: boolean;
  paletteId: string;
  color: string;
  color2: string;
  pattern: SymbolMapperPattern;
  shape?: 'circle' | 'square' | 'none';
}

export interface SymbolMapperTemplate {
  version: number;
  id: string;
  name: string;
  updatedAt: string;
  symbols: SymbolMapperTemplateSymbol[];
}

export interface SymbolMapperTemplateSaveResult {
  ok: boolean;
  template: SymbolMapperTemplate;
  added: number;
  updated: number;
  total: number;
}

export interface SymbolMapperSession {
  id: string;
  createdAt: string;
  sourceName: string;
  sourceSha256: string;
  pageCount: 1;
  page: {
    widthPt: number;
    heightPt: number;
    rotation: number;
    previewWidth: number;
    previewHeight: number;
    previewDpi: number;
    hasText: boolean;
    wordCount: number;
  };
  previewUrl: string;
  visualMatchingAvailable: boolean;
  legend: SymbolMapperLegend;
  template: SymbolMapperTemplate;
}

export interface SymbolMapperCandidate {
  id: string;
  classId: string;
  code: string;
  label: string;
  bbox: [number, number, number, number];
  markerBox: [number, number, number, number];
  method: string;
  evidence: string[];
  score: number;
  status: 'accepted' | 'review' | 'rejected';
  accepted: boolean;
  shapeRect?: [number, number, number, number] | null;
  text?: string;
}

export interface SymbolMapperSummaryRow {
  classId: string;
  code: string;
  label: string;
  accepted: number;
  review: number;
  rejected: number;
  total: number;
}

export interface SymbolMapperDetection {
  sessionId: string;
  createdAt: string;
  sourceSha256: string;
  classes: SymbolMapperClass[];
  candidates: SymbolMapperCandidate[];
  summary: SymbolMapperSummaryRow[];
  warnings: string[];
  policy: Record<string, string>;
  reviewPdfUrl: string;
  reviewPngUrl: string;
}

export interface SymbolMapperCountPackageRow {
  code: string;
  glyph?: string;
  label: string;
  color: string;
  color2: string;
  pattern: SymbolMapperPattern;
  shape?: SymbolMapperClass['shape'];
  included: number;
}

export interface SymbolMapperCountPackageResult {
  ok: boolean;
  pdfUrl: string;
  legendPngUrl: string;
  legendSvgUrl: string;
  pageCount: 2;
  listedRows: number;
  totalIncluded: number;
}

export interface SymbolMapperRenderResult {
  sessionId: string;
  renderedAt: string;
  sourceSha256: string;
  outputSha256: string;
  acceptedCount: number;
  reviewCount: number;
  rejectedCount: number;
  summary: SymbolMapperSummaryRow[];
  pdfUrl: string;
  pngUrl: string;
  png: { width: number; height: number; dpi: number };
  sourceName: string;
}

async function symbolMapperJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = await res.text();
    try {
      const parsed = JSON.parse(message) as { error?: string; detail?: string };
      message = [parsed.error, parsed.detail].filter(Boolean).join(' - ') || message;
    } catch {
      // Keep the server text response.
    }
    throw new Error(message || `Symbol Mapper request failed (${res.status}).`);
  }
  return res.json() as Promise<T>;
}

export async function getSymbolMapperTemplate(): Promise<SymbolMapperTemplate> {
  const res = await fetch('/api/symbol-mapper/template');
  const data = await symbolMapperJson<{ ok: boolean; template: SymbolMapperTemplate }>(res);
  return data.template;
}

export async function saveSymbolMapperTemplate(
  symbols: SymbolMapperTemplateSymbol[],
): Promise<SymbolMapperTemplateSaveResult> {
  const res = await fetch('/api/symbol-mapper/template', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'Singh360 Standard', symbols }),
  });
  return symbolMapperJson<SymbolMapperTemplateSaveResult>(res);
}

export async function createSymbolMapperSession(file: File): Promise<SymbolMapperSession> {
  const body = new FormData();
  body.append('file', file);
  const res = await fetch('/api/symbol-mapper/sessions', { method: 'POST', body });
  return symbolMapperJson<SymbolMapperSession>(res);
}

export async function detectSymbolMap(sessionId: string, classes: SymbolMapperClass[]): Promise<SymbolMapperDetection> {
  const res = await fetch(`/api/symbol-mapper/sessions/${encodeURIComponent(sessionId)}/detect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ classes }),
  });
  return symbolMapperJson<SymbolMapperDetection>(res);
}

export async function renderSymbolMap(
  sessionId: string,
  classes: SymbolMapperClass[],
  candidates: SymbolMapperCandidate[],
): Promise<SymbolMapperRenderResult> {
  const res = await fetch(`/api/symbol-mapper/sessions/${encodeURIComponent(sessionId)}/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ classes, candidates }),
  });
  return symbolMapperJson<SymbolMapperRenderResult>(res);
}

export async function createSymbolMapperCountPackage(
  sessionId: string,
  payload: {
    title: string;
    drawingCode?: string;
    sourceName: string;
    rows: SymbolMapperCountPackageRow[];
  },
): Promise<SymbolMapperCountPackageResult> {
  const res = await fetch(`/api/symbol-mapper/sessions/${encodeURIComponent(sessionId)}/package`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return symbolMapperJson<SymbolMapperCountPackageResult>(res);
}

export async function deleteSymbolMapperSession(sessionId: string): Promise<void> {
  const res = await fetch(`/api/symbol-mapper/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  if (!res.ok && res.status !== 404) throw new Error(await res.text());
}
// S360 SYMBOL MAPPER END

// S360 PROJECT HOME + EXTERNAL WORKBOOK LINK V1
export interface WorkbookLinkWorkbookInfo {
  path: string;
  filename: string;
  sheetCount: number;
  projectId?: string;
  schemaVersion?: string;
  helpVersion?: string;
  projectName?: string;
  modified?: string;
  size?: number;
  sha256?: string;
}

export interface WorkbookLinkStatus {
  ok: boolean;
  status: string;
  mode: string;
  path: string;
  message: string;
  workbook?: WorkbookLinkWorkbookInfo;
  baselineWorkbookHash?: string;
  baselineAppHash?: string;
  currentWorkbookHash?: string;
  currentAppHash?: string;
  lastSyncUtc?: string;
  warning?: string;
  verified?: boolean;
  verification?: {
    status?: string;
    verified?: boolean;
    basePageCount?: number;
  };
}

export async function getWorkbookLinkStatus(projectId: string): Promise<WorkbookLinkStatus> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function linkWorkbookPath(projectId: string, path: string): Promise<{ project: ProjectModel; status: WorkbookLinkStatus }> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function pickWorkbookPath(projectId: string): Promise<{
  cancelled: boolean;
  selectedPath?: string;
  status: WorkbookLinkStatus;
}> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link/pick`, { method: 'POST' });
  const payload = await res.json().catch(async () => ({
    error: await res.text(),
  }));
  if (!res.ok) throw new Error(payload.detail || payload.error || 'Workbook picker failed.');
  return payload;
}
export async function syncWorkbookLink(projectId: string): Promise<{ project: ProjectModel; status: WorkbookLinkStatus }> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link/sync`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function resolveWorkbookLink(
  projectId: string,
  direction: 'workbook_to_app' | 'app_to_workbook' | 'baseline',
): Promise<{ project: ProjectModel; status: WorkbookLinkStatus }> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ direction }),
  });
  if (!res.ok) throw await exactApiError(res);
  return res.json();
}

export async function autoLayoutImportedPage(
  projectId: string,
  pageId: string,
  layoutOverride: 'exact_source' | 'two_columns' | 'keep_one_page',
): Promise<{
  project: ProjectModel;
  pageIds: string[];
  continuationCount: number;
  layoutDiagnostics: Record<string, unknown>;
}> {
  const res = await fetch(`/api/projects/${projectId}/pages/${pageId}/auto-layout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ layoutOverride }),
  });
  if (!res.ok) throw await exactApiError(res);
  return res.json();
}

export async function unlinkWorkbook(projectId: string): Promise<void> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
}

export async function openLinkedWorkbook(projectId: string): Promise<void> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link/open`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
}

export async function revealLinkedWorkbook(projectId: string): Promise<void> {
  const res = await fetch(`/api/projects/${projectId}/workbook-link/reveal`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
}

// S360 FOOLPROOF PROJECT WORKFLOW V1
export interface WorkbookQualityIssue {
  severity: 'critical' | 'error' | 'warning' | 'info';
  code: string;
  message: string;
  items?: unknown[];
}

export interface WorkbookQualityReport {
  ok: boolean;
  path: string;
  filename: string;
  modifiedUtc: string;
  counts: {
    sheets: number;
    indexRows: number;
    includedRows: number;
    excludedRows: number;
    unindexedSheets: number;
    formulaErrors: number;
    critical: number;
    errors: number;
    warnings: number;
  };
  issues: WorkbookQualityIssue[];
  safeRepairAvailable: boolean;
  strictRepairAvailable: boolean;
}

export async function getWorkbookQuality(projectId: string): Promise<WorkbookQualityReport> {
  const res = await fetch(`/api/projects/${projectId}/workbook-quality`);
  const payload = await res.json().catch(async () => ({ error: await res.text() }));
  if (!res.ok) throw new Error(payload.detail || payload.error || 'Workbook audit failed.');
  return payload;
}

export async function repairWorkbookQuality(
  projectId: string,
  mode: 'safe' | 'strict',
): Promise<{ ok: boolean; mode: string; backup: string; changes: string[]; audit: WorkbookQualityReport; message: string }> {
  const res = await fetch(`/api/projects/${projectId}/workbook-quality/repair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  const payload = await res.json().catch(async () => ({ error: await res.text() }));
  if (!res.ok) throw new Error(payload.detail || payload.error || 'Workbook repair failed.');
  return payload;
}

export function aiGuideUrl(format: 'html' | 'markdown' = 'html'): string {
  return format === 'markdown' ? '/api/docs/ai-guide' : '/docs/ai-guide';
}

// S360 PAGE INCLUSION SAVE V1
export interface PageInclusionSaveResult {
  ok: boolean;
  project: ProjectModel;
  included: number;
  excluded: number;
  workbookSync?: Record<string, unknown>;
}

export async function savePageInclusion(
  projectId: string,
  includedByPageId: Record<string, boolean>,
): Promise<PageInclusionSaveResult> {
  const response = await fetch(`/api/projects/${projectId}/page-inclusion`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ includedByPageId }),
  });
  const payload = await response.json().catch(async () => ({
    error: await response.text(),
  }));
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || 'Page selection save failed.');
  }
  return payload;
}
