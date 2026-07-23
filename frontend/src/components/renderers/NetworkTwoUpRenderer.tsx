// S360_HEB_IDF_SWITCH_MATRIX_V1 — H-E-B seven-column switch-matrix renderer.
import type { PageBlock } from '../../model/types';

interface Props {
  block: PageBlock;
  exporting?: boolean;
}

const DEFAULT_COL = 90;
const HEB_TABLE_PROFILE = 'heb_idf_switch_matrix';

function NetworkTable({
  headers,
  rows,
  colWidths,
  caption,
  rowHeight,
  tableProfile,
}: {
  headers: string[];
  rows: string[][];
  colWidths?: number[];
  caption?: string;
  rowHeight?: number;
  tableProfile?: string;
}) {
  const rh = rowHeight && rowHeight > 0 ? rowHeight : undefined;
  const isHeb = tableProfile === HEB_TABLE_PROFILE;
  return (
    <table className={`np-idf-table ${isHeb ? 'np-idf-table-heb' : ''}`}>
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
 * RDM / IDF network table renderer.
 *
 * Legacy network schedules retain the generic Port/Label/Path layout. H-E-B
 * switch matrices use only their seven source columns and pair two switches
 * side by side, matching the source drawing-table layout.
 */
export default function NetworkTwoUpRenderer({ block, exporting = false }: Props) {
  const headers = block.headers || [];
  const colWidths = block.colWidths;
  const fontSize = block.fontSize || 7;
  const caption = block.sectionTitle || '';
  const layoutMode = block.layoutMode || 'single';
  const rowHeight = typeof block.rowHeight === 'number' ? block.rowHeight : undefined;
  const tableProfile = block.tableProfile || '';
  const isHeb = tableProfile === HEB_TABLE_PROFILE;

  if (!headers.length) {
    return <div className="np np-empty">No network table data.</div>;
  }

  if (layoutMode === 'two_up') {
    const left = block.leftRows || [];
    const right = block.rightRows || [];
    const leftCaption = block.leftCaption ?? (block.portRangeLeft ? `PORTS ${block.portRangeLeft}` : '');
    const rightCaption = block.rightCaption ?? (block.portRangeRight ? `PORTS ${block.portRangeRight}` : '');
    return (
      <div className={`np-idf-single ${isHeb ? 'np-idf-heb' : ''}`} style={{ fontSize }}>
        {block.layoutWarnings?.length && !exporting ? (
          <div className="np-xr-warning">{block.layoutWarnings.join(' ')}</div>
        ) : null}
        {caption && <div className="np-idf-section-band">{caption}</div>}
        <div className="np-idf-two-up-row">
          <div className="np-idf-two-up-col">
            <NetworkTable
              headers={headers}
              rows={left}
              colWidths={colWidths}
              caption={leftCaption}
              rowHeight={rowHeight}
              tableProfile={tableProfile}
            />
          </div>
          <div className="np-idf-two-up-col">
            <NetworkTable
              headers={headers}
              rows={right}
              colWidths={colWidths}
              caption={rightCaption}
              rowHeight={rowHeight}
              tableProfile={tableProfile}
            />
          </div>
        </div>
      </div>
    );
  }

  const rows = block.rows || [];
  return (
    <div className={`np-idf-single ${isHeb ? 'np-idf-heb' : ''}`} style={{ fontSize }}>
      {block.layoutWarnings?.length && !exporting ? (
        <div className="np-xr-warning">{block.layoutWarnings.join(' ')}</div>
      ) : null}
      {caption && <div className="np-idf-section-band">{caption}</div>}
      <div className={isHeb ? 'np-idf-single-slot' : undefined}>
        <NetworkTable
          headers={headers}
          rows={rows}
          colWidths={colWidths}
          rowHeight={rowHeight}
          tableProfile={tableProfile}
        />
      </div>
    </div>
  );
}
