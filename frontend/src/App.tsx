import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  archiveProject,
  autoLayoutImportedPage,
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
  savePageRebuildBackup,
  updateLibV2Component,
  uploadAssetDataUrl,
  uploadAssetFile,
  type ExportWarning,
} from './api/client';
import type { SymbolMapperRenderResult } from './api/client';
import type { AnnotationApi, AnnotationSelection, AnnotationStyle, AnnotationTool, BusOptions, CalloutFamily, CalloutSetConfig, CanvasApi, CanvasSelection, LibraryComponentInsertMeta, LineStyle, PageBlock, PageModel, PlacedSymbolEditorConfig, ProjectModel, QuickAssemblyId, SavedAssembly, SmartComponentConfig, SmartComponentType, SymbolLegendInsertConfig, ViewMode, Worksheet, ImageCropPlacement, ImageCropRect, ImageCropState } from './model/types';
import { newCanvasObjectId } from './model/canvasObjectIdentity';
import { writeRecoverySnapshot } from './model/recovery';
import { duplicateAsAppManagedPage } from './model/pageDuplication';
import { normalizeProjectAssetUrls } from './model/assetUrl';
import { refreshBlockFromWorksheet, regenerateExcelGroup, refreshPageFromSource, applyCoverSourceTruth } from './model/excelRange';
import { isCoverWorksheet } from './model/metadataInference';
import { SourceWorksheetHistory } from './model/sourceWorksheetHistory';
import { PageRebuildHistory } from './model/pageRebuildHistory';
import { applyRebuiltPage, rebuildSinglePageFromSource } from './model/pageRebuild';
import { validatePageRebuild } from './model/pageRebuildValidation';
import { isCoverPage, isSheetIndexPage, normalizePackageManifest } from './model/packageIndex';
import { nextLogicalSheetCode } from './model/sheetCodes';
import { reconcileLayoutRebuildResult, reconcilePdfImportResult } from './model/asyncProjectMerge';
import RebuildValidationModal from './components/RebuildValidationModal';
import ProjectShell from './components/ProjectShell';
import SheetManager from './components/SheetManager';
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
import AddImportPageModal from './components/AddImportPageModal';
import ImageCropModal from './components/ImageCropModal';
import SymbolMapperModal from './components/SymbolMapperModal';
import { buildSymbolCountSummaryArtifacts, type SymbolMapperCountPageRequest } from './model/symbolCountSummary';
import BackupRecoveryModal from './components/BackupRecoveryModal';
import BusModal from './components/BusModal';
import SmartComponentModal from './components/SmartComponentModal';
import CalloutEditorModal from './components/CalloutEditorModal';
import PlacedSymbolEditorModal from './components/PlacedSymbolEditorModal';
import CollapsibleSection from './components/CollapsibleSection';
import StatusBar from './components/StatusBar';
import HelpCenter from './components/HelpCenter';
import ProjectDashboard from './components/ProjectDashboard';
import ProjectSettingsModal, { type ProjectSettingsUpdate } from './components/ProjectSettingsModal';
import ProjectFilesPage from './components/ProjectFilesPage';
import { defaultSmartComponentConfig, normalizeSmartComponentConfig } from './model/smartComponents';
import { defaultCalloutSetConfig, normalizeCalloutSetConfig } from './model/callouts';
import { isClipboardEditingContext } from './model/clipboardFocus';
import {
  classifyProjectChanges,
  confirmedProjectSaveState,
  hasUnconfirmedLocalEdits,
  type DirtyDomain,
  type SaveState,
} from './model/saveState';
import { DEFAULT_ANNOTATION_STYLE } from './model/annotations';

const DataWorkspace = lazy(() => import('./workspace/DataWorkspace'));
const ANNOTATIONS_OPEN_STORAGE_KEY = 'singh360-annotations-open:v1';

function getUrlParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    projectId: params.get('project'),
    print: params.get('print') === '1',
    help: params.get('help') === '1',
    mode: params.get('mode') === 'editor' ? 'editor' : 'home',
    view: params.get('view') || '',
    tool: params.get('tool') || '',
    projectFileId: params.get('projectFile') || '',
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
  return match ? `${match[1].toUpperCase()} ${match[2]}` : '';
}

// Canonical package order + live Page X of Y. This also keeps the generated
// Sheet Index second, moves excluded/internal pages after package pages, and
// counts every included physical continuation page.
function withPageNumbers(pages: PageModel[]): PageModel[] {
  // Page-level mutations do not own archivedPages or managed-page policy.
  // Preserve their exact incoming order here; setProjectSync performs the
  // project-level automatic index pass only for automatic standalone sets.
  const total = pages.filter((page) => page.include !== false).length;
  let pageNumber = 0;
  return pages.map((page, index) => {
    if (page.include === false) {
      return { ...page, order: index + 1, pageNumber: null, pageTotal: total };
    }
    pageNumber += 1;
    return { ...page, order: index + 1, pageNumber, pageTotal: total };
  });
}

function stampPageIfChanged(prior: PageModel | undefined, page: PageModel, timestamp: string): PageModel {
  if (!prior) return page.createdAt ? page : { ...page, createdAt: timestamp, modifiedAt: timestamp };
  const priorContent = { ...prior, modifiedAt: undefined };
  const nextContent = { ...page, modifiedAt: undefined };
  return JSON.stringify(priorContent) === JSON.stringify(nextContent)
    ? page
    : { ...page, createdAt: page.createdAt || prior.createdAt || timestamp, modifiedAt: timestamp };
}

function stampChangedPages(previous: PageModel[], next: PageModel[]): PageModel[] {
  const priorById = new Map(previous.map((page) => [page.id, page]));
  const timestamp = new Date().toISOString();
  return next.map((page) => stampPageIfChanged(priorById.get(page.id), page, timestamp));
}

