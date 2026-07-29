from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server
from core.project_workspace import WorkbookDocumentStore, drawing_workspace_sequence
from tests.generated_fixtures import isolate_server_runtime
from tests.test_sync_order_reconciliation import (
    document_for,
    fixture_project,
    write_fixture_workbook,
)


class BlankSheetTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = isolate_server_runtime(server)
        self.source = tempfile.TemporaryDirectory(prefix="s360_blank_source_")
        self.workbook = Path(self.source.name) / "disposable-blank-sheet.xlsx"
        write_fixture_workbook(self.workbook)
        self.project_id = "b1a2c3d4e5f60718"
        self.project = fixture_project(self.workbook)
        self.project["id"] = self.project_id
        self.project["workbookSync"]["workbook"] = str(self.workbook)
        server.store.save(self.project_id, self.project)
        self.project_dir = server.store.dir_for(self.project_id, self.project)
        self.document_store = WorkbookDocumentStore(self.project_dir)
        self.document_store.save(
            self.project,
            0,
            document_for(self.project),
        )
        self.client = server.app.test_client()

    def tearDown(self) -> None:
        self.source.cleanup()
        self.runtime.cleanup()

    def candidate_with_blank(self) -> dict:
        candidate = deepcopy(self.project)
        candidate["pages"].append(
            {
                "id": "page-blank",
                "order": 6,
                "include": True,
                "sheetCode": "",
                "displaySheetCode": "",
                "sheetTab": "",
                "sheetTitle": "New Sheet",
                "pageType": "canvas",
                "blocks": [],
                "canvasObjects": [],
            }
        )
        return candidate

    def test_save_atomically_persists_page_worksheet_and_both_index_rows(self) -> None:
        response = self.client.post(
            f"/api/projects/{self.project_id}",
            json=self.candidate_with_blank(),
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))

        payload = response.get_json()
        blank = next(page for page in payload["pages"] if page["id"] == "page-blank")
        self.assertEqual("", blank["sheetCode"])
        self.assertEqual("New Sheet", blank["sheetTab"])
        self.assertTrue(blank["linkedWorksheetId"].startswith("worksheet_"))

        saved = server.store.load(self.project_id)
        self.assertIsNotNone(saved)
        saved_blank = next(page for page in saved["pages"] if page["id"] == "page-blank")
        self.assertEqual(blank["linkedWorksheetId"], saved_blank["linkedWorksheetId"])
        project_worksheet = next(
            sheet
            for sheet in saved["worksheets"]
            if sheet["id"] == blank["linkedWorksheetId"]
        )
        self.assertEqual("New Sheet", project_worksheet["name"])

        index = next(sheet for sheet in saved["worksheets"] if sheet["name"] == "00_INDEX")
        headers = {str(value): column for column, value in enumerate(index["grid"][0])}
        row = next(
            row
            for row in index["grid"][1:]
            if row[headers["Page ID"]] == "page-blank"
        )
        self.assertEqual("", row[headers["Sheet Code"]])
        self.assertEqual("New Sheet", row[headers["Sheet Tab"]])

        document = self.document_store.load(saved)
        workspace = drawing_workspace_sequence(document)
        workspace_blank = next(item for item in workspace if item["pageId"] == "page-blank")
        self.assertEqual("", workspace_blank["sheetCode"])
        self.assertEqual("New Sheet", workspace_blank["sheetTab"])
        self.assertEqual(
            blank["linkedWorksheetId"],
            next(
                sheet["id"]
                for sheet in document["sheets"]
                if sheet["name"] == "New Sheet"
            ),
        )

    def test_workspace_commit_failure_rolls_back_project_json(self) -> None:
        project_path = self.project_dir / "project.json"
        before = project_path.read_bytes()
        with patch.object(
            WorkbookDocumentStore,
            "commit_reconciled_order",
            side_effect=OSError("injected disposable workspace write failure"),
        ):
            response = self.client.post(
                f"/api/projects/{self.project_id}",
                json=self.candidate_with_blank(),
            )
        self.assertEqual(500, response.status_code, response.get_data(as_text=True))
        self.assertEqual(before, project_path.read_bytes())
        reloaded = server.store.load(self.project_id)
        self.assertNotIn("page-blank", {page["id"] for page in reloaded["pages"]})


if __name__ == "__main__":
    unittest.main()
