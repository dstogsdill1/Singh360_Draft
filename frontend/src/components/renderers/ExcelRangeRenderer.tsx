import { useEffect, useMemo, useRef } from 'react';
import type { BorderSide, ExcelCellStyle, MergedCell, PageBlock } from '../../model/types';
import { BODY_W } from '../../model/sheetGeometry';

interface Props {
  block: PageBlock;
  /** Vertical space (px) consumed above the page body by the title band. */
  reservedTop?: number;
  /** When true (PDF export), suppress on-page diagnostic banners. */
  exporting?: boolean;
}

const PAD_X = 10;
const PAD_Y = 10;
const DEFAULT_COL = 64;
const DEFAULT_ROW = 20;
const GROW_CAP = 1.85;
const MIN_BOTTOM_GAP = 20;
const SAFE_FIT_HEIGHT = 700;
// .np has 48px horizontal padding and .np-xr has 10px horizontal padding.
const MIN_FILL_WIDTH = BODY_W - 118;

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

function cellCss(
  st: ExcelCellStyle | undefined,
  rowH: number,
  bodyFontPx?: number,
  opts?: { nowrap?: boolean },
): React.CSSProperties {
  // Source's Wrap/No Wrap flag is authoritative. Undefined/false means the
  // Excel cell is not wrapped; a normalized heuristic may not override it.
  const wraps = st?.wrap === true && !opts?.nowrap;
  const s: React.CSSProperties = {
    minHeight: rowH,
    padding: '2px 4px',
    verticalAlign:
      st?.vAlign === 'top' ? 'top' : st?.vAlign === 'bottom' ? 'bottom' : 'middle',
    whiteSpace: wraps ? 'pre-wrap' : 'pre',
    overflowWrap: wraps ? 'break-word' : 'normal',
    wordBreak: 'normal',
    overflow: 'hidden',
  };
  if (!st) {
    if (bodyFontPx) s.fontSize = bodyFontPx;
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
  if (bodyFontPx) s.fontSize = bodyFontPx;
  return s;
}

/**
 * Excel Exact Range renderer. It uses the source worksheet's widths, heights,
 * merges, fills, borders, fonts and wrap flags. When a table is narrower than
 * the printable body, only its widest column receives the unused space; this
 * keeps Step/ID columns narrow and lets Instructions/Notes use the page.
 */
export default function ExcelRangeRenderer({ block, reservedTop = 0, exporting = false }: Props) {
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

  const displayColWidths = useMemo(() => {
    const widths = Array.from({ length: nCols }, (_, c) => colWidths[c] ?? DEFAULT_COL);
    const sourceWidth = widths.reduce((sum, width) => sum + width, 0);
    if (widths.length && sourceWidth < MIN_FILL_WIDTH) {
      let flexColumn = 0;
      for (let c = 1; c < widths.length; c += 1) {
        if (widths[c] > widths[flexColumn]) flexColumn = c;
      }
      widths[flexColumn] += MIN_FILL_WIDTH - sourceWidth;
    }
    return widths;
  }, [colWidths, nCols]);

  const naturalW = useMemo(
    () => Math.max(1, displayColWidths.reduce((sum, width) => sum + width, 0)),
    [displayColWidths],
  );

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
  const nowrapCols = useMemo(
    () => new Set((block.nowrapColumns as number[] | undefined) ?? []),
    [block.nowrapColumns],
  );

  useEffect(() => {
    const wrap = fitRef.current;
    const table = tableRef.current;
    if (!wrap || !table) return;
    let raf = 0;
    let last = -1;
    const fit = () => {
      const container = wrap.parentElement;
      const containerW = container?.clientWidth ?? BODY_W;
      const availW = Math.max(1, containerW - PAD_X * 2);
      const availH = Math.max(1, SAFE_FIT_HEIGHT - PAD_Y * 2 - Math.max(0, reservedTop) - MIN_BOTTOM_GAP);
      const w = table.scrollWidth || naturalW;
      const h = table.scrollHeight || 1;
      const sw = availW / w;
      const sh = availH / h;
      const growCap = block.noGrow ? 1 : GROW_CAP;
      const scale =
        scaleMode === 'fit_width'
          ? Math.min(growCap, sw)
          : Math.min(growCap, sw, sh);
      if (Math.abs(scale - last) < 0.003) return;
      last = scale;
      wrap.style.setProperty('--xr-scale', String(scale));
      wrap.style.width = `${Math.ceil(w * scale)}px`;
      wrap.style.height = `${Math.ceil(h * scale)}px`;
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
  }, [naturalW, nRows, nCols, scaleMode, grid, reservedTop, block.noGrow]);

  if (!nRows || !nCols) {
    return <div className="np np-empty">No source range data.</div>;
  }

  return (
    <div className="np-xr">
      {block.layoutWarnings?.length && !exporting ? (
        <div className="np-xr-warning">
          {block.layoutWarnings.join(' ')}
        </div>
      ) : null}
      <div className="np-xr-fit" ref={fitRef}>
        <table
          className="np-xr-table"
          ref={tableRef}
          data-block-id={block.id}
          style={{ width: naturalW }}
        >
          <colgroup>
            {displayColWidths.map((width, c) => (
              <col key={c} style={{ width }} />
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
                      style={cellCss(st, rowHeights[r] ?? DEFAULT_ROW, block.bodyFontPx, {
                        nowrap: nowrapCols.has(c),
                      })}
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
