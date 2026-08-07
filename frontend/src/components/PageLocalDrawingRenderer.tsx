/**
 * S360 PAGE-LOCAL DRAWING RENDERER V1
 *
 * The single WYSIWYG spreadsheet renderer used for Drawing view, Print
 * Preview, and PDF export of page-local spreadsheet pages.  There is one
 * code path — what you see in Drawing is exactly what exports.
 *
 * Input: the page's linkedWorksheetId worksheet + drawingRange/placement.
 * Output: a scaled/positioned read-only spreadsheet block covering the
 *   page body, with the canvas overlay rendered on top.
 */
import { useMemo } from 'react';
import type { CanvasApi, CanvasSelection, PageModel, ProjectModel, Worksheet } from '../model/types';
import type { SpreadsheetRegion } from '../model/types';
import ExcelRangeRenderer from './renderers/ExcelRangeRenderer';
import CanvasEditor from './CanvasEditor';
import { spreadsheetRegionBlock, regionScale } from '../model/spreadsheetRegion';
import { letters } from '../workspace/UniverWorkbookAdapter';
import { rangeBounds } from '../workspace/workspaceContract';
import {
  BODY_W,
  BODY_H,
  BODY_LEFT,
  BODY_TOP,
} from '../model/sheetGeometry';

interface Props {
  page: PageModel;
  worksheet: Worksheet;
  project: ProjectModel;
  activeTool?: string;
  snap?: boolean;
  overlayMode?: boolean;
  exporting?: boolean;
  onRegisterApi?: (api: CanvasApi | null) => void;
  onSelectionChange?: (sel: CanvasSelection | null) => void;
  onCanvasChange?: (pageId: string, objects: Record<string, unknown>[]) => void;
  onToolConsumed?: () => void;
}

/** Derive a sensible default range covering the populated content of a worksheet. */
function defaultRange(ws: Worksheet): string {
  const rows = ws.grid?.length || 1;
  const cols = Math.max(1, ...(ws.grid || []).map((r) => r?.length || 0));
  return `A1:${letters(cols - 1)}${rows}`;
}

/** Build a SpreadsheetRegion that fills the page body with fit_box scaling. */
function buildPageBodyRegion(page: PageModel, ws: Worksheet): SpreadsheetRegion {
  const range = page.drawingRange || defaultRange(ws);
  const placement = page.pageLocalPlacement;
  return {
    id: `${page.id}_local_drawing`,
    sourceSheetId: ws.id,
    range,
    pageId: page.id,
    x: BODY_LEFT,
    y: BODY_TOP,
    width: BODY_W,
    height: BODY_H,
    fitMode: placement?.fitMode ?? 'fit_box',
    overflowMode: 'clip',
    repeatRows: [],
    explicitBreaks: [],
    preserveGeometry: true,
    scale: placement?.scale ?? 1,
  };
}

// S360 PAGE-LOCAL DRAWING RENDERER V1
export default function PageLocalDrawingRenderer({
  page,
  worksheet,
  project,
  activeTool = 'select',
  snap = false,
  overlayMode = false,
  exporting = false,
  onRegisterApi,
  onSelectionChange,
  onCanvasChange,
  onToolConsumed = () => undefined,
}: Props) {
  void project; // available for future canvas operations

  const region = useMemo(() => buildPageBodyRegion(page, worksheet), [page, worksheet]);
  const block = useMemo(() => spreadsheetRegionBlock(worksheet, region), [worksheet, region]);

  const overlayInteractive = !exporting && (overlayMode || activeTool !== 'select' || (page.canvasObjects?.length || 0) > 0);

  if (!block) {
    return (
      <div className="pldr-empty" data-testid="page-local-drawing-empty">
        No worksheet data for range {region.range}.
      </div>
    );
  }

  const scale = regionScale(region, block);

  return (
    <div className="pldr-root np-page-root" data-testid="page-local-drawing-renderer" data-page-id={page.id} data-worksheet-id={worksheet.id} data-range={region.range}>
      {/* Spreadsheet content — exact same renderer used by PDF export */}
      <div
        className="pldr-content"
        style={{
          position: 'absolute',
          left: region.x,
          top: region.y,
          width: region.width,
          height: region.height,
          overflow: 'hidden',
        }}
      >
        <ExcelRangeRenderer block={block} scaleOverride={scale} embedded exporting={exporting} />
      </div>
      {/* Canvas overlays (notes, callouts, components, etc.) */}
      <div className={`np-overlay-layer ${overlayInteractive ? 'active' : ''}`}>
        <CanvasEditor
          key={page.id}
          serialized={page.canvasObjects || []}
          onSerializedChange={onCanvasChange ? (objects) => onCanvasChange(page.id, objects) : () => undefined}
          registerApi={onRegisterApi ?? (() => undefined)}
          onSelectionChange={onSelectionChange ?? (() => undefined)}
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
