import type { ProjectModel, PageModel } from '../model/types';

export async function listProjects(): Promise<Array<{ id: string; projectName: string }>> {
  const res = await fetch('/api/projects');
  const json = await res.json();
  return json.projects ?? [];
}

export async function createProjectFromWorkbook(file: File): Promise<{ id: string }> {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/projects/new', { method: 'POST', body: fd });
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

export async function exportPdf(projectId: string): Promise<Blob> {
  const res = await fetch(`/api/projects/${projectId}/export/pdf`, { method: 'POST' });
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
}

export interface LibraryData {
  components: LibraryComponent[];
  categories: Array<{ id: string; count: number }>;
  connectorStyles: Array<Record<string, unknown>>;
  symbols: Array<Record<string, unknown>>;
}

export function libraryAssetUrl(path: string): string {
  return `/api/library/assets/${path.replace(/^\/+/, '')}`;
}

export async function getLibrary(): Promise<LibraryData> {
  const res = await fetch('/api/library');
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function importLibrarySeed(): Promise<{ ok: boolean; componentCount?: number; filesCopied?: number; error?: string }> {
  const res = await fetch('/api/library/import-seed', { method: 'POST' });
  return res.json();
}

export async function retireLibraryComponent(id: string): Promise<void> {
  const res = await fetch(`/api/library/components/${id}/retire`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
}

export async function deleteLibraryComponent(id: string): Promise<void> {
  const res = await fetch(`/api/library/components/${id}?confirm=1`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
}

