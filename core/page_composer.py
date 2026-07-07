"""core/page_composer.py — page family mapping + deterministic pagination.

Two responsibilities:

1. ``page_family`` — reusable keyword mapping from a worksheet name/title to a
   canonical page family (documented in docs/PAGE_TYPE_MAPPING.md). Not hardcoded
   to SA31; applies across Template / Carthage / SA38 workbook families.

2. ``compose_pages`` — split pages whose normalized blocks overflow the printable
   body region into generated continuation pages with deterministic continuation
   codes, so no output sheet requires internal print scrolling.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

# Usable body height budget (logical px) for one 17x11 sheet, after title block
# and page padding are removed. Kept conservative so print never scrolls.
BODY_BUDGET = 820
BODY_W = 1600
TABLE_HEADER_H = 46
TABLE_ROW_H = 30
TABLE_ROW_EXTRA_LINE_H = 14
TABLE_ROW_MAX_H = 92

# Smallest uniform scale we allow an exact Excel range to shrink to before we
# split it onto continuation pages (keeps dense tables readable at 11x17).
EXCEL_MIN_SCALE = 0.5

# Minimum data rows on a continuation page; smaller tails merge onto prior page.
MIN_ORPHAN_DATA_ROWS = 4

# Page families whose pages render the real Excel range verbatim (excel_exact).
EXCEL_EXACT_FAMILIES = {
    "matrix",
    "idfTable",
    "ioSchedule",
    "panelDetail",
    "rackLayout",
    "table",
}


# --------------------------------------------------------------------------
# Page family mapping (Phase H)
# --------------------------------------------------------------------------
_FAMILY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("cover", ("cover", "title sheet", "project info")),
    ("index", ("index", "sheet index", "drawing list", "sheet list")),
    ("matrix", ("responsibilit", "resp matrix", "matrix")),
    ("idfTable", ("idf", "network frame")),
    ("ioSchedule", ("i/o", "io schedule", "points list", "bacnet", "ccg", "dle", "rack i/o")),
    ("rackLayout", ("racks", "rack", "condenser")),
    ("panelDetail", ("pharmacy panel", "panel detail", "panel", "wi-tdb", "wi-pr")),
    ("wiringDiagram", ("one-line", "oneline", "one line", "riser", "wiring", "schematic")),
    ("table", ("bom", "bill of material", "schedule", "directory", "contact", "lighting-tdb", "datamanger", "data manager")),
    ("text", ("guideline", "scope", "instruction", "notes", "workflow", "hvac control", "existing case control")),
    ("canvas", ("layout", "location", "diagram", "plan", "map", "overall")),
]


def page_family(sheet_tab: str, title: str, use_source: str = "") -> str:
    blob = f"{sheet_tab} {title} {use_source}".lower()
    for family, keywords in _FAMILY_RULES:
        if any(k in blob for k in keywords):
            return family
    return "table"


# --------------------------------------------------------------------------
# Continuation codes
# --------------------------------------------------------------------------
def continuation_code(base_code: str, index: int) -> str:
    """Deterministic continuation code for continuation *index* (1-based).

    - integer  "1"        -> "1.1", "1.2"
    - decimal  "6.0"      -> "6.0a", "6.0b"
    - eng      "EMS 3.10" -> "EMS 3.10a", "EMS 3.10b"
    """
    base = (base_code or "").strip()
    letter = chr(ord("a") + index - 1)
    if re.fullmatch(r"\d+", base):
        return f"{base}.{index}"
    if re.fullmatch(r"\d+\.\d+", base):
        return f"{base}{letter}"
    if base:
        return f"{base}{letter}"
    return f"cont-{index}"


# --------------------------------------------------------------------------
# Height estimation
# --------------------------------------------------------------------------
def _excel_natural_size(block: dict[str, Any]) -> tuple[int, int]:
    w = sum(block.get("colWidths") or []) or 1
    h = sum(block.get("rowHeights") or []) or 1
    return w, h


def _excel_width_scale(block: dict[str, Any]) -> float:
    w, _ = _excel_natural_size(block)
    return min(1.0, BODY_W / w)


def _block_min_scale(block: dict[str, Any]) -> float:
    try:
        v = float(block.get("minScale") or EXCEL_MIN_SCALE)
    except (TypeError, ValueError):
        return EXCEL_MIN_SCALE
    # Clamp to a sane band so a bad value can't disable/over-shrink.
    return min(1.0, max(0.2, v))


def _block_allows_continuation(block: dict[str, Any]) -> bool:
    if not block.get("allowContinuation", True):
        return False
    return block.get("splitMode", "auto_rows") != "none"


def _excel_best_scale(block: dict[str, Any]) -> float:
    """Largest uniform scale that fits the range in the body (width and height)."""
    scale_w = _excel_width_scale(block)
    _, h = _excel_natural_size(block)
    return min(scale_w, BODY_BUDGET / h)


def _excel_needs_split(block: dict[str, Any]) -> bool:
    """Split only when continuation is allowed AND the range cannot fit even after
    scaling down to the block's minimum readable scale."""
    if not _block_allows_continuation(block):
        return False
    return _excel_best_scale(block) < _block_min_scale(block)


