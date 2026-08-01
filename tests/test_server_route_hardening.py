from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import fitz
from openpyxl import Workbook
from openpyxl.drawing.image import Image as WorkbookImage
from PIL import Image

import server
from core import pdf_page_import as pdf_page_import_module
from core.standalone_project import create_standalone_project
from tests.generated_fixtures import isolate_server_runtime


class ServerRouteHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = isolate_server_runtime(server)
        self.project_id = "d1a2b3c4e5f60718"
        server.store.save(
            self.project_id,
            create_standalone_project(
                self.project_id,
                {"projectName": "Disposable Route Hardening"},
                profile="minimal",
            ),
        )
        self.package = server.store.find_dir(self.project_id)
        self.assertIsNotNone(self.package)
        self.client = server.app.test_client()

    def tearDown(self) -> None:
        self.runtime.cleanup()

    def _package_snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.package).as_posix(): path.read_bytes()
            for path in self.package.rglob("*")
            if path.is_file()
        }

    @staticmethod
    def _workbook_bytes(*, embedded_image: bool = True) -> bytes:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Imported Schedule"
        worksheet.append(["Tag", "Description", "Quantity"])
        worksheet.append(["CTRL-01", "Disposable Controller", 1])
        image_source: BytesIO | None = None
        if embedded_image:
            image_source = BytesIO()
            Image.new("RGB", (12, 8), "#4472c4").save(image_source, format="PNG")
            image_source.seek(0)
            worksheet.add_image(WorkbookImage(image_source), "E3")
        output = BytesIO()
        workbook.save(output)
        workbook.close()
        if image_source is not None:
            image_source.close()
        return output.getvalue()

    @staticmethod
    def _pdf_bytes(page_count: int = 2) -> bytes:
        document = fitz.open()
        try:
            for index in range(page_count):
                page = document.new_page(width=1224, height=792)
                page.insert_text((72, 72), f"Disposable PDF page {index + 1}")
            return document.tobytes()
        finally:
            document.close()

    def _preview_pdf(self) -> tuple[str, Path, Path]:
        response = self.client.post(
            f"/api/projects/{self.project_id}/pdf/import-preview",
            data={"file": (BytesIO(self._pdf_bytes()), "Disposable Set.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        preview_id = response.get_json()["previewId"]
        resolved = server._pending_pdf_paths(preview_id)
        self.assertIsNotNone(resolved)
        return preview_id, resolved[0], resolved[1]

    def _wait_pdf_job(self, job_id: str) -> tuple[dict, list[dict]]:
        deadline = time.time() + 30
        observed: list[dict] = []
        while time.time() < deadline:
            response = self.client.get(
                f"/api/projects/{self.project_id}/pdf/import-jobs/{job_id}"
            )
            self.assertEqual(200, response.status_code, response.get_data(as_text=True))
            payload = response.get_json()
            if payload.get("progress"):
                observed.append(payload["progress"])
            if payload.get("state") in {"succeeded", "failed"}:
                return payload, observed
            time.sleep(0.01)
        self.fail(f"PDF import job {job_id} did not finish")

    def test_pdf_sheet_code_suffixes_remain_unique_beyond_z(self) -> None:
        self.assertEqual("", server._pdf_sheet_code_suffix(0))
        self.assertEqual("a", server._pdf_sheet_code_suffix(1))
        self.assertEqual("z", server._pdf_sheet_code_suffix(26))
        self.assertEqual("aa", server._pdf_sheet_code_suffix(27))
        self.assertEqual("ab", server._pdf_sheet_code_suffix(28))
        generated = [f"NEW{server._pdf_sheet_code_suffix(offset)}" for offset in range(80)]
        self.assertEqual(len(generated), len(set(generated)))

    def test_nonexistent_project_asset_routes_are_404_without_creating_a_package(self) -> None:
        missing_id = "0123456789abcdef"
        before = sorted(path.name for path in server.store.projects_dir.iterdir())

        fetched = self.client.get(f"/api/assets/{missing_id}/safe.png")
        uploaded = self.client.post(
            f"/api/projects/{missing_id}/assets",
            data={"file": (BytesIO(b"not-an-image"), "safe.png")},
            content_type="multipart/form-data",
        )

        self.assertEqual(404, fetched.status_code)
        self.assertEqual(404, uploaded.status_code)
        self.assertIsNone(server.store.find_dir(missing_id))
        self.assertEqual(before, sorted(path.name for path in server.store.projects_dir.iterdir()))

    def test_asset_get_rejects_traversal_and_does_not_create_accessor_folders(self) -> None:
        before = self._package_snapshot()
        response = self.client.get(f"/api/assets/{self.project_id}/..%2Fproject.json")
        self.assertEqual(404, response.status_code)
        self.assertEqual(before, self._package_snapshot())

    def test_csv_validation_and_save_failures_leave_package_unchanged(self) -> None:
        payload = b"Tag,Description,Quantity\nCTRL-01,Disposable Controller,1\n"
        baseline = self._package_snapshot()

        with patch.object(server, "validate_project", return_value=["injected validation failure"]):
            validation = self.client.post(
                f"/api/projects/{self.project_id}/import/csv",
                data={"file": (BytesIO(payload), "Disposable.csv")},
                content_type="multipart/form-data",
            )
        self.assertEqual(400, validation.status_code, validation.get_data(as_text=True))
        self.assertEqual(baseline, self._package_snapshot())

        with patch.object(server.store, "save", side_effect=OSError("injected save failure")):
            save = self.client.post(
                f"/api/projects/{self.project_id}/import/csv",
                data={"file": (BytesIO(payload), "Disposable.csv")},
                content_type="multipart/form-data",
            )
        self.assertEqual(500, save.status_code, save.get_data(as_text=True))
        self.assertEqual(baseline, self._package_snapshot())
        self.assertEqual([], list((server.DOCS_DIR / ".runtime" / "import-staging").glob("*")))

    def test_generic_csv_source_save_failure_also_rolls_back_local_copy(self) -> None:
        baseline = self._package_snapshot()
        with patch.object(server.store, "save", side_effect=OSError("injected save failure")):
            response = self.client.post(
                f"/api/projects/{self.project_id}/sources",
                data={
                    "type": "csv",
                    "file": (BytesIO(b"Tag,Description\nCTRL-01,Disposable\n"), "Source.csv"),
                },
                content_type="multipart/form-data",
            )
        self.assertEqual(500, response.status_code, response.get_data(as_text=True))
        self.assertEqual(baseline, self._package_snapshot())

    def test_workbook_validation_and_save_failures_leave_sources_assets_and_project_unchanged(self) -> None:
        payload = self._workbook_bytes()
        baseline = self._package_snapshot()
        form = {
            "sheetNames": json.dumps(["Imported Schedule"]),
            "preserveExact": "1",
        }

        with patch.object(server, "validate_project", return_value=["injected validation failure"]):
            validation = self.client.post(
                f"/api/projects/{self.project_id}/import/workbook-sheet",
                data={**form, "file": (BytesIO(payload), "Disposable.xlsx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(400, validation.status_code, validation.get_data(as_text=True))
        self.assertEqual(baseline, self._package_snapshot())

        with patch.object(server.store, "save", side_effect=OSError("injected save failure")):
            save = self.client.post(
                f"/api/projects/{self.project_id}/import/workbook-sheet",
                data={**form, "file": (BytesIO(payload), "Disposable.xlsx")},
                content_type="multipart/form-data",
            )
        self.assertEqual(500, save.status_code, save.get_data(as_text=True))
        self.assertEqual(baseline, self._package_snapshot())
        self.assertEqual([], list((server.DOCS_DIR / ".runtime" / "import-staging").glob("*")))

    def test_workbook_preview_is_disposable_and_does_not_add_project_tmp_folder(self) -> None:
        baseline = self._package_snapshot()
        response = self.client.post(
            f"/api/projects/{self.project_id}/import/workbook-sheet/preview",
            data={"file": (BytesIO(self._workbook_bytes(embedded_image=False)), "Preview.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        self.assertEqual(baseline, self._package_snapshot())
        self.assertFalse((self.package / "sources" / "tmp").exists())

    def test_successful_workbook_import_persists_only_final_paths_and_unique_assets(self) -> None:
        response = self.client.post(
            f"/api/projects/{self.project_id}/import/workbook-sheet",
            data={
                "file": (BytesIO(self._workbook_bytes()), "Disposable.xlsx"),
                "sheetNames": json.dumps(["Imported Schedule"]),
                "preserveExact": "1",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        project = server.store.load(self.project_id)
        source = next(item for item in project["sources"] if item.get("originalFileName") == "Disposable.xlsx")
        source_path = self.package / source["projectLocalPath"]
        self.assertEqual(source_path.resolve(), Path(source["path"]).resolve())
        self.assertTrue(source_path.is_file())
        self.assertNotIn(".runtime", json.dumps(project))

        worksheet = next(item for item in project["worksheets"] if item.get("sourceId") == source["id"])
        self.assertEqual(source_path.resolve(), Path(worksheet["provenance"]["sourcePath"]).resolve())
        embedded = worksheet["embeddedImages"]
        self.assertEqual(1, len(embedded))
        self.assertTrue(embedded[0]["name"].startswith(Path(source["projectLocalPath"]).name[:16]))
        asset_path = self.package / "assets" / "images" / "excel" / embedded[0]["name"]
        self.assertTrue(asset_path.is_file())
        fetched = self.client.get(embedded[0]["url"])
        try:
            self.assertEqual(200, fetched.status_code)
            self.assertEqual(asset_path.read_bytes(), fetched.data)
        finally:
            fetched.close()

    def test_malformed_pdf_indices_and_metadata_return_structured_4xx(self) -> None:
        preview_id, _pdf_path, _metadata_path = self._preview_pdf()
        cases = (
            (["not", "an", "object"], "invalid_request_body"),
            ({"previewId": preview_id, "selectedPages": [{"bad": 1}]}, "invalid_page_selection"),
            ({"previewId": preview_id, "selectedPages": [0], "titlePrefix": {"bad": 1}}, "invalid_page_metadata"),
            ({"previewId": preview_id, "selectedPages": [0], "pageMetadata": {"0": []}}, "invalid_page_metadata"),
        )
        for body, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                response = self.client.post(
                    f"/api/projects/{self.project_id}/pdf/import-commit",
                    json=body,
                )
                self.assertEqual(400, response.status_code, response.get_data(as_text=True))
                payload = response.get_json()
                self.assertFalse(payload["ok"])
                self.assertEqual(expected_code, payload["code"])
                self.assertEqual("validate", payload["phase"])

    def test_pending_pdf_commit_rechecks_source_sha_and_metadata(self) -> None:
        baseline = self._package_snapshot()
        preview_id, pdf_path, _metadata_path = self._preview_pdf()
        pdf_path.write_bytes(pdf_path.read_bytes() + b"tampered")
        changed = self.client.post(
            f"/api/projects/{self.project_id}/pdf/import-commit",
            json={"previewId": preview_id, "selectedPages": [0], "action": "add"},
        )
        self.assertEqual(400, changed.status_code, changed.get_data(as_text=True))
        self.assertEqual("preview_source_changed", changed.get_json()["code"])
        self.assertEqual(baseline, self._package_snapshot())

        preview_id, _pdf_path, metadata_path = self._preview_pdf()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["pageCount"] += 1
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        mismatch = self.client.post(
            f"/api/projects/{self.project_id}/pdf/import-commit",
            json={"previewId": preview_id, "selectedPages": [0], "action": "add"},
        )
        self.assertEqual(400, mismatch.status_code, mismatch.get_data(as_text=True))
        self.assertEqual("preview_source_changed", mismatch.get_json()["code"])
        self.assertEqual(baseline, self._package_snapshot())

    def test_background_pdf_import_exposes_live_phase_and_page_counts(self) -> None:
        preview_id, pdf_path, metadata_path = self._preview_pdf()
        original_render = pdf_page_import_module.render_page_to_png

        def slow_render(*args, **kwargs):
            time.sleep(0.05)
            return original_render(*args, **kwargs)

        with patch.object(pdf_page_import_module, "render_page_to_png", side_effect=slow_render):
            started = self.client.post(
                f"/api/projects/{self.project_id}/pdf/import-commit",
                json={
                    "previewId": preview_id,
                    "selectedPages": [0, 1],
                    "action": "add",
                    "placementMode": "fit_body",
                    "background": True,
                },
            )
            self.assertEqual(202, started.status_code, started.get_data(as_text=True))
            start_payload = started.get_json()
            self.assertEqual(
                {"phase": "validate", "completed": 0, "total": 2},
                {
                    key: start_payload["progress"][key]
                    for key in ("phase", "completed", "total")
                },
            )
            finished, observed = self._wait_pdf_job(start_payload["jobId"])

        self.assertEqual("succeeded", finished["state"])
        self.assertEqual("complete", finished["progress"]["phase"])
        self.assertEqual(2, finished["progress"]["completed"])
        self.assertEqual(2, finished["progress"]["total"])
        self.assertEqual(2, len(finished["result"]["pageIds"]))
        self.assertTrue(any(
            event["phase"] == "render" and event["completed"] == 1 and event["total"] == 2
            for event in observed
        ))
        self.assertFalse(pdf_path.exists())
        self.assertFalse(metadata_path.exists())

    def test_background_pdf_import_returns_exact_structured_render_error(self) -> None:
        baseline = self._package_snapshot()
        preview_id, pdf_path, metadata_path = self._preview_pdf()
        with patch.object(
            pdf_page_import_module,
            "render_page_to_png",
            side_effect=RuntimeError("injected disposable render failure"),
        ):
            started = self.client.post(
                f"/api/projects/{self.project_id}/pdf/import-commit",
                json={
                    "previewId": preview_id,
                    "selectedPages": [1],
                    "action": "add",
                    "background": True,
                },
            )
            self.assertEqual(202, started.status_code, started.get_data(as_text=True))
            finished, _observed = self._wait_pdf_job(started.get_json()["jobId"])

        self.assertEqual("failed", finished["state"])
        self.assertFalse(finished["ok"])
        self.assertEqual(400, finished["errorStatus"])
        self.assertEqual("page_render_failed", finished["error"]["code"])
        self.assertEqual("render", finished["error"]["phase"])
        self.assertEqual(1, finished["error"]["pageIndex"])
        self.assertIn("injected disposable render failure", finished["error"]["detail"])
        self.assertEqual(baseline, self._package_snapshot())
        self.assertTrue(pdf_path.is_file())
        self.assertTrue(metadata_path.is_file())

    def test_expired_pending_pdf_pair_is_cleaned_and_returns_structured_410(self) -> None:
        preview_id, pdf_path, metadata_path = self._preview_pdf()
        old = time.time() - server._PDF_IMPORT_PREVIEW_TTL_SECONDS - 60
        os.utime(pdf_path, (old, old))
        os.utime(metadata_path, (old, old))

        response = self.client.post(
            f"/api/projects/{self.project_id}/pdf/import-commit",
            json={"previewId": preview_id, "selectedPages": [0], "action": "add"},
        )
        self.assertEqual(410, response.status_code, response.get_data(as_text=True))
        self.assertEqual("preview_expired", response.get_json()["code"])
        self.assertFalse(pdf_path.exists())
        self.assertFalse(metadata_path.exists())

    def test_export_warnings_get_is_byte_preserving_and_never_normalizes_or_saves(self) -> None:
        project_path = server.store.read_path(self.project_id)
        before = project_path.read_bytes()
        with (
            patch.object(server, "_normalize_project_for_runtime", side_effect=AssertionError("GET normalized")),
            patch.object(server.store, "save", side_effect=AssertionError("GET saved")),
        ):
            response = self.client.get(f"/api/projects/{self.project_id}/export/warnings")
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        self.assertEqual(before, project_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
