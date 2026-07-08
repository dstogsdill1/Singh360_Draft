import { useEffect, useRef, useState } from 'react';
import type {
  CanvasApi,
  CanvasSelection,
  PageBlock,
  PageModel,
  ProjectModel,
  ViewMode,
  Worksheet,
} from '../model/types';
import PageRenderer from './PageRenderer';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';
import PageTabs from './PageTabs';
import ViewportToolbar from './ViewportToolbar';
import { COMPONENT_DRAG_TYPE } from './ComponentLibrary';
import type { ViewControls } from './Ribbon';

export type FitMode = 'width' | 'page' | 'actual';

export const SHEET_W = 1632;
export const SHEET_H = 1056;
export const MIN_SCALE = 0.25;
export const MAX_SCALE = 2;
const VIEWPORT_PAD = 24;

const clampScale = (v: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, v));

interface Props {
  project: ProjectModel;
  pages: PageModel[];
  activePage: PageModel;
  worksheets: Worksheet[];
  view: ViewControls;
  actualZoom: number;
  viewMode: ViewMode;
  sourceDirty?: boolean;
  onViewModeChange: (mode: ViewMode) => void;
  onRefreshFromSource?: () => void;
  activeTool: string;
  snap: boolean;
  overlayMode: boolean;
  onToolConsumed: () => void;
  onRegisterApi: (api: CanvasApi | null) => void;
  onSelectionChange: (sel: CanvasSelection | null) => void;
  onBlockChange: (pageId: string, blockId: string, patch: Partial<PageBlock>) => void;
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
  onDuplicateBlock: (pageId: string, blockId: string) => void;
  onSelectPage: (id: string) => void;
  onReorderPages: (pages: PageModel[]) => void;
  onRenamePageTitle: (id: string, title: string) => void;
  onPageContextMenu: (id: string, x: number, y: number) => void;
  onDropImageFile: (file: File) => void;
  onDropComponent: (url: string, name: string, label: string | null, clientX: number, clientY: number) => void;
  onScaleChange: (scale: number) => void;
  onWorksheetChange: (worksheetId: string, patch: Partial<Worksheet>, opts?: { structural?: boolean }) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

export default function DocumentView({
  project,
  pages,
  activePage,
  worksheets,
  view,
  actualZoom,
  viewMode,
  sourceDirty,
  onViewModeChange,
  onRefreshFromSource,
  activeTool,
  snap,
  overlayMode,
  onToolConsumed,
  onRegisterApi,
  onSelectionChange,
  onBlockChange,
  onPatchPage,
  onDuplicateBlock,
  onSelectPage,
  onReorderPages,
  onRenamePageTitle,
  onPageContextMenu,
  onDropImageFile,
  onDropComponent,
  onScaleChange,
  onWorksheetChange,
  onCanvasChange,
}: Props) {
  const worksheet = worksheets.find((w) => w.id === activePage.linkedWorksheetId);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const scaleRef = useRef<HTMLDivElement | null>(null);
  const [fitScale, setFitScale] = useState(0.5);

  // Recompute fit scale from the actual viewport size (excludes ribbon/tabs/panels).
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;

    const compute = () => {
      const vw = el.clientWidth - VIEWPORT_PAD * 2;
      const vh = el.clientHeight - VIEWPORT_PAD * 2;
      if (vw <= 0 || vh <= 0) return;
      if (view.fitMode === 'width') {
        setFitScale(clampScale(vw / SHEET_W));
      } else if (view.fitMode === 'page') {
        setFitScale(clampScale(Math.min(vw / SHEET_W, vh / SHEET_H)));
      }
    };

    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    // Backup: also recompute on window resize (covers panel collapse/expand
    // and window changes so the sheet never drifts out of frame).
    window.addEventListener('resize', compute);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', compute);
    };
  }, [view.fitMode]);

  const scale = view.fitMode === 'actual' ? clampScale(actualZoom) : fitScale;

  // Report the effective scale up for the zoom indicators.
  useEffect(() => {
    onScaleChange(scale);
  }, [scale, onScaleChange]);

  useEffect(() => {
    if (stageRef.current) {
      stageRef.current.style.width = `${SHEET_W * scale}px`;
      stageRef.current.style.height = `${SHEET_H * scale}px`;
    }
    if (scaleRef.current) {
      scaleRef.current.style.width = `${SHEET_W}px`;
      scaleRef.current.style.height = `${SHEET_H}px`;
      scaleRef.current.style.transform = `scale(${scale})`;
    }
  }, [scale]);

  // Reset scroll to top-left when fitting the whole page.
  useEffect(() => {
    const el = viewportRef.current;
    if (el && view.fitMode === 'page') {
      el.scrollTop = 0;
      el.scrollLeft = 0;
    }
  }, [view.fitMode, scale]);

  return (
    <>
      <PageTabs pages={pages} activePageId={activePage.id} onSelect={onSelectPage} onReorder={onReorderPages} onRenameTitle={onRenamePageTitle} onContextMenu={onPageContextMenu} />
      <ViewportToolbar
        activePage={activePage}
        view={view}
        viewMode={viewMode}
        sourceDirty={sourceDirty}
        onViewModeChange={onViewModeChange}
        onRefreshFromSource={onRefreshFromSource}
      />
      <div
        className="sheet-viewport"
        ref={viewportRef}
        onDragOver={(e) => {
          const types = e.dataTransfer?.types;
          if (types?.includes('Files') || types?.includes(COMPONENT_DRAG_TYPE)) e.preventDefault();
        }}
        onDrop={(e) => {
          const payload = e.dataTransfer?.getData(COMPONENT_DRAG_TYPE);
          if (payload) {
            e.preventDefault();
            try {
              const { url, name, label } = JSON.parse(payload) as { url: string; name: string; label: string | null };
              onDropComponent(url, name, label ?? null, e.clientX, e.clientY);
            } catch {
              /* ignore malformed payload */
            }
            return;
          }
          const file = e.dataTransfer?.files?.[0];
          if (file && file.type.startsWith('image/')) {
            e.preventDefault();
            onDropImageFile(file);
          }
        }}
      >
        <div className="sheet-stage" ref={stageRef}>
          <div
            className={`sheet-scale ${view.showGrid ? 'show-grid' : ''}`}
            ref={scaleRef}
          >
            <SheetFrame titleBlock={<TitleBlock project={project} page={activePage} />} sourceView={viewMode === 'source'}>
              <PageRenderer
                key={`${activePage.id}-${activePage.sourceRevision ?? 0}-${viewMode}`}
                page={activePage}
                worksheet={worksheet}
                project={project}
                viewMode={viewMode}
                activeTool={activeTool}
                snap={snap}
                overlayMode={overlayMode}
                onToolConsumed={onToolConsumed}
                onRegisterApi={onRegisterApi}
                onSelectionChange={onSelectionChange}
                onBlockChange={onBlockChange}
                onPatchPage={onPatchPage}
                onDuplicateBlock={onDuplicateBlock}
                onWorksheetChange={onWorksheetChange}
                onCanvasChange={onCanvasChange}
              />
            </SheetFrame>
          </div>
        </div>
      </div>
    </>
  );
}
