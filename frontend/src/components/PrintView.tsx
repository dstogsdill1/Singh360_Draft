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
    // Mark ready on the next frame after paint so the exporter can wait for it.
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.body.setAttribute('data-print-ready', '1');
      });
    });
    return () => cancelAnimationFrame(raf);
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
