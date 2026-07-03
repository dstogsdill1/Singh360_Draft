import type { CanvasApi, CanvasSelection, PageModel } from '../../model/types';
import CanvasEditor from '../CanvasEditor';

interface Props {
  page: PageModel;
  activeTool: string;
  snap: boolean;
  onToolConsumed: () => void;
  onRegisterApi: (api: CanvasApi | null) => void;
  onSelectionChange: (sel: CanvasSelection | null) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

/** Canvas/diagram page — a clean Fabric surface. Tools live in the ribbon. */
export default function CanvasPageRenderer({
  page,
  activeTool,
  snap,
  onToolConsumed,
  onRegisterApi,
  onSelectionChange,
  onCanvasChange,
}: Props) {
  const empty = !(page.canvasObjects && page.canvasObjects.length);
  return (
    <div className="np-canvas">
      {empty && (
        <div className="np-canvas-hint">
          Empty canvas — use the Insert or Draw ribbon tabs to add text, shapes, lines, and arrows.
        </div>
      )}
      <CanvasEditor
        serialized={page.canvasObjects || []}
        onSerializedChange={(o) => onCanvasChange(page.id, o)}
        registerApi={onRegisterApi}
        onSelectionChange={onSelectionChange}
        activeTool={activeTool}
        onToolConsumed={onToolConsumed}
        snap={snap}
      />
    </div>
  );
}
