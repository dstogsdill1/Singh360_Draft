import { useState } from 'react';
import type { PageModel } from '../model/types';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
  onReorder: (pages: PageModel[]) => void;
}

export default function PageTabs({ pages, activePageId, onSelect, onReorder }: Props) {
  const [dragId, setDragId] = useState<string | null>(null);
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

  return (
    <div className="page-tabs">
      {included.map((p) => (
        <button
          key={p.id}
          className={`page-tab ${p.id === activePageId ? 'active' : ''} ${p.generatedContinuation ? 'cont' : ''}`}
          onClick={() => onSelect(p.id)}
          title={`${p.displaySheetCode || p.sheetCode} ${p.sheetTitle}`}
          draggable
          onDragStart={() => setDragId(p.id)}
          onDragOver={(e) => e.preventDefault()}
          onDrop={() => {
            if (dragId) reorder(dragId, p.id);
            setDragId(null);
          }}
        >
          {p.generatedContinuation && <span className="pt-cont">↳</span>}
          <span className="pt-code">{p.displaySheetCode || p.sheetCode}</span>
          <span className="pt-title">{p.sheetTitle}</span>
        </button>
      ))}
    </div>
  );
}
