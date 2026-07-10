"""Smoke: LCP/I/O technical tokens get nowrap + adequate column width (Phase D)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from core.workbook_importer import import_workbook

_TOKENS = ["0-10VDC", "10K2", "NO", "NO*", "NC", "DI", "AIO1", "PR0650CD-TDB", "PR0663"]


def _workbook(path: Path) -> None:
    wb = Workbook()
    idx = wb.active
    idx.title = "00_INDEX"
    idx.append(["Include", "Order", "Sheet Code", "Sheet Tab", "Page Title"])
    idx.append(["YES", 1, "EMS 16.0", "LCP Panel Schedule", "LCP Panel Schedule"])

    lcp = wb.create_sheet("LCP Panel Schedule")
    lcp.append(["RO#", "Description", "Type", "Signal", "Notes"])
    for i, tok in enumerate(_TOKENS):
        lcp.append([str(i + 1), f"Point {i}", tok, tok, ""])
    wb.save(path)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "lcp_io.xlsx"
    _workbook(xlsx)
    proj = import_workbook(xlsx, project_id="iotok1")
    problems: list[str] = []

    page = next((p for p in proj["pages"] if "LCP" in (p.get("sheetTitle") or "")), None)
    if page is None:
        problems.append("LCP page missing")
        raise SystemExit(1)

    block = next((b for b in (page.get("blocks") or []) if b.get("type") == "excelRange"), None)
    if block is None:
        problems.append("excelRange block missing")
        raise SystemExit(1)

    nowrap = set(block.get("nowrapColumns") or [])
    if not nowrap:
        problems.append("nowrapColumns empty")

    grid = block.get("grid") or []
    header = grid[0] if grid else []
    type_col = next((i for i, h in enumerate(header) if str(h).lower() == "type"), 2)
    signal_col = next((i for i, h in enumerate(header) if str(h).lower() == "signal"), 3)

    for col in (type_col, signal_col):
        if col not in nowrap:
            problems.append(f"column {col} ({header[col] if col < len(header) else '?'}) not in nowrapColumns")

    widths = block.get("colWidths") or []
    longest = max(len(t) for t in _TOKENS)
    for col in (type_col, signal_col):
        if col < len(widths) and widths[col] < longest * 6:
            problems.append(f"col {col} width {widths[col]} too narrow for token len {longest}")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — I/O tokens nowrap configured")
    print(f"  nowrapColumns={sorted(nowrap)} widths={[widths[type_col], widths[signal_col]]}")


if __name__ == "__main__":
    main()
