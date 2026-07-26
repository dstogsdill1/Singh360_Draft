import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  archiveProject,
  attachCsv,
  exportPackage,
  exportPdf,
  exportWorksheetXlsx,
  fetchExportWarnings,
  getProject,
  importWorksheets,
  previewImportWorksheets,
  renameProject,
  saveProject,
  resolveWorkbookLink,
  savePageRebuildBackup,
  uploadAssetDataUrl,
  uploadAssetFile,
  type ExportWarning,
} from './api/client';
import type { SymbolMapperRenderResult } from './api/client';
import type { BusOptions, CanvasApi, CanvasSelection, LineStyle, PageBlock, PageModel, ProjectModel, SymbolLegendInsertConfig, ViewMode, Worksheet, ImageCropPlacement, ImageCropRect, ImageCropState } from './model/types';
import { writeRecoverySnapshot } from './model/recovery';
import { normalizeProjectAssetUrls } from './model/assetUrl';
import ContinuationPreviewModal from './components/ContinuationPreviewModal';
import ReimportWorkbookModal from './components/ReimportWorkbookModal';
import { refreshBlockFromWorksheet, regenerateExcelGroup, refreshPageFromSource, applyCoverSourceTruth } from './model/excelRange';
import { isCoverWorksheet } from './model/metadataInference';
import { SourceWorksheetHistory } from './model/sourceWorksheetHistory';
import { PageRebuildHistory } from './model/pageRebuildHistory';
import { applyRebuiltPage, rebuildSinglePageFromSource } from './model/pageRebuild';
import { validatePageRebuild } from './model/pageRebuildValidation';
import { isSheetIndexPage, normalizePackagePages } from './model/packageIndex';
import RebuildValidationModal from './components/RebuildValidationModal';
import ProjectShell from './components/ProjectShell';
import SheetManager from './components/SheetManager';
import WorkbookView from './components/WorkbookView';
import LibraryPanelV2 from './components/LibraryPanelV2';
import DocumentView, { type FitMode, MAX_SCALE, MIN_SCALE } from './components/DocumentView';
import PropertiesPanel from './components/PropertiesPanel';
import PrintView from './components/PrintView';
import Ribbon, { type PageReviewFilter, type ViewControls } from './components/Ribbon';
import RenumberModal from './components/RenumberModal';
import OpenProjectModal from './components/OpenProjectModal';
import CleanWorkspaceModal from './components/CleanWorkspaceModal';
import ImportWorksheetModal from './components/ImportWorksheetModal';
import AddSheetModal from './components/AddSheetModal';
import SheetContextMenu from './components/SheetContextMenu';
import ExportModal from './components/ExportModal';
import ExportWarningsModal from './components/ExportWarningsModal';
import SavePageTemplateModal from './components/SavePageTemplateModal';
import PageTemplateLibraryModal, { type TemplateInsertMode } from './components/PageTemplateLibraryModal';
import SymbolLegendModal from './components/SymbolLegendModal';
import PdfCropModal from './components/PdfCropModal';
import ImageCropModal from './components/ImageCropModal';
import SymbolMapperModal from './components/SymbolMapperModal';
import { buildSymbolCountSummaryArtifacts, type SymbolMapperCountPageRequest } from './model/symbolCountSummary';
import BackupRecoveryModal from './components/BackupRecoveryModal';
import BusModal from './components/BusModal';
import CollapsibleSection from './components/CollapsibleSection';
import StatusBar from './components/StatusBar';
import HelpCenter from './components/HelpCenter';
import ProjectDashboard from './components/ProjectDashboard';

function getUrlParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    projectId: params.get('project'),
    print: params.get('print') === '1',
    help: params.get('help') === '1',
    mode: params.get('mode') === 'editor' ? 'editor' : 'home',
    tool: params.get('tool') || '',
    requestedPageId: params.get('page') || '',
  };
}

const clampScale = (v: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, v));

function screenshotName(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `Screenshot ${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}.png`;
}

// S360 WORKSPACE UX V10: preserve a real sheet code embedded in a worksheet name.
function suggestedSheetCode(name: string): string {
  const match = (name || '').trim().match(/^([A-Za-z]{2,8})\s*[-_ ]?\s*(\d{1,3}(?:\.\d{1,3})[A-Za-z]?)/);
  return match ? `${match[1].toUpperCase()} ${match[2]}` : 'NEW';
}

// Canonical package order + live Page X of Y. This also keeps the generated
// Sheet Index second, moves excluded/internal pages after package pages, and
// counts every included physical continuation page.
function withPageNumbers(pages: PageModel[]): PageModel[] {
  return normalizePackagePages(pages);
}

