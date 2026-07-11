import { useEffect, useMemo, useRef } from 'react';
import type { BorderSide, ExcelCellStyle, MergedCell, PageBlock } from '../../model/types';
import { BODY_W } from '../../model/sheetGeometry';

interface Props {
  block: PageBlock;
  /** Vertical space (px) consumed above the range by the orange title band. */
  reservedTop?: number;
  /** When true (PDF export), suppress on-page diagnostic banners. */
  exporting?: boolean;
}

// Small insets so the range never touches the sheet frame / title block.
const PAD_X = 10;
const PAD_Y = 10;
const DEFAULT_COL = 64;
const DEFAULT_ROW = 20;
// A small range is grown to use the full printable body width, up to this cap,
// so front-matter tables fill the page instead of floating tiny in the corner.
const GROW_CAP = 1.85;
// FINAL RENDER POLISH 4G, Phase C: the previous fit-to-body scale used 100% of
// the available height with zero margin, so any table that needed to shrink
// landed flush against the title block (and a hair of rounding could clip a
// row). Reserve a fixed safety gap so a table never touches the boundary.
const MIN_BOTTOM_GAP = 20;
// FINAL RELEASE CLEANUP 4H+SA38, Phase H fix: BODY_H (866) models the full
// on-screen sheet body used for page-frame layout, but is taller than the
// backend's proven-safe render budget (core/page_composer.py
// SAFE_BODY_BUDGET = 700). A short, narrow table (e.g. a 2-column
// instruction page) grow-scales width-first up to GROW_CAP, which also
// scales its height by the same factor — using the optimistic BODY_H for
// that height check let the scaled table overflow the page's real
// overflow:hidden body and silently drop its bottom rows (confirmed via a
// real SA31 export: only row 1 of 5 painted onto the PDF page). Match the
// backend's conservative budget for this safety-critical height check only;
// BODY_H itself is untouched everywhere else it's used for page-frame
// layout, so this does not touch the wider, already-flagged 720/866
// calibration mismatch.
const SAFE_FIT_HEIGHT = 700;

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

function cellCss(
  st: ExcelCellStyle | undefined,
  rowH: number,
  bodyFontPx?: number,
  opts?: { nowrap?: boolean },
): React.CSSProperties {
  const s: React.CSSProperties = {
    minHeight: rowH,
    padding: '2px 4px',
    verticalAlign:
      st?.vAlign === 'top' ? 'top' : st?.vAlign === 'bottom' ? 'bottom' : 'middle',
    whiteSpace: opts?.nowrap ? 'nowrap' : 'normal',
    overflowWrap: opts?.nowrap ? 'normal' : 'normal',
    wordBreak: opts?.nowrap ? 'keep-all' : 'normal',
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

  // Normalized output tables always wrap as real table geometry. The backend
  // sizes columns first, then rows are allowed to expand before final scaling.
  if (st.wrap) s.overflowWrap = 'break-word';
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
  // Phase D: an explicit block-level body font (instruction_table pages)
  // always wins over the per-cell Excel font size captured on import.
  if (bodyFontPx) s.fontSize = bodyFontPx;
  return s;
}

/**
 * Excel Exact Range renderer. Reproduces the source worksheet range as a real
 * table using the exact column widths, row heights, merged cells, fills,
 * borders, fonts, alignment and vertical text carried on the block. Nothing is
 * restyled with app defaults; the range is scaled proportionally to fit the
 * printable body (no scrollbars, no distortion).
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
      // Measure the real container so grow-to-fill fits inside whatever padding
      // chain wraps the range (.np / .np-xr), never clipping on the right.
      const container = wrap.parentElement;
      const containerW = container?.clientWidth ?? BODY_W;
      const availW = Math.max(1, containerW - PAD_X * 2);
      const availH = Math.max(1, SAFE_FIT_HEIGHT - PAD_Y * 2 - Math.max(0, reservedTop) - MIN_BOTTOM_GAP);
      const w = table.scrollWidth || naturalW;
      const h = table.scrollHeight || 1;
      const sw = availW / w;
      const sh = availH / h;
      // A block marked noGrow (e.g. a narrow 2-column instruction table)
      // never stretches past its natural size — only shrinks if it doesn't
      // fit (see noGrow doc comment in model/types.ts for why).
      const growCap = block.noGrow ? 1 : GROW_CAP;
      // Fit-to-body: grow small ranges to fill the width (up to growCap) while
      // staying within the available height; shrink oversized ranges to fit.
      const scale =
        scaleMode === 'fit_width'
          ? Math.min(growCap, sw)
          : Math.min(growCap, sw, sh);
      if (Math.abs(scale - last) < 0.003) return;
      last = scale;
      wrap.style.setProperty('--xr-scale', String(scale));
      // `transform: scale()` only changes paint size, not layout size, so the
      // parent `.np-xr` (auto-height, overflow:hidden) would still size itself
      // from the pre-transform box. When scale > 1 (a narrow table grown to
      // fill the body width) that leaves the visually-larger content taller
      // than its own too-small ancestor box, silently clipping the bottom
      // rows. Give the wrapper explicit post-scale dimensions so the ancestor
      // always sizes to the real, visible footprint — never crops, never
      // leaves a shrink-mode gap either.
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
