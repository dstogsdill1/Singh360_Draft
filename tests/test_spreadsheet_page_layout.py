from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.project_preflight import compute_project_preflight
from core.project_workspace import WorkbookDocumentStore
from core.workbook_status_sync import project_hash


def worksheet() -> dict:
    return {
        "id": "ws-lighting",
        "name": "Lighting I-O",
        "grid": [
            ["LCP1", "DESCRIPTION"],
            ["LCP1-1", "Complete first controller description"],
            ["LCP1-2", "Complete second controller description"],
            ["LCP2", "DESCRIPTION"],
            ["LCP2-1", "Complete controller description"],
            ["LCP3", "DESCRIPTION"],
            ["LCP3-1", "Complete third controller description"],
            ["LCP4", "DESCRIPTION"],
            ["LCP4-1", "Complete fourth controller description"],
        ],
        "styles": {
            "A1": {"fontSize": 11, "bold": True, "fill": "#F4B183"},
            "B2": {"fontSize": 10, "wrap": True, "numberFormat": "General"},
        },
        "mergedCells": [],
        "colWidthsPx": [120, 540],
        "rowHeightsPx": [28] * 9,
        "hiddenRows": [],
        "hiddenColumns": [],
    }


def region(region_id: str, page_id: str, cell_range: str) -> dict:
    return {
        "id": region_id,
        "sourceSheetId": "ws-lighting",
        "range": cell_range,
        "pageId": page_id,
        "x": 32,
        "y": 32,
        "width": 1534,
        "height": 800,
        "fitMode": "fit_box",
        "overflowMode": "clip",
        "repeatRows": [],
        "explicitBreaks": [],
        "preserveGeometry": True,
        "scale": 1,
    }


class SpreadsheetPageLayoutTests(unittest.TestCase):
    def test_page_recipes_persist_without_inference(self) -> None:
        recipes = [
            {"pageId": "ems-16-2", "regions": [region("first", "ems-16-2", "A1:B5")]},
            {"pageId": "ems-16-2a", "regions": [region("continuation", "ems-16-2a", "A6:B9")]},
        ]
        document = {
            "revision": 0,
            "updatedAt": "",
            "sheets": [{
                "id": "ws-lighting", "name": "Lighting I-O", "cells": {}, "styles": {},
                "merges": [], "rowHeights": {}, "columnWidths": {},
                "defaultColumnWidth": 8.43, "defaultRowHeight": 15,
                "hiddenRows": [], "hiddenColumns": [], "archived": False,
                "tabColor": None, "role": None, "sourceSetup": {},
                "protectedRanges": [], "dataValidations": [], "conditionalFormats": [],
                "tableRegions": [], "tableLayout": "single", "annotations": [],
                "pageLayouts": recipes,
            }],
        }
        project = {"id": "fixture", "metadata": {"projectName": "Fixture"}, "pages": [], "worksheets": []}
        with tempfile.TemporaryDirectory() as raw:
            saved = WorkbookDocumentStore(Path(raw)).save(project, 0, document)
            reopened = WorkbookDocumentStore(Path(raw)).load(project)
        self.assertEqual(recipes, saved["sheets"][0]["pageLayouts"])
        self.assertEqual(recipes, reopened["sheets"][0]["pageLayouts"])
        self.assertEqual([], recipes[0]["regions"][0]["repeatRows"])
        self.assertEqual([], recipes[1]["regions"][0]["repeatRows"])

    def test_two_explicit_continuation_ranges_have_no_duplicate_rows_or_header(self) -> None:
        first = region("first", "ems-16-2", "A1:B5")
        second = region("continuation", "ems-16-2a", "A6:B9")
        project = {
            "id": "fixture", "metadata": {}, "worksheets": [worksheet()],
            "pages": [
                {"id": "ems-16-2", "include": True, "sheetCode": "EMS 16.2", "sheetTitle": "Lighting Control I/O", "renderMode": "spreadsheet_layout", "spreadsheetRegions": [first]},
                {"id": "ems-16-2a", "include": True, "sheetCode": "EMS 16.2a", "sheetTitle": "Lighting Control I/O Continued", "renderMode": "spreadsheet_layout", "spreadsheetRegions": [second]},
            ],
        }
        codes = {item["code"] for item in compute_project_preflight(project)}
        self.assertNotIn("spreadsheet_duplicate_range", codes)
        self.assertNotIn("spreadsheet_blank_page", codes)
        self.assertEqual("LCP1", project["worksheets"][0]["grid"][0][0])
        self.assertEqual("LCP3", project["worksheets"][0]["grid"][5][0])
        self.assertNotIn(0, second["repeatRows"])

    def test_multiple_intentional_regions_can_share_one_page_without_combining(self) -> None:
        left = region("left", "ems-16-2", "A1:A5")
        right = region("right", "ems-16-2", "B1:B5")
        left.update({"x": 32, "width": 360})
        right.update({"x": 420, "width": 1146})
        project = {
            "id": "fixture", "metadata": {}, "worksheets": [worksheet()],
            "pages": [{
                "id": "ems-16-2", "include": True, "sheetCode": "EMS 16.2",
                "sheetTitle": "Intentional Regions", "renderMode": "spreadsheet_layout",
                "spreadsheetRegions": [left, right],
            }],
        }
        codes = {item["code"] for item in compute_project_preflight(project)}
        self.assertNotIn("spreadsheet_duplicate_range", codes)
        self.assertEqual(["A1:A5", "B1:B5"], [item["range"] for item in project["pages"][0]["spreadsheetRegions"]])

    def test_preflight_detects_duplicate_merge_break_overflow_tiny_font_and_blank(self) -> None:
        source = worksheet()
        source["mergedCells"] = [{"startRow": 2, "endRow": 3, "startCol": 0, "endCol": 1}]
        source["styles"]["A3"] = {"fontSize": 6}
        bad = region("bad", "p2", "A3:B8")
        bad.update({"width": 80, "height": 40, "fitMode": "exact_scale", "scale": .5, "explicitBreaks": [3]})
        project = {
            "id": "fixture", "metadata": {}, "worksheets": [source],
            "pages": [
                {"id": "p1", "include": True, "sheetCode": "1", "sheetTitle": "One", "renderMode": "spreadsheet_layout", "spreadsheetRegions": [region("one", "p1", "A1:B5")]},
                {"id": "p2", "include": True, "sheetCode": "2", "sheetTitle": "Two", "renderMode": "spreadsheet_layout", "spreadsheetRegions": [bad]},
                {"id": "blank", "include": True, "sheetCode": "3", "sheetTitle": "Blank", "renderMode": "spreadsheet_layout", "spreadsheetRegions": []},
            ],
        }
        codes = {item["code"] for item in compute_project_preflight(project)}
        self.assertTrue({
            "spreadsheet_duplicate_range", "spreadsheet_merge_crosses_break",
            "spreadsheet_overflow", "spreadsheet_font_too_small", "spreadsheet_blank_page",
        }.issubset(codes))

    def test_recipe_is_a_conflict_hash_input(self) -> None:
        page = {"id": "p", "spreadsheetRegions": [region("r", "p", "A1:B5")]}
        project = {"metadata": {}, "pages": [page], "worksheets": [worksheet()]}
        before = project_hash(project)
        page["spreadsheetRegions"][0]["range"] = "A1:B4"
        self.assertNotEqual(before, project_hash(project))

    def test_frontend_uses_one_renderer_for_layout_preview_and_pdf(self) -> None:
        root = Path(__file__).resolve().parents[1]
        workspace = (root / "frontend/src/workspace/DataWorkspace.tsx").read_text("utf-8")
        page_renderer = (root / "frontend/src/components/PageRenderer.tsx").read_text("utf-8")
        document_view = (root / "frontend/src/components/DocumentView.tsx").read_text("utf-8")
        print_view = (root / "frontend/src/components/PrintView.tsx").read_text("utf-8")
        ribbon = (root / "frontend/src/components/Ribbon.tsx").read_text("utf-8")
        self.assertIn("['data', 'Data']", workspace)
        self.assertIn("['page-layout', 'Page Layout']", workspace)
        self.assertIn("['print-preview', 'Print Preview']", workspace)
        self.assertIn("Add Selection to Page", workspace)
        self.assertIn("No automatic combining, headers, or continuation", workspace)
        self.assertNotIn("Auto-Detect Tables", workspace)
        self.assertIn("<SpreadsheetPageCanvas", workspace)
        self.assertIn("sheet-viewport-spreadsheet", document_view)
        self.assertIn("if (isPageLocal(page) && worksheet)", page_renderer)
        self.assertIn("viewMode === 'print'", page_renderer)
        self.assertIn("<SpreadsheetPageCanvas", page_renderer)
        self.assertIn("<PageRenderer", print_view)
        self.assertIn("Spreadsheet Table", ribbon)


