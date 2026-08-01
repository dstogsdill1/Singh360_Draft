import { useEffect, useMemo } from 'react';
import type { CanvasApi, CanvasSelection, PageBlock, PageModel, ProjectModel, Worksheet } from '../../model/types';
import { sanitizeCanvasObjectsForPage } from '../../model/canvasCleanup';
import { projectForWorksheetRender } from '../../model/sourceProjection';
import TextPageRenderer from './TextPageRenderer';
import TablePageRenderer from './TablePageRenderer';
import MatrixPageRenderer from './MatrixPageRenderer';
import ExcelRangeRenderer from './ExcelRangeRenderer';
import NetworkTwoUpRenderer from './NetworkTwoUpRenderer';
import CoverPageRenderer from './CoverPageRenderer';
import CompanyInfoRenderer from './CompanyInfoRenderer';
import ImagePlaceholderRenderer from './ImagePlaceholderRenderer';
import GeneratedIndexRenderer from './GeneratedIndexRenderer';
import SheetTitleBand from './SheetTitleBand';
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
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
  onDuplicateBlock: (pageId: string, blockId: string) => void;
  onCanvasChange: (pageId: string, objects: Record<string, unknown>[]) => void;
}

/**
 * Normalized output page. The worksheet is the geometry/style source of truth;
 * persisted normalized blocks are only a fallback/cache. Every page is composed
 * of a source-projected BASE layer and an editable OVERLAY canvas.
 */
export default function NormalizedPage({
  page,
  project,
  worksheet,
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
  onCanvasChange,
}: Props) {
  const projected = useMemo(
    () => projectForWorksheetRender(project, page, worksheet),
    [project, page, worksheet],
  );
  const renderPage = projected.page;
  const renderProject = projected.project;
  const persistedBlocks = renderPage.blocks ?? [];
  // A migrated managed cover may retain old workbook blocks for provenance and
  // rollback. Standalone rendering uses only its managed cover block so stale
  // workbook tables/text can never reappear beside current Project Settings.
  const blocks = renderProject.projectMode === 'standalone_layout' && renderPage.pageType === 'cover'
    ? persistedBlocks.filter((block) => block.type === 'cover').slice(0, 1)
    : persistedBlocks;
  const excelBlocks = blocks.filter((block) => block.type === 'excelRange');
  const isImageType = renderPage.pageType === 'canvas' || blocks.some((b) => b.type === 'canvas');
  const isIndexPage = renderPage.pageType === 'index';
  const indexUsesExcelExact = isIndexPage && renderPage.renderMode === 'excel_exact';
  const isCoverPage = renderPage.pageType === 'cover' || blocks.some((b) => b.type === 'cover');
  const headerStyle = (renderPage.normalizedHeaderStyle as string | undefined) ?? 'orange';
  const showBand = headerStyle === 'orange' && !isCoverPage;
  const bandReserve = showBand ? 64 : 0;

  const rawCanvasObjects = page.canvasObjects ?? [];
  const canvasObjects = useMemo(
    () => sanitizeCanvasObjectsForPage(renderPage, rawCanvasObjects),
    [renderPage.pageType, renderPage.sheetTitle, renderPage.sheetCode, renderPage.displaySheetCode, rawCanvasObjects],
  );

  // Persist the automatic cover cleanup as soon as that page is rendered. There
  // is intentionally no "clean workspace/artifacts" button for this defect.
  useEffect(() => {
    if (canvasObjects !== rawCanvasObjects) onCanvasChange(page.id, canvasObjects);
  }, [canvasObjects, rawCanvasObjects, onCanvasChange, page.id]);

  const hasOverlay = canvasObjects.length > 0;
  const baseTypes = ['table', 'matrix', 'excelRange', 'idfNetworkTable', 'title', 'subtitle', 'paragraph', 'bulletList', 'sectionHeading', 'note', 'cover', 'companyInfo'];
  const hasEditableBase = isIndexPage || (!isImageType && blocks.some((b) => baseTypes.includes(b.type)));
  const overlayInteractive = overlayMode || activeTool !== 'select' || (hasOverlay && !hasEditableBase);

  const base = (() => {
    if (isIndexPage && !indexUsesExcelExact) {
      return <GeneratedIndexRenderer project={renderProject} page={renderPage} onPatchPage={onPatchPage} />;
    }

    if (isIndexPage && indexUsesExcelExact) {
      const xr = blocks.find((b) => b.type === 'excelRange');
      if (xr) {
        return (
          <div className="np">
            <ExcelRangeRenderer block={xr} reservedTop={bandReserve} />
          </div>
        );
      }
    }

    if (isImageType) {
      const imgBlocks = blocks.filter((b) => b.type === 'imagePlaceholder' || b.type === 'underlayPlaceholder');
      if (imgBlocks.length) {
        return (
          <div className="np np-image-base">
            {imgBlocks.map((b) => <ImagePlaceholderRenderer key={b.id} block={b} />)}
          </div>
        );
      }
      if (hasOverlay) return <div className="np np-image-base" />;
      if (exporting) {
        const message = renderPage.blankPagePlaceholder || 'DRAWING TO BE INSERTED';
        return (
          <div className="np np-image-base">
            <div className="np-reserved-note">{message}</div>
          </div>
        );
      }
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
              return <CoverPageRenderer key={b.id} block={b} project={renderProject} />;
            case 'companyInfo':
              return <CompanyInfoRenderer key={b.id} block={b} project={renderProject} />;
            case 'excelRange':
              if (excelBlocks.length > 1) {
                if (b.id !== excelBlocks[0].id) return null;
                const rightNote = renderPage.tableAnnotations?.find((item) => item.placement === 'right');
                const bottomNote = renderPage.tableAnnotations?.find((item) => item.placement === 'bottom');
                return <section key="table-region-layout" className={`np-table-region-layout ${renderPage.tableLayout || 'side_by_side'}`}>
                  <div className="np-table-region-group">
                    {excelBlocks.map((block) => <ExcelRangeRenderer key={block.id} block={block} reservedTop={bandReserve} exporting={exporting} />)}
                  </div>
                  {rightNote?.text && <aside className="np-table-region-note right">{rightNote.text}</aside>}
                  {bottomNote?.text && <aside className="np-table-region-note bottom">{bottomNote.text}</aside>}
                </section>;
              }
              return <ExcelRangeRenderer key={b.id} block={b} reservedTop={bandReserve} exporting={exporting} />;
            case 'idfNetworkTable':
              return <NetworkTwoUpRenderer key={b.id} block={b} exporting={exporting} />;
            case 'table':
              return <TablePageRenderer key={b.id} block={b} onChange={patch} onDuplicateTable={() => onDuplicateBlock(page.id, b.id)} />;
            case 'matrix':
              return <MatrixPageRenderer key={b.id} block={b} onChange={patch} onDuplicateTable={() => onDuplicateBlock(page.id, b.id)} />;
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
      <div className={`np-base-layer ${overlayInteractive ? 'passthrough' : ''} ${showBand ? 'np-has-band' : ''}`}>
        {showBand && <SheetTitleBand page={renderPage} />}
        {base}
      </div>
      <div className={`np-overlay-layer ${overlayInteractive ? 'active' : ''}`}>
        <CanvasEditor
          key={page.id}
          serialized={canvasObjects}
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
    </div>
  );
}
