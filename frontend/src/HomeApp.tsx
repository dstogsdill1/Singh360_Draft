import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createProjectFromWorkbook,
  getProject,
  listProjects,
  saveProject,
  type ProjectListItem,
} from './api/client';
import type { PageModel, ProjectModel } from './model/types';

const PAGE_SIZE = 18;
type PageFilter = 'all' | 'included' | 'excluded';

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

function formatSavedAt(value?: string): string {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function openProjectHome(id: string): void {
  window.location.assign(`/app?project=${encodeURIComponent(id)}`);
}

function openEditor(id: string): void {
  window.location.assign(`/app?project=${encodeURIComponent(id)}&editor=1`);
}

export default function HomeApp() {
  const initial = useMemo(currentParams, []);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [currentProject, setCurrentProject] = useState<ProjectModel | null>(null);
  const [reviewProject, setReviewProject] = useState<ProjectModel | null>(null);
  const [reviewPages, setReviewPages] = useState<PageModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<PageFilter>('all');
  const [pageNumber, setPageNumber] = useState(1);

  const refreshProjects = useCallback(async () => {
    const rows = await listProjects();
    setProjects(rows);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const rows = await listProjects();
        if (cancelled) return;
        setProjects(rows);
        if (initial.projectId) {
          const project = await getProject(initial.projectId);
          if (cancelled) return;
          setCurrentProject(project);
          if (initial.review) {
            setReviewProject(project);
            setReviewPages(project.pages.map((page) => ({
              ...page,
              include: requiredPage(page) ? true : page.include,
            })));
          }
        }
      } catch (loadError) {
        if (!cancelled) setError(errorMessage(loadError));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [initial.projectId, initial.review]);

  const beginReview = useCallback((project: ProjectModel) => {
    setReviewProject(project);
    setReviewPages(project.pages.map((page) => ({
      ...page,
      include: requiredPage(page) ? true : page.include,
    })));
    setQuery('');
    setFilter('all');
    setPageNumber(1);
    window.history.replaceState({}, '', `/app?project=${encodeURIComponent(project.id)}&review=1`);
  }, []);

  const handleWorkbook = useCallback(async (file: File) => {
    setImporting(true);
    setError('');
    try {
      const created = await createProjectFromWorkbook(file);
      const project = await getProject(created.id);
      setCurrentProject(project);
      beginReview(project);
      await refreshProjects();
    } catch (importError) {
      setError(errorMessage(importError));
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [beginReview, refreshProjects]);

  const filteredPages = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return [...reviewPages]
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .filter((page) => {
        if (filter === 'included' && !page.include) return false;
        if (filter === 'excluded' && page.include) return false;
        if (!needle) return true;
        return [pageCode(page), page.sheetTitle, page.sheetTab, page.pageFamily, page.pageType]
          .some((value) => String(value || '').toLowerCase().includes(needle));
      });
  }, [filter, query, reviewPages]);

  useEffect(() => {
    setPageNumber(1);
  }, [filter, query]);

  const totalReviewPages = Math.max(1, Math.ceil(filteredPages.length / PAGE_SIZE));
  const safePageNumber = Math.min(pageNumber, totalReviewPages);
  const visiblePages = filteredPages.slice((safePageNumber - 1) * PAGE_SIZE, safePageNumber * PAGE_SIZE);
  const includedReviewCount = reviewPages.filter((page) => page.include || requiredPage(page)).length;

  const patchInclude = useCallback((id: string, include: boolean) => {
    setReviewPages((pages) => pages.map((page) => (
      page.id === id && !requiredPage(page) ? { ...page, include } : page
    )));
  }, []);

  const saveSelectionAndOpen = useCallback(async () => {
    if (!reviewProject) return;
    setSaving(true);
    setError('');
    try {
      const reviewed = new Map(reviewPages.map((page) => [page.id, page]));
      const next: ProjectModel = {
        ...reviewProject,
        pages: reviewProject.pages.map((page) => {
          const edited = reviewed.get(page.id);
          return {
            ...page,
            include: requiredPage(page) ? true : (edited?.include ?? page.include),
          };
        }),
      };
      await saveProject(next);
      openEditor(next.id);
    } catch (saveError) {
      setError(errorMessage(saveError));
      setSaving(false);
    }
  }, [reviewPages, reviewProject]);

  const returnToHome = useCallback(() => {
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

  if (loading) {
    return (
      <main className="home-shell home-loading">
        <div className="home-spinner" aria-hidden="true" />
        <p>Loading Singh360 Draft…</p>
      </main>
    );
  }

  if (reviewProject) {
    return (
      <main className="home-shell review-shell">
        <header className="home-topbar">
          <div>
            <div className="home-brand">SINGH360 DRAFT</div>
            <h1>Review drawing pages</h1>
            <p>{projectName(reviewProject)}</p>
          </div>
          <button className="home-button ghost" type="button" onClick={returnToHome}>Back to Project Home</button>
        </header>

        {error && <div className="home-alert error" role="alert">{error}</div>}

        <section className="review-summary">
          <div><strong>{reviewPages.length}</strong><span>Total pages</span></div>
          <div><strong>{includedReviewCount}</strong><span>Included</span></div>
          <div><strong>{reviewPages.length - includedReviewCount}</strong><span>Excluded</span></div>
          <div><strong>{reviewProject.worksheets.length}</strong><span>Workbook tabs</span></div>
        </section>

        <section className="review-card">
          <div className="review-toolbar">
            <label className="review-search">
              <span>Search pages</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Code, title, tab, type…"
              />
            </label>
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
          </div>

          <div className="review-table-wrap">
            <table className="review-table">
              <thead>
                <tr>
                  <th className="include-col">Include</th>
                  <th className="order-col">Order</th>
                  <th className="code-col">Sheet</th>
                  <th>Page title</th>
                  <th>Workbook tab</th>
                  <th className="type-col">Type</th>
                </tr>
              </thead>
              <tbody>
                {visiblePages.map((page) => {
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
                      <td><strong>{page.sheetTitle || 'Untitled page'}</strong>{page.pageFamily && <small>{page.pageFamily}</small>}</td>
                      <td>{page.sheetTab || page.sourceSheet || 'App-owned page'}</td>
                      <td className="type-col"><span className="type-pill">{page.pageType}</span></td>
                    </tr>
                  );
                })}
                {visiblePages.length === 0 && (
                  <tr><td colSpan={6} className="review-empty">No pages match this filter.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <footer className="review-footer">
            <div className="review-pagination">
              <button type="button" disabled={safePageNumber <= 1} onClick={() => setPageNumber((value) => Math.max(1, value - 1))}>Previous</button>
              <span>Page {safePageNumber} of {totalReviewPages} · {filteredPages.length} rows</span>
              <button type="button" disabled={safePageNumber >= totalReviewPages} onClick={() => setPageNumber((value) => Math.min(totalReviewPages, value + 1))}>Next</button>
            </div>
            <button className="home-button primary wide" type="button" disabled={saving} onClick={() => void saveSelectionAndOpen()}>
              {saving ? 'Saving project…' : 'Save & Open Editor'}
            </button>
          </footer>
        </section>
      </main>
    );
  }

  if (currentProject) {
    const included = currentProject.pages.filter((page) => page.include).length;
    const excluded = currentProject.pages.length - included;
    const sourceWorkbook = currentProject.sourceWorkbookName || currentProject.metadata.sourceFile || 'No workbook name recorded';
    const lastSaved = currentProject.lastSavedAt || currentProject.modified;

    return (
      <main className="home-shell project-home-shell">
        <header className="home-topbar">
          <div>
            <div className="home-brand">SINGH360 DRAFT</div>
            <h1>{projectName(currentProject)}</h1>
            <p>{[currentProject.metadata.client, currentProject.metadata.storeNumber, currentProject.metadata.location].filter(Boolean).join(' · ') || 'Drawing package project'}</p>
          </div>
          <button className="home-button ghost" type="button" onClick={() => window.location.assign('/app')}>All Projects</button>
        </header>

        {error && <div className="home-alert error" role="alert">{error}</div>}

        <section className="project-hero-card">
          <div>
            <span className="eyebrow">PROJECT HOME</span>
            <h2>Project is ready to edit</h2>
            <p>Open the drawing editor for page work. Use page review only when you need to change what publishes.</p>
          </div>
          <div className="project-primary-actions">
            <button className="home-button primary jumbo" type="button" onClick={() => openEditor(currentProject.id)}>Open Editor</button>
            <button className="home-button secondary" type="button" onClick={() => beginReview(currentProject)}>Review Included Pages</button>
          </div>
        </section>

        <section className="project-stats">
          <div><strong>{included}</strong><span>Published pages</span></div>
          <div><strong>{excluded}</strong><span>Excluded/source-only</span></div>
          <div><strong>{currentProject.worksheets.length}</strong><span>Workbook tabs</span></div>
          <div><strong>{formatSavedAt(lastSaved)}</strong><span>Last local save</span></div>
        </section>

        <section className="project-details-card">
          <div>
            <span>Linked workbook</span>
            <strong>{sourceWorkbook}</strong>
            <small>The project keeps its own source copy. Workbook update controls stay out of the daily home screen.</small>
          </div>
          <details>
            <summary>Change Workbook</summary>
            <p>Open the editor and use <strong>File → Upload Workbook</strong>. The existing reimport preview separates workbook-driven pages from manual drawing pages before any update is applied.</p>
            <button className="home-button secondary" type="button" onClick={() => openEditor(currentProject.id)}>Open Controlled Update</button>
          </details>
        </section>

        <section className="home-new-project compact">
          <div>
            <h2>Start a different project</h2>
            <p>A new workbook always creates a new Singh360 project. It does not overwrite this one.</p>
          </div>
          <button className="home-button secondary" type="button" disabled={importing} onClick={() => fileInputRef.current?.click()}>
            {importing ? 'Reading workbook…' : 'New Project from Workbook'}
          </button>
        </section>

        <input
          ref={fileInputRef}
          className="home-file-input"
          type="file"
          accept=".xlsx,.xlsm"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleWorkbook(file);
          }}
        />
      </main>
    );
  }

  return (
    <main className="home-shell landing-shell">
      <header className="landing-header">
        <div>
          <div className="home-brand">SINGH360 DRAFT</div>
          <h1>Drawing Package Editor</h1>
          <p>Open a project, or create one from the latest workbook.</p>
        </div>
      </header>

      {error && <div className="home-alert error" role="alert">{error}</div>}

      <section className="home-new-project">
        <div>
          <span className="eyebrow">NEW PROJECT</span>
          <h2>Start from an Excel workbook</h2>
          <p>The workbook is parsed into a new local project, then you review a readable list of drawing pages before opening the editor.</p>
        </div>
        <button className="home-button primary jumbo" type="button" disabled={importing} onClick={() => fileInputRef.current?.click()}>
          {importing ? 'Reading workbook…' : 'Choose Workbook'}
        </button>
        <input
          ref={fileInputRef}
          className="home-file-input"
          type="file"
          accept=".xlsx,.xlsm"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleWorkbook(file);
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
              <button className="project-name-button" type="button" onClick={() => openProjectHome(project.id)}>
                <strong>{project.projectName}</strong>
                <span>{project.sourceWorkbook || 'Workbook not recorded'}</span>
              </button>
              <div className="project-row-meta">
                <span>Saved {formatSavedAt(project.lastSavedAt || project.modified)}</span>
                {project.duplicateFolders ? <span className="warning-pill">{project.duplicateFolders} duplicate folder{project.duplicateFolders === 1 ? '' : 's'}</span> : null}
              </div>
              <div className="project-row-actions">
                <button className="home-button ghost" type="button" onClick={() => openProjectHome(project.id)}>Project Home</button>
                <button className="home-button secondary" type="button" onClick={() => openEditor(project.id)}>Open Editor</button>
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
