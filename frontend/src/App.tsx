import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createProjectFromWorkbook, exportPdf, getProject, savePages, saveProject } from './api/client';
import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, ViewMode } from './model/types';
import ProjectShell from './components/ProjectShell';
import SheetManager from './components/SheetManager';
import WorkbookView from './components/WorkbookView';
import DocumentView, { type FitMode, MAX_SCALE, MIN_SCALE } from './components/DocumentView';
import PropertiesPanel from './components/PropertiesPanel';
import PrintView from './components/PrintView';
import Ribbon, { type ViewControls } from './components/Ribbon';
import CollapsibleSection from './components/CollapsibleSection';
import StatusBar from './components/StatusBar';

function getUrlParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    projectId: params.get('project'),
    print: params.get('print') === '1',
  };
}

const clampScale = (v: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, v));
const CANVAS_TYPES = new Set(['canvas', 'hybrid', 'underlay']);

export default function App() {
  const { projectId: initialProjectId, print: printMode } = getUrlParams();

  const [project, setProject] = useState<ProjectModel | null>(null);
  const [activePageId, setActivePageId] = useState<string | null>(null);
  const [selectedWorksheetId, setSelectedWorksheetId] = useState<string | undefined>(undefined);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle');

  // Viewport view-state.
  const [fitMode, setFitMode] = useState<FitMode>('page');
  const [actualZoom, setActualZoom] = useState(1);
  const [effectiveScale, setEffectiveScale] = useState(0.5);
  const [showGrid, setShowGrid] = useState(false);
  const [snap, setSnap] = useState(false);

  // Rendering + editing state.
  const [viewMode, setViewMode] = useState<ViewMode>('normalized');
  const [activeTool, setActiveTool] = useState('select');
  const [selection, setSelection] = useState<CanvasSelection | null>(null);
  const canvasApiRef = useRef<CanvasApi | null>(null);

  useEffect(() => {
    if (!initialProjectId) return;
    void getProject(initialProjectId).then((p) => {
      setProject(p);
      setActivePageId(p.pages?.[0]?.id ?? null);
      setSelectedWorksheetId(p.worksheets?.[0]?.id);
    });
  }, [initialProjectId]);

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

  const onScaleChange = useCallback((s: number) => setEffectiveScale(s), []);
  const onRegisterApi = useCallback((api: CanvasApi | null) => {
    canvasApiRef.current = api;
  }, []);
  const onSelectionChange = useCallback((sel: CanvasSelection | null) => setSelection(sel), []);
  const onToolConsumed = useCallback(() => setActiveTool('select'), []);

  const view: ViewControls = {
    fitMode,
    showGrid,
    snap,
    zoomPct: Math.round(effectiveScale * 100),
    setFitMode,
    setActual: () => {
      setFitMode('actual');
      setActualZoom(1);
    },
    zoomIn: () => {
      setActualZoom(clampScale(effectiveScale + 0.1));
      setFitMode('actual');
    },
    zoomOut: () => {
      setActualZoom(clampScale(effectiveScale - 0.1));
      setFitMode('actual');
    },
    toggleGrid: () => setShowGrid((g) => !g),
    toggleSnap: () => setSnap((s) => !s),
  };

  // ── PRINT MODE (Playwright PDF export at /app?project=<id>&print=1) ──
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
    setSelection(null);
    window.history.replaceState({}, '', `?project=${id}`);
  };

  const onExportPdf = async () => {
    if (!project) return;
    const blob = await exportPdf(project.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.metadata.projectName || project.id}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const onBlockChange = (pageId: string, blockId: string, patch: Partial<PageBlock>) => {
    setProject((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        pages: prev.pages.map((pg) =>
          pg.id === pageId
            ? { ...pg, blocks: (pg.blocks ?? []).map((b) => (b.id === blockId ? { ...b, ...patch } : b)) }
            : pg,
        ),
      };
    });
  };

  const canvasEnabled =
    !!activePage && viewMode === 'normalized' && CANVAS_TYPES.has(activePage.pageType);

  const ribbon = (
    <Ribbon
      saveStatus={saveStatus}
      hasProject={!!project}
      view={view}
      canvasEnabled={canvasEnabled}
      activeTool={activeTool}
      onSetTool={setActiveTool}
      canvas={{
        addText: () => canvasApiRef.current?.addText(),
        addRect: () => canvasApiRef.current?.addRect(),
        addLine: () => canvasApiRef.current?.addLine(),
        addArrow: () => canvasApiRef.current?.addArrow(),
        deleteSelected: () => canvasApiRef.current?.deleteSelected(),
        duplicateSelected: () => canvasApiRef.current?.duplicateSelected(),
        undo: () => canvasApiRef.current?.undo(),
        redo: () => canvasApiRef.current?.redo(),
      }}
      onUploadFile={(f) => void onUploadWorkbook(f)}
      onSaveNow={() => project && void saveProject(project)}
      onExportPdf={() => void onExportPdf()}
    />
  );

  // ── Empty state (no project loaded yet) ──
  if (!project || !activePage) {
    return (
      <ProjectShell
        ribbon={ribbon}
        left={<div className="nav-section-head">Output Pages</div>}
        center={
          <div className="empty-stage">
            <div className="empty-card">
              <h2>No workbook loaded</h2>
              <p>Choose a workbook (.xlsx) from the File tab to generate output pages and begin editing your drawing package.</p>
            </div>
          </div>
        }
        right={<div className="props-group"><h3>Project Properties</h3></div>}
      />
    );
  }

  const includedCount = project.pages.filter((p) => p.include).length;

  return (
    <ProjectShell
      ribbon={ribbon}
      left={
        <>
          <CollapsibleSection title="Output Pages">
            <SheetManager pages={project.pages} activePageId={activePageId} onSelect={setActivePageId} onUpdate={(p) => void updatePages(p)} />
          </CollapsibleSection>
          <CollapsibleSection title="Source Tabs" defaultOpen={false}>
            <WorkbookView worksheets={project.worksheets} selectedWorksheetId={selectedWorksheetId} onSelectWorksheet={setSelectedWorksheetId} />
          </CollapsibleSection>
        </>
      }
      center={
        <DocumentView
          project={project}
          pages={project.pages}
          activePage={activePage}
          worksheets={project.worksheets}
          view={view}
          actualZoom={actualZoom}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          activeTool={activeTool}
          snap={snap}
          onToolConsumed={onToolConsumed}
          onRegisterApi={onRegisterApi}
          onSelectionChange={onSelectionChange}
          onBlockChange={onBlockChange}
          onSelectPage={(id) => {
            setActivePageId(id);
            setSelection(null);
          }}
          onScaleChange={onScaleChange}
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
            selection={selection}
            onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
          />
        </div>
      }
      status={
        <StatusBar
          pageCount={project.pages.length}
          includedCount={includedCount}
          worksheetCount={project.worksheets.length}
          activeLabel={`${activePage.sheetCode} ${activePage.sheetTitle}`}
          zoomPct={Math.round(effectiveScale * 100)}
        />
      }
    />
  );
}
