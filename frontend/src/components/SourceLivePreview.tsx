import { useEffect, useMemo, useRef, useState } from 'react';
import type { PageModel, ProjectModel, Worksheet } from '../model/types';
import { rebuildSinglePageFromSource } from '../model/pageRebuild';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';
import NormalizedPage from './renderers/NormalizedPage';

const SHEET_W = 1632;
const SHEET_H = 1056;

interface Props {
  page: PageModel;
  project: ProjectModel;
  worksheet?: Worksheet;
  onClose: () => void;
}

export default function SourceLivePreview({ page, project, worksheet, onClose }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [scale, setScale] = useState(0.34);

  const previewPage = useMemo(() => {
    if (!worksheet) return page;
    try {
      return rebuildSinglePageFromSource(page, worksheet);
    } catch (error) {
      console.error('live source preview failed', error);
      return page;
    }
  }, [page, worksheet]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const compute = () => {
      const width = Math.max(260, host.clientWidth - 20);
      const height = Math.max(220, host.clientHeight - 48);
      setScale(Math.max(0.18, Math.min(0.55, width / SHEET_W, height / SHEET_H)));
    };
    compute();
    const observer = new ResizeObserver(compute);
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  return (
    <aside className="gx-live-preview" ref={hostRef}>
      <div className="gx-live-preview-head">
        <span>
          <strong>Live Page Preview</strong>
          <small>Uses the same normalized/PDF layout engine</small>
        </span>
        <button type="button" className="gx-btn" onClick={onClose}>Hide</button>
      </div>
      <div className="gx-live-preview-scroll">
        <div
          className="gx-live-preview-stage"
          style={{ width: SHEET_W * scale, height: SHEET_H * scale }}
        >
          <div
            className="gx-live-preview-sheet"
            style={{ width: SHEET_W, height: SHEET_H, transform: `scale(${scale})` }}
          >
            <SheetFrame
              titleBlock={<TitleBlock project={project} page={previewPage} />}
              sourceView={false}
            >
              <NormalizedPage
                page={previewPage}
                project={project}
                worksheet={worksheet}
                activeTool="select"
                snap={false}
                overlayMode={false}
                exporting={false}
                previewOnly
                onToolConsumed={() => undefined}
                onRegisterApi={() => undefined}
                onSelectionChange={() => undefined}
                onBlockChange={() => undefined}
                onPatchPage={() => undefined}
                onDuplicateBlock={() => undefined}
                onCanvasChange={() => undefined}
              />
            </SheetFrame>
          </div>
        </div>
      </div>
    </aside>
  );
}
