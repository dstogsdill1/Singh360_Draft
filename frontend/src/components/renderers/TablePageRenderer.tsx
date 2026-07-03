import { useState } from 'react';
import type { PageBlock } from '../../model/types';
import SheetContextMenu from '../SheetContextMenu';

interface Props {
  block: PageBlock;
  onChange: (patch: Partial<PageBlock>) => void;
  variant?: 'table' | 'matrix';
}

/** Normalized engineering table (also used for matrix with a tighter style). */
export default function TablePageRenderer({ block, onChange, variant = 'table' }: Props) {
  const headers = block.headers ?? [];
  const rows = block.rows ?? [];
  const [menu, setMenu] = useState<{ x: number; y: number; r: number; c: number } | null>(null);

  const updateHeader = (c: number, value: string) => {
    const next = [...headers];
    next[c] = value;
    onChange({ headers: next });
  };

  const updateCell = (r: number, c: number, value: string) => {
    const next = rows.map((row) => [...row]);
    next[r][c] = value;
    onChange({ rows: next });
  };

  const cols = Math.max(headers.length, ...(rows.length ? rows.map((r) => r.length) : [0]));

  const blankRow = () => Array.from({ length: cols }, () => '');

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

  return (
    <>
      <table className={variant === 'matrix' ? 'np-matrix' : 'np-table'}>
        <thead>
          <tr>
            {headers.map((h, c) => (
              <th
                key={c}
                contentEditable
                suppressContentEditableWarning
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setMenu({ x: e.clientX, y: e.clientY, r: -1, c });
                }}
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
                  onContextMenu={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setMenu({ x: e.clientX, y: e.clientY, r, c });
                  }}
                  onBlur={(e) => updateCell(r, c, e.currentTarget.textContent ?? '')}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

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
            { label: 'Bold / Align (Coming soon)', disabled: true, onClick: () => {} },
          ]}
        />
      )}
    </>
  );
}
