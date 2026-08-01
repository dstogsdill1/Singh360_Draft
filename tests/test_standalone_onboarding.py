from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

import server
from tests.generated_fixtures import isolate_server_runtime


class StandaloneOnboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = isolate_server_runtime(server)
        self.client = server.app.test_client()

    def tearDown(self) -> None:
        self.runtime.cleanup()

    @staticmethod
    def _logo_bytes(color: str = "#4472c4") -> bytes:
        output = BytesIO()
        Image.new("RGB", (48, 24), color).save(output, format="PNG")
        return output.getvalue()

    def _multipart(self, metadata: dict, logo: bytes, filename: str = "Customer Logo.png") -> dict:
        return {
            "metadata": json.dumps(metadata),
            "customerLogo": (BytesIO(logo), filename),
        }

    def _active_project_dirs(self) -> list[Path]:
        return sorted(path for path in server.store.projects_dir.iterdir() if path.is_dir())

    def _staging_children(self) -> list[Path]:
        root = server.DOCS_DIR / ".project_staging"
        return sorted(root.iterdir()) if root.is_dir() else []

    def test_only_project_name_is_required_and_optional_metadata_stays_blank(self) -> None:
        response = self.client.post("/api/projects/new", json={"projectName": "Blank Metadata"})
        self.assertEqual(201, response.status_code, response.get_data(as_text=True))
        project = response.get_json()["project"]
        metadata = project["metadata"]
        for field in (
            "client",
            "storeNumber",
            "location",
            "projectType",
            "drawingSetTitle",
            "preparedBy",
            "createdBy",
            "checkedBy",
            "createdDate",
            "revision",
            "notes",
            "drawingPackageFileName",
            "customerLogoAsset",
        ):
            with self.subTest(field=field):
                self.assertEqual("", metadata[field])
        self.assertEqual(1, len(self._active_project_dirs()))
        self.assertEqual([], self._staging_children())

    def test_full_metadata_and_customer_logo_publish_as_one_project(self) -> None:
        metadata = {
            "projectName": "Full Onboarding",
            "client": "Sanitized Customer",
            "storeNumber": "TEST-101",
            "location": "Disposable Location",
            "projectType": "Controls",
            "drawingSetTitle": "Acceptance Drawings",
            "preparedBy": "Test Author",
            "checkedBy": "Test Reviewer",
            "createdDate": "2026-08-01",
            "revision": "A",
            "notes": "Sanitized onboarding fixture.",
            "drawingPackageFileName": "Full_Onboarding",
        }
        logo = self._logo_bytes()
        response = self.client.post(
            "/api/projects/new",
            data=self._multipart(metadata, logo),
            content_type="multipart/form-data",
        )
        self.assertEqual(201, response.status_code, response.get_data(as_text=True))
        payload = response.get_json()
        project_id = payload["id"]
        project = server.store.load(project_id)
        self.assertIsNotNone(project)
        for key, value in metadata.items():
            self.assertEqual(value, project["metadata"][key])
        self.assertEqual("Test Author", project["metadata"]["createdBy"])
        logo_url = project["metadata"]["customerLogoAsset"]
        self.assertRegex(logo_url, rf"^/api/assets/{project_id}/[a-f0-9]{{16}}\.png$")
        fetched = self.client.get(logo_url)
        try:
            self.assertEqual(200, fetched.status_code)
            self.assertEqual(logo, fetched.data)
        finally:
            fetched.close()
        self.assertEqual(1, len(self._active_project_dirs()))
        self.assertEqual([], self._staging_children())

    def test_invalid_logo_leaves_no_orphan_and_retry_creates_exactly_one_project(self) -> None:
        metadata = {"projectName": "Retryable Onboarding"}
        rejected = self.client.post(
            "/api/projects/new",
            data=self._multipart(metadata, b"not a readable PNG"),
            content_type="multipart/form-data",
        )
        self.assertEqual(400, rejected.status_code, rejected.get_data(as_text=True))
        self.assertIn("not a readable image", rejected.get_json()["detail"])
        self.assertEqual([], self._active_project_dirs())
        self.assertEqual([], self._staging_children())

        accepted = self.client.post(
            "/api/projects/new",
            data=self._multipart(metadata, self._logo_bytes("#70ad47")),
            content_type="multipart/form-data",
        )
        self.assertEqual(201, accepted.status_code, accepted.get_data(as_text=True))
        self.assertEqual(1, len(self._active_project_dirs()))
        self.assertEqual([], self._staging_children())

    def test_activation_failure_removes_complete_staging_package_and_no_project_is_listed(self) -> None:
        with patch.object(server.store, "activate_staged_project", side_effect=OSError("injected activation failure")):
            response = self.client.post(
                "/api/projects/new",
                data=self._multipart({"projectName": "Activation Failure"}, self._logo_bytes()),
                content_type="multipart/form-data",
            )
        self.assertEqual(500, response.status_code, response.get_data(as_text=True))
        self.assertEqual([], self._active_project_dirs())
        self.assertEqual([], self._staging_children())
        listing = self.client.get("/api/projects").get_json()
        self.assertEqual([], listing["projects"])

    def test_workbook_upload_cannot_use_the_standalone_creation_route(self) -> None:
        response = self.client.post(
            "/api/projects/new",
            data={"file": (BytesIO(b"not a workbook"), "Legacy.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(415, response.status_code, response.get_data(as_text=True))
        self.assertEqual([], self._active_project_dirs())

    def test_wizard_has_distinct_blank_import_and_skip_paths_without_followup_logo_mutations(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "components"
            / "NewProjectWizard.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("Create Blank Drawing Set", source)
        self.assertIn("Import Files Now", source)
        self.assertIn("Skip and Open Editor", source)
        self.assertIn("&tool=add-import", source)
        self.assertNotIn("&tool=project-pdf", source)
        self.assertEqual(1, source.count("fetch('/api/projects/new'"))
        self.assertNotIn("/assets`,", source)
        self.assertIn("createdDate: ''", source)

    def test_prepared_by_is_authoritative_with_legacy_alias_fallbacks(self) -> None:
        root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        title_block = (root / "components" / "TitleBlock.tsx").read_text(encoding="utf-8")
        settings = (root / "components" / "ProjectSettingsModal.tsx").read_text(encoding="utf-8")
        cover = (root / "components" / "renderers" / "CoverPageRenderer.tsx").read_text(encoding="utf-8")

        canonical_fallback = "m.preparedBy || m.drawnBy || m.createdBy"
        self.assertIn(canonical_fallback, title_block)
        self.assertIn('<Field label="Prepared By" value={preparedBy} />', title_block)
        self.assertIn(
            "metadata.preparedBy || metadata.drawnBy || metadata.createdBy || ''",
            settings,
        )
        self.assertIn(
            "metadata.preparedBy || metadata.drawnBy || metadata.createdBy",
            cover,
        )


if __name__ == "__main__":
    unittest.main()
