import { useEffect, useMemo, useRef, useState } from 'react';
import type { MergedCell, Worksheet } from '../../model/types';
import { HIGHLIGHT_SWATCHES } from '../../model/tableStyle';
import {
  colLetter,
  a1,
  wsSetCell,
  wsSetFill,
  wsSetBorders,
  wsInsertRow,
  wsDeleteRow,
  wsInsertCol,
  wsDeleteCol,
  wsMergeCells,
  wsUnmergeCells,
  wsSetStyle,
  wsSetColWidth,
  wsSetRowHeight,
  wsAutoFitColumns,
  wsAutoFitRows,
  wsAutoFitRange,
  WS_MIN_COL_W,
  WS_MIN_ROW_H,
} from '../../model/excelRange';

interface Props {
  worksheet?: Worksheet;
  onWorksheetChange: (patch: Partial<Worksheet>, opts?: { structural?: boolean; skipHistory?: boolean }) => void;
  onReplaceSource?: () => void;
  onExportSource?: () => void;
  onApplyPreview?: () => void;
  previewVisible?: boolean;
  onTogglePreview?: () => void;
}

interface Rect {
  r0: number;
  c0: number;
  r1: number;
  c1: number;
}

const FONT_SIZES = [8, 9, 10, 11, 12, 14, 16];

function norm(r: Rect): Rect {
  return {
    r0: Math.min(r.r0, r.r1),
    c0: Math.min(r.c0, r.c1),
    r1: Math.max(r.r0, r.r1),
    c1: Math.max(r.c0, r.c1),
  };
}

function cellKey(r: number, c: number): string {
  return `${r}:${c}`;
}

function buildMergeMaps(merges: MergedCell[]) {
  const covered = new Set<string>();
  const spanAt = new Map<string, { rs: number; cs: number }>();
  for (const m of merges) {
    for (let r = m.startRow; r <= m.endRow; r += 1) {
      for (let c = m.startCol; c <= m.endCol; c += 1) {
        if (r === m.startRow && c === m.startCol) continue;
        covered.add(cellKey(r, c));
      }
    }
    spanAt.set(cellKey(m.startRow, m.startCol), {
      rs: m.endRow - m.startRow + 1,
      cs: m.endCol - m.startCol + 1,
    });
  }
  return { covered, spanAt };
}

