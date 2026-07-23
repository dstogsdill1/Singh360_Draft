import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import type { ProjectModel } from '../model/types';
import {
  createProjectFromWorkbook,
  exportPackage,
  getLibV2,
  getWorkbookLinkStatus,
  linkWorkbookPath,
  listProjects,
  openLinkedWorkbook,
  pickWorkbookPath,
  resolveWorkbookLink,
  revealLinkedWorkbook,
  syncWorkbookLink,
  unlinkWorkbook,
  type ProjectListItem,
  type WorkbookLinkStatus,
} from '../api/client';
import LibraryPanelV2 from './LibraryPanelV2';

interface Props {
  project: ProjectModel | null;
}

const statusLabel: Record<string, string> = {
  not_linked: 'Not linked',
  internal: 'Internal copy',
  review_required: 'Review required',
  in_sync: 'In sync',
  workbook_changed: 'Workbook changed',
  app_changed: 'App changed',
  conflict: 'Conflict',
  missing: 'Workbook missing',
  locked: 'Workbook locked',
  invalid: 'Invalid workbook',
  project_mismatch: 'Wrong project workbook',
  pending: 'Project saved · workbook sync pending',
};

function projectName(item: ProjectListItem): string {
  return item.projectName || item.packageFile || item.sourceWorkbook || item.id;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ProjectDashboard({ project }: Props) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [link, setLink] = useState<WorkbookLinkStatus | null>(null);
  const [linkPath, setLinkPath] = useState('');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [libraryHealth, setLibraryHealth] = useState<{ total: number; favorites: number; needsReview: number } | null>(null);
  const newWorkbookRef = useRef<HTMLInputElement | null>(null);

  const reload = async () => {
    const list = await listProjects();
    setProjects(list);
    if (project) {
      const status = await getWorkbookLinkStatus(project.id);
      setLink(status);
      setLinkPath(status.path || '');
    } else {
      setLink(null);
    }
    try {
      const data = await getLibV2(true);
      setLibraryHealth(data.counts);
    } catch {
      setLibraryHealth(null);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id]);

  const selectedWorkbookPending = Boolean(
    linkPath.trim() && linkPath.trim() !== String(link?.path || '').trim(),
  );

  const included = project?.pages.filter((p) => p.include).length ?? 0;
  const excluded = (project?.pages.length ?? 0) - included;
  const stageCounts = useMemo(() => {
    const counts = { draft: 0, draft_confirmed: 0, public: 0, public_confirmed: 0 };
    for (const page of project?.pages ?? []) {
      const key = (page.issueStatus || 'draft') as keyof typeof counts;
      if (key in counts) counts[key] += 1;
    }
    return counts;
  }, [project]);

  const actionUrl = (tool?: string) => {
    if (!project) return '/app';
    const params = new URLSearchParams({ project: project.id, mode: 'editor' });
    if (tool) params.set('tool', tool);
    return `/app?${params.toString()}`;
  };

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label);
    setMessage('');
    try {
      await fn();
      setMessage(`${label} completed.`);
      await reload();
    } catch (err) {
      setMessage(`${label} failed: ${String(err)}`);
    } finally {
      setBusy('');
    }
  };

  const browseWorkbook = async () => {
    if (!project) return;
    setBusy('Browse workbook');
    setMessage('');
    try {
      const result = await pickWorkbookPath(project.id);
      if (result.cancelled) {
        setMessage('Workbook selection cancelled. The existing link was not changed.');
        return;
      }
      const selected = (result.selectedPath || '').trim();
      if (!selected) {
        setMessage('No workbook was selected. The existing link was not changed.');
        return;
      }
      setLinkPath(selected);
      setMessage('Workbook selected — not linked yet. Review the path, then click Confirm Selected Workbook.');
    } catch (err) {
      setMessage(`Browse workbook failed: ${String(err)}`);
    } finally {
      setBusy('');
    }
  };

  const createProject = async (file: File) => {
    setBusy('Creating project');
    try {
      const result = await createProjectFromWorkbook(file);
      window.location.assign(`/app?project=${result.id}`);
    } catch (err) {
      setMessage(`Project creation failed: ${String(err)}`);
      setBusy('');
    }
  };

  const packageDownload = async () => {
    if (!project) return;
    const blob = await exportPackage(project.id);
    const name = project.metadata.drawingPackageFileName || project.projectDisplayName || project.metadata.projectName || project.id;
    downloadBlob(blob, `${name}_package.zip`);
  };

  return (
    <div className="project-home">
      <header className="project-home-head">
        <div>
          <div className="project-home-brand">SINGH360 DRAFT</div>
          <h1>Project Home</h1>
          <p>Open a project, confirm its workbook, run project tools, then enter the page editor.</p>
        </div>
        <div className="project-home-head-actions">
          <button type="button" onClick={() => window.open('/app?help=1', '_blank', 'noopener,noreferrer')}>Instructions</button>
          {project && <button type="button" className="primary" onClick={() => window.location.assign(actionUrl())}>Open Page Editor</button>}
        </div>
      </header>

      <div className="project-home-layout">
        <aside className="project-list-card">
          <div className="card-head">
            <h2>Projects</h2>
            <button type="button" onClick={() => newWorkbookRef.current?.click()}>New from Workbook</button>
            <input
              ref={newWorkbookRef}
              type="file"
              accept=".xlsx,.xlsm"
              hidden
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                const file = event.target.files?.[0];
                event.currentTarget.value = '';
                if (file) void createProject(file);
              }}
            />
          </div>
          <div className="project-list">
            {projects.map((item) => (
              <button
                type="button"
                key={item.id}
                className={item.id === project?.id ? 'active' : ''}
                onClick={() => window.location.assign(`/app?project=${item.id}`)}
              >
                <strong>{projectName(item)}</strong>
                <span>{item.sourceWorkbook || 'No workbook name'}</span>
                <small>{item.lastSavedAt || item.modified || ''}</small>
              </button>
            ))}
            {!projects.length && <p className="empty-note">No saved projects were found.</p>}
          </div>
        </aside>

        <main className="project-home-main">
          {!project ? (
            <section className="welcome-card">
              <h2>Choose a project or create one from a workbook</h2>
              <p>The dashboard opens before the editor so workbook linking, synchronization, exports, and project tools are easy to find.</p>
              <button type="button" className="primary large" onClick={() => newWorkbookRef.current?.click()}>Choose Workbook and Create Project</button>
            </section>
          ) : (
            <>
              <section className="project-summary-card">
                <div>
                  <div className="eyebrow">ACTIVE PROJECT</div>
                  <h2>{project.projectDisplayName || project.metadata.projectName || project.id}</h2>
                  <p>{project.metadata.location || 'Location not entered'}</p>
                  <p className="muted">{project.metadata.drawingPackageFileName || project.sourceWorkbookName || ''}</p>
                </div>
                <div className="summary-grid">
                  <div><b>{project.pages.length}</b><span>Editor pages</span></div>
                  <div><b>{included}</b><span>Included</span></div>
                  <div><b>{excluded}</b><span>Excluded</span></div>
                  <div><b>{project.worksheets.length}</b><span>Workbook drafts</span></div>
                </div>
                <div className="stage-strip">
                  <span className="draft">Draft {stageCounts.draft}</span>
                  <span className="draft-confirmed">✓ Draft Confirmed {stageCounts.draft_confirmed}</span>
                  <span className="public">Public {stageCounts.public}</span>
                  <span className="public-confirmed">✓ Public Confirmed {stageCounts.public_confirmed}</span>
                </div>
              </section>

              <section className="quick-actions-card">
                <div className="card-head"><h2>Project Tools</h2><span>Simple project-wide actions</span></div>
                <div className="quick-action-grid">
                  <button type="button" className="primary" onClick={() => window.location.assign(actionUrl())}><b>Open Page Editor</b><span>Edit drawings, tables, images, and overlays</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('symbol-mapper'))}><b>Run Symbol Mapper</b><span>Highlight and count drawing symbols</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('symbol-legend'))}><b>Build Symbol Legend</b><span>Build and insert the saved legend standard</span></button>
                  <button type="button" onClick={() => setLibraryOpen(true)}><b>Component Library</b><span>Search, clean, review, and manage components</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('export'))}><b>Drawing Set / Export PDF</b><span>Pick exact sheets and export</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('renumber'))}><b>Reorder / Renumber</b><span>Review and apply sheet-code order</span></button>
                  <button type="button" onClick={() => void run('Export package', packageDownload)}><b>Export Project Package</b><span>Download project.json, sources, assets, and exports</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('backups'))}><b>Backups / Recovery</b><span>Review project and page snapshots</span></button>
                </div>
              </section>

              <section className="workbook-link-card">
                <div className="card-head">
                  <div>
                    <h2>Linked Workbook</h2>
                    <p>The project can link to G:, Google Drive, OneDrive, a network folder, or a local workbook.</p>
                  </div>
                  <span className={`sync-badge ${link?.status || 'not_linked'}`}>{statusLabel[link?.status || 'not_linked'] || link?.status}</span>
                </div>
                <div className="link-path-row">
                  <input
                    value={linkPath}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setLinkPath(event.target.value)}
                    placeholder="G:\Shared drives\...\Project Workbook.xlsx"
                  />
                  <button
                    type="button"
                    disabled={!!busy}
                    onClick={() => void browseWorkbook()}
                  >
                    Browse
                  </button>
                  <button
                    type="button"
                    className="primary"
                    disabled={!!busy || !linkPath.trim()}
                    onClick={() => void run('Link workbook', async () => {
                      if (!project) return;
                      const result = await linkWorkbookPath(project.id, linkPath);
                      setLink(result.status);
                    })}
                  >
                    {selectedWorkbookPending ? 'Confirm Selected Workbook' : 'Confirm Link'}
                  </button>
                </div>
                {selectedWorkbookPending && (
                  <div className="workbook-selection-pending">
                    <strong>Selected workbook — not linked yet</strong>
                    <code>{linkPath}</code>
                    <span>The existing workbook link stays active until you click Confirm Selected Workbook.</span>
                  </div>
                )}
                <div className="workbook-status-detail">
                  <strong>{link?.message || 'Choose the project workbook.'}</strong>
                  {link?.path && <code>{link.path}</code>}
                  {link?.workbook && (
                    <div className="workbook-meta">
                      <span>{link.workbook.filename}</span>
                      <span>{link.workbook.sheetCount} sheets</span>
                      <span>Schema {link.workbook.schemaVersion || 'not set'}</span>
                      <span>Help {link.workbook.helpVersion || 'not set'}</span>
                    </div>
                  )}
                </div>
                <div className="workbook-action-row">
                  <button type="button" disabled={!project || !!busy} onClick={() => void run('Sync workbook', async () => {
                    if (!project) return;
                    const result = await syncWorkbookLink(project.id);
                    setLink(result.status);
                  })}>Sync Now</button>
                  <button type="button" disabled={!project || !!busy} onClick={() => void run('Use workbook', async () => {
                    if (!project) return;
                    const result = await resolveWorkbookLink(project.id, 'workbook_to_app');
                    setLink(result.status);
                    window.location.reload();
                  })}>Use Workbook → Update App</button>
                  <button type="button" disabled={!project || !!busy} onClick={() => void run('Use app', async () => {
                    if (!project) return;
                    const result = await resolveWorkbookLink(project.id, 'app_to_workbook');
                    setLink(result.status);
                  })}>Use App → Update Workbook</button>
                  <button type="button" disabled={!project || !link?.path} onClick={() => project && void openLinkedWorkbook(project.id)}>Open in Excel</button>
                  <button type="button" disabled={!project || !link?.path} onClick={() => project && void revealLinkedWorkbook(project.id)}>Show in Explorer</button>
                  <button type="button" className="danger" disabled={!project || !link?.path} onClick={() => void run('Unlink workbook', async () => {
                    if (!project || !window.confirm('Unlink the external workbook? The project data and internal recovery copy will remain.')) return;
                    await unlinkWorkbook(project.id);
                  })}>Unlink</button>
                </div>
              </section>

              <section className="health-card">
                <div><b>Local project save</b><span className="ok">Independent of workbook availability</span></div>
                <div><b>Component library</b><span>{libraryHealth ? `${libraryHealth.total} components · ${libraryHealth.needsReview} need review` : 'Health check unavailable'}</span></div>
                <div><b>Last project save</b><span>{project.lastSavedAt || project.modified || 'Not recorded'}</span></div>
                <div><b>Workbook sync</b><span>{link?.lastSyncUtc || 'Not completed'}</span></div>
              </section>
            </>
          )}

          {message && <div className={`dashboard-message ${message.includes('failed') ? 'error' : ''}`}>{message}</div>}
          {busy && <div className="dashboard-busy">{busy}…</div>}
        </main>
      </div>

      {libraryOpen && (
        <div className="dashboard-overlay">
          <div className="dashboard-overlay-panel component-workspace">
            <div className="overlay-head">
              <div><h2>Component Library</h2><p>Full project component workspace</p></div>
              <div>
                {project && <button type="button" onClick={() => window.location.assign(actionUrl())}>Open Editor to Insert</button>}
                <button type="button" onClick={() => setLibraryOpen(false)}>Close</button>
              </div>
            </div>
            <div className="component-workspace-body">
              <LibraryPanelV2
                onInsert={() => undefined}
                canInsert={false}
                onOpenLegendEditor={() => project && window.location.assign(actionUrl('symbol-legend'))}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
