"""core/excel_parser.py — Excel ingestion for Singh360 Draft.

Source of truth: ``workbook.sheetnames`` — every worksheet tab is returned to the
UI as a page the user can include or exclude in the final PDF.

The 00_INDEX tab (when present) supplies optional metadata only (order, title,
include default, notes). It never filters or hides tabs that exist in the workbook.

Expected 00_INDEX columns (order-independent, alias-tolerant):
  Include | Order | Sheet Tab | Page Title | Use / Source | Notes
"""
from __future__ import annotations

import math
import re
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Classification keyword lists
# ---------------------------------------------------------------------------

CANVAS_KEYWORDS = [
    "schematic", "layout", "staging", "drawing", "elevation", "detail",
    "flow", "diagram", "overall", "network", "view", "lcp", "canvas", "map",
    "plan", "riser", "single line", "one-line", "oneline",
]

DATA_KEYWORDS = [
    "bom", "material", "responsibility", "matrix", "schedule", "register",
    "index", "list", "notes", "scope", "header", "contact", "contactor",
    "bill of", "equipment", "device", "io ", "point",
]

# ---------------------------------------------------------------------------
# Column alias mapping
# Lists are tried left-to-right; all comparisons are lower-cased + stripped.
# ---------------------------------------------------------------------------

_COL_ALIASES: dict[str, list[str]] = {
    "include":    ["include", "inc", "include?", "use?", "selected", "active"],
    "order":      ["order", "no", "num", "code", "sheet no", "sheet no.", "seq"],
    "sheet_tab":  ["sheet tab", "tab", "sheet", "worksheet", "tab name"],
    "page_title": ["page title", "title", "name", "page name", "sheet title"],
    "use_source": ["use / source", "use/source", "use", "source", "type", "view type"],
    "notes":      ["notes", "remarks", "description", "desc", "comment"],
}

# Values in the Include column that explicitly mean "yes, include this sheet"
_INCLUDE_TRUTHY = {"y", "yes", "true", "1", "x", "✓", "check", "include", "on"}

# Values that explicitly mean "no, exclude this sheet" — everything else
# (including blank/NaN cells) defaults to included. See _is_included().
_INCLUDE_FALSY = {"n", "no", "false", "0", "exclude", "skip", "off", "excluded"}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _clean_str(val: Any) -> str:
    """
    Convert any cell value to a clean string.

    Handles:
    - None / NaN / NaT / pandas NA / "nan" / "none"  -> empty string
    - Non-breaking spaces (\\xa0) and other Unicode whitespace -> stripped
    - Integers stored as floats (e.g. 1.0 -> "1")
    """
    if val is None:
        return ""
    if val is pd.NA:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    try:
        if isinstance(val, float) and math.isnan(val):
            return ""
    except TypeError:
        pass
    # Collapse all Unicode whitespace variants (incl. \xa0 non-breaking space)
    text = " ".join(str(val).split()).strip()
    return "" if text.lower() in ("nan", "none", "<na>", "nat") else text


# Keep old name as an alias so other modules that imported it don't break
normalize_cell = _clean_str


def _norm(cell: str) -> str:
    """Lowercase + strip a header cell for alias comparison."""
    return " ".join(cell.lower().split())


def _col_index(header_row: list[str], aliases: list[str]) -> int:
    """Return the index of the first cell whose normalised value is in *aliases*."""
    for ci, cell in enumerate(header_row):
        if _norm(cell) in aliases:
            return ci
    return -1


def _cell(row: list[str], idx: int) -> str:
    """Bounds-safe column access."""
    return row[idx] if 0 <= idx < len(row) else ""


def _sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Guarantee no NaN, NaT, or pandas NA survives into grid extraction.

    Every cell becomes a plain string safe for ``json.dumps`` / ``JSON.parse``.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out = out.fillna("")
    out = out.replace({pd.NA: "", pd.NaT: ""})
    out = out.astype(str)
    # ``astype(str)`` can still yield literal "nan" / "<NA>" strings — scrub them.
    out = out.replace(
        to_replace=r"^(nan|NaN|NaT|<NA>|None|nat|none)$",
        value="",
        regex=True,
    )
    return out


