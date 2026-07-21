import { useEffect, useMemo, useRef, useState } from 'react';
import type { PageModel } from '../model/types';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
}

function pageDescription(page: PageModel): string {
  return page.notes || page.sourceSheet || page.sheetTab || page.pageFamily || page.pageType;
}

export default function PageNavigator({ pages, activePageId, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [showExcluded, setShowExcluded] = useState(true);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', key);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', key);
    };
  }, [open]);

  const listed = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...pages]
      .sort((a, b) => a.order - b.order)
      .filter((page) => showExcluded || page.include)
      .filter((page) => {
        if (!needle) return true;
        return [page.sheetCode, page.displaySheetCode, page.sheetTitle, page.sheetTab, page.sourceSheet, page.notes]
          .join(' ')
          .toLowerCase()
          .includes(needle);
      });
  }, [pages, query, showExcluded]);

  const active = pages.find((page) => page.id === activePageId);

  return (
    <div className="page-nav" ref={rootRef}>
      <button type="button" className={`page-nav-button ${open ? 'active' : ''}`} title="All pages and worksheets" onClick={() => setOpen((value) => !value)}>
        <span className="page-nav-hamburger">☰</span>
        <span className="page-nav-current">{active?.pageNumber ?? '—'}</span>
      </button>
      {open ? (
        <div className="page-nav-popover">
          <div className="page-nav-head">
            <div>
              <strong>All Drawing Pages</strong>
              <span>{pages.filter((page) => page.include).length} published · {pages.length} total</span>
            </div>
            <button type="button" onClick={() => setOpen(false)} title="Close">×</button>
          </div>
          <div className="page-nav-filters">
            <input autoFocus type="search" placeholder="Search code, title, tab, or note…" value={query} onChange={(event) => setQuery(event.target.value)} />
            <label><input type="checkbox" checked={showExcluded} onChange={(event) => setShowExcluded(event.target.checked)} /> Show excluded/source-only</label>
          </div>
          <div className="page-nav-list">
            {listed.map((page) => (
              <button
                type="button"
                key={page.id}
                className={`page-nav-row ${page.id === activePageId ? 'active' : ''} ${page.include ? '' : 'excluded'}`}
                onClick={() => { onSelect(page.id); setOpen(false); }}
              >
                <span className="page-nav-number">{page.pageNumber ?? '—'}</span>
                <span className="page-nav-copy">
                  <span className="page-nav-title"><b>{page.displaySheetCode || page.sheetCode || 'NO CODE'}</b> {page.sheetTitle}</span>
                  <span className="page-nav-desc">{pageDescription(page)}</span>
                </span>
                <span className="page-nav-badges">
                  {page.generatedContinuation || page.continuationOf ? <em>Continuation</em> : null}
                  <em className={page.include ? 'published' : 'source-only'}>{page.include ? 'Published' : 'Excluded'}</em>
                </span>
              </button>
            ))}
            {!listed.length ? <div className="page-nav-empty">No pages match this search.</div> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
