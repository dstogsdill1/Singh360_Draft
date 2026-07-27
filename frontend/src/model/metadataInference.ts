/** Client mirror of core/metadata_inference.py. */
import type { ProjectModel, Worksheet } from './types';

export type MetadataField =
  | 'projectName'
  | 'storeNumber'
  | 'drawingPackageFileName'
  | 'location'
  | 'revision'
  | 'templateVersion'
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
  'store number': 'storeNumber',
  'drawing package file name': 'drawingPackageFileName',
  package: 'drawingPackageFileName',
  location: 'location',
  address: 'location',
  'project revision': 'revision',
  revision: 'revision',
  rev: 'revision',
  'template version': 'templateVersion',
  'issue date': 'issueDate',
  'drawn by': 'drawnBy',
  'checked by': 'checkedBy',
  'prepared for': 'client',
  client: 'client',
  purpose: 'purpose',
  status: 'status',
};

const labelKey = (value: unknown): string =>
  String(value ?? '')
    .replace(/\u00a0/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/[:\s]+$/, '');

const cleanValue = (value: unknown): string => {
  const text = String(value ?? '')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text || /^(none|nan|nat|<na>)$/i.test(text)) return '';
  if (/^[\s:;,.|/\\\-–—_•·]+$/.test(text)) return '';
  return /[A-Za-z0-9]/.test(text) ? text : '';
};

const normalizeIssueDate = (value: string): string => {
  const iso = value.match(/^(\d{4}-\d{2}-\d{2})[ T]00:00:00(?:\.0+)?$/);
  if (iso) return iso[1];

  const us = value.match(/^(\d{1,2}\/\d{1,2}\/\d{4})[ T]00:00:00(?:\.0+)?$/);
  if (us) return us[1];

  const serial = Number(value);
  if (Number.isFinite(serial) && serial >= 20000 && serial <= 80000) {
    return new Date(Date.UTC(1899, 11, 30) + Math.floor(serial) * 86400000)
      .toISOString()
      .slice(0, 10);
  }
  return value;
};

export const projectRevisionForOutput = (value: unknown): string => {
  const text = cleanValue(value);
  return /\b(template(?:\s+version)?|orange\s+header\s+locked)\b/i.test(text)
    ? 'TBD'
    : text;
};

export function inferMetadataFromGrid(grid: string[][]): Partial<Record<MetadataField, string>> {
  const out: Partial<Record<MetadataField, string>> = {};

  for (const row of grid) {
    for (let index = 0; index < row.length; index += 1) {
      const field = METADATA_LABEL_MAP[labelKey(row[index])];
      if (!field || out[field]) continue;

      for (let cursor = index + 1; cursor < Math.min(row.length, index + 13); cursor += 1) {
        if (METADATA_LABEL_MAP[labelKey(row[cursor])]) break;
        let value = cleanValue(row[cursor]);
        if (!value) continue;
        if (field === 'issueDate') value = normalizeIssueDate(value);
        if (field === 'revision') value = projectRevisionForOutput(value);
        out[field] = value;
        break;
      }
    }
  }

  return out;
}

export function inferMetadataFromWorksheet(ws: Worksheet): Partial<Record<MetadataField, string>> {
  return inferMetadataFromGrid(ws.grid ?? []);
}

export function isCoverWorksheet(project: ProjectModel, wsId: string): boolean {
  return project.pages.some(
    (page) => page.linkedWorksheetId === wsId
      && (page.pageType === 'cover' || (page.blocks ?? []).some((block) => block.type === 'cover')),
  );
}

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
