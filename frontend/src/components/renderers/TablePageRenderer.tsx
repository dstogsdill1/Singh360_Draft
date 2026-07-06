import { useEffect, useRef, useState } from 'react';
import type { PageBlock } from '../../model/types';
import { BODY_H } from '../../model/sheetGeometry';
import SheetContextMenu from '../SheetContextMenu';

interface Props {
  block: PageBlock;
  onChange: (patch: Partial<PageBlock>) => void;
  onDuplicateTable?: () => void;
  variant?: 'table' | 'matrix';
}

/** Normalized engineering table (also used for matrix with a tighter style). */
export default function TablePageRenderer({ block, onChange, onDuplicateTable, variant = 'table' }: Props) {
  const headers = block.headers ?? [];
  const rows = block.rows ?? [];
  const [menu, setMenu] = useState<{ x: number; y: number; r: number; c: number } | null>(null);
  const clipboardRef = useRef('');
  const editStartRef = useRef('');
  const fitWrapRef = useRef<HTMLDivElement | null>(null);
  const tableRef = useRef<HTMLTableElement | null>(null);

  useEffect(() => {
    const capture = () => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || !el.isContentEditable || !el.closest(`[data-block-id="${block.id}"]`)) return;
      const r = Number(el.dataset.row ?? -999);
      const c = Number(el.dataset.col ?? -1);
      const value = el.textContent ?? '';
      if (r === -1) updateHeader(c, value);
      else if (r >= 0) updateCell(r, c, value);
    };
    document.addEventListener('singh360:capture-active-editors', capture);
    return () => document.removeEventListener('singh360:capture-active-editors', capture);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.id, headers, rows]);

  useEffect(() => {
    const wrap = fitWrapRef.current;
    const table = tableRef.current;
    if (!wrap || !table) return;
    let lastScale = -1;
    let raf = 0;
    const fit = () => {
      const available = BODY_H - 92; // .np vertical padding + table margins.
      const measured = table.scrollHeight;
      const scale = measured > available ? Math.max(0.58, Math.min(1, available / measured)) : 1;
      if (Math.abs(scale - lastScale) < 0.004) return;
      lastScale = scale;
      wrap.style.setProperty('--table-fit-scale', String(scale));
      wrap.dataset.fit = scale < 1 ? 'scaled' : 'normal';
    };
    const scheduleFit = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(fit);
    };
    fit();
    const ro = new ResizeObserver(scheduleFit);
    ro.observe(table);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [headers, rows, variant]);

  const updateHeader = (c: number, value: string) => {
    const next = [...headers];
    next[c] = value;
    onChange({ headers: next });
  };

  const updateCell = (r: number, c: number, value: string) => {
    const next = rows.map((row) => [...row]);
    while (next[r].length <= c) next[r].push('');
    next[r][c] = value;
    onChange({ rows: next });
  };

  const cols = Math.max(headers.length, ...(rows.length ? rows.map((r) => r.length) : [0]));

  const blankRow = () => Array.from({ length: cols }, () => '');

  const focusCell = (r: number, c: number) => {
    window.requestAnimationFrame(() => {
      const sel = `[data-block-id="${block.id}"] [data-row="${r}"][data-col="${c}"]`;
      const el = document.querySelector<HTMLElement>(sel);
      el?.focus();
      if (el) {
        const range = document.createRange();
        range.selectNodeContents(el);
        range.collapse(false);
        const s = window.getSelection();
        s?.removeAllRanges();
        s?.addRange(range);
      }
    });
  };

  const moveByTab = (r: number, c: number, backwards: boolean) => {
    const flat: Array<{ r: number; c: number }> = [];
    headers.forEach((_, i) => flat.push({ r: -1, c: i }));
    rows.forEach((row, ri) => row.forEach((_, ci) => flat.push({ r: ri, c: ci })));
    const idx = flat.findIndex((x) => x.r === r && x.c === c);
    const next = flat[Math.min(flat.length - 1, Math.max(0, idx + (backwards ? -1 : 1)))] ?? { r, c };
    focusCell(next.r, next.c);
  };

  const onCellKeyDown = (e: React.KeyboardEvent<HTMLElement>, r: number, c: number) => {
    const el = e.currentTarget;
    if (e.key === 'Enter') {
      e.preventDefault();
      const value = el.textContent ?? '';
      if (r === -1) updateHeader(c, value);
      else updateCell(r, c, value);
      el.blur();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      el.textContent = editStartRef.current;
      if (r === -1) updateHeader(c, editStartRef.current);
      else updateCell(r, c, editStartRef.current);
      el.blur();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      const value = el.textContent ?? '';
      if (r === -1) updateHeader(c, value);
      else updateCell(r, c, value);
      moveByTab(r, c, e.shiftKey);
    }
  };

  const addRow = (at: number) => {
    const next = rows.map((row) => [...row]);
    next.splice(at, 0, blankRow());
    onChange({ rows: next });
  };
  const duplicateRow = (r: number) => {
    const next = rows.map((row) => [...row]);
    next.splice(r + 1, 0, [...(rows[r] ?? blankRow())]);
    onChange({ rows: next });
  };
  const deleteRow = (r: number) => {
    const next = rows.map((row) => [...row]);
    next.splice(r, 1);
    onChange({ rows: next });
  };
  const addColumn = (at: number) => {
    onChange({
      headers: [...headers.slice(0, at), '', ...headers.slice(at)],
      rows: rows.map((row) => [...row.slice(0, at), '', ...row.slice(at)]),
    });
  };
  const deleteColumn = (c: number) => {
    onChange({
      headers: headers.filter((_, i) => i !== c),
      rows: rows.map((row) => row.filter((_, i) => i !== c)),
    });
  };
  const clearCell = (r: number, c: number) => updateCell(r, c, '');
  const copyCell = (r: number, c: number) => {
    const value = r < 0 ? (headers[c] ?? '') : (rows[r]?.[c] ?? '');
    clipboardRef.current = value;
    void navigator.clipboard?.writeText(value).catch(() => undefined);
  };
  const pasteCell = async (r: number, c: number) => {
    let value = clipboardRef.current;
    try { value = await navigator.clipboard.readText(); } catch { /* keep local clipboard */ }
    if (r < 0) updateHeader(c, value);
    else updateCell(r, c, value);
  };

  return (
    <>
      <div className="np-table-fit-wrap" ref={fitWrapRef}>
        <table ref={tableRef} className={variant === 'matrix' ? 'np-matrix' : 'np-table'} data-block-id={block.id}>
          <thead>
            <tr>
              {headers.map((h, c) => (
                <th
                  key={c}
                  contentEditable
                  suppressContentEditableWarning
                  data-row={-1}
                  data-col={c}
                  tabIndex={0}
                  onFocus={(e) => { editStartRef.current = e.currentTarget.textContent ?? ''; }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setMenu({ x: e.clientX, y: e.clientY, r: -1, c });
                  }}
                  onInput={(e) => updateHeader(c, e.currentTarget.textContent ?? '')}
                  onKeyDown={(e) => onCellKeyDown(e, -1, c)}
                  onBlur={(e) => updateHeader(c, e.currentTarget.textContent ?? '')}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, c) => (
                  <td
                    key={c}
                    contentEditable
                    suppressContentEditableWarning
                    data-row={r}
                    data-col={c}
                    tabIndex={0}
                    onFocus={(e) => { editStartRef.current = e.currentTarget.textContent ?? ''; }}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setMenu({ x: e.clientX, y: e.clientY, r, c });
                    }}
                    onInput={(e) => updateCell(r, c, e.currentTarget.textContent ?? '')}
                    onKeyDown={(e) => onCellKeyDown(e, r, c)}
                    onBlur={(e) => updateCell(r, c, e.currentTarget.textContent ?? '')}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {menu && (
        <SheetContextMenu
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          actions={[
            { label: 'Add Row Above', disabled: menu.r < 0, onClick: () => addRow(Math.max(menu.r, 0)) },
            { label: 'Add Row Below', disabled: menu.r < 0, onClick: () => addRow(menu.r + 1) },
            { label: 'Duplicate Row', disabled: menu.r < 0, onClick: () => duplicateRow(menu.r) },
            { label: 'Delete Row', disabled: menu.r < 0, onClick: () => deleteRow(menu.r) },
            { label: 'Add Column Left', divider: true, onClick: () => addColumn(menu.c) },
            { label: 'Add Column Right', onClick: () => addColumn(menu.c + 1) },
            { label: 'Delete Column', onClick: () => deleteColumn(menu.c) },
            { label: 'Clear Cell', divider: true, disabled: menu.r < 0, onClick: () => clearCell(menu.r, menu.c) },
            { label: 'Copy Cell', onClick: () => copyCell(menu.r, menu.c) },
            { label: 'Paste Cell', onClick: () => void pasteCell(menu.r, menu.c) },
            { label: 'Duplicate Table', divider: true, disabled: !onDuplicateTable, onClick: () => onDuplicateTable?.() },
            { label: 'Fit Table to Body', onClick: () => onChange({ styleRole: 'fit-to-body' }) },
            { label: 'Resize Columns', disabled: true, hint: 'Column resize handles are not implemented yet; values still save safely.', onClick: () => {} },
          ]}
        />
      )}
    </>
  );
}
