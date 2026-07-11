"""Smoke: export QA returns warnings but PDF export is not hard-blocked (Phase A)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from core.export_qa import compute_export_warnings
from core.workbook_importer import import_workbook


def _workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Cover"
    ws.cell(1, 1, "COVER")
    wb.save(path)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "warn.xlsx"
    _workbook(xlsx)
    proj = import_workbook(xlsx, project_id="warnov1")
    proj["pages"][0]["layoutWarnings"] = ["TABLE OVERFLOW — test warning"]
    warns = compute_export_warnings(proj)
    if not warns:
        print("FAIL — expected at least one QA warning")
        raise SystemExit(1)
    print(f"OK — export warnings non-blocking ({len(warns)} warning(s))")


if __name__ == "__main__":
    main()
