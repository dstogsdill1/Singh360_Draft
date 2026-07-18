from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.workbook_reimport as reimport


def canonical(value):
    return json.loads(json.dumps(value, sort_keys=True))


def main() -> int:
    manual_page = {
        "id": "page_manual",
        "order": 1,
        "sheetCode": "EMS 18.0",
        "displaySheetCode": "EMS 18.0",
        "sheetTitle": "LCP-1 Control Wiring Schematic",
        "sheetTab": "EMS 18.0 LCP-1 Wiring",
        "pageType": "canvas",
        "pageFamily": "schematic",
        "include": True,
        "canvasObjects": [
            {"type": "image", "src": "/api/assets/example.png", "left": 100, "top": 80},
            {"type": "line", "x1": 10, "y1": 20, "x2": 300, "y2": 20},
        ],
        "blocks": [{"id": "manual_block", "type": "canvas"}],
        "notes": "Preserve this manual page.",
    }
    source_page = {
        "id": "page_source",
        "order": 2,
        "sheetCode": "EMS 3.0",
        "displaySheetCode": "EMS 3.0",
        "sheetTitle": "Singh360 / H-E-B Guidelines",
        "sheetTab": "EMS 3.0 Guidelines",
        "pageType": "text",
        "pageFamily": "front_matter",
        "include": True,
        "linkedWorksheetId": "ws_old",
        "blocks": [{"id": "old_block", "type": "excelRange", "grid": [["OLD"]]}],
        "canvasObjects": [],
    }
    existing = {
        "id": "project_test",
        "metadata": {"sourceFile": "old.xlsx"},
        "pages": [copy.deepcopy(manual_page), copy.deepcopy(source_page)],
        "archivedPages": [],
        "worksheets": [{"id": "ws_old", "name": "EMS 3.0 Guidelines", "grid": [["OLD"]]}],
        "importHistory": [],
    }

    candidate_source = {
        "id": "candidate_source",
        "order": 1,
        "sheetCode": "EMS 3.0",
        "displaySheetCode": "EMS 3.0",
        "sheetTitle": "Singh360 / H-E-B Guidelines",
        "sheetTab": "EMS 3.0 Guidelines",
        "pageType": "text",
        "pageFamily": "front_matter",
        "include": True,
        "linkedWorksheetId": "ws_new",
        "renderMode": "excel_exact",
        "blocks": [{"id": "new_block", "type": "excelRange", "grid": [["Topic", "Guideline"]]}],
        "canvasObjects": [],
    }
    candidate = {
        "id": "__candidate__",
        "metadata": {"sourceFile": "new.xlsx"},
        "pages": [candidate_source],
        "worksheets": [
            {
                "id": "ws_new",
                "name": "EMS 3.0 Guidelines",
                "sourceSheet": "EMS 3.0 Guidelines",
                "grid": [["Topic", "Guideline"]],
            }
        ],
    }

    original_import = reimport.import_workbook
    reimport.import_workbook = lambda *_args, **_kwargs: copy.deepcopy(candidate)
    try:
        plan = reimport.plan_reimport(existing, "new.xlsx")
        preserve_ids = {
            entry["existingPageId"]
            for entry in plan.get("toPreserveUnmatched", [])
        }
        archive_ids = {
            entry["existingPageId"]
            for entry in plan.get("toArchive", [])
        }
        assert "page_manual" in preserve_ids
        assert "page_manual" not in archive_ids

        updated, summary = reimport.apply_reimport(
            existing,
            "new.xlsx",
            replace_page_ids=[],
            source_filename="new.xlsx",
        )
    finally:
        reimport.import_workbook = original_import

    pages = {page["id"]: page for page in updated["pages"]}
    assert "page_manual" in pages
    assert canonical(pages["page_manual"]["canvasObjects"]) == canonical(manual_page["canvasObjects"])
    assert canonical(pages["page_manual"]["blocks"]) == canonical(manual_page["blocks"])
    assert pages["page_manual"]["notes"] == manual_page["notes"]
    assert not any(page.get("id") == "page_manual" for page in updated.get("archivedPages", []))

    assert updated["worksheets"][0]["id"] == "ws_new"
    assert pages["page_source"]["linkedWorksheetId"] == "ws_new"
    assert "EMS 18.0" in summary["preserved"]

    print("OK: unmatched manual drawing pages remain active and unchanged during workbook reimport.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
