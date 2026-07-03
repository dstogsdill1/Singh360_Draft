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
import ComponentLibrary from './components/ComponentLibrary';
import DocumentView, { type FitMode, MAX_SCALE, MIN_SCALE } from './components/DocumentView';
import PropertiesPanel from './components/PropertiesPanel';
import PrintView from './components/PrintView';
import Ribbon, { type ViewControls } from './components/Ribbon';
import RenumberModal from './components/RenumberModal';
import SheetContextMenu from './components/SheetContextMenu';
import ExportModal from './components/ExportModal';
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
  const [exportOpen, setExportOpen] = useState(false);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number } | null>(null);
  const [pageMenu, setPageMenu] = useState<{ x: number; y: number; pageId: string } | null>(null);
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

  // Insert a library component (image asset) onto the ACTIVE page only.
  const onInsertComponent = (name: string, url: string, label: string | null) => {
    if (!isCanvasContext()) return;
    setOverlayMode(true);
    canvasApiRef.current?.addComponent(url, name, label);
  };

  const onDropComponent = (url: string, name: string, label: string | null, clientX: number, clientY: number) => {
    if (!isCanvasContext()) return;
    setOverlayMode(true);
    canvasApiRef.current?.addComponent(url, name, label, { clientX, clientY });
  };

  // Explicit "Paste Image" via the app context menu. Uses the async Clipboard
  // API when the browser allows it; otherwise instructs the user to press Ctrl+V
  // (never silently fails).
  const pasteImageFromClipboard = async () => {
    if (!isCanvasContext()) return;
    try {
      const nav = navigator as Navigator & { clipboard?: { read?: () => Promise<ClipboardItem[]> } };
      if (!nav.clipboard?.read) {
        window.alert('Press Ctrl+V to paste your screenshot.');
        return;
      }
      const items = await nav.clipboard.read();
      for (const item of items) {
        const type = item.types.find((t) => t.startsWith('image/'));
        if (type) {
          const blob = await item.getType(type);
          const reader = new FileReader();
          reader.onload = () => {
            if (typeof reader.result === 'string') void addImageFromDataUrl(reader.result, screenshotName());
          };
          reader.readAsDataURL(blob);
          return;
        }
      }
      window.alert('No image found on the clipboard. Press Ctrl+V to paste a screenshot.');
    } catch {
      window.alert('Clipboard image paste was blocked by the browser. Press Ctrl+V to paste your screenshot instead.');
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

  // App-level right-click menu on the sheet body (suppress the browser menu).
  useEffect(() => {
    const onCtx = (e: MouseEvent) => {
      const t = e.target as HTMLElement | null;
      if (!t || !t.closest('.sheet-viewport')) return;
      // Tables/matrices provide their own row/column context menu.
      if (t.closest('.np-table, .np-matrix')) return;
      if (!isCanvasContext()) return;
      e.preventDefault();
      setCtxMenu({ x: e.clientX, y: e.clientY });
    };
    window.addEventListener('contextmenu', onCtx);
    return () => window.removeEventListener('contextmenu', onCtx);
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

  // ── Structural page operations (used by tab + left-list context menus) ──
  const newPageId = () => `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

  const mutatePages = (fn: (pages: PageModel[]) => PageModel[]) => {
    if (!project) return;
    const next = withPageNumbers(fn(project.pages).map((p, i) => ({ ...p, order: i + 1 })));
    setProject({ ...project, pages: next });
    void savePages(project.id, next);
  };

  const duplicatePage = (id: string) => {
    mutatePages((pages) => {
      const idx = pages.findIndex((p) => p.id === id);
      if (idx < 0) return pages;
      const src = pages[idx];
      const copy: PageModel = {
        ...structuredClone(src),
        id: newPageId(),
        sheetTitle: `${src.sheetTitle} Copy`,
        continuationOf: null,
        generatedContinuation: false,
        continuationIndex: undefined,
      };
      const out = [...pages];
      out.splice(idx + 1, 0, copy);
      return out;
    });
  };

  const addPage = (refId: string, where: 'before' | 'after') => {
    const title = window.prompt('New sheet title:', 'New Sheet');
    if (title === null) return;
    const code = window.prompt('Sheet code:', '') ?? '';
    mutatePages((pages) => {
      const idx = pages.findIndex((p) => p.id === refId);
      if (idx < 0) return pages;
      const blank: PageModel = {
        id: newPageId(),
        order: 0,
        include: true,
        sheetCode: code,
        displaySheetCode: code,
        sheetTitle: title || 'New Sheet',
        sheetTab: '',
        pageType: 'data-grid',
        template: 'Text / Instructions',
        templateId: '',
        blocks: [{ id: `b_${newPageId()}`, type: 'paragraph', text: '' }],
        canvasObjects: [],
        notes: '',
      };
      const out = [...pages];
      out.splice(where === 'before' ? idx : idx + 1, 0, blank);
      return out;
    });
  };

  const deletePage = (id: string) => {
    if (!window.confirm('Delete this page? This cannot be undone. (Tip: use Exclude to keep it out of the package instead.)')) return;
    if (activePageId === id) {
      const remaining = project?.pages.filter((p) => p.id !== id) ?? [];
      setActivePageId(remaining[0]?.id ?? null);
    }
    mutatePages((pages) => pages.filter((p) => p.id !== id));
  };

  const toggleInclude = (id: string) =>
    mutatePages((pages) => pages.map((p) => (p.id === id ? { ...p, include: !p.include } : p)));

  const movePage = (id: string, dir: -1 | 1) =>
    mutatePages((pages) => {
      const idx = pages.findIndex((p) => p.id === id);
      const t = idx + dir;
      if (idx < 0 || t < 0 || t >= pages.length) return pages;
      const out = [...pages];
      [out[idx], out[t]] = [out[t], out[idx]];
      return out;
    });

  const makeIndependent = (id: string) =>
    mutatePages((pages) =>
      pages.map((p) =>
        p.id === id ? { ...p, continuationOf: null, generatedContinuation: false, continuationIndex: undefined } : p,
      ),
    );

  const mergeContinuationIntoPrevious = (id: string) => {
    mutatePages((pages) => {
      const idx = pages.findIndex((p) => p.id === id);
      if (idx <= 0) return pages;
      const cont = pages[idx];
      const baseId = cont.continuationOf;
      const baseIdx = baseId ? pages.findIndex((p) => p.id === baseId) : idx - 1;
      const target = baseIdx >= 0 ? baseIdx : idx - 1;
      const base = pages[target];
      const mergedBlocks = [...(base.blocks ?? []), ...(cont.blocks ?? [])];
      const out = pages
        .map((p, i) => (i === target ? { ...base, blocks: mergedBlocks, layoutWarnings: ['Merged from continuation — verify it fits one sheet.'] } : p))
        .filter((p) => p.id !== id);
      return out;
    });
  };

  const renamePagePrompt = (id: string) => {
    const cur = project?.pages.find((p) => p.id === id);
    const v = window.prompt('Sheet title:', cur?.sheetTitle ?? '');
    if (v !== null) patchPage(id, { sheetTitle: v.trim() || 'Untitled Sheet' });
  };
  const editCodePrompt = (id: string) => {
    const cur = project?.pages.find((p) => p.id === id);
    const v = window.prompt('Sheet code:', cur?.displaySheetCode || cur?.sheetCode || '');
    if (v !== null) patchPage(id, { sheetCode: v.trim(), displaySheetCode: v.trim() });
  };

  // Build the shared page-action menu for a page id (tab + left list reuse it).
  const buildPageActions = (id: string) => {
    const pg = project?.pages.find((p) => p.id === id);
    const isCont = !!pg?.continuationOf || !!pg?.generatedContinuation;
    const actions = [
      { label: 'Rename Sheet Title', onClick: () => renamePagePrompt(id) },
      { label: 'Edit Sheet Code', onClick: () => editCodePrompt(id) },
      { label: 'Duplicate Page', divider: true, onClick: () => duplicatePage(id) },
      { label: 'Add Page Before', onClick: () => addPage(id, 'before') },
      { label: 'Add Page After', onClick: () => addPage(id, 'after') },
      { label: pg?.include ? 'Exclude Page' : 'Include Page', divider: true, onClick: () => toggleInclude(id) },
      { label: 'Delete Page', onClick: () => deletePage(id) },
      { label: 'Move Left', divider: true, onClick: () => movePage(id, -1) },
      { label: 'Move Right', onClick: () => movePage(id, 1) },
    ];
    if (isCont) {
      actions.push(
        { label: 'Make Independent', divider: true, onClick: () => makeIndependent(id) },
        { label: 'Merge Into Previous', onClick: () => mergeContinuationIntoPrevious(id) },
      );
    }
    return actions;
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

  const onExportPdfSized = async (width: number, height: number) => {
    if (!project) return;
    setExportOpen(false);
    const blob = await exportPdf(project.id, { width, height });
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
        addPageTitle: () => { setOverlayMode(true); canvasApiRef.current?.addPageTitle(activePage?.sheetTitle ?? 'Page Title'); },
        addSectionHeader: () => { setOverlayMode(true); canvasApiRef.current?.addSectionHeader('Section Header'); },
        addNote: () => { setOverlayMode(true); canvasApiRef.current?.addNote('Note'); },
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
      onInsertImage={(f) => void onDropImageFile(f)}
      onSaveNow={() => project && void saveProject(project)}
      onExportPdf={() => setExportOpen(true)}
      onExportPackage={() => void onExportPackage()}
      onRenumber={onRenumber}
      selection={selection}
      onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
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
            <SheetManager pages={project.pages} activePageId={activePageId} onSelect={setActivePageId} onUpdate={(p) => void updatePages(p)} onContextMenu={(id, x, y) => setPageMenu({ x, y, pageId: id })} />
          </CollapsibleSection>
          <CollapsibleSection title="Source Tabs" defaultOpen={false}>
            <WorkbookView worksheets={project.worksheets} selectedWorksheetId={selectedWorksheetId} onSelectWorksheet={setSelectedWorksheetId} />
          </CollapsibleSection>
          <CollapsibleSection title="Component Library" defaultOpen={false}>
            <ComponentLibrary onInsert={onInsertComponent} canInsert={canvasEnabled} />
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
          onPageContextMenu={(id, x, y) => setPageMenu({ x, y, pageId: id })}
          onDropImageFile={(file) => void onDropImageFile(file)}
          onDropComponent={onDropComponent}
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
    {exportOpen && (
      <ExportModal onExport={(w, h) => void onExportPdfSized(w, h)} onCancel={() => setExportOpen(false)} />
    )}
    {ctxMenu && (
      <SheetContextMenu
        x={ctxMenu.x}
        y={ctxMenu.y}
        onClose={() => setCtxMenu(null)}
        actions={[
          { label: 'Paste Image (Ctrl+V)', onClick: () => void pasteImageFromClipboard(), hint: 'Paste a screenshot from the clipboard' },
          { label: 'Insert Text Box', divider: true, onClick: () => { setOverlayMode(true); canvasApiRef.current?.addText(); } },
          { label: 'Insert Arrow', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addArrow(); } },
          { label: 'Insert Line', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addLine(); } },
          { label: 'Duplicate', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.duplicateSelected() },
          { label: 'Delete', disabled: !selection, onClick: () => canvasApiRef.current?.deleteSelected() },
          { label: 'Bring to Front', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.bringToFront() },
          { label: 'Send to Back', disabled: !selection, onClick: () => canvasApiRef.current?.sendToBack() },
          { label: selection?.locked ? 'Unlock' : 'Lock', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.updateSelected({ locked: !selection?.locked }) },
        ]}
      />
    )}
    {pageMenu && (
      <SheetContextMenu
        x={pageMenu.x}
        y={pageMenu.y}
        onClose={() => setPageMenu(null)}
        actions={buildPageActions(pageMenu.pageId)}
      />
    )}
    </>
  );
}
