"""Smoke: RDM/IDF two-up scale-up fills body better (FINAL SA31 POLISH 4I Phase D)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from core.page_composer import BODY_BUDGET
from core.workbook_importer import import_workbook


def _workbook(path: Path) -> None:
    wb = Workbook()
    idx = wb.active
    idx.title = "00_INDEX"
    idx.append(["Include", "Order", "Sheet Code", "Sheet Tab", "Page Title", "Family", "Page Type", "Notes"])
    idx.append(["YES", 12, "EMS 1.1", "RDM IDF NETWORK", "RDM / IDF Network Table", "Network", "table", ""])

    ws = wb.create_sheet("RDM IDF NETWORK")
    ws.append(["Port", "Label", "Device / Drop", "From", "To", "Cable", "Notes", "Controller ID", "IP Address", "Network"])
    for p in range(1, 49):
        ws.append([
            str(p), f"L{p}", f"Device-{p}", f"IDF-{p}", f"Drop-{p}", f"CAT6-{p}", f"note-{p}",
            f"C{(p % 4) + 1}", f"10.0.0.{p}", "VLAN10",
        ])
    wb.save(path)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "idf_scale.xlsx"
    _workbook(xlsx)
    proj = import_workbook(xlsx, project_id="idfscale1")
    problems: list[str] = []

    pages = [p for p in proj["pages"] if p["sheetTab"] == "RDM IDF NETWORK"]
    if len(pages) != 1:
        problems.append(f"expected 1 IDF page, got {len(pages)}")
    else:
        page = pages[0]
        block = (page.get("blocks") or [{}])[0]
        if block.get("layoutMode") != "two_up":
            problems.append(f"layoutMode={block.get('layoutMode')}, expected two_up")
        left = block.get("leftRows") or []
        right = block.get("rightRows") or []
        if len(left) != 24 or len(right) != 24:
            problems.append(f"ports not 24/24: {len(left)}/{len(right)}")
        font = float(block.get("fontSize") or 0)
        if font < 6.5:
            problems.append(f"font {font} below 6.5pt floor")
        if font < 7.0:
            problems.append(f"font {font} preferred >= 7pt when possible")
        content_h = float(block.get("contentHeight") or 0)
        fill = content_h / BODY_BUDGET if BODY_BUDGET else 0
        if fill < 0.55:
            problems.append(f"two-up content fill {fill:.2%} still below 55% (scale-up failed)")
        if fill > 0.90:
            problems.append(f"two-up content fill {fill:.2%} too aggressive (risk title-block collision)")
        if page.get("orientation") != "landscape":
            problems.append("page rotated away from landscape")
        headers = block.get("headers") or []
        # Low-value columns may be folded; essential columns must remain.
        for must in ("Port", "Label", "Device / Drop"):
            if must not in headers:
                problems.append(f"missing essential column {must!r}")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — SA31 IDF two-up scale-up passed")
    print(f"  font={block.get('fontSize')}, contentH={block.get('contentHeight')}, fill={fill:.1%}, headers={headers}")


if __name__ == "__main__":
    main()
