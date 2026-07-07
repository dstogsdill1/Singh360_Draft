"""Smoke: LCP / Lighting continuations split by logical sections, not tails."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from core.workbook_importer import import_workbook

GOLD = PatternFill("solid", fgColor="FFC000")
GRAY = PatternFill("solid", fgColor="D9D9D9")


def _section_row(ws, row: int, title: str, cols: int = 6) -> None:
    ws.cell(row, 1, title)
    ws.cell(row, 1).fill = GOLD
    ws.cell(row, 1).font = Font(bold=True)
    for c in range(2, cols + 1):
        ws.cell(row, c).fill = GOLD


def _headers(ws, row: int, cols: int = 6) -> None:
    for c in range(1, cols + 1):
        cell = ws.cell(row, c, f"Header {c}")
        cell.fill = GRAY
        cell.font = Font(bold=True)


def _workbook(path: Path) -> None:
    wb = Workbook()
    idx = wb.active
    idx.title = "00_INDEX"
    idx.append(["Order", "Sheet Tab", "Page Title", "Include?", "Use Source"])
    idx.append(["14", "LIGHTING-TDB", "Lighting Output Matrix", "YES", ""])
    idx.append(["15", "LCP Panel", "LCP Panel Schedule", "YES", ""])

    lighting = wb.create_sheet("LIGHTING-TDB")
    _section_row(lighting, 1, "Controller I/O Table")
    _headers(lighting, 2)
    r = 3
    for i in range(28):
        for c in range(1, 7):
            lighting.cell(r, c, f"IO {i}-{c}")
        lighting.row_dimensions[r].height = 30
        r += 1
    _section_row(lighting, r, "Relay / Contactor Schedule")
    relay_row = r
    r += 1
    _headers(lighting, r)
    r += 1
    for i in range(26):
        for c in range(1, 7):
            lighting.cell(r, c, f"Relay {i}-{c}")
        lighting.row_dimensions[r].height = 30
        r += 1

    lcp = wb.create_sheet("LCP Panel")
    _section_row(lcp, 1, "LCP-1 Dimming Panel")
    _headers(lcp, 2)
    r = 3
    for i in range(18):
        for c in range(1, 7):
            lcp.cell(r, c, f"LCP1 {i}-{c}")
        lcp.row_dimensions[r].height = 30
        r += 1
    _section_row(lcp, r, "Expansion I/O Device PR0663")
    r += 1
    _headers(lcp, r)
    r += 1
    for i in range(10):
        for c in range(1, 7):
            lcp.cell(r, c, f"PR0663 {i}-{c}")
        lcp.row_dimensions[r].height = 30
        r += 1
    _section_row(lcp, r, "LCP-2 Contactor Panel")
    lcp2_row = r
    r += 1
    _headers(lcp, r)
    r += 1
    for i in range(26):
        for c in range(1, 7):
            lcp.cell(r, c, f"RO{i + 1}-{c}")
        lcp.row_dimensions[r].height = 30
        r += 1

    wb.save(path)


def _page_text(page: dict) -> str:
    return "\n".join(" | ".join(r) for b in page.get("blocks") or [] for r in (b.get("grid") or []))


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "logical_splits.xlsx"
    _workbook(xlsx)
    proj = import_workbook(xlsx, project_id="split1")
    problems: list[str] = []

    lcp_pages = [p for p in proj["pages"] if p["sheetTab"] == "LCP Panel"]
    if len(lcp_pages) != 2:
        problems.append(f"LCP expected 2 logical pages, got {len(lcp_pages)}")
    else:
        if "LCP-2 Contactor Panel" not in _page_text(lcp_pages[1]):
            problems.append("LCP continuation does not start with LCP-2 section")
        data_rows = len(lcp_pages[1]["blocks"][0].get("grid") or [])
        if data_rows < 8:
            problems.append("LCP continuation is an orphan tail")

    lighting_pages = [p for p in proj["pages"] if p["sheetTab"] == "LIGHTING-TDB"]
    if len(lighting_pages) != 2:
        problems.append(f"Lighting expected 2 logical pages, got {len(lighting_pages)}")
    else:
        if "Relay / Contactor Schedule" not in _page_text(lighting_pages[1]):
            problems.append("Lighting continuation does not start with relay/contactor section")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK - logical section splits passed")


if __name__ == "__main__":
    main()
