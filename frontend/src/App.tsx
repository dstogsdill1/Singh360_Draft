import { useEffect, useMemo, useState } from 'react';
import { createProjectFromWorkbook, exportPdf, getProject, savePages, saveProject } from './api/client';
import type { PageModel, ProjectModel } from './model/types';
import ProjectShell from './components/ProjectShell';
import SheetManager from './components/SheetManager';
import WorkbookView from './components/WorkbookView';
import DocumentView, { type FitMode } from './components/DocumentView';
import PropertiesPanel from './components/PropertiesPanel';
import ExportPanel from './components/ExportPanel';
import PrintView from './components/PrintView';

function getUrlParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    projectId: params.get('project'),
    print: params.get('print') === '1',
  };
}

export default function App() {
  const { projectId: initialProjectId, print: printMode } = getUrlParams();

  const [project, setProject] = useState<ProjectModel | null>(null);
  const [activePageId, setActivePageId] = useState<string | null>(null);
  const [selectedWorksheetId, setSelectedWorksheetId] = useState<string | undefined>(undefined);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle');
  const [fitMode, setFitMode] = useState<FitMode>('width');

  // Load an existing project when a project id is present in the URL.
  useEffect(() => {
    if (!initialProjectId) return;
    void getProject(initialProjectId).then((p) => {
      setProject(p);
      setActivePageId(p.pages?.[0]?.id ?? null);
      setSelectedWorksheetId(p.worksheets?.[0]?.id);
    });
  }, [initialProjectId]);

  // Autosave (disabled in print mode).
  useEffect(() => {
    if (!project || printMode) return;
    const t = setTimeout(async () => {
      try {
        setSaveStatus('saving');
        await saveProject(project);
        setSaveStatus('saved');
      } catch {
        setSaveStatus('failed');
      }
    }, 600);
    return () => clearTimeout(t);
  }, [project, printMode]);

  const activePage = useMemo(() => {
    if (!project || !activePageId) return null;
    return project.pages.find((p) => p.id === activePageId) ?? null;
  }, [project, activePageId]);

  // ── PRINT MODE (used by Playwright PDF export at /app?project=<id>&print=1) ──
  if (printMode) {
    return <PrintView project={project} />;
  }

  const updatePages = async (pages: PageModel[]) => {
    if (!project) return;
    const next: ProjectModel = { ...project, pages };
    setProject(next);
    await savePages(project.id, pages);
  };

  const onUploadWorkbook = async (file: File) => {
    const { id } = await createProjectFromWorkbook(file);
    const p = await getProject(id);
    setProject(p);
    setActivePageId(p.pages?.[0]?.id ?? null);
    setSelectedWorksheetId(p.worksheets?.[0]?.id);
    window.history.replaceState({}, '', `?project=${id}`);
  };

  const uploadButton = (
    <label className="file-btn">
      <span>Upload Workbook</span>
      <input
        title="Upload Workbook"
        type="file"
        accept=".xlsx"
        onChange={(e) => e.target.files?.[0] && void onUploadWorkbook(e.target.files[0])}
      />
    </label>
  );

  const brand = (
    <div className="toolbar-brand">
      <span className="brand-main">Singh360 Draft</span>
      <span className="brand-sub">Drawing Package Editor</span>
    </div>
  );

  // ── Empty state (no project loaded yet) ──
  if (!project || !activePage) {
    return (
      <ProjectShell
        toolbar={
          <>
            {brand}
            <div className="toolbar-actions">{uploadButton}</div>
          </>
        }
        left={<div className="panel-section-head">Output Pages</div>}
        center={
          <div className="empty-stage">
            <div className="empty-card">
              <h2>No workbook loaded</h2>
              <p>Choose a workbook (.xlsx) to generate output pages and begin editing your drawing package.</p>
              {uploadButton}
            </div>
          </div>
        }
        right={<div className="props-group"><h3>Project Properties</h3></div>}
      />
    );
  }

  return (
    <ProjectShell
      toolbar={
        <>
          {brand}
          <div className="toolbar-actions">
            {uploadButton}
            <button className="btn" onClick={() => void saveProject(project)}>Save Now</button>
            <ExportPanel
              onExportPdf={async () => {
                const blob = await exportPdf(project.id);
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${project.metadata.projectName || project.id}.pdf`;
                a.click();
                URL.revokeObjectURL(url);
              }}
            />
          </div>
          <div className="toolbar-right">
            <span className={`status-pill ${saveStatus}`}>{saveStatus}</span>
          </div>
        </>
      }
      left={
        <>
          <SheetManager pages={project.pages} activePageId={activePageId} onSelect={setActivePageId} onUpdate={(p) => void updatePages(p)} />
          <WorkbookView worksheets={project.worksheets} selectedWorksheetId={selectedWorksheetId} onSelectWorksheet={setSelectedWorksheetId} />
        </>
      }
      center={
        <DocumentView
          project={project}
          activePage={activePage}
          worksheets={project.worksheets}
          fitMode={fitMode}
          onFitModeChange={setFitMode}
          onGridChange={(wsId, grid) => {
            setProject({
              ...project,
              worksheets: project.worksheets.map((ws) => (ws.id === wsId ? { ...ws, grid } : ws)),
            });
          }}
          onCanvasChange={(pageId, objects) => {
            setProject({
              ...project,
              pages: project.pages.map((pg) => (pg.id === pageId ? { ...pg, canvasObjects: objects } : pg)),
            });
          }}
        />
      }
      right={
        <div className="props">
          <div className="props-group">
            <h3>Project Properties</h3>
            <div className="field">
              <label htmlFor="proj-name">Project Name</label>
              <input
                id="proj-name"
                value={project.metadata.projectName || ''}
                onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, projectName: e.target.value } })}
              />
            </div>
            <div className="field">
              <label htmlFor="proj-loc">Location</label>
              <input
                id="proj-loc"
                value={project.metadata.location || ''}
                onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, location: e.target.value } })}
              />
            </div>
            <div className="field">
              <label htmlFor="proj-file">File</label>
              <input id="proj-file" value={project.metadata.sourceFile || ''} readOnly />
            </div>
          </div>
          <PropertiesPanel
            page={activePage}
            onChange={(next) => setProject({ ...project, pages: project.pages.map((p) => (p.id === next.id ? next : p)) })}
          />
        </div>
      }
    />
  );
}
