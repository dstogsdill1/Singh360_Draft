import type { PageIssueStatus, PageModel } from './types';

export const HELP_VERSION = '2026.07.22-status-sync-1';

export const PAGE_ISSUE_STATUSES: Array<{
  value: PageIssueStatus;
  label: string;
  confirmed: boolean;
  color: string;
}> = [
  { value: 'draft', label: 'Draft', confirmed: false, color: '#f28c28' },
  { value: 'draft_confirmed', label: 'Draft Confirmed', confirmed: true, color: '#76b852' },
  { value: 'public', label: 'Public', confirmed: false, color: '#2d7dd2' },
  { value: 'public_confirmed', label: 'Public Confirmed', confirmed: true, color: '#14845a' },
];

export function normalizePageIssueStatus(value: unknown): PageIssueStatus {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (raw === 'draft_confirmed') return 'draft_confirmed';
  if (raw === 'public') return 'public';
  if (raw === 'public_confirmed') return 'public_confirmed';
  return 'draft';
}

export function pageIssueLabel(value: unknown): string {
  const normalized = normalizePageIssueStatus(value);
  return PAGE_ISSUE_STATUSES.find((item) => item.value === normalized)?.label || 'Draft';
}

export function pageStatusClass(page: PageModel): string {
  if (!page.include) return 'status-excluded';
  return `status-${normalizePageIssueStatus(page.issueStatus)}`;
}

export function pageStatusColor(page: PageModel): string {
  if (!page.include) return '#9aa3ab';
  const normalized = normalizePageIssueStatus(page.issueStatus);
  return PAGE_ISSUE_STATUSES.find((item) => item.value === normalized)?.color || '#f28c28';
}
