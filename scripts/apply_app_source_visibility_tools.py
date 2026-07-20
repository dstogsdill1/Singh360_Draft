"""Install app-only worksheet visibility tools in Singh360 Draft.

This patch intentionally does not read, modify, copy, hash, or re-import any
Excel workbook. Hidden rows, columns, and cell contents are stored only in the
Singh360 project worksheet JSON.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


class PatchError(RuntimeError):
    pass


VISIBILITY_HELPER = '\n/** Apply Singh360 app-only row/column/cell visibility before normalized render.\n * The underlying Worksheet grid remains intact and Excel export stays unchanged.\n */\nfunction applySourceVisibility(ws: Worksheet): Worksheet {\n  const sourceGrid = ws.grid ?? [];\n  const nRows = sourceGrid.length;\n  const nCols = Math.max(0, ...sourceGrid.map((row) => row.length));\n  const hiddenRows = new Set(\n    (ws.hiddenRows ?? []).filter((row) => Number.isInteger(row) && row >= 0 && row < nRows),\n  );\n  const hiddenColumns = new Set(\n    (ws.hiddenColumns ?? []).filter((col) => Number.isInteger(col) && col >= 0 && col < nCols),\n  );\n  const hiddenCells = new Set(ws.hiddenCells ?? []);\n\n  let visibleRows = Array.from({ length: nRows }, (_, row) => row).filter((row) => !hiddenRows.has(row));\n  let visibleColumns = Array.from({ length: nCols }, (_, col) => col).filter((col) => !hiddenColumns.has(col));\n\n  if (!visibleRows.length && nRows) visibleRows = [0];\n  if (!visibleColumns.length && nCols) visibleColumns = [0];\n\n  const rowMap = new Map(visibleRows.map((row, index) => [row, index]));\n  const colMap = new Map(visibleColumns.map((col, index) => [col, index]));\n\n  const grid = visibleRows.map((row) =>\n    visibleColumns.map((col) => (\n      hiddenCells.has(`${row}:${col}`) ? \'\' : cellText(sourceGrid[row]?.[col])\n    )),\n  );\n\n  const styles: Record<string, ExcelCellStyle> = {};\n  for (const [key, value] of Object.entries(ws.styles ?? {})) {\n    const parsed = parseA1(key);\n    if (!parsed) continue;\n    const nextRow = rowMap.get(parsed.r);\n    const nextCol = colMap.get(parsed.c);\n    if (nextRow === undefined || nextCol === undefined) continue;\n    if (hiddenCells.has(`${parsed.r}:${parsed.c}`)) continue;\n    styles[a1(nextRow, nextCol)] = value;\n  }\n\n  const mergedCells: MergedCell[] = [];\n  for (const merge of ws.mergedCells ?? []) {\n    const rows = Array.from(\n      { length: merge.endRow - merge.startRow + 1 },\n      (_, index) => merge.startRow + index,\n    );\n    const columns = Array.from(\n      { length: merge.endCol - merge.startCol + 1 },\n      (_, index) => merge.startCol + index,\n    );\n    if (!rows.every((row) => rowMap.has(row)) || !columns.every((col) => colMap.has(col))) {\n      continue;\n    }\n    mergedCells.push({\n      startRow: rowMap.get(merge.startRow) as number,\n      startCol: colMap.get(merge.startCol) as number,\n      endRow: rowMap.get(merge.endRow) as number,\n      endCol: colMap.get(merge.endCol) as number,\n    });\n  }\n\n  return {\n    ...ws,\n    grid,\n    styles,\n    mergedCells,\n    colWidthsPx: visibleColumns.map((col) => ws.colWidthsPx?.[col] ?? DEFAULT_COL),\n    rowHeightsPx: visibleRows.map((row) => ws.rowHeightsPx?.[row] ?? DEFAULT_ROW),\n  };\n}\n'
CSS_ADD = '\n\n/* App-only Source visibility controls. Hidden content stays in project source\n   and the original Excel workbook; only Singh360 Source/Normalized/PDF omit it. */\n.gx-hidden-summary {\n  display: inline-flex;\n  align-items: center;\n  min-height: 24px;\n  padding: 2px 8px;\n  border: 1px solid #9eb4c8;\n  border-radius: 4px;\n  background: #eaf3fb;\n  color: #244f71;\n  font-size: 10px;\n  font-weight: 700;\n  white-space: nowrap;\n}\n.gx-cell.gx-app-hidden-cell {\n  background-color: #eef2f5 !important;\n  background-image:\n    repeating-linear-gradient(\n      135deg,\n      transparent 0,\n      transparent 5px,\n      rgba(72, 91, 108, 0.12) 5px,\n      rgba(72, 91, 108, 0.12) 7px\n    );\n}\n.gx-cell.gx-app-hidden-cell .gx-cell-text {\n  color: transparent !important;\n  user-select: none;\n}\n'


def find_repo(argument: str | None) -> Path:
    candidates: list[Path] = []
    if argument:
        candidates.append(Path(argument))
    candidates.extend(
        [
            Path.cwd(),
            Path.home()
            / "OneDrive - Homeland Development Services LLC"
            / "Desktop"
            / "Singh360_SmartDraw",
            Path.home() / "Desktop" / "Singh360_SmartDraw",
        ]
    )
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if (
            (candidate / "server.py").is_file()
            and (candidate / "frontend" / "src" / "App.tsx").is_file()
        ):
            return candidate
    raise PatchError("Singh360_SmartDraw repository was not found.")


def backup_files(repo: Path, files: list[Path]) -> tuple[Path, dict[Path, Path]]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = repo / ".docs" / "patch_backups" / f"app_source_visibility_{stamp}"
    mapping: dict[Path, Path] = {}
    for source in files:
        if not source.is_file():
            raise PatchError(f"Required source file is missing: {source}")
        target = backup / source.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        mapping[source] = target
    return backup, mapping


def restore(mapping: dict[Path, Path]) -> None:
    for target, source in mapping.items():
        if source.is_file():
            shutil.copy2(source, target)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise PatchError(f"Could not locate {label}.")
    return text.replace(old, new, 1)


def patch_types(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = """  colWidthsPx?: number[];
  rowHeightsPx?: number[];
  sourceSheet?: string;
