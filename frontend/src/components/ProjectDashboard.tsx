import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import type { ProjectModel } from '../model/types';
import {
  aiGuideUrl,
  archiveProject,
  createProjectFromWorkbook,
  exportPackage,
  getLibV2,
  getWorkbookLinkStatus,
  getWorkbookQuality,
  linkWorkbookPath,
  listProjects,
  openLinkedWorkbook,
  pickWorkbookPath,
  repairWorkbookQuality,
  resolveWorkbookLink,
  revealLinkedWorkbook,
  savePageInclusion,
  unlinkWorkbook,
  type ProjectListItem,
  type WorkbookLinkStatus,
  type WorkbookQualityReport,
} from '../api/client';
import LibraryPanelV2 from './LibraryPanelV2';
import SyncDecisionModal from './SyncDecisionModal';
import PageManagerModal from './PageManagerModal';
import WorkbookQualityModal from './WorkbookQualityModal';
import DeleteProjectModal from './DeleteProjectModal';

interface Props {
  project: ProjectModel | null;
}

const statusLabel: Record<string, string> = {
  not_linked: 'Not linked',
  internal: 'Internal copy',
  review_required: 'First sync decision required',
  in_sync: 'In sync',
  workbook_changed: 'Workbook changed',
  app_changed: 'App changed',
  conflict: 'Both changed — review required',
  missing: 'Workbook missing',
  locked: 'Workbook locked',
  invalid: 'Invalid workbook',
  project_mismatch: 'Wrong project workbook',
  pending: 'Project saved · workbook sync pending',
};

function projectName(item: ProjectListItem): string {
  return item.projectName || item.packageFile || item.sourceWorkbook || item.id;
}

