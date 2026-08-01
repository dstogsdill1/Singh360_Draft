from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server
from core.project_workspace import WorkbookDocumentStore
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

    def test_save_persists_blank_page_without_mutating_workbook_workspace(self) -> None:
        document_before = self.document_store.path.read_bytes()
        worksheets_before = deepcopy(self.project["worksheets"])
        response = self.client.post(
            f"/api/projects/{self.project_id}",
            json=self.candidate_with_blank(),
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))

        payload = response.get_json()
        blank = next(page for page in payload["pages"] if page["id"] == "page-blank")
        self.assertEqual("", blank["sheetCode"])
        self.assertEqual("", blank["sheetTab"])
        self.assertNotIn("linkedWorksheetId", blank)

        saved = server.store.load(self.project_id)
        self.assertIsNotNone(saved)
        self.assertEqual("preserve_existing", saved["managedPagePolicy"])
        self.assertEqual(
            [page["id"] for page in self.candidate_with_blank()["pages"]],
            [page["id"] for page in saved["pages"]],
            "a normal standalone save must not synthesize or reorder protected legacy pages",
        )
        saved_blank = next(page for page in saved["pages"] if page["id"] == "page-blank")
        self.assertEqual("New Sheet", saved_blank["sheetTitle"])
        self.assertEqual(worksheets_before, saved["worksheets"])
        self.assertEqual(
            document_before,
            self.document_store.path.read_bytes(),
        )

    def test_local_save_never_invokes_workbook_workspace_commit(self) -> None:
        with patch.object(
            WorkbookDocumentStore,
            "commit_reconciled_order",
            side_effect=OSError("injected disposable workspace write failure"),
        ) as workspace_commit:
            response = self.client.post(
                f"/api/projects/{self.project_id}",
                json=self.candidate_with_blank(),
            )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        workspace_commit.assert_not_called()
        reloaded = server.store.load(self.project_id)
        self.assertIn("page-blank", {page["id"] for page in reloaded["pages"]})

    def test_protected_export_clone_preserves_exact_pages_and_policy(self) -> None:
        protected = deepcopy(self.project)
        protected["projectMode"] = "standalone_layout"
        protected["managedPagePolicy"] = "preserve_existing"
        protected["pages"][0].setdefault("canvasObjects", []).append(
            {"objectId": "literal-source-text", "type": "textbox", "text": "NaN"}
        )
        expected_pages = deepcopy(protected["pages"])
        export_id = "f1e2d3c4b5a60718"
        server._write_export_only_project(protected, export_id)
        clone = server.store.load(export_id)
        self.assertIsNotNone(clone)
        self.assertEqual("preserve_existing", clone["managedPagePolicy"])
        self.assertEqual(expected_pages, clone["pages"])
        self.assertEqual(expected_pages, server._normalize_project_for_runtime(clone)["pages"])


if __name__ == "__main__":
    unittest.main()
