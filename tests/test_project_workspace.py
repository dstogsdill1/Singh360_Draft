from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.project_workspace import (
    ProjectFileLibrary,
    WorkbookDocumentStore,
    WorkbookRevisionConflict,
)


class ProjectWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = Path(__file__).resolve().parents[1] / ".tmp"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(
            prefix="project-workspace-", dir=scratch
        )
        self.project_dir = Path(self.temp.name)
        self.project = {
            "id": "0123456789abcdef",
            "metadata": {"projectName": "Sanitized Workspace Fixture"},
            "worksheets": [
                {
                    "id": "fixture-sheet",
                    "name": "Fixture Schedule",
                    "visible": True,
                    "grid": [["Device", "Count"], ["Sensor", "2"]],
                    "styles": {},
                    "mergedCells": [],
                    "rowHeights": {"1": 18.0, "2": 15.0},
                    "columnWidths": {"A": 31.5, "B": 11.25},
                    "rowHeightsPx": [24, 20],
                    "colWidthsPx": [225, 84],
                    "defaultColumnWidth": 8.43,
                    "defaultRowHeight": 15.0,
                    "hiddenRows": [1],
                    "hiddenColumns": [1],
                }
            ],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_file_and_folder_lifecycle_is_virtual_and_recoverable(self) -> None:
        library = ProjectFileLibrary(self.project_dir)
        self.assertIn("Drawings", library.load()["folders"])
        library.create_folder("References/Submittals")
        record = library.upload(
            io.BytesIO(b"fixture text"),
            "fixture.txt",
            "References/Submittals",
        )
        self.assertEqual(1, len(library.load()["files"]))
        renamed = library.rename_file(record["id"], "renamed.txt")
        self.assertEqual("renamed.txt", renamed["originalFileName"])
        moved = library.move_file(record["id"], "Programming")
        self.assertEqual("Programming", moved["virtualPath"])
        archived = library.archive_file(record["id"])
        self.assertEqual("archived", archived["status"])
        restored = library.restore_file(record["id"])
        self.assertEqual("active", restored["status"])
        preview = library.preview(record["id"])
        self.assertEqual("fixture text", preview["text"])

        renamed_folder = library.rename_folder(
            "References/Submittals", "Approved"
        )
        self.assertEqual("References/Approved", renamed_folder)
        moved_folder = library.move_folder("References/Approved", "Assets")
        self.assertEqual("Assets/Approved", moved_folder)
        archived_folder = library.archive_folder("Assets/Approved")
        self.assertEqual("Archive/Assets/Approved", archived_folder)
        restored_folder = library.restore_folder(archived_folder)
        self.assertEqual("Assets/Approved", restored_folder)

    def test_zip_import_preserves_nested_folders(self) -> None:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as bundle:
            bundle.writestr("Drawings/Area A/plan.txt", "safe fixture")
            bundle.writestr("References/readme.txt", "reference")
        payload.seek(0)
        result = ProjectFileLibrary(self.project_dir).import_zip(
            payload, "fixture.zip"
        )
        self.assertEqual(2, result["report"]["imported"])
        paths = {
            item["relativePath"]
            for item in ProjectFileLibrary(self.project_dir).load()["files"]
        }
        self.assertIn("Drawings/Area A/plan.txt", paths)
        self.assertIn("References/readme.txt", paths)

    def test_data_workspace_seeds_saves_and_imports_csv(self) -> None:
        store = WorkbookDocumentStore(self.project_dir)
        initial = store.load(self.project)
        self.assertEqual(0, initial["revision"])
        self.assertEqual("Fixture Schedule", initial["sheets"][0]["name"])
        self.assertEqual(
            {"1": 18.0, "2": 15.0},
            initial["sheets"][0]["rowHeights"],
        )
        self.assertEqual(
            {"A": 31.5, "B": 11.25},
            initial["sheets"][0]["columnWidths"],
        )
        self.assertEqual(8.43, initial["sheets"][0]["defaultColumnWidth"])
        self.assertEqual(15.0, initial["sheets"][0]["defaultRowHeight"])
        self.assertEqual([2], initial["sheets"][0]["hiddenRows"])
        self.assertEqual(["B"], initial["sheets"][0]["hiddenColumns"])
        initial["sheets"][0]["cells"]["B2"] = {"v": "3"}
        saved = store.save(self.project, 0, initial)
        self.assertEqual(1, saved["revision"])
        with self.assertRaises(WorkbookRevisionConflict):
            store.save(self.project, 0, initial)

        csv_path = self.project_dir / "converted.csv"
        csv_path.write_text("Point,Value\nAI-1,42\n", encoding="utf-8")
        imported = store.import_file(self.project, csv_path, "converted.csv")
        self.assertEqual(2, imported["revision"])
        self.assertEqual(2, len(imported["sheets"]))


if __name__ == "__main__":
    unittest.main()