"""
    new = """  colWidthsPx?: number[];
  rowHeightsPx?: number[];
  /** App-only visibility. These never alter the original Excel workbook. */
  hiddenRows?: number[];
  hiddenColumns?: number[];
  /** Hidden cell coordinates use zero-based "row:column" keys. */
  hiddenCells?: string[];
  sourceSheet?: string;
"""
    text = replace_once(text, old, new, "Worksheet visibility fields")
    path.write_text(text, encoding="utf-8")


def patch_excel_range(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    parse_marker = """function parseA1(key: string): { r: number; c: number } | null {
  const m = /^([A-Z]+)(\\d+)$/.exec(key);
  if (!m) return null;
  return { c: colIndex(m[1]), r: Number(m[2]) - 1 };
}
"""
    if "function applySourceVisibility(ws: Worksheet)" not in text:
        if parse_marker not in text:
            raise PatchError("Could not locate excelRange parseA1 helper.")
        text = text.replace(parse_marker, parse_marker + VISIBILITY_HELPER, 1)

    start = text.find("export function buildExcelRangeBlock(ws: Worksheet, blockId: string): PageBlock {")
    end_marker = "\n}\n\n/** Slice a full block"
    end = text.find(end_marker, start)
    if start < 0 or end < 0:
        raise PatchError("Could not locate buildExcelRangeBlock.")
    end += 2
    block = text[start:end]
    if "const visibleWs = applySourceVisibility(ws);" not in block:
        block = block.replace(
            "  const src = ws.grid ?? [];",
            "  const visibleWs = applySourceVisibility(ws);\n  const src = visibleWs.grid ?? [];",
            1,
        )
        replacements = {
            "Object.entries(ws.styles ?? {})": "Object.entries(visibleWs.styles ?? {})",
            "(ws.mergedCells ?? [])": "(visibleWs.mergedCells ?? [])",
            "ws.colWidthsPx?.[c]": "visibleWs.colWidthsPx?.[c]",
            "ws.rowHeightsPx?.[r]": "visibleWs.rowHeightsPx?.[r]",
            "sourceSheet: ws.sourceSheet || ws.name": "sourceSheet: visibleWs.sourceSheet || visibleWs.name",
            "sourceRange: ws.sourceRange || ''": "sourceRange: visibleWs.sourceRange || ''",
        }
        for old, new in replacements.items():
            if old not in block:
                raise PatchError(f"Could not locate excelRange build marker: {old}")
            block = block.replace(old, new)
        text = text[:start] + block + text[end:]

    refresh_start = text.find("export function refreshPageFromSource(page: PageModel, ws: Worksheet): PageModel {")
    refresh_end_marker = "\n}\n\n/** For cover pages"
    refresh_end = text.find(refresh_end_marker, refresh_start)
    if refresh_start < 0 or refresh_end < 0:
        raise PatchError("Could not locate refreshPageFromSource.")
    refresh_end += 2
    refresh = text[refresh_start:refresh_end]
    if "const visibleWs = applySourceVisibility(ws);" not in refresh:
        refresh = refresh.replace(
            "export function refreshPageFromSource(page: PageModel, ws: Worksheet): PageModel {\n",
            "export function refreshPageFromSource(page: PageModel, ws: Worksheet): PageModel {\n  const visibleWs = applySourceVisibility(ws);\n",
            1,
        )
        refresh = refresh.replace("const grid = ws.grid ?? [];", "const grid = visibleWs.grid ?? [];")
        refresh = refresh.replace("(ws.grid ?? [])", "(visibleWs.grid ?? [])")
        text = text[:refresh_start] + refresh + text[refresh_end:]

    path.write_text(text, encoding="utf-8")


def patch_raw_grid(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    dimensions_marker = """  const colWidthsPx = worksheet?.colWidthsPx ?? [];
  const rowHeightsPx = worksheet?.rowHeightsPx ?? [];

