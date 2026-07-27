"""Smoke: EMS 13 IDF network table rebuild uses idfNetworkTable (not tiny excelRange)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from core.page_rebuild import rebuild_single_page_from_source, validate_page_rebuild
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
        ["3", "LCP1", "Lighting Control Panel 1", "601", "TBD", "Sanitized Client", "IDF-A", "SW1", "CAT6", "Primary", "Tech"],
        ["4", "LCP2", "Lighting Control Panel 2", "602", "TBD", "Sanitized Client", "IDF-A", "SW1", "CAT6", "Primary", "Tech"],
    ]
    for p in range(5, 49):
        rows.append([str(p), f"L{p}", f"Device-{p}", "", "TBD", "RDM Network", "A", "B", "CAT6", f"note-{p}", ""])
    for row in rows:
        ws.append(row)
    wb.save(path)


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    xlsx = tmp / "idf_rebuild.xlsx"
    _workbook(xlsx)
    proj = import_workbook(xlsx, project_id="idfrebuild1")
    problems: list[str] = []

    page = next((p for p in proj["pages"] if "IDF" in (p.get("sheetTitle") or "")), None)
    ws = next((w for w in proj["worksheets"] if w.get("id") == page.get("linkedWorksheetId")), None) if page else None
    if not page or not ws:
        print("FAIL — IDF page or worksheet missing")
        return 1

    # Simulate bad excelRange overwrite (the bug).
    bad_page = dict(page)
    bad_page["blocks"] = [{
        "id": "bad",
        "type": "excelRange",
        "grid": [["tiny"]],
        "colWidths": [40],
        "rowHeights": [12],
        "layoutWarnings": ["Range exceeds one page; scaled/cropped (continuation disabled)."],
        "splitMode": "none",
        "allowContinuation": False,
        "minScale": 0.5,
    }]
    bad_page["layoutProfile"] = "network_48_port"

    rebuilt = rebuild_single_page_from_source(bad_page, ws)
    ok, issues = validate_page_rebuild(page, rebuilt)
    if not ok:
        problems.extend(issues)

    block = next((b for b in (rebuilt.get("blocks") or []) if b.get("type") == "idfNetworkTable"), None)
    if block is None:
        problems.append(f"rebuild produced {rebuilt['blocks'][0].get('type')}, expected idfNetworkTable")

    if block:
        headers = block.get("headers") or []
        left = block.get("leftRows") or []
        right = block.get("rightRows") or []
        if len(left) != 24 or len(right) != 24:
            problems.append(f"expected 24/24 two-up, got {len(left)}/{len(right)}")
        ci = headers.index("Controller ID") if "Controller ID" in headers else -1
        if ci >= 0:
            for port, want in (("3", "601"), ("4", "602")):
                for row in left:
                    if str(row[0]).strip() == port and str(row[ci]).strip() != want:
                        problems.append(f"port {port} Controller ID = {row[ci]!r}, want {want}")
        for w in (block.get("layoutWarnings") or []) + (rebuilt.get("layoutWarnings") or []):
            if "scaled/cropped" in str(w).lower():
                problems.append(f"crop warning after rebuild: {w}")

    if problems:
        print("FAIL — EMS 13 IDF network rebuild")
        for p in problems:
            print(" -", p)
        return 1

    print("OK — EMS 13 IDF network rebuild")
    print(f"  type={block.get('type')} left={len(left)} right={len(right)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