if __name__ == "__main__":
    unittest.main()
# S360 PAGE-LOCAL SPREADSHEET USABILITY V2 CONTRACT
def test_page_local_spreadsheet_usability_v2_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    spreadsheet = (root / "frontend/src/components/PageLocalSpreadsheet.tsx").read_text("utf-8")
    drawing = (root / "frontend/src/components/PageLocalDrawingRenderer.tsx").read_text("utf-8")
    geometry = (root / "frontend/src/model/sheetGeometry.ts").read_text("utf-8")
    app_css = (root / "frontend/src/styles/app.css").read_text("utf-8")

    # Full-work-area Spreadsheet editor with page context and native Univer isolation.
    assert "pls-page-context" in spreadsheet
    assert "merged cells behave like Excel" in spreadsheet
    assert 'className="pls-univer-host univer-host"' in spreadsheet
    assert "endEditingAsync" in spreadsheet

    # Simple, explicit cell operations for imported merged geometry.
    for label in (
        "Merge",
        "Unmerge",
        "Split + Repeat Value",
        "Clear Fill",
        "Clear Formatting",
        "Delete Contents",
    ):
        assert label in spreadsheet

    # Drawing uses the standard sheet title band and a body-local safe content box.
    assert "SheetTitleBand" in drawing
    assert "<SheetTitleBand page={page}" in drawing
    assert "PAGE_CONTENT_TOP" in drawing
    assert "PAGE_CONTENT_LEFT" in drawing
    assert "BODY_LEFT" not in drawing
    assert "blockHasVisibleContent" in drawing

    # One shared geometry contract keeps the table below the header and above title block.
    assert "PAGE_HEADER_H = 62" in geometry
    assert "PAGE_CONTENT_MARGIN_X" in geometry
    assert "PAGE_CONTENT_H" in geometry

    # The editor has visible margins, two readable action rows, and a full-size Univer host.
    assert "S360 PAGE-LOCAL SPREADSHEET USABILITY V2" in app_css
    assert ".pls-toolbar-row" in app_css
    assert ".pls-univer-host.univer-host" in app_css