"""
    dimensions_add = dimensions_marker + """  const hiddenRows = useMemo(() => new Set(worksheet?.hiddenRows ?? []), [worksheet?.hiddenRows]);
  const hiddenColumns = useMemo(() => new Set(worksheet?.hiddenColumns ?? []), [worksheet?.hiddenColumns]);
  const hiddenCells = useMemo(() => new Set(worksheet?.hiddenCells ?? []), [worksheet?.hiddenCells]);

"""
    if "const hiddenRows = useMemo" not in text:
        text = replace_once(text, dimensions_marker, dimensions_add, "RawGrid visibility state")

    ncols_marker = """  const nCols = useMemo(
    () => Math.max(1, ...(grid.length ? grid.map((r) => r.length) : [1])),
    [grid],
  );

"""
    ncols_add = ncols_marker + """  const visibleRows = useMemo(() => {
    const rows = grid.map((_, row) => row).filter((row) => !hiddenRows.has(row));
    return rows.length ? rows : (grid.length ? [0] : []);
  }, [grid, hiddenRows]);

  const visibleCols = useMemo(() => {
    const cols = Array.from({ length: nCols }, (_, col) => col).filter((col) => !hiddenColumns.has(col));
    return cols.length ? cols : [0];
  }, [nCols, hiddenColumns]);

  const visibleGridRows = useMemo(
    () => visibleRows.map((r) => ({ r, row: grid[r] ?? [] })),
    [visibleRows, grid],
  );