def _estimate_height(block: dict[str, Any]) -> int:
    t = block.get("type")
    if t == "excelRange":
        if _excel_needs_split(block):
            return BODY_BUDGET + 1
        scale_w = _excel_width_scale(block)
        _, h = _excel_natural_size(block)
        return min(BODY_BUDGET, max(1, int(h * scale_w)))
    if t in ("canvas", "cover"):
        return BODY_BUDGET + 1  # full-page, never split
    if t == "title":
        return 84
    if t == "subtitle":
        return 42
    if t == "sectionHeading":
        return 46
    if t == "note":
        return 30
    if t == "paragraph":
        text = block.get("text") or ""
        lines = max(1, -(-len(text) // 95))
        return 24 * lines + 6
    if t == "bulletList":
        return 26 * len(block.get("items") or []) + 12
    if t in ("table", "matrix"):
        return TABLE_HEADER_H + sum(_estimate_table_row_height(r, block) for r in (block.get("rows") or []))
    if t in ("imagePlaceholder", "underlayPlaceholder"):
        return 150
    return 40


def _estimate_table_row_height(row: list[Any], block: dict[str, Any]) -> int:
    """Estimate rendered row height for wrapped normalized tables.

    The previous paginator assumed every row was 30px tall. Real Excel-derived
    schedules often have narrow columns and wrapped cells (for example lighting
    matrices with DESCRIPTION / FROM / OFFSET columns), so 10 logical rows can
    render as 15-20 visual lines and collide with the title block. This estimate
    intentionally errs conservative: if a row might wrap, split earlier.
    """
    headers = block.get("headers") or []
    ncols = max(len(headers), len(row or []), 1)
    kind = block.get("type")
    # Approximate characters that fit in an average column at the renderer's
    # default font. Matrix tables usually have more/narrower columns.
    base_chars = 110 if kind == "matrix" else 145
    chars_per_line = max(6 if kind == "matrix" else 9, base_chars // ncols)
    max_lines = 1
    for cell in row or []:
        text = " ".join(str(cell or "").split())
        if not text:
            continue
        longest_token = max((len(tok) for tok in text.split(" ")), default=0)
        wrapped = max(1, -(-len(text) // chars_per_line), -(-longest_token // max(chars_per_line, 1)))
        max_lines = max(max_lines, wrapped)
    return min(TABLE_ROW_MAX_H, TABLE_ROW_H + TABLE_ROW_EXTRA_LINE_H * (max_lines - 1))


def _split_table_block(block: dict[str, Any], first_budget: int) -> list[dict[str, Any]]:
    """Split a large table/matrix into row-chunks that each fit a page body."""
    rows = block.get("rows") or []

    chunks: list[list[list[str]]] = []
    if not rows:
        chunks.append([])
    else:
        i = 0
        budget = max(TABLE_HEADER_H + TABLE_ROW_H, first_budget)
        while i < len(rows):
            used = TABLE_HEADER_H
            chunk: list[list[str]] = []
            while i < len(rows):
                row_h = _estimate_table_row_height(rows[i], block)
                if chunk and used + row_h > budget:
                    break
                chunk.append(rows[i])
                used += row_h
                i += 1
            if not chunk:
                # A single monster row gets its own continuation rather than
                # disappearing; renderer will scale as a last resort.
                chunk.append(rows[i])
                i += 1
            chunks.append(chunk)
            budget = BODY_BUDGET

    out: list[dict[str, Any]] = []
    for ci, chunk in enumerate(chunks):
        nb = deepcopy(block)
        nb["rows"] = chunk
        nb["id"] = f"{block.get('id', 'blk')}_p{ci}"
        out.append(nb)
    return out


def _slice_excel_block(block: dict[str, Any], row_indices: list[int], part_index: int) -> dict[str, Any]:
    """Build a continuation sub-block containing exactly ``row_indices`` (which
    already include the repeated header rows), remapping styles and merges."""
    grid = block.get("grid") or []
    row_h = block.get("rowHeights") or []
    styles = block.get("styles") or {}
    merges = block.get("mergedCells") or []
    orig_repeat = set(block.get("repeatRows") or [])

    remap = {old: new for new, old in enumerate(row_indices)}
    new_grid = [list(grid[r]) for r in row_indices if 0 <= r < len(grid)]
    new_row_h = [row_h[r] if r < len(row_h) else 20 for r in row_indices]

    new_styles: dict[str, Any] = {}
    for key, val in styles.items():
        try:
            rs, cs = key.split(":")
            r, c = int(rs), int(cs)
        except (ValueError, AttributeError):
            continue
        if r in remap:
            new_styles[f"{remap[r]}:{c}"] = val

    new_merges: list[dict[str, Any]] = []
    for m in merges:
        rows = list(range(m.get("startRow", 0), m.get("endRow", 0) + 1))
        if rows and all(rr in remap for rr in rows):
            ns = [remap[rr] for rr in rows]
            nm = dict(m)
            nm["startRow"], nm["endRow"] = min(ns), max(ns)
            new_merges.append(nm)

    header_present = sum(1 for r in row_indices if r in orig_repeat)
    src_rows = block.get("srcRows") or list(range(len(block.get("grid") or [])))
    nb = deepcopy(block)
    nb["id"] = f"{block.get('id', 'blk')}_p{part_index}"
    nb["grid"] = new_grid
    nb["rowHeights"] = new_row_h
    nb["styles"] = new_styles
    nb["mergedCells"] = new_merges
    nb["srcRows"] = [src_rows[r] if r < len(src_rows) else r for r in row_indices]
    nb["repeatRows"] = list(range(header_present))
    return nb


def _excel_data_chunks(block: dict[str, Any], data_rows: list[int], header_h: float) -> list[list[int]]:
    """Greedily pack data rows into page-height chunks, then rebalance so the last
    page is never a single orphan row when a legal alternative exists."""
    row_h = block.get("rowHeights") or []
    scale_w = _excel_width_scale(block)
    budget = BODY_BUDGET / max(scale_w, _block_min_scale(block))

    chunks: list[list[int]] = []
    i = 0
    while i < len(data_rows):
        used = header_h
        chunk: list[int] = []
        while i < len(data_rows):
            r = data_rows[i]
            h = row_h[r] if r < len(row_h) else 20
            if chunk and used + h > budget:
                break
            chunk.append(r)
            used += h
            i += 1
        if not chunk:  # a single row taller than the whole budget: unavoidable
            chunk.append(data_rows[i])
            i += 1
        chunks.append(chunk)

    # Orphan avoidance: if the last chunk has fewer than MIN_ORPHAN_DATA_ROWS,
    # pull rows from the previous chunk until the tail is big enough or the prior
    # page would drop below MIN_ORPHAN_DATA_ROWS (then the split is unavoidable).
    if len(chunks) >= 2 and len(chunks[-1]) < MIN_ORPHAN_DATA_ROWS:
        while len(chunks[-1]) < MIN_ORPHAN_DATA_ROWS and len(chunks) >= 2 and len(chunks[-2]) > MIN_ORPHAN_DATA_ROWS:
            moved = chunks[-2].pop()
            chunks[-1].insert(0, moved)
        if len(chunks) >= 2 and len(chunks[-1]) < MIN_ORPHAN_DATA_ROWS and len(chunks[-2]) >= 2:
            moved = chunks[-2].pop()
            chunks[-1].insert(0, moved)
    return chunks


def _manual_chunks(block: dict[str, Any], repeat: list[int], n_rows: int) -> list[list[int]]:
    """Chunks from explicit manualRanges ([[startRow,endRow], ...], absolute,
    inclusive). Header/repeat rows are excluded from data and re-added per page."""
    ranges = block.get("manualRanges") or []
    repeat_set = set(repeat)
    chunks: list[list[int]] = []
    for rng in ranges:
        try:
            s, e = int(rng[0]), int(rng[1])
        except (TypeError, ValueError, IndexError):
            continue
        rows = [r for r in range(max(0, s), min(n_rows - 1, e) + 1) if r not in repeat_set]
        if rows:
            chunks.append(rows)
    return chunks


def _split_excel_range_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Split an exact Excel range along real row boundaries, repeating the header
    band on each continuation. Column widths are preserved unchanged.

    Honors per-block ``splitMode`` (none / auto_rows / manual_ranges),
    ``minScale`` and ``allowContinuation``. When continuation is disallowed the
    range stays a single page (renderer scales/crops); an overflow warning is
    recorded instead of adding pages."""
    grid = block.get("grid") or []
    row_h = block.get("rowHeights") or []
    n_rows = len(grid)
    if n_rows == 0:
        return [block]

    repeat = sorted({r for r in (block.get("repeatRows") or []) if 0 <= r < n_rows})
    header_h = sum(row_h[r] for r in repeat if r < len(row_h))

    # splitMode none / continuation disabled: never add pages.
    if not _block_allows_continuation(block):
        if _excel_best_scale(block) < _block_min_scale(block):
            warn = list(block.get("layoutWarnings") or [])
            warn.append("Range exceeds one page; scaled/cropped (continuation disabled).")
            block["layoutWarnings"] = warn
        return [block]

    mode = block.get("splitMode", "auto_rows")
    if mode == "manual_ranges" and block.get("manualRanges"):
        chunks = _manual_chunks(block, repeat, n_rows)
    else:
        data_rows = [r for r in range(n_rows) if r not in set(repeat)]
        chunks = _excel_data_chunks(block, data_rows, header_h)

    # Drop any empty chunks (rule: never create blank continuation pages).
    chunks = [c for c in chunks if c]
    if len(chunks) <= 1:
        return [block]

    return [
        _slice_excel_block(block, sorted(set(repeat) | set(chunk)), ci)
        for ci, chunk in enumerate(chunks)
    ]


def plan_excel_range(block: dict[str, Any]) -> dict[str, Any]:
    """Preview how many pages an exact range will produce (no mutation)."""
    probe = deepcopy(block)
    parts = _split_excel_range_block(probe)
    best = _excel_best_scale(block)
    min_scale = _block_min_scale(block)
    return {
        "pages": len(parts),
        "willSplit": len(parts) > 1,
        "bestScale": round(best, 4),
        "minScale": min_scale,
        "allowContinuation": _block_allows_continuation(block),
        "cropped": (not _block_allows_continuation(block)) and best < min_scale,
    }


def _paginate_blocks(blocks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Greedily pack blocks into page-sized groups; split oversized tables."""
    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0

    def flush() -> None:
        nonlocal current, used
        if current:
            pages.append(current)
            current = []
            used = 0

    for block in blocks:
        h = _estimate_height(block)
        if h >= BODY_BUDGET + 1:
            if block.get("type") == "excelRange":
                flush()
                for part in _split_excel_range_block(block):
                    pages.append([part])
                continue
            if block.get("type") in ("table", "matrix"):
                flush()
                for part in _split_table_block(block, BODY_BUDGET):
                    pages.append([part])
                continue
            # full-page block (canvas/cover) — own page
            flush()
            pages.append([block])
            continue
        if used + h <= BODY_BUDGET:
            current.append(block)
            used += h
            continue
        # doesn't fit remaining space
        if block.get("type") == "excelRange":
            flush()
            for part in _split_excel_range_block(block):
                pages.append([part])
            continue
        if block.get("type") in ("table", "matrix"):
            remaining = BODY_BUDGET - used
            parts = _split_table_block(block, remaining if remaining > TABLE_HEADER_H + TABLE_ROW_H else BODY_BUDGET)
            # first part fills current page if it fits, else new page
            first = parts[0]
            if used + _estimate_height(first) <= BODY_BUDGET and used > 0:
                current.append(first)
                flush()
                rest = parts[1:]
            else:
                flush()
                rest = parts
            for part in rest:
                pages.append([part])
        else:
            flush()
            current.append(block)
            used = h
    flush()
    return pages if pages else [[]]


def _continuation_title(base_title: str) -> str:
    low = (base_title or "").lower()
    if "continued" in low:
        return base_title
    return f"{base_title} — CONTINUED"


def _page_should_paginate(page: dict[str, Any]) -> bool:
    """Only normalized block pages with explicit continuation permission may split."""
    if page.get("renderMode") == "excel_exact":
        return False
    if page.get("splitMode") == "none" or not page.get("allowContinuation", False):
        return False
    if page.get("pageType") in ("index", "cover", "canvas", "hybrid", "underlay"):
        return False
    return True


def _append_continuation_pages(
    composed: list[dict[str, Any]],
    base: dict[str, Any],
    groups: list[list[dict[str, Any]]],
) -> None:
    """Insert generated continuation pages immediately after ``base``."""
    base_code = base.get("sheetCode", "")
    base_title = base.get("sheetTitle", "")
    group_id = base["id"]
    cont_title = _continuation_title(base_title)

    base["blocks"] = groups[0]
    base["pageGroupId"] = group_id
    base["continuationIndex"] = 0
    base["displaySheetCode"] = base_code
    composed.append(base)

    for ci, grp in enumerate(groups[1:], start=1):
        composed.append(
            {
                "id": f"{group_id}_c{ci}",
                "order": base.get("order", 0),
                "include": base.get("include", True),
                "sheetCode": continuation_code(base_code, ci),
                "displaySheetCode": continuation_code(base_code, ci),
                "sheetTitle": cont_title,
                "sheetTab": base.get("sheetTab", ""),
                "pageType": base.get("pageType", "data-grid"),
                "pageFamily": base.get("pageFamily", "table"),
                "renderMode": base.get("renderMode", "normalized"),
                "sourceSheet": base.get("sourceSheet", ""),
                "sourceRange": base.get("sourceRange", ""),
                "printArea": base.get("printArea"),
                "splitMode": base.get("splitMode", "none"),
                "repeatRows": base.get("repeatRows", []),
                "minScale": base.get("minScale", EXCEL_MIN_SCALE),
                "allowContinuation": base.get("allowContinuation", False),
                "scaleMode": base.get("scaleMode", "fit_body"),
                "orientation": base.get("orientation", "landscape"),
                "templateId": base.get("templateId", "ansi-b-standard"),
                "linkedWorksheetId": base.get("linkedWorksheetId"),
                "blocks": grp,
                "canvasObjects": [],
                "assets": [],
                "underlays": [],
                "notes": "",
                "revisionRows": [],
                "pageGroupId": group_id,
                "continuationOf": group_id,
                "continuationIndex": ci,
                "generatedContinuation": True,
                "layoutWarnings": [],
            }
        )


def continuation_summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-sheet page counts for the import continuation preview.

    Groups by ``pageGroupId`` (base + its continuations), preserving order."""
    included = [p for p in pages if p.get("include", True)]
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for p in included:
        gid = p.get("pageGroupId") or p.get("id")
        if gid not in groups:
            pages_count = 0
            groups[gid] = {
                "sheetTab": p.get("sheetTab", ""),
                "sheetTitle": p.get("sheetTitle", ""),
                "sheetCode": p.get("sheetCode", ""),
                "renderMode": p.get("renderMode", "normalized"),
                "splitMode": p.get("splitMode", "none"),
                "pages": 0,
            }
            order.append(gid)
        groups[gid]["pages"] += 1

    sheets = []
    for g in order:
        s = groups[g]
        n = s["pages"]
        s["message"] = f"This sheet will create {n} page{'s' if n != 1 else ''}."
        sheets.append(s)
    return {
        "sheets": sheets,
        "totalPages": len(included),
        "totalSheets": len(sheets),
        "multiPageSheets": sum(1 for s in sheets if s["pages"] > 1),
    }


# --------------------------------------------------------------------------
# Public: compose_pages
# --------------------------------------------------------------------------
def compose_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a new page list where overflowing pages are split into generated
    continuation pages. Base pages keep their id; continuations are inserted
    immediately after and flagged as generated.
    """
    composed: list[dict[str, Any]] = []

    for page in pages:
        if not page.get("include", True):
            continue

        blocks = page.get("blocks") or []
        page_type = page.get("pageType", "")
        page.setdefault("pageFamily", page_family(page.get("sheetTab", ""), page.get("sheetTitle", ""), ""))
        page.setdefault("pageGroupId", page["id"])
        page.setdefault("continuationIndex", 0)
        page.setdefault("continuationOf", None)
        page.setdefault("generatedContinuation", False)
        page.setdefault("displaySheetCode", page.get("sheetCode", ""))
        page.setdefault("layoutWarnings", [])

        # Canvas/cover/hybrid or empty → never split.
        if page_type in ("canvas", "hybrid", "underlay", "cover") or not blocks:
            composed.append(page)
            continue

        excel_blocks = [b for b in blocks if b.get("type") == "excelRange"]
        if page.get("renderMode") == "excel_exact" or excel_blocks:
            if len(excel_blocks) == 1 and len(blocks) == len(excel_blocks):
                parts = _split_excel_range_block(excel_blocks[0])
                if len(parts) <= 1:
                    page["blocks"] = parts
                    composed.append(page)
                else:
                    base = deepcopy(page)
                    _append_continuation_pages(composed, base, [[p] for p in parts])
            else:
                composed.append(page)
            continue

        if not _page_should_paginate(page):
            composed.append(page)
            continue

        groups = _paginate_blocks(blocks)
        if len(groups) <= 1:
            page["blocks"] = groups[0] if groups else []
            composed.append(page)
            continue

        base = deepcopy(page)
        _append_continuation_pages(composed, base, groups)

    # Re-sequence order to reflect insertion order.
    for i, p in enumerate(composed, start=1):
        p["order"] = i
    return composed
