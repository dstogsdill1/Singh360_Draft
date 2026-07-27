from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core.project_workspace import (
    ProjectFileLibrary,
    ProjectWorkspaceError,
    WorkbookDocumentStore,
    WorkbookRevisionConflict,
    open_local_path,
    reveal_local_path,
)
from core.project_store import ProjectStore


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

    def test_linked_root_is_exact_live_recursive_filesystem_view(self) -> None:
        root = self.project_dir / "physical-root"
        project_meta = self.project_dir / "project-package"
        (root / "Drawings" / "Issued").mkdir(parents=True)
        (root / "Cx").mkdir()
        (root / ".singh360-project-root.json").write_text(
            '{"fixture":true}', encoding="utf-8"
        )
        (root / "Drawings" / "Issued" / "plan.pdf").write_bytes(
            b"sanitized pdf fixture"
        )
        project = {
            **self.project,
            "projectRoot": str(root),
            "linkedProjectRoot": str(root),
            "projectFilesMode": "EXACT_LINKED_PROJECT_ROOT",
        }

        library = ProjectFileLibrary(project_meta, project)
        first = library.load()
        self.assertEqual("linked", first["mode"])
        self.assertEqual(str(root.resolve()), first["rootPath"])
        self.assertEqual(["Cx", "Drawings", "Drawings/Issued"], first["folders"])
        self.assertEqual(
            {
                ".singh360-project-root.json",
                "Drawings/Issued/plan.pdf",
            },
            {item["relativePath"] for item in first["files"]},
        )
        self.assertNotIn("Converted Schedules", first["folders"])

        (root / "Cx" / "external-change.txt").write_text(
            "external", encoding="utf-8"
        )
        refreshed = ProjectFileLibrary(project_meta, project).load()
        self.assertIn(
            "Cx/external-change.txt",
            {item["relativePath"] for item in refreshed["files"]},
        )

    def test_linked_root_writes_real_paths_conflict_safely_and_restores(self) -> None:
        root = self.project_dir / "physical-root"
        project_meta = self.project_dir / "project-package"
        (root / "Programming").mkdir(parents=True)
        (root / "Cx").mkdir()
        project = {"projectRoot": str(root)}
        library = ProjectFileLibrary(project_meta, project)

        created = library.create_folder("Programming/Controls")
        self.assertEqual("Programming/Controls", created)
        renamed = library.rename_folder(created, "Approved Controls")
        self.assertTrue((root / "Programming" / "Approved Controls").is_dir())
        moved = library.move_folder(renamed, "Cx")
        self.assertEqual("Cx/Approved Controls", moved)
        self.assertTrue((root / moved).is_dir())

        uploaded = library.upload(
            io.BytesIO(b"first"),
            "fixture.txt",
            moved,
            {"modifiedTimeMs": 1_700_000_000_000},
        )
        duplicate = library.upload(
            io.BytesIO(b"second"), "fixture.txt", moved
        )
        self.assertEqual("Cx/Approved Controls/fixture.txt", uploaded["relativePath"])
        self.assertEqual(
            "Cx/Approved Controls/fixture (1).txt",
            duplicate["relativePath"],
        )
        self.assertEqual(
            b"first", (root / uploaded["relativePath"]).read_bytes()
        )

        renamed_file = library.rename_file(uploaded["id"], "renamed.txt")
        self.assertTrue((root / renamed_file["relativePath"]).is_file())
        moved_file = library.move_file(renamed_file["id"], "Programming")
        self.assertEqual("Programming/renamed.txt", moved_file["relativePath"])
        archived = library.archive_file(moved_file["id"])
        self.assertEqual("archived", archived["status"])
        self.assertTrue((root / archived["relativePath"]).is_file())
        restored = library.restore_file(archived["id"])
        self.assertEqual("Programming/renamed.txt", restored["relativePath"])
        self.assertTrue((root / restored["relativePath"]).is_file())

        archived_folder = library.archive_folder(moved)
        self.assertTrue((root / archived_folder).is_dir())
        restored_folder = library.restore_folder(archived_folder)
        self.assertEqual(moved, restored_folder)
        self.assertTrue((root / moved).is_dir())
        with self.assertRaises(ProjectWorkspaceError):
            library.create_folder("../outside")

    def test_linked_zip_open_reveal_and_reload_use_real_paths(self) -> None:
        root = self.project_dir / "physical-root"
        project_meta = self.project_dir / "project-package"
        (root / "Drawings").mkdir(parents=True)
        project = {"linkedProjectRoot": str(root)}
        library = ProjectFileLibrary(project_meta, project)
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as bundle:
            bundle.writestr("Area A/note.txt", "linked fixture")
        payload.seek(0)
        imported = library.import_zip(payload, "fixture.zip", "Drawings")
        self.assertEqual(1, imported["report"]["imported"])
        record = ProjectFileLibrary(project_meta, project).load()["files"][0]
        resolved_record, path = library.resolve(record["id"])
        self.assertEqual("Drawings/Area A/note.txt", resolved_record["relativePath"])
        self.assertEqual(b"linked fixture", path.read_bytes())

        with (
            patch("core.project_workspace.os.name", "nt"),
            patch(
                "core.project_workspace.os.startfile", create=True
            ) as startfile,
            patch(
                "core.project_workspace.subprocess.Popen"
            ) as popen,
        ):
            open_local_path(path)
            reveal_local_path(path, select=True)
        startfile.assert_called_once_with(str(path))
        popen.assert_called_once()
        self.assertEqual(
            ["explorer.exe", f"/select,{path}"],
            popen.call_args.args[0],
        )

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

    def test_project_store_reads_windows_utf8_bom_without_rewriting(self) -> None:
        docs = self.project_dir / "docs"
        store = ProjectStore(docs)
        project_id = "fedcba9876543210"
        project_dir = (
            docs / "projects" / f"Sanitized-BOM-Project__{project_id}"
        )
        project_dir.mkdir()
        project_json = project_dir / "project.json"
        original = (
            '\ufeff{"id":"fedcba9876543210","metadata":'
            '{"projectName":"Sanitized BOM Project"}}'
        ).encode("utf-8")
        project_json.write_bytes(original)

        loaded = store.load(project_id)
        self.assertEqual("Sanitized BOM Project", loaded["metadata"]["projectName"])
        self.assertEqual(
            ["Sanitized BOM Project"],
            [item["projectName"] for item in store.list_projects()],
        )
        self.assertEqual(original, project_json.read_bytes())


if __name__ == "__main__":
    unittest.main()
