import { useEffect, useRef, useState } from 'react';
import type { PageModel } from '../model/types';
import PageNavigator from './PageNavigator';

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
    const next = [...pages];
    const from = next.findIndex((p) => p.id === draggedId);
    const to = next.findIndex((p) => p.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = next.splice(from, 1);
    const insertAt = next.findIndex((p) => p.id === targetId);
    next.splice(insertAt, 0, moved);
    next.forEach((p, i) => (p.order = i + 1));
    onReorder(next);
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
            className={`page-tab ${p.id === activePageId ? 'active' : ''} ${p.generatedContinuation ? 'cont' : ''}`}
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
            draggable={editId !== p.id}
            onDragStart={() => setDragId(p.id)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => {
              if (dragId) reorder(dragId, p.id);
              setDragId(null);
            }}
          >
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
