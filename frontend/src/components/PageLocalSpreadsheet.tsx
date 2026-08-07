/**
 * Page-local Univer spreadsheet editor (S360 PAGE LOCAL SPREADSHEET V1).
 *
 * One drawing page = one page-local worksheet.  This component mounts a full
 * Univer editor showing only the page's linkedWorksheetId worksheet.  It uses
 * the same toUniverWorkbook / fromUniverWorkbook adapter as DataWorkspace so
 * both editors share a single canonical serialisation contract.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { createUniver, type FUniver } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import sheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US';
import { UniverSheetsDataValidationPreset } from '@univerjs/preset-sheets-data-validation';
import dataValidationEnUS from '@univerjs/preset-sheets-data-validation/locales/en-US';
import { UniverSheetsConditionalFormattingPreset } from '@univerjs/preset-sheets-conditional-formatting';
import conditionalFormattingEnUS from '@univerjs/preset-sheets-conditional-formatting/locales/en-US';
import {
  CommandType,
  LocaleType,
  type IRange,
  type Univer,
} from '@univerjs/core';
import type { WorkbookDocument } from '../api/client';
import type { PageModel, Worksheet } from '../model/types';
import {
  fromUniverWorkbook,
  letters,
  toUniverWorkbook,
} from '../workspace/UniverWorkbookAdapter';
import { activeRangeA1, pasteTargetRange, protectedOverlap, rangeBounds } from '../workspace/workspaceContract';
import { sheetToWorksheet } from '../workspace/workspaceProject';

interface Props {
  page: PageModel;
  worksheet: Worksheet;
  onWorksheetChange: (
    worksheetId: string,
    patch: Partial<Worksheet>,
    opts?: { structural?: boolean; skipHistory?: boolean },
  ) => void;
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
  onOpenDataWorkspace?: () => void;
  onDuplicateSpreadsheetPage?: () => void;
}

/** Convert app Worksheet model → minimal WorkbookDocument for Univer. */
function worksheetToDoc(ws: Worksheet): WorkbookDocument {
  const cells: Record<string, { v?: unknown; f?: string }> = {};
  const formulas = ws.formulas || {};
  (ws.grid || []).forEach((row, r) => {
    row.forEach((val, c) => {
      const coord = `${letters(c)}${r + 1}`;
      const formula = formulas[coord];
      if (formula) {
        cells[coord] = { f: formula, v: val };
      } else if (val !== '' && val !== null && val !== undefined) {
        cells[coord] = { v: val };
      }
    });
  });
  return {
    revision: 0,
    updatedAt: '',
    sheets: [{
      id: ws.id,
      name: ws.name,
      cells,
      styles: { ...(ws.styles || {}) } as Record<string, Record<string, unknown>>,
      merges: (ws.mergedCells || []).map(
        (m) => `${letters(m.startCol)}${m.startRow + 1}:${letters(m.endCol)}${m.endRow + 1}`,
      ),
      rowHeights: { ...(ws.rowHeights || {}) },
      columnWidths: { ...(ws.columnWidths || {}) },
      defaultColumnWidth: ws.defaultColumnWidth || 8.43,
      defaultRowHeight: ws.defaultRowHeight || 15,
      hiddenRows: (ws.hiddenRows || []).map((r) => r + 1),
      hiddenColumns: (ws.hiddenColumns || []).map((c) => letters(c)),
      archived: false,
      tabColor: null,
      role: ws.role || null,
      sourceSetup: ws.sourceSetup || {},
      protectedRanges: ws.protectedRanges || [],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      dataValidations: (ws.dataValidations || []) as any[],
      conditionalFormats: ws.conditionalFormats || [],
      tableRegions: ws.tableRegions || [],
      tableLayout: ws.tableLayout || 'single',
      annotations: ws.annotations || [],
      pageLayouts: ws.pageLayouts || [],
    }],
  };
}

function mergeLocales() {
  return { ...sheetsCoreEnUS, ...dataValidationEnUS, ...conditionalFormattingEnUS };
}

