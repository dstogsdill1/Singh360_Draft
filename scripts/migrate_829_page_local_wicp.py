"""
Migration script: page-local worksheet split for project a214bea233ee4dcc.

Splits the shared WICP worksheet (ws_d7c6a4e2e59f) into two independent
page-local worksheets so each drawing page owns its own data:

  page_dd925d990ff0  → ws_d7c6a4e2e59f      (rows 1-44: header + WICP01-06)
  page_dd925d990ff0_c1 → ws_d7c6a4e2e59f_p4 (NEW: header rows + WICP07-10)

The split is identified from ACTUAL cell values (WICP 07 appears at row 45,
1-indexed) — no row numbers are guessed.

Refuses to migrate if WICP boundaries cannot be confidently identified.

Usage:
    python scripts/migrate_829_page_local_wicp.py [--dry-run]
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

# Page IDs to migrate (must be preserved exactly)
PAGE_P3 = "page_dd925d990ff0"      # WICP 01-06
PAGE_P4 = "page_dd925d990ff0_c1"   # WICP 07-10

# Original shared worksheet ID
SHARED_WS_ID = "ws_d7c6a4e2e59f"

# New page-local worksheet ID for page 4
NEW_WS_ID = "ws_d7c6a4e2e59f_p4"


def _find_wicp07_row(ws: dict) -> int:
    """Return 0-based row index of WICP 07 header. Raises if not found."""
    for r, row in enumerate(ws.get("grid", [])):
        cell = str(row[0] if row else "").strip()
        if re.match(r"WICP\s*07", cell, re.IGNORECASE):
            return r
    raise ValueError(
        "Cannot identify WICP 07 boundary in worksheet "
        f"'{ws.get('name')}'. Migration aborted."
    )


def _find_header_row(ws: dict) -> int:
    """Return 0-based row index of the column-header row (RETURN/SUPPLY AIR SENSOR)."""
    for r, row in enumerate(ws.get("grid", [])):
        for cell in (row or []):
            if "RETURN AIR" in str(cell).upper() or "SUPPLY AIR" in str(cell).upper():
                return r
    return -1  # Not found; will use row 0


def _crop_worksheet(ws: dict, start_row: int, end_row: int, header_row: int) -> dict:
    """
    Return a NEW worksheet dict containing:
      row 0  = original header_row (column headers)
      rows 1+= original rows start_row..end_row-1

    All coordinates (styles, merges, rowHeights) are remapped.
    """
    grid_src = ws.get("grid", [])
    styles_src = ws.get("styles", {})
    merges_src = ws.get("mergedCells", [])
    row_heights_src = ws.get("rowHeights", {})

    # Build new row list: [header_row] + [start_row .. end_row-1]
    if header_row >= 0 and header_row < start_row:
        src_rows = [header_row] + list(range(start_row, end_row))
    else:
        src_rows = list(range(start_row, end_row))

    # Row mapping: src_row → new_row_index (0-based)
    row_map: dict[int, int] = {r: i for i, r in enumerate(src_rows)}
    new_row_count = len(src_rows)

    # Grid
    new_grid = []
    for r in src_rows:
        row = list(grid_src[r]) if r < len(grid_src) else []
        new_grid.append(row)

    # Styles — coordinate format is e.g. "A3", "B10"
    new_styles: dict[str, object] = {}
    coord_re = re.compile(r"^([A-Za-z]+)(\d+)$")
    for coord, style in styles_src.items():
        m = coord_re.match(coord)
        if not m:
            continue
        col_letter = m.group(1)
        row_1based = int(m.group(2))
        row_0based = row_1based - 1
        new_row = row_map.get(row_0based)
        if new_row is None:
            continue
        new_styles[f"{col_letter}{new_row + 1}"] = copy.deepcopy(style)

    # Merges — stored as {startRow, endRow, startCol, endCol} with 0-based rows
    new_merges = []
    for m in merges_src:
        sr, er = m.get("startRow", 0), m.get("endRow", 0)
        new_sr = row_map.get(sr)
        new_er = row_map.get(er)
        if new_sr is None or new_er is None:
            # Only include if the ENTIRE merge is within the new range
            continue
        new_merges.append({
            "startRow": new_sr,
            "endRow": new_er,
            "startCol": m["startCol"],
            "endCol": m["endCol"],
        })

    # Row heights — stored as {"1": height, "2": height, ...} with 1-based keys
    new_row_heights: dict[str, float] = {}
    for key_str, height in row_heights_src.items():
        try:
            row_1based = int(key_str)
        except ValueError:
            continue
        row_0based = row_1based - 1
        new_row = row_map.get(row_0based)
        if new_row is not None:
            new_row_heights[str(new_row + 1)] = height

    # Compute pixel arrays from source
    default_col_w = ws.get("defaultColumnWidth", 8.43)
    default_row_h = ws.get("defaultRowHeight", 15)
    col_widths_px = ws.get("colWidthsPx", [])
    row_heights_px = ws.get("rowHeightsPx", [])
    new_col_widths_px = list(col_widths_px)  # shared columns, same widths
    new_row_heights_px = [row_heights_px[r] if r < len(row_heights_px) else default_row_h
                          for r in src_rows]

    return {
        "id": NEW_WS_ID,
        "name": "WICP Schedules P2",
        "sourceSheet": ws.get("sourceSheet", ws.get("name")),
        "grid": new_grid,
        "formulas": {},
        "styles": new_styles,
        "mergedCells": new_merges,
        "rowHeights": new_row_heights,
        "columnWidths": dict(ws.get("columnWidths", {})),
        "defaultColumnWidth": default_col_w,
        "defaultRowHeight": default_row_h,
        "geometryAuthority": "workbook-v1",
        "colWidthsPx": new_col_widths_px,
        "rowHeightsPx": new_row_heights_px,
        "hiddenRows": [],
        "hiddenColumns": [],
        "visible": True,
        "tabColor": None,
        "role": ws.get("role"),
        "sourceSetup": copy.deepcopy(ws.get("sourceSetup", {})),
        "protectedRanges": [],
        "dataValidations": [],
        "conditionalFormats": [],
        "tableRegions": [],
        "tableLayout": "single",
        "annotations": [],
        "pageLayouts": [],
    }


def _build_block_for_page(ws_id: str, block_id_suffix: str, source_range: str,
                           ws: dict) -> dict:
    """Build a minimal excel_exact block pointing at the given worksheet."""
    return {
        "id": f"{ws_id}_{block_id_suffix}",
        "type": "excelRange",
        "sourceWorksheetId": ws_id,
        "sourceSheet": ws.get("name", ""),
        "sourceRange": source_range,
        "renderMode": "spreadsheet_region",
        "renderProfile": "source_exact",
        "grid": [],   # will be rebuilt by renderer
        "styles": {},
        "mergedCells": [],
        "colWidths": [],
        "rowHeights": [],
        "srcRows": [],
        "repeatRows": [],
        "headerRowCount": 0,
        "allowContinuation": False,
        "splitMode": "explicit_ranges",
        "scaleMode": "fit_width",
        "noGrow": True,
        "trimBlankRows": False,
        "trimBlankColumns": False,
        "preserveGeometry": True,
    }


def migrate(dry_run: bool = False) -> None:
    data = json.loads(PROJECT_JSON.read_text(encoding="utf-8"))

    # ── 1. Locate the shared WICP worksheet ───────────────────────────────
    shared_ws = next(
        (w for w in data.get("worksheets", []) if w.get("id") == SHARED_WS_ID),
        None,
    )
    if shared_ws is None:
        raise RuntimeError(f"Worksheet {SHARED_WS_ID} not found in project.")

    # ── 2. Identify WICP07 split boundary from actual cell values ─────────
    wicp07_row = _find_wicp07_row(shared_ws)  # 0-based
    print(f"  WICP 07 found at row {wicp07_row + 1} (1-indexed).")

    header_row = _find_header_row(shared_ws)
    print(f"  Column header row: {header_row + 1 if header_row >= 0 else 'not found'} (1-indexed).")

    total_rows = len(shared_ws.get("grid", []))
    print(f"  Total rows in shared worksheet: {total_rows}")
    print(f"  Page 3 will show rows 1-{wicp07_row} (WICP01-06 section).")
    print(f"  Page 4 will show rows {wicp07_row + 1}-{total_rows} (WICP07-10 + notes).")

    # ── 3. Verify WICP01 absence in the WICP07+ section ──────────────────
    for r in range(wicp07_row, total_rows):
        row = shared_ws.get("grid", [])[r]
        for cell in (row or []):
            if re.search(r"WICP\s*01\b", str(cell), re.IGNORECASE):
                raise RuntimeError(
                    f"WICP01 appears at row {r+1} (after the WICP07 boundary). "
                    "Cannot split safely — investigate the source data."
                )
    print("  Verified: WICP01 does NOT appear in rows >= WICP07 boundary. Safe to split.")

    # ── 4. Build the new page-4 worksheet ────────────────────────────────
    new_ws = _crop_worksheet(shared_ws, wicp07_row, total_rows, header_row)
    new_ws_rows = len(new_ws["grid"])
    print(f"  New worksheet {NEW_WS_ID} will have {new_ws_rows} rows.")

    # ── 5. Update pages ───────────────────────────────────────────────────
    # Page 3: update block sourceRange to A2:T{wicp07_row} (rows 2..wicp07_row 1-indexed)
    # (row 1 in the original is blank; row 2 is the column header starting A2)
    p3_end_row = wicp07_row  # 0-based exclusive = rows 0..wicp07_row-1 → 1-indexed 1..wicp07_row
    # In A1 notation: header is row 2 (1-indexed), last WICP06 row is wicp07_row (1-indexed)
    header_1idx = header_row + 1 if header_row >= 0 else 2
    p3_range = f"A{header_1idx}:T{p3_end_row}"

    # Page 4: all rows in the new worksheet; header is row 1 (we copied it as row 0 → 1-indexed 1)
    p4_range = f"A1:T{new_ws_rows}"

    pages_out = []
    for page in data.get("pages", []):
        if page.get("id") == PAGE_P3:
            page = dict(page)
            page["linkedWorksheetId"] = SHARED_WS_ID
            page["blocks"] = [
                _build_block_for_page(SHARED_WS_ID, "excel_exact_source_p0", p3_range, shared_ws)
            ]
            page["generatedContinuation"] = False
            page["continuationOf"] = None
            print(f"  Updated {PAGE_P3}: block range → {p3_range}")
        elif page.get("id") == PAGE_P4:
            page = dict(page)
            page["linkedWorksheetId"] = NEW_WS_ID
            page["blocks"] = [
                _build_block_for_page(NEW_WS_ID, "excel_exact_source_p4", p4_range, new_ws)
            ]
            page["generatedContinuation"] = False
            page["continuationOf"] = None
            print(f"  Updated {PAGE_P4}: linkedWorksheetId → {NEW_WS_ID}, block range → {p4_range}")
        pages_out.append(page)

    # ── 6. Add new worksheet to project ──────────────────────────────────
    worksheets_out = list(data.get("worksheets", []))
    if not any(w.get("id") == NEW_WS_ID for w in worksheets_out):
        worksheets_out.append(new_ws)
        print(f"  Added new worksheet {NEW_WS_ID} ({new_ws['name']}).")

    data["pages"] = pages_out
    data["worksheets"] = worksheets_out

    if dry_run:
        print("\n[DRY RUN] No files written.")
        print(f"  Would write {PROJECT_JSON}")
        return

    PROJECT_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  Migration applied → {PROJECT_JSON}")
    print("  Restart Singh360 Draft and verify pages 3 and 4 in the app.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be changed without writing files.")
    args = parser.parse_args()
    try:
        migrate(dry_run=args.dry_run)
        sys.exit(0)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
