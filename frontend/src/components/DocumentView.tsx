import { useEffect, useRef, useState } from 'react';
import type { PageModel, ProjectModel, Worksheet } from '../model/types';
import PageRenderer from './PageRenderer';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';

export type FitMode = 'width' | 'page' | 'actual';

const SHEET_W = 1632;
const SHEET_H = 1056;

interface Props {
  project: ProjectModel;
  activePage: PageModel;
  worksheets: Worksheet[];
  fitMode: FitMode;
  onFitModeChange: (mode: FitMode) => void;
  onGridChange: (worksheetId: string, grid: string[][]) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

export default function DocumentView({
  project,
  activePage,
  worksheets,
  fitMode,
  onFitModeChange,
  onGridChange,
  onCanvasChange,
}: Props) {
  const worksheet = worksheets.find((w) => w.id === activePage.linkedWorksheetId);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const compute = () => {
      if (fitMode === 'actual') {
        setScale(1);
        return;
      }
      const avail = el.clientWidth - 8;
      const widthScale = avail / SHEET_W;
      if (fitMode === 'width') {
        setScale(Math.min(1, widthScale));
      } else {
        const availH = el.clientHeight - 8;
        const heightScale = availH / SHEET_H;
        setScale(Math.min(1, widthScale, heightScale));
      }
    };

    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(el);
    return () => ro.disconnect();
  }, [fitMode]);

  const pageNumberLabel =
    activePage.pageNumber != null
      ? `Page ${activePage.pageNumber} of ${activePage.pageTotal ?? '—'}`
      : 'Not included';

  return (
    <div ref={wrapRef}>
      <div className="doc-toolbar">
        <div className="doc-active-label">
          <span className="doc-code">{activePage.sheetCode}</span>
          {activePage.sheetTitle}
        </div>
        <span className="doc-active-label">{pageNumberLabel}</span>
        <div className="doc-fit-controls">
          <button className={`fit-btn ${fitMode === 'width' ? 'active' : ''}`} onClick={() => onFitModeChange('width')}>Fit Width</button>
          <button className={`fit-btn ${fitMode === 'page' ? 'active' : ''}`} onClick={() => onFitModeChange('page')}>Fit Page</button>
          <button className={`fit-btn ${fitMode === 'actual' ? 'active' : ''}`} onClick={() => onFitModeChange('actual')}>100%</button>
        </div>
      </div>

      <div
        className="sheet-scale-wrap"
        style={{ width: SHEET_W * scale, height: SHEET_H * scale }}
      >
        <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left', width: SHEET_W, height: SHEET_H }}>
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
  );
}
