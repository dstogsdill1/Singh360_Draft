"""Singh360 PDF-quality table profiles and semantic compaction.

Only normalized/output block geometry is changed. Source worksheet values,
styles, row/column dimensions, merges, and print areas remain intact.
"""
from __future__ import annotations

import math
import re
from typing import Any

DEFAULT_BODY_W = 1600
AUTO_TARGET = int(DEFAULT_BODY_W * 0.92)
DENSE_TARGET = int(DEFAULT_BODY_W * 0.94)

_MANAGED = {
    "guideline_table",
    "instruction_table",
    "project_scope_table",
    "workflow_milestone_table",
    "contact_directory_table",
    "equipment_supply_schedule",
    "cable_termination_schedule",
    "bill_of_materials_schedule",
    "responsibility_matrix",
}

_NARROW = (
    "qty", "quantity", "no", "number", "#", "id", "type", "status",
    "marker", "step", "ro#", "di#", "aio#", "input", "output",
)
_WIDE = (
    "description", "instruction", "scope", "use", "purpose", "device",
    "location", "destination", "notes", "remarks", "language",
    "responsibility", "guideline", "deliverable", "email",
)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def is_managed_profile(profile: str) -> bool:
    return profile in _MANAGED


def infer_named_layout_profile(
    family: str,
    page_type: str,
    blob: str,
    current: str = "",
) -> str:
    text = _norm(blob)
    if family == "companyInfo":
        return "company_info"
    if family == "idfTable":
        return "network_48_port"

    if "guideline" in text:
        return "guideline_table"
    if "field instruction" in text or "instruction" in text:
        return "instruction_table"
    if "project directory" in text or "contact" in text:
        return "contact_directory_table"
    if "project scope" in text:
        return "project_scope_table"
    if "workflow" in text or "milestone" in text:
        return "workflow_milestone_table"
    if "equipment supply" in text:
        return "equipment_supply_schedule"
    if "cable pull" in text or "termination schedule" in text:
        return "cable_termination_schedule"
    if "responsibility" in text or "responsibilities matrix" in text:
        return "responsibility_matrix"
    if "bill of material" in text or re.search(r"\bbom\b", text):
        return "bill_of_materials_schedule"

    if family in ("matrix", "ioSchedule", "panelDetail", "rackLayout"):
        return "io_table"
    if current:
        return current
    if page_type == "index":
        return "front_matter_table"
    return "front_matter_table"


def _header_row(grid: list[list[str]]) -> int:
    n_cols = max((len(row) for row in grid), default=0)
    if not n_cols:
        return 0
    for index, row in enumerate(grid[:14]):
        values = [str(cell or "").strip() for cell in row]
        non_empty = [value for value in values if value]
        if len(non_empty) < 2:
            continue
        if len(non_empty) >= max(2, n_cols - 1) and not any(len(value) > 80 for value in non_empty):
            return index
        # Semantic two-column instruction/guideline header separated by styled
        # spacer columns: "Step ... Instruction" or "Topic ... Guideline".
        joined = " | ".join(_norm(value) for value in values if value)
        if (
            ("step" in joined and "instruction" in joined)
            or ("topic" in joined and "guideline" in joined)
        ):
            return index
    return 0


def _has_text(grid: list[list[str]], column: int) -> bool:
    return any(
        column < len(row) and str(row[column] or "").strip()
        for row in grid
    )


