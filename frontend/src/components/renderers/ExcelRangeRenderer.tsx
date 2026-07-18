import { useEffect, useMemo, useRef, useState } from 'react';
import type { BorderSide, ExcelCellStyle, MergedCell, PageBlock } from '../../model/types';
import { BODY_W } from '../../model/sheetGeometry';

interface Props {
  block: PageBlock;
  /** Vertical space (px) consumed above the orange title band. */
  reservedTop?: number;
  /** When true (PDF export), suppress diagnostics and editing controls. */
  exporting?: boolean;
  /** Directly edit the printable normalized table, not the raw worksheet. */
  layoutEditing?: boolean;
  onChange?: (patch: Partial<PageBlock>) => void;
}

const PAD_X = 10;
const PAD_Y = 10;
const DEFAULT_COL = 64;
const DEFAULT_ROW = 20;
const GROW_CAP = 1.85;
const MIN_BOTTOM_GAP = 20;
const SAFE_FIT_HEIGHT = 700;
const MIN_LAYOUT_COL = 36;
const MAX_LAYOUT_COL = 900;
const MIN_LAYOUT_ROW = 18;
const MAX_LAYOUT_ROW = 300;

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
    overflowWrap: opts?.nowrap ? 'normal' : 'anywhere',
    wordBreak: opts?.nowrap ? 'keep-all' : 'break-word',
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
  if (bodyFontPx) s.fontSize = bodyFontPx;
  return s;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(value)));
}

function mergedMaps(merges: MergedCell[]) {
  const covered = new Set<string>();
  const spanAt = new Map<string, { rs: number; cs: number }>();
  for (const merge of merges) {
    for (let r = merge.startRow; r <= merge.endRow; r += 1) {
      for (let c = merge.startCol; c <= merge.endCol; c += 1) {
        if (r === merge.startRow && c === merge.startCol) continue;
        covered.add(`${r}:${c}`);
      }
    }
    spanAt.set(`${merge.startRow}:${merge.startCol}`, {
      rs: merge.endRow - merge.startRow + 1,
      cs: merge.endCol - merge.startCol + 1,
    });
  }
  return { covered, spanAt };
}

function autoRowHeights(
  grid: string[][],
  widths: number[],
  merges: MergedCell[],
  fontPx: number,
): number[] {
  const { covered, spanAt } = mergedMaps(merges);
  const nCols = Math.max(widths.length, ...(grid.length ? grid.map((row) => row.length) : [0]));
  const lineHeight = Math.max(13, Math.round(fontPx * 1.25));

  return grid.map((row, r) => {
    let maxLines = 1;
    let hasText = false;
    for (let c = 0; c < nCols; c += 1) {
      if (covered.has(`${r}:${c}`)) continue;
      const text = String(row[c] ?? '').trim();
      if (!text) continue;
      hasText = true;
      const span = spanAt.get(`${r}:${c}`)?.cs ?? 1;
      const cellWidth = Array.from({ length: span }, (_, offset) => widths[c + offset] ?? DEFAULT_COL)
        .reduce((sum, width) => sum + width, 0);
      const charsPerLine = Math.max(8, Math.floor(Math.max(36, cellWidth - 10) / Math.max(5.2, fontPx * 0.52)));
      const words = text.split(/\s+/);
      let lines = 1;
      let used = 0;
      for (const word of words) {
        if (used && used + word.length + 1 > charsPerLine) {
          lines += 1;
          used = word.length;
        } else {
          used += word.length + (used ? 1 : 0);
        }
      }
      maxLines = Math.max(maxLines, lines);
    }
    if (!hasText) return MIN_LAYOUT_ROW;
    return clamp(lineHeight * Math.min(maxLines, 14) + 8, MIN_LAYOUT_ROW, MAX_LAYOUT_ROW);
  });
}

type DragState = {
  kind: 'col' | 'row';
  index: number;
  startClient: number;
  startValue: number;
  /** Includes the table fit scale and the outer sheet viewport scale. */
  effectiveScale: number;
};

