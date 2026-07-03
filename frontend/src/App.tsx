import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  attachCsv,
  createProjectFromWorkbook,
  exportPackage,
  exportPdf,
  getProject,
  renameProject,
  savePages,
  saveProject,
  uploadAssetDataUrl,
  uploadAssetFile,
} from './api/client';
import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, ViewMode } from './model/types';
import ProjectShell from './components/ProjectShell';
import SheetManager from './components/SheetManager';
import WorkbookView from './components/WorkbookView';
import DocumentView, { type FitMode, MAX_SCALE, MIN_SCALE } from './components/DocumentView';
import PropertiesPanel from './components/PropertiesPanel';
import PrintView from './components/PrintView';
import Ribbon, { type ViewControls } from './components/Ribbon';
import RenumberModal from './components/RenumberModal';
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

function screenshotName(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `Screenshot ${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}.png`;
}

// Recompute live "Page X of Y" numbering across included, non-continuation pages.
function withPageNumbers(pages: PageModel[]): PageModel[] {
  const included = pages.filter((p) => p.include && !p.continuationOf);
  const total = included.length;
  let n = 0;
  const numberById = new Map<string, number>();
  for (const p of included) {
    n += 1;
    numberById.set(p.id, n);
  }
  return pages.map((p) => {
    if (!p.include) return { ...p, pageNumber: null, pageTotal: total };
    if (p.continuationOf) {
      const parentNum = numberById.get(p.continuationOf) ?? null;
      return { ...p, pageNumber: parentNum, pageTotal: total };
    }
    return { ...p, pageNumber: numberById.get(p.id) ?? null, pageTotal: total };
  });
}

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
  const [overlayMode, setOverlayMode] = useState(false);
  const [selection, setSelection] = useState<CanvasSelection | null>(null);
  const [renumberOpen, setRenumberOpen] = useState(false);
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

  // Refs so global paste/keyboard handlers read current values.
  const projectRef = useRef(project);
  const activePageRef = useRef(activePage);
  const viewModeRef = useRef(viewMode);
  projectRef.current = project;
  activePageRef.current = activePage;
  viewModeRef.current = viewMode;

  const isCanvasContext = () =>
    !!activePageRef.current &&
    viewModeRef.current === 'normalized';

  const addImageFromDataUrl = async (dataUrl: string, name: string) => {
    const pid = projectRef.current?.id;
    if (!pid) return;
    try {
      const asset = await uploadAssetDataUrl(pid, dataUrl, name);
      setOverlayMode(true);
      canvasApiRef.current?.addImage(asset.url, asset.name);
    } catch (err) {
      console.error('paste image failed', err);
    }
  };

  const onDropImageFile = async (file: File) => {
    const pid = projectRef.current?.id;
    if (!pid || !isCanvasContext()) return;
    try {
      const asset = await uploadAssetFile(pid, file);
      setOverlayMode(true);
      canvasApiRef.current?.addImage(asset.url, asset.name);
    } catch (err) {
      console.error('drop image failed', err);
    }
  };

  // Global clipboard paste → image onto active canvas page.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (!isCanvasContext()) return;
      const items = e.clipboardData?.items;
      if (!items) return;
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (it.type.startsWith('image/')) {
          const file = it.getAsFile();
          if (file) {
            e.preventDefault();
            const reader = new FileReader();
            reader.onload = () => {
              if (typeof reader.result === 'string') void addImageFromDataUrl(reader.result, screenshotName());
            };
            reader.readAsDataURL(file);
          }
          return;
        }
      }
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Global keyboard: delete / undo / redo / duplicate on canvas (not while typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      if (!isCanvasContext()) return;
      const k = e.key.toLowerCase();
      if (e.key === 'Delete') {
        canvasApiRef.current?.deleteSelected();
      } else if ((e.ctrlKey || e.metaKey) && k === 'z') {
        e.preventDefault();
        canvasApiRef.current?.undo();
      } else if ((e.ctrlKey || e.metaKey) && k === 'y') {
        e.preventDefault();
        canvasApiRef.current?.redo();
      } else if ((e.ctrlKey || e.metaKey) && k === 'd') {
        e.preventDefault();
        canvasApiRef.current?.duplicateSelected();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    const numbered = withPageNumbers(pages);
    const next: ProjectModel = { ...project, pages: numbered };
    setProject(next);
    await savePages(project.id, numbered);
  };

  // Single source of truth for per-page edits. Every edit surface (tab, left
  // list, page heading, right panel) funnels through here so all views stay in
  // sync, page numbering stays correct, and the change autosaves.
  const patchPage = (pageId: string, patch: Partial<PageModel>) => {
    setProject((prev) => {
      if (!prev) return prev;
      const pages = withPageNumbers(prev.pages.map((p) => (p.id === pageId ? { ...p, ...patch } : p)));
      return { ...prev, pages };
    });
  };

  const onRenamePageTitle = (pageId: string, title: string) => patchPage(pageId, { sheetTitle: title });

  const onUploadWorkbook = async (file: File) => {
    const { id } = await createProjectFromWorkbook(file);
    const p = await getProject(id);
    setProject(p);
    setActivePageId(p.pages?.[0]?.id ?? null);
    setSelectedWorksheetId(p.worksheets?.[0]?.id);
    setSelection(null);
    window.history.replaceState({}, '', `?project=${id}`);
  };

  const onUploadCsv = async (file: File) => {
    if (!project) return;
    try {
      setSaveStatus('saving');
      await attachCsv(project.id, file);
      const p = await getProject(project.id);
      setProject(p);
      setSaveStatus('saved');
    } catch (err) {
      console.error('CSV attach failed', err);
      setSaveStatus('failed');
    }
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

  const onExportPackage = async () => {
    if (!project) return;
    const blob = await exportPackage(project.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.metadata.projectName || project.id}_package.zip`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const onRenumber = () => {
    if (!project) return;
    setRenumberOpen(true);
  };

  const applyRenumber = (updated: PageModel[]) => {
    setRenumberOpen(false);
    void updatePages(updated);
  };

  const onRenameProject = async (name: string) => {
    if (!project || !name.trim()) return;
    try {
      setSaveStatus('saving');
      const res = await renameProject(project.id, name.trim());
      setProject((prev) =>
        prev
          ? {
              ...prev,
              projectDisplayName: res.projectDisplayName ?? name.trim(),
              projectFolder: res.projectFolder ?? prev.projectFolder,
              metadata: { ...prev.metadata, projectName: name.trim() },
            }
          : prev,
      );
      setSaveStatus('saved');
    } catch (err) {
      console.error('rename failed', err);
      setSaveStatus('failed');
    }
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
    !!activePage && viewMode === 'normalized';

  const ribbon = (
    <Ribbon
      saveStatus={saveStatus}
      hasProject={!!project}
      view={view}
      canvasEnabled={canvasEnabled}
      activeTool={activeTool}
      onSetTool={setActiveTool}
      overlayMode={overlayMode}
      onToggleOverlay={() => setOverlayMode((v) => !v)}
      canvas={{
        addText: () => canvasApiRef.current?.addText(),
        addRect: () => canvasApiRef.current?.addRect(),
        addCircle: () => canvasApiRef.current?.addCircle(),
        addLine: () => canvasApiRef.current?.addLine(),
        addArrow: () => canvasApiRef.current?.addArrow(),
        deleteSelected: () => canvasApiRef.current?.deleteSelected(),
        duplicateSelected: () => canvasApiRef.current?.duplicateSelected(),
        undo: () => canvasApiRef.current?.undo(),
        redo: () => canvasApiRef.current?.redo(),
        group: () => canvasApiRef.current?.group(),
        ungroup: () => canvasApiRef.current?.ungroup(),
        bringForward: () => canvasApiRef.current?.bringForward(),
        sendBackward: () => canvasApiRef.current?.sendBackward(),
        bringToFront: () => canvasApiRef.current?.bringToFront(),
        sendToBack: () => canvasApiRef.current?.sendToBack(),
      }}
      onUploadFile={(f) => void onUploadWorkbook(f)}
      onUploadCsv={(f) => void onUploadCsv(f)}
      onSaveNow={() => project && void saveProject(project)}
      onExportPdf={() => void onExportPdf()}
      onExportPackage={() => void onExportPackage()}
      onRenumber={onRenumber}
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
    <>
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
          overlayMode={overlayMode}
          onToolConsumed={onToolConsumed}
          onRegisterApi={onRegisterApi}
          onSelectionChange={onSelectionChange}
          onBlockChange={onBlockChange}
          onSelectPage={(id) => {
            setActivePageId(id);
            setSelection(null);
          }}
          onReorderPages={(pages) => void updatePages(pages)}
          onRenamePageTitle={onRenamePageTitle}
          onDropImageFile={(file) => void onDropImageFile(file)}
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
            onChange={(next) => patchPage(next.id, next)}
            selection={selection}
            onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
            projectDisplayName={project.projectDisplayName ?? project.metadata.projectName}
            projectFolder={project.projectFolder}
            onRenameProject={(name) => void onRenameProject(name)}
            overflowWarning={Array.isArray(activePage.layoutWarnings) && activePage.layoutWarnings.length > 0}
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
    {renumberOpen && (
      <RenumberModal pages={project.pages} onApply={applyRenumber} onCancel={() => setRenumberOpen(false)} />
    )}
    </>
  );
}