function activeProjectName(project: ProjectModel): string {
  return project.projectDisplayName || project.metadata.projectName || project.id;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ProjectDashboard({ project }: Props) {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [link, setLink] = useState<WorkbookLinkStatus | null>(null);
  const [linkPath, setLinkPath] = useState('');
  const [quality, setQuality] = useState<WorkbookQualityReport | null>(null);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [pageManagerOpen, setPageManagerOpen] = useState(false);
  const [qualityOpen, setQualityOpen] = useState(false);
  const [syncDecisionOpen, setSyncDecisionOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [libraryHealth, setLibraryHealth] = useState<{ total: number; favorites: number; needsReview: number } | null>(null);
  const newWorkbookRef = useRef<HTMLInputElement | null>(null);

  const reload = async () => {
    const list = await listProjects();
    setProjects(list);
    if (project) {
      const status = await getWorkbookLinkStatus(project.id);
      setLink(status);
      setLinkPath(status.path || '');
      if (status.path && !['missing', 'invalid', 'locked'].includes(status.status)) {
        try {
          setQuality(await getWorkbookQuality(project.id));
        } catch {
          setQuality(null);
        }
      } else {
        setQuality(null);
      }
    } else {
      setLink(null);
      setQuality(null);
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
  const included = project?.pages.filter((page) => page.include).length ?? 0;
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

  const run = async (label: string, fn: () => Promise<unknown>, refresh = true) => {
    setBusy(label);
    setMessage('');
    try {
      await fn();
      setMessage(`${label} completed.`);
      if (refresh) await reload();
    } catch (error) {
      setMessage(`${label} failed: ${String(error)}`);
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
      const linked = await linkWorkbookPath(project.id, selected);
      setLink(linked.status);
      if (['review_required', 'conflict', 'workbook_changed', 'app_changed'].includes(linked.status.status)) {
        setMessage('Workbook selected. Choose which version should be used.');
        setSyncDecisionOpen(true);
      } else {
        setMessage(linked.status.message || 'Workbook linked.');
      }
    } catch (error) {
      setMessage(`Browse workbook failed: ${String(error)}`);
    } finally {
      setBusy('');
    }
  };

  const createProject = async (file: File) => {
    setBusy('Creating project');
    try {
      const result = await createProjectFromWorkbook(file);
      window.location.assign(`/app?project=${result.id}`);
    } catch (error) {
      setMessage(`Project creation failed: ${String(error)}`);
      setBusy('');
    }
  };

  const packageDownload = async () => {
    if (!project) return;
    const blob = await exportPackage(project.id);
    const name = project.metadata.drawingPackageFileName || activeProjectName(project);
    downloadBlob(blob, `${name}_package.zip`);
  };

  const reviewSync = async () => {
    if (!project) return;
    setBusy('Checking workbook versions');
    setMessage('');
    try {
      const status = await getWorkbookLinkStatus(project.id);
      setLink(status);
      if (status.status === 'in_sync') {
        setMessage('The project and workbook are already in sync. No files were changed.');
      } else if (['review_required', 'conflict', 'workbook_changed', 'app_changed'].includes(status.status)) {
        setSyncDecisionOpen(true);
      } else {
        setMessage(status.message);
      }
    } catch (error) {
      setMessage(`Workbook check failed: ${String(error)}`);
    } finally {
      setBusy('');
    }
  };

  const resolveSync = async (direction: 'workbook_to_app' | 'app_to_workbook' | 'baseline') => {
    if (!project) return;
    setBusy(direction === 'baseline' ? 'Linking matching versions' : direction === 'workbook_to_app' ? 'Importing workbook structure' : 'Writing app structure');
    setMessage('');
    try {
      const result = await resolveWorkbookLink(project.id, direction);
      setLink(result.status);
      setSyncDecisionOpen(false);
      const backup = String((result.status as WorkbookLinkStatus & { resolutionBackup?: string }).resolutionBackup || '');
      setMessage(
        `Synchronization completed safely.${backup ? ` Backup: ${backup}` : ''}`,
      );
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      setMessage(`Synchronization failed: ${String(error)}`);
    } finally {
      setBusy('');
    }
  };

  const refreshQuality = async () => {
    if (!project) return;
    setBusy('Auditing workbook');
    try {
      setQuality(await getWorkbookQuality(project.id));
      setMessage('Workbook audit completed. No workbook data was changed.');
    } catch (error) {
      setMessage(`Workbook audit failed: ${String(error)}`);
    } finally {
      setBusy('');
    }
  };

  const repairQuality = async (mode: 'safe' | 'strict') => {
    if (!project) return;
    setBusy(mode === 'safe' ? 'Applying safe workbook repair' : 'Applying strict workbook formatting');
    try {
      const result = await repairWorkbookQuality(project.id, mode);
      setQuality(result.audit);
      setMessage(`${result.message} Backup: ${result.backup}`);
    } catch (error) {
      setMessage(`Workbook repair failed: ${String(error)}`);
    } finally {
      setBusy('');
    }
  };

  const savePageSelection = async (includedByPageId: Record<string, boolean>) => {
    if (!project) return;
    setBusy('Saving drawing-set selection');
    setMessage('');
    try {
      const result = await savePageInclusion(project.id, includedByPageId);
      const sync = result.workbookSync || {};
      const pending = sync.status === 'pending' || Boolean(sync.warning);
      setMessage(
        pending
          ? `Selection saved locally: ${result.included} included / ${result.excluded} excluded. Workbook update is pending: ${String(sync.warning || 'review required')}`
          : `Selection saved: ${result.included} included / ${result.excluded} excluded. Workbook updated.`,
      );
      setPageManagerOpen(false);
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      setMessage(`Page selection save failed before confirmation: ${String(error)}`);
    } finally {
      setBusy('');
    }
  };

  const openPage = (pageId: string) => {
    if (!project) return;
    try {
      localStorage.setItem(`singh360-open-page:${project.id}`, pageId);
    } catch {
      // The editor still opens on page 1 if localStorage is unavailable.
    }
    window.location.assign(actionUrl());
  };

  const removeProject = async () => {
    if (!project) return;
    setBusy('Removing project');
    try {
      await archiveProject(project.id);
      setDeleteOpen(false);
      window.location.assign('/app');
    } catch (error) {
      setMessage(`Project removal failed: ${String(error)}`);
    } finally {
      setBusy('');
    }
  };

  const confirmNewProject = () => {
    if (!window.confirm(
      'Create a separate Singh360 project? Use this only for a different store or a genuinely different workbook. Click Cancel to open an existing project instead.',
    )) return;
    newWorkbookRef.current?.click();
  };

  const syncTone = !project
    ? 'neutral'
    : link?.status === 'in_sync'
      ? 'green'
      : ['workbook_changed', 'app_changed', 'review_required', 'pending'].includes(link?.status || '')
        ? 'yellow'
        : ['conflict', 'project_mismatch', 'missing', 'locked', 'invalid'].includes(link?.status || '')
          ? 'red'
          : 'neutral';

  const syncHeadline = !project
    ? 'Choose an existing project'
    : link?.status === 'in_sync'
      ? 'Ready — Project and workbook match'
      : link?.status === 'workbook_changed'
        ? 'Workbook changed after the last sync'
        : link?.status === 'app_changed'
          ? 'Project changed after the last sync'
          : link?.status === 'conflict'
            ? 'Both versions changed — choose which one is correct'
            : link?.status === 'project_mismatch'
              ? 'Wrong workbook is linked to this project'
              : link?.status === 'review_required'
                ? 'First link — confirm whether the versions match'
                : link?.message || 'Choose the correct project workbook';

  const qualityState = !quality
    ? 'Not audited'
    : quality.counts.critical || quality.counts.errors
      ? `${quality.counts.errors + quality.counts.critical} errors`
      : quality.counts.warnings
        ? `${quality.counts.warnings} warnings`
        : 'Clean';

  return (
    <div className="project-home">
      <header className="project-home-head">
        <div>
          <div className="project-home-brand">SINGH360 DRAFT</div>
          <h1>Project Home</h1>
          <p>Link → Inspect → Synchronize → Review Pages → Edit → Export</p>
        </div>
        <div className="project-home-head-actions">
          <button type="button" onClick={() => window.open(aiGuideUrl('html'), '_blank', 'noopener,noreferrer')}>AI-Ready Instructions</button>
          <button type="button" onClick={() => window.open('/app?help=1', '_blank', 'noopener,noreferrer')}>Quick Help</button>
          <button type="button" onClick={() => window.open('/component-catalog', '_blank', 'noopener,noreferrer')}>Component Builder</button>
          {project && <button type="button" onClick={() => window.location.assign(actionUrl('symbol-mapper'))}>Symbol Mapper</button>}
          {project && <button type="button" className="primary" onClick={() => window.location.assign(actionUrl())}>Open Page Editor</button>}
        </div>
      </header>

      <div className="workflow-strip">
        <span className={link?.path ? 'done' : ''}>1. Link Workbook</span>
        <span className={quality ? 'done' : ''}>2. Inspect / Repair</span>
        <span className={link?.status === 'in_sync' ? 'done' : ''}>3. Establish Sync</span>
        <span>4. Review Pages</span>
        <span>5. Edit / Export</span>
      </div>

      <div className="project-home-layout">
        <aside className="project-list-card">
          <div className="card-head">
            <h2>Projects</h2>
            <button type="button" onClick={confirmNewProject}>Create New Project</button>
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
                onClick={() => window.location.assign(`/app?project=${item.id}&mode=editor`)}
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
              <h2>Open a saved project from the left</h2>
              <p>Click a project to open it. Create New Project is only for a different store or a genuinely different workbook.</p>
              <div className="welcome-actions">
                <button type="button" className="primary large" onClick={confirmNewProject}>Create a Different Project</button>
                <button type="button" className="large" onClick={() => window.open('/component-catalog', '_blank', 'noopener,noreferrer')}>Open Component Builder</button>
              </div>
            </section>
          ) : (
            <>
              <section className="project-summary-card">
                <div>
                  <div className="eyebrow">ACTIVE PROJECT</div>
                  <h2>{activeProjectName(project)}</h2>
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

              <section className={`simple-project-open ${syncTone}`}>
                <div className="simple-project-open-status">
                  <span className="simple-status-light" aria-hidden="true" />
                  <div>
                    <div className="eyebrow">PROJECT / WORKBOOK CHECK</div>
                    <h2>{syncHeadline}</h2>
                    <p>{link?.message || 'Choose the project workbook.'}</p>
                    <div className="simple-edit-times">
                      <span><b>Workbook last edit</b>{link?.workbook?.modified || 'Not recorded'}</span>
                      <span><b>Project last save</b>{project.lastSavedAt || project.modified || 'Not recorded'}</span>
                    </div>
                  </div>
                </div>
                <div className="simple-project-open-actions">
                  {link?.status === 'in_sync' ? (
                    <>
                      <button type="button" className="primary large" onClick={() => window.location.assign(actionUrl())}>Open Project</button>
                      <button type="button" onClick={() => project && void openLinkedWorkbook(project.id)}>Open Workbook</button>
                    </>
                  ) : ['review_required', 'conflict', 'workbook_changed', 'app_changed'].includes(link?.status || '') ? (
                    <button type="button" className="primary large" onClick={() => void reviewSync()}>Compare Versions</button>
                  ) : (
                    <button type="button" className="primary large" onClick={() => void browseWorkbook()}>Choose Correct Workbook</button>
                  )}
                </div>
              </section>

              <section className="quick-actions-card">
                <div className="card-head"><h2>Start Here</h2><span>The five tools used for normal drawing-package work</span></div>
                <div className="project-start-tools">
                  <button type="button" className="primary" onClick={() => window.location.assign(actionUrl())}><b>Open Page Editor</b><span>Open the complete File / Home / Insert / Symbols / Draw editor</span></button>
                  <button type="button" onClick={() => setPageManagerOpen(true)}><b>Review Drawing Pages</b><span>Scroll through every page and choose what publishes</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('symbol-mapper'))}><b>Run Symbol Mapper</b><span>Upload a drawing PDF, identify symbols, highlight, and count</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('symbol-legend'))}><b>Symbol Maker / Legend Builder</b><span>Edit the Singh360 symbol standard and insert a legend</span></button>
                  <button type="button" onClick={() => window.open('/component-catalog', '_blank', 'noopener,noreferrer')}><b>Component Builder</b><span>Create, approve, edit, and maintain reusable components</span></button>
                </div>
                <div className="card-head secondary-tool-head"><h2>Project Administration</h2><span>Workbook, output, recovery, and maintenance tools</span></div>
                <div className="project-more-tools">
                  <button type="button" onClick={() => setQualityOpen(true)}><b>Workbook Inspector / Repair</b><span>Audit, restructure, normalize, and recover from backup</span></button>
                  <button type="button" onClick={() => void reviewSync()}><b>Review Workbook Sync</b><span>Compare workbook and app versions with safety backups</span></button>
                  <button type="button" onClick={() => setLibraryOpen(true)}><b>Component Library Browser</b><span>Search and review the component library inside this project</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('export'))}><b>Drawing Set / Export PDF</b><span>Pick exact sheets and export</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('renumber'))}><b>Reorder / Renumber</b><span>Review and apply sheet-code order</span></button>
                  <button type="button" onClick={() => void run('Export package', packageDownload)}><b>Export Project Package</b><span>Download project.json, sources, assets, and exports</span></button>
                  <button type="button" onClick={() => window.location.assign(actionUrl('backups'))}><b>Backups / Recovery</b><span>Review project, page, workbook, and resolution snapshots</span></button>
                  <button type="button" onClick={() => window.open(aiGuideUrl('markdown'), '_blank', 'noopener,noreferrer')}><b>Copy / Feed AI Instructions</b><span>Open the source-of-truth Markdown guide for ChatGPT</span></button>
                  <button type="button" className="danger" onClick={() => setDeleteOpen(true)}><b>Delete This Project</b><span>Requires the exact project name; external workbook is untouched</span></button>
                </div>
              </section>

              <section className="workbook-link-card">
                <div className="card-head">
                  <div>
                    <h2>Linked Workbook</h2>
                    <p>G:, Google Drive for Desktop, OneDrive, network, or local Excel workbook</p>
                  </div>
                  <span className={`sync-badge ${link?.status || 'not_linked'}`}>{statusLabel[link?.status || 'not_linked'] || link?.status}</span>
                </div>
                <div className="link-path-row">
                  <input
                    value={linkPath}
                    onChange={(event: ChangeEvent<HTMLInputElement>) => setLinkPath(event.target.value)}
                    placeholder="G:\Shared drives\...\Project Workbook.xlsx"
                  />
                  <button type="button" disabled={!!busy} onClick={() => void browseWorkbook()}>Browse</button>
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
                    <span>The existing workbook link stays active until confirmation.</span>
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
                  <button type="button" disabled={!project || !!busy} onClick={() => void browseWorkbook()}>Change Workbook</button>
                  <button type="button" className="primary" disabled={!project || !!busy || !link?.path} onClick={() => void reviewSync()}>
                    {link?.status === 'in_sync' ? 'Check for Workbook Changes' : 'Review and Synchronize Safely'}
                  </button>
                  <button type="button" disabled={!project || !link?.path} onClick={() => project && void openLinkedWorkbook(project.id)}>Open in Excel</button>
                  <button type="button" disabled={!project || !link?.path} onClick={() => project && void revealLinkedWorkbook(project.id)}>Show in Explorer</button>
                  <button type="button" onClick={() => setQualityOpen(true)} disabled={!link?.path}>Inspect / Repair Workbook</button>
                  <button type="button" className="danger" disabled={!project || !link?.path} onClick={() => void run('Unlink workbook', async () => {
                    if (!project || !window.confirm('Unlink the external workbook? Project data and the internal recovery copy remain.')) return;
                    await unlinkWorkbook(project.id);
                  })}>Unlink</button>
                </div>
              </section>

              <section className="health-card expanded">
                <div><b>Local project save</b><span className="ok">Independent of workbook availability</span></div>
                <div><b>Workbook quality</b><span>{qualityState}</span></div>
                <div><b>Component library</b><span>{libraryHealth ? `${libraryHealth.total} components · ${libraryHealth.needsReview} need review` : 'Health check unavailable'}</span></div>
                <div><b>Last project save</b><span>{project.lastSavedAt || project.modified || 'Not recorded'}</span></div>
                <div><b>Workbook sync</b><span>{link?.lastSyncUtc || 'Not completed'}</span></div>
              </section>
            </>
          )}

          {message && <div className={`dashboard-message ${message.toLowerCase().includes('failed') ? 'error' : ''}`}>{message}</div>}
          {busy && <div className="dashboard-busy">{busy}…</div>}
        </main>
      </div>

      {project && syncDecisionOpen && link && (
        <SyncDecisionModal
          status={link}
          projectName={activeProjectName(project)}
          projectSavedAt={project.lastSavedAt || project.modified || ''}
          busy={!!busy}
          onClose={() => setSyncDecisionOpen(false)}
          onResolve={resolveSync}
        />
      )}
      {project && pageManagerOpen && (
        <PageManagerModal
          project={project}
          busy={!!busy}
          onClose={() => setPageManagerOpen(false)}
          onSave={savePageSelection}
          onOpenPage={openPage}
        />
      )}
      {qualityOpen && (
        <WorkbookQualityModal
          report={quality}
          busy={!!busy}
          onClose={() => setQualityOpen(false)}
          onRefresh={refreshQuality}
          onRepair={repairQuality}
        />
      )}
      {project && deleteOpen && (
        <DeleteProjectModal
          projectName={activeProjectName(project)}
          busy={!!busy}
          onClose={() => setDeleteOpen(false)}
          onDelete={removeProject}
        />
      )}
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
              <LibraryPanelV2 onInsert={() => undefined} canInsert={false} onOpenLegendEditor={() => project && window.location.assign(actionUrl('symbol-legend'))} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