"""
    if "const visibleRows = useMemo" not in text:
        text = replace_once(text, ncols_marker, ncols_add, "RawGrid visible row/column maps")

    old_display = """  const displayColWidths = useMemo(() => {
    const widths = Array.from({ length: nCols }, (_, c) => colWidthsPx[c] ?? DEFAULT_SOURCE_COL_W);
    const storedWidth = widths.reduce((sum, width) => sum + width, 0);
    if (widths.length && storedWidth < SOURCE_DATA_WIDTH) {
      let flexColumn = 0;
      for (let c = 1; c < widths.length; c += 1) {
        if (widths[c] > widths[flexColumn]) flexColumn = c;
      }
      widths[flexColumn] += SOURCE_DATA_WIDTH - storedWidth;
    }
    return widths;
  }, [colWidthsPx, nCols]);

  const sourceTableWidth = 36 + displayColWidths.reduce((sum, width) => sum + width, 0);
"""
    new_display = """  const displayColWidths = useMemo(() => {
    const widths = Array.from({ length: nCols }, (_, c) => colWidthsPx[c] ?? DEFAULT_SOURCE_COL_W);
    const storedWidth = visibleCols.reduce((sum, col) => sum + widths[col], 0);
    if (visibleCols.length && storedWidth < SOURCE_DATA_WIDTH) {
      let flexColumn = visibleCols[0];
      for (const col of visibleCols.slice(1)) {
        if (widths[col] > widths[flexColumn]) flexColumn = col;
      }
      widths[flexColumn] += SOURCE_DATA_WIDTH - storedWidth;
    }
    return widths;
  }, [colWidthsPx, nCols, visibleCols]);

  const sourceTableWidth = 36 + visibleCols.reduce((sum, col) => sum + displayColWidths[col], 0);
"""
    text = replace_once(text, old_display, new_display, "RawGrid visible column widths")

    selection_marker = """  const selectionLabel = formatSourceSelectionLabel(selCells());

"""
    visibility_actions = selection_marker + """  const hideColumns = () => {
    const rect = selRect();
    if (!rect || !worksheet) return;
    const selected = Array.from(
      { length: rect.c1 - rect.c0 + 1 },
      (_, index) => rect.c0 + index,
    );
    const next = new Set(worksheet.hiddenColumns ?? []);
    selected.forEach((col) => next.add(col));
    if (next.size >= nCols) {
      window.alert('At least one source column must remain visible.');
      return;
    }
    commit({ hiddenColumns: [...next].sort((a, b) => a - b) }, true);
    setSel(null);
  };

  const hideRows = () => {
    const rect = selRect();
    if (!rect || !worksheet) return;
    const selected = Array.from(
      { length: rect.r1 - rect.r0 + 1 },
      (_, index) => rect.r0 + index,
    );
    const next = new Set(worksheet.hiddenRows ?? []);
    selected.forEach((row) => next.add(row));
    if (next.size >= grid.length) {
      window.alert('At least one source row must remain visible.');
      return;
    }
    commit({ hiddenRows: [...next].sort((a, b) => a - b) }, true);
    setSel(null);
  };

  const hideSelectedCells = () => {
    if (!worksheet) return;
    const cells = selCells();
    if (!cells.length) return;
    const next = new Set(worksheet.hiddenCells ?? []);
    cells.forEach(({ r, c }) => next.add(cellKey(r, c)));
    commit({ hiddenCells: [...next].sort() }, true);
    setSel(null);
    setToggleCells(new Set());
  };

  const unhideAll = () => {
    if (!worksheet) return;
    if (
      !(worksheet.hiddenRows?.length)
      && !(worksheet.hiddenColumns?.length)
      && !(worksheet.hiddenCells?.length)
    ) return;
    commit({ hiddenRows: [], hiddenColumns: [], hiddenCells: [] }, true);
  };

  const hiddenSummary = [
    worksheet?.hiddenColumns?.length ? `${worksheet.hiddenColumns.length} col` : '',
    worksheet?.hiddenRows?.length ? `${worksheet.hiddenRows.length} row` : '',
    worksheet?.hiddenCells?.length ? `${worksheet.hiddenCells.length} cell` : '',
  ].filter(Boolean).join(' / ');