export default function ExcelRangeRenderer({
  block,
  reservedTop = 0,
  exporting = false,
  layoutEditing = false,
  onChange,
}: Props) {
  const grid = block.grid ?? [];
  const styles = block.styles ?? {};
  const sourceColWidths = block.colWidths ?? [];
  const sourceRowHeights = block.rowHeights ?? [];
  const merges: MergedCell[] = block.mergedCells ?? [];
  const scaleMode = block.scaleMode ?? 'fit_body';

  const nRows = grid.length;
  const nCols = useMemo(
    () => Math.max(sourceColWidths.length, ...(grid.length ? grid.map((row) => row.length) : [0])),
    [grid, sourceColWidths],
  );

  const [draftCols, setDraftCols] = useState<number[]>(sourceColWidths);
  const [draftRows, setDraftRows] = useState<number[]>(sourceRowHeights);
  const draftColsRef = useRef<number[]>(sourceColWidths);
  const draftRowsRef = useRef<number[]>(sourceRowHeights);
  const dragRef = useRef<DragState | null>(null);
  const scaleValueRef = useRef(1);

  useEffect(() => {
    if (dragRef.current) return;
    const cols = Array.from({ length: nCols }, (_, index) => sourceColWidths[index] ?? DEFAULT_COL);
    const rows = Array.from({ length: nRows }, (_, index) => sourceRowHeights[index] ?? DEFAULT_ROW);
    draftColsRef.current = cols;
    draftRowsRef.current = rows;
    setDraftCols(cols);
    setDraftRows(rows);
  }, [sourceColWidths, sourceRowHeights, nCols, nRows]);

  const colWidths = layoutEditing ? draftCols : sourceColWidths;
  const rowHeights = layoutEditing ? draftRows : sourceRowHeights;

  const naturalW = useMemo(() => {
    let width = 0;
    for (let c = 0; c < nCols; c += 1) width += colWidths[c] ?? DEFAULT_COL;
    return Math.max(1, width);
  }, [colWidths, nCols]);
  const naturalH = useMemo(
    () => Math.max(1, Array.from({ length: nRows }, (_, r) => rowHeights[r] ?? DEFAULT_ROW).reduce((sum, value) => sum + value, 0)),
    [rowHeights, nRows],
  );

  const { covered, spanAt } = useMemo(() => mergedMaps(merges), [merges]);
  const fitRef = useRef<HTMLDivElement | null>(null);
  const tableRef = useRef<HTMLTableElement | null>(null);
  const nowrapCols = useMemo(
    () => new Set((block.nowrapColumns as number[] | undefined) ?? []),
    [block.nowrapColumns],
  );

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const client = drag.kind === 'col' ? event.clientX : event.clientY;
      const delta = (client - drag.startClient) / Math.max(0.05, drag.effectiveScale);
      if (drag.kind === 'col') {
        const next = [...draftColsRef.current];
        next[drag.index] = clamp(drag.startValue + delta, MIN_LAYOUT_COL, MAX_LAYOUT_COL);
        draftColsRef.current = next;
        setDraftCols(next);
      } else {
        const next = [...draftRowsRef.current];
        next[drag.index] = clamp(drag.startValue + delta, MIN_LAYOUT_ROW, MAX_LAYOUT_ROW);
        draftRowsRef.current = next;
        setDraftRows(next);
      }
    };

    const onUp = () => {
      if (!dragRef.current) return;
      dragRef.current = null;
      onChange?.({
        colWidths: [...draftColsRef.current],
        rowHeights: [...draftRowsRef.current],
        pageLayoutManual: true,
        noGrow: false,
        scaleMode: 'fit_body',
      });
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [onChange]);

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
      const width = table.scrollWidth || naturalW;
      const height = table.scrollHeight || naturalH;
      const sw = availW / width;
      const sh = availH / height;
      const growCap = block.noGrow ? 1 : GROW_CAP;
      const scale =
        scaleMode === 'fit_width'
          ? Math.min(growCap, sw)
          : Math.min(growCap, sw, sh);
      scaleValueRef.current = scale;
      if (Math.abs(scale - last) < 0.003) return;
      last = scale;
      wrap.style.setProperty('--xr-scale', String(scale));
      wrap.style.width = `${Math.ceil(width * scale)}px`;
      wrap.style.height = `${Math.ceil(height * scale)}px`;
    };
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(fit);
    };
    fit();
    const observer = new ResizeObserver(schedule);
    observer.observe(table);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [naturalW, naturalH, nRows, nCols, scaleMode, grid, reservedTop, block.noGrow]);

  if (!nRows || !nCols) {
    return <div className="np np-empty">No source range data.</div>;
  }

  const beginColDrag = (index: number, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const rect = tableRef.current?.getBoundingClientRect();
    const effectiveScale = rect && naturalW > 0 ? rect.width / naturalW : scaleValueRef.current;
    dragRef.current = {
      kind: 'col',
      index,
      startClient: event.clientX,
      startValue: draftColsRef.current[index] ?? DEFAULT_COL,
      effectiveScale,
    };
  };

  const beginRowDrag = (index: number, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const rect = tableRef.current?.getBoundingClientRect();
    const effectiveScale = rect && naturalH > 0 ? rect.height / naturalH : scaleValueRef.current;
    dragRef.current = {
      kind: 'row',
      index,
      startClient: event.clientY,
      startValue: draftRowsRef.current[index] ?? DEFAULT_ROW,
      effectiveScale,
    };
  };

  const setFont = (delta: number) => {
    const next = clamp(Number(block.bodyFontPx ?? 12) + delta, 8, 18);
    onChange?.({ bodyFontPx: next, bodyFontPt: Math.round(next * 0.75 * 100) / 100, pageLayoutManual: true });
  };

  const fitRows = () => {
    const rows = autoRowHeights(grid, draftColsRef.current, merges, Number(block.bodyFontPx ?? 12));
    draftRowsRef.current = rows;
    setDraftRows(rows);
    onChange?.({
      rowHeights: rows,
      colWidths: [...draftColsRef.current],
      pageLayoutManual: true,
    });
  };

  let x = 0;
  const colHandles = Array.from({ length: nCols }, (_, c) => {
    x += colWidths[c] ?? DEFAULT_COL;
    return { index: c, offset: x };
  });
  let y = 0;
  const rowHandles = Array.from({ length: nRows }, (_, r) => {
    y += rowHeights[r] ?? DEFAULT_ROW;
    return { index: r, offset: y };
  });

  return (
    <div className={`np-xr ${layoutEditing ? 'xr-page-layout-editing' : ''}`}>
      {block.layoutWarnings?.length && !exporting ? (
        <div className="np-xr-warning">
          {block.layoutWarnings.join(' ')}
        </div>
      ) : null}

      {layoutEditing && !exporting ? (
        <div className="xr-page-layout-toolbar" data-noexport="1">
          <strong>Page Layout</strong>
          <span>Drag blue column and row lines directly on the finished sheet.</span>
          <button type="button" onClick={() => setFont(-1)}>Font −</button>
          <button type="button" onClick={() => setFont(1)}>Font +</button>
          <button type="button" onClick={fitRows}>Auto Row Heights</button>
        </div>
      ) : null}

      <div className="np-xr-fit" ref={fitRef}>
        <div
          className="xr-page-layout-surface"
          style={{ width: naturalW, height: naturalH }}
        >
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
                    const style = styles[`${r}:${c}`];
                    return (
                      <td
                        key={c}
                        rowSpan={span?.rs}
                        colSpan={span?.cs}
                        style={cellCss(style, rowHeights[r] ?? DEFAULT_ROW, block.bodyFontPx, {
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

          {layoutEditing && !exporting ? (
            <div className="xr-page-layout-handles" data-noexport="1">
              {colHandles.map(({ index, offset }) => (
                <button
                  key={`c-${index}`}
                  type="button"
                  className="xr-layout-col-handle"
                  style={{ left: offset - 4, height: naturalH }}
                  title={`Resize output column ${index + 1}`}
                  onMouseDown={(event: React.MouseEvent) => beginColDrag(index, event)}
                />
              ))}
              {rowHandles.map(({ index, offset }) => (
                <button
                  key={`r-${index}`}
                  type="button"
                  className="xr-layout-row-handle"
                  style={{ top: offset - 4, width: naturalW }}
                  title={`Resize output row ${index + 1}`}
                  onMouseDown={(event: React.MouseEvent) => beginRowDrag(index, event)}
                />
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
