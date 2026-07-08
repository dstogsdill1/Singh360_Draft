import { useEffect, useMemo, useRef, useState } from 'react';
import type { Worksheet } from '../../model/types';
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
} from '../../model/excelRange';

interface Props {
  worksheet?: Worksheet;
  onWorksheetChange: (patch: Partial<Worksheet>, opts?: { structural?: boolean; skipHistory?: boolean }) => void;
}

interface Rect {
  r0: number;
  c0: number;
  r1: number;
  c1: number;
}

function norm(r: Rect): Rect {
  return {
    r0: Math.min(r.r0, r.r1),
    c0: Math.min(r.c0, r.c1),
    r1: Math.max(r.r0, r.r1),
    c1: Math.max(r.c0, r.c1),
  };
}

/** Editable Excel-like source grid: multi-cell selection, fill/border toggles,
 *  copy/paste, and insert/delete row/column. Edits flow up as worksheet patches
 *  so the Normalized (exact range) view refreshes and autosave persists. */
export default function RawGridRenderer({ worksheet, onWorksheetChange }: Props) {
  const grid = worksheet?.grid ?? [];
  const styles = worksheet?.styles ?? {};
  const nCols = useMemo(
    () => Math.max(1, ...(grid.length ? grid.map((r) => r.length) : [1])),
    [grid],
  );

  const [sel, setSel] = useState<Rect | null>(null);
  const [editing, setEditing] = useState<{ r: number; c: number } | null>(null);
  const draggingRef = useRef(false);
  const clipboardRef = useRef<string[][]>([]);
  const editingInputRef = useRef<HTMLInputElement | null>(null);
  const editingCellRef = useRef<{ r: number; c: number } | null>(null);

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
    const up = () => {
      draggingRef.current = false;
    };
    window.addEventListener('mouseup', up);
    return () => window.removeEventListener('mouseup', up);
  }, []);

  if (!worksheet || !grid.length) {
    return <div className="np-empty">No source grid data.</div>;
  }

  const selCells = (): Array<{ r: number; c: number }> => {
    if (!sel) return [];
    const n = norm(sel);
    const out: Array<{ r: number; c: number }> = [];
    for (let r = n.r0; r <= n.r1; r += 1) for (let c = n.c0; c <= n.c1; c += 1) out.push({ r, c });
    return out;
  };

  const inSel = (r: number, c: number): boolean => {
    if (!sel) return false;
    const n = norm(sel);
    return r >= n.r0 && r <= n.r1 && c >= n.c0 && c <= n.c1;
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

  const copySel = () => {
    const cells = sel ? norm(sel) : null;
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

  const onWrapKeyDown = (e: React.KeyboardEvent) => {
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

  return (
    <div className="gx-wrap" tabIndex={0} onKeyDown={onWrapKeyDown}>
      <div className="gx-toolbar">
        <span className="gx-tb-label">Highlight:</span>
        {HIGHLIGHT_SWATCHES.map((s) => (
          <button
            key={s.color}
            type="button"
            className="gx-swatch"
            title={s.label}
            aria-label={s.label}
            style={{ backgroundColor: s.color }}
            onClick={() => applyFill(s.color)}
          />
        ))}
        {tb('Clear Fill', () => applyFill(null))}
        <span className="gx-tb-sep" />
        {tb('Borders', () => applyBorders(true))}
        {tb('No Borders', () => applyBorders(false))}
        <span className="gx-tb-sep" />
        {tb('Ins Row', () => commit(wsInsertRow(worksheet, anchorRow()), true), 'Insert row above selection')}
        {tb('Del Row', () => commit(wsDeleteRow(worksheet, anchorRow()), true), 'Delete selected row')}
        {tb('Ins Col', () => commit(wsInsertCol(worksheet, anchorCol()), true), 'Insert column left of selection')}
        {tb('Del Col', deleteColumn, 'Delete selected column')}
        <span className="gx-tb-sep" />
        {tb('Copy', copySel)}
        {tb('Paste', () => void pasteSel())}
      </div>

      <table className="grid-table gx-table">
        <thead>
          <tr>
            <th className="gx-corner" />
            {Array.from({ length: nCols }, (_, c) => (
              <th
                key={c}
                className="gx-colhead"
                onClick={() => setSel({ r0: 0, c0: c, r1: grid.length - 1, c1: c })}
              >
                {colLetter(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.map((row, r) => (
            <tr key={r}>
              <th
                className="gx-rowhead"
                onClick={() => setSel({ r0: r, c0: 0, r1: r, c1: nCols - 1 })}
              >
                {r + 1}
              </th>
              {Array.from({ length: nCols }, (_, c) => {
                const st = styles[a1(r, c)];
                const fill = typeof st?.fill === 'string' ? st.fill : undefined;
                const isEditing = editing?.r === r && editing?.c === c;
                const cellStyle: React.CSSProperties = { backgroundColor: fill };
                if (st?.bold) cellStyle.fontWeight = 700;
                if (st?.italic) cellStyle.fontStyle = 'italic';
                return (
                  <td
                    key={c}
                    className={`gx-cell ${inSel(r, c) ? 'gx-sel' : ''}`}
                    style={cellStyle}
                    onMouseDown={(e) => {
                      if (isEditing) return;
                      e.preventDefault();
                      draggingRef.current = true;
                      if (e.shiftKey && sel) setSel({ ...sel, r1: r, c1: c });
                      else setSel({ r0: r, c0: c, r1: r, c1: c });
                    }}
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
                          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
                            e.preventDefault();
                            e.stopPropagation();
                            return;
                          }
                          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
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
                      <span className="gx-cell-text">{grid[r]?.[c] ?? ''}</span>
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
