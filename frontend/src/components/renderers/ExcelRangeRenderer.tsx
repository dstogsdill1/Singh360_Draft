import { useEffect, useMemo, useRef } from 'react';
import type { BorderSide, ExcelCellStyle, MergedCell, PageBlock } from '../../model/types';
import { BODY_W, BODY_H } from '../../model/sheetGeometry';

interface Props {
  block: PageBlock;
  /** Vertical space (px) consumed above the range by the orange title band. */
  reservedTop?: number;
}

// Small insets so the range never touches the sheet frame / title block.
const PAD_X = 10;
const PAD_Y = 10;
const DEFAULT_COL = 64;
const DEFAULT_ROW = 20;
// A small range is grown to use the full printable body width, up to this cap,
// so front-matter tables fill the page instead of floating tiny in the corner.
const GROW_CAP = 1.85;

/** Map an Excel border side spec to a CSS border shorthand. */
function borderCss(side?: BorderSide): string | undefined {
  if (!side || !side.style) return undefined;
  const color = side.color || '#000000';
  switch (side.style) {
    case 'hair':
    case 'thin':
      return `1px solid ${color}`;
    case 'medium':
    case 'mediumDashed':
      return `2px solid ${color}`;
    case 'thick':
      return `3px solid ${color}`;
    case 'double':
      return `3px double ${color}`;
    case 'dashed':
      return `1px dashed ${color}`;
    case 'dotted':
      return `1px dotted ${color}`;
    default:
      return `1px solid ${color}`;
  }
}

function cellCss(st: ExcelCellStyle | undefined, rowH: number): React.CSSProperties {
  const s: React.CSSProperties = {
    height: rowH,
    padding: '0 3px',
    overflow: 'hidden',
    verticalAlign:
      st?.vAlign === 'top' ? 'top' : st?.vAlign === 'bottom' ? 'bottom' : 'middle',
  };
  if (!st) {
    s.whiteSpace = 'nowrap';
    return s;
  }
  if (st.bold) s.fontWeight = 700;
  if (st.italic) s.fontStyle = 'italic';
  if (st.underline) s.textDecoration = 'underline';
  if (st.fontSize) s.fontSize = Math.round((st.fontSize as number) * 4 / 3);
  if (st.fontName) s.fontFamily = st.fontName;
  if (st.fontColor) s.color = st.fontColor;
  if (st.fill) s.backgroundColor = st.fill;

  s.textAlign =
    st.hAlign === 'center'
      ? 'center'
      : st.hAlign === 'right'
        ? 'right'
        : st.hAlign === 'justify'
          ? 'justify'
          : 'left';

  s.whiteSpace = st.wrap ? 'normal' : 'nowrap';
  if (st.wrap) s.wordBreak = 'break-word';
  if (st.indent) s.paddingLeft = 3 + st.indent * 8;

  const rot = st.rotation ?? 0;
  if (rot === 255) {
    s.writingMode = 'vertical-rl';
  } else if (rot === 90) {
    s.writingMode = 'vertical-rl';
    s.transform = 'rotate(180deg)';
  } else if (rot === -90 || rot === 270) {
    s.writingMode = 'vertical-rl';
  } else if (rot) {
    s.transform = `rotate(${-rot}deg)`;
  }

  const b = st.borders;
  if (b) {
    const top = borderCss(b.top);
    const right = borderCss(b.right);
    const bottom = borderCss(b.bottom);
    const left = borderCss(b.left);
    if (top) s.borderTop = top;
    if (right) s.borderRight = right;
    if (bottom) s.borderBottom = bottom;
    if (left) s.borderLeft = left;
  }
  return s;
}

/**
 * Excel Exact Range renderer. Reproduces the source worksheet range as a real
 * table using the exact column widths, row heights, merged cells, fills,
 * borders, fonts, alignment and vertical text carried on the block. Nothing is
 * restyled with app defaults; the range is scaled proportionally to fit the
 * printable body (no scrollbars, no distortion).
 */
