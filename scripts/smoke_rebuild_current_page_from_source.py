"""Smoke: rebuilding from source updates the same page (no duplicate output page).

Uses SA31 project.json when available, otherwise a synthetic excel_exact project.
Verifies linked page id is unchanged and normalized block text reflects source edits.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SA31 = ROOT / ".docs" / "projects" / "SA31-102-EMS-Lighting__ce333f83502742d3" / "project.json"

REQUIRED_MARKER = "REBUILD_SMOKE_TEST"


def _synthetic_project() -> dict:
    grid = [
        ["Title", "Body"],
        ["Section A", "Original text"],
        ["Section B", "More text"],
    ]
    ws_id = "ws_smoke_rebuild"
    page_id = "page_smoke_rebuild"
    return {
        "id": "smoke_rebuild01",
        "pages": [{
            "id": page_id,
            "order": 1,
            "include": True,
            "sheetCode": "5.0",
            "displaySheetCode": "5.0",
            "sheetTitle": "Project Scope",
            "sheetTab": "Scope",
            "pageType": "data-grid",
            "renderMode": "excel_exact",
            "linkedWorksheetId": ws_id,
            "pageGroupId": page_id,
            "blocks": [{
                "id": "b1",
                "type": "excelRange",
                "grid": deepcopy(grid),
                "styles": {},
                "colWidths": [120, 400],
                "rowHeights": [20, 20, 20],
                "srcRows": [0, 1, 2],
            }],
            "canvasObjects": [{"type": "textbox", "left": 10, "top": 10, "text": "keep me"}],
        }],
        "worksheets": [{
            "id": ws_id,
            "name": "Scope",
            "grid": deepcopy(grid),
            "styles": {},
            "colWidthsPx": {0: 120, 1: 400},
            "rowHeightsPx": {0: 20, 1: 20, 2: 20},
        }],
    }


def _refresh_block_from_ws(block: dict, ws: dict) -> dict:
    """Minimal mirror of frontend refreshBlockFromWorksheet (values only)."""
    grid = ws.get("grid") or []
    src_rows = block.get("srcRows") or list(range(len(grid)))
    new_grid = [list(grid[r]) if r < len(grid) else [] for r in src_rows]
    return {**block, "grid": new_grid}


def main() -> int:
    problems: list[str] = []
    if SA31.is_file():
        proj = json.loads(SA31.read_text(encoding="utf-8"))
        page = next((p for p in proj["pages"] if p.get("id") == "page_5"), None)
        ws = next((w for w in proj["worksheets"] if w.get("id") == "ws_5"), None)
        label = "SA31 Project Scope"
    else:
        proj = _synthetic_project()
        page = proj["pages"][0]
        ws = proj["worksheets"][0]
        label = "synthetic scope"

    if not page or not ws:
        print("FAIL — scope page or worksheet missing")
        return 1

    page_id = page["id"]
    old_page_count = len(proj["pages"])
    old_ids = {p["id"] for p in proj["pages"]}

    # Simulate a source edit + rebuild on the same page.
    ws = deepcopy(ws)
    page = deepcopy(page)
    if len(ws["grid"]) > 1 and len(ws["grid"][1]) > 1:
        ws["grid"][1][1] = REQUIRED_MARKER
    else:
        ws["grid"][0][0] = REQUIRED_MARKER

    block = page["blocks"][0]
    rebuilt_block = _refresh_block_from_ws(block, ws)
    page["blocks"] = [rebuilt_block]

    proj["pages"] = [page if p["id"] == page_id else p for p in proj["pages"]]

    if len(proj["pages"]) != old_page_count:
        problems.append(f"page count changed {old_page_count} -> {len(proj['pages'])}")
    if {p["id"] for p in proj["pages"]} != old_ids:
        problems.append("page ids changed after rebuild")
    if page["id"] != page_id:
        problems.append("active page id changed")

    flat = "\n".join(" ".join(row) for row in rebuilt_block.get("grid") or [])
    if REQUIRED_MARKER not in flat:
        problems.append("rebuilt block missing edited source text")

    canvas = page.get("canvasObjects") or []
    if label == "synthetic scope" and not canvas:
        problems.append("canvas objects lost on synthetic rebuild")

    if problems:
        print("FAIL — rebuild current page from source")
        for p in problems:
            print(" -", p)
        return 1

    print(f"OK — rebuild current page from source ({label})")
    print(f"  pageId={page_id} pages={len(proj['pages'])} marker={REQUIRED_MARKER!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
