import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { PageModel, ProjectModel, Worksheet } from '../model/types';
import PageRenderer from './PageRenderer';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';
import { isCoverPage, isSheetIndexPage } from '../model/packageIndex';
import { pageStatusClass } from '../model/pageStatus';

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
}

interface PageActionState {
  pageId: string;
  title: string;
  code: string;
  newTitle: string;
  newCode: string;
}

const noop = () => {};
const PREVIEW_SCALE = 0.145;

function pageDescription(page: PageModel): string {
  return page.notes || page.sourceSheet || page.sheetTab || page.pageFamily || page.pageType;
}

function LazyPagePreview({
  project,
  page,
  worksheet,
}: {
  project: ProjectModel;
  page: PageModel;
  worksheet?: Worksheet;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (!('IntersectionObserver' in window)) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: '700px 0px' },
    );
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="page-nav-preview-viewport" ref={hostRef}>
      {visible ? (
        <div className="page-nav-preview-centering">
          <div className="page-nav-preview-sheet" style={{ transform: `scale(${PREVIEW_SCALE})` }}>
            <SheetFrame titleBlock={<TitleBlock project={project} page={page} />}>
              <PageRenderer
                page={page}
                worksheet={worksheet}
                project={project}
                viewMode="normalized"
                activeTool="select"
                snap={false}
                overlayMode={false}
                exporting
                onToolConsumed={noop}
                onRegisterApi={noop}
                onSelectionChange={noop}
                onBlockChange={noop}
                onPatchPage={noop}
                onDuplicateBlock={noop}
                onWorksheetChange={noop}
                onCanvasChange={noop}
              />
            </SheetFrame>
          </div>
        </div>
      ) : (
        <div className="page-nav-preview-loading">Loading page preview…</div>
      )}
    </div>
  );
}

