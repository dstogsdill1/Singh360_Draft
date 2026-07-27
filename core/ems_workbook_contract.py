"""Canonical workbook-to-drawing bindings for Singh360 EMS packages.

``00_INDEX`` decides which physical drawing pages publish.  The physical
``EMS ...`` worksheets are page containers only; table content comes from the
canonical editable data sheets declared here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


CANONICAL_REPOSITORY = "dstogsdill1/Singh360_Draft"

RECIPE_HEADERS = ("field", "value", "notes")
RECIPE_MARKERS = (
    "current content",
    "paste source snapshot",
    "allow app renderer",
    "source / data",
)

SAMPLE_ROW_MARKERS = (
    "sample from",
    "placeholder count",
    "paste/assign",
    "paste from",
    "paste/normalize",
    "fill from",
    "spare network port",
    "generated regression",
)


@dataclass(frozen=True)
class CanonicalSource:
    """One editable source table used to render a published page."""

    names: tuple[str, ...]
    filter_column: str = ""
    filter_value: str = ""
    view: str = ""

    @property
    def canonical_name(self) -> str:
        return self.names[0]


FRONT_MATTER_SOURCES: dict[str, CanonicalSource] = {
    "3.0": CanonicalSource(("32_GUIDELINES", "92_GUIDELINES")),
    "4.0": CanonicalSource(("33_ABBREVIATIONS", "93_ABBREVIATIONS")),
    "5.0": CanonicalSource(("34_PROJECT_DIRECTORY", "04_PROJECT_DIRECTORY")),
    "6.0": CanonicalSource(("35_PROJECT_SCOPE", "03_SCOPE_AND_PLAN")),
    "7.0": CanonicalSource(("36_WORKFLOW_MILESTONES", "06_WORKFLOW_MILESTONES")),
    "8.0": CanonicalSource(("37_RESPONSIBILITY_MATRIX", "05_RESPONSIBILITY_MATRIX")),
}


def _code_number(sheet_code: str) -> str:
    match = re.search(r"\bEMS\s+(\d+(?:\.\d+)?)", str(sheet_code or ""), re.IGNORECASE)
    return match.group(1) if match else ""


def canonical_sources_for_page(
    sheet_code: str,
    sheet_tab: str = "",
    sheet_title: str = "",
) -> tuple[CanonicalSource, ...]:
    """Return the canonical editable sources for one indexed drawing page."""
    code = _code_number(sheet_code)
    text = f"{sheet_tab} {sheet_title}".casefold()

    if code == "2.0" or "sheet index" in text or "table of contents" in text:
        return (CanonicalSource(("00_INDEX",)),)
    if code in FRONT_MATTER_SOURCES:
        return (FRONT_MATTER_SOURCES[code],)
    if code == "10.0" or "bill of materials" in text:
        return (CanonicalSource(("29_BOM", "19_BILL_OF_MATERIALS")),)
    if code in {"12.1", "17.0"}:
        return (
            CanonicalSource(("24_REFRIG_CIRCUITS", "14_REFRIG_CIRCUITS")),
            CanonicalSource(("25_RACKS", "15_RACKS")),
        )
    if code == "23.0":
        return (
            CanonicalSource(
                ("20_CONTROLLERS", "10_CONTROLLERS"),
                view="case_controllers",
            ),
        )
    if code in {"18.0", "19.0", "20.0"}:
        rack = {"18.0": "A", "19.0": "B", "20.0": "C"}[code]
        return (
            CanonicalSource(
                ("23_PANEL_IO", "13_PANEL_IO"),
                filter_value=rack,
                view="rack_io",
            ),
        )
    if code == "13.0":
        return (
            CanonicalSource(
                ("21_NETWORK_PORTS", "11_NETWORK_PORTS"),
                view="network_summary",
            ),
            CanonicalSource(
                ("22_PANELS", "12_PANELS"),
                view="wicp_count_summary",
            ),
        )
    if code in {"13.1", "13.2", "13.3"}:
        idf = code.rsplit(".", 1)[-1]
        return (
            CanonicalSource(
                ("21_NETWORK_PORTS", "11_NETWORK_PORTS"),
                "IDF",
                idf,
            ),
        )
    if code == "14.0":
        return (CanonicalSource(("28_CABLE_PULLS", "18_CABLE_SCHEDULE")),)
    if code == "21.0":
        return (
            CanonicalSource(
                ("22_PANELS", "12_PANELS"),
                view="wicp_count_summary",
            ),
        )
    if code == "22.0":
        return (
            CanonicalSource(
                ("23_PANEL_IO", "13_PANEL_IO"),
                view="wicp_io",
            ),
        )
    if code in {"24.0", "24.1", "24.2"}:
        view = {
            "24.0": "lighting_matrix",
            "24.1": "lighting_io",
            "24.2": "lighting_dimming",
        }[code]
        return (
            CanonicalSource(
                ("26_LIGHTING_OUTPUTS", "17_LIGHTING_OUTPUTS"),
                view=view,
            ),
        )
    if code == "25.0":
        return (CanonicalSource(("27_HVAC_EQUIPMENT", "16_HVAC_EQUIPMENT")),)
    if code == "26.0":
        return (CanonicalSource(("30_COMMISSIONING", "20_COMMISSIONING")),)
    if code == "27.0":
        return (CanonicalSource(("31_OPEN_ITEMS", "07_OPEN_ITEMS")),)
    return ()


def _normalized_row(row: list[Any] | tuple[Any, ...]) -> list[str]:
    return [" ".join(str(value or "").split()).strip().casefold() for value in row]


def is_recipe_grid(grid: list[list[Any]]) -> bool:
    """True when a worksheet is a page recipe rather than publishable data."""
    for row in grid[:12]:
        normalized = _normalized_row(row)
        populated = [value for value in normalized if value]
        if tuple(populated[:3]) == RECIPE_HEADERS:
            return True
        blob = " | ".join(populated)
        if any(marker in blob for marker in RECIPE_MARKERS):
            return True
    return False


def sample_row_numbers(grid: list[list[Any]]) -> list[int]:
    """Return one-based worksheet rows containing template/sample engineering."""
    hits: list[int] = []
    for row_number, row in enumerate(grid[4:], start=5):
        blob = " | ".join(_normalized_row(row))
        if blob and any(marker in blob for marker in SAMPLE_ROW_MARKERS):
            hits.append(row_number)
    return hits


def header_row_index(grid: list[list[Any]]) -> int | None:
    """Find the canonical table header after the title/note/blank style rows."""
    if not grid:
        return None
    if len(grid) >= 4 and any(str(value or "").strip() for value in grid[3]):
        return 3
    for index, row in enumerate(grid[:20]):
        populated = sum(1 for value in row if str(value or "").strip())
        if populated >= 2:
            return index
    return None
