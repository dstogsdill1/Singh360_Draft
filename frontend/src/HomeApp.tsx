import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  getProject,
  listProjects,
  saveProject,
  type ProjectListItem,
} from './api/client';
import ContinuationPreviewModal from './components/ContinuationPreviewModal';
import type { PageIssueStatus, PageModel, ProjectModel } from './model/types';

type PageFilter = 'all' | 'included' | 'excluded';
type ProjectWithSaveTime = ProjectModel & { lastSavedAt?: string };

function currentParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    projectId: params.get('project'),
    review: params.get('review') === '1',
  };
}

function projectName(project: ProjectModel): string {
  return project.projectDisplayName
    || project.metadata.projectName
    || project.sourceWorkbookName
    || 'Untitled Project';
}

function requiredPage(page: PageModel): boolean {
  return page.pageType === 'cover' || page.pageType === 'index';
}

function pageCode(page: PageModel): string {
  return page.displaySheetCode || page.sheetCode || '—';
}

function formatDate(value?: string): string {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function looksTemporaryWorkbook(name?: string): boolean {
  return /^(?:temp|preview)_[a-f0-9]{16}\.(?:xlsx|xlsm)$/i.test((name || '').trim());
}

function statusLabel(status?: PageIssueStatus): string {
  if (status === 'draft_confirmed') return 'Draft Confirmed';
  if (status === 'public') return 'Public';
  if (status === 'public_confirmed') return 'Public Confirmed';
  return 'Draft';
}

function openComponentBuilder(): void {
  window.open('/component-catalog', '_blank', 'noopener,noreferrer');
}

function editorUrl(projectId: string, action?: 'symbol-mapper' | 'symbol-legend'): string {
  const params = new URLSearchParams({ project: projectId, editor: '1' });
  if (action === 'symbol-mapper') params.set('openSymbolMapper', '1');
  if (action === 'symbol-legend') params.set('openSymbolLegend', '1');
  return `/app?${params.toString()}`;
}

export default function HomeApp() {
  const initial = useMemo(currentParams, []);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [currentProject, setCurrentProject] = useState<ProjectModel | null>(null);
  const [reviewProject, setReviewProject] = useState<ProjectModel | null>(null);
  const [reviewPages, setReviewPages] = useState<PageModel[]>([]);
  const [pendingWorkbookFile, setPendingWorkbookFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<PageFilter>('all');

  useEffect(() => {
    document.documentElement.classList.add('s360-home-mode');
    return () => document.documentElement.classList.remove('s360-home-mode');
  }, []);

  const hydrateProjectRows = useCallback(async (rows: ProjectListItem[]): Promise<ProjectListItem[]> => {
    return Promise.all(rows.map(async (row) => {
      if (row.sourceWorkbook && !looksTemporaryWorkbook(row.sourceWorkbook)) return row;
      try {
        const project = await getProject(row.id);
        return {
          ...row,
          projectName: projectName(project),
          sourceWorkbook: project.sourceWorkbookName || project.metadata.sourceFile || row.sourceWorkbook,
          modified: (project as ProjectWithSaveTime).lastSavedAt || project.modified || row.modified,
          lastSavedAt: (project as ProjectWithSaveTime).lastSavedAt || row.lastSavedAt,
        };
      } catch {
        return row;
      }
    }));
  }, []);

  const refreshProjects = useCallback(async () => {
    const rows = await listProjects();
    setProjects(await hydrateProjectRows(rows));
  }, [hydrateProjectRows]);

  const beginReview = useCallback((project: ProjectModel) => {
    setReviewProject(project);
    setReviewPages(project.pages.map((page) => ({
      ...page,
      include: requiredPage(page) ? true : page.include,
    })));
    setQuery('');
    setFilter('all');
    window.history.replaceState({}, '', `/app?project=${encodeURIComponent(project.id)}&review=1`);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const rows = await listProjects();
        if (cancelled) return;
        setProjects(await hydrateProjectRows(rows));
        if (initial.projectId) {
          const project = await getProject(initial.projectId);
          if (cancelled) return;
          setCurrentProject(project);
          if (initial.review) beginReview(project);
        }
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [beginReview, hydrateProjectRows, initial.projectId, initial.review]);

  const loadProject = useCallback(async (id: string): Promise<ProjectModel | null> => {
    setSyncing(true);
    setError('');
    try {
      // GET /api/projects/:id performs the workbook-to-app manifest check before
      // the project is shown or the editor is opened.
      const project = await getProject(id);
      setCurrentProject(project);
      window.history.replaceState({}, '', `/app?project=${encodeURIComponent(id)}`);
      return project;
    } catch (loadError) {
      setError(errorMessage(loadError));
      return null;
    } finally {
      setSyncing(false);
    }
  }, []);

  const refreshCurrentProject = useCallback(async () => {
    if (!currentProject) return;
    await loadProject(currentProject.id);
    await refreshProjects();
  }, [currentProject, loadProject, refreshProjects]);

  const openEditor = useCallback(async (
    projectId: string,
    action?: 'symbol-mapper' | 'symbol-legend',
  ) => {
    const checked = await loadProject(projectId);
    if (!checked) return;
    window.location.assign(editorUrl(projectId, action));
  }, [loadProject]);

  const finishWorkbookImport = useCallback(async (projectId: string) => {
    setPendingWorkbookFile(null);
    const project = await loadProject(projectId);
    if (!project) return;
    await refreshProjects();
    beginReview(project);
  }, [beginReview, loadProject, refreshProjects]);

  const filteredPages = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...reviewPages]
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .filter((page) => {
        if (filter === 'included' && !page.include) return false;
        if (filter === 'excluded' && page.include) return false;
        if (!needle) return true;
        return [
          pageCode(page), page.sheetTitle, page.sheetTab, page.pageFamily,
          page.pageType, page.sourceMode, statusLabel(page.issueStatus),
        ].some((value) => String(value || '').toLowerCase().includes(needle));
      });
  }, [filter, query, reviewPages]);

  const patchInclude = useCallback((id: string, include: boolean) => {
    setReviewPages((pages) => pages.map((page) => (
      page.id === id && !requiredPage(page) ? { ...page, include } : page
    )));
  }, []);

  const patchVisible = useCallback((include: boolean) => {
    const visibleIds = new Set(filteredPages.map((page) => page.id));
    setReviewPages((pages) => pages.map((page) => (
      visibleIds.has(page.id) && !requiredPage(page) ? { ...page, include } : page
    )));
  }, [filteredPages]);

  const saveSelectionAndOpen = useCallback(async () => {
    if (!reviewProject) return;
    setSaving(true);
    setError('');
    try {
      const reviewed = new Map(reviewPages.map((page) => [page.id, page]));
      const next: ProjectModel = {
        ...reviewProject,
        pages: reviewProject.pages.map((page) => ({
          ...page,
          include: requiredPage(page) ? true : (reviewed.get(page.id)?.include ?? page.include),
        })),
      };
      // The existing save endpoint writes supported page-manifest changes back to
      // the linked workbook and returns the synchronized project.
      await saveProject(next);
      window.location.assign(editorUrl(next.id));
    } catch (saveError) {
      setError(errorMessage(saveError));
      setSaving(false);
    }
  }, [reviewPages, reviewProject]);

  const returnToProjectHome = useCallback(() => {
    const project = reviewProject || currentProject;
    setReviewProject(null);
    setReviewPages([]);
    setQuery('');
    setFilter('all');
    if (project) {
      setCurrentProject(project);
      window.history.replaceState({}, '', `/app?project=${encodeURIComponent(project.id)}`);
    } else {
      window.history.replaceState({}, '', '/app');
    }
  }, [currentProject, reviewProject]);

  const includedReviewCount = reviewPages.filter((page) => page.include || requiredPage(page)).length;

  let content: ReactNode;

  if (loading) {
    content = (
      <main className="home-shell home-loading">
        <div className="home-spinner" aria-hidden="true" />
        <p>Loading Singh360 Draft…</p>
      </main>
    );
  } else if (reviewProject) {
    content = (
      <main className="home-shell review-shell">
        <header className="home-topbar">
          <div>
            <div className="home-brand">SINGH360 DRAFT</div>
            <h1>Review Drawing Pages</h1>
            <p>{projectName(reviewProject)}</p>
          </div>
          <button className="home-button ghost light" type="button" onClick={returnToProjectHome}>Project Home</button>
        </header>

        {error && <div className="home-alert error" role="alert">{error}</div>}

        <section className="review-summary" aria-label="Page review summary">
          <div><strong>{reviewPages.length}</strong><span>Total editor pages</span></div>
          <div><strong>{includedReviewCount}</strong><span>Included</span></div>
          <div><strong>{reviewPages.length - includedReviewCount}</strong><span>Excluded / source-only</span></div>
          <div><strong>{reviewProject.worksheets.length}</strong><span>Workbook drafts</span></div>
        </section>

        <section className="review-card">
          <div className="review-toolbar">
            <label className="review-search">
              <span>Search pages</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Code, title, tab, family, status…"
              />
            </label>
            <div className="review-filter-stack">
              <div className="review-filters" aria-label="Page filter">
                {(['all', 'included', 'excluded'] as PageFilter[]).map((value) => (
                  <button
                    type="button"
                    key={value}
                    className={filter === value ? 'active' : ''}
                    onClick={() => setFilter(value)}
                  >
                    {value[0].toUpperCase() + value.slice(1)}
                  </button>
                ))}
              </div>
              <div className="review-bulk-actions">
                <button type="button" onClick={() => patchVisible(true)}>Include visible</button>
                <button type="button" onClick={() => patchVisible(false)}>Exclude visible</button>
              </div>
            </div>
          </div>

          <div className="review-table-wrap" tabIndex={0} aria-label="Scrollable drawing page review table">
            <table className="review-table">
              <thead>
                <tr>
                  <th className="include-col">Include</th>
                  <th className="order-col">Order</th>
                  <th className="code-col">Sheet</th>
                  <th>Page title</th>
                  <th>Workbook tab / source</th>
                  <th className="status-col">Issue status</th>
                  <th className="type-col">Type</th>
                </tr>
              </thead>
              <tbody>
                {filteredPages.map((page) => {
                  const required = requiredPage(page);
                  return (
                    <tr key={page.id} className={!page.include ? 'excluded' : ''}>
                      <td className="include-col">
                        <label className="include-toggle" title={required ? 'Cover and Sheet Index are required published pages.' : 'Include this page in the published package'}>
                          <input
                            type="checkbox"
                            checked={required || page.include}
                            disabled={required}
                            onChange={(event) => patchInclude(page.id, event.target.checked)}
                          />
                          <span>{required ? 'Required' : (page.include ? 'Yes' : 'No')}</span>
                        </label>
                      </td>
                      <td className="order-col">{page.order}</td>
                      <td className="code-col"><strong>{pageCode(page)}</strong></td>
                      <td>
                        <strong>{page.sheetTitle || 'Untitled page'}</strong>
                        <small>{page.pageFamily || page.sourceMode || ''}</small>
                      </td>
                      <td>{page.sheetTab || page.sourceSheet || 'App-owned page'}</td>
                      <td className="status-col"><span className={`issue-pill ${page.issueStatus || 'draft'}`}>{statusLabel(page.issueStatus)}</span></td>
                      <td className="type-col"><span className="type-pill">{page.pageType}</span></td>
                    </tr>
                  );
                })}
                {filteredPages.length === 0 && (
                  <tr><td colSpan={7} className="review-empty">No pages match this filter.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <footer className="review-footer">
            <div>
              <strong>{filteredPages.length} page{filteredPages.length === 1 ? '' : 's'} shown</strong>
              <span>Scroll inside the table to review the complete drawing package.</span>
            </div>
            <button className="home-button primary wide" type="button" disabled={saving} onClick={() => void saveSelectionAndOpen()}>
              {saving ? 'Saving project and workbook…' : 'Save & Open Page Editor'}
            </button>
          </footer>
        </section>
      </main>
    );
  } else if (currentProject) {
    const included = currentProject.pages.filter((page) => page.include).length;
    const excluded = currentProject.pages.length - included;
    const workbook = currentProject.workbookSync?.workbook
      || currentProject.sourceWorkbookName
      || currentProject.metadata.sourceFile
      || 'No linked workbook was found';
    const syncWarning = currentProject.workbookSync?.warning || '';
    const syncState = syncWarning
      ? 'Workbook check needs attention'
      : currentProject.workbookSync?.lastSyncUtc
        ? 'Workbook synchronized'
        : 'Workbook linked — first sync not recorded';
    const lastProjectSave = (currentProject as ProjectWithSaveTime).lastSavedAt || currentProject.modified;

    content = (
      <main className="home-shell project-home-shell">
        <header className="home-topbar">
          <div>
            <div className="home-brand">SINGH360 DRAFT</div>
            <h1>{projectName(currentProject)}</h1>
            <p>{[
              currentProject.metadata.client,
              currentProject.metadata.storeNumber,
              currentProject.metadata.location || currentProject.metadata.address,
            ].filter(Boolean).join(' · ') || 'Drawing package project'}</p>
          </div>
          <div className="home-header-actions">
            <button className="home-button ghost light" type="button" onClick={openComponentBuilder}>Component Builder</button>
            <button className="home-button ghost light" type="button" onClick={() => window.location.assign('/app')}>All Projects</button>
          </div>
        </header>

        {error && <div className="home-alert error" role="alert">{error}</div>}
        {syncWarning && (
          <div className="home-alert warning" role="alert">
            <strong>Workbook synchronization warning</strong>
            <span>{syncWarning}</span>
          </div>
        )}

        <section className="project-intro-card">
          <div>
            <span className="eyebrow">PROJECT HOME</span>
            <h2>Choose the work you need to do</h2>
            <p>The workbook manifest is checked when this project home opens and checked again before the Page Editor opens. Manual drawings, images, crops, connectors, and app-only objects remain project-owned.</p>
          </div>
          <span className={`sync-badge ${syncWarning ? 'warning' : 'ok'}`}>{syncing ? 'Checking workbook…' : syncState}</span>
        </section>

        <section className="project-tool-grid" aria-label="Project tools">
          <button className="project-tool-card primary" type="button" disabled={syncing} onClick={() => void openEditor(currentProject.id)}>
            <span className="tool-icon">▣</span>
            <strong>Open Page Editor</strong>
            <small>Drawing pages, source drafts, overlays, connectors, undo/redo, File tools, and PDF export.</small>
          </button>
          <button className="project-tool-card" type="button" onClick={() => beginReview(currentProject)}>
            <span className="tool-icon">☷</span>
            <strong>Review Drawing Pages</strong>
            <small>Include or exclude pages, review order, status, workbook source, and the complete scrollable page list.</small>
          </button>
          <button className="project-tool-card" type="button" disabled={syncing} onClick={() => void openEditor(currentProject.id, 'symbol-mapper')}>
            <span className="tool-icon">◎</span>
            <strong>Run Symbol Mapper</strong>
            <small>Open the existing PDF symbol-detection and reviewed-highlight workflow directly.</small>
          </button>
          <button className="project-tool-card" type="button" disabled={syncing} onClick={() => void openEditor(currentProject.id, 'symbol-legend')}>
            <span className="tool-icon">◉</span>
            <strong>Build Symbol Legend</strong>
            <small>Edit the Singh360 symbol standard, wording, order, colors, and included legend rows.</small>
          </button>
          <button className="project-tool-card" type="button" onClick={openComponentBuilder}>
            <span className="tool-icon">◇</span>
            <strong>Component Builder</strong>
            <small>Open the component catalog workbench and library administration tools.</small>
          </button>
          <button className="project-tool-card" type="button" onClick={() => window.location.assign(`/app?project=${encodeURIComponent(currentProject.id)}&editor=1&help=1`)}>
            <span className="tool-icon">?</span>
            <strong>Help & Workflow</strong>
            <small>Workbook status stages, Include/Exclude rules, source editing, drawing tools, and export guidance.</small>
          </button>
        </section>

        <section className="project-stats">
          <div><strong>{currentProject.pages.length}</strong><span>Editor pages</span></div>
          <div><strong>{included}</strong><span>Included pages</span></div>
          <div><strong>{excluded}</strong><span>Excluded / source-only</span></div>
          <div><strong>{currentProject.worksheets.length}</strong><span>Workbook drafts</span></div>
        </section>

        <section className="workbook-sync-card">
          <div className="workbook-sync-main">
            <span className="eyebrow">LINKED WORKBOOK</span>
            <strong>{workbook}</strong>
            <p>{syncState}. Workbook-owned manifest and structured sheet changes synchronize through the existing guarded workflow; manual drawing layers are not replaced.</p>
          </div>
          <div className="workbook-sync-meta">
            <div><span>Last workbook sync</span><strong>{formatDate(currentProject.workbookSync?.lastSyncUtc)}</strong></div>
            <div><span>Last project save</span><strong>{formatDate(lastProjectSave)}</strong></div>
            <button className="home-button secondary" type="button" disabled={syncing} onClick={() => void refreshCurrentProject()}>
              {syncing ? 'Checking…' : 'Check Workbook Now'}
            </button>
          </div>
        </section>

        <section className="home-new-project compact">
          <div>
            <h2>Start a different project</h2>
            <p>A new workbook creates a new Singh360 project. It does not overwrite this project or its manual drawing work.</p>
          </div>
          <button className="home-button secondary" type="button" onClick={() => fileInputRef.current?.click()}>New Project from Workbook</button>
        </section>

        <input
          ref={fileInputRef}
          className="home-file-input"
          type="file"
          accept=".xlsx,.xlsm"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.currentTarget.value = '';
            if (file) setPendingWorkbookFile(file);
          }}
        />
      </main>
    );
  } else {
    content = (
      <main className="home-shell landing-shell">
        <header className="home-topbar landing-header">
          <div>
            <div className="home-brand">SINGH360 DRAFT</div>
            <h1>Drawing Package Editor</h1>
            <p>Start a project from the latest workbook, or continue local work.</p>
          </div>
          <div className="home-header-actions">
            <button className="home-button ghost light" type="button" onClick={openComponentBuilder}>Component Builder</button>
            <button className="home-button ghost light" type="button" onClick={() => window.location.assign('/app?editor=1&help=1')}>Help</button>
          </div>
        </header>

        {error && <div className="home-alert error" role="alert">{error}</div>}

        <section className="home-new-project">
          <div>
            <span className="eyebrow">NEW PROJECT</span>
            <h2>Start from an Excel workbook</h2>
            <p>The workbook is analyzed first, then a new project is created and you review its complete drawing-page plan before opening the editor.</p>
          </div>
          <button className="home-button primary jumbo" type="button" onClick={() => fileInputRef.current?.click()}>Choose Workbook</button>
          <input
            ref={fileInputRef}
            className="home-file-input"
            type="file"
            accept=".xlsx,.xlsm"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.currentTarget.value = '';
              if (file) setPendingWorkbookFile(file);
            }}
          />
        </section>

        <section className="recent-projects-card">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">RECENT PROJECTS</span>
              <h2>Continue local work</h2>
            </div>
            <button className="home-button ghost" type="button" onClick={() => void refreshProjects()}>Refresh</button>
          </div>

          <div className="recent-project-list">
            {projects.map((project) => (
              <article key={project.id} className="recent-project-row">
                <button className="project-name-button" type="button" disabled={syncing} onClick={() => void loadProject(project.id)}>
                  <strong>{project.projectName}</strong>
                  <span>{project.sourceWorkbook || 'Workbook name not recorded'}</span>
                </button>
                <div className="project-row-meta">
                  <span>Saved {formatDate(project.lastSavedAt || project.modified)}</span>
                  {project.duplicateFolders ? <span className="warning-pill">{project.duplicateFolders} duplicate folder{project.duplicateFolders === 1 ? '' : 's'}</span> : null}
                </div>
                <div className="project-row-actions">
                  <button className="home-button ghost" type="button" disabled={syncing} onClick={() => void loadProject(project.id)}>Project Home</button>
                  <button className="home-button secondary" type="button" disabled={syncing} onClick={() => void openEditor(project.id)}>Open Page Editor</button>
                </div>
              </article>
            ))}
            {projects.length === 0 && (
              <div className="recent-empty">
                <strong>No saved projects found.</strong>
                <span>Choose an .xlsx or .xlsm workbook to create the first project.</span>
              </div>
            )}
          </div>
        </section>
      </main>
    );
  }

  return (
    <>
      {content}
      {pendingWorkbookFile && (
        <ContinuationPreviewModal
          file={pendingWorkbookFile}
          onImported={(projectId) => void finishWorkbookImport(projectId)}
          onCancel={() => setPendingWorkbookFile(null)}
        />
      )}
    </>
  );
}
