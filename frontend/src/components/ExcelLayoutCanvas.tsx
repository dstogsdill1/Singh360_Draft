import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ExcelLayoutModel, ExcelLayoutTable, PageModel } from '../model/types';
import '../styles/excelLayout.css';

const PAGE_W = 1632;
const PAGE_H = 1056;
const ORANGE = '#F4B183';

interface ParsedTable {
  rows: string[][];
  columnWidths?: number[];
  rowHeights?: number[];
  merges?: ExcelLayoutTable['merges'];
  cellStyles?: ExcelLayoutTable['cellStyles'];
}

function cssColor(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed && trimmed !== 'transparent' && trimmed !== 'rgba(0, 0, 0, 0)' ? trimmed : undefined;
}

export function parseHtmlTable(html: string): ParsedTable {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const table = doc.querySelector('table');
  if (!table) return { rows: [] };
  const rows: string[][] = [];
  const merges: ExcelLayoutTable['merges'] = [];
  const cellStyles: NonNullable<ExcelLayoutTable['cellStyles']> = {};
  const occupied = new Set<string>();
  const columnWidths: number[] = [];
  const rowHeights: number[] = [];
  Array.from(table.rows).forEach((row, rowIndex) => {
    rows[rowIndex] ||= [];
    rowHeights[rowIndex] = parseFloat(row.style.height || row.getAttribute('height') || '') || 28;
    let columnIndex = 0;
    Array.from(row.cells).forEach((cell) => {
      while (occupied.has(`${rowIndex}:${columnIndex}`)) columnIndex += 1;
      const rowSpan = Math.max(1, cell.rowSpan || 1);
      const colSpan = Math.max(1, cell.colSpan || 1);
      rows[rowIndex][columnIndex] = (cell.textContent || '').trim();
      const inline = cell.style;
      const fontSize = parseFloat(inline.fontSize || '');
      cellStyles[`${rowIndex}:${columnIndex}`] = {
        fill: cssColor(inline.backgroundColor),
        fontColor: cssColor(inline.color),
        fontSize: Number.isFinite(fontSize) ? fontSize * 0.75 : undefined,
        bold: /bold|[6-9]00/.test(inline.fontWeight),
        align: ['center', 'right'].includes(inline.textAlign) ? inline.textAlign as 'center' | 'right' : 'left',
        wrap: inline.whiteSpace !== 'nowrap',
        borderStyle: inline.borderStyle === 'none' ? 'none' : 'thin',
      };
      const width = parseFloat(inline.width || cell.getAttribute('width') || '');
      if (Number.isFinite(width)) columnWidths[columnIndex] = Math.max(columnWidths[columnIndex] || 0, width);
      for (let r = rowIndex; r < rowIndex + rowSpan; r += 1) {
        for (let c = columnIndex; c < columnIndex + colSpan; c += 1) occupied.add(`${r}:${c}`);
      }
      if (rowSpan > 1 || colSpan > 1) merges.push({
        startRow: rowIndex, startCol: columnIndex,
        endRow: rowIndex + rowSpan - 1, endCol: columnIndex + colSpan - 1,
      });
      columnIndex += colSpan;
    });
  });
  const columns = Math.max(1, ...rows.map((row) => row.length));
  rows.forEach((row) => { while (row.length < columns) row.push(''); });
  const fallback = (parseFloat(table.style.width || table.getAttribute('width') || '') || 900) / columns;
  return {
    rows,
    merges,
    cellStyles,
    columnWidths: Array.from({ length: columns }, (_, column) => columnWidths[column] || fallback),
    rowHeights,
  };
}

function parseDelimited(text: string): ParsedTable {
  const lines = text.replace(/\r/g, '').split('\n').filter((line) => line.length);
  if (!lines.length) return { rows: [] };
  const delimiter = lines.some((line) => line.includes('\t')) ? '\t' : ',';
  return { rows: lines.map((line) => line.split(delimiter).map((value) => value.trim())) };
}

