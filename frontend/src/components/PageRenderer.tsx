import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, ViewMode, Worksheet } from '../model/types';
import NormalizedPage from './renderers/NormalizedPage';
import RawGridRenderer from './renderers/RawGridRenderer';

interface Props {
  page: PageModel;
  worksheet?: Worksheet;
  project: ProjectModel;
  viewMode: ViewMode;
  activeTool: string;
  snap: boolean;
  overlayMode: boolean;
  exporting?: boolean;
  onToolConsumed: () => void;
  onRegisterApi: (api: CanvasApi | null) => void;
  onSelectionChange: (sel: CanvasSelection | null) => void;
  onBlockChange: (pageId: string, blockId: string, patch: Partial<PageBlock>) => void;
  onGridChange: (worksheetId: string, grid: string[][]) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

export default function PageRenderer({
  page,
  worksheet,
  project,
  viewMode,
  activeTool,
  snap,
  overlayMode,
  exporting,
  onToolConsumed,
  onRegisterApi,
  onSelectionChange,
  onBlockChange,
  onGridChange,
  onCanvasChange,
}: Props) {
  if (viewMode === 'source') {
    return (
      <RawGridRenderer
        worksheet={worksheet}
        onGridChange={(grid) => {
          if (!page.linkedWorksheetId) return;
          onGridChange(page.linkedWorksheetId, grid);
        }}
      />
    );
  }

  return (
    <NormalizedPage
      page={page}
      project={project}
      worksheet={worksheet}
      activeTool={activeTool}
      snap={snap}
      overlayMode={overlayMode}
      exporting={exporting}
      onToolConsumed={onToolConsumed}
      onRegisterApi={onRegisterApi}
      onSelectionChange={onSelectionChange}
      onBlockChange={onBlockChange}
      onCanvasChange={onCanvasChange}
    />
  );
}
