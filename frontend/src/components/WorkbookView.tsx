import { useMemo, useState } from 'react';
import type { PageModel, Worksheet } from '../model/types';

interface Props {
  worksheets: Worksheet[];
  pages: PageModel[];
  selectedWorksheetId?: string;
  onOpenDraft: (id: string) => void;
  onPublishWorksheet: (id: string) => void;
}

export default function WorkbookView({ worksheets, pages, selectedWorksheetId, onOpenDraft, onPublishWorksheet }: Props) {
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return worksheets;
    return worksheets.filter((worksheet) => worksheet.name.toLowerCase().includes(needle));
  }, [worksheets, query]);

  return (
    <div className="source-browser">
      <div className="source-browser-help">
        <strong>Workbook Drafts</strong>
        <span>Open any original worksheet in Draft view. Publish an excluded worksheet when it belongs in the drawing package.</span>
      </div>
      <input className="source-browser-search" type="search" placeholder="Search workbook tabs…" value={query} onChange={(event) => setQuery(event.target.value)} />
      <div className="source-browser-list">
        {filtered.map((worksheet) => {
          const linked = pages.filter((page) => page.linkedWorksheetId === worksheet.id);
          const publishedPage = linked.find((page) => page.include);
          const primary = publishedPage || linked.find((page) => !page.continuationOf) || linked[0];
          const rows = worksheet.grid?.length ?? 0;
          const cols = worksheet.grid?.reduce((max, row) => Math.max(max, row.length), 0) ?? 0;
          const state = publishedPage ? 'Published' : linked.length ? 'Excluded' : 'Source-only';
          return (
            <div
              key={worksheet.id}
              role="button"
              tabIndex={0}
              className={`source-tab-card ${worksheet.id === selectedWorksheetId ? 'active' : ''}`}
              onClick={() => onOpenDraft(worksheet.id)}
              onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onOpenDraft(worksheet.id); }}
            >
              <div className="source-tab-main">
                <span className="source-tab-name">{worksheet.name}</span>
                <span className="source-tab-meta">{rows} rows × {cols} columns{primary ? ` · ${primary.displaySheetCode || primary.sheetCode} ${primary.sheetTitle}` : ''}</span>
              </div>
              <div className="source-tab-actions" onClick={(event) => event.stopPropagation()}>
                <span className={`source-tab-state ${state.toLowerCase().replace('-', '')}`}>{state}</span>
                <button type="button" onClick={() => onOpenDraft(worksheet.id)}>Open Draft</button>
                <button type="button" className="source-publish-btn" onClick={() => onPublishWorksheet(worksheet.id)}>{publishedPage ? 'Open Published' : 'Publish'}</button>
              </div>
            </div>
          );
        })}
        {!filtered.length ? <div className="source-browser-empty">No workbook tabs match this search.</div> : null}
      </div>
    </div>
  );
}