// S360 PAGE LOCAL SPREADSHEET V1
export default function PageLocalSpreadsheet({
  page,
  worksheet,
  onWorksheetChange,
  onPatchPage,
  onOpenDataWorkspace,
  onDuplicateSpreadsheetPage,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<Univer | null>(null);
  const apiRef = useRef<FUniver | null>(null);
  const baseDocRef = useRef<WorkbookDocument | null>(null);
  const worksheetIdRef = useRef(worksheet.id);
  const subscriptionsRef = useRef<Array<{ dispose(): void }>>([]);
  const readyRef = useRef(false);
  const [activeRange, setActiveRange] = useState<IRange | null>(null);
  const [message, setMessage] = useState('');

  const drawingRange = page.drawingRange || '';

  // Extract a Worksheet from the current Univer snapshot.
  const extractWorksheet = useCallback((): Worksheet | null => {
    const base = baseDocRef.current;
    const workbook = apiRef.current?.getActiveWorkbook();
    if (!base || !workbook) return null;
    const doc = fromUniverWorkbook(workbook.getSnapshot(), base);
    const sheet = doc.sheets[0];
    if (!sheet) return null;
    return sheetToWorksheet(sheet);
  }, []);

  // Flush current Univer state → onWorksheetChange (debounced via useEffect).
  const flushChanges = useCallback((structural = false) => {
    if (!readyRef.current) return;
    const ws = extractWorksheet();
    if (!ws) return;
    onWorksheetChange(worksheetIdRef.current, ws, { structural });
  }, [extractWorksheet, onWorksheetChange]);

  // Re-initialise Univer when the worksheet changes identity.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    readyRef.current = false;

    const doc = worksheetToDoc(worksheet);
    baseDocRef.current = doc;
    worksheetIdRef.current = worksheet.id;

    // Dispose any existing Univer instance first.
    subscriptionsRef.current.forEach((s) => s.dispose());
    subscriptionsRef.current = [];
    if (univerRef.current) {
      univerRef.current.dispose();
      univerRef.current = null;
      apiRef.current = null;
    }

    const { univer, univerAPI } = createUniver({
      locale: LocaleType.EN_US,
      locales: { [LocaleType.EN_US]: mergeLocales() },
      presets: [
        UniverSheetsCorePreset({
          container,
          header: true,
          toolbar: true,
          formulaBar: true,
          footer: { sheetBar: false, statisticBar: true, menus: true, zoomSlider: true },
        }),
        UniverSheetsDataValidationPreset({ showEditOnDropdown: true }),
        UniverSheetsConditionalFormattingPreset(),
      ],
    });

    if (disposed) {
      univer.dispose();
      return;
    }

    univerRef.current = univer;
    apiRef.current = univerAPI;

    univer.createUniverSheet(
      toUniverWorkbook(doc, page.sheetTitle || worksheet.name, `page-${page.id}`),
    );

    subscriptionsRef.current = [
      univerAPI.addEvent(univerAPI.Event.BeforeClipboardPaste, (event) => {
        const sheet = baseDocRef.current?.sheets[0];
        const selection = event.worksheet.getActiveRange()?.getRange();
        if (!selection || !sheet) return;
        const target = pasteTargetRange(selection, event.text || '');
        const blocked = protectedOverlap(target, sheet.protectedRanges || []);
        if (!blocked) return;
        event.cancel = true;
        setMessage(`Paste rejected: overlaps locked cells (${blocked}).`);
      }),
      univerAPI.addEvent(univerAPI.Event.SelectionChanged, (event) => {
        setActiveRange(event.selections[0] || null);
      }),
      univerAPI.addEvent(univerAPI.Event.CommandExecuted, (event) => {
        if (!readyRef.current || event.type !== CommandType.COMMAND) return;
        window.setTimeout(() => {
          const ws = extractWorksheet();
          if (!ws) return;
          baseDocRef.current = worksheetToDoc(ws);
          onWorksheetChange(worksheetIdRef.current, ws, { structural: false });
        }, 0);
      }),
    ];

    const timer = window.setTimeout(() => {
      if (!disposed) {
        readyRef.current = true;
        setActiveRange(univerAPI.getActiveWorkbook()?.getActiveSheet()?.getActiveRange()?.getRange() || null);
      }
    }, 400);

    return () => {
      disposed = true;
      window.clearTimeout(timer);
      readyRef.current = false;
      subscriptionsRef.current.forEach((s) => s.dispose());
      subscriptionsRef.current = [];
      univer.dispose();
      univerRef.current = null;
      apiRef.current = null;
    };
    // Re-run only when the worksheet identity changes (not on every prop re-render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worksheet.id]);

  // Drawing-area commands ---------------------------------------------------

  const setDrawingAreaFromSelection = useCallback(() => {
    const api = apiRef.current;
    if (!api) return;
    const range = api.getActiveWorkbook()?.getActiveSheet()?.getActiveRange()?.getRange();
    if (!range) return;
    const a1 = activeRangeA1(range);
    if (!a1) return;
    onPatchPage(page.id, { drawingRange: a1 });
    setMessage(`Drawing area set to ${a1}`);
  }, [page.id, onPatchPage]);

  const useEntireSheet = useCallback(() => {
    onPatchPage(page.id, { drawingRange: '' });
    setMessage('Drawing area set to entire sheet.');
  }, [page.id, onPatchPage]);

  const clearDrawingArea = useCallback(() => {
    onPatchPage(page.id, { drawingRange: undefined });
    setMessage('Drawing area cleared.');
  }, [page.id, onPatchPage]);

  const copySelectionToClipboard = useCallback(() => {
    const api = apiRef.current;
    if (!api) return;
    const ws = extractWorksheet();
    const range = api.getActiveWorkbook()?.getActiveSheet()?.getActiveRange()?.getRange();
    if (!ws || !range) return;
    const { startRow, endRow, startColumn, endColumn } = range;
    const rows: string[][] = [];
    for (let r = startRow; r <= endRow; r++) {
      const row: string[] = [];
      for (let c = startColumn; c <= endColumn; c++) row.push(ws.grid[r]?.[c] ?? '');
      rows.push(row);
    }
    void navigator.clipboard?.writeText(rows.map((r) => r.join('\t')).join('\n')).catch(() => undefined);
    setMessage(`Copied ${rows.length} × ${rows[0]?.length || 0} cells.`);
  }, [extractWorksheet]);

  const rangeLabel = activeRange
    ? (() => {
      const { startRow, endRow, startColumn, endColumn } = activeRange;
      if (startRow === endRow && startColumn === endColumn) {
        return `${letters(startColumn)}${startRow + 1}`;
      }
      return `${letters(startColumn)}${startRow + 1}:${letters(endColumn)}${endRow + 1}`;
    })()
    : '';

  const drawingRangeLabel = drawingRange
    ? `Drawing area: ${drawingRange}`
    : 'Drawing area: (entire sheet)';

  // Highlight drawing area boundary as an absolute overlay inside the container.
  // We compute the pixel position from the worksheet geometry.
  const drawingOverlay = (() => {
    if (!drawingRange) return null;
    const bounds = rangeBounds(drawingRange);
    if (!bounds) return null;
    const colWidths = worksheet.colWidthsPx || [];
    const rowHeights = worksheet.rowHeightsPx || [];
    const DEFAULT_COL_W = 80;
    const DEFAULT_ROW_H = 20;
    // Approximate header offsets in Univer
    const HEADER_ROW_H = 25;
    const HEADER_COL_W = 40;
    let x = HEADER_COL_W;
    let y = HEADER_ROW_H + 40; // 40px for formula bar
    for (let c = 0; c < bounds.startColumn; c++) x += colWidths[c] || DEFAULT_COL_W;
    for (let r = 0; r < bounds.startRow; r++) y += rowHeights[r] || DEFAULT_ROW_H;
    let w = 0;
    let h = 0;
    for (let c = bounds.startColumn; c <= bounds.endColumn; c++) w += colWidths[c] || DEFAULT_COL_W;
    for (let r = bounds.startRow; r <= bounds.endRow; r++) h += rowHeights[r] || DEFAULT_ROW_H;
    return (
      <div
        className="page-local-drawing-area-overlay"
        style={{ left: x, top: y, width: w, height: h }}
        title={`Drawing area: ${drawingRange}`}
        aria-label={`Drawing area boundary: ${drawingRange}`}
      />
    );
  })();

  return (
    <div className="page-local-spreadsheet" data-testid="page-local-spreadsheet" data-page-id={page.id} data-worksheet-id={worksheet.id}>
      <div className="pls-toolbar" role="toolbar" aria-label="Spreadsheet page drawing area controls">
        <span className="pls-range-label" title="Current selection">{rangeLabel}</span>
        <span className="pls-separator" />
        <span className="pls-drawing-label" title={drawingRange || 'Entire sheet used as drawing area'}>{drawingRangeLabel}</span>
        <span className="pls-separator" />
        <button type="button" className="pls-btn" onClick={setDrawingAreaFromSelection} title="Set drawing area from the current selection">Set Drawing Area</button>
        <button type="button" className="pls-btn" onClick={useEntireSheet} title="Use entire sheet as drawing area">Use Entire Sheet</button>
        <button type="button" className="pls-btn" onClick={clearDrawingArea} title="Clear explicit drawing area">Clear Drawing Area</button>
        <span className="pls-separator" />
        <button type="button" className="pls-btn" onClick={copySelectionToClipboard} title="Copy selection to system clipboard for cross-page paste">Copy Selection</button>
        <span className="pls-separator" />
        {onDuplicateSpreadsheetPage && (
          <button type="button" className="pls-btn" onClick={onDuplicateSpreadsheetPage}>Duplicate Page</button>
        )}
        {onOpenDataWorkspace && (
          <button type="button" className="pls-btn" onClick={onOpenDataWorkspace}>Open Data Workspace</button>
        )}
        {message && <span className="pls-message" role="status">{message}</span>}
      </div>
      <div className="pls-univer-host-wrap">
        <div ref={containerRef} className="pls-univer-host" aria-label="Page local spreadsheet editor" />
        {drawingOverlay}
      </div>
    </div>
  );
}
