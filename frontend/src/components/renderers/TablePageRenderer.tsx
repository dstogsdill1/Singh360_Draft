import type { PageBlock } from '../../model/types';

interface Props {
  block: PageBlock;
  onChange: (patch: Partial<PageBlock>) => void;
  variant?: 'table' | 'matrix';
}

/** Normalized engineering table (also used for matrix with a tighter style). */
export default function TablePageRenderer({ block, onChange, variant = 'table' }: Props) {
  const headers = block.headers ?? [];
  const rows = block.rows ?? [];

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

  return (
    <table className={variant === 'matrix' ? 'np-matrix' : 'np-table'}>
      <thead>
        <tr>
          {headers.map((h, c) => (
            <th
              key={c}
              contentEditable
              suppressContentEditableWarning
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
                onBlur={(e) => updateCell(r, c, e.currentTarget.textContent ?? '')}
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
