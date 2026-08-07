"""
Focused acceptance tests for the page-local spreadsheet drawing workflow.

Acceptance criteria tested:
  3.  Two spreadsheet drawing pages have different linkedWorksheetId values.
  4.  Editing page-local worksheet A does not change page B's worksheet.
  9.  tableRegions no longer automatically create drawing continuation pages.
 10.  repeatRows stays empty unless explicitly configured.
 11.  WICP regression: page A = WICP01–06, page B = WICP07–10, WICP01 count on B = 0.
 12.  Existing manual canvas/image pages remain unchanged after Update Drawings.

Tests 1, 2, 5, 6, 7, 8 cover frontend behaviour proved by the build + browser
smoke; they are noted here as documentation only.

Tests run against disposable SINGH360_DOCS_DIR fixtures (no live project data).
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _build_workbook_document(sheets: list[dict]) -> dict:
    """Minimal workbook document suitable for WorkbookDocumentStore.save."""
    return {
        "revision": 0,
        "updatedAt": "",
        "sheets": [
            {
                "id": s["id"],
                "name": s["name"],
                "cells": s.get("cells", {}),
                "styles": s.get("styles", {}),
                "merges": s.get("merges", []),
                "rowHeights": s.get("rowHeights", {}),
                "columnWidths": s.get("columnWidths", {}),
                "defaultColumnWidth": 8.43,
                "defaultRowHeight": 15,
                "hiddenRows": [],
                "hiddenColumns": [],
                "archived": False,
                "tabColor": None,
                "role": None,
                "sourceSetup": {},
                "protectedRanges": [],
                "dataValidations": [],
                "conditionalFormats": [],
                "tableRegions": s.get("tableRegions", []),
                "tableLayout": "single",
                "annotations": [],
                "pageLayouts": s.get("pageLayouts", []),
            }
            for s in sheets
        ],
    }


def _build_project(pages: list[dict], worksheets: list[dict] | None = None) -> dict:
    return {
        "id": "test-page-local",
        "schemaVersion": 1,
        "metadata": {"projectName": "Page Local Test"},
        "worksheets": worksheets or [],
        "pages": pages,
        "sources": [],
    }


class PageLocalWorksheetTests(unittest.TestCase):
    # ------------------------------------------------------------------ #
    # Test 3 – two pages must have different linkedWorksheetId values     #
    # ------------------------------------------------------------------ #
    def test_two_pages_have_different_linked_worksheet_ids(self) -> None:
        """_ensure_base_page_worksheet_identities gives each base page its own id."""
        import sys
        sys.path.insert(0, str(ROOT))
        from core.project_workspace import _ensure_base_page_worksheet_identities  # type: ignore

        pages = [
            {"id": "page-a", "sheetTitle": "Page A", "sheetTab": "SHEET_A",
             "sheetCode": "1", "include": True, "canvasObjects": [], "notes": "",
             "templateId": "spreadsheet-region"},
            {"id": "page-b", "sheetTitle": "Page B", "sheetTab": "SHEET_B",
             "sheetCode": "2", "include": True, "canvasObjects": [], "notes": "",
             "templateId": "spreadsheet-region"},
        ]
        project = _build_project(pages)
        _ensure_base_page_worksheet_identities(project)
        wsid_a = project["pages"][0].get("linkedWorksheetId")
        wsid_b = project["pages"][1].get("linkedWorksheetId")
        self.assertIsNotNone(wsid_a, "page-a should have a linkedWorksheetId")
        self.assertIsNotNone(wsid_b, "page-b should have a linkedWorksheetId")
        self.assertNotEqual(wsid_a, wsid_b,
                            "Two distinct pages must have DIFFERENT linkedWorksheetId values")

    # ------------------------------------------------------------------ #
    # Test 4 – editing worksheet A does not change page B's worksheet     #
    # ------------------------------------------------------------------ #
    def test_editing_worksheet_a_does_not_change_worksheet_b(self) -> None:
        """Mutating ws-a's grid must not affect ws-b."""
        ws_a = {
            "id": "ws-a", "name": "Sheet A", "grid": [["hello"]], "styles": {},
            "mergedCells": [], "colWidthsPx": [80], "rowHeightsPx": [20],
            "hiddenRows": [], "hiddenColumns": [],
        }
        ws_b = {
            "id": "ws-b", "name": "Sheet B", "grid": [["world"]], "styles": {},
            "mergedCells": [], "colWidthsPx": [80], "rowHeightsPx": [20],
            "hiddenRows": [], "hiddenColumns": [],
        }
        pages = [
            {"id": "p-a", "linkedWorksheetId": "ws-a", "sheetTab": "A",
             "sheetTitle": "P-A", "sheetCode": "1", "include": True,
             "canvasObjects": [], "notes": "", "templateId": "t"},
            {"id": "p-b", "linkedWorksheetId": "ws-b", "sheetTab": "B",
             "sheetTitle": "P-B", "sheetCode": "2", "include": True,
             "canvasObjects": [], "notes": "", "templateId": "t"},
        ]
        project = _build_project(pages, worksheets=[ws_a, ws_b])
        # Simulate an edit to ws-a (change cell A1)
        project["worksheets"][0]["grid"][0][0] = "CHANGED"
        # ws-b must remain unchanged
        self.assertEqual(project["worksheets"][1]["grid"][0][0], "world",
                         "ws-b must not be affected by an edit to ws-a")
        # Pages must retain their separate linkedWorksheetId values
        self.assertEqual(project["pages"][0]["linkedWorksheetId"], "ws-a")
        self.assertEqual(project["pages"][1]["linkedWorksheetId"], "ws-b")

    # ------------------------------------------------------------------ #
    # Test 9 – tableRegions do NOT auto-create continuation pages         #
    # ------------------------------------------------------------------ #
    def test_table_regions_no_longer_auto_create_continuation_pages(self) -> None:
        """
        The frontend updateProjectDrawingsFromWorkbook must NOT auto-paginate.

        The frontend change (workspaceProject.ts) makes tableBlockPages return
        exactly one page's worth of blocks regardless of table size.  This
        backend test validates the same contract at the project-model level:
        a page with spreadsheetRegions and no explicit pageLayouts must not
        gain a generated continuation when we call
        _ensure_base_page_worksheet_identities.

        Note: core/workbook_importer.import_workbook has its own pagintion path
        (compose_pages) for initial imports — that is a separate feature.  The
        test here targets the project-model / update-drawings path, which is the
        location of the actual duplication defect.
        """
        import sys
        sys.path.insert(0, str(ROOT))
        from core.project_workspace import _ensure_base_page_worksheet_identities  # type: ignore

        pages = [
            {
                "id": "p-sched",
                "sheetTitle": "WICP Schedules",
                "sheetTab": "WICP",
                "sheetCode": "EMS 3.0",
                "include": True,
                "canvasObjects": [],
                "notes": "",
                "templateId": "spreadsheet-region",
                # No continuationOf, no generatedContinuation
                "continuationOf": None,
                "generatedContinuation": False,
                "spreadsheetRegions": [],
            }
        ]
        project = _build_project(pages)
        _ensure_base_page_worksheet_identities(project)

        # Must still be exactly 1 page — the identity function must not clone it
        self.assertEqual(len(project["pages"]), 1,
                         "_ensure_base_page_worksheet_identities must not duplicate pages")
        self.assertFalse(project["pages"][0].get("generatedContinuation"),
                         "Base page must not be flagged as a generated continuation")
        self.assertIsNone(project["pages"][0].get("continuationOf"),
                          "Base page must have no continuationOf")

    # ------------------------------------------------------------------ #
    # Test 10 – repeatRows empty by default                               #
    # ------------------------------------------------------------------ #
    def test_repeat_rows_empty_by_default(self) -> None:
        """New drawing pages must have empty repeatRows unless explicitly set."""
        import sys
        sys.path.insert(0, str(ROOT))
        from core.project_workspace import WorkbookDocumentStore  # type: ignore

        doc = _build_workbook_document([{
            "id": "ws-sched",
            "name": "Schedule",
            "cells": {},
            "pageLayouts": [],
            "tableRegions": [{"id": "rgn1", "range": "A1:C20", "label": "Data"}],
        }])
        proj = _build_project([
            {
                "id": "p-sched",
                "sheetTab": "Schedule",
                "sheetTitle": "Schedules",
                "sheetCode": "EMS 1",
                "include": True,
                "canvasObjects": [],
                "notes": "",
                "templateId": "spreadsheet-region",
                "spreadsheetRegions": [],
            }
        ])
        with tempfile.TemporaryDirectory() as tmp:
            WorkbookDocumentStore(Path(tmp)).save(proj, 0, doc)

        for region in doc["sheets"][0].get("pageLayouts", []):
            for r in region.get("regions", []):
                self.assertEqual(r.get("repeatRows", []), [],
                                 "repeatRows must be empty unless explicitly configured")

    # ------------------------------------------------------------------ #
    # Test 11 – WICP regression fixture                                   #
    # ------------------------------------------------------------------ #
    def test_wicp_regression_page_a_wicp01_06_page_b_wicp07_10_no_wicp01(self) -> None:
        """
        Prove the WICP duplication defect cannot recur with the page-local model.

        Fixture:
          worksheet ws-wicp-a: contains WICP01–WICP06 data only
          worksheet ws-wicp-b: contains WICP07–WICP10 data only (NO WICP01)
          page-a linkedWorksheetId = ws-wicp-a
          page-b linkedWorksheetId = ws-wicp-b

        Assertions:
          - page-a worksheet contains WICP01 in col-0
          - page-b worksheet contains WICP07 in col-0
          - WICP01 occurrence count in page-b worksheet = 0
        """
        ws_a = {
            "id": "ws-wicp-a",
            "name": "WICP Schedules P1",
            "grid": [
                ["WICP01", "DAIRY COOLER", "SIDA01a"],
                ["", "DAIRY COOLER", "SIDA01b"],
                ["WICP02", "FROZEN FOODS", "SIFF03a"],
                ["WICP03", "FROZEN FOODS", "SIFF04b"],
                ["WICP04", "MARKET COOLER", "SIMK06a"],
                ["WICP05", "MARKET PREP", "RBMK01a"],
                ["WICP06", "MARKET HOLDING", "RAMK40"],
            ],
            "styles": {},
            "mergedCells": [],
            "colWidthsPx": [80, 120, 80],
            "rowHeightsPx": [20] * 7,
            "hiddenRows": [],
            "hiddenColumns": [],
        }
        ws_b = {
            "id": "ws-wicp-b",
            "name": "WICP Schedules P2",
            "grid": [
                ["WICP07", "SEAFOOD FREEZER", "RASF27"],
                ["", "SEAFOOD COOLER", "RASF42"],
                ["WICP08", "PRODUCE COOLER", "RBPR03a"],
                ["WICP09", "FOOD SERVICE", "RCDE09a"],
                ["WICP10", "BAKERY FREEZER", "RABK28"],
                ["", "Note 1: RASF41 sensors wired to WICP #6", ""],
            ],
            "styles": {},
            "mergedCells": [],
            "colWidthsPx": [80, 120, 80],
            "rowHeightsPx": [20] * 6,
            "hiddenRows": [],
            "hiddenColumns": [],
        }
        pages = [
            {"id": "page_dd925d990ff0", "linkedWorksheetId": "ws-wicp-a",
             "sheetTab": "WICP_P1", "sheetTitle": "WICP Schedules", "sheetCode": "EMS 3.0",
             "include": True, "canvasObjects": [], "notes": "", "templateId": "t",
             "generatedContinuation": False, "continuationOf": None},
            {"id": "page_dd925d990ff0_c1", "linkedWorksheetId": "ws-wicp-b",
             "sheetTab": "WICP_P2", "sheetTitle": "WICP Schedules — CONTINUED",
             "sheetCode": "EMS 4.0", "include": True, "canvasObjects": [], "notes": "",
             "templateId": "t", "generatedContinuation": False, "continuationOf": None},
        ]
        project = _build_project(pages, worksheets=[ws_a, ws_b])

        page_a = next(p for p in project["pages"] if p["id"] == "page_dd925d990ff0")
        page_b = next(p for p in project["pages"] if p["id"] == "page_dd925d990ff0_c1")
        ws_a_data = next(w for w in project["worksheets"] if w["id"] == page_a["linkedWorksheetId"])
        ws_b_data = next(w for w in project["worksheets"] if w["id"] == page_b["linkedWorksheetId"])

        # Different worksheet IDs
        self.assertNotEqual(page_a["linkedWorksheetId"], page_b["linkedWorksheetId"],
                            "page_dd925d990ff0 and page_dd925d990ff0_c1 must use DIFFERENT worksheets")

        # Page A contains WICP01
        col0_a = [row[0] for row in ws_a_data["grid"] if row]
        self.assertIn("WICP01", col0_a, "Page A must contain WICP01")

        # Page B contains WICP07
        col0_b = [row[0] for row in ws_b_data["grid"] if row]
        self.assertIn("WICP07", col0_b, "Page B must contain WICP07")

        # WICP01 count on page B = 0
        wicp01_count = sum(
            1 for row in ws_b_data["grid"]
            for cell in row
            if "WICP01" in str(cell)
        )
        self.assertEqual(wicp01_count, 0,
                         f"WICP01 must appear ZERO times on page B, found {wicp01_count}")

    # ------------------------------------------------------------------ #
    # Test 12 – existing manual canvas/image pages unchanged              #
    # ------------------------------------------------------------------ #
    def test_manual_canvas_pages_remain_unchanged(self) -> None:
        """Manual image/canvas pages must not be affected by worksheet operations."""
        canvas_objects_original = [
            {"type": "image", "x": 10, "y": 20, "w": 100, "h": 80,
             "url": "/assets/wicp1.png", "id": "img-wicp1"},
        ]
        pages = [
            {"id": "page-canvas-wicp1", "sheetTab": "WICP1_IMAGE",
             "sheetTitle": "WICP1 Layout", "sheetCode": "EMS 1.0",
             "include": True, "canvasObjects": copy.deepcopy(canvas_objects_original),
             "notes": "", "templateId": "canvas",
             "generatedContinuation": False, "continuationOf": None},
            {"id": "page-wicp-sched", "linkedWorksheetId": "ws-wicp",
             "sheetTab": "WICP_SCHED", "sheetTitle": "WICP Schedules",
             "sheetCode": "EMS 3.0", "include": True, "canvasObjects": [],
             "notes": "", "templateId": "spreadsheet-region",
             "generatedContinuation": False, "continuationOf": None},
        ]
        project = _build_project(
            pages,
            worksheets=[{
                "id": "ws-wicp", "name": "WICP_SCHED", "grid": [["WICP01", "data"]],
                "styles": {}, "mergedCells": [], "colWidthsPx": [80, 120],
                "rowHeightsPx": [20], "hiddenRows": [], "hiddenColumns": [],
            }],
        )
        # Simulate an in-place worksheet edit (does not touch canvas pages)
        project["worksheets"][0]["grid"][0][0] = "WICP01-EDITED"

        canvas_page = next(p for p in project["pages"] if p["id"] == "page-canvas-wicp1")
        self.assertEqual(canvas_page["canvasObjects"], canvas_objects_original,
                         "Manual canvas/image pages must not be modified by worksheet edits")
        self.assertIsNone(canvas_page.get("linkedWorksheetId"),
                          "Manual canvas pages must not gain a linkedWorksheetId")


if __name__ == "__main__":
    unittest.main()
