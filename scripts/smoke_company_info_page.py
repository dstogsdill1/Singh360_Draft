"""Smoke: Company Info imports as centered company page, not tiny table."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from core.workbook_importer import import_workbook


def _workbook(path: Path) -> None:
    wb = Workbook()
    idx = wb.active
    idx.title = "00_INDEX"
    idx.append(["Order", "Sheet Tab", "Page Title", "Include?", "Use Source"])
    idx.append(["23", "Company Info", "Company Info", "YES", ""])

    ws = wb.create_sheet("Company Info")
    ws.append(["Company", "Singh360 Inc."])
    ws.append(["Services", "Engineering Services"])
    ws.append(["Website", "www.singh360.com"])
    ws.append(["Phone", "555-0100"])
    ws.append(["Address", "San Antonio, TX"])
    ws.append(["Standard Note", "Prepared to Singh360 drawing standards."])
    wb.save(path)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "company_info.xlsx"
    _workbook(xlsx)
    proj = import_workbook(xlsx, project_id="company1")
    pages = [p for p in proj["pages"] if p["sheetTab"] == "Company Info"]
    problems: list[str] = []
    if len(pages) != 1:
        problems.append(f"expected one Company Info page, got {len(pages)}")
    else:
        block = pages[0]["blocks"][0]
        if block.get("type") != "companyInfo":
            problems.append(f"Company Info rendered as {block.get('type')} instead of companyInfo")
        if pages[0].get("renderMode") == "excel_exact":
            problems.append("Company Info used exact table renderer")
        text = " ".join(" ".join(r) for r in block.get("rows") or [])
        if "Singh360" not in text or "www.singh360.com" not in text:
            problems.append("Company Info source values not carried")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK - company info page passed")


if __name__ == "__main__":
    main()
