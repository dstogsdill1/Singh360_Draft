import { useCallback, useEffect, useState } from 'react';
import type { ProjectModel } from '../model/types';
import NewProjectWizard from './NewProjectWizard';

interface Props {
  project: ProjectModel | null;
}

interface ProjectListItem {
  id: string;
  projectName?: string;
  projectDisplayName?: string;
  modified?: string;
  lastSavedAt?: string;
  projectMode?: string;
  pageCount?: number;
  assetCount?: number;
  archivedAt?: string;
  archiveReason?: string;
  metadata?: {
    projectName?: string;
    storeNumber?: string;
    client?: string;
    location?: string;
  };
}

interface ProjectListResponse {
  projects?: ProjectListItem[];
  archivedProjects?: ProjectListItem[];
}

function displayName(item: ProjectListItem): string {
  return (
    item.projectName
    || item.projectDisplayName
    || item.metadata?.projectName
    || `Drawing Project ${item.id}`
  );
}

function displayDate(value?: string): string {
  if (!value) return 'Not saved yet';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

async function responseJson<T>(response: Response): Promise<T> {
  let payload: Record<string, unknown> = {};
  try {
    payload = await response.json() as Record<string, unknown>;
  } catch {
    payload = {};
  }
  if (!response.ok) {
    const detail = String(payload.detail || payload.error || response.statusText || 'Request failed.');
    throw new Error(detail);
  }
  return payload as T;
}

export default function ProjectDashboard({ project }: Props) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [archivedProjects, setArchivedProjects] = useState<ProjectListItem[]>([]);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyProjectId, setBusyProjectId] = useState('');
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');

  const closeWizard = useCallback(() => setWizardOpen(false), []);

  const loadProjects = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/projects', {
        headers: { Accept: 'application/json' },
        signal,
      });
      const result = await responseJson<ProjectListResponse>(response);
      setProjects(Array.isArray(result.projects) ? result.projects : []);
      setArchivedProjects(Array.isArray(result.archivedProjects) ? result.archivedProjects : []);
    } catch (requestError) {
      if ((requestError as Error).name !== 'AbortError') {
        setError(`Projects could not be loaded. ${String(requestError)}`);
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadProjects(controller.signal);
    return () => controller.abort();
  }, [loadProjects]);

  const openProject = (projectId: string) => {
    window.location.assign(`/app?project=${encodeURIComponent(projectId)}&mode=editor`);
  };

  const archive = async (item: ProjectListItem) => {
    if (!window.confirm(`Archive "${displayName(item)}"? It can be restored later.`)) return;
    setBusyProjectId(item.id);
    setStatus('');
    setError('');
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(item.id)}/archive`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      await responseJson<Record<string, unknown>>(response);
      setStatus(`${displayName(item)} was archived and remains recoverable.`);
      await loadProjects();
    } catch (requestError) {
      setError(`Project archive failed. ${String(requestError)}`);
    } finally {
      setBusyProjectId('');
    }
  };

  const restore = async (item: ProjectListItem) => {
    setBusyProjectId(item.id);
    setStatus('');
    setError('');
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(item.id)}/restore`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      await responseJson<Record<string, unknown>>(response);
      setStatus(`${displayName(item)} was restored to Active Projects.`);
      await loadProjects();
    } catch (requestError) {
      setError(`Project restore failed. ${String(requestError)}`);
    } finally {
      setBusyProjectId('');
    }
  };

  return (
    <main className="project-home">
      <header className="project-home-head">
        <div>
          <div className="project-home-brand">SINGH360 DRAFT</div>
          <h1>Drawing Projects</h1>
          <p>Create, open, archive, and restore self-contained drawing sets.</p>
        </div>
        <div className="project-home-head-actions">
          <button className="primary" type="button" onClick={() => setWizardOpen(true)}>
            New Drawing Project
          </button>
          <button type="button" onClick={() => { void loadProjects(); }} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh Projects'}
          </button>
        </div>
      </header>

      <div className="project-home-layout">
        <aside className="project-list-card" aria-label="Active project shortcuts">
          <div className="card-head">
            <div>
              <h2>Open Active Project</h2>
              <p>{projects.length} active drawing {projects.length === 1 ? 'project' : 'projects'}</p>
            </div>
          </div>
          <div className="project-list">
            {projects.map((item) => (
              <button
                className={item.id === project?.id ? 'active' : ''}
                key={item.id}
                type="button"
                onClick={() => openProject(item.id)}
                aria-current={item.id === project?.id ? 'page' : undefined}
              >
                <strong>{displayName(item)}</strong>
                <span>{item.metadata?.storeNumber || item.metadata?.location || 'Standalone drawing set'}</span>
                <small>{displayDate(item.lastSavedAt || item.modified)}</small>
              </button>
            ))}
            {!loading && projects.length === 0 ? (
              <p className="muted">No active projects yet.</p>
            ) : null}
          </div>
        </aside>

        <div className="project-home-main">
          <section className="welcome-card" aria-labelledby="drawing-project-start">
            <div className="eyebrow">STANDALONE DRAWING-SET EDITOR</div>
            <h2 id="drawing-project-start">Start with only a project name</h2>
            <p className="muted">
              Singh360 stores the cover, sheet index, pages, imports, annotations, and components inside the project.
            </p>
            <div className="welcome-actions">
              <button className="primary large" type="button" onClick={() => setWizardOpen(true)}>
                New Drawing Project
              </button>
            </div>
          </section>

          <section className="quick-actions-card" aria-labelledby="active-projects-heading">
            <div className="card-head">
              <div>
                <h2 id="active-projects-heading">Active Projects</h2>
                <p>Open a project in the editor or archive it recoverably.</p>
              </div>
            </div>
            <div className="project-home-main">
              {projects.map((item) => (
                <article className="simple-project-open green" key={item.id}>
                  <div className="simple-project-open-status">
                    <span className="simple-status-light" aria-hidden="true" />
                    <div>
                      <div className="eyebrow">ACTIVE DRAWING SET</div>
                      <h2>{displayName(item)}</h2>
                      <p>
                        {item.metadata?.client || item.metadata?.location || 'Ready to edit'}
                      </p>
                      <div className="simple-edit-times">
                        <span><b>Last saved</b>{displayDate(item.lastSavedAt || item.modified)}</span>
                        {typeof item.pageCount === 'number' ? <span><b>Pages</b>{item.pageCount}</span> : null}
                        {typeof item.assetCount === 'number' ? <span><b>Assets</b>{item.assetCount}</span> : null}
                      </div>
                    </div>
                  </div>
                  <div className="simple-project-open-actions">
                    <button className="primary" type="button" onClick={() => openProject(item.id)}>
                      Open Project
                    </button>
                    <button
                      className="danger"
                      type="button"
                      disabled={Boolean(busyProjectId)}
                      onClick={() => { void archive(item); }}
                    >
                      {busyProjectId === item.id ? 'Archiving…' : 'Archive'}
                    </button>
                  </div>
                </article>
              ))}
              {!loading && projects.length === 0 ? (
                <div className="welcome-card">
                  <h2>No active projects</h2>
                  <p className="muted">Create a blank drawing set to begin.</p>
                </div>
              ) : null}
            </div>
          </section>

          <section className="quick-actions-card" id="archived-projects" aria-labelledby="archived-projects-heading">
            <div className="card-head">
              <div>
                <h2 id="archived-projects-heading">Archived Projects</h2>
                <p>Archived drawing sets remain recoverable and can be restored here.</p>
              </div>
            </div>
            <div className="project-home-main">
              {archivedProjects.map((item) => (
                <article className="simple-project-open yellow" key={item.id}>
                  <div className="simple-project-open-status">
                    <span className="simple-status-light" aria-hidden="true" />
                    <div>
                      <div className="eyebrow">ARCHIVED DRAWING SET</div>
                      <h2>{displayName(item)}</h2>
                      <p>{item.archiveReason || 'This project is excluded from Active Projects.'}</p>
                      <div className="simple-edit-times">
                        <span><b>Archived</b>{displayDate(item.archivedAt)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="simple-project-open-actions">
                    <button
                      type="button"
                      disabled={Boolean(busyProjectId)}
                      onClick={() => { void restore(item); }}
                    >
                      {busyProjectId === item.id ? 'Restoring…' : 'Restore Project'}
                    </button>
                  </div>
                </article>
              ))}
              {!loading && archivedProjects.length === 0 ? (
                <div className="welcome-card">
                  <p className="muted">No archived projects.</p>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      </div>

      {loading ? <div className="dashboard-busy" role="status">Loading projects…</div> : null}
      {status ? <div className="dashboard-message" role="status">{status}</div> : null}
      {error ? <div className="dashboard-message error" role="alert">{error}</div> : null}
      {wizardOpen ? <NewProjectWizard onClose={closeWizard} /> : null}
    </main>
  );
}
