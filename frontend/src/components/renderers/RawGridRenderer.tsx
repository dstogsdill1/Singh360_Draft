import { useState } from 'react';
import type { Worksheet } from '../../model/types';

interface Props {
  worksheet?: Worksheet;
  onGridChange: (grid: string[][]) => void;
}

/** Raw workbook grid — used for Source View and Source Tabs (closer to Excel). */
export default function RawGridRenderer({ worksheet, onGridChange }: Props) {
  const grid = worksheet?.grid ?? [];
  const styles = worksheet?.styles ?? {};
  const [activeCol, setActiveCol] = useState<number | null>(null);

  if (!grid.length) {
    return <div className="np-empty">No source grid data.</div>;
  }

  const colLetter = (c: number) => {
    let s = '';
    let n = c + 1;
    while (n > 0) {
      const rem = (n - 1) % 26;
      s = String.fromCharCode(65 + rem) + s;
      n = Math.floor((n - 1) / 26);
    }
    return s;
  };

  const updateCell = (r: number, c: number, value: string) => {
    const clone = grid.map((x) => [...x]);
    while ((clone[r] ?? []).length <= c) clone[r].push('');
    clone[r][c] = value;
    onGridChange(clone);
  };

  return (
    <table className="grid-table">
      <tbody>
        {grid.map((row, r) => (
          <tr key={r}>
            {row.map((cell, c) => {
              const st = styles[`${colLetter(c)}${r + 1}`];
              const cls = [
                st?.bold ? 'gc-bold' : '',
                st?.italic ? 'gc-italic' : '',
                st?.fill ? 'gc-fill' : '',
                activeCol === c ? 'gc-col-active' : '',
              ].join(' ').trim();
              return (
                <td key={c} className={cls || undefined}>
                  <input
                    className="grid-cell-input"
                    value={cell ?? ''}
                    title={`Cell ${colLetter(c)}${r + 1}`}
                    aria-label={`Cell ${colLetter(c)}${r + 1}`}
                    onFocus={() => setActiveCol(c)}
                    onBlur={() => setActiveCol(null)}
                    onChange={(e) => updateCell(r, c, e.currentTarget.value)}
                  />
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
