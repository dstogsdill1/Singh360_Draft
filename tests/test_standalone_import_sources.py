from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib
import os
import unittest
from unittest.mock import patch

from PIL import Image

import server
from core.project_store import ProjectStore
from core.standalone_project import create_standalone_project
from tests.generated_fixtures import isolate_server_runtime


class StandaloneImportSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = isolate_server_runtime(server)
        self.project_id = "c1a2b3d4e5f60718"
        server.store.save(
            self.project_id,
            create_standalone_project(
                self.project_id,
                {"projectName": "Disposable Source Import"},
                profile="minimal",
            ),
        )
        self.client = server.app.test_client()

    def tearDown(self) -> None:
        self.runtime.cleanup()

    def test_csv_import_is_project_local_and_records_complete_provenance(self) -> None:
        payload = b"Tag,Description,Quantity\nCTRL-01,Disposable Controller,2\n"
        response = self.client.post(
            f"/api/projects/{self.project_id}/import/csv",
            data={"file": (BytesIO(payload), "Disposable Schedule.csv")},
            content_type="multipart/form-data",
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))

        project = server.store.load(self.project_id)
        self.assertIsNotNone(project)
        source = next(item for item in project["sources"] if item.get("type") == "csv")
        expected_sha = hashlib.sha256(payload).hexdigest()
        self.assertEqual(expected_sha, source["sha256"])
        self.assertEqual("Disposable Schedule.csv", source["originalFileName"])
        self.assertEqual("one_time_editable_table", source["importMode"])
        self.assertTrue(source["projectLocalPath"].startswith("sources/csv/"))

        package = server.store.find_dir(self.project_id)
        local_copy = package / source["projectLocalPath"]
        self.assertEqual(payload, local_copy.read_bytes())
        imported = [page for page in project["pages"] if (page.get("sourceImport") or {}).get("sourceId") == source["id"]]
        self.assertTrue(imported)
        self.assertTrue(all(page["sourceImport"]["sha256"] == expected_sha for page in imported))
        self.assertTrue(all(page["sourceImport"]["projectLocalPath"] == source["projectLocalPath"] for page in imported))

    def test_uploaded_image_is_a_project_local_asset_with_stable_bytes(self) -> None:
        image = BytesIO()
        Image.new("RGB", (32, 18), "#f4b183").save(image, format="PNG")
        payload = image.getvalue()
        response = self.client.post(
            f"/api/projects/{self.project_id}/assets",
            data={"file": (BytesIO(payload), "Disposable Screenshot.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        asset = response.get_json()["asset"]
        package = server.store.find_dir(self.project_id)
        local_copy = package / asset["projectLocalPath"]
        self.assertEqual(Path(asset["url"]).name, asset["storedFileName"])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), asset["sha256"])
        self.assertEqual(payload, local_copy.read_bytes())

        fetched = self.client.get(asset["url"])
        try:
            self.assertEqual(200, fetched.status_code)
            self.assertEqual(payload, fetched.data)
        finally:
            fetched.close()

        project = server.store.load(self.project_id)
        image_page = {
            "id": "page_image_fixture",
            "order": len(project["pages"]) + 1,
            "include": True,
            "sheetCode": "IMG-1",
            "displaySheetCode": "IMG-1",
            "sheetTitle": "Disposable Screenshot",
            "sheetTab": "",
            "pageType": "image",
            "blocks": [],
            "canvasObjects": [{
                "objectId": "image_object_fixture",
                "type": "image",
                "src": asset["url"],
                "width": 32,
                "height": 18,
                "scaleX": 1,
                "scaleY": 1,
            }],
            "notes": "",
            "createdAt": "2026-08-01T00:00:00Z",
            "modifiedAt": "2026-08-01T00:00:00Z",
            "sourceImport": {
                "id": "image_page_fixture",
                "groupId": "image_page_fixture",
                "type": "image",
                "originalName": "Disposable Screenshot.png",
                "sha256": asset["sha256"],
                "localAsset": asset["storedFileName"],
                "projectLocalPath": asset["projectLocalPath"],
                "placementMode": "fit_body",
                "importedAt": "2026-08-01T00:00:00Z",
            },
        }
        project["pages"].append(image_page)
        saved = self.client.post(f"/api/projects/{self.project_id}", json=project)
        self.assertEqual(200, saved.status_code, saved.get_data(as_text=True))

        # A fresh store instance models server restart; neither the original
        # upload nor an external drive is needed to reopen/render the page.
        server.store = ProjectStore(server.DOCS_DIR)
        reloaded = server.store.load(self.project_id)
        persisted = next(page for page in reloaded["pages"] if page["id"] == image_page["id"])
        self.assertEqual(asset["projectLocalPath"], persisted["sourceImport"]["projectLocalPath"])
        self.assertEqual(payload, (server.store.find_dir(self.project_id) / persisted["sourceImport"]["projectLocalPath"]).read_bytes())

    def test_legacy_workbook_authority_routes_are_disabled_without_mutation(self) -> None:
        project_path = server.store.read_path(self.project_id)
        before = project_path.read_bytes()
        requests = (
            ("get", f"/api/projects/{self.project_id}/workbook-link"),
            ("post", f"/api/projects/{self.project_id}/workbook-link/sync"),
            ("post", f"/api/projects/{self.project_id}/workbook-link/resolve"),
            ("get", f"/api/projects/{self.project_id}/workbook-quality"),
            ("post", f"/api/projects/{self.project_id}/workbook-quality/repair"),
            ("post", f"/api/projects/{self.project_id}/reimport"),
            ("post", "/api/import/workbook"),
        )
        with patch.dict(os.environ, {"SINGH360_ENABLE_LEGACY_WORKBOOK_ROUTES": ""}):
            for method, path in requests:
                response = getattr(self.client, method)(path)
                self.assertEqual(410, response.status_code, path)
                self.assertIn("disabled", response.get_json()["error"].lower())
        self.assertEqual(before, project_path.read_bytes())

    def test_legacy_delete_action_archives_without_removing_package(self) -> None:
        package = server.store.find_dir(self.project_id)
        response = self.client.delete(f"/api/projects/{self.project_id}?confirm=true")
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        self.assertTrue(response.get_json()["archived"])
        self.assertFalse(response.get_json()["permanentDeletionAvailable"])
        self.assertTrue(package.is_dir())
        self.assertTrue((package / "project.json").is_file())
        archived = server.store.load(self.project_id)
        self.assertTrue(archived["archived"])
        self.assertTrue(list((package / "backups").glob("project_*.json")))


if __name__ == "__main__":
    unittest.main()
