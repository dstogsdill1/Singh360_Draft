/**
 * Page-local Univer spreadsheet editor (S360 PAGE LOCAL SPREADSHEET V2).
 *
 * One drawing page = one page-local worksheet. Spreadsheet mode is a
 * full-work-area editor. Drawing/Print/PDF use the saved drawing range.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import type { MergedCell, PageModel, Worksheet } from '../model/types';
import {
  fromUniverWorkbook,
  letters,
  toUniverWorkbook,
} from '../workspace/UniverWorkbookAdapter';
import {
  activeRangeA1,
  pasteTargetRange,
  protectedOverlap,
  rangeBounds,
} from '../workspace/workspaceContract';
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
  onAfterSetDrawingArea?: () => void;
  onOpenDataWorkspace?: () => void;
  onDuplicateSpreadsheetPage?: () => void;
}

type PageSpreadsheetState = {
  rangeA1?: string;
  scrollLeft: number;
  scrollTop: number;
};

type FacadeRangeCompat = {
  activate?: () => unknown;
  merge?: () => unknown;
  breakApart?: () => unknown;
  clearFormat?: () => unknown;
  clearContent?: () => unknown;
  setBackground?: (color: string) => unknown;
  setBackgroundColor?: (color: string) => unknown;
  setValues?: (values: unknown[][]) => unknown;
};

type FacadeSelectionCompat = {
  getActiveRangeList?: () => FacadeRangeCompat[];
};

type FacadeSheetCompat = {
  getActiveRange?: () => FacadeRangeCompat | null;
  getSelection?: () => FacadeSelectionCompat | null;
  getRange: (range: string) => FacadeRangeCompat;
};

type FacadeWorkbookCompat = {
  getActiveSheet?: () => FacadeSheetCompat | null;
  endEditingAsync?: (confirm?: boolean) => Promise<unknown>;
};

const spreadsheetUiState = new Map<string, PageSpreadsheetState>();

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

function mergeA1(merge: MergedCell): string {
  return `${letters(merge.startCol)}${merge.startRow + 1}:${letters(merge.endCol)}${merge.endRow + 1}`;
}

function rangeIntersectsMerge(range: IRange, merge: MergedCell): boolean {
  return range.startRow <= merge.endRow
    && range.endRow >= merge.startRow
    && range.startColumn <= merge.endCol
    && range.endColumn >= merge.startCol;
}

function waitForUniver(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, 0));
}

// S360 PAGE LOCAL SPREADSHEET V2
export default function PageLocalSpreadsheet({
  page,
  worksheet,
  onWorksheetChange,
  onPatchPage,
  onAfterSetDrawingArea,
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

  const [activeRanges, setActiveRanges] = useState<IRange[]>([]);
  const [message, setMessage] = useState('');
  const [rangeInput, setRangeInput] = useState(page.drawingRange || '');

  const activeRange = activeRanges[0] || null;
  const drawingRange = page.drawingRange || '';
  const excludedRows = page.drawingExcludedRows || [];
  const excludedColumns = page.drawingExcludedColumns || [];
  const maskedRanges = page.drawingMaskedRanges || [];

  useEffect(() => {
    setRangeInput(page.drawingRange || '');
  }, [page.id, page.drawingRange]);

  const getFacadeWorkbook = useCallback((): FacadeWorkbookCompat | null => (
    apiRef.current?.getActiveWorkbook() as unknown as FacadeWorkbookCompat | null
  ), []);

  const getFacadeSheet = useCallback((): FacadeSheetCompat | null => (
    getFacadeWorkbook()?.getActiveSheet?.() || null
  ), [getFacadeWorkbook]);

  const getActiveFacadeRanges = useCallback((): FacadeRangeCompat[] => {
    const sheet = getFacadeSheet();
    if (!sheet) return [];
    const list = sheet.getSelection?.()?.getActiveRangeList?.() || [];
    if (list.length) return list;
    const single = sheet.getActiveRange?.();
    return single ? [single] : [];
  }, [getFacadeSheet]);

  const endEditing = useCallback(async () => {
    const workbook = getFacadeWorkbook();
    if (workbook?.endEditingAsync) {
      await workbook.endEditingAsync(true);
    }
    await waitForUniver();
  }, [getFacadeWorkbook]);

  const extractWorksheet = useCallback((): Worksheet | null => {
    const base = baseDocRef.current;
    const workbook = apiRef.current?.getActiveWorkbook();
    if (!base || !workbook) return null;
    const doc = fromUniverWorkbook(workbook.getSnapshot(), base);
    const sheet = doc.sheets[0];
    if (!sheet) return null;
    return sheetToWorksheet(sheet);
  }, []);

  const flushChanges = useCallback(async (structural = false): Promise<Worksheet | null> => {
    if (!readyRef.current) return null;
    await endEditing();
    const ws = extractWorksheet();
    if (!ws) return null;
    baseDocRef.current = worksheetToDoc(ws);
    onWorksheetChange(worksheetIdRef.current, ws, { structural });
    return ws;
  }, [endEditing, extractWorksheet, onWorksheetChange]);

  const currentRangeA1 = useMemo(() => {
    if (!activeRange) return '';
    return activeRangeA1(activeRange);
  }, [activeRange]);

  const selectedRows = useMemo(() => (
    [...new Set<number>(activeRanges.flatMap<number>((range) => Array.from(
      { length: range.endRow - range.startRow + 1 },
      (_, i) => range.startRow + i,
    )))].sort((a, b) => a - b)
  ), [activeRanges]);

  const selectedColumns = useMemo(() => (
    [...new Set<number>(activeRanges.flatMap<number>((range) => Array.from(
      { length: range.endColumn - range.startColumn + 1 },
      (_, i) => range.startColumn + i,
    )))].sort((a, b) => a - b)
  ), [activeRanges]);

  const selectedMerges = useMemo(() => (
    (worksheet.mergedCells || []).filter(
      (merge) => activeRanges.some((range) => rangeIntersectsMerge(range, merge)),
    )
  ), [activeRanges, worksheet.mergedCells]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    readyRef.current = false;

    const doc = worksheetToDoc(worksheet);
    baseDocRef.current = doc;
    worksheetIdRef.current = worksheet.id;

    subscriptionsRef.current.forEach((subscription) => subscription.dispose());
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

    const activeSheet = univerAPI.getActiveWorkbook()?.getActiveSheet();
    const remembered = spreadsheetUiState.get(page.id);
    const targetRange = remembered?.rangeA1 || drawingRange;
    if (activeSheet && targetRange) {
      try {
        activeSheet.getRange(targetRange).activate();
      } catch {
        // Ignore invalid remembered ranges and leave Univer at its default cell.
      }
    }

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
        const selections = (event.selections || []).filter(Boolean);
        setActiveRanges(selections);
        const a1 = selections[0] ? activeRangeA1(selections[0]) : '';
        if (a1) setRangeInput(a1);
        spreadsheetUiState.set(page.id, {
          rangeA1: a1 || undefined,
          scrollLeft: spreadsheetUiState.get(page.id)?.scrollLeft || 0,
          scrollTop: spreadsheetUiState.get(page.id)?.scrollTop || 0,
        });
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
      if (disposed) return;
      readyRef.current = true;
      const selection = univerAPI.getActiveWorkbook()?.getActiveSheet()?.getActiveRange()?.getRange();
      setActiveRanges(selection ? [selection] : []);
      const host = container.querySelector('.univer-render-canvas-container') as HTMLElement | null;
      const saved = spreadsheetUiState.get(page.id);
      if (host && saved) {
        host.scrollLeft = saved.scrollLeft || 0;
        host.scrollTop = saved.scrollTop || 0;
      }
    }, 450);

    const resizeObserver = new ResizeObserver(() => {
      const anyUniver = univerRef.current as unknown as { resize?: () => void };
      anyUniver?.resize?.();
      window.dispatchEvent(new Event('resize'));
    });
    resizeObserver.observe(container);

    const shiftWheel = (event: WheelEvent) => {
      if (!event.shiftKey) return;
      const host = container.querySelector('.univer-render-canvas-container') as HTMLElement | null;
      if (!host) return;
      event.preventDefault();
      host.scrollLeft += event.deltaY;
      const saved = spreadsheetUiState.get(page.id) || { scrollLeft: 0, scrollTop: 0 };
      spreadsheetUiState.set(page.id, {
        ...saved,
        scrollLeft: host.scrollLeft,
        scrollTop: host.scrollTop,
      });
    };
    container.addEventListener('wheel', shiftWheel, { passive: false });

    const rememberScroll = () => {
      const host = container.querySelector('.univer-render-canvas-container') as HTMLElement | null;
      if (!host) return;
      const saved = spreadsheetUiState.get(page.id) || { scrollLeft: 0, scrollTop: 0 };
      spreadsheetUiState.set(page.id, {
        ...saved,
        scrollLeft: host.scrollLeft,
        scrollTop: host.scrollTop,
      });
    };
    container.addEventListener('scroll', rememberScroll, true);

    return () => {
      disposed = true;
      window.clearTimeout(timer);
      readyRef.current = false;
      resizeObserver.disconnect();
      container.removeEventListener('wheel', shiftWheel);
      container.removeEventListener('scroll', rememberScroll, true);
      subscriptionsRef.current.forEach((subscription) => subscription.dispose());
      subscriptionsRef.current = [];
      univer.dispose();
      univerRef.current = null;
      apiRef.current = null;
    };
    // Recreate only when a different page-local worksheet is selected.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [worksheet.id]);

  const activateRangeInput = useCallback(() => {
    const candidate = rangeInput.trim().toUpperCase();
    if (!candidate || !rangeBounds(candidate)) {
      setMessage('Enter a valid range such as A1:T43.');
      return false;
    }
    const sheet = getFacadeSheet();
    if (!sheet) return false;
    try {
      sheet.getRange(candidate).activate?.();
      setMessage(`Selected ${candidate}.`);
      return true;
    } catch {
      setMessage(`Unable to select ${candidate}.`);
      return false;
    }
  }, [getFacadeSheet, rangeInput]);

  const setDrawingAreaFromSelection = useCallback(async () => {
    const candidate = (rangeInput.trim() || currentRangeA1).toUpperCase();
    if (!candidate || !rangeBounds(candidate)) {
      setMessage('Select a rectangular range or enter one such as A1:T43.');
      return;
    }
    await flushChanges(true);
    const sheet = getFacadeSheet();
    try {
      sheet?.getRange(candidate).activate?.();
    } catch {
      setMessage(`Unable to select ${candidate}.`);
      return;
    }
    onPatchPage(page.id, {
      drawingRange: candidate,
      drawingExcludedColumns: page.drawingExcludedColumns || [],
      drawingExcludedRows: page.drawingExcludedRows || [],
      drawingMaskedRanges: page.drawingMaskedRanges || [],
    });
    setMessage(`Drawing updated from ${candidate}.`);
    onAfterSetDrawingArea?.();
  }, [
    currentRangeA1,
    flushChanges,
    getFacadeSheet,
    onAfterSetDrawingArea,
    onPatchPage,
    page.drawingExcludedColumns,
    page.drawingExcludedRows,
    page.drawingMaskedRanges,
    page.id,
    rangeInput,
  ]);

  const useEntireSheet = useCallback(async () => {
    await flushChanges(true);
    onPatchPage(page.id, { drawingRange: '' });
    setMessage('Drawing area set to entire sheet.');
    onAfterSetDrawingArea?.();
  }, [flushChanges, onAfterSetDrawingArea, onPatchPage, page.id]);

  const previewDrawing = useCallback(async () => {
    await flushChanges(false);
    onAfterSetDrawingArea?.();
  }, [flushChanges, onAfterSetDrawingArea]);

  const clearDrawingArea = useCallback(() => {
    onPatchPage(page.id, {
      drawingRange: undefined,
      drawingExcludedColumns: [],
      drawingExcludedRows: [],
      drawingMaskedRanges: [],
    });
    setRangeInput('');
    setMessage('Drawing area and render-only filters cleared.');
  }, [onPatchPage, page.id]);

  const excludeSelectedRows = useCallback(() => {
    if (!selectedRows.length) {
      setMessage('Select rows to exclude first.');
      return;
    }
    const merged = [...new Set([...(page.drawingExcludedRows || []), ...selectedRows])]
      .sort((a, b) => a - b);
    onPatchPage(page.id, { drawingExcludedRows: merged });
    setMessage(`Excluded ${selectedRows.length} row(s) from Drawing only.`);
  }, [onPatchPage, page.drawingExcludedRows, page.id, selectedRows]);

  const excludeSelectedColumns = useCallback(() => {
    if (!selectedColumns.length) {
      setMessage('Select columns to exclude first.');
      return;
    }
    const merged = [...new Set([...(page.drawingExcludedColumns || []), ...selectedColumns])]
      .sort((a, b) => a - b);
    onPatchPage(page.id, { drawingExcludedColumns: merged });
    setMessage(`Excluded ${selectedColumns.length} column(s) from Drawing only.`);
  }, [onPatchPage, page.drawingExcludedColumns, page.id, selectedColumns]);

  const maskSelectedRange = useCallback(() => {
    const ranges = activeRanges.map(activeRangeA1).filter(Boolean);
    if (!ranges.length) {
      setMessage('Select cells to mask first.');
      return;
    }
    const existing = page.drawingMaskedRanges || [];
    const additions = ranges
      .filter((range) => !existing.some((item) => item.range === range))
      .map((range) => ({ range }));
    onPatchPage(page.id, { drawingMaskedRanges: [...existing, ...additions] });
    setMessage(`Masked ${additions.length || ranges.length} range(s) in Drawing only.`);
  }, [activeRanges, onPatchPage, page.drawingMaskedRanges, page.id]);

  const restoreRenderFilters = useCallback(() => {
    onPatchPage(page.id, {
      drawingExcludedRows: [],
      drawingExcludedColumns: [],
      drawingMaskedRanges: [],
    });
    setMessage('Restored excluded rows/columns and masked cells.');
  }, [onPatchPage, page.id]);

  const performRangeAction = useCallback(async (
    label: string,
    action: (range: FacadeRangeCompat) => void,
  ) => {
    await endEditing();
    const ranges = getActiveFacadeRanges();
    if (!ranges.length) {
      setMessage('Select cells first.');
      return;
    }
    ranges.forEach(action);
    await waitForUniver();
    await flushChanges(true);
    setMessage(label);
  }, [endEditing, flushChanges, getActiveFacadeRanges]);

  const mergeSelection = useCallback(async () => {
    await performRangeAction('Merged the selected cells.', (range) => range.merge?.());
  }, [performRangeAction]);

  const unmergeSelection = useCallback(async () => {
    await performRangeAction('Unmerged the selected cells.', (range) => range.breakApart?.());
  }, [performRangeAction]);

  const unmergeAndRepeat = useCallback(async () => {
    if (!selectedMerges.length) {
      setMessage('The current selection does not contain a merged range.');
      return;
    }
    const ws = await flushChanges(false) || worksheet;
    const sheet = getFacadeSheet();
    if (!sheet) return;

    for (const merge of selectedMerges) {
      const range = sheet.getRange(mergeA1(merge));
      const value = ws.grid[merge.startRow]?.[merge.startCol] ?? '';
      range.breakApart?.();
      const values = Array.from(
        { length: merge.endRow - merge.startRow + 1 },
        () => Array.from(
          { length: merge.endCol - merge.startCol + 1 },
          () => value,
        ),
      );
      range.setValues?.(values);
    }
    await waitForUniver();
    await flushChanges(true);
    setMessage(`Split ${selectedMerges.length} merged range(s) and repeated the top-left value.`);
  }, [flushChanges, getFacadeSheet, selectedMerges, worksheet]);

  const clearFill = useCallback(async () => {
    if (selectedMerges.length) {
      setMessage(`Selection contains merged cells (${selectedMerges.map(mergeA1).join(', ')}). Unmerge first to change individual cell fills.`);
      return;
    }
    await performRangeAction('Cleared the selected cell fill.', (range) => {
      if (range.setBackground) range.setBackground('#ffffff');
      else range.setBackgroundColor?.('#ffffff');
    });
  }, [performRangeAction, selectedMerges]);

  const clearFormatting = useCallback(async () => {
    await performRangeAction('Cleared formatting from the selected cells.', (range) => range.clearFormat?.());
  }, [performRangeAction]);

  const deleteContents = useCallback(async () => {
    await performRangeAction('Deleted contents from the selected cells.', (range) => range.clearContent?.());
  }, [performRangeAction]);

  const copySelectionToClipboard = useCallback(() => {
    const ws = extractWorksheet();
    if (!ws || !activeRange) return;
    const { startRow, endRow, startColumn, endColumn } = activeRange;
    const rows: string[][] = [];
    for (let r = startRow; r <= endRow; r += 1) {
      const row: string[] = [];
      for (let c = startColumn; c <= endColumn; c += 1) {
        row.push(ws.grid[r]?.[c] ?? '');
      }
      rows.push(row);
    }
    void navigator.clipboard?.writeText(rows.map((row) => row.join('\t')).join('\n'))
      .catch(() => undefined);
    setMessage(`Copied ${rows.length} x ${rows[0]?.length || 0} cells.`);
  }, [activeRange, extractWorksheet]);

  const rangeLabel = activeRanges.length
    ? activeRanges.map(activeRangeA1).filter(Boolean).join(', ')
    : 'No selection';

  const mergeStatus = selectedMerges.length
    ? `Merged: ${selectedMerges.map(mergeA1).join(', ')}`
    : 'No merged cells in selection';

  const filterStatus = `Excluded ${excludedRows.length} row(s), ${excludedColumns.length} column(s); masked ${maskedRanges.length} range(s)`;

  return (
    <div
      className="page-local-spreadsheet"
      data-testid="page-local-spreadsheet"
      data-page-id={page.id}
      data-worksheet-id={worksheet.id}
    >
      <div className="pls-page-context">
        <div className="pls-page-identity">
          <span className="pls-page-code">{page.displaySheetCode || page.sheetCode}</span>
          <strong className="pls-page-title">{page.sheetTitle}</strong>
        </div>
        <div className="pls-page-help">
          Spreadsheet editor - merged cells behave like Excel. Unmerge before changing individual cells inside a merged block.
        </div>
        <div className="pls-page-status" title={filterStatus}>
          Drawing: {drawingRange || 'entire sheet'} - {filterStatus}
        </div>
      </div>

      <div className="pls-toolbar" role="toolbar" aria-label="Spreadsheet drawing and cell controls">
        <div className="pls-toolbar-row pls-toolbar-drawing">
          <span className="pls-group-label">Drawing area</span>
          <span className="pls-range-label" title="Current selection">{rangeLabel}</span>
          <input
            className="pls-range-input"
            value={rangeInput}
            onChange={(event) => setRangeInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                activateRangeInput();
              }
            }}
            aria-label="Drawing range"
            placeholder="A1:T43"
          />
          <button type="button" className="pls-btn" onClick={activateRangeInput}>Select Range</button>
          <button type="button" className="pls-btn pls-btn-primary" onClick={() => void setDrawingAreaFromSelection()}>Set Drawing Area</button>
          <button type="button" className="pls-btn" onClick={() => void previewDrawing()}>Preview Drawing</button>
          <button type="button" className="pls-btn" onClick={() => void useEntireSheet()}>Use Entire Sheet</button>
          <button type="button" className="pls-btn" onClick={excludeSelectedRows}>Exclude Rows</button>
          <button type="button" className="pls-btn" onClick={excludeSelectedColumns}>Exclude Columns</button>
          <button type="button" className="pls-btn" onClick={maskSelectedRange}>Mask Cells</button>
          <button type="button" className="pls-btn" onClick={restoreRenderFilters}>Restore Exclusions/Masks</button>
          <button type="button" className="pls-btn" onClick={clearDrawingArea}>Clear Drawing Area</button>
        </div>

        <div className="pls-toolbar-row pls-toolbar-cells">
          <span className="pls-group-label">Cell editing</span>
          <span className={`pls-merge-status ${selectedMerges.length ? 'is-merged' : ''}`} title={mergeStatus}>
            {mergeStatus}
          </span>
          <button type="button" className="pls-btn" onClick={() => void mergeSelection()}>Merge</button>
          <button type="button" className="pls-btn" onClick={() => void unmergeSelection()}>Unmerge</button>
          <button type="button" className="pls-btn" onClick={() => void unmergeAndRepeat()}>Split + Repeat Value</button>
          <button type="button" className="pls-btn" onClick={() => void clearFill()}>Clear Fill</button>
          <button type="button" className="pls-btn" onClick={() => void clearFormatting()}>Clear Formatting</button>
          <button type="button" className="pls-btn" onClick={() => void deleteContents()}>Delete Contents</button>
          <button type="button" className="pls-btn" onClick={copySelectionToClipboard}>Copy Selection</button>
          {onDuplicateSpreadsheetPage && (
            <button type="button" className="pls-btn" onClick={onDuplicateSpreadsheetPage}>Duplicate Page</button>
          )}
          {onOpenDataWorkspace && (
            <button type="button" className="pls-btn" onClick={onOpenDataWorkspace}>Open Data Workspace</button>
          )}
          {message && <span className="pls-message" role="status">{message}</span>}
        </div>
      </div>

      <div className="pls-univer-host-wrap">
        <div
          ref={containerRef}
          className="pls-univer-host univer-host"
          aria-label="Page local spreadsheet editor"
        />
      </div>
    </div>
  );
}
