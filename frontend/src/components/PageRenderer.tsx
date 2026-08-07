import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, ViewMode, Worksheet } from '../model/types';
import NormalizedPage from './renderers/NormalizedPage';
import RawGridRenderer from './renderers/RawGridRenderer';
import ExcelLayoutCanvas from './ExcelLayoutCanvas';
import SpreadsheetPageCanvas from './SpreadsheetPageCanvas';
import PageLocalSpreadsheet from './PageLocalSpreadsheet';
import PageLocalDrawingRenderer from './PageLocalDrawingRenderer';
import CanvasEditor from './CanvasEditor';

/** True when the page should use the page-local spreadsheet render path. */
function isPageLocal(page: PageModel): boolean {
  return page.renderMode === 'page_local_spreadsheet';
}

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
  onAfterSetDrawingArea?: () => void;
  onOpenDataWorkspace?: () => void;
  onDuplicateSpreadsheetPage?: () => void;
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
  onAfterSetDrawingArea,
  onOpenDataWorkspace,
  onDuplicateSpreadsheetPage,
}: Props) {
  const printPreviewMode = viewMode === 'print';
  const effectiveExporting = Boolean(exporting || printPreviewMode);

  // 'spreadsheet' mode: the page-local Univer editor — never RawGridRenderer.
  if (viewMode === 'spreadsheet' && worksheet) {
    return (
      <PageLocalSpreadsheet
        page={page}
        worksheet={worksheet}
        onWorksheetChange={onWorksheetChange}
        onPatchPage={onPatchPage}
        onAfterSetDrawingArea={onAfterSetDrawingArea}
        onOpenDataWorkspace={onOpenDataWorkspace}
        onDuplicateSpreadsheetPage={onDuplicateSpreadsheetPage}
      />
    );
  }
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

  // Drawing / export: page-local path takes ABSOLUTE PRIORITY over all legacy
  // renderers (excelLayout, spreadsheetRegions, blocks, NormalizedPage).
  // This prevents ExcelLayoutCanvas and stale blocks from overriding WYSIWYG.
  if (isPageLocal(page) && worksheet) {
    return (
      <PageLocalDrawingRenderer
        page={page}
        worksheet={worksheet}
        project={project}
        activeTool={activeTool}
        snap={snap}
        overlayMode={overlayMode}
        exporting={effectiveExporting}
        onRegisterApi={onRegisterApi}
        onSelectionChange={onSelectionChange}
        onCanvasChange={onCanvasChange}
        onToolConsumed={onToolConsumed}
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
        exporting={effectiveExporting}
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
          exporting={effectiveExporting}
        />
      </div>
      {page.excelLayout && <ExcelLayoutCanvas page={page} onPatchPage={onPatchPage} exporting={effectiveExporting} overlay />}
    </div>;
  }
  if (page.excelLayout) {
    return <ExcelLayoutCanvas page={page} onPatchPage={onPatchPage} exporting={effectiveExporting} />;
  }

  return (
    <NormalizedPage
      page={page}
      project={project}
      worksheet={worksheet}
      activeTool={activeTool}
      snap={snap}
      overlayMode={overlayMode}
      exporting={effectiveExporting}
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