def _json_safe_bool(val: Any, default: bool = True) -> bool:
    """Return a strict Python ``bool`` — never NaN and never ambiguous."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, float):
        if math.isnan(val):
            return default
        return val != 0.0
    if isinstance(val, (int,)):
        return val != 0
    text = _clean_str(val).lower()
    if not text or text in ("nan", "none", "<na>", "nat"):
        return default
    if text in _INCLUDE_FALSY:
        return False
    if text in _INCLUDE_TRUTHY:
        return True
    return default


def _sanitize_grid(grid: list[list[Any]]) -> list[list[str]]:
    """Deep-clean a 2-D grid so every cell is a JSON-safe string."""
    return [[_clean_str(cell) for cell in row] for row in grid]


def _is_included(raw: str) -> bool:
    """
    Interpret an Include cell as a boolean.

    Blank, empty, NaN, or otherwise unrecognised cells default to True so
    every row listed in 00_INDEX renders in the UI by default. Only an
    explicit negative marker (N, No, FALSE, 0, Exclude, ...) turns a page off.
    """
    norm = _norm(raw)
    if not norm:
        return True
    if norm in _INCLUDE_FALSY:
        return False
    if norm in _INCLUDE_TRUTHY:
        return True
    # Unrecognised non-empty value — still default to included per spec
    return True


# ---------------------------------------------------------------------------
# Sheet classification
# ---------------------------------------------------------------------------

def classify_sheet(sheet_tab: str, page_title: str, use_source: str = "") -> str:
    """Return ``'canvas'`` or ``'data'`` based on all available text clues."""
    combined = f"{sheet_tab} {page_title} {use_source}".lower()
    if any(kw in combined for kw in CANVAS_KEYWORDS):
        return "canvas"
    if any(kw in combined for kw in DATA_KEYWORDS):
        return "data"
    return "data"


# ---------------------------------------------------------------------------
# INDEX sheet parser
# ---------------------------------------------------------------------------

def find_index_sheet(sheet_names: list[str]) -> str | None:
    """Return the first sheet whose name contains 'INDEX' (case-insensitive)."""
    for name in sheet_names:
        if "INDEX" in name.upper().replace(" ", "").replace("_", ""):
            return name
    return None


def _find_header_row(rows: list[list[str]]) -> int:
    """
    Scan rows top-down for the real column header row.

    Strategy:
      1. Look for a row that matches at least one alias from BOTH the
         ``sheet_tab`` group AND the ``page_title`` group — the only
         combination that unambiguously identifies the header row even
         when there are logo / title rows above.
      2. Softer pass: any row matching >= 3 known aliases.
      3. Last resort: row 0.

    Prints diagnostic info so header detection failures are visible in the
    server terminal.
    """
    tab_aliases   = set(_COL_ALIASES["sheet_tab"])
    title_aliases = set(_COL_ALIASES["page_title"])
    all_aliases   = {a for aliases in _COL_ALIASES.values() for a in aliases}

    for i, row in enumerate(rows):
        normed = {_norm(c) for c in row if c}
        hit_tab   = normed & tab_aliases
        hit_title = normed & title_aliases
        if hit_tab and hit_title:
            print(f"[excel_parser]   Header row found at index {i}  "
                  f"(matched sheet_tab={hit_tab}, page_title={hit_title})")
            return i

    print("[excel_parser]   WARNING - strong header match failed; trying soft pass (>=3 aliases).")
    for i, row in enumerate(rows):
        normed = {_norm(c) for c in row if c}
        hits = normed & all_aliases
        if len(hits) >= 3:
            print(f"[excel_parser]   Soft header match at row {i}: {hits}")
            return i

    print("[excel_parser]   WARNING - no header row detected; defaulting to row 0.")
    print(f"[excel_parser]   First row cells: {rows[0] if rows else '(empty)'}")
    return 0


def parse_index_sheet(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Parse the INDEX sheet into a list of page-entry dicts.

    Prints every structural decision and every entry produced so the
    server terminal gives a full trace of what was (or was not) found.
    """
    print(f"[excel_parser]   INDEX sheet shape: {df.shape[0]} rows x {df.shape[1]} cols")

    # Normalise the whole frame to clean strings up front (no NaN/NaT/NA)
    df = _sanitize_dataframe(df)

    rows: list[list[str]] = [
        [_clean_str(c) for c in row]
        for row in df.itertuples(index=False, name=None)
    ]

    if not rows:
        print("[excel_parser]   ERROR - INDEX sheet is completely empty.")
        return []

    # Print the first few raw rows so we can see what Excel actually contains
    print("[excel_parser]   First 5 raw rows from INDEX:")
    for i, r in enumerate(rows[:5]):
        print(f"[excel_parser]     row[{i}]: {r}")

    hdr_i = _find_header_row(rows)
    header = rows[hdr_i]
    print(f"[excel_parser]   Header row [{hdr_i}] cells: {header}")

    # Map each logical field to its column index
    col: dict[str, int] = {
        field: _col_index(header, aliases)
        for field, aliases in _COL_ALIASES.items()
    }
    print(f"[excel_parser]   Column index map: { {k: v for k, v in col.items()} }")

    # Warn about any field that went unmapped
    missing = [k for k, v in col.items() if v == -1]
    if missing:
        print(f"[excel_parser]   WARNING - could not map columns: {missing}")
        print(f"[excel_parser]   Available header cells (normalised): "
              f"{[_norm(c) for c in header if c]}")

    entries: list[dict[str, Any]] = []
    skipped = 0

    for row_i, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 1):
        if not any(r):
            skipped += 1
            continue

        sheet_tab   = _cell(r, col["sheet_tab"])
        page_title  = _cell(r, col["page_title"])
        order       = _cell(r, col["order"])
        use_source  = _cell(r, col["use_source"])
        notes       = _cell(r, col["notes"])
        include_raw = _cell(r, col["include"])

        if not sheet_tab and not page_title:
            skipped += 1
            continue

        code = order or str(len(entries) + 1)
        # _is_included() already defaults to True for blank/NaN/unmapped cells
        included_default = bool(_is_included(include_raw))

        entry = {
            "code":             code,
            "sheet_tab":        sheet_tab,
            "title":            page_title or sheet_tab,
            "description":      notes,
            "use_source":       use_source,
            "included_default": included_default,
        }
        print(f"[excel_parser]     row[{row_i}] -> entry: "
              f"code={code!r}  tab={sheet_tab!r}  title={page_title!r}  "
              f"include={include_raw!r}->{included_default}")
        entries.append(entry)

    print(f"[excel_parser]   INDEX parse complete: {len(entries)} entries, {skipped} rows skipped.")
    return entries


