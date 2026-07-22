import { useEffect, useRef, useState } from 'react';
import type { PageModel } from '../model/types';
import PageNavigator from './PageNavigator';
import { isCoverPage, isSheetIndexPage } from '../model/packageIndex';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
  onReorder: (pages: PageModel[]) => void;
  onRenameTitle: (id: string, title: string) => void;
  onContextMenu: (id: string, x: number, y: number) => void;
}

export default function PageTabs({ pages, activePageId, onSelect, onReorder, onRenameTitle, onContextMenu }: Props) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const activeRef = useRef<HTMLDivElement | null>(null);
  const stripRef = useRef<HTMLDivElement | null>(null);
  const included = pages.filter((p) => p.include);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: 'smooth' });
  }, [activePageId]);

  const reorder = (draggedId: string, targetId: string) => {
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
    onReorder(next.map((page, index) => ({ ...page, order: index + 1 })));
  };

  const startEdit = (p: PageModel) => {
    setEditId(p.id);
    setEditValue(p.sheetTitle);
  };
  const commitEdit = () => {
    if (editId) onRenameTitle(editId, editValue.trim() || 'Untitled Sheet');
    setEditId(null);
  };

  const scroll = (direction: -1 | 1) => stripRef.current?.scrollBy({ left: direction * 420, behavior: 'smooth' });

  return (
    <div className="page-tabs-shell">
      <div className="page-tabs-controls">
        <PageNavigator pages={pages} activePageId={activePageId} onSelect={onSelect} />
        <button type="button" title="Scroll tabs left" onClick={() => scroll(-1)}>‹</button>
        <button type="button" title="Scroll tabs right" onClick={() => scroll(1)}>›</button>
      </div>
      <div
        className="page-tabs"
        ref={stripRef}
        onWheel={(event) => {
          if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) stripRef.current?.scrollBy({ left: event.deltaY });
        }}
      >
        {included.map((p) => (
          <div
            key={p.id}
            role="button"
            tabIndex={0}
            ref={p.id === activePageId ? activeRef : null}
            className={`page-tab ${p.id === activePageId ? 'active' : ''} ${p.generatedContinuation ? 'cont' : ''} ${dragOverId === p.id ? 'drag-over' : ''}`}
            onClick={() => onSelect(p.id)}
            onDoubleClick={() => startEdit(p)}
            onContextMenu={(e) => {
              e.preventDefault();
              onContextMenu(p.id, e.clientX, e.clientY);
            }}
            onKeyDown={(e) => {
              if (editId === p.id) return;
              if (e.key === 'Enter' || e.key === ' ') onSelect(p.id);
              else if (e.key === 'F2') startEdit(p);
            }}
            title={`Page ${p.pageNumber ?? '—'} · ${p.displaySheetCode || p.sheetCode} ${p.sheetTitle} — double-click to rename`}
            draggable={!isCoverPage(p) && !isSheetIndexPage(p) && editId !== p.id}

            onDragStart={(event) => {
              if (isCoverPage(p) || isSheetIndexPage(p)) return;
              event.dataTransfer.effectAllowed = 'move';
              event.dataTransfer.setData('text/plain', p.id);
              setDragId(p.id);
              setDragOverId(null);
            }}
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
              if (dragId) reorder(dragId, p.id);
              setDragId(null);
              setDragOverId(null);
            }}
            onDragEnd={() => {
              setDragId(null);
              setDragOverId(null);
            }}
          >
            <span className={`pt-drag ${isCoverPage(p) || isSheetIndexPage(p) ? 'locked' : ''}`} aria-hidden="true">{isCoverPage(p) || isSheetIndexPage(p) ? 'LOCK' : '⋮⋮'}</span>
            {p.generatedContinuation && <span className="pt-cont">↳</span>}
            <span className="pt-page">{p.pageNumber ?? '—'}</span>
            <span className="pt-code">{p.displaySheetCode || p.sheetCode}</span>
            {editId === p.id ? (
              <input
                className="pt-title-input"
                value={editValue}
                autoFocus
                aria-label="Sheet title"
                title="Sheet title — Enter to save, Esc to cancel"
                placeholder="Sheet title"
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitEdit();
                  else if (e.key === 'Escape') setEditId(null);
                }}
              />
            ) : (
              <span className="pt-title">{p.sheetTitle}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
