interface Props {
  grid: string[][];
  onGridChange: (grid: string[][]) => void;
}

export default function GridPage({ grid, onGridChange }: Props) {
  if (!grid.length) {
    return <div>No grid data loaded.</div>;
  }

  return (
    <table className="grid-table">
      <tbody>
        {grid.map((row, r) => (
          <tr key={r}>
            {row.map((cell, c) => (
              <td
                key={`${r}-${c}`}
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
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