export default function PageNavigator({
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
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [showExcluded, setShowExcluded] = useState(true);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [actions, setActions] = useState<PageActionState | null>(null);

  useEffect(() => {
    if (!open && !actions) return;
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (actions) setActions(null);
        else setOpen(false);
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [open, actions]);

  const listed = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...pages]
      .sort((a, b) => a.order - b.order)
      .filter((page) => showExcluded || page.include)
      .filter((page) => {
        if (!needle) return true;
        return [
          page.sheetCode,
          page.displaySheetCode,
          page.sheetTitle,
          page.sheetTab,
          page.sourceSheet,
          page.notes,
        ]
          .join(' ')
          .toLowerCase()
          .includes(needle);
      });
  }, [pages, query, showExcluded]);

  const active = pages.find((page) => page.id === activePageId);
  const actionPage = actions
    ? pages.find((page) => page.id === actions.pageId) ?? null
    : null;

  const openActions = (page: PageModel) => {
    const code = page.displaySheetCode || page.sheetCode || '';
    setActions({
      pageId: page.id,
      title: page.sheetTitle || '',
      code,
      newTitle: `${page.sheetTitle || 'New Sheet'} Copy`,
      newCode: code ? `${code} COPY` : 'NEW',
    });
  };

  const reorder = (draggedId: string, targetId: string) => {
    if (draggedId === targetId) return;
    const dragged = pages.find((page) => page.id === draggedId);
    const target = pages.find((page) => page.id === targetId);
    if (!dragged || !target) return;
    if (
      isCoverPage(dragged)
      || isSheetIndexPage(dragged)
      || isCoverPage(target)
      || isSheetIndexPage(target)
    ) return;

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
    const insertAt = remaining.findIndex(
      (page) => (page.continuationOf || page.id) === targetRoot,
    );
    if (insertAt < 0) return;

    const next = [...remaining];
    next.splice(insertAt, 0, ...moving);
    onReorder(next.map((page, index) => ({ ...page, order: index + 1 })));
  };

  const actionOverlay = actions && actionPage ? createPortal(
    <div
      className="page-nav-action-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) setActions(null);
      }}
    >
      <section className="page-nav-action-modal" role="dialog" aria-modal="true">
        <header>
          <div>
            <div className="page-nav-eyebrow">PAGE ACTIONS</div>
            <h3>{actionPage.displaySheetCode || actionPage.sheetCode || 'NO CODE'} — {actionPage.sheetTitle}</h3>
            <p>Edit, duplicate, add, include/exclude, or delete without leaving the Visual Page Manager.</p>
          </div>
          <button type="button" onClick={() => setActions(null)}>Close</button>
        </header>

        <div className="page-nav-action-body">
          <section className="page-nav-action-section">
            <h4>Edit selected page</h4>
            <label>
              Sheet code
              <input
                value={actions.code}
                onChange={(event) => setActions((current) => current ? { ...current, code: event.target.value } : current)}
              />
            </label>
            <label>
              Sheet title
              <input
                value={actions.title}
                onChange={(event) => setActions((current) => current ? { ...current, title: event.target.value } : current)}
              />
            </label>
            <div className="page-nav-action-buttons">
              <button
                type="button"
                className="primary"
                onClick={() => {
                  onEditCode(actionPage.id, actions.code.trim());
                  onRenameTitle(actionPage.id, actions.title.trim() || 'Untitled Sheet');
                  setActions(null);
                }}
              >
                Save Name + Code
              </button>
              <button
                type="button"
                onClick={() => {
                  onSelect(actionPage.id);
                  setActions(null);
                  setOpen(false);
                }}
              >
                Open Page
              </button>
              <button
                type="button"
                onClick={() => {
                  onToggleInclude(actionPage.id);
                  setActions(null);
                }}
              >
                {actionPage.include ? 'Exclude Page' : 'Include Page'}
              </button>
            </div>
          </section>

          <section className="page-nav-action-section">
            <h4>Duplicate or add a page</h4>
            <label>
              New sheet code
              <input
                value={actions.newCode}
                onChange={(event) => setActions((current) => current ? { ...current, newCode: event.target.value } : current)}
              />
            </label>
            <label>
              New sheet title
              <input
                value={actions.newTitle}
                onChange={(event) => setActions((current) => current ? { ...current, newTitle: event.target.value } : current)}
              />
            </label>
            <div className="page-nav-action-buttons">
              <button
                type="button"
                className="primary"
                onClick={() => {
                  onDuplicatePage(
                    actionPage.id,
                    actions.newTitle.trim() || `${actionPage.sheetTitle} Copy`,
                    actions.newCode.trim() || 'NEW',
                  );
                  setActions(null);
                }}
              >
                Duplicate With These Fields
              </button>
              <button
                type="button"
                onClick={() => {
                  onCreateBlankPage(
                    actionPage.id,
                    'before',
                    actions.newTitle.trim() || 'New Sheet',
                    actions.newCode.trim() || 'NEW',
                  );
                  setActions(null);
                }}
              >
                Add Blank Before
              </button>
              <button
                type="button"
                onClick={() => {
                  onCreateBlankPage(
                    actionPage.id,
                    'after',
                    actions.newTitle.trim() || 'New Sheet',
                    actions.newCode.trim() || 'NEW',
                  );
                  setActions(null);
                }}
              >
                Add Blank After
              </button>
            </div>
          </section>

          <section className="page-nav-action-section danger">
            <h4>Delete</h4>
            <p>This removes the page from the local project. Use Backups / Recover if you need to restore it.</p>
            <button
              type="button"
              disabled={isCoverPage(actionPage) || isSheetIndexPage(actionPage)}
              onClick={() => {
                const label = `${actionPage.displaySheetCode || actionPage.sheetCode} ${actionPage.sheetTitle}`.trim();
                if (!window.confirm(`Delete "${label}" from this project?`)) return;
                onDeletePage(actionPage.id);
                setActions(null);
              }}
            >
              Delete Page
            </button>
          </section>
        </div>

        <footer>
          Local edits autosave. Click <b>SAVE + WRITE EXCEL</b> when you want new or renamed pages mirrored to 00_INDEX and workbook tabs.
        </footer>
      </section>
    </div>,
    document.body,
  ) : null;

  const modal = open ? createPortal(
    <div
      className="page-nav-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) setOpen(false);
      }}
    >
      <section className="page-nav-modal" role="dialog" aria-modal="true" aria-label="Visual Page Manager">
        <header className="page-nav-modal-head">
          <div>
            <div className="page-nav-eyebrow">VISUAL PAGE MANAGER</div>
            <h2>All Drawing Pages</h2>
            <p>
              {pages.filter((page) => page.include).length} published · {pages.length} total ·
              click to open · drag to reorder · right-click for page actions
            </p>
          </div>
          <button type="button" className="page-nav-close" onClick={() => setOpen(false)}>Close</button>
        </header>

        <div className="page-nav-modal-tools">
          <input
            autoFocus
            type="search"
            placeholder="Search sheet code, title, worksheet, or note…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <label>
            <input
              type="checkbox"
              checked={showExcluded}
              onChange={(event) => setShowExcluded(event.target.checked)}
            />
            Show excluded/source-only pages
          </label>
          <span className="page-nav-drag-help">Right-click any card to edit, duplicate, add, include/exclude, or delete.</span>
        </div>

        <div className="page-nav-card-grid">
          {listed.map((page) => {
            const locked = isCoverPage(page) || isSheetIndexPage(page);
            const worksheet = worksheets.find((item) => item.id === page.linkedWorksheetId);
            return (
              <article
                key={page.id}
                className={[
                  'page-nav-card',
                  page.id === activePageId ? 'active' : '',
                  page.include ? '' : 'excluded',
                  pageStatusClass(page),
                  dragOverId === page.id ? 'drag-over' : '',
                ].filter(Boolean).join(' ')}
                draggable={!locked}
                onContextMenu={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  openActions(page);
                }}
                onDragStart={(event) => {
                  if (locked) return;
                  event.dataTransfer.effectAllowed = 'move';
                  event.dataTransfer.setData('text/plain', page.id);
                  setDragId(page.id);
                  setDragOverId(null);
                }}
                onDragOver={(event) => {
                  if (!dragId || locked) return;
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
                <button
                  type="button"
                  className="page-nav-card-open"
                  onClick={() => {
                    onSelect(page.id);
                    setOpen(false);
                  }}
                >
                  <LazyPagePreview project={project} page={page} worksheet={worksheet} />
                  <div className="page-nav-card-copy">
                    <span className="page-nav-card-order">{page.pageNumber ?? '—'}</span>
                    <span>
                      <b>{page.displaySheetCode || page.sheetCode || 'NO CODE'}</b>
                      <strong>{page.sheetTitle}</strong>
                      <small>{pageDescription(page)}</small>
                    </span>
                  </div>
                </button>
                <footer className="page-nav-card-footer">
                  <span className={page.include ? 'published' : 'source-only'}>
                    {page.include ? 'Published' : 'Excluded'}
                  </span>
                  {page.generatedContinuation || page.continuationOf ? <span>Continuation</span> : null}
                  <span className={locked ? 'locked' : 'movable'}>
                    {locked ? 'Locked' : 'Right-click · drag reorder'}
                  </span>
                </footer>
              </article>
            );
          })}
          {!listed.length ? <div className="page-nav-empty">No pages match this search.</div> : null}
        </div>
      </section>
    </div>,
    document.body,
  ) : null;

  return (
    <div className="page-nav">
      <button
        type="button"
        className={`page-nav-button ${open ? 'active' : ''}`}
        title="Open visual page manager"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="page-nav-hamburger">☰</span>
        <span className="page-nav-current">{active?.pageNumber ?? '—'}</span>
      </button>
      {modal}
      {actionOverlay}
    </div>
  );
}
