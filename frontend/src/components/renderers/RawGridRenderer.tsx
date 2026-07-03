import type { Worksheet } from '../../model/types';

interface Props {
  worksheet?: Worksheet;
  onGridChange: (grid: string[][]) => void;
}

/** Raw workbook grid — used for Source View and Source Tabs (closer to Excel). */
export default function RawGridRenderer({ worksheet, onGridChange }: Props) {
  const grid = worksheet?.grid ?? [];
  const styles = worksheet?.styles ?? {};

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
              ].join(' ').trim();
              return (
                <td
                  key={c}
                  className={cls || undefined}
                  contentEditable
                  suppressContentEditableWarning
                  onBlur={(e) => {
                    const clone = grid.map((x) => [...x]);
                    clone[r][c] = e.currentTarget.textContent ?? '';
                    onGridChange(clone);
                  }}
                >
                  {cell}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
