import { useState } from 'react';
import type { PageModel } from '../model/types';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
  onReorder: (pages: PageModel[]) => void;
  onRenameTitle: (id: string, title: string) => void;
}

export default function PageTabs({ pages, activePageId, onSelect, onReorder, onRenameTitle }: Props) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const included = pages.filter((p) => p.include);

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

  return (
    <div className="page-tabs">
      {included.map((p) => (
        <div
          key={p.id}
          role="button"
          tabIndex={0}
          className={`page-tab ${p.id === activePageId ? 'active' : ''} ${p.generatedContinuation ? 'cont' : ''}`}
          onClick={() => onSelect(p.id)}
          onDoubleClick={() => startEdit(p)}
          onKeyDown={(e) => {
            if (editId === p.id) return;
            if (e.key === 'Enter' || e.key === ' ') onSelect(p.id);
            else if (e.key === 'F2') startEdit(p);
          }}
          title={`${p.displaySheetCode || p.sheetCode} ${p.sheetTitle} — double-click to rename`}
          draggable={editId !== p.id}
          onDragStart={() => setDragId(p.id)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={() => {
            if (dragId) reorder(dragId, p.id);
            setDragId(null);
          }}
        >
          {p.generatedContinuation && <span className="pt-cont">↳</span>}
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
  );
}
