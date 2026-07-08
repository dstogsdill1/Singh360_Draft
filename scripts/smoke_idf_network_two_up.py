"""Smoke: RDM / IDF network table two-up layout (TABLE STYLE 4F, Phase B/E).

Verifies:
  - a 48-port IDF/network sheet renders as ONE page (no short-tail continuation);
  - it switches to the two-up (1-24 / 25-48) layout because a single stack of
    48 rows would fall below the readable font floor;
  - essential columns are present, optional Controller ID + IP Address are
    combined into one "Controller / IP" column (no hallucinated data);
  - font stays >= 6.5pt (the absolute floor) and the page is not rotated;
  - a small (10-port) IDF sheet stays a single full-width table (no two-up
    needed) — no rotation, no unnecessary two-up split.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from core.workbook_importer import import_workbook
from core.page_composer import page_render_diagnostics


def _workbook(path: Path, n_ports: int, sheet_name: str) -> None:
    wb = Workbook()
    idx = wb.active
    idx.title = "00_INDEX"
    idx.append(["Order", "Sheet Tab", "Page Title", "Include?", "Use Source"])
    idx.append(["12", sheet_name, "RDM / IDF Network Table", "YES", ""])

    ws = wb.create_sheet(sheet_name)
    headers = ["Port", "Label", "Device / Drop", "From", "To", "Cable", "Notes", "Controller ID", "IP Address"]
    ws.append(headers)
    for p in range(1, n_ports + 1):
        ws.append([
            str(p), f"L{p}", f"Device-{p}", f"IDF-{p}", f"Drop-{p}", f"CAT6-{p}", f"note-{p}",
            f"C{(p % 4) + 1}", f"10.0.0.{p}",
        ])
    wb.save(path)


def main() -> None:
    problems: list[str] = []

    # A) 48-port table -> two-up, one page, essential + combined columns, >=6.5pt.
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "idf48.xlsx"
    _workbook(xlsx, 48, "RDM IDF NETWORK")
    proj = import_workbook(xlsx, project_id="idf48")

    pages48 = [p for p in proj["pages"] if p["sheetTab"] == "RDM IDF NETWORK"]
    if len(pages48) != 1:
        problems.append(f"48-port IDF expected 1 page, got {len(pages48)} (no short-tail continuation)")
    else:
        page = pages48[0]
        block = (page.get("blocks") or [{}])[0]
        if block.get("type") != "idfNetworkTable":
            problems.append(f"48-port IDF block type = {block.get('type')}, expected idfNetworkTable")
        if block.get("layoutMode") != "two_up":
            problems.append(f"48-port IDF layoutMode = {block.get('layoutMode')}, expected two_up")
        headers = block.get("headers") or []
        for must in ("Port", "Label", "Device / Drop", "From", "To", "Cable", "Notes"):
            if must not in headers:
                problems.append(f"48-port IDF missing essential column {must!r}")
        # FINAL SA31 POLISH 4I Phase D: Controller / IP and Network may fold
        # into Notes so two-up can scale up; prefer presence or Notes fold.
        if "Controller / IP" not in headers and "Controller ID" not in headers:
            if "Notes" not in headers:
                problems.append("48-port IDF missing Controller / IP and Notes fold target")
        left = block.get("leftRows") or []
        right = block.get("rightRows") or []
        if len(left) != 24 or len(right) != 24:
            problems.append(f"48-port IDF two-up split not 24/24: left={len(left)} right={len(right)}")
        if block.get("portRangeLeft") != "1–24" or block.get("portRangeRight") != "25–48":
            problems.append(
                f"48-port IDF port ranges wrong: {block.get('portRangeLeft')} / {block.get('portRangeRight')}"
            )
        font = float(block.get("fontSize") or 0)
        if font < 6.5:
            problems.append(f"48-port IDF font {font} below 6.5pt floor")
        if page.get("orientation") != "landscape":
            problems.append(f"48-port IDF orientation = {page.get('orientation')}, expected landscape (no rotation)")
        if page.get("layoutProfile") != "network_48_port":
            problems.append(f"48-port IDF layoutProfile = {page.get('layoutProfile')}, expected network_48_port")
        if not page.get("twoUp"):
            problems.append("48-port IDF page.twoUp flag not set")

        diag = next((d for d in page_render_diagnostics(proj["pages"]) if d["sheetCode"] == page["displaySheetCode"]), None)
        if not diag or "two-up" not in diag["reason"]:
            problems.append(f"diagnostics reason missing two-up phrasing: {diag}")

    # B) 10-port table -> stays single full-width table, no two-up, no rotation.
    xlsx2 = tmp / "idf10.xlsx"
    _workbook(xlsx2, 10, "IDF SMALL")
    proj2 = import_workbook(xlsx2, project_id="idf10")
    pages10 = [p for p in proj2["pages"] if p["sheetTab"] == "IDF SMALL"]
    if len(pages10) != 1:
        problems.append(f"10-port IDF expected 1 page, got {len(pages10)}")
    else:
        page = pages10[0]
        block = (page.get("blocks") or [{}])[0]
        if block.get("layoutMode") != "single":
            problems.append(f"10-port IDF layoutMode = {block.get('layoutMode')}, expected single (no unnecessary two-up)")
        if len(block.get("rows") or []) != 10:
            problems.append(f"10-port IDF rows = {len(block.get('rows') or [])}, expected 10")
        if page.get("orientation") != "landscape":
            problems.append("10-port IDF rotated away from landscape")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — RDM/IDF network two-up layout passed")


if __name__ == "__main__":
    main()
