import { useState, type DragEvent } from 'react';
import type { PageModel } from '../model/types';
import { PAGE_ISSUE_STATUSES, normalizePageIssueStatus, pageStatusClass } from '../model/pageStatus';
import { PAGE_TEMPLATES, applyTemplate, templateForPage, type PageTemplate } from '../model/pageTemplates';
import { isCoverPage, isSheetIndexPage } from '../model/packageIndex';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
  onUpdate: (next: PageModel[]) => void;
  onToggleInclude: (id: string) => void;
  onContextMenu: (id: string, x: number, y: number) => void;
}

export default function SheetManager({ pages, activePageId, onSelect, onUpdate, onToggleInclude, onContextMenu }: Props) {
  const [edit, setEdit] = useState<{ id: string; field: 'code' | 'title'; value: string } | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);

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


  const reorderByDrop = (draggedId: string, targetId: string) => {
    if (draggedId === targetId) return;
    const dragged = pages.find((page) => page.id === draggedId);
    const target = pages.find((page) => page.id === targetId);
    if (!dragged || !target) return;
    if (isCoverPage(dragged) || isSheetIndexPage(dragged) || isCoverPage(target) || isSheetIndexPage(target)) return;

    const draggedRoot = dragged.continuationOf || dragged.id;
    const targetRoot = target.continuationOf || target.id;
    if (draggedRoot === targetRoot) return;

    const movingIds = new Set(
      pages
        .filter((page) => page.id === draggedRoot || page.continuationOf === draggedRoot)
        .map((page) => page.id),
    );
    const moving = pages.filter((page) => movingIds.has(page.id));
    const remaining = pages.filter((page) => !movingIds.has(page.id));
    const insertAt = remaining.findIndex((page) => (page.continuationOf || page.id) === targetRoot);
    if (insertAt < 0) return;
    const next = [...remaining];
    next.splice(insertAt, 0, ...moving);
    onUpdate(next.map((page, index) => ({ ...page, order: index + 1 })));
  };

  const finishDrop = (targetId: string) => {
    if (dragId) reorderByDrop(dragId, targetId);
    setDragId(null);
    setDragOverId(null);
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
            className={`sheet-item ${p.id === activePageId ? 'active' : ''} ${isCont ? 'cont' : ''} ${dragOverId === p.id ? 'drag-over' : ''} ${pageStatusClass(p)}`}
            onClick={() => onSelect(p.id)}
            onDragOver={(event) => {
              if (!dragId || isCoverPage(p) || isSheetIndexPage(p)) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = 'move';
              setDragOverId(p.id);
            }}
            onDragLeave={() => {
              if (dragOverId === p.id) setDragOverId(null);
            }}
            onDrop={(event) => {
              event.preventDefault();
              event.stopPropagation();
              finishDrop(p.id);
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              onContextMenu(p.id, e.clientX, e.clientY);
            }}
          >
            <div className="sheet-item-head">
              <button
                type="button"
                className={`sheet-drag-handle ${isCoverPage(p) || isSheetIndexPage(p) ? 'locked' : ''}`}
                draggable={!isCoverPage(p) && !isSheetIndexPage(p)}
                disabled={isCoverPage(p) || isSheetIndexPage(p)}
                title={isCoverPage(p) || isSheetIndexPage(p) ? 'Cover and Sheet Index stay first' : 'Drag this page to a new package position'}
                aria-label={`Drag ${p.sheetTitle}`}
                onClick={(event) => event.stopPropagation()}
                onDragStart={(event: DragEvent<HTMLButtonElement>) => {
                  if (isCoverPage(p) || isSheetIndexPage(p)) return;
                  event.stopPropagation();
                  event.dataTransfer.effectAllowed = 'move';
                  event.dataTransfer.setData('text/plain', p.id);
                  setDragId(p.id);
                  setDragOverId(null);
                }}
                onDragEnd={() => {
                  setDragId(null);
                  setDragOverId(null);
                }}
              >
                {isCoverPage(p) || isSheetIndexPage(p) ? 'LOCK' : '⋮⋮'}
              </button>
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
              <select
                className="sheet-status-select"
                title="Page issue status"
                value={normalizePageIssueStatus(p.issueStatus)}
                onChange={(e) => patch(idx, {
                  issueStatus: e.target.value as PageModel['issueStatus'],
                  statusUpdatedAt: new Date().toISOString(),
                  statusConfirmedAt: e.target.value.endsWith('_confirmed') ? new Date().toISOString() : undefined,
                })}
              >
                {PAGE_ISSUE_STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.confirmed ? '✓ ' : ''}{status.label}
                  </option>
                ))}
              </select>
              <label title="Include this page in the drawing set">
                <input
                  type="checkbox"
                  checked={p.include}
                  onChange={() => onToggleInclude(p.id)}
                />
                include in drawing set
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
