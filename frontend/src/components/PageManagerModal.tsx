import { useEffect, useMemo, useState, type ChangeEvent } from 'react';
import type { PageModel, ProjectModel } from '../model/types';
import { pageStatusClass } from '../model/pageStatus';

interface Props {
  project: ProjectModel;
  busy?: boolean;
  onClose: () => void;
  onSave: (includedByPageId: Record<string, boolean>) => Promise<void>;
  onOpenPage: (pageId: string) => void;
}


function statusLabel(page: PageModel): string {
  const value = String(page.issueStatus || 'draft').replace(/_/g, ' ');
  return value.replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function previewUrl(page: PageModel): string {
  const record = page as unknown as Record<string, unknown>;
  for (const key of ['thumbnailUrl', 'underlayUrl', 'sourcePdfUrl', 'previewUrl']) {
    if (typeof record[key] === 'string' && record[key]) return String(record[key]);
  }
  const blocks = Array.isArray(page.blocks) ? page.blocks : [];
  for (const block of blocks) {
    const entry = block as unknown as Record<string, unknown>;
    for (const key of ['url', 'src', 'imageUrl']) {
      if (typeof entry[key] === 'string' && entry[key]) return String(entry[key]);
    }
  }
  return '';
}

export default function PageManagerModal({
  project,
  busy,
  onClose,
  onSave,
  onOpenPage,
}: Props) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'included' | 'excluded'>('all');
  const [included, setIncluded] = useState<Record<string, boolean>>(
    Object.fromEntries(project.pages.map((page) => [page.id, Boolean(page.include)])),
  );

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  const sortedPages = useMemo(
    () => [...project.pages].sort((a, b) => a.order - b.order),
    [project.pages],
  );

  const physicalNumber = useMemo(
    () => Object.fromEntries(sortedPages.map((page, index) => [page.id, index + 1])),
    [sortedPages],
  );

  const filteredPages = useMemo(() => {
    const search = query.trim().toLowerCase();
    return sortedPages.filter((page) => {
      if (filter === 'included' && !included[page.id]) return false;
      if (filter === 'excluded' && included[page.id]) return false;
      if (!search) return true;
      return `${page.sheetCode} ${page.displaySheetCode || ''} ${page.sheetTitle} ${page.sheetTab}`
        .toLowerCase()
        .includes(search);
    });
  }, [sortedPages, included, filter, query]);

  const visiblePages = filteredPages;

  const includedCount = Object.values(included).filter(Boolean).length;
  const excludedCount = project.pages.length - includedCount;

  const includeAll = () => {
    setIncluded(Object.fromEntries(project.pages.map((page) => [page.id, true])));
  };

  const excludeAll = () => {
    if (!window.confirm(
      'Exclude every page from the published drawing set? The pages will remain in the editor and can be included again.',
    )) return;
    setIncluded(Object.fromEntries(project.pages.map((page) => [page.id, false])));
  };

  return (
    <div className="dashboard-overlay page-manager-overlay" role="dialog" aria-modal="true">
      <div className="dashboard-overlay-panel page-manager-modal">
        <div className="overlay-head page-manager-head">
          <div>
            <div className="eyebrow">DRAWING SET REVIEW</div>
            <h2>Review Drawing Pages</h2>
            <p>Scroll through every page, choose what publishes, or open an exact page in the editor. Nothing changes until you save.</p>
          </div>
          <div className="page-manager-head-actions">
            <button type="button" onClick={onClose}>Close Without Saving</button>
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() => void onSave(included)}
            >
              Save Drawing Set Selection · {includedCount} Included / {excludedCount} Excluded
            </button>
          </div>
        </div>

        <div className="page-manager-summary">
          <div><b>{project.pages.length}</b><span>Total editor pages</span></div>
          <div className="included"><b>{includedCount}</b><span>Included in drawing set</span></div>
          <div className="excluded"><b>{excludedCount}</b><span>Excluded but editable</span></div>
          <div><b>{filteredPages.length}</b><span>Shown by current filter</span></div>
        </div>

        <div className="page-manager-tools">
          <input
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
            placeholder="Search sheet code, title, or workbook tab"
          />
          <button type="button" className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All</button>
          <button type="button" className={filter === 'included' ? 'active' : ''} onClick={() => setFilter('included')}>Included</button>
          <button type="button" className={filter === 'excluded' ? 'active' : ''} onClick={() => setFilter('excluded')}>Excluded</button>
          <button type="button" onClick={includeAll}>Include All {project.pages.length}</button>
          <button type="button" onClick={excludeAll}>Exclude All {project.pages.length}</button>
        </div>

        <div className="page-manager-scroll-note">
          Showing all {filteredPages.length} matching page{filteredPages.length === 1 ? '' : 's'}. Use the scrollbar to review the complete drawing package.
        </div>
        <div className="page-manager-scroll" aria-label="Complete drawing page list">
          <div className="page-thumbnail-grid readable">
          {visiblePages.map((page) => {
            const image = previewUrl(page);
            const isIncluded = Boolean(included[page.id]);
            return (
              <article key={page.id} className={`page-thumbnail-card readable ${isIncluded ? 'included' : 'excluded'} ${isIncluded ? pageStatusClass({ ...page, include: true }) : 'status-excluded'}`}>
                <button type="button" className="page-thumb-preview readable" onClick={() => onOpenPage(page.id)}>
                  {image ? (
                    <img src={image} alt={`Preview of ${page.sheetTitle}`} />
                  ) : (
                    <div className="page-thumb-placeholder">
                      <div className="page-thumb-code">{page.displaySheetCode || page.sheetCode || 'NEW'}</div>
                      <div className="page-thumb-title">{page.sheetTitle}</div>
                      <div className="page-thumb-type">{page.pageType || 'Page'}</div>
                      <div className="page-thumb-titleblock">Open in editor for full page</div>
                    </div>
                  )}
                </button>

                <div className="page-thumb-info readable">
                  <div className="page-thumb-order">Editor Page {physicalNumber[page.id]} of {project.pages.length}</div>
                  <strong>{page.displaySheetCode || page.sheetCode || 'NEW'}</strong>
                  <span>{page.sheetTitle}</span>
                  <small>{statusLabel(page)} · {page.pageType || 'Page'} · Tab: {page.sheetTab}</small>
                </div>

                <div className="page-include-control">
                  <label>
                    <input
                      type="checkbox"
                      checked={isIncluded}
                      onChange={(event: ChangeEvent<HTMLInputElement>) => {
                        const checked = event.target.checked;
                        setIncluded((current) => ({ ...current, [page.id]: checked }));
                      }}
                    />
                    <span>
                      <b>{isIncluded ? 'Included in Drawing Set' : 'Excluded from Drawing Set'}</b>
                      <small>{isIncluded ? 'Will appear in Sheet Index, Page X of Y, and export.' : 'Stays in the editor and can be included later.'}</small>
                    </span>
                  </label>
                </div>

                <button type="button" className="open-page-button" onClick={() => onOpenPage(page.id)}>
                  Open This Page in Editor
                </button>
              </article>
            );
          })}
          </div>
        </div>

        <div className="page-manager-footer">
          <button type="button" onClick={onClose}>Close Without Saving</button>
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => void onSave(included)}
          >
            Save Drawing Set Selection · {includedCount} Included / {excludedCount} Excluded
          </button>
        </div>
      </div>
    </div>
  );
}