def _compact_axis(
    block: dict[str, Any],
    profile: str,
) -> None:
    """Remove styled-but-empty spacer columns/rows from text-centric output."""
    if profile not in {
        "guideline_table",
        "instruction_table",
        "project_scope_table",
        "workflow_milestone_table",
        "contact_directory_table",
    }:
        return

    grid = [list(row) for row in (block.get("grid") or [])]
    if not grid:
        return
    styles = dict(block.get("styles") or {})
    merges = [dict(item) for item in (block.get("mergedCells") or [])]
    col_widths = list(block.get("colWidths") or [])
    row_heights = list(block.get("rowHeights") or [])
    src_rows = list(block.get("srcRows") or range(len(grid)))
    old_repeat = list(block.get("repeatRows") or [])

    n_rows = len(grid)
    n_cols = max((len(row) for row in grid), default=0)
    if not n_cols:
        return
    grid = [row + [""] * (n_cols - len(row)) for row in grid]

    # For instructions/guidelines, decorative spacer columns are not semantic
    # even when Excel borders exist. For other text profiles, only truly empty
    # columns are removed.
    keep_cols = [c for c in range(n_cols) if _has_text(grid, c)]
    if not keep_cols:
        keep_cols = [0]

    # Preserve all rows containing values. Styled blank filler rows stay in the
    # Source grid but are intentionally omitted from Normalized/PDF output.
    keep_rows = [
        r for r, row in enumerate(grid)
        if any(str(value or "").strip() for value in row)
    ]
    if not keep_rows:
        keep_rows = [0]

    col_map = {old: new for new, old in enumerate(keep_cols)}
    row_map = {old: new for new, old in enumerate(keep_rows)}

    next_grid = [
        [grid[r][c] for c in keep_cols]
        for r in keep_rows
    ]

    next_styles: dict[str, Any] = {}
    for key, value in styles.items():
        try:
            rs, cs = key.split(":")
            r, c = int(rs), int(cs)
        except (ValueError, AttributeError):
            continue
        if r in row_map and c in col_map:
            next_styles[f"{row_map[r]}:{col_map[c]}"] = value

    next_merges: list[dict[str, Any]] = []
    for merge in merges:
        old_cols = [
            c for c in keep_cols
            if int(merge.get("startCol", 0)) <= c <= int(merge.get("endCol", 0))
        ]
        old_rows = [
            r for r in keep_rows
            if int(merge.get("startRow", 0)) <= r <= int(merge.get("endRow", 0))
        ]
        if not old_cols or not old_rows:
            continue
        item = dict(merge)
        item["startCol"] = min(col_map[c] for c in old_cols)
        item["endCol"] = max(col_map[c] for c in old_cols)
        item["startRow"] = min(row_map[r] for r in old_rows)
        item["endRow"] = max(row_map[r] for r in old_rows)
        next_merges.append(item)

    block["grid"] = next_grid
    block["styles"] = next_styles
    block["mergedCells"] = next_merges
    block["colWidths"] = [
        col_widths[c] if c < len(col_widths) else 64
        for c in keep_cols
    ]
    block["rowHeights"] = [
        row_heights[r] if r < len(row_heights) else 20
        for r in keep_rows
    ]
    block["srcRows"] = [
        src_rows[r] if r < len(src_rows) else r
        for r in keep_rows
    ]

    mapped_repeat = [row_map[r] for r in old_repeat if r in row_map]
    block["repeatRows"] = sorted(set(mapped_repeat))
    old_header_count = int(block.get("headerRowCount") or 1)
    mapped_headers = [row_map[r] for r in keep_rows if r < old_header_count]
    if mapped_headers:
        block["headerRowCount"] = max(mapped_headers) + 1
    else:
        block["headerRowCount"] = min(len(next_grid), _header_row(next_grid) + 1)


def compact_block_for_profile(block: dict[str, Any], profile: str) -> None:
    _compact_axis(block, profile)


def _fit_widths(
    shares: list[float],
    target: int,
    minimums: list[int],
) -> list[int]:
    total = sum(shares) or 1.0
    widths = [
        max(minimums[index], int(round(target * share / total)))
        for index, share in enumerate(shares)
    ]
    delta = target - sum(widths)
    if delta > 0:
        order = sorted(range(len(widths)), key=lambda i: shares[i], reverse=True)
        cursor = 0
        while delta > 0 and order:
            widths[order[cursor % len(order)]] += 1
            delta -= 1
            cursor += 1
    elif delta < 0:
        order = sorted(
            range(len(widths)),
            key=lambda i: widths[i] - minimums[i],
            reverse=True,
        )
        cursor = 0
        guard = 0
        while delta < 0 and order and guard < 200000:
            index = order[cursor % len(order)]
            if widths[index] > minimums[index]:
                widths[index] -= 1
                delta += 1
            cursor += 1
            guard += 1
            if all(widths[i] <= minimums[i] for i in order):
                break
    return widths


def normalize_manual_col_widths(
    widths: list[int],
    body_w: int = DEFAULT_BODY_W,
) -> list[int]:
    if not widths:
        return []
    clean = [max(36, int(round(float(value or 64)))) for value in widths]
    total = sum(clean) or 1
    target = int(body_w * 0.92)
    shares = [value / total for value in clean]
    minimums = [36 for _ in clean]
    return _fit_widths(shares, target, minimums)


