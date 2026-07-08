import type { PageBlock } from '../../model/types';

interface Props {
  block: PageBlock;
}

const DEFAULT_COL = 90;

function NetworkTable({
  headers,
  rows,
  colWidths,
  caption,
  rowHeight,
}: {
  headers: string[];
  rows: string[][];
  colWidths?: number[];
  caption?: string;
  rowHeight?: number;
}) {
  const rh = rowHeight && rowHeight > 0 ? rowHeight : undefined;
  return (
    <table className="np-idf-table">
      <colgroup>
        {headers.map((_, i) => (
          <col key={i} style={{ width: colWidths?.[i] ?? DEFAULT_COL }} />
        ))}
      </colgroup>
      <thead>
        {caption ? (
          <tr>
            <th className="np-idf-caption" colSpan={headers.length}>{caption}</th>
          </tr>
        ) : null}
        <tr style={rh ? { height: rh + 4 } : undefined}>
          {headers.map((h, i) => (
            <th key={i} className="np-idf-colhead">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri} style={rh ? { height: rh } : undefined}>
            {headers.map((_, ci) => (
              <td key={ci} title={row[ci] || ''}>{row[ci] || ''}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * RDM / IDF network table renderer (TABLE STYLE 4F, Phase B).
 *
 * Default: one full-width table, no rotation. Only switches to the two-up
 * (ports 1-N / N+1-total) side-by-side layout when the backend determined a
 * single stack would fall below the readable font floor (6.5pt). Uses only
 * the Singh360 standard colors: dark page header (rendered above by
 * SheetTitleBand), orange section band, gray column headers, white gridlines.
 */
export default function NetworkTwoUpRenderer({ block }: Props) {
  const headers = block.headers || [];
  const colWidths = block.colWidths;
  const fontSize = block.fontSize || 7;
  const caption = block.sectionTitle || '';
  const layoutMode = block.layoutMode || 'single';
  const rowHeight = typeof block.rowHeight === 'number' ? block.rowHeight : undefined;

  if (!headers.length) {
    return <div className="np np-empty">No network table data.</div>;
  }

  if (layoutMode === 'two_up') {
    const left = block.leftRows || [];
    const right = block.rightRows || [];
    return (
      <div className="np-idf-single" style={{ fontSize }}>
        {block.layoutWarnings?.length ? (
          <div className="np-xr-warning">{block.layoutWarnings.join(' ')}</div>
        ) : null}
        {caption && <div className="np-idf-section-band">{caption}</div>}
        <div className="np-idf-two-up-row">
          <div className="np-idf-two-up-col">
            <NetworkTable headers={headers} rows={left} colWidths={colWidths} caption={`PORTS ${block.portRangeLeft || ''}`} rowHeight={rowHeight} />
          </div>
          <div className="np-idf-two-up-col">
            <NetworkTable headers={headers} rows={right} colWidths={colWidths} caption={`PORTS ${block.portRangeRight || ''}`} rowHeight={rowHeight} />
          </div>
        </div>
      </div>
    );
  }

  const rows = block.rows || [];
  return (
    <div className="np-idf-single" style={{ fontSize }}>
      {block.layoutWarnings?.length ? (
        <div className="np-xr-warning">{block.layoutWarnings.join(' ')}</div>
      ) : null}
      {caption && <div className="np-idf-section-band">{caption}</div>}
      <NetworkTable headers={headers} rows={rows} colWidths={colWidths} rowHeight={rowHeight} />
    </div>
  );
}