export default function ExcelRangeRenderer({ block, reservedTop = 0 }: Props) {
  const grid = block.grid ?? [];
  const styles = block.styles ?? {};
  const colWidths = block.colWidths ?? [];
  const rowHeights = block.rowHeights ?? [];
  const merges: MergedCell[] = block.mergedCells ?? [];
  const scaleMode = block.scaleMode ?? 'fit_body';

  const nRows = grid.length;
  const nCols = useMemo(
    () => Math.max(colWidths.length, ...(grid.length ? grid.map((r) => r.length) : [0])),
    [grid, colWidths],
  );

  const naturalW = useMemo(() => {
    let w = 0;
    for (let c = 0; c < nCols; c += 1) w += colWidths[c] ?? DEFAULT_COL;
    return Math.max(1, w);
  }, [colWidths, nCols]);

  // Merged-cell bookkeeping: covered cells are skipped, top-left carries spans.
  const { covered, spanAt } = useMemo(() => {
    const cov = new Set<string>();
    const span = new Map<string, { rs: number; cs: number }>();
    for (const m of merges) {
      for (let r = m.startRow; r <= m.endRow; r += 1) {
        for (let c = m.startCol; c <= m.endCol; c += 1) {
          if (r === m.startRow && c === m.startCol) continue;
          cov.add(`${r}:${c}`);
        }
      }
      span.set(`${m.startRow}:${m.startCol}`, {
        rs: m.endRow - m.startRow + 1,
        cs: m.endCol - m.startCol + 1,
      });
    }
    return { covered: cov, spanAt: span };
  }, [merges]);

  const fitRef = useRef<HTMLDivElement | null>(null);
  const tableRef = useRef<HTMLTableElement | null>(null);

  useEffect(() => {
    const wrap = fitRef.current;
    const table = tableRef.current;
    if (!wrap || !table) return;
    let raf = 0;
    let last = -1;
    const fit = () => {
      // Measure the real container so grow-to-fill fits inside whatever padding
      // chain wraps the range (.np / .np-xr), never clipping on the right.
      const container = wrap.parentElement;
      const containerW = container?.clientWidth ?? BODY_W;
      const availW = Math.max(1, containerW - PAD_X * 2);
      const availH = BODY_H - PAD_Y * 2 - Math.max(0, reservedTop);
      const w = table.scrollWidth || naturalW;
      const h = table.scrollHeight || 1;
      const sw = availW / w;
      const sh = availH / h;
      // Fit-to-body: grow small ranges to fill the width (up to GROW_CAP) while
      // staying within the available height; shrink oversized ranges to fit.
      const scale =
        scaleMode === 'fit_width'
          ? Math.min(GROW_CAP, sw)
          : Math.min(GROW_CAP, sw, sh);
      if (Math.abs(scale - last) < 0.003) return;
      last = scale;
      wrap.style.setProperty('--xr-scale', String(scale));
    };
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(fit);
    };
    fit();
    const ro = new ResizeObserver(schedule);
    ro.observe(table);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [naturalW, nRows, nCols, scaleMode, grid, reservedTop]);

  if (!nRows || !nCols) {
    return <div className="np np-empty">No source range data.</div>;
  }

  return (
    <div className="np-xr">
      <div className="np-xr-fit" ref={fitRef}>
        <table
          className="np-xr-table"
          ref={tableRef}
          data-block-id={block.id}
          style={{ width: naturalW }}
        >
          <colgroup>
            {Array.from({ length: nCols }, (_, c) => (
              <col key={c} style={{ width: colWidths[c] ?? DEFAULT_COL }} />
            ))}
          </colgroup>
          <tbody>
            {grid.map((row, r) => (
              <tr key={r} style={{ height: rowHeights[r] ?? DEFAULT_ROW }}>
                {Array.from({ length: nCols }, (_, c) => {
                  if (covered.has(`${r}:${c}`)) return null;
                  const span = spanAt.get(`${r}:${c}`);
                  const st = styles[`${r}:${c}`];
                  return (
                    <td
                      key={c}
                      rowSpan={span?.rs}
                      colSpan={span?.cs}
                      style={cellCss(st, rowHeights[r] ?? DEFAULT_ROW)}
                    >
                      {row[c] ?? ''}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