"""
    if "const hideColumns = () =>" not in text:
        text = replace_once(text, selection_marker, visibility_actions, "RawGrid visibility actions")

    toolbar_marker = """        {tb('Ins Col', () => commit(wsInsertCol(worksheet, anchorCol()), true), 'Insert column left of selection')}
        {tb('Del Col', deleteColumn, 'Delete selected column')}
        <span className="gx-tb-sep" />
        {tb('Fit Cols', autoFitCols, 'Auto-fit selected columns')}
"""
    toolbar_new = """        {tb('Ins Col', () => commit(wsInsertCol(worksheet, anchorCol()), true), 'Insert column left of selection')}
        {tb('Del Col', deleteColumn, 'Delete selected column')}
        <span className="gx-tb-sep" />
        {tb('Hide Col', hideColumns, 'Hide selected columns in Singh360 only; the Excel workbook is unchanged')}
        {tb('Hide Row', hideRows, 'Hide selected rows in Singh360 only; the Excel workbook is unchanged')}
        {tb('Hide Cells', hideSelectedCells, 'Hide selected cell contents in Singh360 only')}
        {tb('Unhide All', unhideAll, 'Restore every app-hidden row, column, and cell')}
        <span className="gx-hidden-summary" title="App-only hidden source content">
          {hiddenSummary ? `Hidden: ${hiddenSummary}` : 'App-only visibility'}
        </span>
        <span className="gx-tb-sep" />
        {tb('Fit Cols', autoFitCols, 'Auto-fit selected columns')}
"""
    if "Hide Col" not in text:
        text = replace_once(text, toolbar_marker, toolbar_new, "RawGrid hide toolbar")

    text = replace_once(
        text,
        """          {displayColWidths.map((width, c) => (
            <col key={c} style={{ width }} />
          ))}
""",
        """          {visibleCols.map((c) => (
            <col key={c} style={{ width: displayColWidths[c] }} />
          ))}
