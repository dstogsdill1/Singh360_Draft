import { useEffect, useMemo, useState } from 'react';
import { createProjectFromWorkbook, exportPdf, getProject, savePages, saveProject } from './api/client';
import type { PageModel, ProjectModel } from './model/types';
import ProjectShell from './components/ProjectShell';
import SheetManager from './components/SheetManager';
import WorkbookView from './components/WorkbookView';
import DocumentView from './components/DocumentView';
import PropertiesPanel from './components/PropertiesPanel';
import ExportPanel from './components/ExportPanel';

function getProjectIdFromUrl() {
  return new URLSearchParams(window.location.search).get('project');
}

export default function App() {
  const [project, setProject] = useState<ProjectModel | null>(null);
  const [activePageId, setActivePageId] = useState<string | null>(null);
  const [selectedWorksheetId, setSelectedWorksheetId] = useState<string | undefined>(undefined);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle');

  useEffect(() => {
    const id = getProjectIdFromUrl();
    if (!id) return;
    void getProject(id).then((p) => {
      setProject(p);
      setActivePageId(p.pages?.[0]?.id ?? null);
      setSelectedWorksheetId(p.worksheets?.[0]?.id);
    });
  }, []);

  useEffect(() => {
    if (!project) return;
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
  }, [project]);

  const activePage = useMemo(() => {
    if (!project || !activePageId) return null;
    return project.pages.find((p) => p.id === activePageId) ?? null;
  }, [project, activePageId]);

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

  if (!project || !activePage) {
    return (
      <ProjectShell
        toolbar={<><strong>Singh360 SmartDraw</strong></>}
        left={<div className="panel-padding"><input title="Upload workbook" type="file" accept=".xlsx" onChange={(e) => e.target.files?.[0] && void onUploadWorkbook(e.target.files[0])} /></div>}
        center={<div className="panel-intro">Upload SA31 workbook to begin.</div>}
        right={<div />}
      />
    );
  }

  return (
    <ProjectShell
      toolbar={
        <>
          <strong>Singh360 SmartDraw</strong>
          <input title="Upload workbook" type="file" accept=".xlsx" onChange={(e) => e.target.files?.[0] && void onUploadWorkbook(e.target.files[0])} />
          <button onClick={() => void saveProject(project)}>Save Now</button>
          <ExportPanel
            onExportPdf={async () => {
              const blob = await exportPdf(project.id);
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${project.id}.pdf`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          />
          <span className="status-pill">{saveStatus}</span>
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
        <>
          <div className="meta-grid">
            <label>Project Name</label>
            <input
              title="Project Name"
              placeholder="Project Name"
              value={project.metadata.projectName || ''}
              onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, projectName: e.target.value } })}
            />
            <label>Location</label>
            <input
              title="Location"
              placeholder="Location"
              value={project.metadata.location || ''}
              onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, location: e.target.value } })}
            />
          </div>
          <PropertiesPanel
            page={activePage}
            onChange={(next) => setProject({ ...project, pages: project.pages.map((p) => (p.id === next.id ? next : p)) })}
          />
        </>
      }
    />
  );
}
