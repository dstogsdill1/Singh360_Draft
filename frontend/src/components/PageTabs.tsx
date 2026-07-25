import { useEffect, useRef, useState } from 'react';
import type { PageModel, ProjectModel, Worksheet } from '../model/types';
import PageNavigator from './PageNavigator';
import { pageIssueLabel, pageStatusClass } from '../model/pageStatus';
import { isCoverPage, isSheetIndexPage } from '../model/packageIndex';

interface Props {
  project: ProjectModel;
  worksheets: Worksheet[];
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
  onReorder: (pages: PageModel[]) => void;
  onRenameTitle: (id: string, title: string) => void;
  onEditCode: (id: string, code: string) => void;
  onDuplicatePage: (id: string, title: string, code: string) => void;
  onCreateBlankPage: (
    id: string,
    where: 'before' | 'after',
    title: string,
    code: string,
  ) => void;
  onToggleInclude: (id: string) => void;
  onDeletePage: (id: string) => void;
  onContextMenu: (id: string, x: number, y: number) => void;
}

export default function PageTabs({
  project,
  worksheets,
  pages,
  activePageId,
  onSelect,
  onReorder,
  onRenameTitle,
  onEditCode,
  onDuplicatePage,
  onCreateBlankPage,
  onToggleInclude,
  onDeletePage,
  onContextMenu,
}: Props) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const activeRef = useRef<HTMLDivElement | null>(null);
  const stripRef = useRef<HTMLDivElement | null>(null);
  const visible = [...pages].sort((a, b) => a.order - b.order);

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

  const startEdit = (page: PageModel) => {
    setEditId(page.id);
    setEditValue(page.sheetTitle);
  };

  const commitEdit = () => {
    if (editId) onRenameTitle(editId, editValue.trim() || 'Untitled Sheet');
    setEditId(null);
  };

  const scroll = (direction: -1 | 1) =>
    stripRef.current?.scrollBy({ left: direction * 420, behavior: 'smooth' });

  const navigator = (
    <PageNavigator
      project={project}
      worksheets={worksheets}
      pages={pages}
      activePageId={activePageId}
      onSelect={onSelect}
      onReorder={onReorder}
      onRenameTitle={onRenameTitle}
      onEditCode={onEditCode}
      onDuplicatePage={onDuplicatePage}
      onCreateBlankPage={onCreateBlankPage}
      onToggleInclude={onToggleInclude}
      onDeletePage={onDeletePage}
    />
  );

  return (
    <div className="page-tabs-shell">
      <div className="page-tabs-controls">
        {navigator}
        <button type="button" title="Scroll tabs left" onClick={() => scroll(-1)}>‹</button>
        <button type="button" title="Scroll tabs right" onClick={() => scroll(1)}>›</button>
      </div>

      <div
        className="page-tabs"
        ref={stripRef}
        onWheel={(event) => {
          if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
            stripRef.current?.scrollBy({ left: event.deltaY });
          }
        }}
      >
        {visible.map((page) => (
          <div
            key={page.id}
            role="button"
            tabIndex={0}
            ref={page.id === activePageId ? activeRef : null}
            className={`page-tab ${page.id === activePageId ? 'active' : ''} ${page.generatedContinuation ? 'cont' : ''} ${dragOverId === page.id ? 'drag-over' : ''} ${pageStatusClass(page)}`}
            onClick={() => onSelect(page.id)}
            onDoubleClick={() => startEdit(page)}
            onContextMenu={(event) => {
              event.preventDefault();
              onContextMenu(page.id, event.clientX, event.clientY);
            }}
            onKeyDown={(event) => {
              if (editId === page.id) return;
              if (event.key === 'Enter' || event.key === ' ') onSelect(page.id);
              else if (event.key === 'F2') startEdit(page);
            }}
            title={`${page.include ? 'Included' : 'Excluded'} · ${pageIssueLabel(page.issueStatus)} · Page ${page.pageNumber ?? '—'} · ${page.displaySheetCode || page.sheetCode} ${page.sheetTitle} — double-click to rename`}
            draggable={!isCoverPage(page) && !isSheetIndexPage(page) && editId !== page.id}
            onDragStart={(event) => {
              if (isCoverPage(page) || isSheetIndexPage(page)) return;
              event.dataTransfer.effectAllowed = 'move';
              event.dataTransfer.setData('text/plain', page.id);
              setDragId(page.id);
              setDragOverId(null);
            }}
            onDragOver={(event) => {
              if (!dragId || isCoverPage(page) || isSheetIndexPage(page)) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = 'move';
              setDragOverId(page.id);
            }}
            onDragLeave={() => {
              if (dragOverId === page.id) setDragOverId(null);
            }}
            onDrop={(event) => {
              event.preventDefault();
              if (dragId) reorder(dragId, page.id);
              setDragId(null);
              setDragOverId(null);
            }}
            onDragEnd={() => {
              setDragId(null);
              setDragOverId(null);
            }}
          >
            <span className={`pt-drag ${isCoverPage(page) || isSheetIndexPage(page) ? 'locked' : ''}`} aria-hidden="true">
              {isCoverPage(page) || isSheetIndexPage(page) ? 'LOCK' : '⋮⋮'}
            </span>
            {page.generatedContinuation && <span className="pt-cont">↳</span>}
            <span className="pt-page">{page.pageNumber ?? '—'}</span>
            <span className="pt-code">{page.displaySheetCode || page.sheetCode}</span>
            {editId === page.id ? (
              <input
                className="pt-title-input"
                value={editValue}
                autoFocus
                aria-label="Sheet title"
                title="Sheet title — Enter to save, Esc to cancel"
                placeholder="Sheet title"
                onClick={(event) => event.stopPropagation()}
                onChange={(event) => setEditValue(event.target.value)}
                onBlur={commitEdit}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') commitEdit();
                  else if (event.key === 'Escape') setEditId(null);
                }}
              />
            ) : (
              <span className="pt-title">{page.sheetTitle}</span>
            )}
          </div>
        ))}
      </div>

      <div className="page-tabs-controls page-tabs-controls-right">
        <button type="button" title="Scroll tabs left" onClick={() => scroll(-1)}>‹</button>
        <button type="button" title="Scroll tabs right" onClick={() => scroll(1)}>›</button>
        {navigator}
      </div>
    </div>
  );
}