# ---------------------------------------------------------------------------
# Grid data extraction
# ---------------------------------------------------------------------------

def clean_grid_data(df: pd.DataFrame) -> list[list[str]]:
    """Convert a dataframe to a trimmed string grid (drops empty trailing rows/cols)."""
    df = _sanitize_dataframe(df)
    grid = _sanitize_grid([
        list(row)
        for row in df.itertuples(index=False, name=None)
    ])

    while grid and not any(grid[-1]):
        grid.pop()

    if not grid:
        return []

    max_cols = max(len(row) for row in grid)
    cols_to_keep = max_cols
    for ci in range(max_cols - 1, -1, -1):
        if all(ci >= len(row) or not row[ci] for row in grid):
            cols_to_keep = ci
        else:
            break

    return [row[:cols_to_keep] for row in grid]


def _read_grid(xl: pd.ExcelFile, sheet_name: str) -> list[list[str]]:
    try:
        df = pd.read_excel(xl, sheet_name=sheet_name, header=None)
        grid = clean_grid_data(df)
        print(f"[excel_parser]   Grid read OK for '{sheet_name}': "
              f"{len(grid)} rows x {len(grid[0]) if grid else 0} cols")
        return grid
    except Exception as exc:
        print(f"[excel_parser]   ERROR reading grid for '{sheet_name}': {exc}")
        traceback.print_exc()
        return []


# ---------------------------------------------------------------------------
# Fallback helpers (no INDEX sheet, or INDEX produced 0 entries)
# ---------------------------------------------------------------------------