/** Editable Excel-like source grid with merge, auto-fit, alignment, and resize. */
export default function RawGridRenderer({
  worksheet,
  onWorksheetChange,
  onReplaceSource,
  onExportSource,
  onApplyPreview,
  previewVisible = true,
  onTogglePreview,
}: Props) {
  const grid = worksheet?.grid ?? [];
  const styles = worksheet?.styles ?? {};
  const merges = worksheet?.mergedCells ?? [];
  const colWidthsPx = worksheet?.colWidthsPx ?? [];
  const rowHeightsPx = worksheet?.rowHeightsPx ?? [];

  const nCols = useMemo(
    () => Math.max(1, ...(grid.length ? grid.map((r) => r.length) : [1])),
    [grid],
  );

  const [sel, setSel] = useState<Rect | null>(null);
  const [toggleCells, setToggleCells] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<{ r: number; c: number } | null>(null);
  const draggingRef = useRef(false);
  const resizeRef = useRef<{ kind: 'col' | 'row'; index: number; start: number; startSize: number } | null>(null);
  const clipboardRef = useRef<string[][]>([]);
  const editingInputRef = useRef<HTMLInputElement | null>(null);
  const editingCellRef = useRef<{ r: number; c: number } | null>(null);

  const { covered, spanAt } = useMemo(() => buildMergeMaps(merges), [merges]);

  useEffect(() => {
    const capture = () => {
      const cell = editingCellRef.current;
      const input = editingInputRef.current;
      if (!cell || !input || !worksheet) return;
      onWorksheetChange(wsSetCell(worksheet, cell.r, cell.c, input.value));
      setEditing(null);
      editingCellRef.current = null;
      editingInputRef.current = null;
    };
    const discard = () => {
      setEditing(null);
      editingCellRef.current = null;
      editingInputRef.current = null;
    };
    document.addEventListener('singh360:capture-active-editors', capture);
    document.addEventListener('singh360:discard-active-editors', discard);
    return () => {
      document.removeEventListener('singh360:capture-active-editors', capture);
      document.removeEventListener('singh360:discard-active-editors', discard);
    };
  }, [worksheet, onWorksheetChange]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const rz = resizeRef.current;
      if (!rz || !worksheet) return;
      if (rz.kind === 'col') {
        const delta = e.clientX - rz.start;
        onWorksheetChange(
          { ...wsSetColWidth(worksheet, rz.index, rz.startSize + delta), layoutMode: 'manual' },
          { skipHistory: true },
        );
      } else {
        const delta = e.clientY - rz.start;
        onWorksheetChange(
          { ...wsSetRowHeight(worksheet, rz.index, rz.startSize + delta), layoutMode: 'manual' },
          { skipHistory: true },
        );
      }
    };
    const onUp = () => {
      draggingRef.current = false;
      resizeRef.current = null;
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [worksheet, onWorksheetChange]);

  if (!worksheet || !grid.length) {
    return <div className="np-empty">No source grid data.</div>;
  }

  const selRect = (): Rect | null => (sel ? norm(sel) : null);

  const selCells = (): Array<{ r: number; c: number }> => {
    const out: Array<{ r: number; c: number }> = [];
    const rect = selRect();
    if (rect) {
      for (let r = rect.r0; r <= rect.r1; r += 1) {
        for (let c = rect.c0; c <= rect.c1; c += 1) out.push({ r, c });
      }
    }
    for (const key of toggleCells) {
      const [rs, cs] = key.split(':');
      const r = Number(rs);
      const c = Number(cs);
      if (!out.some((x) => x.r === r && x.c === c)) out.push({ r, c });
    }
    return out;
  };

  const inSel = (r: number, c: number): boolean => {
    const rect = selRect();
    if (rect && r >= rect.r0 && r <= rect.r1 && c >= rect.c0 && c <= rect.c1) return true;
    return toggleCells.has(cellKey(r, c));
  };

  const commit = (patch: Partial<Worksheet>, structural = false) =>
    onWorksheetChange(patch, { structural });

  const setValue = (r: number, c: number, value: string) =>
    commit(wsSetCell(worksheet, r, c, value));

  const applyFill = (color: string | null) => {
    const cells = selCells();
    if (cells.length) commit(wsSetFill(worksheet, cells, color));
  };

  const applyBorders = (on: boolean) => {
    const cells = selCells();
    if (cells.length) commit(wsSetBorders(worksheet, cells, on));
  };

  const applyStyle = (patch: Parameters<typeof wsSetStyle>[2]) => {
    const cells = selCells();
    if (cells.length) commit(wsSetStyle(worksheet, cells, patch));
  };

  const anchorRow = () => (sel ? norm(sel).r0 : 0);
  const anchorCol = () => (sel ? norm(sel).c0 : 0);

  const columnHasData = (c: number): boolean => {
    for (let r = 0; r < grid.length; r += 1) {
      if ((grid[r]?.[c] ?? '').trim()) return true;
      const st = styles[a1(r, c)];
      if (st?.fill || st?.borders) return true;
    }
    return false;
  };

  const deleteColumn = () => {
    const c = anchorCol();
    if (columnHasData(c) && !window.confirm('Delete this column? You can undo with Ctrl+Z.')) return;
    commit(wsDeleteCol(worksheet, c), true);
  };

  const mergeSel = () => {
    const rect = selRect();
    if (!rect) return;
    commit(wsMergeCells(worksheet, rect), true);
  };

  const unmergeSel = () => {
    const rect = selRect();
    if (!rect) return;
    commit(wsUnmergeCells(worksheet, rect), true);
  };

  const autoFitCols = () => {
    const rect = selRect();
    if (!rect) return;
    const cols = Array.from({ length: rect.c1 - rect.c0 + 1 }, (_, i) => rect.c0 + i);
    commit({ ...wsAutoFitColumns(worksheet, cols), layoutMode: 'manual' }, true);
  };

  const autoFitRows = () => {
    const rect = selRect();
    if (!rect) return;
    const rows = Array.from({ length: rect.r1 - rect.r0 + 1 }, (_, i) => rect.r0 + i);
    commit({ ...wsAutoFitRows(worksheet, rows), layoutMode: 'manual' }, true);
  };

  const autoFitRange = () => {
    const rect = selRect();
    if (!rect) return;
    commit({ ...wsAutoFitRange(worksheet, rect), layoutMode: 'manual' }, true);
  };

  const autoFitSheet = () => {
    const cols = Array.from({ length: nCols }, (_, index) => index);
    const rows = Array.from({ length: grid.length }, (_, index) => index);
    const colPatch = wsAutoFitColumns(worksheet, cols);
    const interim: Worksheet = { ...worksheet, ...colPatch };
    const rowPatch = wsAutoFitRows(interim, rows);
    commit({ ...colPatch, ...rowPatch, layoutMode: 'manual' }, true);
  };

  const useAutoLayout = () => {
    commit({ layoutMode: 'auto' }, true);
  };

  const copySel = () => {
    const cells = selRect();
    if (!cells) return;
    const rows: string[][] = [];
    for (let r = cells.r0; r <= cells.r1; r += 1) {
      const row: string[] = [];
      for (let c = cells.c0; c <= cells.c1; c += 1) row.push(grid[r]?.[c] ?? '');
      rows.push(row);
    }
    clipboardRef.current = rows;
    void navigator.clipboard?.writeText(rows.map((r) => r.join('\t')).join('\n')).catch(() => undefined);
  };

  const pasteSel = async () => {
    let rows = clipboardRef.current;
    try {
      const text = await navigator.clipboard.readText();
      if (text) rows = text.replace(/\r/g, '').replace(/\n$/, '').split('\n').map((l) => l.split('\t'));
    } catch {
      /* fall back to local clipboard */
    }
    if (!rows.length) return;
    const r0 = anchorRow();
    const c0 = anchorCol();
    const next = grid.map((row) => [...row]);
    rows.forEach((row, dr) => {
      row.forEach((val, dc) => {
        const r = r0 + dr;
        const c = c0 + dc;
        while (next.length <= r) next.push([]);
        while (next[r].length <= c) next[r].push('');
        next[r][c] = val;
      });
    });
    commit({ grid: next });
  };

  const clearSel = () => {
    const cells = selCells();
    if (!cells.length) return;
    const next = grid.map((row) => [...row]);
    for (const { r, c } of cells) {
      if (next[r] && c < next[r].length) next[r][c] = '';
    }
    commit({ grid: next });
  };

  const onCellMouseDown = (r: number, c: number, e: React.MouseEvent) => {
    if (editing) return;
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {
      const key = cellKey(r, c);
      setToggleCells((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
      return;
    }
    setToggleCells(new Set());
    draggingRef.current = true;
    if (e.shiftKey && sel) setSel({ ...sel, r1: r, c1: c });
    else setSel({ r0: r, c0: c, r1: r, c1: c });
  };

  const onWrapKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && onApplyPreview) {
      e.preventDefault();
      editingInputRef.current?.blur();
      onApplyPreview();
      return;
    }
    if (editing) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
      e.preventDefault();
      copySel();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
      e.preventDefault();
      void pasteSel();
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault();
      clearSel();
    }
  };

  const tb = (label: string, onClick: () => void, title?: string) => (
    <button type="button" className="gx-btn" title={title ?? label} onClick={onClick}>
      {label}
    </button>
  );

  const colWidth = (c: number) => colWidthsPx[c] ?? WS_MIN_COL_W + 45;
  const rowHeight = (r: number) => rowHeightsPx[r] ?? WS_MIN_ROW_H + 4;

  return (
    <div className="gx-wrap" tabIndex={0} onKeyDown={onWrapKeyDown}>
      <div className="gx-toolbar">
        <div className="gx-toolbar-primary">
          {onApplyPreview ? (
            <button type="button" className="gx-btn gx-btn-primary" onClick={onApplyPreview}>
              Apply Data & Return
            </button>
          ) : null}
          {tb('Fit Sheet', autoFitSheet, 'Auto-fit the source-data worksheet only')}
          <span className="gx-source-data-hint">
            Data mode changes values and source formatting. Use Page → Edit Layout for printable sizing.
          </span>
          <span className="gx-source-exit-hint">Esc = Apply Data & Return</span>
        </div>
        <div className="gx-toolbar-menus">
          <details className="gx-tool-menu"><summary>Color & Borders</summary><div className="gx-tool-popover">
            {HIGHLIGHT_SWATCHES.map((s) => <button key={s.color} type="button" className="gx-swatch" title={s.label} style={{ backgroundColor: s.color }} onClick={() => applyFill(s.color)} />)}
            {tb('Clear Fill', () => applyFill(null))}{tb('Borders', () => applyBorders(true))}{tb('No Borders', () => applyBorders(false))}
          </div></details>
          <details className="gx-tool-menu"><summary>Rows, Columns & Merge</summary><div className="gx-tool-popover">
            {tb('Merge', mergeSel)}{tb('Unmerge', unmergeSel)}
            {tb('Ins Row', () => commit(wsInsertRow(worksheet, anchorRow()), true))}
            {tb('Del Row', () => commit(wsDeleteRow(worksheet, anchorRow()), true))}
            {tb('Ins Col', () => commit(wsInsertCol(worksheet, anchorCol()), true))}
            {tb('Del Col', deleteColumn)}{tb('Fit Cols', autoFitCols)}{tb('Fit Rows', autoFitRows)}{tb('Fit Range', autoFitRange)}
          </div></details>
          <details className="gx-tool-menu"><summary>Text & Alignment</summary><div className="gx-tool-popover">
            {tb('Left', () => applyStyle({ hAlign: 'left' }))}{tb('Center', () => applyStyle({ hAlign: 'center' }))}{tb('Right', () => applyStyle({ hAlign: 'right' }))}
            {tb('Top', () => applyStyle({ vAlign: 'top' }))}{tb('Middle', () => applyStyle({ vAlign: 'center' }))}{tb('Bottom', () => applyStyle({ vAlign: 'bottom' }))}
            {tb('Wrap', () => applyStyle({ wrap: true }))}{tb('No Wrap', () => applyStyle({ wrap: false }))}{tb('Bold', () => applyStyle({ bold: true }))}{tb('Italic', () => applyStyle({ italic: true }))}
            <select className="gx-font-size" defaultValue="" onChange={(e) => { const v = Number(e.target.value); if (v) applyStyle({ fontSize: v }); e.target.value = ''; }}>
              <option value="" disabled>Size</option>{FONT_SIZES.map((s) => <option key={s} value={s}>{s}pt</option>)}
            </select>
          </div></details>
          <details className="gx-tool-menu"><summary>Clipboard & Source</summary><div className="gx-tool-popover">
            {tb('Copy', copySel)}{tb('Paste', () => void pasteSel())}
            {onReplaceSource ? tb('Replace Source', onReplaceSource) : null}
            {onExportSource ? tb('Export Sheet', onExportSource) : null}
          </div></details>
        </div>
      </div>

      <table className="grid-table gx-table" style={{ tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: 36 }} />
          {Array.from({ length: nCols }, (_, c) => (
            <col key={c} style={{ width: colWidth(c) }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th className="gx-corner" />
            {Array.from({ length: nCols }, (_, c) => (
              <th
                key={c}
                className="gx-colhead gx-colhead-resize"
                style={{ width: colWidth(c), minWidth: colWidth(c) }}
                onClick={() => {
                  setToggleCells(new Set());
                  setSel({ r0: 0, c0: c, r1: grid.length - 1, c1: c });
                }}
              >
                {colLetter(c)}
                <span
                    className="gx-col-resize"
                    title="Drag to resize; double-click to auto-fit this column"
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      commit({
                        ...wsAutoFitColumns(worksheet, [c]),
                        layoutMode: 'manual',
                      }, true);
                    }}
                    onMouseDown={(e) => {
                    e.stopPropagation();
                    onWorksheetChange({});
                    resizeRef.current = {
                      kind: 'col',
                      index: c,
                      start: e.clientX,
                      startSize: colWidth(c),
                    };
                  }}
                />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.map((row, r) => (
            <tr key={r} style={{ height: rowHeight(r) }}>
              <th
                className="gx-rowhead gx-rowhead-resize"
                style={{ height: rowHeight(r) }}
                onClick={() => {
                  setToggleCells(new Set());
                  setSel({ r0: r, c0: 0, r1: r, c1: nCols - 1 });
                }}
              >
                {r + 1}
                <span
                   className="gx-row-resize"
                   title="Drag to resize; double-click to auto-fit this row"
                   onDoubleClick={(e) => {
                     e.stopPropagation();
                     commit({
                       ...wsAutoFitRows(worksheet, [r]),
                       layoutMode: 'manual',
                     }, true);
                   }}
                   onMouseDown={(e) => {
                    e.stopPropagation();
                    onWorksheetChange({});
                    resizeRef.current = {
                      kind: 'row',
                      index: r,
                      start: e.clientY,
                      startSize: rowHeight(r),
                    };
                  }}
                />
              </th>
              {Array.from({ length: nCols }, (_, c) => {
                if (covered.has(cellKey(r, c))) return null;
                const st = styles[a1(r, c)];
                const fill = typeof st?.fill === 'string' ? st.fill : undefined;
                const isEditing = editing?.r === r && editing?.c === c;
                const span = spanAt.get(cellKey(r, c));
                const cellStyle: React.CSSProperties = {
                  backgroundColor: fill,
                  height: rowHeight(r),
                  textAlign: (st?.hAlign as React.CSSProperties['textAlign']) ?? 'left',
                  verticalAlign: (st?.vAlign as React.CSSProperties['verticalAlign']) ?? 'top',
                };
                if (st?.bold) cellStyle.fontWeight = 700;
                if (st?.italic) cellStyle.fontStyle = 'italic';
                if (st?.fontSize) cellStyle.fontSize = st.fontSize;
                if (st?.wrap) {
                  cellStyle.whiteSpace = 'pre-wrap';
                  cellStyle.wordBreak = 'break-word';
                }
                return (
                  <td
                    key={c}
                    rowSpan={span?.rs}
                    colSpan={span?.cs}
                    className={`gx-cell ${inSel(r, c) ? 'gx-sel' : ''}`}
                    style={cellStyle}
                    onMouseDown={(e) => onCellMouseDown(r, c, e)}
                    onMouseEnter={() => {
                      if (draggingRef.current && sel) setSel({ ...sel, r1: r, c1: c });
                    }}
                    onDoubleClick={() => {
                      setEditing({ r, c });
                      editingCellRef.current = { r, c };
                    }}
                  >
                    {isEditing ? (
                      <input
                        className="grid-cell-input"
                        autoFocus
                        defaultValue={grid[r]?.[c] ?? ''}
                        aria-label={`Cell ${a1(r, c)}`}
                        ref={(el) => {
                          editingInputRef.current = el;
                          if (el && editingCellRef.current?.r === r && editingCellRef.current?.c === c) {
                            editingCellRef.current = { r, c };
                          }
                        }}
                        onBlur={(e) => {
                          setValue(r, c, e.currentTarget.value);
                          setEditing(null);
                          editingCellRef.current = null;
                          editingInputRef.current = null;
                        }}
                        onKeyDown={(e) => {
                          if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'z' || e.key.toLowerCase() === 'y')) {
                            e.preventDefault();
                            e.stopPropagation();
                            return;
                          }
                          if (e.key === 'Enter') {
                            setValue(r, c, e.currentTarget.value);
                            setEditing(null);
                            editingCellRef.current = null;
                            editingInputRef.current = null;
                          } else if (e.key === 'Escape') {
                            setEditing(null);
                            editingCellRef.current = null;
                            editingInputRef.current = null;
                          }
                        }}
                      />
                    ) : (
                      <span className={`gx-cell-text ${st?.wrap ? 'gx-wrap' : ''}`}>{grid[r]?.[c] ?? ''}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