function newTable(parsed: ParsedTable, selected?: ExcelLayoutTable): ExcelLayoutTable {
  const rows = parsed.rows;
  const columns = Math.max(1, ...rows.map((row) => row.length));
  const x = selected?.x ?? 96;
  const y = selected ? selected.y + selected.height + 24 : 96;
  const naturalWidth = parsed.columnWidths?.reduce((sum, value) => sum + value, 0) || 900;
  const naturalHeight = 28 + (parsed.rowHeights?.reduce((sum, value) => sum + value, 0) || rows.length * 28);
  return {
    id: `xl_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    x, y, width: naturalWidth, height: Math.max(110, naturalHeight),
    rows, columnWidths: parsed.columnWidths || Array.from({ length: columns }, () => 900 / columns),
    rowHeights: parsed.rowHeights || Array.from({ length: rows.length }, () => 28), merges: parsed.merges || [], cellStyles: parsed.cellStyles, title: 'TABLE TITLE',
    titleStyle: { fill: ORANGE, fontColor: '#000000', fontSize: 14, bold: true, align: 'center', wrap: true, borderStyle: 'thin' },
    headerStyle: { fill: '#D9EAF7', fontColor: '#000000', fontSize: 10, bold: true, align: 'center', wrap: true, borderStyle: 'thin' },
    bodyStyle: { fill: '#FFFFFF', fontColor: '#000000', fontSize: 10, align: 'left', wrap: true, borderStyle: 'thin' },
    keepTogether: false, splitRows: true, repeatTitle: true, repeatHeaders: true,
  };
}

interface Props {
  page: PageModel;
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
  exporting?: boolean;
  overlay?: boolean;
}

export default function ExcelLayoutCanvas({ page, onPatchPage, exporting, overlay = false }: Props) {
  const layout = page.excelLayout!;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [history, setHistory] = useState<ExcelLayoutModel[]>([]);
  const [future, setFuture] = useState<ExcelLayoutModel[]>([]);
  const clipboard = useRef<ExcelLayoutTable | null>(null);
  const drag = useRef<{ id: string; x: number; y: number; ox: number; oy: number } | null>(null);
  const [guides, setGuides] = useState<{ x?: number; y?: number }>({});
  const selected = layout.tables.find((table) => table.id === selectedId);
  const pageCount = useMemo(() => Math.max(1, ...layout.tables.map((table) =>
    Math.ceil((table.y + table.height) / layout.pageHeight))), [layout]);

  const commit = useCallback((next: ExcelLayoutModel) => {
    setHistory((items) => [...items.slice(-49), layout]);
    setFuture([]);
    onPatchPage(page.id, { excelLayout: next });
  }, [layout, onPatchPage, page.id]);

  const patchSelected = (patch: Partial<ExcelLayoutTable>) => {
    if (!selectedId) return;
    commit({ ...layout, tables: layout.tables.map((table) => table.id === selectedId ? { ...table, ...patch } : table) });
  };
  const addRows = useCallback((parsed: ParsedTable) => {
    if (!parsed.rows.length) return;
    const table = newTable(parsed, selected);
    commit({ ...layout, tables: [...layout.tables, table] });
    setSelectedId(table.id);
  }, [commit, layout, selected]);

  useEffect(() => {
    const onPaste = (event: ClipboardEvent) => {
      if (exporting) return;
      const html = event.clipboardData?.getData('text/html') || '';
      const text = event.clipboardData?.getData('text/plain') || '';
      const parsed = html ? parseHtmlTable(html) : parseDelimited(text);
      if (parsed.rows.length && (html.includes('<table') || text.includes('\t') || text.includes(','))) {
        event.preventDefault();
        event.stopImmediatePropagation();
        addRows(parsed);
      }
    };
    window.addEventListener('paste', onPaste, true);
    return () => window.removeEventListener('paste', onPaste, true);
  }, [addRows, exporting]);

  const undo = () => {
    const prior = history[history.length - 1]; if (!prior) return;
    setFuture((items) => [layout, ...items]); setHistory((items) => items.slice(0, -1));
    onPatchPage(page.id, { excelLayout: prior });
  };
  const redo = () => {
    const next = future[0]; if (!next) return;
    setHistory((items) => [...items, layout]); setFuture((items) => items.slice(1));
    onPatchPage(page.id, { excelLayout: next });
  };
  const copy = () => { clipboard.current = selected ? structuredClone(selected) : null; };
  const paste = () => {
    if (!clipboard.current) return;
    const clone = structuredClone(clipboard.current);
    clone.id = `xl_${Date.now().toString(36)}`; clone.x += 24; clone.y += 24;
    commit({ ...layout, tables: [...layout.tables, clone] }); setSelectedId(clone.id);
  };
  const duplicate = () => { copy(); paste(); };
  const remove = () => {
    if (!selectedId) return;
    commit({ ...layout, tables: layout.tables.filter((table) => table.id !== selectedId) }); setSelectedId(null);
  };

  return (
    <div
      className={`excel-layout-root ${overlay ? 'overlay' : ''}`}
      data-testid="excel-layout-canvas"
      data-action="excel-layout-canvas"
      data-help-id="excelLayout.table"
      aria-label="Excel Layout canvas"
      tabIndex={0}
      onPointerMove={(event) => {
        if (!drag.current) return;
        const dx = event.clientX - drag.current.x, dy = event.clientY - drag.current.y;
        const snap = layout.snapSize || 8;
        const x = Math.round((drag.current.ox + dx) / snap) * snap;
        const y = Math.round((drag.current.oy + dy) / snap) * snap;
        const centeredX = selected && Math.abs(x + selected.width / 2 - PAGE_W / 2) < snap;
        const centeredY = selected && Math.abs((y % PAGE_H) + selected.height / 2 - PAGE_H / 2) < snap;
        setGuides({ x: centeredX ? PAGE_W / 2 : undefined, y: centeredY ? Math.floor(y / PAGE_H) * PAGE_H + PAGE_H / 2 : undefined });
        patchSelected({ x: centeredX && selected ? PAGE_W / 2 - selected.width / 2 : x, y: centeredY && selected ? Math.floor(y / PAGE_H) * PAGE_H + PAGE_H / 2 - selected.height / 2 : y });
      }}
      onPointerUp={() => { drag.current = null; setGuides({}); }}>
      {!exporting && <div className="excel-layout-toolbar">
        <button onClick={undo} disabled={!history.length}>Undo</button><button onClick={redo} disabled={!future.length}>Redo</button>
        <button onClick={copy} disabled={!selected}>Copy</button><button onClick={paste} disabled={!clipboard.current}>Paste</button>
        <button onClick={duplicate} disabled={!selected}>Duplicate</button><button onClick={remove} disabled={!selected}>Delete</button>
        <button onClick={() => addRows({ rows: [['COLUMN A', 'COLUMN B'], ['', '']] })}>New Table</button>
        <button disabled={!selected} onClick={() => selected && patchSelected({ x: 48, width: PAGE_W - 96 })}>Fit to Page Width</button>
        <button disabled={!selected} onClick={() => selected && patchSelected({ splitRows: true, height: Math.max(selected.height, selected.rowHeights.reduce((sum, value) => sum + value, 0) + 28) })}>Continue on Next Page</button>
        <label>Tab color <input aria-label="Workbook tab color" type="color" value={layout.tabColor || '#F4B183'} onChange={(e) => commit({ ...layout, tabColor: e.target.value })} /></label>
      </div>}
      {Array.from({ length: pageCount }, (_, index) => <div key={index} className="excel-layout-page" style={{ top: index * PAGE_H }}>
        <span className="excel-layout-page-label">Page {index + 1}</span><div className="excel-print-boundary" />
      </div>)}
      {guides.x != null && <div className="excel-align-guide vertical" style={{ left: guides.x }} />}
      {guides.y != null && <div className="excel-align-guide horizontal" style={{ top: guides.y }} />}
      {layout.tables.map((table) => {
        const covered = new Set<string>();
        const spanAt = new Map<string, { rowSpan: number; colSpan: number }>();
        table.merges.forEach((merge) => {
          spanAt.set(`${merge.startRow}:${merge.startCol}`, { rowSpan: merge.endRow - merge.startRow + 1, colSpan: merge.endCol - merge.startCol + 1 });
          for (let row = merge.startRow; row <= merge.endRow; row += 1) for (let column = merge.startCol; column <= merge.endCol; column += 1) {
            if (row !== merge.startRow || column !== merge.startCol) covered.add(`${row}:${column}`);
          }
        });
        return <div key={table.id} data-table-id={table.id}
          className={`excel-layout-table ${selectedId === table.id ? 'selected' : ''}`}
          style={{ left: table.x, top: table.y, width: table.width, minHeight: table.height }}
          onClick={(e) => { e.stopPropagation(); setSelectedId(table.id); }}>
          <div className="excel-layout-title" style={{ background: table.titleStyle.fill, color: table.titleStyle.fontColor, fontSize: table.titleStyle.fontSize, fontWeight: table.titleStyle.bold ? 700 : 400, textAlign: table.titleStyle.align }}
            onPointerDown={(event) => { setSelectedId(table.id); drag.current = { id: table.id, x: event.clientX, y: event.clientY, ox: table.x, oy: table.y }; }}
            contentEditable={!exporting} suppressContentEditableWarning onBlur={(e) => patchSelected({ title: e.currentTarget.textContent || '' })}>{table.title}</div>
          <table className="excel-layout-grid" style={{ width: table.width }}><colgroup>{table.columnWidths.map((width, index) => <col key={index} style={{ width }} />)}</colgroup><tbody>
            {table.rows.map((row, ri) => <tr className={ri === 0 ? 'header' : ''} key={ri} style={{ height: table.rowHeights[ri] || 28 }}>
              {Array.from({ length: table.columnWidths.length }, (_, ci) => {
                if (covered.has(`${ri}:${ci}`)) return null;
                const span = spanAt.get(`${ri}:${ci}`);
                const cellStyle = table.cellStyles?.[`${ri}:${ci}`];
                return <td key={ci} rowSpan={span?.rowSpan} colSpan={span?.colSpan} className="excel-layout-cell" style={{
                  background: cellStyle?.fill,
                  color: cellStyle?.fontColor,
                  fontSize: cellStyle?.fontSize,
                  fontWeight: cellStyle?.bold ? 700 : undefined,
                  textAlign: cellStyle?.align,
                  whiteSpace: cellStyle?.wrap === false ? 'nowrap' : 'pre-wrap',
                }} contentEditable={!exporting} suppressContentEditableWarning
                onDoubleClick={(event) => event.currentTarget.focus()}
                onBlur={(e) => { const rows = table.rows.map((r) => [...r]); while (rows[ri].length <= ci) rows[ri].push(''); rows[ri][ci] = e.currentTarget.textContent || ''; patchSelected({ rows }); }}>{row[ci] || ''}</td>;
              })}
            </tr>)}
          </tbody></table>
          {!exporting && selectedId === table.id && <div className="excel-layout-properties">
            <label>Title <input value={table.title} onChange={(e) => patchSelected({ title: e.target.value })} /></label>
            <label>Title fill <input aria-label="Title fill" type="color" value={table.titleStyle.fill || ORANGE} onChange={(e) => patchSelected({ titleStyle: { ...table.titleStyle, fill: e.target.value } })} /></label>
            <label>Title color <input aria-label="Title font color" type="color" value={table.titleStyle.fontColor || '#000000'} onChange={(e) => patchSelected({ titleStyle: { ...table.titleStyle, fontColor: e.target.value } })} /></label>
            <label>Title size <input aria-label="Title font size" type="number" value={table.titleStyle.fontSize || 14} onChange={(e) => patchSelected({ titleStyle: { ...table.titleStyle, fontSize: Number(e.target.value) } })} /></label>
            <label><input aria-label="Title bold" type="checkbox" checked={!!table.titleStyle.bold} onChange={(e) => patchSelected({ titleStyle: { ...table.titleStyle, bold: e.target.checked } })} />Title Bold</label>
            <label>Title align <select aria-label="Title alignment" value={table.titleStyle.align || 'center'} onChange={(e) => patchSelected({ titleStyle: { ...table.titleStyle, align: e.target.value as 'left' | 'center' | 'right' } })}><option>left</option><option>center</option><option>right</option></select></label>
            <label>Header fill <input aria-label="Header fill" type="color" value={table.headerStyle.fill || '#D9EAF7'} onChange={(e) => patchSelected({ headerStyle: { ...table.headerStyle, fill: e.target.value } })} /></label>
            <label>Body fill <input aria-label="Body fill" type="color" value={table.bodyStyle.fill || '#FFFFFF'} onChange={(e) => patchSelected({ bodyStyle: { ...table.bodyStyle, fill: e.target.value } })} /></label>
            <label>Alt fill <input aria-label="Alternating fill" type="color" value={table.alternatingFill || '#F2F2F2'} onChange={(e) => patchSelected({ alternatingFill: e.target.value })} /></label>
            <label>Border <select aria-label="Border style" value={table.bodyStyle.borderStyle || 'thin'} onChange={(e) => patchSelected({ bodyStyle: { ...table.bodyStyle, borderStyle: e.target.value as 'none' | 'thin' | 'medium' } })}><option>none</option><option>thin</option><option>medium</option></select></label>
            <label><input aria-label="Wrap body cells" type="checkbox" checked={table.bodyStyle.wrap !== false} onChange={(e) => patchSelected({ bodyStyle: { ...table.bodyStyle, wrap: e.target.checked } })} />Wrap</label>
            <label>Row height <input aria-label="Body row height" type="number" value={table.rowHeights[1] || 28} onChange={(e) => patchSelected({ rowHeights: table.rowHeights.map((height, index) => index ? Number(e.target.value) : height) })} /></label>
            <label>Width <input aria-label="Table width" type="number" value={table.width} onChange={(e) => patchSelected({ width: Math.max(120, Number(e.target.value)) })} /></label>
            <label>Height <input aria-label="Table height" type="number" value={table.height} onChange={(e) => patchSelected({ height: Math.max(60, Number(e.target.value)) })} /></label>
            <label>Column 1 <input aria-label="Column 1 width" type="number" value={table.columnWidths[0] || 40} onChange={(e) => patchSelected({ columnWidths: [Math.max(20, Number(e.target.value)), ...table.columnWidths.slice(1)] })} /></label>
            <label><input type="checkbox" checked={table.keepTogether} onChange={(e) => patchSelected({ keepTogether: e.target.checked })} />Keep Together</label>
            <label><input type="checkbox" checked={table.splitRows} onChange={(e) => patchSelected({ splitRows: e.target.checked })} />Split Rows</label>
            <label><input type="checkbox" checked={table.repeatTitle} onChange={(e) => patchSelected({ repeatTitle: e.target.checked })} />Repeat Title</label>
            <label><input type="checkbox" checked={table.repeatHeaders} onChange={(e) => patchSelected({ repeatHeaders: e.target.checked })} />Repeat Headers</label>
            <button onClick={() => patchSelected({ merges: [{ startRow: 0, startCol: 0, endRow: 0, endCol: Math.max(0, table.columnWidths.length - 1) }] })}>Merge Across</button>
            <button onClick={() => patchSelected({ merges: [] })}>Unmerge</button>
          </div>}
        </div>;
      })}
    </div>
  );
}
