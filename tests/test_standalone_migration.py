from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import scripts.migrate_standalone_projects as migration_module
from scripts.migrate_standalone_projects import (
    ARCHIVED_MI_TIENDA_NAME,
    CANONICAL_MI_TIENDA_ID,
    CANONICAL_MI_TIENDA_NAME,
    LEGACY_MI_TIENDA_ID,
    MigrationSafetyError,
    SA31_ID,
    apply_migration_plan,
    build_migration_plan,
)


NOW = "2026-08-01T15:00:00Z"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page(page_id: str, order: int, page_type: str = "canvas") -> dict:
    return {
        "id": page_id,
        "order": order,
        "include": True,
        "sheetCode": f"S-{order}",
        "displaySheetCode": f"S-{order}",
        "sheetTitle": page_id,
        "sheetTab": page_id,
        "pageType": page_type,
        "templateId": "ansi-b-standard",
        "blocks": [],
        "canvasObjects": [{"id": f"object-{page_id}", "type": "text"}],
        "notes": "",
    }


class DisposableProtectedDocs:
    def __init__(self, root: Path):
        self.docs = root / "disposable-docs"
        self.docs.mkdir()
        self.projects = self.docs / "projects"
        self.projects.mkdir()
        self.originals: dict[str, bytes] = {}
        self.paths: dict[str, Path] = {}
        self.workbooks: dict[str, Path] = {}
        self.workbook_state: dict[str, tuple[str, int]] = {}
        self._create_all()

    def _write_project(self, project_id: str, name: str, project: dict) -> None:
        folder = self.projects / f"{name}__{project_id}"
        folder.mkdir()
        workbook = folder / "sources" / "workbook" / f"{project_id}.xlsx"
        workbook.parent.mkdir(parents=True)
        workbook.write_bytes(b"synthetic workbook bytes\n" + project_id.encode("ascii"))
        project["projectFolder"] = str(folder)
        project["projectRoot"] = f"X:/Synthetic/{project_id}"
        project["linkedProjectRoot"] = f"X:/Synthetic/{project_id}"
        project["sourceWorkbookName"] = workbook.name
        project["workbookSync"] = {
            "status": "in_sync",
            "workbook": f"X:/Synthetic/{project_id}/{workbook.name}",
            "baselineWorkbookHash": f"hash-{project_id}",
        }
        target = folder / "project.json"
        payload = json.dumps(project, ensure_ascii=False, indent=2).encode("utf-8")
        target.write_bytes(payload)
        self.originals[project_id] = payload
        self.paths[project_id] = target
        self.workbooks[project_id] = workbook
        stat = workbook.stat()
        self.workbook_state[project_id] = (sha256(workbook), stat.st_mtime_ns)

    def _create_all(self) -> None:
        self._write_project(
            CANONICAL_MI_TIENDA_ID,
            "Layout-Sandbox",
            {
                "id": CANONICAL_MI_TIENDA_ID,
                "schemaVersion": 1,
                "metadata": {"projectName": "Layout Sandbox", "sourceFile": "layout.xlsx"},
                "pages": [
                    page("layout-user", 1),
                    page("layout-cover", 2, "cover"),
                    page("layout-index", 3, "index"),
                ],
                "assets": [{"id": "layout-asset", "url": "assets/layout.png"}],
                "savedAssemblies": [{"id": "layout-assembly", "objects": [{"id": "child"}]}],
                "sources": [{"id": "layout-source", "type": "workbook", "local": "sources/workbook/layout.xlsx"}],
            },
        )
        self._write_project(
            LEGACY_MI_TIENDA_ID,
            "Mi-Tienda-Legacy",
            {
                "id": LEGACY_MI_TIENDA_ID,
                "schemaVersion": 1,
                "projectDisplayName": "Mi Tienda 03",
                "metadata": {"projectName": "Mi Tienda 03"},
                "pages": [page("legacy-page", 1)],
                "assets": [{"id": "legacy-asset"}],
                "savedAssemblies": [{"id": "legacy-assembly"}],
                "sources": [],
            },
        )
        self._write_project(
            SA31_ID,
            "SA31",
            {
                "id": SA31_ID,
                "schemaVersion": 1,
                "projectDisplayName": "SA31",
                "metadata": {"projectName": "SA31", "sourceFile": "SA31.xlsm"},
                "pages": [page("sa31-second", 9), page("sa31-first", 2)],
                "archivedPages": [{**page("sa31-archived", 4), "archivedAt": "2025-01-01T00:00:00Z"}],
                "assets": [{"id": "sa31-asset"}],
                "savedAssemblies": [{"id": "sa31-assembly"}],
                "sources": [{"id": "sa31-source", "type": "workbook"}],
            },
        )

    def load(self, project_id: str) -> dict:
        return json.loads(self.paths[project_id].read_text(encoding="utf-8"))

    def assert_workbooks_untouched(self, case: unittest.TestCase) -> None:
        for project_id, workbook in self.workbooks.items():
            stat = workbook.stat()
            case.assertEqual(self.workbook_state[project_id], (sha256(workbook), stat.st_mtime_ns))


