from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.project_store import ProjectStore


class ProjectStoreBackupSafetyTests(unittest.TestCase):
    def test_existing_project_is_unchanged_when_history_backup_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="s360_project_store_backup_") as raw:
            store = ProjectStore(Path(raw))
            original = {
                "id": "fixture",
                "metadata": {"projectName": "Backup Safety Fixture"},
                "pages": [{"id": "page-original", "sheetTitle": "Original"}],
            }
            project_json = store.save("fixture", deepcopy(original))
            exact_prior_bytes = project_json.read_bytes()

            updated = deepcopy(original)
            updated["pages"][0]["sheetTitle"] = "Must Not Persist"
            with patch.object(
                Path,
                "write_bytes",
                side_effect=OSError("injected disposable backup write failure"),
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "recovery snapshot could not be created",
                ):
                    store.save("fixture", updated)

            self.assertEqual(exact_prior_bytes, project_json.read_bytes())
            self.assertEqual("Original", store.load("fixture")["pages"][0]["sheetTitle"])
            self.assertFalse(list(project_json.parent.glob(".project-*.tmp")))

    def test_first_save_remains_valid_when_no_history_backup_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="s360_project_store_first_save_") as raw:
            store = ProjectStore(Path(raw))
            project = {
                "id": "fixture",
                "metadata": {"projectName": "First Save Fixture"},
                "pages": [],
            }

            with patch.object(store, "_backup_before_write", return_value=None) as backup:
                project_json = store.save("fixture", project)

            backup.assert_called_once()
            self.assertTrue(project_json.is_file())
            self.assertEqual("fixture", store.load("fixture")["id"])


if __name__ == "__main__":
    unittest.main()
