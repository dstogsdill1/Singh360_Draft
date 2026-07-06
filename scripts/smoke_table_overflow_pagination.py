"""Smoke: wrapped table rows paginate instead of clipping into the title block."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.page_composer import BODY_BUDGET, compose_pages  # noqa: E402


def main() -> int:
    headers = [
        "Relay", "Contactor", "Controlled Circuits", "# of Poles", "Description",
        "Control", "From", "Offset", "To", "Offset", "From", "Offset",
    ]
    long_desc = "INTERIOR DISPLAY LIGHTS AND EXTERIOR SECURITY WALL PACKS"
    rows = []
    for i in range(18):
        rows.append([
            f"R{i + 1}", f"C{i + 1}", "HA-8,10,12,14,16,18,20,22", "4",
            long_desc if i % 2 == 0 else "PARKING LOT LIGHTING",
            "TC OFF", "STORE OPENING", "00:00:00", "DAWN", "+00:30", "DUSK", "-00:30",
        ])

    page = {
        "id": "page_lighting_matrix",
        "order": 1,
        "include": True,
        "sheetCode": "EMS 1.3",
        "displaySheetCode": "EMS 1.3",
        "sheetTitle": "Lighting Matrix",
        "sheetTab": "Lighting Matrix",
        "pageType": "data-grid",
        "pageFamily": "matrix",
        "templateId": "ansi-b-standard",
        "blocks": [{"id": "b_lighting", "type": "matrix", "headers": headers, "rows": rows, "editable": True}],
        "canvasObjects": [],
        "notes": "",
    }

    pages = compose_pages([page])
    problems: list[str] = []
    if len(pages) < 2:
        problems.append(f"expected continuation pages for wrapped 18-row matrix, got {len(pages)} page(s)")
    total_rows = sum(len((p.get("blocks") or [{}])[0].get("rows") or []) for p in pages)
    if total_rows != len(rows):
        problems.append(f"row count changed during split: {total_rows} != {len(rows)}")
    if not any(p.get("generatedContinuation") for p in pages[1:]):
        problems.append("continuation pages were not flagged generatedContinuation")
    if any(len((p.get("blocks") or [{}])[0].get("rows") or []) == 0 for p in pages):
        problems.append("empty table chunk generated")

    print(f"pages={len(pages)} totalRows={total_rows} bodyBudget={BODY_BUDGET}")
    if problems:
        print("TABLE OVERFLOW PAGINATION PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: wrapped table overflow pagination smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
