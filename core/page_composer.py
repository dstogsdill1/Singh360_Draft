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
TABLE_HEADER_H = 46
TABLE_ROW_H = 30
TABLE_ROW_EXTRA_LINE_H = 14
TABLE_ROW_MAX_H = 92


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
def _estimate_height(block: dict[str, Any]) -> int:
    t = block.get("type")
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
        if page_type in ("canvas", "hybrid", "underlay") or not blocks:
            composed.append(page)
            continue

        groups = _paginate_blocks(blocks)
        if len(groups) <= 1:
            page["blocks"] = groups[0] if groups else []
            composed.append(page)
            continue

        base_code = page.get("sheetCode", "")
        base_title = page.get("sheetTitle", "")
        group_id = page["id"]

        # First group stays on the base page.
        base = page
        base["blocks"] = groups[0]
        base["pageGroupId"] = group_id
        base["continuationIndex"] = 0
        base["displaySheetCode"] = base_code
        composed.append(base)

        # Remaining groups become generated continuation pages.
        for ci, grp in enumerate(groups[1:], start=1):
            cont = {
                "id": f"{group_id}_c{ci}",
                "order": base.get("order", 0),
                "include": base.get("include", True),
                "sheetCode": continuation_code(base_code, ci),
                "displaySheetCode": continuation_code(base_code, ci),
                "sheetTitle": f"{base_title} — CONTINUED",
                "sheetTab": base.get("sheetTab", ""),
                "pageType": base.get("pageType", "data-grid"),
                "pageFamily": base.get("pageFamily", "table"),
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
            composed.append(cont)

    # Re-sequence order to reflect insertion order.
    for i, p in enumerate(composed, start=1):
        p["order"] = i
    return composed
