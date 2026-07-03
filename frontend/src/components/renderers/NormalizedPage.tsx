import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, Worksheet } from '../../model/types';
import TextPageRenderer from './TextPageRenderer';
import TablePageRenderer from './TablePageRenderer';
import MatrixPageRenderer from './MatrixPageRenderer';
import CoverPageRenderer from './CoverPageRenderer';
import ImagePlaceholderRenderer from './ImagePlaceholderRenderer';
import CanvasEditor from '../CanvasEditor';

interface Props {
  page: PageModel;
  project: ProjectModel;
  worksheet?: Worksheet;
  activeTool: string;
  snap: boolean;
  overlayMode: boolean;
  exporting?: boolean;
  onToolConsumed: () => void;
  onRegisterApi: (api: CanvasApi | null) => void;
  onSelectionChange: (sel: CanvasSelection | null) => void;
  onBlockChange: (pageId: string, blockId: string, patch: Partial<PageBlock>) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

/**
 * Normalized output page. Every page is composed of two layers:
 *  - a BASE layer (normalized blocks: cover / text / table / matrix / image), and
 *  - an editable OVERLAY canvas (screenshots, shapes, arrows, text boxes).
 *
 * The overlay exists on every page so users can paste/annotate anywhere. Pointer
 * events on the overlay are enabled only when overlay edit mode is on or a draw
 * tool is active, so base content (editable tables/text) stays clickable.
 */
export default function NormalizedPage({
  page,
  project,
  activeTool,
  snap,
  overlayMode,
  exporting,
  onToolConsumed,
  onRegisterApi,
  onSelectionChange,
  onBlockChange,
  onCanvasChange,
}: Props) {
  const blocks = page.blocks ?? [];
  const isImageType = page.pageType === 'canvas' || blocks.some((b) => b.type === 'canvas');
  const overlayInteractive = overlayMode || activeTool !== 'select';
  const hasOverlay = (page.canvasObjects?.length ?? 0) > 0;

  const base = (() => {
    if (isImageType) {
      const imgBlocks = blocks.filter((b) => b.type === 'imagePlaceholder' || b.type === 'underlayPlaceholder');
      if (imgBlocks.length) {
        return (
          <div className="np np-image-base">
            {imgBlocks.map((b) => <ImagePlaceholderRenderer key={b.id} block={b} />)}
          </div>
        );
      }
      // No base image block. If an overlay image/PDF is present, or we're
      // exporting, render nothing (the overlay shows through, no placeholder).
      if (exporting || hasOverlay) {
        return <div className="np np-image-base" />;
      }
      // Editor-only drop zone hint (never exported).
      return (
        <div className="np np-image-base">
          <div className="np-dropzone" data-noexport="1">
            <div className="np-dropzone-icon">▧</div>
            <div className="np-dropzone-text">Drop image, PDF, or screenshot here</div>
            <div className="np-dropzone-sub">or use Insert ▸ Image, paste (Ctrl+V), or drag a Component</div>
          </div>
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
  })();

  return (
    <div className="np-page-root">
      <div className={`np-base-layer ${overlayInteractive ? 'passthrough' : ''}`}>
        {base}
      </div>
      <div className={`np-overlay-layer ${overlayInteractive ? 'active' : ''}`}>
        <CanvasEditor
          key={page.id}
          serialized={page.canvasObjects || []}
          onSerializedChange={(o) => onCanvasChange(page.id, o)}
          registerApi={onRegisterApi}
          onSelectionChange={onSelectionChange}
          activeTool={activeTool}
          onToolConsumed={onToolConsumed}
          snap={snap}
          overlayMode={overlayMode}
        />
      </div>
    </div>
  );
}
