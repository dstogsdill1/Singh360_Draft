"""Deterministic Singh360 named table-layout profiles.

The profiles only change normalized/output geometry. They never modify the
Source worksheet grid. Column sizing is stable across initial import, browser
rebuilds, saved projects, and PDF export.
"""
from __future__ import annotations

import re
from typing import Any

DEFAULT_BODY_W = 1600

_NARROW_HEADERS = (
    "qty", "quantity", "no", "number", "#", "id", "type", "status",
    "marker", "step", "ro#", "di#", "aio#", "input", "output",
)
_WIDE_HEADERS = (
    "description", "instruction", "scope", "use", "purpose", "device",
    "location", "destination", "notes", "remarks", "language",
    "responsibility",
)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def infer_named_layout_profile(
    family: str,
    page_type: str,
    blob: str,
    current: str = "",
) -> str:
    """Return the single profile used by import, rebuild, and migration."""
    text = _norm(blob)

    if family == "companyInfo":
        return "company_info"
    if family == "idfTable":
        return "network_48_port"

    # Named sheet purposes take priority over generic family names.
    if "equipment supply" in text:
        return "equipment_supply_schedule"
    if "cable pull" in text or "termination schedule" in text:
        return "cable_termination_schedule"
    if "responsibility" in text or "responsibilities matrix" in text:
        return "responsibility_matrix"
    if "bill of material" in text or re.search(r"\bbom\b", text):
        return "bill_of_materials_schedule"
    if "instruction" in text:
        return "instruction_table"
    if any(token in text for token in ("project scope", "workflow", "milestone")):
        return "front_matter_narrative_table"

    if family in ("matrix", "ioSchedule", "panelDetail", "rackLayout"):
        return "io_table"
    if current:
        return current
    if page_type == "index":
        return "front_matter_table"
    return "front_matter_table"


def _header_share(profile: str, header: str, index: int, n_cols: int) -> float:
    h = _norm(header)

    if profile == "equipment_supply_schedule":
        if any(k in h for k in ("qty", "quantity")):
            return 0.055
        if any(k in h for k in ("item", "part")):
            return 0.125
        if "description" in h:
            return 0.18
        if "scope" in h or "use" in h:
            return 0.21
        if "supplied" in h:
            return 0.095
        if "installed" in h:
            return 0.095
        if "destination" in h or "location" in h:
            return 0.14
        if "notes" in h or "remarks" in h:
            return 0.10

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

    if profile == "responsibility_matrix":
        return 0.34 if index == 0 else 0.66 / max(1, n_cols - 1)

    if profile == "bill_of_materials_schedule":
        if any(k in h for k in ("qty", "quantity")):
            return 0.06
        if any(k in h for k in ("part", "item", "model")):
            return 0.17
        if "description" in h:
            return 0.30
        if "manufacturer" in h:
            return 0.16
        if "notes" in h or "remarks" in h:
            return 0.20

    if any(token in h for token in _NARROW_HEADERS):
        return 0.07
    if any(token in h for token in _WIDE_HEADERS):
        return 0.22
    return 1.0 / max(1, n_cols)


def _column_has_content(grid: list[list[str]], column: int) -> bool:
    return any(
        column < len(row) and str(row[column] or "").strip()
        for row in grid
    )


def _find_header_row(grid: list[list[str]]) -> int:
    n_cols = max((len(row) for row in grid), default=0)
    if not n_cols:
        return 0
    for index, row in enumerate(grid[:12]):
        values = [str(cell or "").strip() for cell in row]
        non_empty = [value for value in values if value]
        if len(non_empty) < max(2, min(n_cols, n_cols - 1)):
            continue
        if any(len(value) > 70 for value in non_empty):
            continue
        return index
    return 0


def _fit_widths(
    shares: list[float],
    target: int,
    minimums: list[int],
) -> list[int]:
    total_share = sum(shares) or 1.0
    widths = [
        max(minimums[i], int(round(target * shares[i] / total_share)))
        for i in range(len(shares))
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
        while delta < 0 and order and guard < 100000:
            i = order[cursor % len(order)]
            if widths[i] > minimums[i]:
                widths[i] -= 1
                delta += 1
            cursor += 1
            guard += 1
            if all(widths[j] <= minimums[j] for j in order):
                break
    return widths


def preferred_named_col_widths(
    grid: list[list[str]],
    profile: str,
    body_w: int = DEFAULT_BODY_W,
) -> list[int] | None:
    """Return fixed widths for a named schedule; ``None`` for generic pages."""
    named = {
        "equipment_supply_schedule",
        "cable_termination_schedule",
        "responsibility_matrix",
        "bill_of_materials_schedule",
    }
    if profile not in named:
        return None

    n_cols = max((len(row) for row in grid), default=0)
    if not n_cols:
        return []

    header_row = _find_header_row(grid)
    header = grid[header_row] if header_row < len(grid) else []
    target = int(body_w * (0.94 if profile == "responsibility_matrix" else 0.92))

    shares: list[float] = []
    minimums: list[int] = []
    for column in range(n_cols):
        value = str(header[column] if column < len(header) else "")
        if not _column_has_content(grid, column):
            shares.append(0.012)
            minimums.append(18)
            continue
        share = _header_share(profile, value, column, n_cols)
        shares.append(max(0.015, share))
        lower = _norm(value)
        if any(token in lower for token in _NARROW_HEADERS):
            minimums.append(46)
        elif any(token in lower for token in _WIDE_HEADERS):
            minimums.append(92)
        else:
            minimums.append(60)

    return _fit_widths(shares, target, minimums)


def profile_body_font_px(profile: str) -> int | None:
    if profile in ("instruction_table", "front_matter_narrative_table"):
        return 12
    if profile in (
        "equipment_supply_schedule",
        "cable_termination_schedule",
        "bill_of_materials_schedule",
        "responsibility_matrix",
    ):
        return 11
    return None


def profile_min_scale(profile: str) -> float | None:
    if profile in ("instruction_table", "front_matter_narrative_table"):
        return 7.5 / 9.0
    if profile in (
        "equipment_supply_schedule",
        "cable_termination_schedule",
        "bill_of_materials_schedule",
        "responsibility_matrix",
    ):
        return 0.75
    return None


def profile_nowrap_columns(grid: list[list[str]], profile: str) -> list[int]:
    if not grid:
        return []
    header = grid[_find_header_row(grid)]
    out: list[int] = []
    for index, value in enumerate(header):
        h = _norm(value)
        if any(token in h for token in _NARROW_HEADERS):
            out.append(index)
        elif profile == "cable_termination_schedule" and any(
            token in h for token in ("circuit", "tag", "cable type", "installed")
        ):
            out.append(index)
        elif profile == "equipment_supply_schedule" and any(
            token in h for token in ("item", "part", "supplied", "installed")
        ):
            out.append(index)
    return sorted(set(out))