def _role_share(
    profile: str,
    header: str,
    index: int,
    n_cols: int,
) -> float:
    h = _norm(header)

    if profile in ("guideline_table", "instruction_table"):
        if any(token in h for token in ("step", "topic", "section")):
            return 0.20
        if any(token in h for token in ("instruction", "guideline", "description")):
            return 0.80

    if profile == "project_scope_table":
        if "section" in h:
            return 0.22
        if "scope" in h or "language" in h:
            return 0.58
        if "status" in h:
            return 0.08
        if "notes" in h:
            return 0.12

    if profile == "workflow_milestone_table":
        if "step" in h:
            return 0.06
        if "milestone" in h:
            return 0.18
        if "task" in h or "deliverable" in h:
            return 0.38
        if "owner" in h:
            return 0.13
        if "status" in h:
            return 0.08
        if "notes" in h:
            return 0.17

    if profile == "contact_directory_table":
        if "trade" in h or "code" in h:
            return 0.08
        if "role" in h or "responsibility" in h:
            return 0.21
        if "firm" in h:
            return 0.18
        if "contact" in h:
            return 0.15
        if "phone" in h:
            return 0.15
        if "email" in h:
            return 0.23

    if profile == "equipment_supply_schedule":
        if "qty" in h or "quantity" in h:
            return 0.055
        if "item" in h or "part" in h:
            return 0.125
        if "description" in h:
            return 0.18
        if "scope" in h or "use" in h:
            return 0.20
        if "supplied" in h:
            return 0.09
        if "installed" in h:
            return 0.09
        if "destination" in h or "location" in h:
            return 0.14
        if "notes" in h or "remarks" in h:
            return 0.12

    if profile == "cable_termination_schedule":
        if "marker" in h:
            return 0.05
        if "circuit" in h or "tag" in h:
            return 0.085
        if "cable type" in h:
            return 0.145
        if h == "from":
            return 0.12
        if h == "to":
            return 0.12
        if "purpose" in h or "device" in h:
            return 0.18
        if "cable standard" in h:
            return 0.13
        if "installed" in h:
            return 0.075
        if "notes" in h:
            return 0.095

    if profile == "bill_of_materials_schedule":
        if "qty" in h or "quantity" in h:
            return 0.06
        if "part" in h or "item" in h or "model" in h:
            return 0.16
        if "description" in h:
            return 0.27
        if "comment" in h:
            return 0.21
        if "installed" in h:
            return 0.13
        if "status" in h or "notes" in h:
            return 0.17

    if profile == "responsibility_matrix":
        if n_cols <= 5:
            if "section" in h:
                return 0.14
            if "item" in h:
                return 0.28
            if "responsibility" in h:
                return 0.18
            if "notes" in h:
                return 0.40
        else:
            if "task" in h or "component" in h:
                return 0.28
            if "notes" in h:
                return 0.22
            return 0.50 / max(1, n_cols - 2)

    if any(token in h for token in _NARROW):
        return 0.07
    if any(token in h for token in _WIDE):
        return 0.22
    return 1.0 / max(1, n_cols)


def preferred_named_col_widths(
    grid: list[list[str]],
    profile: str,
    body_w: int = DEFAULT_BODY_W,
) -> list[int] | None:
    if profile not in _MANAGED:
        return None
    n_cols = max((len(row) for row in grid), default=0)
    if not n_cols:
        return []

    row_index = _header_row(grid)
    header = grid[row_index] if row_index < len(grid) else []
    target = int(body_w * (0.94 if profile == "responsibility_matrix" and n_cols > 5 else 0.92))
    shares: list[float] = []
    minimums: list[int] = []

    for column in range(n_cols):
        value = str(header[column] if column < len(header) else "")
        if not _has_text(grid, column):
            shares.append(0.012)
            minimums.append(18)
            continue
        share = max(0.015, _role_share(profile, value, column, n_cols))
        shares.append(share)
        h = _norm(value)
        if any(token in h for token in _NARROW):
            minimums.append(46)
        elif any(token in h for token in _WIDE):
            minimums.append(92)
        else:
            minimums.append(60)

    return _fit_widths(shares, target, minimums)


def profile_body_font_px(profile: str, n_cols: int = 0) -> int | None:
    if profile in ("guideline_table", "instruction_table"):
        return 14
    if profile in (
        "project_scope_table",
        "workflow_milestone_table",
        "contact_directory_table",
    ):
        return 13
    if profile in (
        "equipment_supply_schedule",
        "cable_termination_schedule",
        "bill_of_materials_schedule",
    ):
        return 12
    if profile == "responsibility_matrix":
        return 13 if 0 < n_cols <= 5 else 11
    return None


def profile_body_font_pt(profile: str, n_cols: int = 0) -> float:
    px = profile_body_font_px(profile, n_cols)
    return round((px or 12) * 0.75, 2)


def profile_min_font_pt(profile: str, n_cols: int = 0) -> float:
    if profile in ("guideline_table", "instruction_table"):
        return 9.0
    if profile in (
        "project_scope_table",
        "workflow_milestone_table",
        "contact_directory_table",
    ):
        return 8.5
    if profile == "responsibility_matrix" and n_cols > 5:
        return 7.0
    return 8.0


