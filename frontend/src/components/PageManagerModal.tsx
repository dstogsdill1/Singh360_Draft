import { useMemo, useState, type ChangeEvent } from 'react';
import type { PageModel, ProjectModel } from '../model/types';

interface Props {
  project: ProjectModel;
  busy?: boolean;
  onClose: () => void;
  onSave: (project: ProjectModel) => Promise<void>;
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

export default function PageManagerModal({ project, busy, onClose, onSave, onOpenPage }: Props) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'included' | 'excluded'>('all');
  const [included, setIncluded] = useState<Record<string, boolean>>(
    Object.fromEntries(project.pages.map((page) => [page.id, Boolean(page.include)])),
  );

  const pages = useMemo(() => {
    const search = query.trim().toLowerCase();
    return [...project.pages]
      .sort((a, b) => a.order - b.order)
      .filter((page) => {
        if (filter === 'included' && !included[page.id]) return false;
        if (filter === 'excluded' && included[page.id]) return false;
        if (!search) return true;
        return `${page.sheetCode} ${page.sheetTitle} ${page.sheetTab}`.toLowerCase().includes(search);
      });
  }, [project.pages, included, filter, query]);

  const apply = async () => {
    const next: ProjectModel = {
      ...project,
      pages: project.pages.map((page) => ({ ...page, include: Boolean(included[page.id]) })),
    };
    await onSave(next);
  };

  return (
    <div className="dashboard-overlay" role="dialog" aria-modal="true">
      <div className="dashboard-overlay-panel page-manager-modal">
        <div className="overlay-head">
          <div>
            <h2>Page Manager</h2>
            <p>Review every page before entering the editor. Excluded pages stay visible and editable.</p>
          </div>
          <div>
            <button type="button" disabled={busy} onClick={() => {
              setIncluded(Object.fromEntries(project.pages.map((page) => [page.id, true])));
            }}>Include All</button>
            <button type="button" disabled={busy} onClick={() => {
              setIncluded(Object.fromEntries(project.pages.map((page) => [page.id, false])));
            }}>Exclude All</button>
            <button type="button" className="primary" disabled={busy} onClick={() => void apply()}>Save Include / Exclude</button>
            <button type="button" onClick={onClose} disabled={busy}>Close</button>
          </div>
        </div>
        <div className="page-manager-tools">
          <input
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
            placeholder="Search sheet code, title, or tab"
          />
          <button type="button" className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All {project.pages.length}</button>
          <button type="button" className={filter === 'included' ? 'active' : ''} onClick={() => setFilter('included')}>Included</button>
          <button type="button" className={filter === 'excluded' ? 'active' : ''} onClick={() => setFilter('excluded')}>Excluded</button>
        </div>
        <div className="page-thumbnail-grid">
          {pages.map((page) => {
            const image = previewUrl(page);
            const isIncluded = Boolean(included[page.id]);
            return (
              <article key={page.id} className={`page-thumbnail-card ${isIncluded ? 'included' : 'excluded'}`}>
                <button type="button" className="page-thumb-preview" onClick={() => onOpenPage(page.id)}>
                  {image ? (
                    <img src={image} alt="" />
                  ) : (
                    <div className="page-thumb-skeleton">
                      <div className="thumb-title-band">{page.sheetTitle}</div>
                      <div className="thumb-lines"><i /><i /><i /><i /><i /><i /></div>
                      <div className="thumb-title-block">{page.displaySheetCode || page.sheetCode}</div>
                    </div>
                  )}
                </button>
                <div className="page-thumb-info">
                  <strong>{page.displaySheetCode || page.sheetCode}</strong>
                  <span>{page.sheetTitle}</span>
                  <small>{statusLabel(page)} · {page.pageType}</small>
                </div>
                <label>
                  <input
                    type="checkbox"
                    checked={isIncluded}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setIncluded((current) => ({ ...current, [page.id]: event.target.checked }))}
                  />
                  {isIncluded ? 'Included in Drawing Set' : 'Excluded — still editable'}
                </label>
                <button type="button" onClick={() => onOpenPage(page.id)}>Open This Page in Editor</button>
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
