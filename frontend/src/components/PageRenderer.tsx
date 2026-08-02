import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, ViewMode, Worksheet } from '../model/types';
import NormalizedPage from './renderers/NormalizedPage';
import RawGridRenderer from './renderers/RawGridRenderer';
import ExcelLayoutCanvas from './ExcelLayoutCanvas';
import SpreadsheetPageCanvas from './SpreadsheetPageCanvas';
import CanvasEditor from './CanvasEditor';

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
  onWorksheetChange: (worksheetId: string, patch: Partial<Worksheet>, opts?: { structural?: boolean; skipHistory?: boolean }) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
  onReplacePageSource?: () => void;
  onExportPageSource?: () => void;
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
  onReplacePageSource,
  onExportPageSource,
}: Props) {
  if (viewMode === 'source') {
    return (
      <RawGridRenderer
        worksheet={worksheet}
        onWorksheetChange={(patch, opts) => {
          if (!worksheet?.id) return;
          onWorksheetChange(worksheet.id, patch, opts);
        }}
        onReplaceSource={onReplacePageSource}
        onExportSource={onExportPageSource}
      />
    );
  }
  if (page.spreadsheetRegions?.length) {
    const overlayInteractive = overlayMode || activeTool !== 'select' || (page.canvasObjects?.length || 0) > 0;
    return <div className="np-page-root">
      <SpreadsheetPageCanvas
        pageId={page.id}
        regions={page.spreadsheetRegions}
        project={project}
        readOnly
        exporting={exporting}
      />
      <div className={`np-overlay-layer ${overlayInteractive ? 'active' : ''}`}>
        <CanvasEditor
          key={page.id}
          serialized={page.canvasObjects || []}
          onSerializedChange={(objects) => onCanvasChange(page.id, objects)}
          registerApi={onRegisterApi}
          onSelectionChange={onSelectionChange}
          activeTool={activeTool}
          onToolConsumed={onToolConsumed}
          snap={snap}
          overlayMode={overlayMode}
          exporting={exporting}
        />
      </div>
      {page.excelLayout && <ExcelLayoutCanvas page={page} onPatchPage={onPatchPage} exporting={exporting} overlay />}
    </div>;
  }
  if (page.excelLayout) {
    return <ExcelLayoutCanvas page={page} onPatchPage={onPatchPage} exporting={exporting} />;
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

// S360 WORKSPACE UX V10
