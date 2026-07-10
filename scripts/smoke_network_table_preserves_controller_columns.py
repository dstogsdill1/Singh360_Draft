"""Smoke: IDF network table keeps Controller ID / IP / Network columns (Phase C)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from core.page_composer import BODY_W
from core.workbook_importer import import_workbook

_REQUIRED = (
    "Port", "Label", "Device / Drop", "Controller ID", "IP Address", "Network",
    "From", "To", "Cable", "Notes",
)


def _workbook(path: Path) -> None:
    wb = Workbook()
    idx = wb.active
    idx.title = "00_INDEX"
    idx.append(["Include", "Order", "Sheet Code", "Sheet Tab", "Page Title"])
    idx.append(["YES", 1, "EMS 13.0", "RDM IDF NETWORK", "RDM / IDF Network Table"])

    ws = wb.create_sheet("RDM IDF NETWORK")
    ws.append(list(_REQUIRED) + ["Terminated By"])
    rows = [
        ["1", "DM00", "Data Manager 00", "", "TBD", "RDM", "IDF-A", "SW1", "CAT6", "", ""],
        ["2", "DM01", "Data Manager 01", "", "TBD", "RDM", "IDF-A", "SW1", "CAT6", "", ""],
        ["3", "LCP1", "Lighting Control Panel 1", "601", "TBD", "H-E-B", "IDF-A", "SW1", "CAT6", "Primary", "Tech"],
        ["4", "LCP2", "Lighting Control Panel 2", "602", "TBD", "H-E-B", "IDF-A", "SW1", "CAT6", "Primary", "Tech"],
    ]
    for p in range(5, 49):
        rows.append([str(p), f"L{p}", f"Device-{p}", "", "TBD", "RDM Network", "A", "B", "CAT6", f"note-{p}", ""])
    for row in rows:
        ws.append(row)
    wb.save(path)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "idf_network.xlsx"
    _workbook(xlsx)
    proj = import_workbook(xlsx, project_id="idfnet1")
    problems: list[str] = []

    page = next((p for p in proj["pages"] if "IDF" in (p.get("sheetTitle") or "")), None)
    if page is None:
        problems.append("IDF page missing")
        raise SystemExit(1)

    block = next((b for b in (page.get("blocks") or []) if b.get("type") == "idfNetworkTable"), None)
    if block is None:
        problems.append("idfNetworkTable block missing")
        raise SystemExit(1)

    headers = block.get("headers") or []
    for col in _REQUIRED:
        if col not in headers:
            problems.append(f"missing header {col!r}; got {headers}")

    if "Terminated By" in headers:
        problems.append("Terminated By should be hidden by default")

    left = block.get("leftRows") or []
    right = block.get("rightRows") or []
    if len(left) != 24 or len(right) != 24:
        problems.append(f"expected 24/24 two-up split, got {len(left)}/{len(right)}")

    def _cell(rows: list, port: str, col: str) -> str:
        ci = headers.index(col)
        for row in rows:
            if str(row[0]).strip() == port:
                return str(row[ci]).strip()
        return ""

    if _cell(left, "3", "Controller ID") != "601":
        problems.append(f"LCP1 Controller ID: {_cell(left, '3', 'Controller ID')!r}")
    if _cell(left, "4", "Controller ID") != "602":
        problems.append(f"LCP2 Controller ID: {_cell(left, '4', 'Controller ID')!r}")
    if _cell(left, "3", "IP Address") != "TBD":
        problems.append("LCP1 IP Address not TBD")
    if "601" in _cell(left, "3", "Notes") or "602" in _cell(left, "4", "Notes"):
        problems.append("Controller IDs folded into Notes")

    single_w = sum(block.get("colWidths") or [])
    two_up_usable = (BODY_W - 80 - 18) // 2
    if single_w > two_up_usable + 2:
        problems.append(f"table too wide for two-up: {single_w} > {two_up_usable}")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — network table preserves controller columns")
    print(f"  headers={headers}")


if __name__ == "__main__":
    main()
