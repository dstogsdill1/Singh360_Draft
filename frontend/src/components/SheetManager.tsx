import { useState } from 'react';
import type { PageModel } from '../model/types';
import { PAGE_TEMPLATES, applyTemplate, templateForPage, type PageTemplate } from '../model/pageTemplates';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
  onUpdate: (next: PageModel[]) => void;
}

export default function SheetManager({ pages, activePageId, onSelect, onUpdate }: Props) {
  const [edit, setEdit] = useState<{ id: string; field: 'code' | 'title'; value: string } | null>(null);

  const patch = (idx: number, p: Partial<PageModel>) => {
    const clone = [...pages];
    clone[idx] = { ...clone[idx], ...p };
    onUpdate(clone);
  };

  const move = (idx: number, dir: -1 | 1) => {
    const t = idx + dir;
    if (t < 0 || t >= pages.length) return;
    const clone = [...pages];
    [clone[idx], clone[t]] = [clone[t], clone[idx]];
    clone.forEach((p, i) => (p.order = i + 1));
    onUpdate(clone);
  };

  const commit = (idx: number) => {
    if (!edit) return;
    const val = edit.value.trim();
    if (edit.field === 'code') patch(idx, { sheetCode: val, displaySheetCode: val });
    else patch(idx, { sheetTitle: val || 'Untitled Sheet' });
    setEdit(null);
  };

  return (
    <>
      {pages.map((p, idx) => {
        const isCont = !!p.continuationOf || !!p.generatedContinuation;
        return (
          <div
            key={p.id}
            className={`sheet-item ${p.id === activePageId ? 'active' : ''} ${isCont ? 'cont' : ''}`}
            onClick={() => onSelect(p.id)}
          >
            <div className="sheet-item-head">
              {edit && edit.id === p.id && edit.field === 'code' ? (
                <input
                  className="sheet-inline-input code"
                  value={edit.value}
                  autoFocus
                  aria-label="Sheet code"
                  title="Sheet code"
                  placeholder="Code"
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setEdit({ ...edit, value: e.target.value })}
                  onBlur={() => commit(idx)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commit(idx);
                    else if (e.key === 'Escape') setEdit(null);
                  }}
                />
              ) : (
                <span
                  className="sheet-item-code"
                  title="Double-click to edit sheet code"
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setEdit({ id: p.id, field: 'code', value: p.displaySheetCode || p.sheetCode });
                  }}
                >
                  {p.displaySheetCode || p.sheetCode}
                </span>
              )}
              {edit && edit.id === p.id && edit.field === 'title' ? (
                <input
                  className="sheet-inline-input title"
                  value={edit.value}
                  autoFocus
                  aria-label="Sheet title"
                  title="Sheet title"
                  placeholder="Sheet title"
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setEdit({ ...edit, value: e.target.value })}
                  onBlur={() => commit(idx)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commit(idx);
                    else if (e.key === 'Escape') setEdit(null);
                  }}
                />
              ) : (
                <span
                  className="sheet-item-title"
                  title="Double-click to edit sheet title"
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    setEdit({ id: p.id, field: 'title', value: p.sheetTitle });
                  }}
                >
                  {isCont && <span className="cont-mark" title="Continuation page">↳ </span>}
                  {p.sheetTitle}
                </span>
              )}
              <div className="sheet-item-actions" onClick={(e) => e.stopPropagation()}>
                <button className="reorder-btn" title="Move up" onClick={() => move(idx, -1)}>↑</button>
                <button className="reorder-btn" title="Move down" onClick={() => move(idx, 1)}>↓</button>
              </div>
            </div>

            {isCont && (
              <div className="sheet-cont-banner" onClick={(e) => e.stopPropagation()}>
                <span title="This page continues the previous sheet">Continuation of previous sheet</span>
                <button
                  className="cont-convert-btn"
                  title="Convert this continuation into an independent page with its own sheet code"
                  onClick={() => patch(idx, { continuationOf: null, generatedContinuation: false, continuationIndex: undefined })}
                >
                  Make independent
                </button>
              </div>
            )}

            <div className="sheet-item-meta" onClick={(e) => e.stopPropagation()}>
              <label title="Include this page in the exported package">
                <input
                  type="checkbox"
                  checked={p.include}
                  onChange={(e) => patch(idx, { include: e.target.checked })}
                />
                include
              </label>
              <select
                className="sheet-item-type"
                title="Page template"
                value={templateForPage(p)}
                onChange={(e) => onUpdate(pages.map((pg, i) => (i === idx ? applyTemplate(pg, e.target.value as PageTemplate) : pg)))}
              >
                {PAGE_TEMPLATES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>
        );
      })}
    </>
  );
}
