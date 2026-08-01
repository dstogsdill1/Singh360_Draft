import { useEffect, useRef } from 'react';
import type { ProjectModel } from '../model/types';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';
import PageRenderer from './PageRenderer';
import { pdfPointsToPixels } from '../model/workbookGeometry';
import { SHEET_H, SHEET_W } from '../model/sheetGeometry';

interface Props {
  project: ProjectModel | null;
}

const noop = () => {};

function paperFromUrl(): { wPx: number; hPx: number; scale: number } {
  const params = new URLSearchParams(window.location.search);
  const pw = parseFloat(params.get('pw') || '17');
  const ph = parseFloat(params.get('ph') || '11');
  const wPx = pdfPointsToPixels((Number.isFinite(pw) ? pw : 17) * 72);
  const hPx = pdfPointsToPixels((Number.isFinite(ph) ? ph : 11) * 72);
  // Fit the fixed-design 17x11 sheet onto the chosen paper, preserving aspect.
  const scale = Math.min(wPx / SHEET_W, hPx / SHEET_H);
  return { wPx, hPx, scale };
}

function PrintPageShell({ pageId, wPx, hPx, scale, children }: { pageId: string; wPx: number; hPx: number; scale: number; children: React.ReactNode }) {
  const pageRef = useRef<HTMLDivElement | null>(null);
  const fitRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (pageRef.current) {
      pageRef.current.style.width = `${wPx}px`;
      pageRef.current.style.height = `${hPx}px`;
    }
    if (fitRef.current) {
      fitRef.current.style.width = `${SHEET_W}px`;
      fitRef.current.style.height = `${SHEET_H}px`;
      fitRef.current.style.transform = `scale(${scale})`;
    }
  }, [wPx, hPx, scale]);
  return (
    <div className="print-page" key={pageId} ref={pageRef}>
      <div className="print-sheet-fit" ref={fitRef}>
        {/* S360 EXPORT PAGE IDENTITY V1 - invisible text retained in the PDF so post-processing maps vectors to the correct physical page. */}
        <span className="s360-export-page-id" aria-hidden="true">{`S360PID_${pageId}`}</span>
        {children}
      </div>
    </div>
  );
}

/**
 * Print renderer used by the Playwright PDF export at:
 *   /app?project=<id>&print=1
 *
 * It reuses the exact SheetFrame / TitleBlock / PageRenderer components so the
 * exported PDF matches the on-screen editor. When every included page has been
 * committed to the DOM it sets document.body[data-print-ready="1"] so the
 * backend export can wait for a deterministic ready signal.
 */
export default function PrintView({ project }: Props) {
  const includedPages = (project?.pages.filter((p) => p.include) ?? [])
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  useEffect(() => {
    if (!project) return;
    document.body.removeAttribute('data-print-ready');
    document.body.removeAttribute('data-print-error');
    let cancelled = false;
    let timer: number | undefined;

    const afterPaint = () => new Promise<void>((resolve) => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    });
    const checkReady = async () => {
      try {
        await document.fonts?.ready;
        const deadline = Date.now() + 20_000;
        while (!cancelled && Date.now() < deadline) {
          const shells = [...document.querySelectorAll<HTMLElement>('.print-page')];
          const images = [...document.images];
          const canvases = [...document.querySelectorAll<HTMLElement>('.canvas-wrap')];
          const shellsReady = shells.length === includedPages.length;
          const imagesReady = images.every((image) => image.complete && (!image.src || image.naturalWidth > 0));
          const canvasesReady = canvases.every((canvas) => canvas.dataset.canvasHydrated === '1');
          if (shellsReady && imagesReady && canvasesReady) {
            await afterPaint();
            if (!cancelled) document.body.setAttribute('data-print-ready', '1');
            return;
          }
          await new Promise<void>((resolve) => {
            timer = window.setTimeout(resolve, 50);
          });
        }
        if (!cancelled) document.body.setAttribute('data-print-error', 'Timed out waiting for fonts, images, or drawing canvases.');
      } catch (error) {
        if (!cancelled) document.body.setAttribute('data-print-error', error instanceof Error ? error.message : String(error));
      }
    };
    void checkReady();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [project, includedPages.length]);

  if (!project) {
    return <div className="print-root" />;
  }

  const { wPx, hPx, scale } = paperFromUrl();

  return (
    <div className="print-root">
      {includedPages.map((page) => {
        const worksheet = project.worksheets.find((w) => w.id === page.linkedWorksheetId);
        return (
          <PrintPageShell pageId={page.id} key={page.id} wPx={wPx} hPx={hPx} scale={scale}>
              <SheetFrame
                titleBlock={<TitleBlock project={project} page={page} />}
                fullSheet={page.pdfPlacementMode === 'full_sheet' || page.suppressTitleBlock}
                fullSheetPageLabel={page.pageNumber ? `Page ${page.pageNumber} of ${page.pageTotal ?? includedPages.length}` : ''}
              >
                <PageRenderer
                  page={page}
                  worksheet={worksheet}
                  project={project}
                  viewMode="normalized"
                  activeTool="select"
                  snap={false}
                  overlayMode={false}
                  exporting
                  onToolConsumed={noop}
                  onRegisterApi={noop}
                  onSelectionChange={noop}
                  onBlockChange={noop}
                  onPatchPage={noop}
                  onDuplicateBlock={noop}
                  onWorksheetChange={noop}
                  onCanvasChange={noop}
                />
              </SheetFrame>
          </PrintPageShell>
        );
      })}
    </div>
  );
}
