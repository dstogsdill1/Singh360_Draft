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
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
  onDuplicateBlock: (pageId: string, blockId: string) => void;
  onWorksheetChange: (worksheetId: string, patch: Partial<Worksheet>, opts?: { structural?: boolean }) => void;
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
  onPatchPage,
  onDuplicateBlock,
  onWorksheetChange,
  onCanvasChange,
}: Props) {
  if (viewMode === 'source') {
    return (
      <RawGridRenderer
        worksheet={worksheet}
        onWorksheetChange={(patch, opts) => {
          if (!page.linkedWorksheetId) return;
          onWorksheetChange(page.linkedWorksheetId, patch, opts);
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
      onPatchPage={onPatchPage}
      onDuplicateBlock={onDuplicateBlock}
      onCanvasChange={onCanvasChange}
    />
  );
}
