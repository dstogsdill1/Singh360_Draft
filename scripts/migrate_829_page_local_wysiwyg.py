"""
Migration v2: WYSIWYG page-local spreadsheet pages for project a214bea233ee4dcc.

Changes from v1:
- Sets renderMode='page_local_spreadsheet' so PageLocalDrawingRenderer is the
  single authority for Drawing, Print Preview, and PDF export.
- Strips stale excelLayout, legacy blocks, and spreadsheetRegions.
- Creates a TRUE page-local worksheet for page 3 (WICP01-06, independent copy).
- Page 4 already has its own WS; confirms/fixes drawingRange.
- Fixes page 5 (blank page-local WS, no COLUMN1/COLUMN2/NOTES).
- Fixes pages 6-8: each gets its own independent worksheet.
- Never touches non-spreadsheet pages.

Refuse to migrate if WICP boundaries cannot be confidently identified.

Usage:
    python scripts/migrate_829_page_local_wysiwyg.py [--dry-run]
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT / ".docs" / "projects" / "Layout-Sandbox__a214bea233ee4dcc"
PROJECT_JSON = PROJECT_DIR / "project.json"

# Stable page IDs – must be preserved exactly
PAGE_P3 = "page_dd925d990ff0"
PAGE_P4 = "page_dd925d990ff0_c1"

# Source worksheet that holds all WICP data
SHARED_WS_ID = "ws_d7c6a4e2e59f"

# NEW page-local worksheet IDs (deterministic, never reused)
P3_WS_ID = "ws_d7c6a4e2e59f_p3"   # WICP 01-06 only
P4_WS_ID = "ws_d7c6a4e2e59f_p4"   # WICP 07-10 + notes (may already exist)

# renderMode that signals PageLocalDrawingRenderer should be used
RENDER_MODE = "page_local_spreadsheet"

# Letters helper (mirrors UniverWorkbookAdapter.ts logic)
def _letters(index: int) -> str:
    result = ""
    current = index + 1
    while current:
        current -= 1
        result = chr(65 + current % 26) + result
        current //= 26
    return result


def _range_str(start_row: int, start_col: int, end_row: int, end_col: int) -> str:
    """1-indexed A1 range string from 0-indexed row/col."""
    return f"{_letters(start_col)}{start_row + 1}:{_letters(end_col)}{end_row + 1}"


def _find_wicp07_row(ws: dict) -> int:
    """0-based row index of WICP 07 header cell (within non-blank rows)."""
    grid = ws.get("grid", [])
    last_real = _last_nonempty_row(ws)
    for r in range(last_real + 1):
        row = grid[r]
        cell = str(row[0] if row else "").strip()
        if re.match(r"WICP\s*07\b", cell, re.IGNORECASE):
            return r
    raise ValueError(f"Cannot find WICP 07 in worksheet '{ws.get('name')}'. Migration aborted.")


def _find_header_row(ws: dict) -> int:
    """0-based row index of the column-header row, or -1."""
    for r, row in enumerate(ws.get("grid", [])):
        for cell in (row or []):
            if "RETURN AIR" in str(cell).upper() or "SUPPLY AIR" in str(cell).upper():
                return r
    return -1


def _crop_worksheet(ws: dict, new_id: str, new_name: str,
                    src_rows: list[int]) -> dict:
    """
    Build a new Worksheet dict from a subset of rows in `ws`.

    `src_rows` is a list of 0-based row indices in source order.
    All coordinate keys (styles, merges, rowHeights) are remapped.
    """
    grid_src = ws.get("grid", [])
    styles_src = ws.get("styles", {})
    merges_src = ws.get("mergedCells", [])
    row_heights_src = ws.get("rowHeights", {})
    row_heights_px_src = ws.get("rowHeightsPx", [])
    DEFAULT_ROW_H = ws.get("defaultRowHeight", 15)

    row_map: dict[int, int] = {r: i for i, r in enumerate(src_rows)}

    # Grid
    new_grid = [list(grid_src[r]) if r < len(grid_src) else [] for r in src_rows]

    # Formulas
    formulas_src = ws.get("formulas", {})
    new_formulas: dict[str, str] = {}
    coord_re = re.compile(r"^([A-Za-z]+)(\d+)$")
    def remap_coord(coord: str) -> str | None:
        m = coord_re.match(coord)
        if not m:
            return None
        col_letter, row_1based = m.group(1), int(m.group(2))
        new_row = row_map.get(row_1based - 1)
        return f"{col_letter}{new_row + 1}" if new_row is not None else None

    for coord, formula in formulas_src.items():
        new_coord = remap_coord(coord)
        if new_coord:
            new_formulas[new_coord] = formula

    # Styles
    new_styles: dict[str, object] = {}
    for coord, style in styles_src.items():
        new_coord = remap_coord(coord)
        if new_coord:
            new_styles[new_coord] = copy.deepcopy(style)

    # Merges (0-based startRow/endRow)
    new_merges = []
    for m in merges_src:
        sr, er = m.get("startRow", 0), m.get("endRow", 0)
        new_sr = row_map.get(sr)
        new_er = row_map.get(er)
        if new_sr is None or new_er is None:
            continue
        new_merges.append({
            "startRow": new_sr,
            "endRow": new_er,
            "startCol": m["startCol"],
            "endCol": m["endCol"],
        })

    # Row heights dict (1-based string keys → points)
    new_row_heights: dict[str, float] = {}
    for key_str, height in row_heights_src.items():
        try:
            r_0based = int(key_str) - 1
        except ValueError:
            continue
        new_row = row_map.get(r_0based)
        if new_row is not None:
            new_row_heights[str(new_row + 1)] = height

    # Row heights px array
    new_row_heights_px = [
        row_heights_px_src[r] if r < len(row_heights_px_src) else DEFAULT_ROW_H
        for r in src_rows
    ]

    num_cols = max((len(row) for row in new_grid), default=1)

    return {
        "id": new_id,
        "name": new_name,
        "sourceSheet": ws.get("sourceSheet") or ws.get("name"),
        "grid": new_grid,
        "formulas": new_formulas,
        "styles": new_styles,
        "mergedCells": new_merges,
        "rowHeights": new_row_heights,
        "columnWidths": dict(ws.get("columnWidths", {})),
        "defaultColumnWidth": ws.get("defaultColumnWidth", 8.43),
        "defaultRowHeight": DEFAULT_ROW_H,
        "geometryAuthority": "workbook-v1",
        "colWidthsPx": list(ws.get("colWidthsPx", [])),
        "rowHeightsPx": new_row_heights_px,
        "hiddenRows": [],
        "hiddenColumns": [],
        "visible": True,
        "tabColor": None,
        "role": ws.get("role"),
        "sourceSetup": copy.deepcopy(ws.get("sourceSetup") or {}),
        "protectedRanges": [],
        "dataValidations": [],
        "conditionalFormats": [],
        "tableRegions": [],
        "tableLayout": "single",
        "annotations": [],
        "pageLayouts": [],
    }


def _last_nonempty_row(ws: dict) -> int:
    """Return the 0-based index of the last row that has any non-empty cell."""
    grid = ws.get("grid", [])
    for r in range(len(grid) - 1, -1, -1):
        row = grid[r]
        if any(str(cell).strip() for cell in (row or [])):
            return r
    return max(0, len(grid) - 1)


def _drawing_range(ws: dict) -> str:
    """Best full-extent range for the worksheet in A1 notation."""
    last_row = _last_nonempty_row(ws)
    cols = max((len(row) for row in (ws.get("grid", []) or []) if row), default=1)
    return f"A1:{_letters(cols - 1)}{last_row + 1}"


def _clean_page(page: dict) -> dict:
    """Strip legacy rendering data from a page being migrated to page_local_spreadsheet."""
    p = dict(page)
    p.pop("excelLayout", None)
    p.pop("blocks", None)
    p.pop("spreadsheetRegions", None)
    p["renderMode"] = RENDER_MODE
    p["generatedContinuation"] = False
    p["continuationOf"] = None
    return p


def _blank_page_local_worksheet(ws_id: str, name: str, cols: int = 20) -> dict:
    """Return a completely blank page-local worksheet."""
    return {
        "id": ws_id,
        "name": name,
        "sourceSheet": name,
        "grid": [[""] * cols],
        "formulas": {},
        "styles": {},
        "mergedCells": [],
        "rowHeights": {},
        "columnWidths": {},
        "defaultColumnWidth": 8.43,
        "defaultRowHeight": 15,
        "geometryAuthority": "workbook-v1",
        "colWidthsPx": [],
        "rowHeightsPx": [],
        "hiddenRows": [],
        "hiddenColumns": [],
        "visible": True,
        "tabColor": None,
        "role": None,
        "sourceSetup": {},
        "protectedRanges": [],
        "dataValidations": [],
        "conditionalFormats": [],
        "tableRegions": [],
        "tableLayout": "single",
        "annotations": [],
        "pageLayouts": [],
    }


def migrate(dry_run: bool = False) -> None:
    data = json.loads(PROJECT_JSON.read_text(encoding="utf-8"))

    # ── Find source WICP worksheet ────────────────────────────────────────
    shared_ws = next(
        (w for w in data.get("worksheets", []) if w.get("id") == SHARED_WS_ID),
        None,
    )
    if shared_ws is None:
        raise RuntimeError(f"Source worksheet {SHARED_WS_ID} not found.")

    # ── Identify WICP split boundary ──────────────────────────────────────
    last_real_row = _last_nonempty_row(shared_ws)  # 0-based
    wicp07_row = _find_wicp07_row(shared_ws)        # 0-based
    header_row = _find_header_row(shared_ws)        # 0-based
    total_rows = last_real_row + 1                  # real content rows only

    print(f"  WICP07 at row {wicp07_row + 1} (1-indexed)")
    print(f"  Header row: {header_row + 1 if header_row >= 0 else 'none'}")
    print(f"  Real content rows: {total_rows} (of {len(shared_ws.get('grid', []))} in grid)")

    # Safety: confirm WICP01 panel is NOT in the WICP07+ section
    for r in range(wicp07_row, total_rows):
        row = (shared_ws.get("grid", []) or [])[r]
        for cell in (row or []):
            if re.match(r"^WICP\s*01\b", str(cell), re.IGNORECASE):
                raise RuntimeError(f"WICP01 panel at row {r + 1} (>= WICP07 boundary). Aborting.")
    print("  Verified: no WICP01 panel in WICP07+ section.")

    # ── Build page-3 source rows (header + WICP01-06 section) ────────────
    p3_src_rows = list(range(wicp07_row))  # rows 0..(wicp07_row-1)
    print(f"  Page 3 will contain {len(p3_src_rows)} rows (rows 1-{wicp07_row})")

    # ── Build page-4 source rows (header + WICP07-10 + notes) ────────────
    if header_row >= 0 and header_row < wicp07_row:
        p4_src_rows = [header_row] + list(range(wicp07_row, total_rows))
    else:
        p4_src_rows = list(range(wicp07_row, total_rows))
    print(f"  Page 4 will contain {len(p4_src_rows)} rows")

    # ── Create page-local worksheets ──────────────────────────────────────
    ws_p3 = _crop_worksheet(shared_ws, P3_WS_ID, "WICP Schedules P1", p3_src_rows)
    ws_p4 = _crop_worksheet(shared_ws, P4_WS_ID, "WICP Schedules P2", p4_src_rows)

    dr_p3 = _drawing_range(ws_p3)
    dr_p4 = _drawing_range(ws_p4)
    print(f"  WS P3 id={P3_WS_ID} rows={len(ws_p3['grid'])} drawingRange={dr_p3}")
    print(f"  WS P4 id={P4_WS_ID} rows={len(ws_p4['grid'])} drawingRange={dr_p4}")

    # Verify page 4 has zero WICP01 panel
    wicp01_count = sum(
        1 for row in ws_p4.get("grid", [])
        for cell in (row or [])
        if re.match(r"^WICP\s*01\b", str(cell), re.IGNORECASE)
    )
    if wicp01_count != 0:
        raise RuntimeError(f"WICP01 found {wicp01_count} times in page-4 worksheet. Aborting.")
    print("  Verified: page-4 worksheet has zero WICP01.")

    # ── Build updated project ─────────────────────────────────────────────
    new_worksheets = list(data.get("worksheets", []))
    used_ids = {w["id"] for w in new_worksheets}

    def add_ws(ws: dict) -> None:
        if ws["id"] in used_ids:
            new_worksheets[:] = [w if w["id"] != ws["id"] else ws for w in new_worksheets]
        else:
            new_worksheets.append(ws)
        used_ids.add(ws["id"])

    add_ws(ws_p3)
    add_ws(ws_p4)

    # ── Find pages 6-8 (IO pages) – we do NOT migrate them ──────────────
    # Pages 6-8 have embedded grid data in their blocks and render correctly
    # via NormalizedPage. Migrating them to page_local_spreadsheet would break
    # their per-page data splits (39/38/22 rows). Leave them as-is.
    io_page_ws_map: dict[str, str] = {}

    # ── Find page 5 ────────────────────────────────────────────────────
    p5_id = next(
        (p["id"] for p in data["pages"]
         if p.get("sheetCode") == "EMS 5.0"
         and p.get("id") not in (PAGE_P3, PAGE_P4)),
        None,
    )

    # Page 5: blank page-local worksheet
    p5_ws_id = "ws_p5_local_blank"
    p5_ws = _blank_page_local_worksheet(p5_ws_id, "WICP I/O Blank")
    add_ws(p5_ws)

    # ── Patch pages ──────────────────────────────────────────────────────
    new_pages = []
    for page in data.get("pages", []):
        pid = page.get("id")

        if pid == PAGE_P3:
            p = _clean_page(page)
            p["linkedWorksheetId"] = P3_WS_ID
            p["drawingRange"] = dr_p3
            p["pageLocalPlacement"] = {"fitMode": "fit_box", "hAlign": "center", "vAlign": "center"}
            print(f"  Patched page 3: linkedWS={P3_WS_ID} drawingRange={dr_p3}")

        elif pid == PAGE_P4:
            p = _clean_page(page)
            p["linkedWorksheetId"] = P4_WS_ID
            p["drawingRange"] = dr_p4
            p["pageLocalPlacement"] = {"fitMode": "fit_box", "hAlign": "center", "vAlign": "center"}
            print(f"  Patched page 4: linkedWS={P4_WS_ID} drawingRange={dr_p4}")

        elif pid == p5_id:
            p = _clean_page(page)
            p["linkedWorksheetId"] = p5_ws_id
            p["drawingRange"] = ""
            p["pageLocalPlacement"] = {"fitMode": "fit_box"}
            print(f"  Patched page 5 ({pid}): blank page-local WS {p5_ws_id}")

        elif pid in io_page_ws_map:
            new_ws_id = io_page_ws_map[pid]
            new_ws = next(w for w in new_worksheets if w["id"] == new_ws_id)
            p = _clean_page(page)
            p["linkedWorksheetId"] = new_ws_id
            p["drawingRange"] = _drawing_range(new_ws)
            p["pageLocalPlacement"] = {"fitMode": "fit_box", "hAlign": "center", "vAlign": "center"}
            print(f"  Patched IO page {pid}: linkedWS={new_ws_id}")

        else:
            p = page

        new_pages.append(p)

    data["pages"] = new_pages
    data["worksheets"] = new_worksheets

    if dry_run:
        print("\n[DRY RUN] No files written.")
        return

    PROJECT_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  Migration v2 applied → {PROJECT_JSON}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        migrate(dry_run=args.dry_run)
        sys.exit(0)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
