import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, Worksheet } from '../../model/types';
import TextPageRenderer from './TextPageRenderer';
import TablePageRenderer from './TablePageRenderer';
import MatrixPageRenderer from './MatrixPageRenderer';
import CoverPageRenderer from './CoverPageRenderer';
import ImagePlaceholderRenderer from './ImagePlaceholderRenderer';
import CanvasPageRenderer from './CanvasPageRenderer';

interface Props {
  page: PageModel;
  project: ProjectModel;
  worksheet?: Worksheet;
  activeTool: string;
  snap: boolean;
  onToolConsumed: () => void;
  onRegisterApi: (api: CanvasApi | null) => void;
  onSelectionChange: (sel: CanvasSelection | null) => void;
  onBlockChange: (pageId: string, blockId: string, patch: Partial<PageBlock>) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

/**
 * Normalized output page: renders the page's normalized blocks with the right
 * professional renderer per block type. Falls back to a raw-ish table when a
 * page has no blocks (older projects).
 */
export default function NormalizedPage({
  page,
  project,
  activeTool,
  snap,
  onToolConsumed,
  onRegisterApi,
  onSelectionChange,
  onBlockChange,
  onCanvasChange,
}: Props) {
  const blocks = page.blocks ?? [];

  const hasCanvasBlock = blocks.some((b) => b.type === 'canvas');
  if (hasCanvasBlock || page.pageType === 'canvas' || page.pageType === 'underlay' || page.pageType === 'hybrid') {
    return (
      <div className="np np-canvas-page">
        <CanvasPageRenderer
          page={page}
          activeTool={activeTool}
          snap={snap}
          onToolConsumed={onToolConsumed}
          onRegisterApi={onRegisterApi}
          onSelectionChange={onSelectionChange}
          onCanvasChange={onCanvasChange}
        />
        {blocks
          .filter((b) => b.type === 'imagePlaceholder')
          .map((b) => (
            <ImagePlaceholderRenderer key={b.id} block={b} />
          ))}
      </div>
    );
  }

  if (!blocks.length) {
    return <div className="np np-empty">No normalized content — switch to Source View to see the raw worksheet.</div>;
  }

  return (
    <div className="np">
      {blocks.map((b) => {
        const patch = (p: Partial<PageBlock>) => onBlockChange(page.id, b.id, p);
        switch (b.type) {
          case 'cover':
            return <CoverPageRenderer key={b.id} block={b} project={project} />;
          case 'table':
            return <TablePageRenderer key={b.id} block={b} onChange={patch} />;
          case 'matrix':
            return <MatrixPageRenderer key={b.id} block={b} onChange={patch} />;
          case 'imagePlaceholder':
          case 'underlayPlaceholder':
            return <ImagePlaceholderRenderer key={b.id} block={b} />;
          default:
            return <TextPageRenderer key={b.id} block={b} onChange={patch} />;
        }
      })}
    </div>
  );
}
