/**
 * S360 PAGE-LOCAL DRAWING RENDERER V2
 *
 * One renderer is used by Drawing, Print Preview, and PDF export.
 * The saved worksheet range is rendered below the standard Singh360 title band
 * and above the title block with one uniform scale.
 */
import { useMemo } from 'react';
import type {
  CanvasApi,
  CanvasSelection,
  PageModel,
  ProjectModel,
  SpreadsheetRegion,
  Worksheet,
} from '../model/types';
import ExcelRangeRenderer from './renderers/ExcelRangeRenderer';
import SheetTitleBand from './renderers/SheetTitleBand';
import CanvasEditor from './CanvasEditor';
import { spreadsheetRegionBlock, regionScale } from '../model/spreadsheetRegion';
import { letters } from '../workspace/UniverWorkbookAdapter';
import { rangeBounds } from '../workspace/workspaceContract';
import {
  PAGE_CONTENT_H,
  PAGE_CONTENT_LEFT,
  PAGE_CONTENT_TOP,
  PAGE_CONTENT_W,
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

function populatedRange(ws: Worksheet): string | null {
  let lastRow = -1;
  let lastColumn = -1;
  (ws.grid || []).forEach((row, rowIndex) => {
    row.forEach((value, columnIndex) => {
      if (String(value ?? '').trim() === '') return;
      lastRow = Math.max(lastRow, rowIndex);
      lastColumn = Math.max(lastColumn, columnIndex);
    });
  });
  if (lastRow < 0 || lastColumn < 0) return null;
  return `A1:${letters(lastColumn)}${lastRow + 1}`;
}

function selectedRange(page: PageModel, ws: Worksheet): string | null {
  const explicit = String(page.drawingRange || '').trim();
  return explicit || populatedRange(ws);
}

function buildPageBodyRegion(
  page: PageModel,
  ws: Worksheet,
  range: string,
): SpreadsheetRegion {
  const placement = page.pageLocalPlacement;
  return {
    id: `${page.id}_local_drawing`,
    sourceSheetId: ws.id,
    range,
    pageId: page.id,
    x: PAGE_CONTENT_LEFT,
    y: PAGE_CONTENT_TOP,
    width: PAGE_CONTENT_W,
    height: PAGE_CONTENT_H,
    fitMode: placement?.fitMode ?? 'fit_box',
    overflowMode: 'clip',
    repeatRows: [],
    explicitBreaks: [],
    preserveGeometry: true,
    scale: placement?.scale ?? 1,
  };
}

function normalizeWorksheetForDrawing(page: PageModel, ws: Worksheet): Worksheet {
  const excludedRows = new Set(page.drawingExcludedRows || []);
  const excludedColumns = new Set(page.drawingExcludedColumns || []);
  const masked = page.drawingMaskedRanges || [];
  const clone: Worksheet = {
    ...ws,
    grid: (ws.grid || []).map((row) => [...row]),
    hiddenRows: [...new Set([...(ws.hiddenRows || []), ...excludedRows])].sort((a, b) => a - b),
    hiddenColumns: [...new Set([...(ws.hiddenColumns || []), ...excludedColumns])].sort((a, b) => a - b),
  };
  for (const item of masked) {
    const bounds = rangeBounds(item.range);
    if (!bounds) continue;
    for (let rowIndex = bounds.startRow; rowIndex <= bounds.endRow; rowIndex += 1) {
      const row = clone.grid[rowIndex];
      if (!row) continue;
      for (
        let columnIndex = bounds.startColumn;
        columnIndex <= bounds.endColumn;
        columnIndex += 1
      ) {
        if (columnIndex < row.length) row[columnIndex] = '';
      }
    }
  }
  return clone;
}

function blockHasVisibleContent(
  block: ReturnType<typeof spreadsheetRegionBlock>,
): boolean {
  return Boolean(block?.grid?.some((row) => (
    row.some((value) => String(value ?? '').trim() !== '')
  )));
}

// S360 PAGE-LOCAL DRAWING RENDERER V2
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
  void project;

  const resolvedWorksheet = useMemo(
    () => normalizeWorksheetForDrawing(page, worksheet),
    [page, worksheet],
  );
  const range = useMemo(
    () => selectedRange(page, resolvedWorksheet),
    [page, resolvedWorksheet],
  );
  const region = useMemo(
    () => (range ? buildPageBodyRegion(page, resolvedWorksheet, range) : null),
    [page, range, resolvedWorksheet],
  );
  const block = useMemo(
    () => (region ? spreadsheetRegionBlock(resolvedWorksheet, region) : null),
    [region, resolvedWorksheet],
  );

  const overlayInteractive = !exporting && (
    overlayMode
    || activeTool !== 'select'
    || (page.canvasObjects?.length || 0) > 0
  );

  const scale = region && block ? regionScale(region, block) : 1;
  const hasContent = blockHasVisibleContent(block);
  const hAlign = page.pageLocalPlacement?.hAlign ?? 'center';
  const vAlign = page.pageLocalPlacement?.vAlign ?? 'top';
  const justifyContent = hAlign === 'left'
    ? 'flex-start'
    : hAlign === 'right'
      ? 'flex-end'
      : 'center';
  const alignItems = vAlign === 'top'
    ? 'flex-start'
    : vAlign === 'bottom'
      ? 'flex-end'
      : 'center';

  return (
    <div
      className="pldr-root np-page-root"
      data-testid="page-local-drawing-renderer"
      data-page-id={page.id}
      data-worksheet-id={worksheet.id}
      data-range={range || ''}
    >
      <SheetTitleBand page={page} />

      {region && block && hasContent ? (
        <div
          className="pldr-content"
          style={{
            position: 'absolute',
            left: region.x,
            top: region.y,
            width: region.width,
            height: region.height,
            overflow: 'hidden',
            display: 'flex',
            justifyContent,
            alignItems,
            boxSizing: 'border-box',
          }}
        >
          <ExcelRangeRenderer
            block={block}
            scaleOverride={scale}
            embedded
            exporting={exporting}
          />
        </div>
      ) : null}

      <div className={`np-overlay-layer ${overlayInteractive ? 'active' : ''}`}>
        <CanvasEditor
          key={page.id}
          serialized={page.canvasObjects || []}
          onSerializedChange={
            onCanvasChange
              ? (objects) => onCanvasChange(page.id, objects)
              : () => undefined
          }
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
