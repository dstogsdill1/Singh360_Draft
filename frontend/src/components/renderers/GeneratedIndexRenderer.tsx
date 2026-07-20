import { useEffect, useMemo } from 'react';
import type { PageModel, ProjectModel } from '../../model/types';
import { cleanIndexNote, indexPageTypeLabel } from '../../model/packageIndex';

interface Props {
  project: ProjectModel;
  page: PageModel;
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
}

/**
 * Clean generated Sheet Index / TOC.
 *
 * Normalized/PDF output is built from the CURRENT included pages. The linked
 * workbook worksheet remains untouched and fully visible/editable in Source.
 * Internal/excluded pages and internal-only columns never appear here.
 */
export default function GeneratedIndexRenderer({ project, onPatchPage }: Props) {
  const included = useMemo(
    () => [...(project.pages ?? [])]
      .filter((page) => page.include !== false)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [project.pages],
  );

  const commitCode = (target: PageModel, value: string) => {
    const next = value.trim();
    onPatchPage(target.id, { sheetCode: next, displaySheetCode: next });
  };

  const commitTitle = (target: PageModel, value: string) => {
    onPatchPage(target.id, { sheetTitle: value.trim() || 'Untitled Sheet' });
  };

  const onKeyDown = (
    e: React.KeyboardEvent<HTMLElement>,
    target: PageModel,
    field: 'code' | 'title',
  ) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const value = e.currentTarget.textContent ?? '';
      if (field === 'code') commitCode(target, value);
      else commitTitle(target, value);
      e.currentTarget.blur();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.currentTarget.textContent = field === 'code'
        ? (target.displaySheetCode || target.sheetCode || '')
        : target.sheetTitle;
      e.currentTarget.blur();
    }
  };

  useEffect(() => {
    const capture = () => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || !el.isContentEditable || !el.closest('.np-index-table')) return;
      const pageId = el.dataset.pageId ?? '';
      const field = el.dataset.field as 'code' | 'title' | undefined;
      const target = included.find((page) => page.id === pageId);
      if (!target || !field) return;
      const value = el.textContent ?? '';
      if (field === 'code') commitCode(target, value);
      else commitTitle(target, value);
    };
    document.addEventListener('singh360:capture-active-editors', capture);
    return () => document.removeEventListener('singh360:capture-active-editors', capture);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [included, onPatchPage]);

  if (!included.length) {
    return <div className="np-index np-empty">No included sheets.</div>;
  }

  const compact = included.length > 28 ? ' ni-compact' : '';

  return (
    <div className="np-index">
      <table className={`np-index-table${compact}`}>
        <thead>
          <tr>
            <th className="ni-pg">Page</th>
            <th className="ni-code">Sheet Code</th>
            <th className="ni-tab">Sheet Tab</th>
            <th className="ni-title">Page Title</th>
            <th className="ni-type">Page Type</th>
            <th className="ni-notes">Notes</th>
          </tr>
        </thead>
        <tbody>
          {included.map((page) => (
            <tr key={page.id} className={page.generatedContinuation ? 'ni-cont' : ''}>
              <td className="ni-pg">{page.pageNumber ?? '—'}</td>
              <td
                className="ni-code"
                contentEditable
                suppressContentEditableWarning
                tabIndex={0}
                data-page-id={page.id}
                data-field="code"
                title="Edit the actual sheet code. Enter commits; Esc cancels."
                onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onBlur={(e) => commitCode(page, e.currentTarget.textContent ?? '')}
                onKeyDown={(e) => onKeyDown(e, page, 'code')}
              >
                {page.displaySheetCode || page.sheetCode || '—'}
              </td>
              <td className="ni-tab">{page.sheetTab || '—'}</td>
              <td
                className="ni-title"
                contentEditable
                suppressContentEditableWarning
                tabIndex={0}
                data-page-id={page.id}
                data-field="title"
                title="Edit the actual page title. Enter commits; Esc cancels."
                onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onBlur={(e) => commitTitle(page, e.currentTarget.textContent ?? '')}
                onKeyDown={(e) => onKeyDown(e, page, 'title')}
              >
                {page.sheetTitle}
                {page.generatedContinuation && <span className="ni-cont-mark"> — CONTINUED</span>}
              </td>
              <td className="ni-type">{indexPageTypeLabel(page)}</td>
              <td className="ni-notes">{cleanIndexNote(page)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