def profile_min_scale(profile: str, n_cols: int = 0) -> float | None:
    if profile in ("guideline_table", "instruction_table"):
        return 0.90
    if profile in (
        "project_scope_table",
        "workflow_milestone_table",
        "contact_directory_table",
    ):
        return 0.84
    if profile in (
        "equipment_supply_schedule",
        "cable_termination_schedule",
        "bill_of_materials_schedule",
    ):
        return 0.80
    if profile == "responsibility_matrix":
        return 0.82 if 0 < n_cols <= 5 else 0.72
    return None


def profile_nowrap_columns(grid: list[list[str]], profile: str) -> list[int]:
    if not grid:
        return []
    header = grid[_header_row(grid)]
    out: list[int] = []
    for index, value in enumerate(header):
        h = _norm(value)
        if any(token in h for token in _NARROW):
            out.append(index)
        if profile == "cable_termination_schedule" and any(
            token in h for token in ("circuit", "tag", "cable type", "installed")
        ):
            out.append(index)
        if profile == "equipment_supply_schedule" and any(
            token in h for token in ("item", "part", "supplied", "installed")
        ):
            out.append(index)
        if profile == "contact_directory_table" and any(
            token in h for token in ("trade", "phone", "email")
        ):
            out.append(index)
    return sorted(set(out))


def _merge_maps(
    merges: list[dict[str, Any]],
) -> tuple[set[tuple[int, int]], dict[tuple[int, int], tuple[int, int]]]:
    covered: set[tuple[int, int]] = set()
    spans: dict[tuple[int, int], tuple[int, int]] = {}
    for merge in merges:
        sr = int(merge.get("startRow", 0))
        er = int(merge.get("endRow", sr))
        sc = int(merge.get("startCol", 0))
        ec = int(merge.get("endCol", sc))
        spans[(sr, sc)] = (er - sr + 1, ec - sc + 1)
        for row in range(sr, er + 1):
            for col in range(sc, ec + 1):
                if row == sr and col == sc:
                    continue
                covered.add((row, col))
    return covered, spans


def _wrapped_lines(text: str, width: int, font_px: int) -> int:
    clean = _norm(text)
    if not clean:
        return 1
    chars = max(8, int(max(36, width - 10) / max(5.4, font_px * 0.50)))
    words = clean.split()
    lines = 1
    used = 0
    for word in words:
        if used and used + 1 + len(word) > chars:
            lines += 1
            used = len(word)
        else:
            used += (1 if used else 0) + len(word)
    longest = max((len(word) for word in words), default=1)
    return max(lines, math.ceil(longest / chars))


def preferred_row_heights(
    grid: list[list[str]],
    col_widths: list[int],
    merges: list[dict[str, Any]] | None,
    profile: str,
    header_rows: int,
    *,
    font_px: int | None = None,
    source_heights: list[int] | None = None,
    manual: bool = False,
) -> list[int]:
    if not grid:
        return []
    if manual and source_heights:
        return [
            max(18, min(180, int(round(value or 20))))
            for value in source_heights[: len(grid)]
        ]

    n_cols = max((len(row) for row in grid), default=0)
    widths = list(col_widths) + [64] * max(0, n_cols - len(col_widths))
    covered, spans = _merge_maps(list(merges or []))
    real_header = _header_row(grid)
    px = font_px or profile_body_font_px(profile, n_cols) or 12
    line_h = max(13, int(round(px * 1.25)))
    dense = profile == "responsibility_matrix" and n_cols > 5

    out: list[int] = []
    for row_index, row in enumerate(grid):
        values = [str(value or "").strip() for value in row]
        non_empty = [value for value in values if value]
        if not non_empty:
            out.append(14)
            continue

        max_lines = 1
        full_width_anchor = False
        for column, value in enumerate(values):
            if not value or (row_index, column) in covered:
                continue
            _, col_span = spans.get((row_index, column), (1, 1))
            effective_width = sum(
                widths[c]
                for c in range(column, min(n_cols, column + col_span))
            )
            if col_span >= max(1, n_cols - 1):
                full_width_anchor = True
            max_lines = max(
                max_lines,
                min(
                    _wrapped_lines(value, effective_width, px),
                    14 if profile in ("guideline_table", "instruction_table", "project_scope_table") else 9,
                ),
            )

        if row_index < real_header and full_width_anchor:
            base = 30 if row_index == 0 else 32
        elif row_index == real_header:
            base = 30
        elif full_width_anchor and len(non_empty) == 1:
            base = 28
        else:
            base = 22 if dense else 25
        out.append(max(base, line_h * max_lines + 8))
    return out
