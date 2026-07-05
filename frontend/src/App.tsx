import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  archiveProject,
  attachCsv,
  createProjectFromWorkbook,
  exportPackage,
  exportPdf,
  getProject,
  importWorksheets,
  previewImportWorksheets,
  renameProject,
  savePages,
  saveProject,
  uploadAssetDataUrl,
  uploadAssetFile,
} from './api/client';
import type { CanvasApi, CanvasSelection, LineStyle, PageBlock, PageModel, ProjectModel, ViewMode } from './model/types';
import ProjectShell from './components/ProjectShell';
import SheetManager from './components/SheetManager';
import WorkbookView from './components/WorkbookView';
import LibraryPanelV2 from './components/LibraryPanelV2';
import DocumentView, { type FitMode, MAX_SCALE, MIN_SCALE } from './components/DocumentView';
import PropertiesPanel from './components/PropertiesPanel';
import PrintView from './components/PrintView';
import Ribbon, { type ViewControls } from './components/Ribbon';
import RenumberModal from './components/RenumberModal';
import OpenProjectModal from './components/OpenProjectModal';
import CleanWorkspaceModal from './components/CleanWorkspaceModal';
import ImportWorksheetModal from './components/ImportWorksheetModal';
import AddSheetModal from './components/AddSheetModal';
import SheetContextMenu from './components/SheetContextMenu';
import ExportModal from './components/ExportModal';
import PdfInsertModal from './components/PdfInsertModal';
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
  const [snap, setSnap] = useState(true);

  // Rendering + editing state.
  const [viewMode, setViewMode] = useState<ViewMode>('normalized');
  const [activeTool, setActiveTool] = useState('select');
  const [overlayMode, setOverlayMode] = useState(false);
  const [lineStyle, setLineStyle] = useState<LineStyle>({
    stroke: '#111111', dash: 'solid', strokeWidth: 2, arrowStart: false, arrowEnd: false,
  });
  const [selection, setSelection] = useState<CanvasSelection | null>(null);
  const [renumberOpen, setRenumberOpen] = useState(false);
  const [openProjectOpen, setOpenProjectOpen] = useState(false);
  const [cleanWorkspaceOpen, setCleanWorkspaceOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [pdfInsertOpen, setPdfInsertOpen] = useState(false);
  const [addSheetPending, setAddSheetPending] = useState<{ refId: string; where: 'before' | 'after' } | null>(null);
  const [importWsOpen, setImportWsOpen] = useState<{ afterPageId?: string } | null>(null);
  const [renumberBadge, setRenumberBadge] = useState(false);
  const [theme, setThemeState] = useState<'dark' | 'light'>(() => {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem('singh360-theme') : null;
    return saved === 'light' ? 'light' : 'dark';
  });
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('singh360-theme', theme); } catch { /* ignore */ }
  }, [theme]);
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

  // Auto-enable overlay edit mode when the active page has overlay objects or is
  // a drawing page, so existing objects are immediately selectable/movable and
  // the Text/Draw toolbars unlock. On empty content pages, leave the base
  // editable (overlay off). Runs only on page change.
  useEffect(() => {
    const p = activePage;
    if (!p) return;
    const hasObjects = (p.canvasObjects?.length ?? 0) > 0;
    const drawingPage = p.pageType === 'canvas' || p.pageType === 'hybrid' || p.pageType === 'underlay';
    setOverlayMode(hasObjects || drawingPage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePageId]);

  const onScaleChange = useCallback((s: number) => setEffectiveScale(s), []);
  const lineStyleRef = useRef(lineStyle);
  lineStyleRef.current = lineStyle;
  const onRegisterApi = useCallback((api: CanvasApi | null) => {
    canvasApiRef.current = api;
    if (api) api.setLineStyle(lineStyleRef.current);
  }, []);
  const onSelectionChange = useCallback((sel: CanvasSelection | null) => setSelection(sel), []);
  const onToolConsumed = useCallback(() => setActiveTool('select'), []);

  // Push the current new-line style down to the canvas whenever it changes.
  useEffect(() => {
    canvasApiRef.current?.setLineStyle(lineStyle);
  }, [lineStyle]);

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

  // Insert BOTH the source image and the B/W symbol side-by-side ("Both" mode).
  const onInsertComponentBoth = (name: string, sourceUrl: string, symbolUrl: string, label: string | null) => {
    if (!isCanvasContext()) return;
    setOverlayMode(true);
    canvasApiRef.current?.addComponentPair(sourceUrl, symbolUrl, name, label);
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

  // Global clipboard paste → image or text onto active canvas page.
  // Priority: image/png > image/* > SVG from text/html > HTML table → text box > text/plain
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (!isCanvasContext()) return;
      const items = e.clipboardData?.items;
      if (!items) return;

      // 1. Native image types: highest quality, store as asset.
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

      // 2. SVG from text/html or text/plain.
      const htmlItem = Array.from(items).find((it) => it.type === 'text/html');
      const plainItem = Array.from(items).find((it) => it.type === 'text/plain');

      if (htmlItem) {
        htmlItem.getAsString((html) => {
          // Check for inline SVG.
          if (html.includes('<svg')) {
            const svgMatch = html.match(/<svg[\s\S]*?<\/svg>/i);
            if (svgMatch) {
              const svgB64 = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svgMatch[0])))}`;
              void addImageFromDataUrl(svgB64, screenshotName());
              return;
            }
          }
          // Check for <img> tag.
          const imgMatch = html.match(/<img[^>]+src="([^"]+)"/i);
          if (imgMatch) {
            const src = imgMatch[1];
            if (src.startsWith('data:image')) {
              void addImageFromDataUrl(src, screenshotName());
              return;
            }
          }
          // Check for HTML table → offer as text (user can Import Worksheet for full table).
          const hasTable = /<table[\s\S]*?<\/table>/i.test(html);
          if (hasTable) {
            // Strip tags → plain text fallback for now; a full Table paste modal is Phase F/L.
            const div = document.createElement('div');
            div.innerHTML = html;
            const text = (div.textContent || '').trim();
            if (text) {
              setOverlayMode(true);
              canvasApiRef.current?.addNote(text.slice(0, 1000));
            }
            return;
          }
          // Formatted text → text box.
          const div2 = document.createElement('div');
          div2.innerHTML = html;
          const text2 = (div2.textContent || '').trim();
          if (text2) {
            setOverlayMode(true);
            canvasApiRef.current?.addNote(text2.slice(0, 1000));
          }
        });
        e.preventDefault();
        return;
      }

      // 3. Plain text → text box.
      if (plainItem) {
        plainItem.getAsString((text) => {
          if (text.trim()) {
            setOverlayMode(true);
            canvasApiRef.current?.addNote(text.trim().slice(0, 1000));
          }
        });
        e.preventDefault();
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
    setAddSheetPending({ refId, where });
  };

  const addSheetFromModal = (title: string, code: string, template: string, refId: string, where: 'before' | 'after') => {
    mutatePages((pages) => {
      const idx = pages.findIndex((p) => p.id === refId);
      if (idx < 0) return pages;
      const blank: PageModel = {
        id: newPageId(),
        order: 0,
        include: true,
        sheetCode: code || 'NEW',
        displaySheetCode: code || 'NEW',
        sheetTitle: title || 'New Sheet',
        sheetTab: '',
        pageType: template as PageModel['pageType'] || 'data-grid',
        template: template,
        templateId: '',
        blocks: template === 'canvas' ? [] : [{ id: `b_${newPageId()}`, type: 'paragraph', text: '' }],
        canvasObjects: [],
        notes: '',
      };
      const out = [...pages];
      out.splice(where === 'before' ? idx : idx + 1, 0, blank);
      return out;
    });
    setRenumberBadge(true);
    setAddSheetPending(null);
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
      { label: 'Duplicate Sheet', divider: true, onClick: () => duplicatePage(id) },
      { label: 'Add Blank Sheet Before', onClick: () => addPage(id, 'before') },
      { label: 'Add Blank Sheet After', onClick: () => addPage(id, 'after') },
      { label: 'Import Worksheet from Excel', onClick: () => setImportWsOpen({ afterPageId: id }) },
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

  const openProjectById = async (id: string) => {
    try {
      const p = await getProject(id);
      setProject(p);
      setActivePageId(p.pages?.[0]?.id ?? null);
      setSelectedWorksheetId(p.worksheets?.[0]?.id);
      setSelection(null);
      window.history.replaceState({}, '', `?project=${id}`);
    } catch (err) {
      console.error('open project failed', err);
    } finally {
      setOpenProjectOpen(false);
    }
  };

  const onImportedWorksheets = async (pageIds: string[], renumberSuggested: boolean) => {
    setImportWsOpen(null);
    if (!project) return;
    try {
      const p = await getProject(project.id);
      setProject(p);
      // Select the first imported page.
      if (pageIds.length) setActivePageId(pageIds[0]);
      if (renumberSuggested) setRenumberBadge(true);
    } catch (err) {
      console.error('refresh after import failed', err);
    }
  };

  const onArchiveCurrentProject = async () => {
    if (!project) return;
    const name = project.projectDisplayName || (project.metadata as Record<string, string>)?.projectName || project.id;
    if (!window.confirm(`Archive project "${name}"?\n\nThis moves the project to .docs/_archive/ and returns you to the landing screen. Nothing is permanently deleted.`)) return;
    try {
      const res = await archiveProject(project.id);
      window.alert(`Project archived to:\n${res.archivedTo}`);
      setProject(null);
      setActivePageId(null);
      window.history.replaceState({}, '', '/app');
    } catch (err) {
      window.alert(`Archive failed: ${String(err)}`);
    }
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

  const onExportPdfSized = async (width: number, height: number, rev: { updateRevision: boolean; newRevision: string; notes: string }) => {
    if (!project) return;
    setExportOpen(false);
    let proj = project;
    // Optionally stamp a new revision into the title block + revision history.
    if (rev.updateRevision) {
      const today = new Date().toISOString().slice(0, 10);
      const history = [...(project.revisionHistory ?? []), {
        revision: rev.newRevision,
        date: today,
        description: rev.notes || 'Issued',
        exportedBy: 'Singh360',
      }];
      proj = {
        ...project,
        revisionHistory: history,
        metadata: { ...project.metadata, revision: rev.newRevision, issueDate: today },
      };
      setProject(proj);
      try { await saveProject(proj); } catch { /* best-effort */ }
    }
    const base = proj.metadata.drawingPackageFileName || proj.projectDisplayName || proj.metadata.projectName || proj.id;
    const revSuffix = rev.updateRevision ? `_${rev.newRevision.replace(/\s+/g, '')}` : '';
    const blob = await exportPdf(proj.id, { width, height });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${base}${revSuffix}.pdf`;
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
      onSetTool={(t) => { if (t !== 'select') setOverlayMode(true); setActiveTool(t); }}
      overlayMode={overlayMode}
      onToggleOverlay={() => setOverlayMode((v) => !v)}
      canvas={{
        addText: () => { setOverlayMode(true); canvasApiRef.current?.addText(); },
        addRect: () => { setOverlayMode(true); canvasApiRef.current?.addRect(); },
        addCircle: () => { setOverlayMode(true); canvasApiRef.current?.addCircle(); },
        addLine: () => { setOverlayMode(true); canvasApiRef.current?.addLine(); },
        addArrow: () => { setOverlayMode(true); canvasApiRef.current?.addArrow(); },
        addPolyline: () => { setOverlayMode(true); canvasApiRef.current?.addPolyline(); },
        addElbow: () => { setOverlayMode(true); canvasApiRef.current?.addElbow(); },
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
        alignObjects: (d) => canvasApiRef.current?.alignObjects(d),
        distributeObjects: (d) => canvasApiRef.current?.distributeObjects(d),
        matchObjectSize: (w) => canvasApiRef.current?.matchObjectSize(w),
        addLegend: (ids) => { setOverlayMode(true); canvasApiRef.current?.addLegend(ids); },
      }}
      onUploadFile={(f) => void onUploadWorkbook(f)}
      onUploadCsv={(f) => void onUploadCsv(f)}
      onInsertImage={(f) => void onDropImageFile(f)}
      onInsertPdfPage={() => setPdfInsertOpen(true)}
      onSaveNow={() => project && void saveProject(project)}
      onExportPdf={() => setExportOpen(true)}
      onExportPackage={() => void onExportPackage()}
      onRenumber={onRenumber}
      renumberBadge={renumberBadge}
      onOpenProject={() => setOpenProjectOpen(true)}
      onCleanWorkspace={() => setCleanWorkspaceOpen(true)}
      onImportWorksheet={() => setImportWsOpen({ afterPageId: activePageId ?? undefined })}
      onArchiveCurrentProject={() => void onArchiveCurrentProject()}
      theme={theme}
      onSetTheme={setThemeState}
      selection={selection}
      onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
      onSetLineStyle={(style) => setLineStyle(style)}
    />
  );

  // ── Empty state (no project loaded yet) ──
  if (!project || !activePage) {
    return (
      <>
      <ProjectShell
        ribbon={ribbon}
        left={<div className="nav-section-head">Output Pages</div>}
        center={
          <div className="empty-stage">
            <div className="empty-card">
              <h2>No workbook loaded</h2>
              <p>Choose a workbook (.xlsx) from the File tab to generate output pages and begin editing your drawing package, or <button className="link-btn" onClick={() => setOpenProjectOpen(true)}>open a saved project</button>.</p>
            </div>
          </div>
        }
        right={<div className="props-group"><h3>Project Properties</h3></div>}
      />
      {openProjectOpen && (
        <OpenProjectModal
          currentId={project?.id}
          onOpen={(id) => void openProjectById(id)}
          onCancel={() => setOpenProjectOpen(false)}
        />
      )}
      {cleanWorkspaceOpen && (
        <CleanWorkspaceModal onDone={() => setCleanWorkspaceOpen(false)} onCancel={() => setCleanWorkspaceOpen(false)} />
      )}
      {importWsOpen && project && (
        <ImportWorksheetModal
          projectId={project.id}
          insertAfterPageId={importWsOpen.afterPageId}
          onImported={(ids, rs) => void onImportedWorksheets(ids, rs)}
          onCancel={() => setImportWsOpen(null)}
        />
      )}
      {addSheetPending && (
        <AddSheetModal
          onAdd={(title, code, tmpl) => addSheetFromModal(title, code, tmpl, addSheetPending.refId, addSheetPending.where)}
          onCancel={() => setAddSheetPending(null)}
        />
      )}
      </>
    );
  }
  const includedCount = project.pages.filter((p) => p.include).length;

  return (
    <>
    <ProjectShell
      ribbon={ribbon}
      left={
        <>
          <CollapsibleSection title="Output Pages" hint="The pages that make up your drawing package. Drag to reorder; right-click for actions.">
            <SheetManager pages={project.pages} activePageId={activePageId} onSelect={setActivePageId} onUpdate={(p) => void updatePages(p)} onContextMenu={(id, x, y) => setPageMenu({ x, y, pageId: id })} />
          </CollapsibleSection>
          <CollapsibleSection title="Source Tabs" defaultOpen={false} hint="The original workbook worksheets, for reference.">
            <WorkbookView worksheets={project.worksheets} selectedWorksheetId={selectedWorksheetId} onSelectWorksheet={setSelectedWorksheetId} />
          </CollapsibleSection>
          <CollapsibleSection title="Component Library" defaultOpen={false} hint="Reusable EMS/RDM components. Search, then drag onto the active page.">
            <LibraryPanelV2 onInsert={onInsertComponent} onInsertBoth={onInsertComponentBoth} canInsert={canvasEnabled} />
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
              <label htmlFor="proj-name" title="User-facing project name shown in the title block">Project Name</label>
              <input
                id="proj-name"
                title="User-facing project name shown in the title block"
                value={project.metadata.projectName || ''}
                onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, projectName: e.target.value } })}
              />
            </div>
            <div className="field">
              <label htmlFor="proj-pkg" title="Output package / export filename, e.g. SA31_EMS_Lighting_V1">Drawing Package File Name</label>
              <input
                id="proj-pkg"
                title="Output package / export filename, e.g. SA31_EMS_Lighting_V1"
                placeholder="SA31_EMS_Lighting_V1"
                value={project.metadata.drawingPackageFileName || ''}
                onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, drawingPackageFileName: e.target.value } })}
              />
            </div>
            <div className="field">
              <label htmlFor="proj-loc" title="Project location / store address">Location</label>
              <input
                id="proj-loc"
                title="Project location / store address"
                value={project.metadata.location || ''}
                onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, location: e.target.value } })}
              />
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="proj-rev" title="Revision / version shown in the title block">Revision</label>
                <input
                  id="proj-rev"
                  title="Revision / version shown in the title block"
                  placeholder="V1"
                  value={project.metadata.revision || ''}
                  onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, revision: e.target.value } })}
                />
              </div>
              <div className="field">
                <label htmlFor="proj-issue" title="Date this package was issued">Issue Date</label>
                <input
                  id="proj-issue"
                  title="Date this package was issued"
                  value={project.metadata.issueDate || ''}
                  onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, issueDate: e.target.value } })}
                />
              </div>
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="proj-drawn" title="Person who drew the package">Drawn By</label>
                <input
                  id="proj-drawn"
                  title="Person who drew the package"
                  value={project.metadata.drawnBy || ''}
                  onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, drawnBy: e.target.value } })}
                />
              </div>
              <div className="field">
                <label htmlFor="proj-checked" title="Person who checked the package">Checked By</label>
                <input
                  id="proj-checked"
                  title="Person who checked the package"
                  value={project.metadata.checkedBy || ''}
                  onChange={(e) => setProject({ ...project, metadata: { ...project.metadata, checkedBy: e.target.value } })}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="proj-file" title="Original uploaded workbook filename (read-only)">Source Workbook</label>
              <input id="proj-file" title="Original uploaded workbook filename (read-only)" value={project.metadata.sourceFile || ''} readOnly />
            </div>
          </div>
          <PropertiesPanel
            page={activePage}
            onChange={(next) => patchPage(next.id, next)}
            selection={selection}
            onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
            onConnectorConvert={(kind) => canvasApiRef.current?.convertSelectedConnector(kind)}
            onConnectorAddVertex={() => canvasApiRef.current?.addVertexToSelected()}
            onConnectorDeleteVertex={() => canvasApiRef.current?.deleteVertexFromSelected()}
            onConnectorReverse={() => canvasApiRef.current?.reverseConnectorDirection()}
            projectDisplayName={project.projectDisplayName ?? project.metadata.projectName}
            projectFolder={project.projectFolder}
            onRenameProject={(name) => void onRenameProject(name)}
            overflowWarning={Array.isArray(activePage.layoutWarnings) && activePage.layoutWarnings.length > 0}
            onMergeIntoPrevious={activePage.continuationOf ? () => mergeContinuationIntoPrevious(activePage.id) : undefined}
            onMakeIndependent={activePage.continuationOf ? () => makeIndependent(activePage.id) : undefined}
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
    {openProjectOpen && (
      <OpenProjectModal
        currentId={project.id}
        onOpen={(id) => void openProjectById(id)}
        onCancel={() => setOpenProjectOpen(false)}
      />
    )}
    {cleanWorkspaceOpen && (
      <CleanWorkspaceModal onDone={() => setCleanWorkspaceOpen(false)} onCancel={() => setCleanWorkspaceOpen(false)} />
    )}
    {importWsOpen && (
      <ImportWorksheetModal
        projectId={project.id}
        insertAfterPageId={importWsOpen.afterPageId}
        onImported={(ids, rs) => void onImportedWorksheets(ids, rs)}
        onCancel={() => setImportWsOpen(null)}
      />
    )}
    {addSheetPending && (
      <AddSheetModal
        onAdd={(title, code, tmpl) => addSheetFromModal(title, code, tmpl, addSheetPending.refId, addSheetPending.where)}
        onCancel={() => setAddSheetPending(null)}
      />
    )}
    {exportOpen && (
      <ExportModal
        currentRevision={project.metadata.revision || project.metadata.version || ''}
        packageName={project.metadata.drawingPackageFileName || project.projectDisplayName || project.metadata.projectName || ''}
        onExport={(w, h, rev) => void onExportPdfSized(w, h, rev)}
        onCancel={() => setExportOpen(false)}
      />
    )}
    {pdfInsertOpen && (
      <PdfInsertModal
        projectId={project.id}
        onInsertImage={(url, name) => {
          setOverlayMode(true);
          canvasApiRef.current?.addImage(url, name);
          setPdfInsertOpen(false);
        }}
        onCancel={() => setPdfInsertOpen(false)}
      />
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
          { label: 'Insert Polyline', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addPolyline(); } },
          { label: 'Insert Elbow Connector', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addElbow(); } },
          { label: 'Insert Connector Legend', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addLegend(); } },
          { label: 'Import Worksheet from Excel', divider: true, onClick: () => setImportWsOpen({ afterPageId: activePageId ?? undefined }) },
          { label: 'Add Blank Sheet After', onClick: () => activePageId && addPage(activePageId, 'after') },
          { label: 'Duplicate Current Sheet', onClick: () => activePageId && duplicatePage(activePageId) },
          { label: 'Duplicate', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.duplicateSelected() },
          { label: 'Delete', disabled: !selection, onClick: () => canvasApiRef.current?.deleteSelected() },
          { label: 'Bring to Front', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.bringToFront() },
          { label: 'Send to Back', disabled: !selection, onClick: () => canvasApiRef.current?.sendToBack() },
          { label: 'Add Vertex', divider: true, disabled: !selection?.isConnector, onClick: () => canvasApiRef.current?.addVertexToSelected() },
          { label: 'Delete Vertex', disabled: !selection?.isConnector, onClick: () => canvasApiRef.current?.deleteVertexFromSelected() },
          { label: 'Convert to Elbow', disabled: !selection?.isConnector, onClick: () => canvasApiRef.current?.convertSelectedConnector('elbow') },
          { label: 'Convert to Free Polyline', disabled: !selection?.isConnector, onClick: () => canvasApiRef.current?.convertSelectedConnector('polyline') },
          { label: 'Convert to Straight Line', disabled: !selection?.isConnector, onClick: () => canvasApiRef.current?.convertSelectedConnector('line') },
          { label: 'Convert to Arrow', disabled: !selection?.isConnector, onClick: () => canvasApiRef.current?.convertSelectedConnector('arrow') },
          { label: 'Reverse Direction', disabled: !selection?.isConnector, onClick: () => canvasApiRef.current?.reverseConnectorDirection() },
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
