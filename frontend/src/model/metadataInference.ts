/** Client mirror of core/metadata_inference.py — cover source is truth at rebuild. */
import type { ProjectModel, Worksheet } from './types';

export type MetadataField =
  | 'projectName'
  | 'storeNumber'
  | 'drawingPackageFileName'
  | 'location'
  | 'revision'
  | 'issueDate'
  | 'drawnBy'
  | 'checkedBy'
  | 'client'
  | 'purpose'
  | 'status';

export const METADATA_LABEL_MAP: Record<string, MetadataField> = {
  'project name': 'projectName',
  project: 'projectName',
  'store name': 'storeNumber',
  'drawing package file name': 'drawingPackageFileName',
  package: 'drawingPackageFileName',
  location: 'location',
  address: 'location',
  revision: 'revision',
  rev: 'revision',
  'issue date': 'issueDate',
  'drawn by': 'drawnBy',
  'prepared by': 'drawnBy',
  'checked by': 'checkedBy',
  'prepared for': 'client',
  client: 'client',
  purpose: 'purpose',
  status: 'status',
};

/** Infer metadata fields from adjacent label/value pairs in a grid. */
export function inferMetadataFromGrid(grid: string[][]): Partial<Record<MetadataField, string>> {
  const out: Partial<Record<MetadataField, string>> = {};
  for (const row of grid) {
    for (let i = 0; i < row.length - 1; i += 1) {
      const label = (row[i] ?? '').trim().toLowerCase().replace(/:$/, '');
      const field = METADATA_LABEL_MAP[label];
      if (!field) continue;
      const value = (row[i + 1] ?? '').trim();
      if (value && !out[field]) out[field] = value;
    }
  }
  return out;
}

export function inferMetadataFromWorksheet(ws: Worksheet): Partial<Record<MetadataField, string>> {
  return inferMetadataFromGrid(ws.grid ?? []);
}

export function isCoverWorksheet(project: ProjectModel, wsId: string): boolean {
  return project.pages.some(
    (p) => p.linkedWorksheetId === wsId
      && (p.pageType === 'cover' || (p.blocks ?? []).some((b) => b.type === 'cover')),
  );
}

/** Cover source overwrites project metadata (opposite of import fill-if-empty). */
export function mergeCoverMetadata<T extends ProjectModel['metadata']>(
  current: T,
  inferred: Partial<Record<MetadataField, string>>,
): T {
  const next = { ...current };
  for (const [field, value] of Object.entries(inferred) as [MetadataField, string][]) {
    if (value) (next as Record<string, string>)[field] = value;
  }
  return next;
}
