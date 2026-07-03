import { useEffect } from 'react';
import type { ProjectModel } from '../model/types';
import SheetFrame from './SheetFrame';
import TitleBlock from './TitleBlock';
import PageRenderer from './PageRenderer';

interface Props {
  project: ProjectModel | null;
}

const noop = () => {};

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
  const includedPages = project?.pages.filter((p) => p.include) ?? [];

  useEffect(() => {
    if (!project) return;
    // Mark ready after paint AND a short settle delay so async Fabric overlay
    // images (pasted screenshots / embedded workbook images) finish loading
    // before the PDF exporter captures the page.
    let timer: number | undefined;
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        timer = window.setTimeout(() => {
          document.body.setAttribute('data-print-ready', '1');
        }, 600);
      });
    });
    return () => {
      cancelAnimationFrame(raf);
      if (timer) window.clearTimeout(timer);
    };
  }, [project, includedPages.length]);

  if (!project) {
    return <div className="print-root" />;
  }

  return (
    <div className="print-root">
      {includedPages.map((page) => {
        const worksheet = project.worksheets.find((w) => w.id === page.linkedWorksheetId);
        return (
          <div className="print-page" key={page.id}>
            <SheetFrame titleBlock={<TitleBlock project={project} page={page} />}>
              <PageRenderer
                page={page}
                worksheet={worksheet}
                project={project}
                viewMode="normalized"
                activeTool="select"
                snap={false}
                overlayMode={false}
                onToolConsumed={noop}
                onRegisterApi={noop}
                onSelectionChange={noop}
                onBlockChange={noop}
                onGridChange={noop}
                onCanvasChange={noop}
              />
            </SheetFrame>
          </div>
        );
      })}
    </div>
  );
}