class StandaloneMigrationTests(unittest.TestCase):
    def test_cli_defaults_to_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            before = {project_id: path.read_bytes() for project_id, path in fixture.paths.items()}
            script = Path(__file__).resolve().parents[1] / "scripts" / "migrate_standalone_projects.py"
            completed = subprocess.run(
                [sys.executable, str(script), "--docs-dir", str(fixture.docs)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual("dry-run", report["mode"])
            self.assertNotIn("applied", report)
            self.assertFalse((fixture.docs / "_migration_backups").exists())
            self.assertEqual(before, {project_id: path.read_bytes() for project_id, path in fixture.paths.items()})
            fixture.assert_workbooks_untouched(self)

    def test_dry_run_is_read_only_and_reports_all_protected_actions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            before_files = {
                str(path.relative_to(fixture.docs)): path.read_bytes()
                for path in fixture.docs.rglob("*")
                if path.is_file()
            }
            plan = build_migration_plan(fixture.docs, now=NOW)
            after_files = {
                str(path.relative_to(fixture.docs)): path.read_bytes()
                for path in fixture.docs.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before_files, after_files)
            self.assertTrue(plan["safeToApply"])
            self.assertEqual("dry-run", plan["mode"])
            self.assertEqual([], plan["workbooksTouched"])
            self.assertEqual(
                {CANONICAL_MI_TIENDA_ID, LEGACY_MI_TIENDA_ID, SA31_ID},
                {action["projectId"] for action in plan["actions"]},
            )
            self.assertTrue(all(action["needsChange"] for action in plan["actions"]))
            fixture.assert_workbooks_untouched(self)

    def test_apply_migrates_in_place_with_backup_manifest_and_no_workbook_write(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            original_folders = sorted(path.name for path in fixture.projects.iterdir())
            sa31_pages = deepcopy(fixture.load(SA31_ID)["pages"])
            plan = build_migration_plan(fixture.docs, now=NOW)
            result = apply_migration_plan(fixture.docs, plan)

            self.assertTrue(result["applied"])
            self.assertEqual([], result["workbooksTouched"])
            self.assertEqual(
                {CANONICAL_MI_TIENDA_ID, LEGACY_MI_TIENDA_ID, SA31_ID},
                set(result["changedProjectIds"]),
            )
            self.assertEqual(original_folders, sorted(path.name for path in fixture.projects.iterdir()))
            backup = Path(result["backupPath"])
            self.assertTrue((backup / "manifest.sha256").is_file())
            self.assertTrue((backup / "rollback-map.json").is_file())
            self.assertTrue((backup / "rollback_standalone_migration.py").is_file())
            self.assertTrue(result["rollbackCommand"])
            for project_id, original in fixture.originals.items():
                backup_json = backup / "project_json" / project_id / "project.json"
                self.assertEqual(original, backup_json.read_bytes())

            canonical = fixture.load(CANONICAL_MI_TIENDA_ID)
            self.assertEqual(CANONICAL_MI_TIENDA_NAME, canonical["projectDisplayName"])
            self.assertEqual(CANONICAL_MI_TIENDA_NAME, canonical["metadata"]["projectName"])
            self.assertEqual("829", canonical["metadata"]["storeNumber"])
            self.assertEqual("Mi_Tienda_03_829", canonical["metadata"]["drawingPackageFileName"])
            self.assertEqual("standalone_layout", canonical["projectMode"])
            self.assertEqual("automatic", canonical["managedPagePolicy"])
            self.assertFalse(canonical["archived"])
            self.assertEqual(["layout-cover", "layout-index"], [p["id"] for p in canonical["pages"][:2]])
            self.assertIn("layout-user", [p["id"] for p in canonical["pages"]])
            self.assertEqual([{"id": "layout-asset", "url": "assets/layout.png"}], canonical["assets"])
            self.assertEqual("disabled", canonical["workbookSync"]["status"])
            self.assertEqual("X:/Synthetic/a214bea233ee4dcc", canonical["legacyWorkbookReference"]["projectRoot"])
            self.assertEqual("", canonical["projectRoot"])
            self.assertEqual("", canonical["linkedProjectRoot"])

            legacy = fixture.load(LEGACY_MI_TIENDA_ID)
            self.assertTrue(legacy["archived"])
            self.assertEqual(ARCHIVED_MI_TIENDA_NAME, legacy["projectDisplayName"])
            self.assertEqual(ARCHIVED_MI_TIENDA_NAME, legacy["metadata"]["projectName"])
            self.assertEqual(["legacy-page"], [p["id"] for p in legacy["pages"]])
            # Archived legacy project remains otherwise workbook-linked/read-only;
            # it was not converted or physically moved.
            self.assertEqual("in_sync", legacy["workbookSync"]["status"])

            sa31 = fixture.load(SA31_ID)
            self.assertEqual(sa31_pages, sa31["pages"])
            self.assertEqual("standalone_layout", sa31["projectMode"])
            self.assertEqual("preserve_existing", sa31["managedPagePolicy"])
            self.assertFalse(sa31["archived"])
            self.assertEqual("disabled", sa31["workbookSync"]["status"])
            self.assertEqual("X:/Synthetic/95d85da603864a62", sa31["legacyWorkbookReference"]["projectRoot"])
            fixture.assert_workbooks_untouched(self)

    def test_second_apply_is_idempotent_and_creates_no_new_backup(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            first = apply_migration_plan(fixture.docs, build_migration_plan(fixture.docs, now=NOW))
            backup_parent = Path(first["backupPath"]).parent
            backup_names = sorted(path.name for path in backup_parent.iterdir())
            second_plan = build_migration_plan(fixture.docs, now="2026-08-02T00:00:00Z")
            self.assertTrue(second_plan["safeToApply"])
            self.assertTrue(all(not action["needsChange"] for action in second_plan["actions"]))
            second = apply_migration_plan(fixture.docs, second_plan)
            self.assertFalse(second["applied"])
            self.assertEqual([], second["changedProjectIds"])
            self.assertEqual("", second["backupPath"])
            self.assertEqual(backup_names, sorted(path.name for path in backup_parent.iterdir()))
            fixture.assert_workbooks_untouched(self)

    def test_generated_rollback_restores_exact_pre_migration_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            result = apply_migration_plan(
                fixture.docs, build_migration_plan(fixture.docs, now=NOW)
            )
            backup = Path(result["backupPath"])
            completed = subprocess.run(
                [
                    sys.executable,
                    str(backup / "rollback_standalone_migration.py"),
                    "--docs-dir",
                    str(fixture.docs),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            for project_id, original in fixture.originals.items():
                self.assertEqual(original, fixture.paths[project_id].read_bytes())
            fixture.assert_workbooks_untouched(self)

    def test_missing_or_ambiguous_protected_project_blocks_apply(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            fixture.paths[SA31_ID].unlink()
            plan = build_migration_plan(fixture.docs, now=NOW)
            self.assertFalse(plan["safeToApply"])
            self.assertTrue(any(SA31_ID in blocker for blocker in plan["blockers"]))
            with self.assertRaises(MigrationSafetyError):
                apply_migration_plan(fixture.docs, plan)
            self.assertFalse((fixture.docs / "_migration_backups").exists())

        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            duplicate = fixture.projects / f"duplicate__{CANONICAL_MI_TIENDA_ID}"
            duplicate.mkdir()
            (duplicate / "project.json").write_bytes(fixture.originals[CANONICAL_MI_TIENDA_ID])
            plan = build_migration_plan(fixture.docs, now=NOW)
            self.assertFalse(plan["safeToApply"])
            action = next(item for item in plan["actions"] if item["projectId"] == CANONICAL_MI_TIENDA_ID)
            self.assertEqual("ambiguous", action["state"])

    def test_non_managed_page_payload_drift_blocks_plan_and_apply_before_backup(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            before = {
                project_id: path.read_bytes()
                for project_id, path in fixture.paths.items()
            }
            real_migrate = migration_module.migrate_project_to_standalone

            def drift_payload(project, **kwargs):
                migrated = real_migrate(project, **kwargs)
                if migrated.get("id") == CANONICAL_MI_TIENDA_ID:
                    target = next(
                        page for page in migrated["pages"] if page.get("id") == "layout-user"
                    )
                    target["canvasObjects"].append(
                        {"id": "unexpected-drift", "type": "text"}
                    )
                return migrated

            with patch.object(
                migration_module,
                "migrate_project_to_standalone",
                side_effect=drift_payload,
            ):
                plan = build_migration_plan(fixture.docs, now=NOW)

            self.assertFalse(plan["safeToApply"])
            action = next(
                item
                for item in plan["actions"]
                if item["projectId"] == CANONICAL_MI_TIENDA_ID
            )
            self.assertEqual("blocked", action["state"])
            self.assertIn("canvasObjects", action["error"])
            with self.assertRaises(MigrationSafetyError):
                apply_migration_plan(fixture.docs, plan)
            self.assertFalse((fixture.docs / "_migration_backups").exists())
            self.assertEqual(
                before,
                {project_id: path.read_bytes() for project_id, path in fixture.paths.items()},
            )
            fixture.assert_workbooks_untouched(self)

    def test_duplicate_page_id_drift_blocks_plan_and_apply_before_backup(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = DisposableProtectedDocs(Path(raw))
            before = {
                project_id: path.read_bytes()
                for project_id, path in fixture.paths.items()
            }
            real_migrate = migration_module.migrate_project_to_standalone

            def duplicate_identity(project, **kwargs):
                migrated = real_migrate(project, **kwargs)
                if migrated.get("id") == CANONICAL_MI_TIENDA_ID:
                    index = next(
                        page for page in migrated["pages"] if page.get("id") == "layout-index"
                    )
                    index["id"] = "layout-user"
                return migrated

            with patch.object(
                migration_module,
                "migrate_project_to_standalone",
                side_effect=duplicate_identity,
            ):
                plan = build_migration_plan(fixture.docs, now=NOW)

            self.assertFalse(plan["safeToApply"])
            action = next(
                item
                for item in plan["actions"]
                if item["projectId"] == CANONICAL_MI_TIENDA_ID
            )
            self.assertEqual("blocked", action["state"])
            self.assertIn("not unique", action["error"])
            with self.assertRaises(MigrationSafetyError):
                apply_migration_plan(fixture.docs, plan)
            self.assertFalse((fixture.docs / "_migration_backups").exists())
            self.assertEqual(
                before,
                {project_id: path.read_bytes() for project_id, path in fixture.paths.items()},
            )
            fixture.assert_workbooks_untouched(self)


if __name__ == "__main__":
    unittest.main()
