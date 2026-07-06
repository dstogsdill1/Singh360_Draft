import { useEffect } from 'react';
import type { PageModel, ProjectModel } from '../../model/types';

interface Props {
  project: ProjectModel;
  page: PageModel;
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
}

/**
 * Generated Sheet Index / TOC for pages with pageType="index".
 *
 * Renders a clean table built from the CURRENT included pages. This is NOT a
 * raw workbook dump — it is always in sync with the actual package state.
 * Never scrolls; the normalized sheet body enforces overflow:hidden, so if
 * the list is too long the workbook importer or compose_pages must split it
 * into continuation sheets (0.1a, 0.1b).
 */
export default function GeneratedIndexRenderer({ project, onPatchPage }: Props) {
  const included = (project.pages ?? []).filter((p) => p.include);

  const commitCode = (target: PageModel, value: string) => {
    const next = value.trim();
    onPatchPage(target.id, { sheetCode: next, displaySheetCode: next });
  };

  const commitTitle = (target: PageModel, value: string) => {
    onPatchPage(target.id, { sheetTitle: value.trim() || 'Untitled Sheet' });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLElement>, target: PageModel, field: 'code' | 'title') => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const value = e.currentTarget.textContent ?? '';
      if (field === 'code') commitCode(target, value);
      else commitTitle(target, value);
      e.currentTarget.blur();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.currentTarget.textContent = field === 'code' ? (target.displaySheetCode || target.sheetCode || '') : target.sheetTitle;
      e.currentTarget.blur();
    }
  };

  useEffect(() => {
    const capture = () => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || !el.isContentEditable || !el.closest('.np-index-table')) return;
      const pageId = el.dataset.pageId ?? '';
      const field = el.dataset.field as 'code' | 'title' | undefined;
      const target = included.find((p) => p.id === pageId);
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
    return <div className="np-index np-empty">No included sheets — add or include pages to generate the index.</div>;
  }

  return (
    <div className="np-index">
      <table className="np-index-table">
        <thead>
          <tr>
            <th className="ni-code">Sheet Code</th>
            <th className="ni-title">Sheet Title</th>
            <th className="ni-pg">Page</th>
          </tr>
        </thead>
        <tbody>
          {included.map((p) => {
            return (
              <tr key={p.id} className={p.generatedContinuation ? 'ni-cont' : ''}>
                <td
                  className="ni-code"
                  contentEditable
                  suppressContentEditableWarning
                  tabIndex={0}
                  data-page-id={p.id}
                  data-field="code"
                  title="Edit this sheet code. Press Enter to commit, Esc to cancel."
                  onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
                  onBlur={(e) => commitCode(p, e.currentTarget.textContent ?? '')}
                  onKeyDown={(e) => onKeyDown(e, p, 'code')}
                >{p.displaySheetCode || p.sheetCode || '—'}</td>
                <td
                  className="ni-title"
                  contentEditable
                  suppressContentEditableWarning
                  tabIndex={0}
                  data-page-id={p.id}
                  data-field="title"
                  title="Edit this sheet title. Press Enter to commit, Esc to cancel."
                  onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
                  onBlur={(e) => commitTitle(p, e.currentTarget.textContent ?? '')}
                  onKeyDown={(e) => onKeyDown(e, p, 'title')}
                >
                  {p.sheetTitle}
                  {p.generatedContinuation && <span className="ni-cont-mark"> — CONTINUED</span>}
                </td>
                <td className="ni-pg">{p.pageNumber ?? '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
