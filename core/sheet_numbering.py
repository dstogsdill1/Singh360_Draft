"""core/sheet_numbering.py — Milestone 4A EMS sheet numbering scheme (Phase 8).

Deterministic default sheet index for an EMS drawing set. Continuation sheets
(a/b/...) are only ever added when measured content genuinely overflows — this
module never fabricates them. No sheet body should scroll; overflow is handled
by the page templates (Phase 5) creating explicit continuation sheets.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SheetDef:
    number: str
    title: str
    kind: str  # cover | index | directory | notes | scope | matrix | bom |
               # layout | network | oneline | comms | refrigeration | hvac |
               # lighting | power | device_location | vendor_pdf | appendix


# Canonical default set. Series prefixes (3.x, 4.x, ...) expand as content
# requires; the base entries below are always present.
DEFAULT_SHEETS: list[SheetDef] = [
    SheetDef("EMS 0.0", "Cover / Project Info", "cover"),
    SheetDef("EMS 0.1", "Sheet Index / TOC", "index"),
    SheetDef("EMS 0.2", "Project Directory / Contacts", "directory"),
    SheetDef("EMS 0.3", "General Notes / Singh360 / H-E-B Guidelines", "notes"),
    SheetDef("EMS 0.4", "Project Scope / Workflow", "scope"),
    SheetDef("EMS 0.5", "Responsibility Matrix", "matrix"),
    SheetDef("EMS 0.6", "Bill of Materials", "bom"),
    SheetDef("EMS 1.0", "EMS Controls Overall Layout", "layout"),
    SheetDef("EMS 2.0", "IDF / Network / Data Manager", "network"),
    SheetDef("EMS 2.1", "RDM One-Line Diagram", "oneline"),
    SheetDef("EMS 2.2", "BACnet / CANbus / Communications Loop", "comms"),
    SheetDef("EMS 3.0", "Refrigeration / WICP / Rack / Case Controllers", "refrigeration"),
    SheetDef("EMS 4.0", "HVAC / OAU / PACU", "hvac"),
    SheetDef("EMS 5.0", "Lighting Controls / Output Matrix / LCP", "lighting"),
    SheetDef("EMS 6.0", "Power Monitoring", "power"),
    SheetDef("EMS 7.0", "Interior / Exterior Device Locations", "device_location"),
    SheetDef("EMS 8.0", "Vendor / CD Panel Schematics / PDF Underlays", "vendor_pdf"),
    SheetDef("EMS 9.0", "Company / Closeout / Appendix", "appendix"),
]

# Series → next-index tracking so callers can add e.g. EMS 3.1, EMS 3.2 without
# colliding, but only when they have real content for them.
SERIES_PREFIXES = {
    "refrigeration": "EMS 3.",
    "hvac": "EMS 4.",
    "lighting": "EMS 5.",
    "power": "EMS 6.",
    "device_location": "EMS 7.",
    "vendor_pdf": "EMS 8.",
    "appendix": "EMS 9.",
}


def default_sheet_index() -> list[dict]:
    """Return the default EMS sheet index as serializable dicts."""
    return [{"number": s.number, "title": s.title, "kind": s.kind} for s in DEFAULT_SHEETS]


def continuation_number(base_number: str, index: int) -> str:
    """Return a continuation sheet id (e.g. 'EMS 0.6a') — index 1 == 'a'.

    Only call this when measured content genuinely overflows a sheet.
    """
    if index < 1:
        return base_number
    suffix = chr(ord("a") + index - 1)
    return f"{base_number}{suffix}"


def next_in_series(kind: str, used_numbers: set[str]) -> str:
    """Allocate the next available number in a series (e.g. EMS 3.1, 3.2)."""
    prefix = SERIES_PREFIXES.get(kind)
    if not prefix:
        return ""
    i = 0
    while True:
        candidate = f"{prefix}{i}"
        if candidate not in used_numbers:
            return candidate
        i += 1