def _fallback_entry(name: str, position: int) -> dict[str, Any]:
    """Synthesise a page entry from a bare sheet tab name."""
    match = re.match(r"^(\d+)[_\-\s]*(.*)$", name)
    if match:
        code  = match.group(1)
        title = match.group(2).strip() or name
    else:
        code  = str(position + 1)
        title = name
    return {
        "code":             code,
        "sheet_tab":        name,
        "title":            title,
        "description":      "",
        "use_source":       "",
        "included_default": True,
    }


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def _index_lookup(index_entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a case-insensitive lookup from INDEX entries keyed by sheet_tab."""
    lookup: dict[str, dict[str, Any]] = {}
    for entry in index_entries:
        tab = entry.get("sheet_tab", "")
        if not tab:
            continue
        lookup[tab] = entry
        lookup[tab.lower()] = entry
    return lookup


def _metadata_for_sheet(
    sheet_name: str,
    position: int,
    index_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Merge INDEX metadata when available; otherwise synthesise from the tab name."""
    entry = index_lookup.get(sheet_name) or index_lookup.get(sheet_name.lower())
    if entry:
        return {
            "code":             entry["code"],
            "title":            entry["title"],
            "description":      entry["description"],
            "use_source":       entry["use_source"],
            "included_default": _json_safe_bool(entry.get("included_default"), default=True),
        }
    fallback = _fallback_entry(sheet_name, position)
    return {
        "code":             fallback["code"],
        "title":            fallback["title"],
        "description":      fallback["description"],
        "use_source":       fallback["use_source"],
        "included_default": _json_safe_bool(fallback["included_default"], default=True),
    }


def _build_page_from_sheet(
    sheet_name: str,
    position: int,
    index_lookup: dict[str, dict[str, Any]],
    xl: pd.ExcelFile,
) -> dict[str, Any]:
    """
    Build one page dict using the frontend data contract:

    {"sheet_tab", "page_title", "included", "grid_data"}
    """
    meta = _metadata_for_sheet(sheet_name, position, index_lookup)
    view_type = classify_sheet(sheet_name, meta["title"], meta["use_source"])
    grid_data: list[list[str]] = []
    if view_type == "data":
        grid_data = _read_grid(xl, sheet_name)

    page = {
        "sheet_tab":   _clean_str(sheet_name),
        "page_title":  _clean_str(meta["title"]),
        "included":    _json_safe_bool(meta["included_default"], default=True),
        "grid_data":   _sanitize_grid(grid_data),
    }
    print(f"[excel_parser]   Page built: sheet_tab={sheet_name!r}  "
          f"page_title={page['page_title']!r}  included={page['included']}  "
          f"grid={len(grid_data)}x{len(grid_data[0]) if grid_data else 0}")
    return page


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_workbook(xlsx_path: str | Path) -> dict[str, Any]:
    """
    Ingest an Excel workbook and return the Singh360 Draft project model.

    Every stage prints to stdout so the Flask server terminal provides a
    full trace — nothing fails silently.

    Raises ``FileNotFoundError`` if the path does not exist.
    """
    xlsx_path = Path(xlsx_path)

    print("=" * 60)
    print(f"[excel_parser] PARSE START: {xlsx_path.name}")

    if not xlsx_path.exists():
        print(f"[excel_parser] ERROR - file not found: {xlsx_path}")
        raise FileNotFoundError(f"Workbook not found: {xlsx_path}")

    with pd.ExcelFile(xlsx_path) as xl:
        sheet_names: list[str] = xl.sheet_names
        print(f"[excel_parser] Found {len(sheet_names)} sheet(s): {sheet_names}")

        idx_sheet_name = find_index_sheet(sheet_names)
        print(f"[excel_parser] INDEX sheet: {idx_sheet_name!r}")

        # ── Parse INDEX ──────────────────────────────────────────────────
        index_entries: list[dict[str, Any]] = []
        if idx_sheet_name:
            print(f"[excel_parser] Reading INDEX sheet '{idx_sheet_name}' ...")
            try:
                df_idx = pd.read_excel(
                    xl, sheet_name=idx_sheet_name, header=None
                )
                index_entries = parse_index_sheet(df_idx)
            except Exception as exc:
                # Print the FULL traceback — never swallow silently
                print(f"[excel_parser] ERROR - parse_index_sheet raised an exception:")
                traceback.print_exc()
                print(f"[excel_parser] Exception message: {exc}")
        else:
            print("[excel_parser] WARNING - no INDEX sheet found in this workbook.")

        # INDEX is optional metadata only — never the source of which tabs exist.
        index_lookup = _index_lookup(index_entries)
        if index_entries:
            print(f"[excel_parser] INDEX metadata loaded for {len(index_entries)} row(s).")
        else:
            print("[excel_parser] No INDEX metadata — all tabs use sheet-name defaults.")

        # ── Build one page per workbook tab (sheetnames is the source of truth) ──
        print(f"[excel_parser] Building {len(sheet_names)} page(s) - one per workbook tab ...")
        pages: list[dict[str, Any]] = []
        for position, name in enumerate(sheet_names):
            try:
                pages.append(_build_page_from_sheet(name, position, index_lookup, xl))
            except Exception as exc:
                print(f"[excel_parser] ERROR building page for tab '{name}': {exc}")
                traceback.print_exc()

        print(f"[excel_parser] PARSE COMPLETE - {len(pages)} page(s) from "
              f"{len(sheet_names)} workbook tab(s).")
        print("=" * 60)

        return {
            "projectName": "Untitled Project",
            "projectNo":   "",
            "siteAddress": "",
            "date":        "",
            "preparedBy":  "",
            "status":      "Draft",
            "sheetTitle":  "",
            "sheetNumber": "",
            "pages":       pages,
        }
