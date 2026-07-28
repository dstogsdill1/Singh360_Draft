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

from core.workbook_geometry import DEFAULT_ROW_HEIGHT_PX

from core.page_identity import is_sheet_index_page

# Usable body height budget (logical px) for one 17x11 sheet, after title block
# and page padding are removed. Kept conservative so print never scrolls.
BODY_BUDGET = 720
BODY_W = 1600
TABLE_HEADER_H = 46
TABLE_ROW_H = 30
TABLE_ROW_EXTRA_LINE_H = 14
TABLE_ROW_MAX_H = 92

# FINAL RENDER POLISH 4G, Phase C: reserve a fixed bottom safety gap so an
# excel_exact range's scale/split decision never targets the literal edge of
# the printable body — a table that "just fits" at BODY_BUDGET used to render
# flush against the title block with zero margin (the "tight against the
# title block" / occasional clipped-last-row failure). Mirrors
# ExcelRangeRenderer.tsx's MIN_BOTTOM_GAP.
MIN_BOTTOM_GAP = 20
SAFE_BODY_BUDGET = BODY_BUDGET - MIN_BOTTOM_GAP

# Smallest uniform scale we allow an exact Excel range to shrink to before we
# split it onto continuation pages (keeps dense tables readable at 11x17).
# TABLE STYLE 4F Phase C: most Singh360 EMS workbooks carry ~9pt body text, so
# a 0.73 floor keeps the rendered text at/above the 6.5pt absolute minimum
# (9pt * 0.73 ~= 6.6pt) instead of silently shrinking further.
EXCEL_MIN_SCALE = 0.73

# Minimum data rows on a continuation page; smaller tails merge onto prior page.
MIN_ORPHAN_DATA_ROWS = 4

# Used only when an idfNetworkTable block is somehow missing its fontSize.
DENSE_FONT_SIZE_FALLBACK = 7.0

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
    ("companyInfo", ("company info", "singh360 company", "company/reference")),
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
    index = max(1, int(index))
    if re.fullmatch(r"\d+", base):
        return f"{base}.{index}"

    match = re.fullmatch(r"(.*\d(?:\.\d+)?)([a-z]+)?", base, re.IGNORECASE)
    stem = match.group(1) if match else base
    existing = (match.group(2) or "").lower() if match else ""

    def suffix_value(value: str) -> int:
        total = 0
        for char in value:
            total = total * 26 + ord(char) - ord("a") + 1
        return total

    value = suffix_value(existing) + index
    suffix = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        suffix = chr(ord("a") + remainder) + suffix

    if match:
        return f"{stem}{suffix}"
    if base:
        return f"{base}{suffix}"
    return f"cont-{index}"


def _code_key(code: str) -> str:
    return re.sub(r"\s+", "", str(code or "").casefold())


def _next_available_continuation_code(
    base_code: str,
    start_index: int,
    used_codes: set[str],
) -> str:
    candidate_index = max(1, int(start_index))
    while True:
        candidate = continuation_code(base_code, candidate_index)
        key = _code_key(candidate)
        if key not in used_codes:
            used_codes.add(key)
            return candidate
        candidate_index += 1


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
    """Largest uniform scale that fits the range in the body (width and height),
    leaving MIN_BOTTOM_GAP of clean space above the title block (Phase C)."""
    scale_w = _excel_width_scale(block)
    _, h = _excel_natural_size(block)
    return min(scale_w, SAFE_BODY_BUDGET / h)


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
    new_row_h = [
        row_h[r] if r < len(row_h) else DEFAULT_ROW_HEIGHT_PX
        for r in row_indices
    ]

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