export default function App() {
  const {
    projectId: initialProjectId,
    print: printMode,
    help: helpMode,
    mode: appMode,
    view: appView,
    tool: initialTool,
    projectFileId: initialProjectFileId,
    requestedPageId,
  } = getUrlParams();

  const [project, setProject] = useState<ProjectModel | null>(null);
  const [activePageId, setActivePageId] = useState<string | null>(null);
  const [selectedWorksheetId, setSelectedWorksheetId] = useState<string | undefined>(undefined);
  const [saveStatus, setSaveStatus] = useState<SaveState>('cleanLocal');
  const [savedAt, setSavedAt] = useState<string>('');
  const [dirtyDomains, setDirtyDomains] = useState<DirtyDomain[]>([]);
  const [saveError, setSaveError] = useState<string>('');
  const [saveNotice, setSaveNotice] = useState<string>('');
  const [projectLoadError, setProjectLoadError] = useState<string>('');
  const [layoutRebuildBusy, setLayoutRebuildBusy] = useState(false);
  const layoutRebuildBusyRef = useRef(false);

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
  const [annotationsOpen, setAnnotationsOpen] = useState(() => {
    try { return localStorage.getItem(ANNOTATIONS_OPEN_STORAGE_KEY) === '1'; } catch { return false; }
  });
  const [annotationTool, setAnnotationTool] = useState<AnnotationTool>('select');
  const [annotationStyle, setAnnotationStyle] = useState<AnnotationStyle>(DEFAULT_ANNOTATION_STYLE);
  const [annotationSelection, setAnnotationSelection] = useState<AnnotationSelection | null>(null);
  const [annotationApi, setAnnotationApi] = useState<AnnotationApi | null>(null);
  useEffect(() => {
    try { localStorage.setItem(ANNOTATIONS_OPEN_STORAGE_KEY, annotationsOpen ? '1' : '0'); } catch { /* ignore */ }
  }, [annotationsOpen]);
  const [lineStyle, setLineStyle] = useState<LineStyle>({
    stroke: '#111111', dash: 'solid', strokeWidth: 2, arrowStart: false, arrowEnd: false,
  });
  const [selection, setSelection] = useState<CanvasSelection | null>(null);
  useEffect(() => {
    if (selection) document.documentElement.dataset.canvasSelectionActive = 'true';
    else delete document.documentElement.dataset.canvasSelectionActive;
    document.dispatchEvent(new Event('singh360:tooltip-context-changed'));
    return () => {
      delete document.documentElement.dataset.canvasSelectionActive;
    };
  }, [selection]);
  const [renumberOpen, setRenumberOpen] = useState(initialTool === 'renumber');
  const [openProjectOpen, setOpenProjectOpen] = useState(false);
  const [cleanWorkspaceOpen, setCleanWorkspaceOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(initialTool === 'export');
  const [exportWarnings, setExportWarnings] = useState<ExportWarning[] | null>(null);
  const pendingExportRef = useRef<{
    width: number;
    height: number;
    revisionSuffix: string;
    pageIds: string[];
  } | null>(null);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [templateLibOpen, setTemplateLibOpen] = useState(false);
  const [templateLibManageOnly, setTemplateLibManageOnly] = useState(false);
  const [symbolLegendOpen, setSymbolLegendOpen] = useState(initialTool === 'symbol-legend');
  const [pdfCropOpen, setPdfCropOpen] = useState(initialTool === 'project-pdf' || initialTool === 'add-import');
  const [imageCropState, setImageCropState] = useState<ImageCropState | null>(null);
  const [symbolMapperOpen, setSymbolMapperOpen] = useState(initialTool === 'symbol-mapper');
  const [backupOpen, setBackupOpen] = useState(initialTool === 'backups');
  const [projectSettingsOpen, setProjectSettingsOpen] = useState(initialTool === 'settings');
  const [busOpen, setBusOpen] = useState(false);
  const [smartComponentEditor, setSmartComponentEditor] = useState<{
    mode: 'insert' | 'edit';
    config: SmartComponentConfig;
  } | null>(null);
  const [calloutEditor, setCalloutEditor] = useState<{
    mode: 'insert' | 'edit';
    config: CalloutSetConfig;
  } | null>(null);
  const [placedSymbolEditor, setPlacedSymbolEditor] = useState<PlacedSymbolEditorConfig | null>(null);
  const [addSheetPending, setAddSheetPending] = useState<{ refId: string; where: 'before' | 'after' } | null>(null);
  const [importWsOpen, setImportWsOpen] = useState<{
    afterPageId?: string;
    replacePageId?: string;
    replacePageTitle?: string;
  } | null>(null);
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
  const annotationApiRef = useRef<AnnotationApi | null>(null);
  const pendingSymbolPageRef = useRef<{ pageId: string; url: string; name: string; resolve: () => void; reject: (reason: unknown) => void } | null>(null);

  // ── Save manager: single source of truth for persistence + status ──
  // lastSavedJson is the JSON we last confirmed on the server. A project whose
  // JSON differs from it is genuinely dirty; equality means "hydrated, clean".
  const lastSavedJsonRef = useRef<string>('');
  const lastSavedProjectRef = useRef<ProjectModel | null>(null);
  const projectRef = useRef<ProjectModel | null>(project);
  const saveStatusRef = useRef(saveStatus);
  saveStatusRef.current = saveStatus;
  const savingRef = useRef(false);
  const saveLoopRef = useRef<Promise<boolean> | null>(null);

  const setProjectSync = useCallback((updater: ProjectModel | null | ((prev: ProjectModel | null) => ProjectModel | null)) => {
    const rawNext = typeof updater === 'function'
      ? (updater as (prev: ProjectModel | null) => ProjectModel | null)(projectRef.current)
      : updater;
    let next = rawNext;
    if (
      rawNext
      && rawNext.projectMode === 'standalone_layout'
      && rawNext.managedPagePolicy === 'automatic'
    ) {
      const configuredRows = rawNext.indexSettings?.rowsPerPage;
      const configuredCover = rawNext.coverSettings?.include;
      const manifest = normalizePackageManifest(
        rawNext.pages ?? [],
        rawNext.archivedPages ?? [],
        {
          automaticManagedPages: true,
          coverIncluded: typeof configuredCover === 'boolean' ? configuredCover : undefined,
          indexRowsPerPage: Number.isInteger(configuredRows) ? Number(configuredRows) : undefined,
        },
      );
      next = { ...rawNext, ...manifest };
    }
    projectRef.current = next;
    setProject(next);
    return next;
  }, []);

  const establishSavedBaseline = useCallback((saved: ProjectModel) => {
    const applied = setProjectSync(saved);
    const baseline = applied ?? saved;
    lastSavedProjectRef.current = baseline;
    lastSavedJsonRef.current = JSON.stringify(baseline);
    setSavedAt(
      baseline.lastSavedAt
      || new Date().toISOString(),
    );
    setDirtyDomains([]);
    setSaveError('');
    setSaveStatus(confirmedProjectSaveState(baseline));
    return baseline;
  }, [setProjectSync]);

  const markSaved = useCallback((saved?: ProjectModel) => {
    if (saved) {
      establishSavedBaseline(saved);
      return;
    }
    const d = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    setSavedAt(`${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`);
    setDirtyDomains([]);
    setSaveError('');
    setSaveStatus('cleanLocal');
  }, [establishSavedBaseline]);

  // Persist the freshest project to the server. Returns true only when the
  // server actually confirmed the write of the CURRENT project snapshot.
  const flushSave = useCallback(async (): Promise<boolean> => {
    if (printMode) return true;
    if (saveLoopRef.current) return saveLoopRef.current;

    // One caller owns the write loop. Edits made while a request is in flight
    // are coalesced into the next iteration, so a debounced autosave can never
    // be lost merely because its timer fired during an older request.
    const task = (async (): Promise<boolean> => {
      savingRef.current = true;
      try {
        while (true) {
          const snapshot = projectRef.current;
          if (!snapshot) return false;
          const snapshotJson = JSON.stringify(snapshot);
          if (snapshotJson === lastSavedJsonRef.current) return true;

          setSaveStatus('savingLocal');
          setSaveError('');
          let savedFromServer: ProjectModel;
          try {
            savedFromServer = normalizeProjectAssetUrls(await saveProject(snapshot));
          } catch (error) {
            setSaveStatus('saveFailed');
            setSaveError(String(error));
            writeRecoverySnapshot(projectRef.current ?? snapshot);
            return false;
          }

          if (JSON.stringify(projectRef.current) === snapshotJson) {
            markSaved(savedFromServer);
            return true;
          }

          // The completed response belongs to an older snapshot. Preserve the
          // live project and immediately loop to persist its newest revision.
          setSaveStatus('dirtyLocal');
        }
      } finally {
        savingRef.current = false;
      }
    })();

    saveLoopRef.current = task;
    try {
      return await task;
    } finally {
      if (saveLoopRef.current === task) saveLoopRef.current = null;
    }
  }, [markSaved, printMode]);


  // Wait through any in-flight autosave and keep retrying until the exact latest
  // project snapshot is confirmed by the server. This prevents a successfully
  // created Symbol Mapper page from being reported as a false save failure while
  // its reviewed image is still mounting on the Fabric canvas.
  const confirmLatestProjectSaved = useCallback(async (timeoutMs = 10000): Promise<boolean> => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const current = projectRef.current;
      if (!current) return false;
      if (JSON.stringify(current) === lastSavedJsonRef.current) {
        return true;
      }
      const ok = await flushSave();
      if (ok) {
        return true;
      }
      await new Promise<void>((resolve) => window.setTimeout(resolve, 150));
    }
    const current = projectRef.current;
    const confirmed = !!current && JSON.stringify(current) === lastSavedJsonRef.current;
    return confirmed;
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
    const annotationCanvas = annotationApiRef.current;
    const pageId = activePageRef.current?.id;
    if (!pageId || !projectRef.current) return projectRef.current;
    const objects = canvas?.captureCanvas();
    const annotationObjects = annotationCanvas?.captureAnnotations();
    const timestamp = new Date().toISOString();
    const capturedPages = projectRef.current.pages.map((page) => {
      if (page.id !== pageId) return page;
      let captured = page;
      if (objects) captured = { ...captured, canvasObjects: objects };
      if (annotationObjects) captured = { ...captured, annotationObjects };
      return stampPageIfChanged(page, captured, timestamp);
    });
    const updated: ProjectModel = {
      ...projectRef.current,
      pages: capturedPages,
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
    return confirmLatestProjectSaved(15_000);
  }, [captureActivePageState, confirmLatestProjectSaved]);

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
    else {
      setSelectedWorksheetId(undefined);
      setViewMode('normalized');
    }
    setSelection(null);
    setAnnotationSelection(null);
    setAnnotationTool('select');
  }, [ensureSavedBeforeNavigation]);

  // Explicit "Save Now": capture the live canvas, then contact the server.
  const saveNow = useCallback(async (): Promise<boolean> => {
    captureActivePageState(); // sync active-page capture MUST happen before any read of projectRef
    return confirmLatestProjectSaved(15_000);
  }, [captureActivePageState, confirmLatestProjectSaved]);

  const resetSourceEditState = useCallback(() => {
    sourceHistoryRef.current.clear();
    setSourceHistoryTick((n) => n + 1);
    setSourceEditStatus('idle');
    setSourceDirty(false);
  }, []);

  useEffect(() => {
    if (!initialProjectId) return;
    setProjectLoadError('');
    void getProject(initialProjectId).then((p) => {
      const normalized = normalizeProjectAssetUrls(p);
      resetSourceEditState();
      establishSavedBaseline(normalized);
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
    }).catch((error) => {
      console.warn('initial project load failed', error);
      setProjectLoadError(String(error));
    });
  }, [initialProjectId, establishSavedBaseline, resetSourceEditState]);

  // Debounced autosave driven by real changes. Marks Unsaved Changes immediately,
  // writes a local recovery snapshot, then persists after a short quiet period.
  useEffect(() => {
    if (!project || printMode) return;
    projectRef.current = project;
    const json = JSON.stringify(project);
    if (json === lastSavedJsonRef.current) return; // hydrated / no real change
    setDirtyDomains(classifyProjectChanges(lastSavedProjectRef.current, project));
    setSaveStatus(confirmedProjectSaveState(project) === 'conflict' ? 'conflict' : 'dirtyLocal');
    writeRecoverySnapshot(project);
    const t = setTimeout(() => { void flushSave(); }, 800);
    return () => clearTimeout(t);
  }, [project, printMode, flushSave]);

  // Warn before leaving with unsaved/in-flight changes.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (hasUnconfirmedLocalEdits(saveStatusRef.current)) {
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
  const onRegisterAnnotationApi = useCallback((api: AnnotationApi | null) => {
    annotationApiRef.current = api;
    setAnnotationApi(api);
  }, []);
  const onAnnotationSelectionChange = useCallback((value: AnnotationSelection | null) => {
    setAnnotationSelection(value);
  }, []);
  const onAnnotationChange = useCallback((pageId: string, objects: Record<string, unknown>[]) => {
    setProjectSync((previous) => {
      if (!previous) return previous;
      const timestamp = new Date().toISOString();
      return {
        ...previous,
        pages: previous.pages.map((page) => (
          page.id === pageId
            ? stampPageIfChanged(page, { ...page, annotationObjects: objects }, timestamp)
            : page
        )),
      };
    });
  }, [setProjectSync]);
  const changeAnnotationsOpen = useCallback((open: boolean) => {
    setAnnotationsOpen(open);
    if (!open) {
      annotationApiRef.current?.deselect();
      setAnnotationSelection(null);
      setAnnotationTool('select');
    } else {
      setActiveTool('select');
      setSelection(null);
    }
  }, []);

  // Push the current new-line style down to the canvas whenever it changes.
  useEffect(() => {
    canvasApiRef.current?.setLineStyle(lineStyle);
  }, [lineStyle]);

  // Refs so global paste/keyboard handlers read current values.
  const activePageRef = useRef(activePage);
  const viewModeRef = useRef(viewMode);
  const selectionRef = useRef(selection);
  const annotationsOpenRef = useRef(annotationsOpen);
  const annotationSelectionRef = useRef(annotationSelection);
  const selectedWorksheetIdRef = useRef(selectedWorksheetId);
  activePageRef.current = activePage;
  viewModeRef.current = viewMode;
  selectionRef.current = selection;
  annotationsOpenRef.current = annotationsOpen;
  annotationSelectionRef.current = annotationSelection;
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

  const replaceCurrentPageSource = useCallback(async () => {
    const saved = await ensureSavedBeforeNavigation();
    if (!saved) return;
    setImportWsOpen({
      afterPageId: activePageRef.current?.id ?? undefined,
      replacePageId: activePageRef.current?.id ?? undefined,
      replacePageTitle: activePageRef.current?.sheetTitle,
    });
  }, [ensureSavedBeforeNavigation]);

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
    const p = captureActivePageState();
    const page = p?.pages.find((candidate) => candidate.id === activePageRef.current?.id);
    const pageId = page?.id;
    const wsId = page?.linkedWorksheetId;
    if (!pageId || !wsId || !page || !p) return;
    const ws = p.worksheets.find((w) => w.id === wsId);
    if (!ws) return;

    if (!await confirmLatestProjectSaved(15_000)) {
      window.alert('Save failed. The imported table was not rebuilt, so the latest annotations remain unchanged.');
      return;
    }

    let serverSnapshotName: string;
    try {
      const backup = await savePageRebuildBackup(p.id, pageId, page);
      serverSnapshotName = backup.name;
    } catch (error) {
      window.alert(`Could not create the required pre-rebuild history snapshot. No layout was changed.\n\n${String(error)}`);
      return;
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
  }, [applyPageRebuild, captureActivePageState, confirmLatestProjectSaved]);

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
    // Leaving 'source' mode triggers a rebuild; leaving 'spreadsheet' does not
    // (the page-local worksheet is edited in-place via onWorksheetChange).
    if (
      viewModeRef.current === 'source'
      && mode !== 'source'
      && selectedWorksheetIdRef.current === activePageRef.current?.linkedWorksheetId
    ) {
      rebuildCurrentPageFromSource();
    }
    if (mode !== 'normalized') changeAnnotationsOpen(false);
    setViewMode(mode);
  }, [changeAnnotationsOpen, rebuildCurrentPageFromSource]);

  const handleAfterSetDrawingArea = useCallback(() => {
    setFitMode('page');
    setViewMode('normalized');
    setSaveNotice('DRAWING UPDATED FROM SELECTED RANGE');
    window.setTimeout(() => {
      setSaveNotice((current) => current === 'DRAWING UPDATED FROM SELECTED RANGE' ? '' : current);
    }, 2400);
  }, []);

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

  const createImagePageFromFile = async (file: File): Promise<boolean> => {
    const saved = await ensureSavedBeforeNavigation();
    if (!saved) return false;
    const projectId = projectRef.current?.id;
    if (!projectId) return false;
    try {
      const [asset, digest] = await Promise.all([
        uploadAssetFile(projectId, file),
        crypto.subtle.digest('SHA-256', await file.arrayBuffer()).then((bytes) =>
          [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, '0')).join(''),
        ),
      ]);
      if (asset.sha256 !== digest) throw new Error('The project-local image copy failed SHA-256 verification.');
      const dimensions = await new Promise<{ width: number; height: number }>((resolve) => {
        const image = new Image();
        image.onload = () => resolve({ width: image.naturalWidth || 1600, height: image.naturalHeight || 880 });
        image.onerror = () => resolve({ width: 1600, height: 880 });
        image.src = asset.url;
      });
      const maxWidth = 1560;
      const maxHeight = 840;
      const scale = Math.min(maxWidth / dimensions.width, maxHeight / dimensions.height, 1);
      const now = new Date().toISOString();
      const pageId = newPageId();
      let appended = false;
      const updated = setProjectSync((latest) => {
        if (!latest || latest.id !== projectId) return latest;
        const sheetCode = suggestedSheetCode(file.name)
          || nextLogicalSheetCode(latest.pages, activePageRef.current?.id);
        const page: PageModel = {
          id: pageId,
          order: latest.pages.length + 1,
          include: true,
          sheetCode,
          displaySheetCode: sheetCode,
          sheetTitle: file.name.replace(/\.[^.]+$/, '') || 'Imported Image',
          sheetTab: '',
          pageType: 'image',
          pageFamily: 'image',
          template: 'canvas',
          templateId: '',
          blocks: [],
          canvasObjects: [{
            type: 'image',
            objectId: newCanvasObjectId(),
            objName: file.name,
            src: asset.url,
            sourceUrl: asset.url,
            left: 20 + (maxWidth - dimensions.width * scale) / 2,
            top: 20 + (maxHeight - dimensions.height * scale) / 2,
            width: dimensions.width,
            height: dimensions.height,
            scaleX: scale,
            scaleY: scale,
            originX: 'left',
            originY: 'top',
          }],
          notes: '',
          createdAt: now,
          modifiedAt: now,
          sourceImport: {
            id: `image_${pageId}`,
            groupId: `image_${pageId}`,
            type: 'image',
            originalName: file.name,
            sha256: asset.sha256,
            localAsset: asset.storedFileName,
            projectLocalPath: asset.projectLocalPath,
            placementMode: 'fit_body',
            importedAt: now,
          },
        };
        appended = true;
        return { ...latest, pages: withPageNumbers([...latest.pages, page]) };
      });
      if (!updated || !appended) {
        throw new Error('The open project changed before the image page could be added.');
      }
      setActivePageId(pageId);
      setPdfCropOpen(false);
      return true;
    } catch (error) {
      console.error('Image import failed', error);
      throw error;
    }
  };

  const initialProjectImageStarted = useRef(false);
  useEffect(() => {
    if (
      initialTool !== 'project-image'
      || !initialProjectFileId
      || !project?.id
      || !activePageId
      || initialProjectImageStarted.current
    ) return;
    initialProjectImageStarted.current = true;
    const timer = window.setTimeout(() => {
      fetch(`/api/projects/${project.id}/project-files/${initialProjectFileId}/content`)
        .then(async (response) => {
          if (!response.ok) throw new Error(`Project image could not be opened (${response.status}).`);
          const disposition = response.headers.get('content-disposition') || '';
          const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
          const basic = disposition.match(/filename="?([^";]+)"?/i)?.[1];
          const name = encoded ? decodeURIComponent(encoded) : basic || 'project-image';
          const blob = await response.blob();
          await onDropImageFile(new File([blob], name, { type: blob.type }));
        })
        .catch((reason) => window.alert(String(reason)));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [activePageId, initialProjectFileId, initialTool, project?.id]);

  // Insert a library component (image asset) onto the ACTIVE page only.
  const onInsertComponent = (
    name: string,
    url: string,
    label: string | null,
    meta?: LibraryComponentInsertMeta,
  ): Promise<void> => {
    if (!isCanvasContext()) return Promise.resolve();
    setOverlayMode(true);
    return canvasApiRef.current?.addComponent(url, name, label, undefined, meta) ?? Promise.resolve();
  };

  const insertQuickAssembly = (kind: QuickAssemblyId) => {
    if (!isCanvasContext()) return;
    setOverlayMode(true);
    if (kind === 'signage-legend') {
      canvasApiRef.current?.addSymbolLegend({
        title: 'SIGNAGE LEGEND',
        frame: true,
        rows: [
          { label: 'Leak detected / do not enter', acronym: 'DNE', symbolUrl: '/api/lib/asset/symbols/symbols_markers/rdm_sign_leak_dne.svg' },
          { label: 'Person trapped', acronym: 'PT', symbolUrl: '/api/lib/asset/symbols/symbols_markers/rdm_sign_person_trapped.svg' },
          { label: 'Help / trapped', acronym: 'HELP', symbolUrl: '/api/lib/asset/symbols/symbols_markers/rdm_sign_help_trapped.svg' },
        ],
      });
      return;
    }
    if (kind === 'generated-symbol-key') {
      const rows: SymbolLegendInsertConfig['rows'] = [];
      const seen = new Set<string>();
      const visit = (objects: Record<string, unknown>[]) => {
        objects.forEach((object) => {
          const sourceUrl = String(object.sourceUrl || object.src || '').trim();
          const name = String(object.objName || object.symAcronym || 'Symbol').replace(/^Legend\s+/i, '');
          if (sourceUrl && !/^Legend\s/i.test(String(object.objName || ''))) {
            const key = `${sourceUrl}|${name}`;
            if (!seen.has(key)) {
              seen.add(key);
              rows.push({
                label: name,
                acronym: String(object.symAcronym || ''),
                category: String(object.symCategory || ''),
                symbolUrl: sourceUrl,
              });
            }
          }
          if (Array.isArray(object.objects)) visit(object.objects as Record<string, unknown>[]);
        });
      };
      visit(activePageRef.current?.canvasObjects || []);
      if (!rows.length) {
        window.alert('Insert at least one component symbol on this page before generating its symbol key.');
        return;
      }
      canvasApiRef.current?.addSymbolLegend({ title: 'GENERATED SYMBOL KEY', frame: true, rows });
      return;
    }
    void canvasApiRef.current?.addQuickAssembly(kind);
  };

  const openSmartComponent = (kind: SmartComponentType) => {
    if (!isCanvasContext()) return;
    setSmartComponentEditor({
      mode: 'insert',
      config: defaultSmartComponentConfig(kind),
    });
  };

  const editSelectedSmartComponent = () => {
    if (!selection?.smartComponentType || !selection.smartConfig) {
      window.alert('Select one grouped smart component first.');
      return;
    }
    setSmartComponentEditor({
      mode: 'edit',
      config: normalizeSmartComponentConfig(selection.smartConfig, selection.smartComponentType),
    });
  };

  const insertSingleCallout = (family: Extract<CalloutFamily, 'round' | 'square'>) => {
    if (!isCanvasContext()) return;
    const config = defaultCalloutSetConfig(family);
    config.setName = `${family === 'round' ? 'Round' : 'Square'} Callout 1`;
    config.entries = [{
      callout: '1',
      label: '',
      description: '',
      text: '',
    }];
    setOverlayMode(true);
    canvasApiRef.current?.addCalloutSet(config);
  };

  const openCalloutBuilder = (family: CalloutFamily) => {
    if (!isCanvasContext()) return;
    setCalloutEditor({
      mode: 'insert',
      config: defaultCalloutSetConfig(family),
    });
  };

  const editSelectedCallout = () => {
    if (!selection?.calloutConfig) {
      window.alert('Select one editable callout set or block first.');
      return;
    }
    setCalloutEditor({
      mode: 'edit',
      config: normalizeCalloutSetConfig(
        selection.calloutConfig,
        selection.calloutConfig.family,
      ),
    });
  };

  const placedSymbolConfig = (): PlacedSymbolEditorConfig | null => {
    if (!selection) return null;
    return {
      name: selection.name || 'Placed Symbol',
      label: selection.symbolLabel || '',
      width: Math.max(16, selection.width || 96),
      height: Math.max(16, selection.height || 96),
      category: selection.symCategory || 'custom',
      opacity: selection.opacity ?? 1,
      favorite: selection.favorite === true,
    };
  };

  const editPlacedSelection = () => {
    if (selection?.calloutConfig) {
      editSelectedCallout();
      return;
    }
    if (selection?.smartComponentType) {
      editSelectedSmartComponent();
      return;
    }
    const config = placedSymbolConfig();
    if (!config) {
      window.alert('Select a placed symbol or component first.');
      return;
    }
    setPlacedSymbolEditor(config);
  };

  const renamePlacedSelection = () => {
    if (!selection) return;
    const nextName = window.prompt('Rename placed object', selection.name || 'Placed Symbol')?.trim();
    if (!nextName) return;
    if (selection.calloutConfig) {
      canvasApiRef.current?.updateSelectedCalloutSet({
        ...selection.calloutConfig,
        setName: nextName,
      });
      return;
    }
    if (selection.isPlacedSymbol) {
      const config = placedSymbolConfig();
      if (config) canvasApiRef.current?.updateSelectedPlacedSymbol({ ...config, name: nextName });
      return;
    }
    canvasApiRef.current?.updateSelected({ name: nextName });
  };

  const movePlacedSelectionToCategory = () => {
    const config = placedSymbolConfig();
    if (!selection || !config) return;
    const category = window.prompt('Move placed symbol to category', config.category)?.trim();
    if (!category) return;
    canvasApiRef.current?.updateSelectedPlacedSymbol({ ...config, category });
  };

  const togglePlacedSelectionFavorite = () => {
    const config = placedSymbolConfig();
    if (!selection || !config) return;
    const favorite = !config.favorite;
    canvasApiRef.current?.updateSelectedPlacedSymbol({ ...config, favorite });
    if (selection.libraryComponentId) {
      void updateLibV2Component(selection.libraryComponentId, { favorite })
        .then(() => window.dispatchEvent(new CustomEvent('singh360:library-changed')))
        .catch((error) => window.alert(`Could not update the library favorite: ${String(error)}`));
    }
  };

  const saveSelectionAsAssembly = () => {
    const object = canvasApiRef.current?.captureSelectedAssembly();
    if (!object) {
      window.alert('Select any completed object or multi-selection before saving an assembly.');
      return;
    }
    const proposed = String(object.objName || object.assemblyName || 'Saved Assembly');
    const name = window.prompt('Assembly name', proposed)?.trim();
    if (!name) return;
    const assembly: SavedAssembly = {
      id: newCanvasObjectId(),
      name,
      createdAt: new Date().toISOString(),
      object,
    };
    setProjectSync((current) => current ? {
      ...current,
      savedAssemblies: [...(current.savedAssemblies || []), assembly],
    } : current);
    void confirmLatestProjectSaved(15_000);
  };

  const insertSavedAssembly = (assembly: SavedAssembly) => {
    if (!isCanvasContext()) return;
    setOverlayMode(true);
    void canvasApiRef.current?.addSavedAssembly(assembly);
  };

  const updateSavedAssembly = (id: string, patch: Partial<SavedAssembly>) => {
    setProjectSync((current) => current ? {
      ...current,
      savedAssemblies: (current.savedAssemblies || []).map((assembly) =>
        assembly.id === id ? { ...assembly, ...patch } : assembly),
    } : current);
    void confirmLatestProjectSaved(15_000);
  };

  const deleteSavedAssembly = (id: string) => {
    setProjectSync((current) => current ? {
      ...current,
      savedAssemblies: (current.savedAssemblies || []).filter((assembly) => assembly.id !== id),
    } : current);
    void confirmLatestProjectSaved(15_000);
  };

  const duplicateSavedAssembly = (assembly: SavedAssembly, proposedName?: string) => {
    const name = proposedName || window.prompt('Assembly copy name', `${assembly.name} Copy`)?.trim();
    if (!name) return;
    const duplicate: SavedAssembly = {
      ...assembly,
      id: newCanvasObjectId(),
      name,
      createdAt: new Date().toISOString(),
      object: structuredClone(assembly.object),
    };
    setProjectSync((current) => current ? {
      ...current,
      savedAssemblies: [...(current.savedAssemblies || []), duplicate],
    } : current);
    void confirmLatestProjectSaved(15_000);
  };

  const onDropComponent = (
    url: string,
    name: string,
    label: string | null,
    clientX: number,
    clientY: number,
    meta?: LibraryComponentInsertMeta,
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
      if (layoutRebuildBusyRef.current) {
        e.preventDefault();
        return;
      }
      if (isClipboardEditingContext(e.target)) return;
      if (!isCanvasContext()) return;
      if (annotationsOpenRef.current) {
        if (annotationSelectionRef.current) annotationApiRef.current?.pasteCopied();
        e.preventDefault();
        return;
      }
      if (activePageRef.current?.excelLayout) return;
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
      if (layoutRebuildBusyRef.current) {
        e.preventDefault();
        return;
      }
      const k = e.key.toLowerCase();
      if (isClipboardEditingContext(e.target)) return;
      if (viewModeRef.current === 'normalized' && annotationsOpenRef.current) {
        if (e.key === 'Escape') {
          // Fullscreen Escape belongs to browser chrome. Do not collapse the
          // annotation dock or consume the key while the app shell is fullscreen.
          if (document.fullscreenElement) return;
          e.preventDefault();
          changeAnnotationsOpen(false);
          return;
        }
        if (e.key === 'Delete') {
          e.preventDefault();
          annotationApiRef.current?.deleteSelected();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && k === 'z') {
          e.preventDefault();
          annotationApiRef.current?.undo();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && k === 'y') {
          e.preventDefault();
          annotationApiRef.current?.redo();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && k === 'c' && annotationSelectionRef.current) {
          e.preventDefault();
          annotationApiRef.current?.copySelected();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && k === 'v' && annotationSelectionRef.current) {
          e.preventDefault();
          annotationApiRef.current?.pasteCopied();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && k === 'd' && annotationSelectionRef.current) {
          e.preventDefault();
          annotationApiRef.current?.duplicateSelected();
          return;
        }
      }
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
  }, [changeAnnotationsOpen]);

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
    // Child page-management surfaces receive the last rendered page array.
    // Capture may synchronously advance projectRef beyond that render, so apply
    // only fields the child actually changed compared with its rendered input.
    // This preserves freshly captured Fabric/DOM content while still accepting
    // reorder, rename, recode, status, and template operations by stable ID.
    const renderedPages = project?.pages ?? [];
    captureActivePageState();
    const cur = projectRef.current;
    if (!cur) return;
    const renderedById = new Map(renderedPages.map((page) => [page.id, page]));
    const authoritativeById = new Map(cur.pages.map((page) => [page.id, page]));
    const incomingIds = new Set(pages.map((page) => page.id));
    const merged = pages.map((incoming) => {
      const authoritative = authoritativeById.get(incoming.id);
      const rendered = renderedById.get(incoming.id);
      if (!authoritative || !rendered) return incoming;
      const next = { ...authoritative } as PageModel & Record<string, unknown>;
      const incomingRecord = incoming as PageModel & Record<string, unknown>;
      const renderedRecord = rendered as PageModel & Record<string, unknown>;
      Object.keys(incomingRecord).forEach((key) => {
        if (key === 'id') return;
        if (JSON.stringify(incomingRecord[key]) !== JSON.stringify(renderedRecord[key])) {
          next[key] = incomingRecord[key];
        }
      });
      return next;
    });
    cur.pages.forEach((page) => {
      if (!incomingIds.has(page.id)) merged.push(page);
    });
    const numbered = stampChangedPages(cur.pages, withPageNumbers(merged));
    const next: ProjectModel = { ...cur, pages: numbered };
    setProjectSync(next);
    await confirmLatestProjectSaved(15_000);
  };

  // Single source of truth for per-page edits. Every edit surface (tab, left
  // list, page heading, right panel) funnels through here so all views stay in
  // sync, page numbering stays correct, and the change autosaves.
  const patchPage = (pageId: string, patch: Partial<PageModel>) => {
    setProjectSync((prev) => {
      if (!prev) return prev;
      const pages = stampChangedPages(
        prev.pages,
        withPageNumbers(prev.pages.map((p) => (p.id === pageId ? { ...p, ...patch } : p))),
      );
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
    const next = stampChangedPages(
      cur.pages,
      withPageNumbers(fn(cur.pages).map((p, i) => ({ ...p, order: i + 1 }))),
    );
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
    const cleanCode = sheetCode.trim() || nextLogicalSheetCode(latest.pages, activePageRef.current?.id);
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
      throw new Error('The highlighted and count-summary pages were created, but the project save could not be confirmed. Use Save Project before navigating away.');
    }
  };

  const duplicatePage = (id: string) => {
    mutatePages((pages) => {
      const idx = pages.findIndex((p) => p.id === id);
      if (idx < 0) return pages;
      const src = pages[idx];
      if (isCoverPage(src) || isSheetIndexPage(src)) return pages;
      const now = new Date().toISOString();
      const code = nextLogicalSheetCode(pages, id);
      const copy = {
        ...duplicateAsAppManagedPage(src, newPageId()),
        sheetCode: code,
        displaySheetCode: code,
        createdAt: now,
        modifiedAt: now,
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
      if (isCoverPage(source) || isSheetIndexPage(source)) return pages;
      const newId = newPageId();
      const now = new Date().toISOString();
      const copy: PageModel = {
        ...duplicateAsAppManagedPage(source, newId),
        sheetTitle: title.trim() || `${source.sheetTitle} Copy`,
        sheetCode: code.trim() || nextLogicalSheetCode(pages, id),
        displaySheetCode: code.trim() || nextLogicalSheetCode(pages, id),
        createdAt: now,
        modifiedAt: now,
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
      code.trim() || nextLogicalSheetCode(projectRef.current?.pages ?? [], id),
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
      const now = new Date().toISOString();
      const cleanCode = code.trim() || nextLogicalSheetCode(pages, refId);
      const blank: PageModel = {
        id: newPageId(),
        order: 0,
        include: true,
        sheetCode: cleanCode,
        displaySheetCode: cleanCode,
        sheetTitle: title || 'New Sheet',
        sheetTab: '',
        pageType: template as PageModel['pageType'] || 'data-grid',
        template: template,
        templateId: '',
        blocks: template === 'canvas'
          ? []
          : [
              { id: `b_${newPageId()}`, type: 'paragraph', text: '', editable: true },
              {
                id: `b_${newPageId()}`,
                type: 'table',
                headers: ['Column 1', 'Column 2', 'Notes'],
                rows: [['', '', '']],
                editable: true,
              },
            ],
        canvasObjects: [],
        notes: '',
        createdAt: now,
        modifiedAt: now,
      };
      const out = [...pages];
      out.splice(where === 'before' ? idx : idx + 1, 0, blank);
      return out;
    });
    setRenumberBadge(true);
    setAddSheetPending(null);
  };

  const deletePage = async (id: string) => {
    const target = projectRef.current?.pages.find((page) => page.id === id);
    // Keep the selected-page identity across the archive save. Removing the
    // selected page makes the next render set activePageRef.current to null;
    // reading that ref after the await would strand the editor in its empty
    // state even though the archive reached the server successfully.
    const activePageIdBeforeArchive = activePageRef.current?.id ?? null;
    if (target && (target.pageType === 'cover' || isSheetIndexPage(target))) {
      window.alert('The app-managed Cover and Sheet Index cannot be archived. They update automatically from the project.');
      return;
    }
    if (!target || !window.confirm(`Archive page "${target.sheetTitle}"? You can restore it from Archived Pages.`)) return;
    // Archiving is a navigation operation. Capture the live Fabric canvas
    // before removing any page from React state, then require the exact archive
    // snapshot to reach the server before switching away. Otherwise a quick
    // draw -> Archive gesture can archive a stale page and lose the last edit.
    const authoritative = captureActivePageState();
    if (!authoritative) return;
    const index = authoritative.pages.findIndex((page) => page.id === id);
    if (index < 0) return;
    const groupIds = new Set(
      target.continuationOf
        ? [id]
        : authoritative.pages
          .filter((page) => page.id === id || page.continuationOf === id)
          .map((page) => page.id),
    );
    const archivedGroupRootId = id;
    const archivedAt = new Date().toISOString();
    const archived = authoritative.pages.flatMap((page, pageIndex) => (
      groupIds.has(page.id)
        ? [{
            ...page,
            include: false,
            archivedInclude: page.include,
            archivedAt,
            archivedReason: page.id === id
              ? 'Archived from Pages panel'
              : `Archived with continuation group ${target.sheetCode || target.sheetTitle}`,
            archivedFromIndex: pageIndex,
            archivedPreviousPageId: authoritative.pages[pageIndex - 1]?.id || '',
            archivedNextPageId: authoritative.pages[pageIndex + 1]?.id || '',
            archivedGroupRootId,
            modifiedAt: archivedAt,
          }]
        : []
    ));
    const archivedProject: ProjectModel = {
      ...authoritative,
      pages: withPageNumbers(authoritative.pages.filter((page) => !groupIds.has(page.id))),
      archivedPages: [...(authoritative.archivedPages ?? []), ...archived],
    };
    const normalizedArchivedProject = setProjectSync(archivedProject) ?? archivedProject;
    writeRecoverySnapshot(normalizedArchivedProject);

    const saved = await confirmLatestProjectSaved(15_000);
    if (!saved) {
      projectRef.current = authoritative;
      setProject(authoritative);
      writeRecoverySnapshot(authoritative);
      window.alert('Archive failed. The page and its captured edits were restored; try Save Project and archive again.');
      return;
    }
    if (activePageIdBeforeArchive && groupIds.has(activePageIdBeforeArchive)) {
      const remaining = projectRef.current?.pages ?? [];
      const next = remaining[Math.min(index, Math.max(0, remaining.length - 1))] ?? remaining[index - 1] ?? remaining[0];
      setActivePageId(next?.id ?? null);
      if (next?.linkedWorksheetId) setSelectedWorksheetId(next.linkedWorksheetId);
      else {
        setSelectedWorksheetId(undefined);
        setViewMode('normalized');
      }
      setSelection(null);
    }
  };

  const restoreArchivedPage = async (id: string) => {
    const authoritative = captureActivePageState();
    if (!authoritative) return;
    const selected = (authoritative.archivedPages ?? []).find((page) => page.id === id);
    if (!selected) return;
    const inferredLegacyGroupRoot = selected.continuationOf
      && (authoritative.archivedPages ?? []).some((page) => page.id === selected.continuationOf)
      ? selected.continuationOf
      : '';
    const archivedGroupRootId = selected.archivedGroupRootId || inferredLegacyGroupRoot;
    const groupIds = new Set(
      archivedGroupRootId
        ? (authoritative.archivedPages ?? [])
          .filter((page) => (
            page.archivedGroupRootId === archivedGroupRootId
            || page.id === archivedGroupRootId
            || page.continuationOf === archivedGroupRootId
          ))
          .map((page) => page.id)
        : selected.continuationOf
          ? [id]
          : (authoritative.archivedPages ?? [])
            .filter((page) => page.id === id || page.continuationOf === id)
            .map((page) => page.id),
    );
    const group = (authoritative.archivedPages ?? [])
      .filter((page) => groupIds.has(page.id))
      .sort((a, b) => (a.archivedFromIndex ?? Number.MAX_SAFE_INTEGER) - (b.archivedFromIndex ?? Number.MAX_SAFE_INTEGER));
    const remaining = (authoritative.archivedPages ?? []).filter((page) => !groupIds.has(page.id));
    const restoredAt = new Date().toISOString();
    const pages = [...authoritative.pages];
    for (const archived of group) {
      const previousIndex = pages.findIndex((page) => page.id === archived.archivedPreviousPageId);
      const nextIndex = pages.findIndex((page) => page.id === archived.archivedNextPageId);
      const fallbackIndex = Math.max(0, Math.min(pages.length, archived.archivedFromIndex ?? pages.length));
      const insertAt = previousIndex >= 0 ? previousIndex + 1 : nextIndex >= 0 ? nextIndex : fallbackIndex;
      const restored = {
        ...archived,
        include: archived.archivedInclude ?? true,
        archivedAt: undefined,
        archivedReason: undefined,
        archivedFromIndex: undefined,
        archivedPreviousPageId: undefined,
        archivedNextPageId: undefined,
        archivedInclude: undefined,
        archivedGroupRootId: undefined,
        lastArchivedAt: archived.archivedAt || '',
        lastArchivedReason: archived.archivedReason || '',
        lastArchivedFromIndex: archived.archivedFromIndex ?? insertAt,
        lastArchivedGroupRootId: archived.archivedGroupRootId || archived.id,
        restoredAt,
        modifiedAt: restoredAt,
      };
      pages.splice(insertAt, 0, restored);
    }
    const restoredProject: ProjectModel = {
      ...authoritative,
      pages: withPageNumbers(pages),
      archivedPages: remaining,
    };
    const normalizedRestoredProject = setProjectSync(restoredProject) ?? restoredProject;
    writeRecoverySnapshot(normalizedRestoredProject);
    const saved = await confirmLatestProjectSaved(15_000);
    if (!saved) {
      projectRef.current = authoritative;
      setProject(authoritative);
      writeRecoverySnapshot(authoritative);
      window.alert('Restore failed. The archived-page state was kept unchanged; try Save Project and restore again.');
    }
  };

  const setPageIncludedAtStoredPosition = (
    pages: PageModel[],
    pageId: string,
    include: boolean,
  ): PageModel[] => {
    const target = pages.find((page) => page.id === pageId);
    if (!target) return pages;
    if (target.include === include) return pages;
    // Include is an export flag, not an ordering operation. Re-including a
    // page must keep the position the user chose while it was excluded.
    return pages.map((page) => (
      page.id === pageId
        ? { ...page, include, restorePackageIndex: undefined }
        : page
    ));
  };

  const toggleInclude = (id: string) =>
    mutatePages((pages) => {
      const target = pages.find((page) => page.id === id);
      if (target && (isCoverPage(target) || isSheetIndexPage(target))) return pages;
      return target ? setPageIncludedAtStoredPosition(pages, id, !target.include) : pages;
    });

  // S360 RAPID PAGE REVIEW V35
  const toggleIncludeAndAdvance = async () => {
    if (rapidReviewBusy) return;
    const activePageIdBeforeCapture = activePageRef.current?.id;
    const currentProject = captureActivePageState();
    const currentPage = currentProject?.pages.find((page) => page.id === activePageIdBeforeCapture);
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
    setSaveStatus('savingLocal');
    setSaveNotice('Saving page review…');
    await new Promise<void>((resolve) => window.setTimeout(resolve, 700));
    const saved = await confirmLatestProjectSaved(15000);
    if (!saved) {
      setSaveStatus('saveFailed');
      setSaveError('Page review save failed before the current project revision was confirmed.');
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
    const codeInput = window.prompt('Sheet code for the new drawing page:', suggestedCode);
    if (codeInput === null) return;
    const titleInput = window.prompt('Drawing page title:', worksheet.name);
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
      if (
        isCoverPage(pages[idx])
        || isSheetIndexPage(pages[idx])
        || isCoverPage(pages[t])
        || isSheetIndexPage(pages[t])
      ) return pages;
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
    if (!cur || isCoverPage(cur) || isSheetIndexPage(cur)) return;
    const v = window.prompt('Sheet title:', cur?.sheetTitle ?? '');
    if (v !== null) patchPage(id, { sheetTitle: v.trim() || 'Untitled Sheet' });
  };
  const editCodePrompt = (id: string) => {
    const cur = project?.pages.find((p) => p.id === id);
    if (!cur || isCoverPage(cur) || isSheetIndexPage(cur)) return;
    const v = window.prompt('Sheet code:', cur?.displaySheetCode || cur?.sheetCode || '');
    if (v !== null) patchPage(id, { sheetCode: v.trim(), displaySheetCode: v.trim() });
  };

  const openAddImportPage = async () => {
    const saved = await ensureSavedBeforeNavigation();
    if (saved) setPdfCropOpen(true);
  };

  const openProjectSettings = async () => {
    const saved = await ensureSavedBeforeNavigation();
    if (saved) setProjectSettingsOpen(true);
  };

  const saveProjectSettings = async (update: ProjectSettingsUpdate): Promise<boolean> => {
    captureActivePageState();
    const next = setProjectSync((latest) => {
      if (!latest) return latest;
      return {
        ...latest,
        projectMode: 'standalone_layout',
        projectDisplayName: update.projectDisplayName,
        coverSettings: {
          ...(latest.coverSettings || {}),
          managed: true,
          include: update.includeCover,
        },
        pages: latest.pages.map((page) => (
          page.managedPage === 'cover' || page.pageType === 'cover'
            ? { ...page, include: update.includeCover }
            : page
        )),
        metadata: {
          ...latest.metadata,
          ...update.metadata,
        },
      };
    });
    if (!next) return false;
    writeRecoverySnapshot(next);
    const saved = await confirmLatestProjectSaved(15_000);
    if (saved) setProjectSettingsOpen(false);
    return saved;
  };

  const openWorksheetImport = async (options: {
    afterPageId?: string;
    replacePageId?: string;
    replacePageTitle?: string;
  }) => {
    const saved = await ensureSavedBeforeNavigation();
    if (saved) setImportWsOpen(options);
  };

  const waitForEditorPaint = async () => {
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
  };

  const openSavePageTemplate = async (pageId: string) => {
    const target = projectRef.current?.pages.find((page) => page.id === pageId);
    if (!target || isCoverPage(target) || isSheetIndexPage(target)) return;
    if (activePageRef.current?.id !== pageId) {
      await switchPageSafely(pageId);
      await waitForEditorPaint();
      if (activePageRef.current?.id !== pageId) return;
    }
    const saved = await captureAndSave();
    if (!saved) {
      window.alert('Save failed. The page template was not opened so its drawing content cannot be stale.');
      return;
    }
    setSaveTemplateOpen(true);
  };

  const openInsertPageTemplate = async (pageId: string) => {
    const target = projectRef.current?.pages.find((page) => page.id === pageId);
    if (!target) return;
    if (activePageRef.current?.id !== pageId) {
      await switchPageSafely(pageId);
      await waitForEditorPaint();
      if (activePageRef.current?.id !== pageId) return;
    } else if (!await ensureSavedBeforeNavigation()) {
      return;
    }
    setTemplateLibManageOnly(false);
    setTemplateLibOpen(true);
  };

  // Build the shared page-action menu for a page id (tab + left list reuse it).
  const buildPageActions = (id: string) => {
    const pg = project?.pages.find((p) => p.id === id);
    const isCont = !!pg?.continuationOf || !!pg?.generatedContinuation;
    const managed = !!pg && (isCoverPage(pg) || isSheetIndexPage(pg));
    const actions: Array<{
      label: string;
      onClick: () => void;
      disabled?: boolean;
      divider?: boolean;
    }> = [
      { label: 'Rename Sheet Title', disabled: managed, onClick: () => renamePagePrompt(id) },
      { label: 'Edit Sheet Code', disabled: managed, onClick: () => editCodePrompt(id) },
      { label: 'Duplicate Sheet', divider: true, disabled: managed, onClick: () => duplicatePage(id) },
      { label: 'Add Blank Sheet Before', disabled: managed, onClick: () => addPage(id, 'before') },
      { label: 'Add Blank Sheet After', disabled: managed, onClick: () => addPage(id, 'after') },
      { label: 'Import Worksheet from Excel', onClick: () => { void openWorksheetImport({ afterPageId: id }); } },
      { label: 'Save Page as Template', disabled: managed, onClick: () => { void openSavePageTemplate(id); } },
      { label: 'Insert Page Template', onClick: () => { void openInsertPageTemplate(id); } },
      { label: pg?.include ? 'Exclude Page' : 'Include Page', divider: true, disabled: managed, onClick: () => toggleInclude(id) },
      { label: 'Archive Page', disabled: managed, onClick: () => { void deletePage(id); } },
      { label: 'Move Left', divider: true, disabled: managed, onClick: () => movePage(id, -1) },
      { label: 'Move Right', disabled: managed, onClick: () => movePage(id, 1) },
    ];
    if (isCont) {
      actions.push(
        { label: 'Make Independent', divider: true, disabled: managed, onClick: () => makeIndependent(id) },
        { label: 'Merge Into Previous', disabled: managed, onClick: () => mergeContinuationIntoPrevious(id) },
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
        const now = new Date().toISOString();
        const copyId = newPageId();
        const code = nextLogicalSheetCode(pages, activePageId);
        const copy: PageModel = {
          ...structuredClone(tplPage),
          id: copyId,
          order: pages[idx].order + 0.5,
          pageGroupId: copyId,
          continuationOf: null,
          generatedContinuation: false,
          createdAt: now,
          modifiedAt: now,
          include: true,
          sheetCode: code,
          displaySheetCode: code,
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
    setSaveStatus('dirtyLocal');
  };

  const reapplyPagePagination = async (pageId: string) => {
    const authoritative = captureActivePageState();
    const pg = authoritative?.pages.find((page) => page.id === pageId);
    if (!authoritative || !pg?.linkedWorksheetId || pg.renderMode !== 'excel_exact') return;
    if (!await confirmLatestProjectSaved(15_000)) {
      window.alert('Save failed. Pagination was not rebuilt, so the latest annotations remain unchanged.');
      return;
    }
    let snapshotName: string;
    try {
      const backup = await savePageRebuildBackup(authoritative.id, pageId, pg);
      snapshotName = backup.name;
    } catch (error) {
      window.alert(`Could not create the required pre-pagination history snapshot. No layout was changed.\n\n${String(error)}`);
      return;
    }
    pageRebuildHistoryRef.current.pushBeforeRebuild(pg, snapshotName);
    setPageRebuildTick((count) => count + 1);
    const next: ProjectModel = {
      ...authoritative,
      pages: regenerateExcelGroup(authoritative, pg.linkedWorksheetId),
      paginationLocked: true,
    };
    setProjectSync(next);
    writeRecoverySnapshot(next);
    if (!await confirmLatestProjectSaved(15_000)) {
      projectRef.current = authoritative;
      setProject(authoritative);
      writeRecoverySnapshot(authoritative);
      window.alert('Pagination save failed. The captured pre-pagination project was restored.');
    }
  };

  const applyExcelLayout = async (
    pageId: string,
    layoutOverride: 'exact_source' | 'two_columns' | 'keep_one_page',
  ) => {
    const captured = captureActivePageState();
    if (!captured) return;
    const saved = await confirmLatestProjectSaved(15_000);
    if (!saved) {
      window.alert('Save failed. The imported worksheet layout was not rebuilt.');
      return;
    }
    const requestProject = projectRef.current;
    if (!requestProject) return;
    layoutRebuildBusyRef.current = true;
    setLayoutRebuildBusy(true);
    setSaveNotice('Rebuilding imported worksheet layout…');
    try {
      const result = await autoLayoutImportedPage(requestProject.id, pageId, layoutOverride);
      const rebuilt = normalizeProjectAssetUrls(result.project);
      const latest = captureActivePageState();
      if (!latest) throw new Error('The active project closed before the layout rebuild completed.');
      const merged = reconcileLayoutRebuildResult(
        latest,
        rebuilt,
        pageId,
        result.pageIds ?? [],
      );
      const baseline = establishSavedBaseline(rebuilt);
      const applied = setProjectSync(merged) ?? merged;
      if (JSON.stringify(applied) !== JSON.stringify(baseline)) {
        writeRecoverySnapshot(applied);
        if (!await confirmLatestProjectSaved(15_000)) {
          setSaveNotice('LAYOUT REBUILD SAVE FAILED');
          window.alert('The layout was rebuilt, but newer editor changes could not be confirmed. They remain open and recoverable; retry Save Project.');
          return;
        }
      }
      setActivePageId(pageId);
      setSaveNotice('Imported worksheet layout saved');
    } catch (error) {
      setSaveError(String(error));
      setSaveNotice('LAYOUT REBUILD FAILED');
    } finally {
      layoutRebuildBusyRef.current = false;
      setLayoutRebuildBusy(false);
    }
  };

  const openProjectById = async (id: string) => {
    try {
      const ok = await ensureSavedBeforeNavigation();
      if (!ok) return;
      const p = await getProject(id);
      setProjectLoadError('');
      resetSourceEditState();
      establishSavedBaseline(p);
      const firstPage = p.pages?.[0];
    setActivePageId(firstPage?.id ?? null);
    setSelectedWorksheetId(firstPage?.linkedWorksheetId ?? p.worksheets?.[0]?.id);
      setSelection(null);
      window.history.replaceState({}, '', `?project=${id}`);
    } catch (err) {
      console.warn('open project failed', err);
      setProjectLoadError(String(err));
    } finally {
      setOpenProjectOpen(false);
    }
  };

  const openProjectHome = async () => {
    if (projectRef.current) {
      const ok = await ensureSavedBeforeNavigation();
      if (!ok) return;
    }
    window.location.assign('/app');
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
      resetSourceEditState();
      establishSavedBaseline(p);
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

  // Server restores are already persisted. Browser-local recovery snapshots
  // must be posted and read back before they can become a saved baseline.
  const applyRestoredProject = async (
    p: ProjectModel,
    source: 'server' | 'local',
  ): Promise<boolean> => {
    resetSourceEditState();
    const restored = normalizeProjectAssetUrls(p);
    if (source === 'local') {
      projectRef.current = restored;
      setProject(restored);
      setSaveStatus('dirtyLocal');
      writeRecoverySnapshot(restored);
      const confirmed = await confirmLatestProjectSaved(15_000);
      if (!confirmed) return false;
    } else {
      establishSavedBaseline(restored);
    }
    const current = projectRef.current ?? restored;
    const firstPage = current.pages?.[0];
    setActivePageId(firstPage?.id ?? activePageId);
    setSelectedWorksheetId(firstPage?.linkedWorksheetId ?? current.worksheets?.[0]?.id);
    setSelection(null);
    setSaveStatus(confirmedProjectSaveState(current));
    setBackupOpen(false);
    return true;
  };

  const onArchiveCurrentProject = async () => {
    if (!project) return;
    const name = project.projectDisplayName || (project.metadata as Record<string, string>)?.projectName || project.id;
    if (!window.confirm(`Archive project "${name}"?\n\nIt will move out of Active Projects but remain fully recoverable. Nothing is permanently deleted.`)) return;
    try {
      const saved = await ensureSavedBeforeNavigation();
      if (!saved) return;
      const res = await archiveProject(project.id);
      window.alert(`Project archived and available under Archived Projects.\n\nPackage retained at:\n${res.archivedTo}`);
      window.location.assign('/app');
    } catch (err) {
      window.alert(`Archive failed: ${String(err)}`);
    }
  };

  const onUploadCsv = async (file: File) => {
    if (!project) return false;
    try {
      const saved = await ensureSavedBeforeNavigation();
      if (!saved) return false;
      setSaveStatus('savingLocal');
      await attachCsv(project.id, file);
      const p = await getProject(project.id);
      establishSavedBaseline(p);
      return true;
    } catch (err) {
      console.error('CSV attach failed', err);
      setSaveStatus('saveFailed');
      setSaveError(String(err));
      return false;
    }
  };

  const onExportPdfSized = async (width: number, height: number, rev: { updateRevision: boolean; newRevision: string; notes: string }, pageIds: string[]) => {
    const captured = captureActivePageState();
    if (!captured) return;
    setExportOpen(false);
    // Optionally stamp a new revision into the title block + revision history.
    if (rev.updateRevision) {
      const today = new Date().toISOString().slice(0, 10);
      setProjectSync((latest) => latest ? {
        ...latest,
        revisionHistory: [...(latest.revisionHistory ?? []), {
          revision: rev.newRevision,
          date: today,
          description: rev.notes || 'Issued',
          exportedBy: 'Singh360',
        }],
        metadata: { ...latest.metadata, revision: rev.newRevision, issueDate: today },
      } : latest);
    }
    // Confirm the captured latest project (including an optional functional
    // revision patch) before deriving warnings, filename, or export content.
    const ok = await confirmLatestProjectSaved(15_000);
    if (!ok) return;
    const proj = projectRef.current;
    if (!proj) return;
    const base = proj.metadata.drawingPackageFileName || proj.projectDisplayName || proj.metadata.projectName || proj.id;
    const revSuffix = rev.updateRevision ? `_${rev.newRevision.replace(/\s+/g, '')}` : '';
    const downloadName = `${base}${revSuffix}.pdf`;
    try {
      const warnings = await fetchExportWarnings(proj.id, pageIds);
      if (warnings.length > 0) {
        pendingExportRef.current = {
          width,
          height,
          revisionSuffix: revSuffix,
          pageIds,
        };
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
      if (!await captureAndSave()) return;
      const latest = projectRef.current;
      if (!latest) return;
      const refreshedWarnings = await fetchExportWarnings(latest.id, pending.pageIds);
      if (
        refreshedWarnings.length > 0
        && JSON.stringify(refreshedWarnings) !== JSON.stringify(exportWarnings ?? [])
      ) {
        setExportWarnings(refreshedWarnings);
        window.alert('The saved project changed while export warnings were open. Review and confirm the updated warning list.');
        return;
      }
      const blob = await exportPdf(latest.id, {
        width: pending.width,
        height: pending.height,
        pageIds: pending.pageIds,
        confirmPreflight: true,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const base = latest.metadata.drawingPackageFileName
        || latest.projectDisplayName
        || latest.metadata.projectName
        || latest.id;
      a.download = `${base}${pending.revisionSuffix}.pdf`;
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
      const warnings = await fetchExportWarnings(project.id);
      if (warnings.length) {
        const summary = warnings
          .slice(0, 12)
          .map((warning) => `${warning.pageCode || 'Project'}: ${warning.issue}`)
          .join('\n');
        const suffix = warnings.length > 12 ? `\n…plus ${warnings.length - 12} more issue(s).` : '';
        if (!window.confirm(
          `Package preflight found ${warnings.length} issue(s):\n\n${summary}${suffix}\n\n`
          + 'Cancel to correct them, or OK to explicitly confirm and export the package.',
        )) return;
      }
      const blob = await exportPackage(project.id, warnings.length > 0);
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
      setSaveStatus('savingLocal');
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
      setSaveStatus(confirmedProjectSaveState(projectRef.current));
    } catch (err) {
      console.error('rename failed', err);
      setSaveStatus('saveFailed');
      setSaveError(String(err));
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
    !!activePage && viewMode === 'normalized' && !annotationsOpen;

  const sourceStatusLabel = (() => {
    if (!activePage?.linkedWorksheetId) return '';
    if (viewMode === 'source') {
      if (sourceCanUndo) return 'Undo available';
      if (sourceEditStatus === 'edited' || sourceDirty) return 'Imported table edited';
      return '';
    }
    if (rebuildValidationModal) return 'Imported-table rebuild failed validation — current drawing kept';
    if (sourceEditStatus === 'updated') return 'Drawing updated';
    if (sourceDirty) return 'Imported table edited';
    return '';
  })();

  const ribbon = (
    <Ribbon
      saveStatus={saveStatus}
      savedAt={savedAt}
      dirtyDomains={dirtyDomains}
      saveError={saveError}
      onRetrySave={() => { void saveNow(); }}
      hasProject={!!project}
      view={view}
      canvasEnabled={canvasEnabled}
      viewMode={viewMode}
      sourceCanUndo={sourceCanUndo}
      sourceCanRedo={sourceCanRedo}
      activeTool={activeTool}
      onSetTool={(t) => {
        if (annotationsOpen) changeAnnotationsOpen(false);
        if (t !== 'select') setOverlayMode(true);
        setActiveTool(t);
      }}
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
        equalSpaceObjects: (d) => canvasApiRef.current?.equalSpaceObjects(d),
        centerInPanel: (d) => canvasApiRef.current?.centerInPanel(d),
        matchObjectSize: (w) => canvasApiRef.current?.matchObjectSize(w),
        addLegend: (ids) => { setOverlayMode(true); canvasApiRef.current?.addLegend(ids); },
        addSymbolLegend: (config: SymbolLegendInsertConfig) => { setOverlayMode(true); canvasApiRef.current?.addSymbolLegend(config); },
        normalizeSymbolSize: () => canvasApiRef.current?.normalizeSymbolSize(),
        cropImage: openSelectedImageCrop,
        fitImageToPage: () => placeSelectedImageOnPage('fit'),
        fillImageToPage: () => placeSelectedImageOnPage('fill'),
        addBus: () => setBusOpen(true),
      }}
      onUploadCsv={(f) => void onUploadCsv(f)}
      onInsertImage={(f) => void onDropImageFile(f)}
      onInsertPdfPage={() => { void openAddImportPage(); }}
      onInsertSpreadsheetTable={() => {
        if (!activePageId) return;
        patchPage(activePageId, {
          excelLayout: activePage?.excelLayout || {
            version: 1,
            pageWidth: 1632,
            pageHeight: 1056,
            printableMargin: 48,
            snapSize: 8,
            tabColor: '#F4B183',
            tables: [],
          },
        });
        window.setTimeout(() => window.alert('Paste Excel or Google Sheets cells now. They will be inserted as one movable editable table.'), 0);
      }}
      onSaveNow={() => void saveNow()}
      onProjectSettings={() => { void openProjectSettings(); }}
      onOpenBackups={() => setBackupOpen(true)}
      onExportPdf={() => setExportOpen(true)}
      onExportPackage={() => void onExportPackage()}
      onRenumber={onRenumber}
      renumberBadge={renumberBadge}
      onOpenProject={() => setOpenProjectOpen(true)}
      onOpenHome={() => { void openProjectHome(); }}
      onCleanWorkspace={() => setCleanWorkspaceOpen(true)}
      onImportWorksheet={() => { void openWorksheetImport({
        afterPageId: activePageId ?? undefined,
        replacePageId: activePageId ?? undefined,
        replacePageTitle: activePage?.sheetTitle,
      }); }}
      canSavePageTemplate={!!activePage && !isCoverPage(activePage) && !isSheetIndexPage(activePage)}
      onSavePageTemplate={() => { if (activePageId) void openSavePageTemplate(activePageId); }}
      onInsertPageTemplate={() => { if (activePageId) void openInsertPageTemplate(activePageId); }}
      onManagePageTemplates={() => { setTemplateLibManageOnly(true); setTemplateLibOpen(true); }}
      onInsertSymbolLegend={() => setSymbolLegendOpen(true)}
      onOpenSymbolMapper={() => setSymbolMapperOpen(true)}
      onSaveSelectionAssembly={saveSelectionAsAssembly}
      onArchiveCurrentProject={() => void onArchiveCurrentProject()}
      theme={theme}
      onSetTheme={setThemeState}
      selection={selection}
      onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
      onSetLineStyle={(style) => setLineStyle(style)}
      pageFilter={pageFilter}
      onSetPageFilter={setPageFilter}
      annotationsOpen={annotationsOpen}
      onToggleAnnotations={() => changeAnnotationsOpen(!annotationsOpen)}
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

  if (!printMode && project && (appView === 'files' || appView === 'sources')) {
    return <ProjectFilesPage project={project} />;
  }

  if (!printMode && project && appView === 'data') {
    return <Suspense fallback={<div className="data-workspace-loading">Loading Data Workspace…</div>}>
      <DataWorkspace project={project} />
    </Suspense>;
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
              <h2>{projectLoadError ? 'Project could not be loaded' : 'No drawing project open'}</h2>
              <p>{projectLoadError || <>Return to Project Home to create a drawing set, or <button className="link-btn" onClick={() => setOpenProjectOpen(true)}>open an active project</button>.</>}</p>
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
          <CollapsibleSection title="Pages" hint="Drawing pages. Drag to reorder; right-click to duplicate, rename, include, or archive.">
            <button type="button" className="pages-add-import" onClick={() => { void openAddImportPage(); }}>+ Add / Import Page</button>
            <SheetManager pages={project.pages} activePageId={activePageId} onSelect={(id) => { void switchPageSafely(id); }} onUpdate={(p) => void updatePages(p)} onToggleInclude={toggleInclude} onContextMenu={(id, x, y) => setPageMenu({ x, y, pageId: id })} />
          </CollapsibleSection>
          {(project.archivedPages?.length ?? 0) > 0 && (
            <CollapsibleSection title={`Archived Pages (${project.archivedPages?.length ?? 0})`} defaultOpen={false} hint="Recoverable pages removed from the active drawing set.">
              <div className="archived-page-list">
                {(project.archivedPages ?? [])
                  .filter((page) => (
                    (!page.archivedGroupRootId || page.id === page.archivedGroupRootId)
                    && (!page.continuationOf || !(project.archivedPages ?? []).some((candidate) => candidate.id === page.continuationOf))
                  ))
                  .map((page) => {
                    const groupRoot = page.archivedGroupRootId || page.id;
                    const groupSize = (project.archivedPages ?? []).filter((candidate) => (
                      candidate.archivedGroupRootId === groupRoot
                      || candidate.id === groupRoot
                      || candidate.continuationOf === groupRoot
                    )).length;
                    return (
                  <div key={page.id} className="archived-page-item">
                    <span className="archived-page-summary">
                      <span><b>{page.displaySheetCode || page.sheetCode}</b> {page.sheetTitle}</span>
                      {groupSize > 1 ? <small>Includes {groupSize - 1} continuation page{groupSize === 2 ? '' : 's'}</small> : null}
                      <small>{page.archivedAt ? new Date(page.archivedAt).toLocaleString() : 'Archive time unavailable'} · {page.archivedReason || 'No archive reason recorded'}</small>
                    </span>
                    <button type="button" onClick={() => { void restoreArchivedPage(page.id); }}>Restore</button>
                  </div>
                    );
                  })}
              </div>
            </CollapsibleSection>
          )}
          <CollapsibleSection title="Components" defaultOpen={false} hint="Search reusable devices and drag them onto the active drawing page.">
            <LibraryPanelV2
              onInsert={onInsertComponent}
              canInsert={canvasEnabled}
              activePageType={activePage?.pageType}
              onOpenLegendEditor={() => setSymbolLegendOpen(true)}
              onOpenSymbolMapper={() => setSymbolMapperOpen(true)}
              savedAssemblies={project.savedAssemblies}
              onInsertSavedAssembly={insertSavedAssembly}
              onSaveSelectionAssembly={saveSelectionAsAssembly}
              onInsertQuickAssembly={insertQuickAssembly}
              onInsertSmartComponent={openSmartComponent}
              onInsertSingleCallout={insertSingleCallout}
              onCreateCalloutSet={openCalloutBuilder}
              onUpdateSavedAssembly={updateSavedAssembly}
              onDuplicateSavedAssembly={duplicateSavedAssembly}
              onDeleteSavedAssembly={deleteSavedAssembly}
            />
          </CollapsibleSection>
        </>
      }
      center={
        <DocumentView
          project={project}
          pages={project.pages}
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
          onAfterSetDrawingArea={handleAfterSetDrawingArea}
          onOpenDataWorkspace={() => window.location.assign(`/workspace?project=${project.id}`)}
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
          onReorderPages={(pages) => void updatePages(pages)}
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
              const timestamp = new Date().toISOString();
              const pages = prev.pages.map((pg) => (
                pg.id === pageId
                  ? stampPageIfChanged(pg, { ...pg, canvasObjects: objects }, timestamp)
                  : pg
              ));
              return {
                ...prev,
                pages,
              };
            });
          }}
          annotationsOpen={annotationsOpen}
          annotationTool={annotationTool}
          annotationStyle={annotationStyle}
          annotationSelection={annotationSelection}
          annotationApi={annotationApi}
          onAnnotationsOpenChange={changeAnnotationsOpen}
          onAnnotationToolChange={setAnnotationTool}
          onAnnotationStyleChange={setAnnotationStyle}
          onAnnotationSelectionChange={onAnnotationSelectionChange}
          onRegisterAnnotationApi={onRegisterAnnotationApi}
          onAnnotationChange={onAnnotationChange}
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
          </div>
          <PropertiesPanel
            page={activePage}
            onChange={(patch) => patchPage(activePage.id, patch)}
            selection={selection}
            onUpdateSelection={(patch) => canvasApiRef.current?.updateSelected(patch)}
            onConnectorConvert={(kind) => canvasApiRef.current?.convertSelectedConnector(kind)}
            onConnectorAddVertex={() => canvasApiRef.current?.addVertexToSelected()}
            onConnectorDeleteVertex={() => canvasApiRef.current?.deleteVertexFromSelected()}
            onConnectorReverse={() => canvasApiRef.current?.reverseConnectorDirection()}
            onEditSmartComponent={editSelectedSmartComponent}
            onExplodeSmartComponent={() => canvasApiRef.current?.ungroup()}
            onEditCallout={editSelectedCallout}
            onEditPlacedSymbol={editPlacedSelection}
            projectDisplayName={project.projectDisplayName ?? project.metadata.projectName}
            projectFolder={project.projectFolder}
            onRenameProject={(name) => void onRenameProject(name)}
            overflowWarning={Array.isArray(activePage.layoutWarnings) && activePage.layoutWarnings.length > 0}
            onMergeIntoPrevious={activePage.continuationOf && !isSheetIndexPage(activePage) ? () => mergeContinuationIntoPrevious(activePage.id) : undefined}
            onMakeIndependent={activePage.continuationOf && !isSheetIndexPage(activePage) ? () => makeIndependent(activePage.id) : undefined}
            onReapplyPagination={
              activePage.renderMode === 'excel_exact' && !activePage.continuationOf
                ? () => reapplyPagePagination(activePage.id)
                : undefined
            }
            onApplyExcelLayout={(layout) => { void applyExcelLayout(activePage.id, layout); }}
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
    {layoutRebuildBusy && (
      <div className="modal-backdrop" role="presentation">
        <section className="modal" role="dialog" aria-modal="true" aria-labelledby="layout-rebuild-title" aria-busy="true">
          <div className="modal-head"><h2 id="layout-rebuild-title">Rebuilding Imported Worksheet Layout</h2></div>
          <div className="modal-body" role="status" aria-live="polite">
            <p>The latest project state is locked while Singh360 rebuilds and verifies this page.</p>
            <progress aria-label="Imported worksheet layout rebuild in progress" />
          </div>
        </section>
      </div>
    )}
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
    {addSheetPending && (
      <AddSheetModal
        suggestedCode={nextLogicalSheetCode(project.pages, addSheetPending.refId)}
        onAdd={(title, code, tmpl) => addSheetFromModal(title, code, tmpl, addSheetPending.refId, addSheetPending.where)}
        onCancel={() => setAddSheetPending(null)}
      />
    )}
    {exportOpen && (
      <ExportModal
        currentRevision={project.metadata.revision || ''}
        packageName={project.metadata.drawingPackageFileName || project.projectDisplayName || project.metadata.projectName || ''}
        pages={project.pages}
        onExport={(w, h, rev, pageIds) => void onExportPdfSized(w, h, rev, pageIds)}
        onCancel={() => setExportOpen(false)}
      />
    )}
    {projectSettingsOpen && project && (
      <ProjectSettingsModal
        project={project}
        onCancel={() => setProjectSettingsOpen(false)}
        onSave={saveProjectSettings}
      />
    )}
    {exportWarnings && (
      <ExportWarningsModal
        key={JSON.stringify(exportWarnings)}
        warnings={exportWarnings}
        onClose={() => {
          pendingExportRef.current = null;
          setExportWarnings(null);
        }}
        onExportAnyway={onExportPdfDespiteWarnings}
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
        initialFileUrl={initialTool === 'project-pdf' && initialProjectFileId
          ? `/api/projects/${project.id}/project-files/${initialProjectFileId}/content`
          : undefined}
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
    {smartComponentEditor && (
      <SmartComponentModal
        key={`${smartComponentEditor.mode}:${smartComponentEditor.config.kind}`}
        initialConfig={smartComponentEditor.config}
        mode={smartComponentEditor.mode}
        onApply={(config) => {
          setOverlayMode(true);
          if (smartComponentEditor.mode === 'edit') {
            canvasApiRef.current?.updateSelectedSmartComponent(config);
          } else {
            canvasApiRef.current?.addSmartComponent(config);
          }
          setSmartComponentEditor(null);
        }}
        onCancel={() => setSmartComponentEditor(null)}
      />
    )}
    {calloutEditor && (
      <CalloutEditorModal
        key={`${calloutEditor.mode}:${calloutEditor.config.family}:${activePage.id}:${calloutEditor.config.setName}`}
        initialConfig={calloutEditor.config}
        mode={calloutEditor.mode}
        projectId={project.id}
        pageId={activePage.id}
        onApply={(config, action) => {
          setOverlayMode(true);
          if (calloutEditor.mode === 'edit' && action === 'update') {
            canvasApiRef.current?.updateSelectedCalloutSet(config);
          } else {
            canvasApiRef.current?.addCalloutSet(config);
          }
          setCalloutEditor(null);
        }}
        onCancel={() => setCalloutEditor(null)}
      />
    )}
    {placedSymbolEditor && (
      <PlacedSymbolEditorModal
        initialConfig={placedSymbolEditor}
        sourceUrl={selection?.sourceUrl}
        onApply={(config) => {
          canvasApiRef.current?.updateSelectedPlacedSymbol(config);
          if (selection?.libraryComponentId && config.favorite !== selection.favorite) {
            void updateLibV2Component(selection.libraryComponentId, { favorite: config.favorite })
              .then(() => window.dispatchEvent(new CustomEvent('singh360:library-changed')))
              .catch((error) => window.alert(`Could not update the library favorite: ${String(error)}`));
          }
          setPlacedSymbolEditor(null);
        }}
        onCancel={() => setPlacedSymbolEditor(null)}
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
      <AddImportPageModal
        project={project}
        onClose={() => setPdfCropOpen(false)}
        onProjectImported={async (updated, pageIds) => {
          try {
            const latest = captureActivePageState();
            if (!latest) return false;
            const imported = normalizeProjectAssetUrls(updated);
            const merged = reconcilePdfImportResult(latest, imported, pageIds);
            const baseline = establishSavedBaseline(imported);
            const applied = setProjectSync(merged) ?? merged;
            if (
              JSON.stringify(applied) !== JSON.stringify(baseline)
              && !await confirmLatestProjectSaved(15_000)
            ) {
              return false;
            }
            setActivePageId(pageIds[0] ?? applied.pages[0]?.id ?? null);
            return true;
          } catch (error) {
            setSaveStatus('saveFailed');
            setSaveError(String(error));
            return false;
          }
        }}
        onBlank={(title, code) => {
          const reference = activePageId || project.pages[project.pages.length - 1]?.id;
          if (reference) addSheetFromModal(title, code, 'canvas', reference, 'after');
          setPdfCropOpen(false);
        }}
        onText={(title, code) => {
          const reference = activePageId || project.pages[project.pages.length - 1]?.id;
          if (reference) addSheetFromModal(title, code, 'data-grid', reference, 'after');
          setPdfCropOpen(false);
        }}
        onImage={createImagePageFromFile}
        onTable={() => {
          setPdfCropOpen(false);
          setImportWsOpen({ afterPageId: activePageId ?? undefined });
        }}
        onCsv={(file) => onUploadCsv(file)}
        onTemplate={() => {
          setPdfCropOpen(false);
          setTemplateLibManageOnly(false);
          setTemplateLibOpen(true);
        }}
      />
    )}
    {backupOpen && (
      <BackupRecoveryModal
        projectId={project.id}
        beforeRestore={ensureSavedBeforeNavigation}
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
          { label: selection?.calloutConfig?.family === 'block' ? 'Edit Callout Block' : 'Edit', disabled: !selection, onClick: editPlacedSelection, hint: 'Open the active editor for this symbol, smart component, or callout' },
          { label: 'Rename', disabled: !selection, onClick: renamePlacedSelection },
          { label: 'Duplicate', disabled: !selection, onClick: () => canvasApiRef.current?.duplicateSelected() },
          { label: 'Delete', disabled: !selection, onClick: () => canvasApiRef.current?.deleteSelected() },
          { label: 'Move to Category', disabled: !selection, onClick: movePlacedSelectionToCategory },
          { label: selection?.favorite ? 'Remove from Favorites' : 'Add to Favorites', disabled: !selection, onClick: togglePlacedSelectionFavorite },
          { label: 'Save as Assembly', disabled: !selection, onClick: saveSelectionAsAssembly },
          { label: 'Paste Image (Ctrl+V)', onClick: () => void pasteImageFromClipboard(), hint: 'Paste a screenshot from the clipboard' },
          { label: 'Insert Text Box', divider: true, onClick: () => { setOverlayMode(true); canvasApiRef.current?.addText(); } },
          { label: 'Insert Arrow', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addArrow(); } },
          { label: 'Insert Line', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addLine(); } },
          { label: 'Insert Polyline', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addPolyline(); } },
          { label: 'Insert Elbow Connector', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addElbow(); } },
          { label: 'Insert Connector Legend', onClick: () => { setOverlayMode(true); canvasApiRef.current?.addLegend(); } },
          { label: 'Insert Symbol Legend', onClick: () => setSymbolLegendOpen(true) },
          { label: 'Import Worksheet from Excel', divider: true, onClick: () => { void openWorksheetImport({ afterPageId: activePageId ?? undefined }); } },
          { label: 'Add Blank Sheet After', onClick: () => activePageId && addPage(activePageId, 'after') },
          { label: 'Duplicate Current Sheet', onClick: () => activePageId && duplicatePage(activePageId) },
          { label: 'Copy', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.copySelected() },
          { label: 'Paste', onClick: () => canvasApiRef.current?.pasteCopied() },
          { label: 'Normalize Symbol Size', divider: true, disabled: !selection, onClick: () => canvasApiRef.current?.normalizeSymbolSize() },
          { label: 'Crop / Fit Selected Image', divider: true, disabled: !selection?.isImage, onClick: openSelectedImageCrop, hint: 'Choose the visible crop and optionally fit/fill the drawing area' },
          { label: 'Fit Selected Image to Page', disabled: !selection?.isImage, onClick: () => placeSelectedImageOnPage('fit') },
          { label: 'Fill Page with Selected Image', disabled: !selection?.isImage, onClick: () => placeSelectedImageOnPage('fill') },
          { label: 'Group Selected Objects', disabled: !selection, onClick: () => canvasApiRef.current?.group() },
          { label: selection?.isLegend ? 'Edit Legend / Marker' : 'Edit Group (Ungroup)', disabled: !selection?.isGroup, onClick: () => canvasApiRef.current?.ungroup(), hint: 'Break the grouped marker into editable text, symbols, and lines' },
          { label: 'Edit Smart Component', disabled: !selection?.smartComponentType, onClick: editSelectedSmartComponent, hint: 'Change the selected smart component parameters and regenerate its editable vector parts' },
          { label: 'Explode Smart Component', disabled: !selection?.smartComponentType, onClick: () => canvasApiRef.current?.ungroup(), hint: 'Break the smart component into independent editable shapes and labels' },
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