export default function App() {
  const { projectId: initialProjectId, print: printMode, help: helpMode, mode: appMode, tool: initialTool, requestedPageId } = getUrlParams();

  const [project, setProject] = useState<ProjectModel | null>(null);
  const [activePageId, setActivePageId] = useState<string | null>(null);
  const [selectedWorksheetId, setSelectedWorksheetId] = useState<string | undefined>(undefined);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'unsaved' | 'saving' | 'saved' | 'failed'>('idle');
  const [savedAt, setSavedAt] = useState<string>('');
  const [saveNotice, setSaveNotice] = useState<string>('');
  // S360 SAVE + WRITE EXCEL BUTTON V26
  const [excelWriteBusy, setExcelWriteBusy] = useState(false);

  // Viewport view-state.
  const [fitMode, setFitMode] = useState<FitMode>('page');
  const [actualZoom, setActualZoom] = useState(1);
  const [effectiveScale, setEffectiveScale] = useState(0.5);
  const [showGrid, setShowGrid] = useState(false);
  const [snap, setSnap] = useState(true);
  // S360 RAPID PAGE REVIEW V35
  const [pageFilter, setPageFilter] = useState<PageReviewFilter>(() => {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem('singh360-page-filter') : null;
    return saved === 'included' || saved === 'excluded' ? saved : 'all';
  });
  const [rapidReviewBusy, setRapidReviewBusy] = useState(false);
  useEffect(() => {
    try { localStorage.setItem('singh360-page-filter', pageFilter); } catch { /* ignore */ }
  }, [pageFilter]);

  // Rendering + editing state.
  const [viewMode, setViewMode] = useState<ViewMode>('normalized');
  const [sourceDirty, setSourceDirty] = useState(false);
  const [sourceEditStatus, setSourceEditStatus] = useState<'idle' | 'edited' | 'updated'>('idle');
  const [sourceHistoryTick, setSourceHistoryTick] = useState(0);
  const sourceHistoryRef = useRef(new SourceWorksheetHistory());
  const pageRebuildHistoryRef = useRef(new PageRebuildHistory());
  const [pageRebuildTick, setPageRebuildTick] = useState(0);
  const [rebuildValidationModal, setRebuildValidationModal] = useState<{
    pageId: string;
    rebuilt: PageModel;
    issues: string[];
  } | null>(null);
  const [activeTool, setActiveTool] = useState('select');
  const [overlayMode, setOverlayMode] = useState(false);
  const [lineStyle, setLineStyle] = useState<LineStyle>({
    stroke: '#111111', dash: 'solid', strokeWidth: 2, arrowStart: false, arrowEnd: false,
  });
  const [selection, setSelection] = useState<CanvasSelection | null>(null);
  const [renumberOpen, setRenumberOpen] = useState(initialTool === 'renumber');
  const [openProjectOpen, setOpenProjectOpen] = useState(false);
  const [cleanWorkspaceOpen, setCleanWorkspaceOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(initialTool === 'export');
  const [exportWarnings, setExportWarnings] = useState<ExportWarning[] | null>(null);
  const pendingExportRef = useRef<{ width: number; height: number; downloadName: string; pageIds: string[] } | null>(null);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [templateLibOpen, setTemplateLibOpen] = useState(false);
  const [templateLibManageOnly, setTemplateLibManageOnly] = useState(false);
  const [symbolLegendOpen, setSymbolLegendOpen] = useState(initialTool === 'symbol-legend');
  const [pdfCropOpen, setPdfCropOpen] = useState(false);
  const [imageCropState, setImageCropState] = useState<ImageCropState | null>(null);
  const [symbolMapperOpen, setSymbolMapperOpen] = useState(initialTool === 'symbol-mapper');
  const [backupOpen, setBackupOpen] = useState(initialTool === 'backups');
  const [busOpen, setBusOpen] = useState(false);
  const [addSheetPending, setAddSheetPending] = useState<{ refId: string; where: 'before' | 'after' } | null>(null);
  const [importWsOpen, setImportWsOpen] = useState<{
    afterPageId?: string;
    replacePageId?: string;
    replacePageTitle?: string;
  } | null>(null);
  const [pendingWorkbookFile, setPendingWorkbookFile] = useState<File | null>(null);
  const [pendingReimportFile, setPendingReimportFile] = useState<File | null>(null);
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
  const pendingSymbolPageRef = useRef<{ pageId: string; url: string; name: string; resolve: () => void; reject: (reason: unknown) => void } | null>(null);

  // ── Save manager: single source of truth for persistence + status ──
  // lastSavedJson is the JSON we last confirmed on the server. A project whose
  // JSON differs from it is genuinely dirty; equality means "hydrated, clean".
  const lastSavedJsonRef = useRef<string>('');
  const projectRef = useRef<ProjectModel | null>(project);
  const saveStatusRef = useRef(saveStatus);
  saveStatusRef.current = saveStatus;
  const savingRef = useRef(false);

  const setProjectSync = useCallback((updater: ProjectModel | null | ((prev: ProjectModel | null) => ProjectModel | null)) => {
    const rawNext = typeof updater === 'function'
      ? (updater as (prev: ProjectModel | null) => ProjectModel | null)(projectRef.current)
      : updater;
    const next = rawNext
      ? { ...rawNext, pages: normalizePackagePages(rawNext.pages ?? []) }
      : rawNext;
    projectRef.current = next;
    setProject(next);
    return next;
  }, []);

  const markSaved = (saved?: ProjectModel) => {
    const d = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    setSavedAt(`${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`);
    const sync = (saved?.workbookSync || {}) as Record<string, unknown>;
    const pending = sync.status === 'pending' || sync.status === 'conflict' || Boolean(sync.warning);
    setSaveNotice(pending ? 'Project Saved · Workbook Sync Pending' : '');
    setSaveStatus('saved');
  };

  // Persist the freshest project to the server. Returns true only when the
  // server actually confirmed the write of the CURRENT project snapshot.
  const flushSave = useCallback(async (): Promise<boolean> => {
    const p = projectRef.current;
    if (!p || printMode) return true;
    const json = JSON.stringify(p);
    if (json === lastSavedJsonRef.current) return true; // nothing new to save
    if (savingRef.current) return false; // a save is already in flight
    savingRef.current = true;
    setSaveStatus('saving');
    try {
      const savedFromServer = normalizeProjectAssetUrls(await saveProject(p));
      savingRef.current = false;
      if (JSON.stringify(projectRef.current) !== json) {
        // A newer local edit exists. Do not overwrite it with this older response;
        // the next autosave will synchronize the latest Sheet Index.
        setSaveStatus('unsaved');
        return false;
      }
      const applied = setProjectSync(savedFromServer);
      lastSavedJsonRef.current = JSON.stringify(applied ?? savedFromServer);
      markSaved(savedFromServer);
      return true;
    } catch {
      savingRef.current = false;
      setSaveStatus('failed');
      writeRecoverySnapshot(p);
      return false;
    }
  }, [printMode]);


  // Wait through any in-flight autosave and keep retrying until the exact latest
  // project snapshot is confirmed by the server. This prevents a successfully
  // created Symbol Mapper page from being reported as a false save failure while
  // its reviewed image is still mounting on the Fabric canvas.
  const confirmLatestProjectSaved = useCallback(async (timeoutMs = 10000): Promise<boolean> => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const current = projectRef.current;
      if (!current) return false;
      if (JSON.stringify(current) === lastSavedJsonRef.current) return true;
      if (!savingRef.current) {
        const ok = await flushSave();
        if (ok) return true;
      }
      await new Promise<void>((resolve) => window.setTimeout(resolve, 150));
    }
    const current = projectRef.current;
    return !!current && JSON.stringify(current) === lastSavedJsonRef.current;
  }, [flushSave]);

  // ── captureActivePageState ─────────────────────────────────────────────────
  // THE CRITICAL FIX: synchronously read the live Fabric canvas and write the
  // result into projectRef BEFORE any save or page-switch so flushSave always
  // gets the freshest editor state — not a stale React snapshot.
  //
  // React's setProject is async (batched). When the user draws something and
  // immediately clicks Save Now or another page tab, the onSerializedChange →
  // setProject update hasn't been committed yet. captureActivePageState bypasses
  // that by going straight to live editors and projectRef.
  const captureActivePageState = useCallback(() => {
    try {
      document.dispatchEvent(new CustomEvent('singh360:capture-active-editors'));
      const el = document.activeElement as HTMLElement | null;
      if (el?.isContentEditable) el.blur();
    } catch {
      /* capture is best effort for DOM editors; projectRef remains authoritative */
    }
    const canvas = canvasApiRef.current;
    const pageId = activePageRef.current?.id;
    if (!pageId || !projectRef.current) return projectRef.current;
    const objects = canvas?.captureCanvas();
    const updated: ProjectModel = {
      ...projectRef.current,
      pages: projectRef.current.pages.map((p) =>
        p.id === pageId && objects ? { ...p, canvasObjects: objects } : p,
      ),
    };
    // Synchronously update the mutable ref so flushSave reads the right data.
    projectRef.current = updated;
    // Also schedule the React state update so the UI stays consistent.
    setProject(updated);
    writeRecoverySnapshot(updated);
    return updated;
  }, []);

  // Capture then save. Every explicit save (Save Now, Ctrl+S) and every
  // page/project switch must call this before doing anything else.
  const captureAndSave = useCallback(async (): Promise<boolean> => {
    captureActivePageState();
    return flushSave();
  }, [captureActivePageState, flushSave]);

  // Hard gate for navigation: do not switch pages/projects unless the current
  // active canvas has been captured AND the server confirms persistence.
  const ensureSavedBeforeNavigation = useCallback(async (): Promise<boolean> => {
    const ok = await captureAndSave();
    if (!ok) {
      window.alert('Save failed. Staying on the current page so your drawing is not lost.');
      return false;
    }
    return true;
  }, [captureAndSave]);

  const switchPageSafely = useCallback(async (id: string) => {
    if (id === activePageRef.current?.id) return;
    const ok = await ensureSavedBeforeNavigation();
    if (!ok) return;
    const target = projectRef.current?.pages.find((page) => page.id === id);
    setActivePageId(id);
    if (target?.linkedWorksheetId) setSelectedWorksheetId(target.linkedWorksheetId);
    setSelection(null);
  }, [ensureSavedBeforeNavigation]);

  // Explicit "Save Now": capture the live canvas, then contact the server.
  const saveNow = useCallback(async (): Promise<boolean> => {
    captureActivePageState(); // sync active-page capture MUST happen before any read of projectRef
    let p = projectRef.current;
    if (p) {
      const wsId = activePageRef.current?.linkedWorksheetId;
      if (wsId && isCoverWorksheet(p, wsId)) {
        p = applyCoverSourceTruth(p, wsId);
        projectRef.current = p;
        setProjectSync(p);
        setSourceEditStatus('updated');
        setSourceDirty(false);
      }
    }
    if (!p || printMode) return true;
    const json = JSON.stringify(p);
    savingRef.current = true;
    setSaveStatus('saving');
    try {
      const savedFromServer = normalizeProjectAssetUrls(await saveProject(p));
      savingRef.current = false;
      if (JSON.stringify(projectRef.current) !== json) {
        setSaveStatus('unsaved');
        return false;
      }
      const applied = setProjectSync(savedFromServer);
      lastSavedJsonRef.current = JSON.stringify(applied ?? savedFromServer);
      markSaved(savedFromServer);
      return true;
    } catch {
      savingRef.current = false;
      setSaveStatus('failed');
      writeRecoverySnapshot(p);
      return false;
    }
  }, [printMode, captureActivePageState, setProjectSync]);

  // S360 SAVE + WRITE EXCEL BUTTON V26
  const writeProjectToExcel = useCallback(async (): Promise<boolean> => {
    if (excelWriteBusy || printMode) return false;
    captureActivePageState();
    const current = projectRef.current;
    if (!current) {
      window.alert('Open a project before writing to Excel.');
      return false;
    }
    setExcelWriteBusy(true);
    setSaveStatus('saving');
    setSaveNotice('Saving project locally…');
    try {
      const localSaved = await saveNow();
      if (!localSaved) throw new Error('The local project save did not complete.');
      const latest = projectRef.current;
      if (!latest) throw new Error('The active project disappeared before Excel synchronization.');
      setSaveStatus('saving');
      setSaveNotice('Writing project to Excel…');
      const result = await resolveWorkbookLink(latest.id, 'app_to_workbook');
      const synced = normalizeProjectAssetUrls(result.project);
      const applied = setProjectSync(synced);
      lastSavedJsonRef.current = JSON.stringify(applied ?? synced);
      markSaved(synced);
      setSaveStatus('saved');
      setSaveNotice('PROJECT + EXCEL SAVED');
      window.setTimeout(() => {
        setSaveNotice((notice) => notice === 'PROJECT + EXCEL SAVED' ? '' : notice);
      }, 6000);
      return true;
    } catch (error) {
      console.error('Save + Write Excel failed', error);
      setSaveStatus('failed');
      setSaveNotice('EXCEL WRITE FAILED · LOCAL PROJECT IS STILL SAVED');
      writeRecoverySnapshot(projectRef.current ?? current);
      window.alert(
        `Could not write the project to Excel.\n\n${String(error)}\n\n`
        + 'Your local Singh360 project remains saved. Close Excel and try again.',
      );
      return false;
    } finally {
      setExcelWriteBusy(false);
    }
  }, [excelWriteBusy, printMode, captureActivePageState, saveNow, setProjectSync]);

  const resetSourceEditState = useCallback(() => {
    sourceHistoryRef.current.clear();
    setSourceHistoryTick((n) => n + 1);
    setSourceEditStatus('idle');
    setSourceDirty(false);
  }, []);

  useEffect(() => {
    if (!initialProjectId) return;
    void getProject(initialProjectId).then((p) => {
      const normalized = normalizeProjectAssetUrls(p);
      lastSavedJsonRef.current = JSON.stringify(normalized);
      resetSourceEditState();
      setProjectSync(normalized);
      // S360 PAGE MANAGER DEEP LINK V1
      let savedPageId = '';
      try {
        savedPageId = localStorage.getItem(`singh360-open-page:${initialProjectId}`) || '';
        localStorage.removeItem(`singh360-open-page:${initialProjectId}`);
      } catch {
        savedPageId = '';
      }
      const targetPageId = requestedPageId || savedPageId;
      const firstPage = normalized.pages?.find((page) => page.id === targetPageId) ?? normalized.pages?.[0];
      setActivePageId(firstPage?.id ?? null);
      setSelectedWorksheetId(firstPage?.linkedWorksheetId ?? normalized.worksheets?.[0]?.id);
    });
  }, [initialProjectId, setProjectSync, resetSourceEditState]);

  // Debounced autosave driven by real changes. Marks Unsaved Changes immediately,
  // writes a local recovery snapshot, then persists after a short quiet period.
  useEffect(() => {
    if (!project || printMode) return;
    projectRef.current = project;
    const json = JSON.stringify(project);
    if (json === lastSavedJsonRef.current) return; // hydrated / no real change
    setSaveStatus('unsaved');
    writeRecoverySnapshot(project);
    const t = setTimeout(() => { void flushSave(); }, 800);
    return () => clearTimeout(t);
  }, [project, printMode, flushSave]);

  // Warn before leaving with unsaved/in-flight changes.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (saveStatusRef.current === 'unsaved' || saveStatusRef.current === 'saving') {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  const activePage = useMemo(() => {
    if (!project || !activePageId) return null;
    return project.pages.find((p) => p.id === activePageId) ?? null;
  }, [project, activePageId]);

  // S360 RAPID PAGE REVIEW V35
  const reviewPages = useMemo(() => {
    const ordered = [...(project?.pages ?? [])].sort((a, b) => a.order - b.order);
    if (pageFilter === 'included') return ordered.filter((page) => page.include);
    if (pageFilter === 'excluded') return ordered.filter((page) => !page.include);
    return ordered;
  }, [project?.pages, pageFilter]);

  const navigateReviewPage = useCallback(async (direction: -1 | 1) => {
    if (!reviewPages.length) return;
    const currentIndex = reviewPages.findIndex((page) => page.id === activePageRef.current?.id);
    const targetIndex = currentIndex < 0
      ? (direction > 0 ? 0 : reviewPages.length - 1)
      : currentIndex + direction;
    if (targetIndex < 0 || targetIndex >= reviewPages.length) return;
    await switchPageSafely(reviewPages[targetIndex].id);
  }, [reviewPages, switchPageSafely]);

  // S360 CRITICAL SYNC V44 — the active page and every page navigator obey
  // the same All / Included / Not Included filter.
  const setPageFilterSafely = useCallback((filter: PageReviewFilter) => {
    setPageFilter(filter);
    const current = projectRef.current;
    if (!current) return;
    const visible = [...current.pages]
      .sort((a, b) => a.order - b.order)
      .filter((page) => (
        filter === 'all'
        || (filter === 'included' ? page.include : !page.include)
      ));
    const activeId = activePageRef.current?.id;
    if (visible.length && !visible.some((page) => page.id === activeId)) {
      void switchPageSafely(visible[0].id);
    }
  }, [switchPageSafely]);

  // Auto-enable overlay edit mode only for pages whose *base* is not itself
  // editable (pure image/canvas/underlay sheets, or pages that already carry
  // annotations but have no editable table/text underneath). Pages with an
  // editable table/matrix/text base (including hybrid schedule sheets) default
  // to overlay OFF so the table cells are immediately clickable and editable.
  useEffect(() => {
    const p = activePage;
    if (!p) return;
    const hasObjects = (p.canvasObjects?.length ?? 0) > 0;
    const baseTypes = ['table', 'matrix', 'title', 'subtitle', 'paragraph', 'bulletList', 'sectionHeading', 'note', 'cover'];
    const hasEditableBase = p.pageType === 'index' || (p.blocks ?? []).some((b) => baseTypes.includes(b.type));
    const pureDrawingPage = p.pageType === 'canvas' || p.pageType === 'underlay';
    // Keep the editable base clickable by default; only auto-open overlay when
    // there is nothing editable underneath to protect.
    setOverlayMode(!hasEditableBase && (hasObjects || pureDrawingPage));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePageId]);

  const onScaleChange = useCallback((s: number) => setEffectiveScale(s), []);
  const lineStyleRef = useRef(lineStyle);
  lineStyleRef.current = lineStyle;
  const onRegisterApi = useCallback((api: CanvasApi | null) => {
    canvasApiRef.current = api;
    if (!api) return;
    api.setLineStyle(lineStyleRef.current);
    const pending = pendingSymbolPageRef.current;
    if (pending && pending.pageId === activePageId) {
      pendingSymbolPageRef.current = null;
      Promise.resolve(api.addPdfCrop(pending.url, pending.name, { underlay: true, opacity: 1 }))
        .then(() => {
          window.requestAnimationFrame(() => {
            captureActivePageState();
            pending.resolve();
          });
        })
        .catch((err) => {
          console.error('Symbol Mapper page image insertion failed', err);
          pending.reject(err);
        });
    }
  }, [activePageId, captureActivePageState]);
  const onSelectionChange = useCallback((sel: CanvasSelection | null) => setSelection(sel), []);
  const onToolConsumed = useCallback(() => setActiveTool('select'), []);

  // Push the current new-line style down to the canvas whenever it changes.
  useEffect(() => {
    canvasApiRef.current?.setLineStyle(lineStyle);
  }, [lineStyle]);

  // Refs so global paste/keyboard handlers read current values.
  const activePageRef = useRef(activePage);
  const viewModeRef = useRef(viewMode);
  const selectionRef = useRef(selection);
  const selectedWorksheetIdRef = useRef(selectedWorksheetId);
  activePageRef.current = activePage;
  viewModeRef.current = viewMode;
  selectionRef.current = selection;
  selectedWorksheetIdRef.current = selectedWorksheetId;

  const activeWorksheetId = (viewMode === 'source' ? selectedWorksheetId : activePage?.linkedWorksheetId) ?? null;
  void sourceHistoryTick;
  void pageRebuildTick;
  const sourceCanUndo = sourceHistoryRef.current.canUndo(activeWorksheetId);
  const sourceCanRedo = sourceHistoryRef.current.canRedo(activeWorksheetId);
  const canRestorePageRebuild = pageRebuildHistoryRef.current.canRestore(activePage?.id);
  const sourceUndoRef = useRef<() => boolean>(() => false);
  const sourceRedoRef = useRef<() => boolean>(() => false);
  const pageRebuildUndoRef = useRef<() => boolean>(() => false);

  /** Rebuild linked normalized pages for a worksheet from its source grid. */
  const refreshPagesFromWorksheet = useCallback((
    wsId: string,
    pageId?: string | null,
    opts?: { full?: boolean },
  ) => {
    setProjectSync((prev) => {
      if (!prev) return prev;
      const ws = prev.worksheets.find((w) => w.id === wsId);
      if (!ws) return prev;
      const linked = prev.pages.filter((p) => p.linkedWorksheetId === wsId);
      const isExact = linked.some((p) => p.renderMode === 'excel_exact');
      let next = prev;
      if (isExact && opts?.full) {
        next = { ...prev, pages: regenerateExcelGroup({ ...prev, worksheets: prev.worksheets }, wsId) };
      } else if (isExact) {
        let pages = linked.map((pg) => {
          const b = (pg.blocks ?? [])[0];
          if (!b || b.type !== 'excelRange') return pg;
          return { ...pg, blocks: [refreshBlockFromWorksheet(b, ws)] };
        });
        const byId = new Map(pages.map((p) => [p.id, p]));
        pages = prev.pages.map((p) => (p.linkedWorksheetId === wsId ? (byId.get(p.id) ?? p) : p));
        next = { ...prev, pages };
      } else if (isCoverWorksheet(prev, wsId)) {
        next = applyCoverSourceTruth(prev, wsId);
      } else {
        const pages = prev.pages.map((pg) =>
          pg.linkedWorksheetId === wsId ? refreshPageFromSource(pg, ws) : pg,
        );
        next = { ...prev, pages };
      }
      // Bump sourceRevision on the active page so Normalized remounts.
      if (pageId) {
        next = {
          ...next,
          pages: next.pages.map((p) =>
            p.id === pageId ? { ...p, sourceRevision: (p.sourceRevision ?? 0) + 1 } : p,
          ),
        };
      }
      return next;
    });
  }, [setProjectSync]);

  /** Apply a validated rebuilt page to the project. */
  const applyPageRebuild = useCallback((pageId: string, rebuilt: PageModel) => {
    setProjectSync((prev) => (prev ? applyRebuiltPage(prev, pageId, rebuilt) : prev));
    setSourceDirty(false);
    setSourceEditStatus('updated');
  }, [setProjectSync]);

  const pageRebuildUndo = useCallback(() => {
    const pageId = activePageRef.current?.id;
    const p = projectRef.current;
    if (!pageId || !p) return false;
    const next = pageRebuildHistoryRef.current.undo(p, pageId);
    if (!next) return false;
    setProjectSync(next);
    setPageRebuildTick((n) => n + 1);
    setSourceEditStatus('updated');
    writeRecoverySnapshot(next);
    return true;
  }, [setProjectSync]);

  const restoreLastPageRebuild = useCallback(() => {
    pageRebuildUndo();
  }, [pageRebuildUndo]);

  const replaceCurrentPageSource = useCallback(() => {
    setImportWsOpen({
      afterPageId: activePageRef.current?.id ?? undefined,
      replacePageId: activePageRef.current?.id ?? undefined,
      replacePageTitle: activePageRef.current?.sheetTitle,
    });
  }, []);

  const exportCurrentSourceSheet = useCallback(async () => {
    const p = projectRef.current;
    const page = activePageRef.current;
    const worksheetId = viewModeRef.current === 'source' ? selectedWorksheetIdRef.current : page?.linkedWorksheetId;
    if (!p || !worksheetId) return;
    try {
      const blob = await exportWorksheetXlsx(p.id, { worksheetId });
      const ws = p.worksheets.find((w) => w.id === worksheetId);
      const base = (ws?.name || ws?.sourceSheet || page?.sheetTitle || 'source').replace(/[^\w.\- ]+/g, '_').trim() || 'source';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${base}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      window.alert(`Export failed: ${err}`);
    }
  }, []);

  /** Rebuild the active page's normalized blocks from its linked worksheet. */
  const rebuildCurrentPageFromSource = useCallback(async () => {
    document.dispatchEvent(new CustomEvent('singh360:capture-active-editors'));
    const el = document.activeElement as HTMLElement | null;
    el?.blur?.();
    const page = activePageRef.current;
    const p = projectRef.current;
    const pageId = page?.id;
    const wsId = page?.linkedWorksheetId;
    if (!pageId || !wsId || !page || !p) return;
    const ws = p.worksheets.find((w) => w.id === wsId);
    if (!ws) return;

    let serverSnapshotName: string | undefined;
    try {
      const backup = await savePageRebuildBackup(p.id, pageId, page);
      serverSnapshotName = backup.name;
    } catch {
      /* server backup is best-effort */
    }
    pageRebuildHistoryRef.current.pushBeforeRebuild(page, serverSnapshotName);
    setPageRebuildTick((n) => n + 1);

    const rebuilt = rebuildSinglePageFromSource(page, ws);
    const validation = validatePageRebuild(page, rebuilt);
    if (!validation.ok) {
      setRebuildValidationModal({ pageId, rebuilt, issues: validation.issues });
      return;
    }
    applyPageRebuild(pageId, rebuilt);
  }, [applyPageRebuild]);

  const applyWorksheetPatch = useCallback((
    wsId: string,
    patch: Partial<Worksheet>,
    opts?: { structural?: boolean; skipHistory?: boolean },
  ) => {
    if (!opts?.skipHistory && projectRef.current) {
      sourceHistoryRef.current.pushBeforeEdit(projectRef.current, wsId);
      setSourceHistoryTick((n) => n + 1);
    }
    if (
      activePageRef.current?.linkedWorksheetId === wsId
      && viewModeRef.current === 'source'
    ) {
      setSourceDirty(true);
      setSourceEditStatus('edited');
    }
    setProjectSync((prev) => {
      if (!prev) return prev;
      const worksheets = prev.worksheets.map((ws) =>
        ws.id === wsId ? { ...ws, ...patch } : ws,
      );
      const base = { ...prev, worksheets };
      if (!opts?.structural) {
        return base;
      }

      const linked = base.pages.filter((page) => page.linkedWorksheetId === wsId);
      if (linked.some((page) => page.renderMode === 'excel_exact')) {
        return { ...base, pages: regenerateExcelGroup(base, wsId) };
      }
      if (isCoverWorksheet(base, wsId)) {
        return applyCoverSourceTruth(base, wsId);
      }
      const updatedWorksheet = base.worksheets.find((ws) => ws.id === wsId);
      if (!updatedWorksheet) return base;
      return {
        ...base,
        pages: base.pages.map((page) =>
          page.linkedWorksheetId === wsId ? refreshPageFromSource(page, updatedWorksheet) : page,
        ),
      };
    });
  }, [setProjectSync]);

  const sourceUndo = useCallback(() => {
    document.dispatchEvent(new CustomEvent('singh360:discard-active-editors'));
    const wsId = (viewModeRef.current === 'source' ? selectedWorksheetIdRef.current : activePageRef.current?.linkedWorksheetId);
    const p = projectRef.current;
    if (!wsId || !p) return false;
    const next = sourceHistoryRef.current.undo(p, wsId);
    if (!next) return false;
    projectRef.current = next;
    setProjectSync(next);
    setSourceHistoryTick((n) => n + 1);
    setSourceDirty(true);
    setSourceEditStatus('edited');
    writeRecoverySnapshot(next);
    return true;
  }, [setProjectSync]);

  const sourceRedo = useCallback(() => {
    document.dispatchEvent(new CustomEvent('singh360:discard-active-editors'));
    const wsId = (viewModeRef.current === 'source' ? selectedWorksheetIdRef.current : activePageRef.current?.linkedWorksheetId);
    const p = projectRef.current;
    if (!wsId || !p) return false;
    const next = sourceHistoryRef.current.redo(p, wsId);
    if (!next) return false;
    projectRef.current = next;
    setProjectSync(next);
    setSourceHistoryTick((n) => n + 1);
    setSourceDirty(true);
    setSourceEditStatus('edited');
    writeRecoverySnapshot(next);
    return true;
  }, [setProjectSync]);

  sourceUndoRef.current = sourceUndo;
  sourceRedoRef.current = sourceRedo;
  pageRebuildUndoRef.current = pageRebuildUndo;

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    if (mode === 'source' && activePageRef.current?.linkedWorksheetId) {
      setSelectedWorksheetId(activePageRef.current.linkedWorksheetId);
    }
    if (
      viewModeRef.current === 'source'
      && mode === 'normalized'
      && selectedWorksheetIdRef.current === activePageRef.current?.linkedWorksheetId
    ) {
      rebuildCurrentPageFromSource();
    }
    setViewMode(mode);
  }, [rebuildCurrentPageFromSource]);

  // Keep the mutable project ref in sync with committed React state only.
  // Do NOT assign this during render: a page-switch render can otherwise
  // overwrite a freshly captured project snapshot with a stale one before the
  // save completes.
  useEffect(() => {
    projectRef.current = project;
  }, [project]);

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
  const onInsertComponent = (
    name: string,
    url: string,
    label: string | null,
    meta?: { category?: string; defaultWidth?: number; defaultHeight?: number; acronym?: string },
  ) => {
    if (!isCanvasContext()) return;
    setOverlayMode(true);
    canvasApiRef.current?.addComponent(url, name, label, undefined, meta);
  };

  const onDropComponent = (
    url: string,
    name: string,
    label: string | null,
    clientX: number,
    clientY: number,
    meta?: { category?: string; defaultWidth?: number; defaultHeight?: number },
  ) => {
    if (!isCanvasContext()) return;
    setOverlayMode(true);
    canvasApiRef.current?.addComponent(url, name, label, { clientX, clientY }, meta);
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

  // Global keyboard: source undo/redo, canvas delete/undo, quick tools.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (viewModeRef.current === 'source' && (e.ctrlKey || e.metaKey) && (k === 'z' || k === 'y')) {
        e.preventDefault();
        if (k === 'z') sourceUndoRef.current();
        else sourceRedoRef.current();
        return;
      }
      if (
        viewModeRef.current === 'normalized'
        && (e.ctrlKey || e.metaKey)
        && k === 'z'
        && pageRebuildHistoryRef.current.canUndo(activePageRef.current?.id)
      ) {
        e.preventDefault();
        pageRebuildUndoRef.current();
        return;
      }
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      if (!isCanvasContext()) return;
      if (e.key === 'Delete') {
        canvasApiRef.current?.deleteSelected();
      } else if ((e.ctrlKey || e.metaKey) && k === 'z') {
        e.preventDefault();
        canvasApiRef.current?.undo();
      } else if ((e.ctrlKey || e.metaKey) && k === 'y') {
        e.preventDefault();
        canvasApiRef.current?.redo();
      } else if ((e.ctrlKey || e.metaKey) && k === 'c') {
        if (selectionRef.current) {
          e.preventDefault();
          canvasApiRef.current?.copySelected();
        }
      } else if ((e.ctrlKey || e.metaKey) && k === 'v') {
        if (selectionRef.current) {
          e.preventDefault();
          canvasApiRef.current?.pasteCopied();
        }
      } else if ((e.ctrlKey || e.metaKey) && k === 'd') {
        e.preventDefault();
        canvasApiRef.current?.duplicateSelected();
      } else if ((e.ctrlKey || e.metaKey) && k === 's') {
        e.preventDefault();
        void saveNow();
      } else if (!e.ctrlKey && !e.metaKey && !e.altKey) {
        // Quick-draw tool shortcuts (Visio-style): L line, P polyline, E elbow,
        // B bus/harness. Ignored while typing (guarded above).
        if (k === 'l') { setOverlayMode(true); setActiveTool('line'); }
        else if (k === 'p') { setOverlayMode(true); setActiveTool('polyline'); }
        else if (k === 'e') { setOverlayMode(true); setActiveTool('elbow'); }
        else if (k === 'b') { setBusOpen(true); }
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
      // Tables/matrices/generated sheet index provide their own editing surface.
      if (t.closest('.np-table, .np-matrix, .np-index-table')) return;
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
    captureActivePageState();
    const cur = projectRef.current;
    if (!cur) return;
    const numbered = withPageNumbers(pages);
    const next: ProjectModel = { ...cur, pages: numbered };
    setProjectSync(next);
    await flushSave();
  };

  // S360 CRITICAL SYNC V44 — when a filter is active, edits/reorder operations
  // update only the visible slots and merge them back into the complete project.
  // Hidden pages are never discarded.
  const updateFilteredPages = async (visiblePages: PageModel[]) => {
    if (pageFilter === 'all') {
      await updatePages(visiblePages);
      return;
    }
    captureActivePageState();
    const cur = projectRef.current;
    if (!cur) return;
    const visibleIds = new Set(reviewPages.map((page) => page.id));
    if (visiblePages.length !== visibleIds.size) {
      throw new Error('Filtered page update did not contain the complete visible set.');
    }
    const queue = [...visiblePages];
    const merged = cur.pages.map((page) => (
      visibleIds.has(page.id) ? (queue.shift() ?? page) : page
    ));
    const numbered = withPageNumbers(
      merged.map((page, index) => ({ ...page, order: index + 1 })),
    );
    const next: ProjectModel = { ...cur, pages: numbered };
    setProjectSync(next);
    await flushSave();
  };

  // Single source of truth for per-page edits. Every edit surface (tab, left
  // list, page heading, right panel) funnels through here so all views stay in
  // sync, page numbering stays correct, and the change autosaves.
  const patchPage = (pageId: string, patch: Partial<PageModel>) => {
    setProjectSync((prev) => {
      if (!prev) return prev;
      const pages = withPageNumbers(prev.pages.map((p) => (p.id === pageId ? { ...p, ...patch } : p)));
      return { ...prev, pages };
    });
  };

  const onRenamePageTitle = (pageId: string, title: string) => patchPage(pageId, { sheetTitle: title });

  // ── Structural page operations (used by tab + left-list context menus) ──
  const newPageId = () => `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

  const mutatePages = (fn: (pages: PageModel[]) => PageModel[]) => {
    captureActivePageState();
    const cur = projectRef.current;
    if (!cur) return;
    const next = withPageNumbers(fn(cur.pages).map((p, i) => ({ ...p, order: i + 1 })));
    const nextProject = { ...cur, pages: next };
    setProjectSync(nextProject);
    void flushSave();
  };

  // S360 SYMBOL MAPPER: append a reviewed output as a normal, user-manageable
  // canvas page. Option A also creates a separate compact count-legend page.
  const addSymbolMapPage = async (
    result: SymbolMapperRenderResult,
    title: string,
    sheetCode: string,
    countPage: SymbolMapperCountPageRequest,
  ): Promise<void> => {
    captureActivePageState();
    const current = projectRef.current;
    if (!current) throw new Error('Open a Singh360 project before adding a Symbol Mapper page.');

    const imageResponse = await fetch(result.pngUrl, { cache: 'no-store' });
    if (!imageResponse.ok) throw new Error(`Could not read the reviewed Symbol Mapper PNG (${imageResponse.status}).`);
    const imageBlob = await imageResponse.blob();
    const safeBase = (result.sourceName || 'symbol-map')
      .replace(/\.pdf$/i, '')
      .replace(/[^A-Za-z0-9._-]+/g, '_')
      .replace(/^_+|_+$/g, '') || 'symbol-map';
    const imageFile = new File([imageBlob], `${safeBase}_reviewed.png`, { type: 'image/png' });
    const asset = await uploadAssetFile(current.id, imageFile);

    const latest = projectRef.current;
    if (!latest || latest.id !== current.id) throw new Error('The active project changed before the page could be added.');
    const pageId = newPageId();
    const cleanTitle = title.trim() || 'SYMBOL HIGHLIGHT PLAN';
    const cleanCode = sheetCode.trim() || 'NEW';
    const page: PageModel = {
      id: pageId,
      order: latest.pages.length + 1,
      include: true,
      sheetCode: cleanCode,
      displaySheetCode: cleanCode,
      sheetTitle: cleanTitle,
      sheetTab: cleanTitle,
      pageType: 'canvas',
      pageFamily: 'Image / Layout',
      layoutProfile: 'symbol_mapper',
      renderMode: 'canvas',
      renderProfile: 'symbol_mapper',
      normalizedHeaderStyle: 'none',
      template: 'canvas',
      templateId: '',
      blocks: [],
      canvasObjects: [],
      notes: `Created from ${result.sourceName || 'a reviewed Symbol Mapper PDF'}. Only user-accepted detections were rendered.`,
      pageGroupId: pageId,
    };

    const countArtifacts = countPage?.enabled
      ? buildSymbolCountSummaryArtifacts(
          countPage,
          result.sourceName || cleanTitle,
          newPageId(),
          `ws_symbol_count_${newPageId()}`,
        )
      : null;

    const imageReady = new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        if (pendingSymbolPageRef.current?.pageId === pageId) pendingSymbolPageRef.current = null;
        reject(new Error('The highlighted image did not finish loading onto the new page.'));
      }, 20000);
      pendingSymbolPageRef.current = {
        pageId,
        url: asset.url,
        name: asset.name,
        resolve: () => { window.clearTimeout(timer); resolve(); },
        reject: (reason: unknown) => { window.clearTimeout(timer); reject(reason); },
      };
    });

    const pagesToAdd = countArtifacts ? [page, countArtifacts.page] : [page];
    const pages = withPageNumbers([...latest.pages, ...pagesToAdd].map((item, index) => ({ ...item, order: index + 1 })));
    const next: ProjectModel = {
      ...latest,
      worksheets: latest.worksheets,
      pages,
    };
    setProjectSync(next);
    setActivePageId(pageId);
    setViewMode('normalized');
    setOverlayMode(true);
    setSelection(null);
    setRenumberBadge(true);
    writeRecoverySnapshot(next);

    await imageReady;
    captureActivePageState();
    if (countArtifacts) {
      setActivePageId(countArtifacts.page.id);
      setOverlayMode(false);
      setSelection(null);
    }
    const completed = projectRef.current;
    if (completed) writeRecoverySnapshot(completed);
    const saved = await confirmLatestProjectSaved();
    if (!saved) {
      throw new Error('The highlighted and count-summary pages were created, but the project save could not be confirmed. Use Save Now before navigating away.');
    }
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


  // S360 VISUAL PAGE ACTIONS V29
  const duplicatePageWithIdentity = (id: string, title: string, code: string) => {
    mutatePages((pages) => {
      const index = pages.findIndex((page) => page.id === id);
      if (index < 0) return pages;
      const source = pages[index];
      const newId = newPageId();
      const copy: PageModel = {
        ...structuredClone(source),
        id: newId,
        order: source.order + 0.5,
        sheetTitle: title.trim() || `${source.sheetTitle} Copy`,
        sheetCode: code.trim() || 'NEW',
        displaySheetCode: code.trim() || 'NEW',
        sheetTab: '',
        linkedWorksheetId: undefined,
        continuationOf: null,
        generatedContinuation: false,
        continuationIndex: undefined,
        pageGroupId: newId,
      };
      const next = [...pages];
      next.splice(index + 1, 0, copy);
      return next;
    });
  };

  const createBlankPageFromManager = (
    id: string,
    where: 'before' | 'after',
    title: string,
    code: string,
  ) => {
    addSheetFromModal(
      title.trim() || 'New Sheet',
      code.trim() || 'NEW',
      'canvas',
      id,
      where,
    );
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
    const target = projectRef.current?.pages.find((page) => page.id === id);
    if (target && isSheetIndexPage(target)) {
      window.alert('The Sheet Index / TOC is required and cannot be deleted. Excluded pages are removed from it automatically.');
      return;
    }
    if (!window.confirm('Delete this page? This cannot be undone. (Tip: use Exclude to keep it out of the package instead.)')) return;
    if (activePageId === id) {
      const remaining = project?.pages.filter((p) => p.id !== id) ?? [];
      setActivePageId(remaining[0]?.id ?? null);
    }
    mutatePages((pages) => pages.filter((p) => p.id !== id));
  };

  const setPageIncludedAtStoredPosition = (
    pages: PageModel[],
    pageId: string,
    include: boolean,
  ): PageModel[] => {
    const index = pages.findIndex((page) => page.id === pageId);
    if (index < 0) return pages;
    const target = pages[index];
    if (target.include === include) return pages;

    if (!include) {
      return pages.map((page, pageIndex) => (
        page.id === pageId
          ? { ...page, include: false, restorePackageIndex: pageIndex }
          : page
      ));
    }

    const remaining = pages.filter((page) => page.id !== pageId);
    const rawIndex = Number.isFinite(target.restorePackageIndex)
      ? Number(target.restorePackageIndex)
      : remaining.length;
    const insertAt = Math.max(0, Math.min(remaining.length, rawIndex));
    const restored = { ...target, include: true, restorePackageIndex: undefined };
    const next = [...remaining];
    next.splice(insertAt, 0, restored);
    return next;
  };

  const toggleInclude = (id: string) =>
    mutatePages((pages) => {
      const target = pages.find((page) => page.id === id);
      return target ? setPageIncludedAtStoredPosition(pages, id, !target.include) : pages;
    });

  // S360 RAPID PAGE REVIEW V35
  const toggleIncludeAndAdvance = async () => {
    if (rapidReviewBusy) return;
    const currentPage = activePageRef.current;
    const currentProject = projectRef.current;
    if (!currentPage || !currentProject) return;
    const includeLocked = currentPage.pageType === 'cover' || isSheetIndexPage(currentPage);
    if (includeLocked) return;

    const ordered = [...currentProject.pages].sort((a, b) => a.order - b.order);
    const filteredBefore = pageFilter === 'included'
      ? ordered.filter((page) => page.include)
      : pageFilter === 'excluded'
        ? ordered.filter((page) => !page.include)
        : ordered;
    const currentIndex = filteredBefore.findIndex((page) => page.id === currentPage.id);
    const nextPageId = currentIndex >= 0
      ? (filteredBefore[currentIndex + 1]?.id ?? filteredBefore[currentIndex - 1]?.id ?? null)
      : (filteredBefore[0]?.id ?? null);

    const pages = withPageNumbers(setPageIncludedAtStoredPosition(currentProject.pages, currentPage.id, !currentPage.include));
    const nextProject = { ...currentProject, pages };
    setRapidReviewBusy(true);
    setProjectSync(nextProject);
    setSaveStatus('saving');
    setSaveNotice('Saving page review…');
    await new Promise<void>((resolve) => window.setTimeout(resolve, 700));
    const saved = await confirmLatestProjectSaved(15000);
    if (!saved) {
      setSaveStatus('failed');
      setSaveNotice('PAGE REVIEW SAVE FAILED · STAYING ON CURRENT PAGE');
      setRapidReviewBusy(false);
      return;
    }
    if (nextPageId && nextPageId !== currentPage.id) {
      const target = projectRef.current?.pages.find((page) => page.id === nextPageId);
      setActivePageId(nextPageId);
      if (target?.linkedWorksheetId) setSelectedWorksheetId(target.linkedWorksheetId);
      setSelection(null);
    }
    setSaveNotice('PAGE REVIEW SAVED');
    window.setTimeout(() => setSaveNotice((notice) => notice === 'PAGE REVIEW SAVED' ? '' : notice), 2500);
    setRapidReviewBusy(false);
  };

  const openWorksheetDraft = useCallback(async (worksheetId: string) => {
    const ok = await ensureSavedBeforeNavigation();
    if (!ok) return;
    const current = projectRef.current;
    if (!current) return;
    const linked = current.pages.find((page) => page.linkedWorksheetId === worksheetId && !page.continuationOf)
      || current.pages.find((page) => page.linkedWorksheetId === worksheetId);
    if (linked) setActivePageId(linked.id);
    setSelectedWorksheetId(worksheetId);
    setViewMode('source');
    setSelection(null);
  }, [ensureSavedBeforeNavigation]);

  const publishWorksheet = useCallback(async (worksheetId: string) => {
    const ok = await ensureSavedBeforeNavigation();
    if (!ok) return;
    const current = projectRef.current;
    if (!current) return;
    const worksheet = current.worksheets.find((item) => item.id === worksheetId);
    if (!worksheet) return;

    const existing = current.pages.find((page) => page.linkedWorksheetId === worksheetId && !page.continuationOf)
      || current.pages.find((page) => page.linkedWorksheetId === worksheetId);
    if (existing) {
      // S360 EXISTING WORKSHEET ONE PAGE V1
      // Rebuild the already-loaded worksheet as one exact formatted page and
      // remove stale generated continuations before including it.
      const groupId = existing.pageGroupId || existing.id;
      const rebuilt = rebuildSinglePageFromSource({
        ...existing,
        renderMode: 'excel_exact',
        layoutProfile: 'single_sheet_excel_exact',
        splitMode: 'none',
        allowContinuation: false,
        minScale: 0.35,
        scaleMode: 'fit_body',
        trimBlankRows: false,
        trimBlankColumns: false,
      }, worksheet);
      const withoutContinuations = current.pages
        .filter((page) => !(
          page.id !== existing.id
          && page.generatedContinuation
          && (page.continuationOf === groupId || page.pageGroupId === groupId)
        ))
        .map((page) => page.id === existing.id ? rebuilt : page);
      const pages = withPageNumbers(setPageIncludedAtStoredPosition(withoutContinuations, existing.id, true));
      const next = { ...current, pages };
      setProjectSync(next);
      setActivePageId(existing.id);
      setSelectedWorksheetId(worksheetId);
      setViewMode('normalized');
      setRenumberBadge(true);
      await flushSave();
      return;
    }

    const suggestedCode = suggestedSheetCode(worksheet.name);
    const codeInput = window.prompt('Sheet code for the published page:', suggestedCode);
    if (codeInput === null) return;
    const titleInput = window.prompt('Published page title:', worksheet.name);
    if (titleInput === null) return;
    const id = newPageId();
    const base: PageModel = {
      id,
      order: current.pages.length + 1,
      include: true,
      sheetCode: codeInput.trim() || suggestedCode,
      displaySheetCode: codeInput.trim() || suggestedCode,
      sheetTitle: titleInput.trim() || worksheet.name,
      sheetTab: worksheet.name,
      pageType: 'data-grid',
      template: 'Text / Instructions',
      templateId: '',
      linkedWorksheetId: worksheet.id,
      sourceSheet: worksheet.name,
      sourceRange: worksheet.sourceRange,
      printArea: worksheet.printArea,
      renderMode: 'excel_exact',
      layoutProfile: 'single_sheet_excel_exact',
      splitMode: 'none',
      allowContinuation: false,
      minScale: 0.35,
      scaleMode: 'fit_body',
      trimBlankRows: false,
      trimBlankColumns: false,
      blocks: [],
      canvasObjects: [],
      notes: '',
      pageGroupId: id,
    };
    const published = rebuildSinglePageFromSource(base, worksheet);
    const pages = withPageNumbers([...current.pages, published]);
    const next = { ...current, pages };
    setProjectSync(next);
    setActivePageId(published.id);
    setSelectedWorksheetId(worksheetId);
    setViewMode('normalized');
    setRenumberBadge(true);
    writeRecoverySnapshot(next);
    await flushSave();
  }, [ensureSavedBeforeNavigation, flushSave, setProjectSync]);

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
      { label: 'Save Page as Template', onClick: () => { setActivePageId(id); setSaveTemplateOpen(true); } },
      { label: 'Insert Page Template', onClick: () => { setActivePageId(id); setTemplateLibManageOnly(false); setTemplateLibOpen(true); } },
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

  const insertPageFromTemplate = (tplPage: PageModel, mode: TemplateInsertMode) => {
    if (!project || !activePageId) return;
    mutatePages((pages) => {
      const idx = pages.findIndex((p) => p.id === activePageId);
      if (idx < 0) return pages;
      if (mode === 'new_after') {
        const copy: PageModel = {
          ...structuredClone(tplPage),
          id: newPageId(),
          order: pages[idx].order + 0.5,
          pageGroupId: newPageId(),
          continuationOf: null,
          generatedContinuation: false,
          include: true,
        };
        const next = [...pages];
        next.splice(idx + 1, 0, copy);
        return next.map((p, i) => ({ ...p, order: i + 1 }));
      }
      if (mode === 'replace_canvas') {
        return pages.map((p, i) =>
          i === idx
            ? {
                ...p,
                canvasObjects: structuredClone(tplPage.canvasObjects ?? []),
                blocks: structuredClone(tplPage.blocks ?? p.blocks ?? []),
                pageType: tplPage.pageType ?? p.pageType,
                layoutProfile: tplPage.layoutProfile ?? p.layoutProfile,
              }
            : p,
        );
      }
      // overlay
      return pages.map((p, i) =>
        i === idx
          ? {
              ...p,
              canvasObjects: [...(p.canvasObjects ?? []), ...structuredClone(tplPage.canvasObjects ?? [])],
            }
          : p,
      );
    });
    setSaveStatus('unsaved');
  };

  const onUploadWorkbook = async (file: File) => {
    const ok = await ensureSavedBeforeNavigation();
    if (!ok) return;
    // PHASE E: a project is already open — merge the workbook into it
    // (same project id, manual layout pages preserved) instead of always
    // bootstrapping a brand-new project from the upload.
    if (project) {
      setPendingReimportFile(file);
    } else {
      setPendingWorkbookFile(file);
    }
  };

  const onReimportedWorkbook = async () => {
    setPendingReimportFile(null);
    if (!project) return;
    try {
      const p = await getProject(project.id);
      lastSavedJsonRef.current = JSON.stringify(p);
      resetSourceEditState();
      setProjectSync(p);
      setSaveStatus('idle');
      setSelection(null);
    } catch (err) {
      console.error('refresh after reimport failed', err);
    }
  };

  const reapplyPagePagination = (pageId: string) => {
    const pg = project?.pages.find((p) => p.id === pageId);
    if (!pg?.linkedWorksheetId || pg.renderMode !== 'excel_exact') return;
    setProjectSync((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        pages: regenerateExcelGroup(prev, pg.linkedWorksheetId as string),
        paginationLocked: true,
      };
    });
  };

  const finishWorkbookImport = async (id: string) => {
    setPendingWorkbookFile(null);
    const p = await getProject(id);
    lastSavedJsonRef.current = JSON.stringify(p);
    resetSourceEditState();
    setProjectSync(p);
    setSaveStatus('idle');
    const firstPage = p.pages?.[0];
    setActivePageId(firstPage?.id ?? null);
    setSelectedWorksheetId(firstPage?.linkedWorksheetId ?? p.worksheets?.[0]?.id);
    setSelection(null);
    window.history.replaceState({}, '', `?project=${id}`);
  };

  const openProjectById = async (id: string) => {
    try {
      const ok = await ensureSavedBeforeNavigation();
      if (!ok) return;
      const p = await getProject(id);
      lastSavedJsonRef.current = JSON.stringify(p);
      resetSourceEditState();
      setProjectSync(p);
      setSaveStatus('idle');
      const firstPage = p.pages?.[0];
    setActivePageId(firstPage?.id ?? null);
    setSelectedWorksheetId(firstPage?.linkedWorksheetId ?? p.worksheets?.[0]?.id);
      setSelection(null);
      window.history.replaceState({}, '', `?project=${id}`);
    } catch (err) {
      console.error('open project failed', err);
    } finally {
      setOpenProjectOpen(false);
    }
  };

  const onImportedWorksheets = async (
    pageIds: string[],
    renumberSuggested: boolean,
    replacedPageId?: string,
  ) => {
    setImportWsOpen(null);
    if (!project) return;
    try {
      const p = await getProject(project.id);
      lastSavedJsonRef.current = JSON.stringify(p);
      resetSourceEditState();
      setProjectSync(p);
      if (replacedPageId) {
        setActivePageId(replacedPageId);
      } else if (pageIds.length) {
        setActivePageId(pageIds[0]);
      }
      if (renumberSuggested) setRenumberBadge(true);
    } catch (err) {
      console.error('refresh after import failed', err);
    }
  };

  // Restore a project (from a server backup or local recovery snapshot) into the
  // live editor and re-baseline the save manager so status is accurate.
  const applyRestoredProject = (p: ProjectModel) => {
    lastSavedJsonRef.current = JSON.stringify(p);
    resetSourceEditState();
    setProjectSync(p);
    const firstPage = p.pages?.[0];
    setActivePageId(firstPage?.id ?? activePageId);
    setSelectedWorksheetId(firstPage?.linkedWorksheetId ?? p.worksheets?.[0]?.id);
    setSelection(null);
    setSaveStatus('idle');
    setBackupOpen(false);
  };

  const onArchiveCurrentProject = async () => {
    if (!project) return;
    const name = project.projectDisplayName || (project.metadata as Record<string, string>)?.projectName || project.id;
    if (!window.confirm(`Archive project "${name}"?\n\nThis moves the project to .docs/_archive/ and returns you to the landing screen. Nothing is permanently deleted.`)) return;
    try {
      const res = await archiveProject(project.id);
      window.alert(`Project archived to:\n${res.archivedTo}`);
      setProjectSync(null);
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
      setProjectSync(p);
      setSaveStatus('saved');
    } catch (err) {
      console.error('CSV attach failed', err);
      setSaveStatus('failed');
    }
  };

  const onExportPdfSized = async (width: number, height: number, rev: { updateRevision: boolean; newRevision: string; notes: string }, pageIds: string[]) => {
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
      projectRef.current = proj;
      setProjectSync(proj);
    }
    const coverPage = proj.pages.find((pg) => pg.pageType === 'cover' && pg.linkedWorksheetId);
    if (coverPage?.linkedWorksheetId) {
      proj = applyCoverSourceTruth(proj, coverPage.linkedWorksheetId);
      projectRef.current = proj;
      setProjectSync(proj);
    }
    // Make sure the freshest canvas state is on the server before we render it.
    const ok = await captureAndSave();
    if (!ok) return;
    const base = proj.metadata.drawingPackageFileName || proj.projectDisplayName || proj.metadata.projectName || proj.id;
    const revSuffix = rev.updateRevision ? `_${rev.newRevision.replace(/\s+/g, '')}` : '';
    const downloadName = `${base}${revSuffix}.pdf`;
    try {
      const warnings = await fetchExportWarnings(proj.id, pageIds);
      if (warnings.length > 0) {
        pendingExportRef.current = { width, height, downloadName, pageIds };
        setExportWarnings(warnings);
        return;
      }
      const blob = await exportPdf(proj.id, { width, height, pageIds });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = downloadName;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('PDF export failed', err);
      window.alert(`PDF export failed: ${String(err)}`);
    }
  };

  const onExportPdfDespiteWarnings = async () => {
    const pending = pendingExportRef.current;
    if (!project || !pending) {
      setExportWarnings(null);
      return;
    }
    try {
      const blob = await exportPdf(project.id, { width: pending.width, height: pending.height, pageIds: pending.pageIds });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = pending.downloadName;
      a.click();
      URL.revokeObjectURL(url);
      pendingExportRef.current = null;
      setExportWarnings(null);
    } catch (err) {
      console.error('PDF export failed', err);
      window.alert(`PDF export failed: ${String(err)}`);
    }
  };

  const onExportPackage = async () => {
    if (!project) return;
    const ok = await captureAndSave();
    if (!ok) return;
    try {
      const blob = await exportPackage(project.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${project.metadata.projectName || project.id}_package.zip`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      console.error('Package export failed', err);
      window.alert(`Package export failed: ${String(err)}`);
    }
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
      setProjectSync((prev) =>
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
    setProjectSync((prev) => {
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

  const onDuplicateBlock = (pageId: string, blockId: string) => {
    setProjectSync((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        pages: prev.pages.map((pg) => {
          if (pg.id !== pageId) return pg;
          const blocks = pg.blocks ?? [];
          const idx = blocks.findIndex((b) => b.id === blockId);
          if (idx < 0) return pg;
          const copy: PageBlock = {
            ...structuredClone(blocks[idx]),
            id: `b_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
          };
          const nextBlocks = [...blocks];
          nextBlocks.splice(idx + 1, 0, copy);
          return { ...pg, blocks: nextBlocks };
        }),
      };
    });
  };

  const trimTrailingEmptyColumns = (grid: string[][]): string[][] => {
    const maxCol = grid.reduce((m, row) => {
      let last = -1;
      for (let i = 0; i < row.length; i += 1) {
        if ((row[i] ?? '').trim() !== '') last = i;
      }
      return Math.max(m, last + 1);
    }, 0);
    const cols = Math.max(1, maxCol);
    return grid.map((row) => {
      const out = row.slice(0, cols);
      while (out.length < cols) out.push('');
      return out;
    });
  };

  const syncBlocksFromGrid = (page: PageModel, grid: string[][]): PageBlock[] => {
    const blocks = page.blocks ?? [];
    const tableIdx = blocks.findIndex((b) => b.type === 'matrix' || b.type === 'table');
    if (tableIdx < 0) return blocks;
    const normalized = trimTrailingEmptyColumns(grid);
    const headers = (normalized[0] ?? []).map((x) => x ?? '');
    const rows = normalized.slice(1).map((r) => r.map((x) => x ?? ''));
    return blocks.map((b, i) => (i === tableIdx ? { ...b, headers, rows } : b));
  };


  const openSelectedImageCrop = useCallback(() => {
    const cropState = canvasApiRef.current?.getSelectedImageCrop();
    if (!cropState) {
      window.alert('Select one image first.');
      return;
    }
    setImageCropState(cropState);
  }, []);

  const applyImageCrop = useCallback((crop: ImageCropRect, placement: ImageCropPlacement) => {
    canvasApiRef.current?.applySelectedImageCrop(crop, placement);
    setImageCropState(null);
    window.setTimeout(() => captureActivePageState(), 0);
  }, [captureActivePageState]);

  const placeSelectedImageOnPage = useCallback((placement: 'fit' | 'fill') => {
    const cropState = canvasApiRef.current?.getSelectedImageCrop();
    if (!cropState) {
      window.alert('Select one image first.');
      return;
    }
    canvasApiRef.current?.applySelectedImageCrop(cropState.crop, placement);
    window.setTimeout(() => captureActivePageState(), 0);
  }, [captureActivePageState]);

  const canvasEnabled =
    !!activePage && viewMode === 'normalized';

  const sourceStatusLabel = (() => {
    if (!activePage?.linkedWorksheetId) return '';
    if (viewMode === 'source') {
      if (sourceCanUndo) return 'Undo available';
      if (sourceEditStatus === 'edited' || sourceDirty) return 'Draft edited';
      return '';
    }
    if (rebuildValidationModal) return 'Draft rebuild failed validation — current Published page kept';
    if (sourceEditStatus === 'updated') return 'Published updated';
    if (sourceDirty) return 'Draft edited';
    return '';
  })();

  const saveLabel =
    saveStatus === 'saving' ? 'Saving…'
    : saveStatus === 'unsaved' ? 'Unsaved Changes'
    : saveStatus === 'failed' ? 'Save Failed'
    : saveStatus === 'saved' ? (saveNotice || (savedAt ? `Saved ${savedAt}` : 'Saved'))
    : 'Ready';

  const ribbon = (
    <Ribbon
      saveStatus={saveStatus}
      saveLabel={saveLabel}
      hasProject={!!project}
      view={view}
      canvasEnabled={canvasEnabled}
      viewMode={viewMode}
      sourceCanUndo={sourceCanUndo}
      sourceCanRedo={sourceCanRedo}
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
        addBracket: () => { setOverlayMode(true); canvasApiRef.current?.addBracket(); },
        addDashedBox: () => { setOverlayMode(true); canvasApiRef.current?.addDashedBox(); },
        addPageTitle: () => { setOverlayMode(true); canvasApiRef.current?.addPageTitle(activePage?.sheetTitle ?? 'Page Title'); },
        addSectionHeader: () => { setOverlayMode(true); canvasApiRef.current?.addSectionHeader('Section Header'); },
        addNote: () => { setOverlayMode(true); canvasApiRef.current?.addNote('Note'); },
        deleteSelected: () => canvasApiRef.current?.deleteSelected(),
        copySelected: () => canvasApiRef.current?.copySelected(),
        pasteCopied: () => canvasApiRef.current?.pasteCopied(),
        duplicateSelected: () => canvasApiRef.current?.duplicateSelected(),
        unlockAll: () => canvasApiRef.current?.unlockAll(),
        undo: () => {
          if (viewMode === 'source') sourceUndo();
          else if (canRestorePageRebuild) pageRebuildUndo();
          else canvasApiRef.current?.undo();
        },
        redo: () => {
          if (viewMode === 'source') sourceRedo();
          else canvasApiRef.current?.redo();
        },
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
        addSymbolLegend: (config: SymbolLegendInsertConfig) => { setOverlayMode(true); canvasApiRef.current?.addSymbolLegend(config); },
        normalizeSymbolSize: () => canvasApiRef.current?.normalizeSymbolSize(),
        cropImage: openSelectedImageCrop,
        fitImageToPage: () => placeSelectedImageOnPage('fit'),
        fillImageToPage: () => placeSelectedImageOnPage('fill'),
        addBus: () => setBusOpen(true),
      }}
      onUploadFile={(f) => void onUploadWorkbook(f)}
      onUploadCsv={(f) => void onUploadCsv(f)}
      onInsertImage={(f) => void onDropImageFile(f)}
      onInsertPdfPage={() => setPdfCropOpen(true)}
      onSaveNow={() => void saveNow()}
      onWriteExcel={() => { void writeProjectToExcel(); }}
      writeExcelBusy={excelWriteBusy}
      onOpenBackups={() => setBackupOpen(true)}
      onExportPdf={() => setExportOpen(true)}
      onExportPackage={() => void onExportPackage()}
      onRenumber={onRenumber}
      renumberBadge={renumberBadge}
      onOpenProject={() => setOpenProjectOpen(true)}
      onOpenHome={() => window.location.assign(project ? `/app?project=${project.id}` : '/app')}
      onCleanWorkspace={() => setCleanWorkspaceOpen(true)}
      onImportWorksheet={() => setImportWsOpen({
        afterPageId: activePageId ?? undefined,
        replacePageId: activePageId ?? undefined,
        replacePageTitle: activePage?.sheetTitle,
      })}
      onSavePageTemplate={() => setSaveTemplateOpen(true)}
      onInsertPageTemplate={() => { setTemplateLibManageOnly(false); setTemplateLibOpen(true); }}
      onManagePageTemplates={() => { setTemplateLibManageOnly(true); setTemplateLibOpen(true); }}
      onInsertSymbolLegend={() => setSymbolLegendOpen(true)}
      onOpenSymbolMapper={() => setSymbolMapperOpen(true)}
      onArchiveCurrentProject={() => void onArchiveCurrentProject()}
      theme={theme}
      onSetTheme={setThemeState}
      selection={selection}
      onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
      onSetLineStyle={(style) => setLineStyle(style)}
      pageFilter={pageFilter}
      onSetPageFilter={setPageFilterSafely}
    />
  );

  if (helpMode) {
    return (
      <HelpCenter
        onClose={() => {
          const target = initialProjectId ? `/app?project=${initialProjectId}` : '/app';
          window.location.assign(target);
        }}
      />
    );
  }

  // S360 PROJECT HOME DEFAULT ROUTE V1
  if (!printMode && appMode !== 'editor') {
    return <ProjectDashboard project={project} />;
  }

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
              <p>Choose a workbook (.xlsx or .xlsm) from the File tab to generate output pages and begin editing your drawing package, or <button className="link-btn" onClick={() => setOpenProjectOpen(true)}>open a saved project</button>.</p>
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
          replacePageId={importWsOpen.replacePageId}
          replacePageTitle={importWsOpen.replacePageTitle}
          onImported={(ids, rs, replaced) => void onImportedWorksheets(ids, rs, replaced)}
          onCancel={() => setImportWsOpen(null)}
        />
      )}
      {pendingWorkbookFile && (
        <ContinuationPreviewModal
          file={pendingWorkbookFile}
          onImported={(id) => void finishWorkbookImport(id)}
          onCancel={() => setPendingWorkbookFile(null)}
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
          <CollapsibleSection
            title={pageFilter === 'included' ? 'Included Drawing Pages' : pageFilter === 'excluded' ? 'Not Included Pages' : 'All Drawing Pages'}
            hint="This list follows the active page filter. Drag to reorder; right-click for page actions."
          >
            <SheetManager pages={reviewPages} activePageId={activePageId} onSelect={(id) => { void switchPageSafely(id); }} onUpdate={(p) => { void updateFilteredPages(p); }} onToggleInclude={toggleInclude} onContextMenu={(id, x, y) => setPageMenu({ x, y, pageId: id })} />
          </CollapsibleSection>
          <CollapsibleSection title="Workbook Drafts" defaultOpen={false} hint="Original workbook tabs. Open a Draft or publish an excluded worksheet.">
            <WorkbookView
              worksheets={project.worksheets}
              pages={project.pages}
              selectedWorksheetId={selectedWorksheetId}
              onOpenDraft={(worksheetId) => { void openWorksheetDraft(worksheetId); }}
              onPublishWorksheet={(worksheetId) => { void publishWorksheet(worksheetId); }}
            />
          </CollapsibleSection>
          <CollapsibleSection title="Components" defaultOpen={false} hint="Search reusable devices and drag them onto a Published drawing page.">
            <LibraryPanelV2
              onInsert={onInsertComponent}
              canInsert={canvasEnabled}
              activePageType={activePage?.pageType}
              onOpenLegendEditor={() => setSymbolLegendOpen(true)}
            />
          </CollapsibleSection>
        </>
      }
      center={
        <DocumentView
          project={project}
          pages={reviewPages}
          activePage={activePage}
          worksheets={project.worksheets}
          selectedWorksheetId={selectedWorksheetId}
          view={view}
          actualZoom={actualZoom}
          viewMode={viewMode}
          sourceDirty={sourceDirty}
          sourceStatusLabel={sourceStatusLabel}
          onViewModeChange={handleViewModeChange}
          onRebuildFromSource={() => void rebuildCurrentPageFromSource()}
          canRebuildFromSource={!!activePage?.linkedWorksheetId}
          onRestorePageRebuild={restoreLastPageRebuild}
          canRestorePageRebuild={canRestorePageRebuild}
          onReplacePageSource={replaceCurrentPageSource}
          onExportPageSource={() => void exportCurrentSourceSheet()}
          onOpenHelp={() => window.open('/app?help=1', '_blank', 'noopener,noreferrer')}
          reviewPages={reviewPages}
          pageFilter={pageFilter}
          rapidReviewBusy={rapidReviewBusy}
          onNavigateReview={(direction) => { void navigateReviewPage(direction); }}
          onToggleIncludeAndAdvance={() => { void toggleIncludeAndAdvance(); }}
          activeTool={activeTool}
          snap={snap}
          overlayMode={overlayMode}
          onToolConsumed={onToolConsumed}
          onRegisterApi={onRegisterApi}
          onSelectionChange={onSelectionChange}
          onBlockChange={onBlockChange}
          onPatchPage={patchPage}
          onDuplicateBlock={onDuplicateBlock}
          onSelectPage={(id) => {
            void switchPageSafely(id);
          }}
          onReorderPages={(pages) => { void updateFilteredPages(pages); }}
          onRenamePageTitle={onRenamePageTitle}
          onEditPageCode={(id, code) => patchPage(id, {
            sheetCode: code.trim(),
            displaySheetCode: code.trim(),
          })}
          onDuplicatePageWithIdentity={duplicatePageWithIdentity}
          onCreateBlankPage={createBlankPageFromManager}
          onTogglePageInclude={toggleInclude}
          onDeletePage={deletePage}
          onPageContextMenu={(id, x, y) => setPageMenu({ x, y, pageId: id })}
          onDropImageFile={(file) => void onDropImageFile(file)}
          onDropComponent={onDropComponent}
          onScaleChange={onScaleChange}
          onWorksheetChange={(wsId, patch, opts) => {
            applyWorksheetPatch(wsId, patch, opts);
          }}
          onPublishSource={selectedWorksheetId ? () => { void publishWorksheet(selectedWorksheetId); } : undefined}
          onCanvasChange={(pageId, objects) => {
            // CRITICAL: functional update — always merges into the CURRENT state,
            // never into a potentially-stale closure capture of `project`.
            // Using `setProject({...project, ...})` here was the root cause of
            // drawings vanishing: if `project` was a stale closure from before
            // the objects were drawn, this would silently overwrite the live
            // canvas state with an empty canvasObjects array.
            setProjectSync((prev) => {
              if (!prev) return prev;
              return {
                ...prev,
                pages: prev.pages.map((pg) =>
                  pg.id === pageId ? { ...pg, canvasObjects: objects } : pg,
                ),
              };
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
                onChange={(e) => setProjectSync((prev) => prev ? { ...prev, metadata: { ...prev.metadata, projectName: e.target.value } } : prev)}
              />
            </div>
            <div className="field">
              <label htmlFor="proj-pkg" title="Output package / export filename, e.g. SA31_EMS_Lighting_V1">Drawing Package File Name</label>
              <input
                id="proj-pkg"
                title="Output package / export filename, e.g. SA31_EMS_Lighting_V1"
                placeholder="SA31_EMS_Lighting_V1"
                value={project.metadata.drawingPackageFileName || ''}
                onChange={(e) => setProjectSync((prev) => prev ? { ...prev, metadata: { ...prev.metadata, drawingPackageFileName: e.target.value } } : prev)}
              />
            </div>
            <div className="field">
              <label htmlFor="proj-loc" title="Project location / store address">Location</label>
              <input
                id="proj-loc"
                title="Project location / store address"
                value={project.metadata.location || ''}
                onChange={(e) => setProjectSync((prev) => prev ? { ...prev, metadata: { ...prev.metadata, location: e.target.value } } : prev)}
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
                  onChange={(e) => setProjectSync((prev) => prev ? { ...prev, metadata: { ...prev.metadata, revision: e.target.value } } : prev)}
                />
              </div>
              <div className="field">
                <label htmlFor="proj-issue" title="Date this package was issued">Issue Date</label>
                <input
                  id="proj-issue"
                  title="Date this package was issued"
                  value={project.metadata.issueDate || ''}
                  onChange={(e) => setProjectSync((prev) => prev ? { ...prev, metadata: { ...prev.metadata, issueDate: e.target.value } } : prev)}
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
                  onChange={(e) => setProjectSync((prev) => prev ? { ...prev, metadata: { ...prev.metadata, drawnBy: e.target.value } } : prev)}
                />
              </div>
              <div className="field">
                <label htmlFor="proj-checked" title="Person who checked the package">Checked By</label>
                <input
                  id="proj-checked"
                  title="Person who checked the package"
                  value={project.metadata.checkedBy || ''}
                  onChange={(e) => setProjectSync((prev) => prev ? { ...prev, metadata: { ...prev.metadata, checkedBy: e.target.value } } : prev)}
                />
              </div>
            </div>
            <div className="field">
              <label htmlFor="proj-file" title="Original uploaded workbook filename (read-only)">Source Workbook</label>
              <input id="proj-file" title="Original uploaded workbook filename (read-only)" value={project.sourceWorkbookName || project.metadata.sourceFile || ''} readOnly />
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
            onReapplyPagination={
              activePage.renderMode === 'excel_exact' && !activePage.continuationOf
                ? () => reapplyPagePagination(activePage.id)
                : undefined
            }
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
          drawingHint={
            activeTool === 'polyline' || activeTool === 'elbow'
              ? 'Click to add point · double-click or Enter to finish · Esc to cancel'
              : activeTool === 'line' || activeTool === 'arrow'
                ? 'Click-drag to draw a line (or click start, then click end) · Esc to cancel'
                : undefined
          }
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
        replacePageId={importWsOpen.replacePageId}
        replacePageTitle={importWsOpen.replacePageTitle}
        onImported={(ids, rs, replaced) => void onImportedWorksheets(ids, rs, replaced)}
        onCancel={() => setImportWsOpen(null)}
      />
    )}
    {pendingWorkbookFile && (
      <ContinuationPreviewModal
        file={pendingWorkbookFile}
        onImported={(id) => void finishWorkbookImport(id)}
        onCancel={() => setPendingWorkbookFile(null)}
      />
    )}
    {pendingReimportFile && project && (
      <ReimportWorkbookModal
        projectId={project.id}
        file={pendingReimportFile}
        onStartNew={() => {
          const nextFile = pendingReimportFile;
          setPendingReimportFile(null);
          if (nextFile) setPendingWorkbookFile(nextFile);
        }}
        onApplied={() => void onReimportedWorkbook()}
        onCancel={() => setPendingReimportFile(null)}
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
        pages={project.pages}
        onExport={(w, h, rev, pageIds) => void onExportPdfSized(w, h, rev, pageIds)}
        onCancel={() => setExportOpen(false)}
      />
    )}
    {exportWarnings && (
      <ExportWarningsModal
        warnings={exportWarnings}
        onClose={() => {
          pendingExportRef.current = null;
          setExportWarnings(null);
        }}
        onExportAnyway={() => void onExportPdfDespiteWarnings()}
      />
    )}
    {rebuildValidationModal && (
      <RebuildValidationModal
        issues={rebuildValidationModal.issues}
        onKeepCurrent={() => setRebuildValidationModal(null)}
        onReplaceAnyway={() => {
          const { pageId, rebuilt } = rebuildValidationModal;
          setRebuildValidationModal(null);
          applyPageRebuild(pageId, rebuilt);
        }}
      />
    )}
    {symbolMapperOpen && (
      <SymbolMapperModal
        onClose={() => setSymbolMapperOpen(false)}
        onAddPage={(result, title, sheetCode, countPage) => addSymbolMapPage(result, title, sheetCode, countPage)}
      />
    )}
    {symbolLegendOpen && (
      <SymbolLegendModal
        onClose={() => setSymbolLegendOpen(false)}
        onInsert={(config: SymbolLegendInsertConfig) => {
          setOverlayMode(true);
          canvasApiRef.current?.addSymbolLegend(config);
        }}
      />
    )}
    {saveTemplateOpen && activePage && (
      <SavePageTemplateModal
        page={activePage}
        onSaved={() => { setSaveTemplateOpen(false); window.alert('Page template saved.'); }}
        onCancel={() => setSaveTemplateOpen(false)}
      />
    )}
    {templateLibOpen && (
      <PageTemplateLibraryModal
        manageOnly={templateLibManageOnly}
        onInsert={templateLibManageOnly ? undefined : insertPageFromTemplate}
        onClose={() => setTemplateLibOpen(false)}
      />
    )}
    {imageCropState && (
      <ImageCropModal
        state={imageCropState}
        onApply={applyImageCrop}
        onCancel={() => setImageCropState(null)}
      />
    )}
    {pdfCropOpen && (
      <PdfCropModal
        projectId={project.id}
        onInsert={(url, name, meta, mode) => {
          setOverlayMode(true);
          // Current-page placement is implemented now. "Create new page" is
          // intentionally disabled in the modal for this pass.
          canvasApiRef.current?.addPdfCrop(url, name, {
            underlay: mode === 'underlay',
            meta,
          });
          setPdfCropOpen(false);
        }}
        onCancel={() => setPdfCropOpen(false)}
      />
    )}
    {backupOpen && (
      <BackupRecoveryModal
        projectId={project.id}
        onRestore={applyRestoredProject}
        onClose={() => setBackupOpen(false)}
      />
    )}
    {busOpen && (
      <BusModal
        onCreate={(opts: BusOptions) => {
          setOverlayMode(true);
          canvasApiRef.current?.startBus(opts);
          setBusOpen(false);
        }}
        onCancel={() => setBusOpen(false)}
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
          { label: 'Insert Symbol Legend', onClick: () => setSymbolLegendOpen(true) },
          { label: 'Import Worksheet from Excel', divider: true, onClick: () => setImportWsOpen({ afterPageId: activePageId ?? undefined }) },
          { label: 'Add Blank Sheet After', onClick: () => activePageId && addPage(activePageId, 'after') },
          { label: 'Duplicate Current Sheet', onClick: () => activePageId && duplicatePage(activePageId) },
          { label: 'Duplicate', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.duplicateSelected() },
          { label: 'Copy', disabled: !selection, onClick: () => canvasApiRef.current?.copySelected() },
          { label: 'Paste', onClick: () => canvasApiRef.current?.pasteCopied() },
          { label: 'Delete', disabled: !selection, onClick: () => canvasApiRef.current?.deleteSelected() },
          { label: 'Normalize Symbol Size', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.normalizeSymbolSize() },
          { label: 'Crop / Fit Selected Image', divider: true, disabled: !selection?.isImage, onClick: openSelectedImageCrop, hint: 'Choose the visible crop and optionally fit/fill the drawing area' },
          { label: 'Fit Selected Image to Page', disabled: !selection?.isImage, onClick: () => placeSelectedImageOnPage('fit') },
          { label: 'Fill Page with Selected Image', disabled: !selection?.isImage, onClick: () => placeSelectedImageOnPage('fill') },
          { label: 'Group Selected Objects', disabled: !selection, onClick: () => canvasApiRef.current?.group() },
          { label: selection?.isLegend ? 'Edit Legend / Marker' : 'Edit Group (Ungroup)', disabled: !selection?.isGroup, onClick: () => canvasApiRef.current?.ungroup(), hint: 'Break the grouped marker into editable text, symbols, and lines' },
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
          { label: 'Unlock All on Page', onClick: () => canvasApiRef.current?.unlockAll() },
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

// S360 WORKSPACE UX V14