""",
        "RawGrid visible colgroup",
    )

    text = replace_once(
        text,
        """            {Array.from({ length: nCols }, (_, c) => (
              <th
""",
        """            {visibleCols.map((c) => (
              <th
""",
        "RawGrid visible column headers",
    )

    text = replace_once(
        text,
        """          {grid.map((row, r) => (
            <tr key={r} style={{ height: rowHeight(r) }}>
""",
        """          {visibleGridRows.map(({ row, r }) => (
            <tr key={r} style={{ height: rowHeight(r) }}>
""",
        "RawGrid visible rows",
    )

    text = replace_once(
        text,
        """              {Array.from({ length: nCols }, (_, c) => {
""",
        """              {visibleCols.map((c) => {
""",
        "RawGrid visible body columns",
    )

    edit_marker = """                const isEditing = editing?.r === r && editing?.c === c;
                const span = spanAt.get(cellKey(r, c));
"""
    edit_new = """                const isEditing = editing?.r === r && editing?.c === c;
                const isAppHidden = hiddenCells.has(cellKey(r, c));
                const span = spanAt.get(cellKey(r, c));
"""
    if "const isAppHidden =" not in text:
        text = replace_once(text, edit_marker, edit_new, "RawGrid hidden cell state")

    text = replace_once(
        text,
        """                    className={`gx-cell ${inSel(r, c) ? 'gx-sel' : ''}`}
""",
        """                    className={`gx-cell ${inSel(r, c) ? 'gx-sel' : ''} ${isAppHidden ? 'gx-app-hidden-cell' : ''}`}
""",
        "RawGrid hidden cell class",
    )

    text = replace_once(
        text,
        """                    onDoubleClick={() => {
                      setEditing({ r, c });
""",
        """                    onDoubleClick={() => {
                      if (isAppHidden) return;
                      setEditing({ r, c });
""",
        "RawGrid hidden cell editing guard",
    )

    text = replace_once(
        text,
        """                      <span className={`gx-cell-text ${wraps ? 'gx-wrap' : ''}`}>{grid[r]?.[c] ?? ''}</span>
""",
        """                      <span className={`gx-cell-text ${wraps ? 'gx-wrap' : ''}`}>
                        {isAppHidden ? '' : (grid[r]?.[c] ?? '')}
                      </span>
""",
        "RawGrid hidden cell content",
    )

    path.write_text(text, encoding="utf-8")


def patch_app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = """    setProjectSync((prev) => {
      if (!prev) return prev;
      const worksheets = prev.worksheets.map((ws) =>
        ws.id === wsId ? { ...ws, ...patch } : ws,
      );
      // Source edits update worksheet payload only — normalized pages refresh on
      // explicit Rebuild This Page From Source (or when leaving Source view).
      return { ...prev, worksheets };
    });
"""
    new = """    setProjectSync((prev) => {
      if (!prev) return prev;
      const worksheets = prev.worksheets.map((ws) =>
        ws.id === wsId ? { ...ws, ...patch } : ws,
      );
      const base = { ...prev, worksheets };
      if (!opts?.structural) {
        return base;
      }

      const linked = base.pages.filter((page) => page.linkedWorksheetId === wsId);
      if (linked.some((page) => page.renderMode === 'excel_exact')) {
        return { ...base, pages: regenerateExcelGroup(base, wsId) };
      }
      if (isCoverWorksheet(base, wsId)) {
        return applyCoverSourceTruth(base, wsId);
      }
      const updatedWorksheet = base.worksheets.find((ws) => ws.id === wsId);
      if (!updatedWorksheet) return base;
      return {
        ...base,
        pages: base.pages.map((page) =>
          page.linkedWorksheetId === wsId ? refreshPageFromSource(page, updatedWorksheet) : page,
        ),
      };
    });
"""
    text = replace_once(text, old, new, "App structural worksheet rebuild")
    path.write_text(text, encoding="utf-8")


def patch_css(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if ".gx-hidden-summary" not in text:
        text += CSS_ADD
    path.write_text(text, encoding="utf-8")


def verify(repo: Path) -> None:
    checks = {
        "worksheet fields": "hiddenColumns?: number[]" in (repo / "frontend/src/model/types.ts").read_text(encoding="utf-8"),
        "normalized visibility filter": "function applySourceVisibility(ws: Worksheet)" in (repo / "frontend/src/model/excelRange.ts").read_text(encoding="utf-8"),
        "source hide controls": "Hide Cells" in (repo / "frontend/src/components/renderers/RawGridRenderer.tsx").read_text(encoding="utf-8"),
        "structural rebuild": "const linked = base.pages.filter" in (repo / "frontend/src/App.tsx").read_text(encoding="utf-8"),
        "visibility CSS": ".gx-hidden-summary" in (repo / "frontend/src/styles/sheet.css").read_text(encoding="utf-8"),
    }
    for label, ok in checks.items():
        print(f"[{'OK' if ok else 'FAIL'}] {label}")
    failed = [label for label, ok in checks.items() if not ok]
    if failed:
        raise PatchError("Verification failed: " + ", ".join(failed))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="")
    args = parser.parse_args()

    repo = find_repo(args.repo or None)
    files = [
        repo / "frontend/src/model/types.ts",
        repo / "frontend/src/model/excelRange.ts",
        repo / "frontend/src/components/renderers/RawGridRenderer.tsx",
        repo / "frontend/src/App.tsx",
        repo / "frontend/src/styles/sheet.css",
    ]
    backup, mapping = backup_files(repo, files)
    print(f"Repository: {repo}")
    print(f"Source backup: {backup}")

    try:
        patch_types(files[0])
        patch_excel_range(files[1])
        patch_raw_grid(files[2])
        patch_app(files[3])
        patch_css(files[4])
        verify(repo)
    except Exception:
        print("[FAIL] Restoring every source file changed by this patch.")
        restore(mapping)
        raise

    print("[OK] App-only Source visibility tools installed.")
    print("[OK] No workbook was read, modified, copied, hashed, or re-imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
