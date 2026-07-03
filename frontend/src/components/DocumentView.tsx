import { useEffect, useRef, useState } from 'react';
import type { PageModel, ProjectModel, Worksheet } from '../model/types';
import PageRenderer from './PageRenderer';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';
import PageTabs from './PageTabs';
import ViewportToolbar from './ViewportToolbar';
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
  onSelectPage: (id: string) => void;
  onScaleChange: (scale: number) => void;
  onGridChange: (worksheetId: string, grid: string[][]) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

export default function DocumentView({
  project,
  pages,
  activePage,
  worksheets,
  view,
  actualZoom,
  onSelectPage,
  onScaleChange,
  onGridChange,
  onCanvasChange,
}: Props) {
  const worksheet = worksheets.find((w) => w.id === activePage.linkedWorksheetId);
  const viewportRef = useRef<HTMLDivElement | null>(null);
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
    return () => ro.disconnect();
  }, [view.fitMode]);

  const scale = view.fitMode === 'actual' ? clampScale(actualZoom) : fitScale;

  // Report the effective scale up for the zoom indicators.
  useEffect(() => {
    onScaleChange(scale);
  }, [scale, onScaleChange]);

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
      <PageTabs pages={pages} activePageId={activePage.id} onSelect={onSelectPage} />
      <ViewportToolbar activePage={activePage} view={view} />
      <div className="sheet-viewport" ref={viewportRef}>
        <div className="sheet-stage" style={{ width: SHEET_W * scale, height: SHEET_H * scale }}>
          <div
            className={`sheet-scale ${view.showGrid ? 'show-grid' : ''}`}
            style={{ transform: `scale(${scale})`, width: SHEET_W, height: SHEET_H }}
          >
            <SheetFrame titleBlock={<TitleBlock project={project} page={activePage} />}>
              <PageRenderer
                page={activePage}
                worksheet={worksheet}
                project={project}
                onGridChange={onGridChange}
                onCanvasChange={onCanvasChange}
              />
            </SheetFrame>
          </div>
        </div>
      </div>
    </>
  );
}