def _gold_section_starts(block: dict[str, Any]) -> list[tuple[int, int]]:
    """Ordered ``(gold_row, gray_row)`` pairs: a gold controller/section band
    row immediately followed by its own gray column-header row (Kyle/SA38
    -style repeating multi-controller sheets — RACK A/B, DLE Controllers,
    and similar; FINAL RELEASE CLEANUP 4H+SA38, Phase F).

    This is the atomic "controller section" unit for those sheets: a split
    should only ever land on a ``gold_row`` boundary, and a continuation
    whose data starts mid-section must repeat this exact pair as its own
    header. Also fires for SA31-style LCP-1/LCP-2 gold section bands
    (already used by ``_logical_section_chunks``'s keyword special case),
    generalizing that same idea by fill color instead of row text.
    """
    from core.table_style_profile import is_gold_fill

    styles = block.get("styles") or {}
    grid = block.get("grid") or []
    merges = block.get("mergedCells") or []
    n_rows = len(grid)
    ncols = max((len(r) for r in grid), default=0)
    if not ncols:
        return []

    # A gold section-title band is usually one wide merged cell — Excel (and
    # openpyxl) only carries the fill on the merge's top-left anchor cell, not
    # on every covered cell, so a per-cell fill count alone misses it. Treat a
    # single-row merge spanning at least half the columns, whose anchor cell
    # is gold, as a full gold band across its span.
    wide_gold_rows: set[int] = set()
    for m in merges:
        start_row, end_row = m.get("startRow", -1), m.get("endRow", -1)
        if start_row != end_row or start_row < 0:
            continue
        span = m.get("endCol", 0) - m.get("startCol", 0) + 1
        if span < max(2, ncols // 2):
            continue
        anchor_fill = (styles.get(f"{start_row}:{m.get('startCol', 0)}") or {}).get("fill")
        if is_gold_fill(anchor_fill):
            wide_gold_rows.add(start_row)

    pairs: list[tuple[int, int]] = []
    for r in range(n_rows - 1):
        if r in wide_gold_rows:
            pairs.append((r, r + 1))
            continue
        gold_cols = sum(1 for c in range(ncols) if is_gold_fill((styles.get(f"{r}:{c}") or {}).get("fill")))
        if gold_cols >= max(2, ncols // 2):
            pairs.append((r, r + 1))
    return pairs


def _section_break_rows(block: dict[str, Any], data_rows: list[int]) -> set[int]:
    """Rows that start a new visual section (a filled band spanning the row).

    Used as preferred split points so panel/lighting schedules break *between*
    controller/section blocks instead of orphaning a few trailing rows.

    Phase F: when the block has repeating gold+gray controller sections, the
    gold rows are the ONLY preferred/allowed break points — never a generic
    keyword/fill match that could land strictly inside a section pair.
    """
    gold_pairs = _gold_section_starts(block)
    if gold_pairs:
        gold_rows = {g for g, _ in gold_pairs}
        return {r for r in data_rows if r in gold_rows}

    styles = block.get("styles") or {}
    grid = block.get("grid") or []
    ncols = max((len(r) for r in grid), default=0)
    breaks: set[int] = set()
    if not ncols:
        return breaks
    for r in data_rows:
        banded = sum(1 for c in range(ncols) if (styles.get(f"{r}:{c}") or {}).get("fill"))
        text = " ".join(str(c or "") for c in (grid[r] if r < len(grid) else [])).lower()
        if banded >= max(2, ncols // 2):
            breaks.add(r)
        elif any(k in text for k in ("lcp-1", "lcp-2", "pr0663", "expansion", "relay", "contactor", "controller i/o")):
            breaks.add(r)
    return breaks


def _section_aware_chunks(
    block: dict[str, Any],
    data_rows: list[int],
    header_h: float,
    budget: float,
) -> list[list[int]]:
    """Split ``data_rows`` into page chunks that only ever cut at a gold
    section boundary, unless a single section alone exceeds one page's
    budget — then (and only then) hard-cut inside it at a plain row
    boundary (FINAL RELEASE CLEANUP 4H+SA38, Phase F rule 7). Used instead
    of ``_balanced_chunks`` whenever the block has gold+gray controller
    sections (see ``_gold_section_starts``).
    """
    row_h = block.get("rowHeights") or []

    def h(r: int) -> float:
        return row_h[r] if r < len(row_h) else DEFAULT_ROW_HEIGHT_PX

    gold_pairs = _gold_section_starts(block)
    gold_rows = {g for g, _ in gold_pairs}
    repeat_h_by_gold = {g: h(g) + h(gr) for g, gr in gold_pairs}

    sections: list[list[int]] = []
    cur_section: list[int] = []
    for r in data_rows:
        if r in gold_rows and cur_section:
            sections.append(cur_section)
            cur_section = []
        cur_section.append(r)
    if cur_section:
        sections.append(cur_section)

    data_budget = max(1.0, budget - header_h)

    chunks: list[list[int]] = []
    cur: list[int] = []
    used = 0.0
    for section in sections:
        sec_h = sum(h(r) for r in section)
        repeat_extra = repeat_h_by_gold.get(section[0], 0.0)

        if cur and used + sec_h > data_budget:
            chunks.append(cur)
            cur = []
            used = 0.0

        if sec_h > data_budget:
            # A single section alone doesn't fit one page — hard-split at a
            # plain row boundary. Every sub-chunk after the first repeats
            # this section's own gold+gray pair (added back in
            # _split_excel_range_block), so reserve that height for them.
            if cur:
                chunks.append(cur)
                cur = []
                used = 0.0
            i = 0
            first_sub = True
            while i < len(section):
                sub: list[int] = []
                sub_budget = data_budget if first_sub else max(1.0, data_budget - repeat_extra)
                sub_used = 0.0
                while i < len(section) and (not sub or sub_used + h(section[i]) <= sub_budget):
                    sub.append(section[i])
                    sub_used += h(section[i])
                    i += 1
                chunks.append(sub)
                first_sub = False
            continue

        cur.extend(section)
        used += sec_h

    if cur:
        chunks.append(cur)
    return [c for c in chunks if c]


def _logical_section_chunks(block: dict[str, Any], data_rows: list[int]) -> list[list[int]] | None:
    """Known SA31 schedule section splits, used only when a split is required."""
    grid = block.get("grid") or []
    family = block.get("pageFamily", "")
    sheet_blob = f"{block.get('sourceSheet', '')} {block.get('sourceRange', '')}".lower()

    def row_text(r: int) -> str:
        return " ".join(str(c or "") for c in (grid[r] if r < len(grid) else [])).lower()

    if family == "panelDetail":
        lcp2 = next((r for r in data_rows if "lcp-2" in row_text(r) or "contactor panel" in row_text(r)), None)
        if lcp2 is not None:
            before = [r for r in data_rows if r < lcp2]
            after = [r for r in data_rows if r >= lcp2]
            if before and len(after) >= MIN_ORPHAN_DATA_ROWS:
                return [before, after]

    if "lighting" in sheet_blob or any("lighting" in row_text(r) for r in data_rows[:5]):
        relay = next((r for r in data_rows if "relay" in row_text(r) or "contactor" in row_text(r)), None)
        if relay is not None:
            before = [r for r in data_rows if r < relay]
            after = [r for r in data_rows if r >= relay]
            if before and len(after) >= MIN_ORPHAN_DATA_ROWS:
                return [before, after]

    if family == "idfTable" and len(data_rows) >= 40:
        mid = len(data_rows) // 2
        return [data_rows[:mid], data_rows[mid:]]

    return None


def _balanced_chunks(
    block: dict[str, Any],
    data_rows: list[int],
    header_h: float,
    n_pages: int,
    budget: float,
) -> list[list[int]]:
    """Distribute ``data_rows`` across ``n_pages`` as evenly as possible (by
    rendered height), never exceeding the page budget, snapping cuts to section
    boundaries, and never stranding an orphan tail (< MIN_ORPHAN_DATA_ROWS)."""
    row_h = block.get("rowHeights") or []

    def h(r: int) -> float:
        return row_h[r] if r < len(row_h) else DEFAULT_ROW_HEIGHT_PX

    total = sum(h(r) for r in data_rows)
    target = max(1.0, total / n_pages)
    breaks = _section_break_rows(block, data_rows)

    chunks: list[list[int]] = []
    cur: list[int] = []
    used = 0.0
    pages_left = n_pages
    n = len(data_rows)

    for idx, r in enumerate(data_rows):
        rh = h(r)
        rows_left = n - idx
        # Hard cut: this row would overflow the usable page budget.
        if cur and used + rh > budget:
            chunks.append(cur)
            cur = []
            used = 0.0
            if pages_left > 1:
                pages_left -= 1
        # Balanced cut: hit the per-page height target with pages to spare and no
        # orphan risk. Snap early to a section band if one lands near the target.
        elif (
            cur
            and pages_left > 1
            and rows_left > MIN_ORPHAN_DATA_ROWS
            and len(cur) >= MIN_ORPHAN_DATA_ROWS
            and (used >= target or (r in breaks and used >= target * 0.8))
        ):
            chunks.append(cur)
            cur = []
            used = 0.0
            pages_left -= 1
        cur.append(r)
        used += rh

    if cur:
        chunks.append(cur)

    # Orphan sweep: pull rows back so the last page is never a tiny tail.
    if len(chunks) >= 2 and len(chunks[-1]) < MIN_ORPHAN_DATA_ROWS:
        while (
            len(chunks[-1]) < MIN_ORPHAN_DATA_ROWS
            and len(chunks) >= 2
            and len(chunks[-2]) > MIN_ORPHAN_DATA_ROWS
        ):
            chunks[-1].insert(0, chunks[-2].pop())
    return chunks


def _excel_data_chunks(block: dict[str, Any], data_rows: list[int], header_h: float) -> list[list[int]]:
    """Split data rows into balanced, section-aware page chunks.

    First a greedy pass learns the minimum page count that fits the height
    budget; then rows are distributed evenly across exactly that many pages so
    we never produce a full page followed by a short orphan tail (the old
    37/11 IDF and RO9–RO12 LCP failures)."""
    row_h = block.get("rowHeights") or []

    def h(r: int) -> float:
        return row_h[r] if r < len(row_h) else DEFAULT_ROW_HEIGHT_PX

    if not data_rows:
        return []

    # A page can hold as many natural rows as fit the safe body budget once the
    # range is scaled down to its minimum readable scale — so we only split when
    # the range genuinely cannot fit even at min scale (Phase C rule 1: scale
    # before split; SAFE_BODY_BUDGET keeps the bottom-gap margin either way).
    min_scale = max(_block_min_scale(block), 0.2)
    budget = SAFE_BODY_BUDGET / min_scale

    # 1) Greedy pass → minimum page count.
    n_pages = 0
    i = 0
    while i < len(data_rows):
        used = header_h
        took = False
        while i < len(data_rows):
            if took and used + h(data_rows[i]) > budget:
                break
            used += h(data_rows[i])
            i += 1
            took = True
        n_pages += 1

    if n_pages <= 1:
        return [list(data_rows)]

    logical = _logical_section_chunks(block, list(data_rows))
    if logical and len(logical) == n_pages:
        return logical

    # 2) Gold+gray controller/module sections (Phase F): never cut strictly
    # inside a section unless that section alone exceeds one page.
    if _gold_section_starts(block):
        return _section_aware_chunks(block, list(data_rows), header_h, budget)

    # 3) Balanced, section-aware distribution across exactly n_pages.
    return _balanced_chunks(block, list(data_rows), header_h, n_pages, budget)



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
            # Phase C rule 5: never claim a clip happened — the renderer always
            # auto-shrinks to fit (it never crops), but shrinking this far means
            # the result would read below the accepted minimum, which is worth a
            # loud, exact-phrase warning in the editor/export diagnostics.
            warn = list(block.get("layoutWarnings") or [])
            warn.append(
                "TABLE OVERFLOW — NOT EXPORTED CLIPPED: range exceeds one page "
                "even at minimum readable scale, and continuation is disabled "
                "for this page; content is auto-shrunk below the readable floor "
                "instead of being cropped."
            )
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

    # Phase F rule 5/7: a chunk whose first row falls strictly inside a gold
    # section (its own gold+gray pair isn't already the start of the chunk —
    # only possible from a forced mid-section hard split) gets that section's
    # header pair unioned in, so the continuation repeats its own controller
    # section header instead of showing orphaned data rows with no label.
    gold_pairs = sorted(_gold_section_starts(block))

    def row_indices_for(chunk: list[int]) -> list[int]:
        ids = set(repeat) | set(chunk)
        if gold_pairs and chunk:
            first = chunk[0]
            owning = None
            for g, gr in gold_pairs:
                if g <= first:
                    owning = (g, gr)
                else:
                    break
            if owning:
                ids.add(owning[0])
                ids.add(owning[1])
        return sorted(ids)

    return [
        _slice_excel_block(block, row_indices_for(chunk), ci)
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
    if is_sheet_index_page(page) or page.get("pageType") in ("cover", "canvas", "hybrid", "underlay"):
        return False
    return True


def _append_continuation_pages(
    composed: list[dict[str, Any]],
    base: dict[str, Any],
    groups: list[list[dict[str, Any]]],
    used_codes: set[str],
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
        code = _next_available_continuation_code(base_code, ci, used_codes)
        composed.append(
            {
                "id": f"{group_id}_c{ci}",
                "order": base.get("order", 0),
                "include": base.get("include", True),
                "sheetCode": code,
                "displaySheetCode": code,
                "sheetTitle": cont_title,
                "sheetTab": base.get("sheetTab", ""),
                "pageType": base.get("pageType", "data-grid"),
                "pageFamily": base.get("pageFamily", "table"),
                "layoutProfile": base.get("layoutProfile", "front_matter_table"),
                "twoUp": False,
                "renderMode": base.get("renderMode", "normalized"),
                "renderProfile": base.get("renderProfile", "singh360_standard_table"),
                "normalizedHeaderStyle": base.get("normalizedHeaderStyle", "orange"),
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


def _page_font_size(page: dict[str, Any]) -> float:
    """Font size the Singh360 profile targets for this page family.

    Minimums (TABLE STYLE 4F, Phase C): normal table 8pt, dense table 7pt,
    absolute floor 6.5pt. The RDM/IDF network layout carries its own explicit
    ``fontSize`` on its block (see ``page_render_diagnostics``), which takes
    priority over this family default.
    """
    family = page.get("pageFamily", "table")
    if family in ("matrix", "idfTable", "ioSchedule", "panelDetail", "rackLayout"):
        return 7.0
    return 8.0


def page_render_diagnostics(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-page render diagnostics for the import/export log (Phase G).

    Reports family, render profile, computed scale, font size, rows rendered and
    the continuation count/reason so a user can see exactly why a page split."""
    included = [p for p in pages if p.get("include", True)]
    # Continuation counts per group.
    group_counts: dict[str, int] = {}
    for p in included:
        gid = p.get("pageGroupId") or p.get("id")
        group_counts[gid] = group_counts.get(gid, 0) + 1

    out: list[dict[str, Any]] = []
    for p in included:
        gid = p.get("pageGroupId") or p.get("id")
        cont_total = group_counts.get(gid, 1)
        blocks = p.get("blocks") or []
        xr = next((b for b in blocks if b.get("type") == "excelRange"), None)
        idf = next((b for b in blocks if b.get("type") == "idfNetworkTable"), None)

        two_up = bool(idf and idf.get("layoutMode") == "two_up")
        if idf is not None:
            best = 1.0
            min_scale = 1.0
            content_w = int(idf.get("contentWidth") or 0)
            content_h = int(idf.get("contentHeight") or 0)
            rows = int(idf.get("sourceRowCount") or 0)
            font_size = float(idf.get("fontSize") or DENSE_FONT_SIZE_FALLBACK)
            clipping = any(
                token in str(warning).casefold()
                for warning in (idf.get("layoutWarnings") or [])
                for token in ("clip", "overflow")
            )
            if two_up:
                reason = "network_48_port: two-up 1–24 / 25–48" if rows == 48 else (
                    f"network_48_port: two-up {idf.get('portRangeLeft', '')} / {idf.get('portRangeRight', '')}"
                )
            else:
                reason = "network_48_port: one-page full table, font >= 6.5"
        else:
            best = round(_excel_best_scale(xr), 3) if xr else 1.0
            min_scale = _block_min_scale(xr) if xr else EXCEL_MIN_SCALE
            content_w, content_h = _excel_natural_size(xr) if xr else (0, 0)
            rows = len(xr.get("grid") or []) if xr else sum(
                len(b.get("rows") or []) for b in blocks if b.get("type") in ("table", "matrix")
            )
            font_size = _page_font_size(p)
            if cont_total > 1:
                reason = "balanced split (range exceeds one page at min scale)"
            elif best < 1.0:
                reason = "single page, scaled to fit body"
            else:
                reason = "single page"
            clipping = bool(xr and (not _block_allows_continuation(xr)) and best < min_scale)

        # Phase I: render-range-before/after-trim + safe body + bottom gap, so a
        # diagnostic consumer can see exactly why a page did/did not need to
        # split without re-deriving the fit math.
        rows_before = xr.get("rowsBeforeTrim") if xr else None
        cols_before = xr.get("colsBeforeTrim") if xr else None
        rows_after = xr.get("rowsAfterTrim") if xr else None
        cols_after = xr.get("colsAfterTrim") if xr else None
        rendered_h = content_h * best if best else content_h
        bottom_gap = round(BODY_BUDGET - rendered_h, 1)
        # A negative gap can only happen if best_scale/content math disagrees
        # with the renderer's own fit-to-body pass; flag it defensively too.
        if bottom_gap < 0:
            clipping = True

        out.append(
            {
                "sheetCode": p.get("displaySheetCode") or p.get("sheetCode", ""),
                "sourceSheetCode": p.get("sheetCode", ""),
                "titleBlockSheetCode": p.get("displaySheetCode") or p.get("sheetCode", ""),
                "outputOrder": p.get("order", 0),
                "pageTitle": p.get("sheetTitle", ""),
                "included": bool(p.get("include", True)),
                "renderMode": p.get("renderMode", "normalized"),
                "renderProfile": p.get("renderProfile", "singh360_standard_table"),
                "layoutProfile": p.get("layoutProfile", "front_matter_table"),
                "headerStyle": p.get("normalizedHeaderStyle", "orange"),
                "bestScale": best,
                "minScale": min_scale,
                "fontSize": font_size,
                "sourceRows": len(xr.get("srcRows") or []) if xr else rows,
                "outputRows": rows,
                "contentWidth": content_w,
                "contentHeight": content_h,
                "renderRangeBeforeTrim": (
                    f"{rows_before}x{cols_before}" if rows_before is not None else ""
                ),
                "renderRangeAfterTrim": (
                    f"{rows_after}x{cols_after}" if rows_after is not None else ""
                ),
                "safeBodyWidth": BODY_W,
                "safeBodyHeight": SAFE_BODY_BUDGET,
                "bottomGap": bottom_gap,
                "rowsPerPage": rows,
                "clipping": clipping,
                "twoUp": two_up,
                "splitMode": p.get("splitMode", "none"),
                "continuationOf": p.get("continuationOf"),
                "continuationTotal": cont_total,
                "reason": reason,
            }
        )
    return out


def log_render_diagnostics(pages: list[dict[str, Any]]) -> None:
    """Emit a one-line render diagnostic per page group to stdout (Phase G/E).

    Includes page code, title, render/layout profile, font size, scale, table
    width/height, split mode, split reason, row count, and (for RDM/IDF pages)
    whether a two-up layout was used.
    """
    seen: set[str] = set()
    for d in page_render_diagnostics(pages):
        gid = d.get("continuationOf") or d.get("sheetCode")
        if d.get("continuationOf") and gid in seen:
            continue
        seen.add(gid or "")
        n = d["continuationTotal"]
        pages_txt = f"{n} page{'s' if n != 1 else ''}"
        print(
            f"Sheet {d['sheetCode']} {d['pageTitle']}: profile={d['layoutProfile']}, {pages_txt}, "
            f"rows {d['outputRows']}, size {d['contentWidth']}x{d['contentHeight']}, "
            f"scale {d['bestScale']}, font {d['fontSize']}, bottomGap={d['bottomGap']}, "
            f"splitMode={d['splitMode']}, twoUp={d['twoUp']}, clipping={d['clipping']}, "
            f"{'continuation ' + str(n - 1) if n > 1 else 'no continuation'} "
            f"[{d['reason']}]"
        )


# --------------------------------------------------------------------------
# Public: compose_pages
# --------------------------------------------------------------------------
def compose_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a new page list where overflowing pages are split into generated
    continuation pages. Base pages keep their id; continuations are inserted
    immediately after and flagged as generated.
    """
    if any(
        page.get("generatedContinuation")
        and re.fullmatch(r".+_c\d+", str(page.get("id") or ""))
        for page in pages
    ):
        existing = deepcopy(pages)
        for order, page in enumerate(existing, start=1):
            page["order"] = order
        return existing

    composed: list[dict[str, Any]] = []
    used_codes = {
        _code_key(str(page.get("displaySheetCode") or page.get("sheetCode") or ""))
        for page in pages
        if str(page.get("displaySheetCode") or page.get("sheetCode") or "").strip()
    }

    for page in pages:
        if not page.get("include", True):
            # Exclusion controls publication only. Keep the complete editable
            # page and its manual canvas state in the project; export/index
            # filtering happens downstream.
            composed.append(deepcopy(page))
            continue

        blocks = page.get("blocks") or []
        page_type = page.get("pageType", "")
        page.setdefault("pageFamily", page_family(page.get("sheetTab", ""), page.get("sheetTitle", ""), ""))
        page.setdefault("layoutProfile", "front_matter_table")
        page.setdefault("twoUp", False)
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
                    _append_continuation_pages(composed, base, [[p] for p in parts], used_codes)
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
        _append_continuation_pages(composed, base, groups, used_codes)

    # Re-sequence order to reflect insertion order.
    for i, p in enumerate(composed, start=1):
        p["order"] = i
    return composed
