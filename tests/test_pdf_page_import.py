from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz

from core.pdf_page_import import (
    BODY_HEIGHT_PX,
    BODY_WIDTH_PX,
    SHEET_HEIGHT_PX,
    SHEET_WIDTH_PX,
    PdfPageImportError,
    commit_pdf_import,
    existing_pdf_import_groups,
    preview_pdf,
)
from core.project_model import default_project
from core.project_store import ProjectStore


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_three_page_pdf(path: Path, revision: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    for index in range(3):
        page = document.new_page(width=6 * 72, height=4 * 72)
        page.insert_text(
            (36, 48),
            f"{revision} DRAWING PAGE {index + 1}",
            fontsize=20,
        )
        page.draw_rect(
            fitz.Rect(30 + index * 4, 70, 400 - index * 5, 250),
            color=(0.1 * index, 0.2, 0.7),
            width=1.5,
        )
        page.insert_text(
            (40, 275),
            f"Stable test marker {revision}-{index + 1}",
            fontsize=10,
        )
    document.save(path)
    document.close()
    return path


def _seed_project(store: ProjectStore, project_id: str) -> dict:
    project = default_project(project_id)
    project["projectDisplayName"] = f"PDF Fixture {project_id[-2:]}"
    project["metadata"]["projectName"] = project["projectDisplayName"]
    project["pages"] = [
        {
            "id": f"cover_{project_id[-4:]}",
            "order": 1,
            "include": True,
            "publishStatus": "YES",
            "sheetCode": "COVER",
            "displaySheetCode": "COVER",
            "sheetTitle": "Cover",
            "sheetTab": "COVER",
            "pageType": "cover",
            "templateId": "ansi-b-standard",
            "blocks": [{"id": "cover-block", "type": "cover"}],
            "canvasObjects": [],
            "notes": "",
        }
    ]
    store.save(project_id, project)
    return project


def _pdf_pages(project: dict, group_id: str | None = None) -> list[dict]:
    pages = [page for page in project.get("pages", []) if page.get("pageType") == "pdf"]
    if group_id is not None:
        pages = [
            page
            for page in pages
            if (page.get("sourceImport") or {}).get("importGroupId") == group_id
        ]
    return pages


def _base(page: dict) -> dict:
    values = [obj for obj in page.get("canvasObjects", []) if obj.get("pdfBase") is True]
    if len(values) != 1:
        raise AssertionError(f"expected one PDF base object, got {len(values)}")
    return values[0]


def _overlays(page: dict) -> list[dict]:
    return [copy.deepcopy(obj) for obj in page.get("canvasObjects", []) if obj.get("pdfBase") is not True]


class PdfPageImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="s360_pdf_page_import_")
        self.root = Path(self.temp.name)
        self.store = ProjectStore(self.root / ".docs")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _project(self, suffix: int) -> str:
        project_id = f"{suffix:016x}"
        _seed_project(self.store, project_id)
        return project_id

    def test_preview_and_one_many_all_selection_are_project_local(self) -> None:
        source = _write_three_page_pdf(self.root / "incoming" / "drawing.pdf", "REV-A")
        preview = preview_pdf(source, original_name="Drawing Package.pdf")
        self.assertTrue(preview["ok"])
        self.assertEqual(3, preview["pageCount"])
        self.assertEqual(_sha256(source), preview["sha256"])
        self.assertEqual(3, len({page["fingerprint"] for page in preview["pages"]}))
        for index, page in enumerate(preview["pages"]):
            self.assertEqual(index, page["index"])
            self.assertTrue(page["thumbnailDataUrl"].startswith("data:image/png;base64,"))
            self.assertGreater(page["thumbnailWidth"], 90)

        cases = [
            (self._project(1), [1], "fit_body", [1]),
            (self._project(2), [2, 0], "full_sheet", [2, 0]),
            (self._project(3), None, "fit_body", [0, 1, 2]),
        ]
        local_sources: list[Path] = []
        for project_id, selection, placement, expected in cases:
            progress_events: list[dict] = []
            result = commit_pdf_import(
                self.store,
                project_id,
                source,
                original_name="Drawing Package.pdf",
                selected_page_indices=selection,
                placement_mode=placement,
                action="add",
                progress_callback=lambda event: progress_events.append(dict(event)),
            )
            self.assertTrue(result["ok"])
            phases = [event["phase"] for event in progress_events]
            self.assertEqual("validate", phases[0])
            self.assertEqual("complete", phases[-1])
            for phase in ("validate", "render", "install", "compose", "save", "complete"):
                self.assertIn(phase, phases)
                phase_events = [event for event in progress_events if event["phase"] == phase]
                self.assertTrue(all(event["total"] == len(expected) for event in phase_events))
                self.assertTrue(all(0 <= event["completed"] <= len(expected) for event in phase_events))
            for phase in ("render", "install", "compose"):
                completed = [
                    event["completed"]
                    for event in progress_events
                    if event["phase"] == phase and event["completed"] > 0
                ]
                self.assertEqual(list(range(1, len(expected) + 1)), completed)
            imported = _pdf_pages(result["project"], result["importGroupId"])
            self.assertEqual(expected, [page["sourceImport"]["sourcePageIndex"] for page in imported])
            self.assertEqual(expected, [item["sourcePageIndex"] for item in result["pageResults"]])
            self.assertEqual(len(expected), len({page["id"] for page in imported}))
            source_path = self.store.find_dir(project_id) / result["source"]["projectLocalPath"]
            local_sources.append(source_path)
            self.assertTrue(source_path.is_file())
            self.assertEqual(_sha256(source), _sha256(source_path))
            for page in imported:
                provenance = page["sourceImport"]
                self.assertEqual(1, provenance["revision"])
                self.assertEqual(result["importGroupId"], provenance["importGroupId"])
                self.assertEqual(_sha256(source), provenance["sha256"])
                self.assertEqual(300, provenance["renderDpi"])
                preview_path = self.store.find_dir(project_id) / provenance["renderAssetPath"]
                self.assertTrue(preview_path.is_file())
                base = _base(page)
                self.assertEqual(300, base["pdfDpi"])
                rendered_width = base["width"] * base["scaleX"]
                rendered_height = base["height"] * base["scaleY"]
                if placement == "full_sheet":
                    self.assertEqual("sheet", base["pdfCoordinateSpace"])
                    self.assertTrue(page["suppressTitleBlock"])
                    display_scale_x = SHEET_WIDTH_PX / BODY_WIDTH_PX
                    display_scale_y = SHEET_HEIGHT_PX / BODY_HEIGHT_PX
                    displayed_width = rendered_width * display_scale_x
                    displayed_height = rendered_height * display_scale_y
                    displayed_left = base["left"] * display_scale_x
                    displayed_top = base["top"] * display_scale_y
                    self.assertLessEqual(displayed_width, SHEET_WIDTH_PX + 0.01)
                    self.assertLessEqual(displayed_height, SHEET_HEIGHT_PX + 0.01)
                    self.assertAlmostEqual(
                        base["width"] / base["height"],
                        displayed_width / displayed_height,
                        places=6,
                    )
                    self.assertAlmostEqual(
                        displayed_left,
                        (SHEET_WIDTH_PX - displayed_width) / 2,
                        places=5,
                    )
                    self.assertAlmostEqual(
                        displayed_top,
                        (SHEET_HEIGHT_PX - displayed_height) / 2,
                        places=5,
                    )
                else:
                    self.assertEqual("body", base["pdfCoordinateSpace"])
                    self.assertFalse(page["suppressTitleBlock"])
                    self.assertLessEqual(rendered_width, BODY_WIDTH_PX + 0.01)
                    self.assertLessEqual(rendered_height, BODY_HEIGHT_PX + 0.01)

        source.unlink()
        for local_source in local_sources:
            self.assertTrue(local_source.is_file())
            with fitz.open(local_source) as retained:
                self.assertEqual(3, retained.page_count)

    def test_same_original_filename_never_overwrites_an_existing_source(self) -> None:
        project_id = self._project(4)
        first = _write_three_page_pdf(self.root / "first" / "same-name.pdf", "FIRST")
        second = _write_three_page_pdf(self.root / "second" / "same-name.pdf", "SECOND")
        first_sha = _sha256(first)
        second_sha = _sha256(second)
        self.assertNotEqual(first_sha, second_sha)

        added_first = commit_pdf_import(
            self.store,
            project_id,
            first,
            original_name="same-name.pdf",
            selected_page_indices=[0],
            action="add",
        )
        first_local = self.store.find_dir(project_id) / added_first["source"]["projectLocalPath"]
        first_local_before = first_local.read_bytes()

        added_second = commit_pdf_import(
            self.store,
            project_id,
            second,
            original_name="same-name.pdf",
            selected_page_indices=[0],
            action="add",
        )
        second_local = self.store.find_dir(project_id) / added_second["source"]["projectLocalPath"]
        self.assertNotEqual(first_local, second_local)
        self.assertEqual(first_local_before, first_local.read_bytes())
        self.assertEqual(first_sha, _sha256(first_local))
        self.assertEqual(second_sha, _sha256(second_local))
        self.assertEqual("same-name.pdf", added_first["source"]["originalFileName"])
        self.assertEqual("same-name.pdf", added_second["source"]["originalFileName"])

    def test_all_existing_groups_are_offered_with_same_name_first_and_fingerprints(self) -> None:
        project_id = self._project(8)
        first = _write_three_page_pdf(self.root / "groups" / "first.pdf", "FIRST")
        second = _write_three_page_pdf(self.root / "groups" / "second.pdf", "SECOND")
        added_first = commit_pdf_import(
            self.store,
            project_id,
            first,
            original_name="Original Name.pdf",
            selected_page_indices=[2, 0],
            action="add",
        )
        added_second = commit_pdf_import(
            self.store,
            project_id,
            second,
            original_name="Revised Candidate.pdf",
            selected_page_indices=[1],
            action="add",
        )
        project = added_second["project"]
        groups = existing_pdf_import_groups(project, original_name="REVISED CANDIDATE.PDF")
        self.assertEqual(2, len(groups))
        self.assertEqual(added_second["importGroupId"], groups[0]["groupId"])
        self.assertTrue(groups[0]["sameName"])
        self.assertFalse(groups[1]["sameName"])
        self.assertEqual(added_first["importGroupId"], groups[1]["groupId"])
        for group in groups:
            self.assertEqual(len(group["pageIds"]), len(group["pageIndices"]))
            self.assertEqual(len(group["pageIds"]), len(group["pageFingerprints"]))
            self.assertTrue(all(group["pageFingerprints"]))

        renamed_revision_groups = existing_pdf_import_groups(project, original_name="renamed-revision.pdf")
        self.assertEqual(2, len(renamed_revision_groups))
        self.assertTrue(all(group["sameName"] is False for group in renamed_revision_groups))

    def test_project_transform_is_applied_before_one_atomic_save(self) -> None:
        project_id = self._project(9)
        source = _write_three_page_pdf(self.root / "transform" / "drawing.pdf", "TRANSFORM")
        original_save = self.store.save

        def transform(project: dict) -> dict:
            project["pdfTransformMarker"] = "normalized-before-save"
            return project

        with mock.patch.object(self.store, "save", wraps=original_save) as save_spy:
            result = commit_pdf_import(
                self.store,
                project_id,
                source,
                selected_page_indices=[0],
                action="add",
                project_transform=transform,
            )
        self.assertEqual(1, save_spy.call_count)
        self.assertEqual("normalized-before-save", result["project"]["pdfTransformMarker"])
        self.assertEqual(
            "normalized-before-save",
            self.store.load(project_id)["pdfTransformMarker"],
        )

    def test_project_transform_failure_rolls_back_new_assets_and_project(self) -> None:
        project_id = self._project(10)
        source = _write_three_page_pdf(self.root / "transform-failure" / "drawing.pdf", "FAIL")
        project_path = self.store.read_path(project_id)
        project_dir = self.store.find_dir(project_id)
        before_json = project_path.read_bytes()
        before_files = {
            str(path.relative_to(project_dir))
            for path in project_dir.rglob("*")
            if path.is_file()
        }

        def fail_transform(_project: dict) -> dict:
            raise ValueError("simulated normalization failure")

        with self.assertRaises(PdfPageImportError) as caught:
            commit_pdf_import(
                self.store,
                project_id,
                source,
                selected_page_indices=[0],
                action="add",
                project_transform=fail_transform,
            )
        self.assertEqual("project_transform_failed", caught.exception.code)
        self.assertEqual("save", caught.exception.phase)
        self.assertEqual(before_json, project_path.read_bytes())
        self.assertEqual(
            before_files,
            {
                str(path.relative_to(project_dir))
                for path in project_dir.rglob("*")
                if path.is_file()
            },
        )

    def test_explicit_replace_preserves_page_identity_metadata_and_overlays(self) -> None:
        project_id = self._project(5)
        original = _write_three_page_pdf(self.root / "original" / "plans.pdf", "ORIGINAL")
        initial = commit_pdf_import(
            self.store,
            project_id,
            original,
            selected_page_indices=None,
            placement_mode="fit_body",
            action="add",
        )
        group_id = initial["importGroupId"]
        project = initial["project"]
        imported = _pdf_pages(project, group_id)
        first, middle, last = imported
        preserved_by_id: dict[str, dict] = {}
        base_ids: dict[str, str] = {}
        for offset, page in enumerate((first, last)):
            page["sheetCode"] = f"KEEP-{offset + 1}"
            page["displaySheetCode"] = f"KEEP-{offset + 1}"
            page["sheetTitle"] = f"Preserved title {offset + 1}"
            page["include"] = offset == 0
            page["publishStatus"] = "YES" if page["include"] else "NO"
            page["order"] = 20.25 + offset
            page["notes"] = f"Preserved notes {offset + 1}"
            page["canvasObjects"].extend([
                {
                    "type": "textbox",
                    "objectId": f"overlay_text_{offset}",
                    "text": f"annotation {offset}",
                    "left": 200,
                    "top": 120,
                },
                {
                    "type": "image",
                    "objectId": f"component_{offset}",
                    "libraryComponentId": f"stable_component_{offset}",
                    "src": "/api/library/asset/stable",
                },
            ])
            unrelated_asset = {
                "id": f"unrelated_asset_{offset}",
                "type": "annotation-asset",
                "url": f"/api/assets/unrelated-{offset}.png",
            }
            page["assets"].append(unrelated_asset)
            preserved_by_id[page["id"]] = {
                "sheetCode": page["sheetCode"],
                "displaySheetCode": page["displaySheetCode"],
                "sheetTitle": page["sheetTitle"],
                "include": page["include"],
                "publishStatus": page["publishStatus"],
                "order": page["order"],
                "notes": page["notes"],
                "overlays": _overlays(page),
                "unrelatedAsset": unrelated_asset,
            }
            base_ids[page["id"]] = _base(page)["objectId"]
        middle_before = copy.deepcopy(middle)
        self.store.save(project_id, project)

        revised = _write_three_page_pdf(self.root / "revised" / "plans.pdf", "REVISED")
        revised_sha = _sha256(revised)
        mapping = {first["id"]: 2, last["id"]: 0}
        replaced = commit_pdf_import(
            self.store,
            project_id,
            revised,
            original_name="plans.pdf",
            selected_page_indices=[2, 0],
            placement_mode=None,
            action="replace",
            replace_mapping=mapping,
            import_group_id=group_id,
        )
        self.assertEqual(2, replaced["revision"])
        self.assertEqual([middle["id"]], replaced["unmatchedExistingPageIds"])
        self.assertEqual([1], replaced["unmatchedSourcePageIndices"])
        self.assertEqual(len(project["pages"]), len(replaced["project"]["pages"]))

        after_by_id = {page["id"]: page for page in replaced["project"]["pages"]}
        for page_id, source_index in mapping.items():
            page = after_by_id[page_id]
            expected = preserved_by_id[page_id]
            for field in (
                "sheetCode",
                "displaySheetCode",
                "sheetTitle",
                "include",
                "publishStatus",
                "order",
                "notes",
            ):
                self.assertEqual(expected[field], page[field], f"field changed: {field}")
            self.assertEqual(expected["overlays"], _overlays(page))
            self.assertEqual(base_ids[page_id], _base(page)["objectId"])
            self.assertEqual(source_index, _base(page)["pdfPage"])
            self.assertEqual(revised_sha, page["sourceImport"]["sha256"])
            self.assertEqual(2, page["sourceImport"]["revision"])
            self.assertEqual(group_id, page["sourceImport"]["importGroupId"])
            self.assertEqual(initial["source"]["sha256"], page["sourceImport"]["previousSha256"])
            self.assertIn(expected["unrelatedAsset"], page["assets"])
            pdf_assets = [asset for asset in page["assets"] if asset.get("type") == "pdf-preview"]
            self.assertEqual(1, len(pdf_assets))
            self.assertEqual(page["sourceImport"]["renderAssetUrl"], pdf_assets[0]["url"])

        self.assertEqual(middle_before, after_by_id[middle["id"]])
        original_local = self.store.find_dir(project_id) / initial["source"]["projectLocalPath"]
        revised_local = self.store.find_dir(project_id) / replaced["source"]["projectLocalPath"]
        self.assertTrue(original_local.is_file())
        self.assertTrue(revised_local.is_file())
        self.assertNotEqual(original_local, revised_local)

    def test_out_of_range_and_save_failure_leave_project_and_assets_unchanged(self) -> None:
        project_id = self._project(6)
        source = _write_three_page_pdf(self.root / "rollback" / "rollback.pdf", "ROLLBACK")
        project_path = self.store.read_path(project_id)
        self.assertIsNotNone(project_path)
        before_json = project_path.read_bytes()
        project_dir = self.store.find_dir(project_id)

        def files() -> set[str]:
            return {
                str(path.relative_to(project_dir))
                for path in project_dir.rglob("*")
                if path.is_file()
            }

        before_files = files()
        with self.assertRaises(PdfPageImportError) as out_of_range:
            commit_pdf_import(
                self.store,
                project_id,
                source,
                selected_page_indices=[3],
                action="add",
            )
        self.assertEqual("page_out_of_range", out_of_range.exception.code)
        self.assertEqual("validate", out_of_range.exception.phase)
        self.assertEqual(before_json, project_path.read_bytes())
        self.assertEqual(before_files, files())

        with mock.patch.object(self.store, "save", side_effect=OSError("simulated atomic save failure")):
            with self.assertRaises(PdfPageImportError) as save_failure:
                commit_pdf_import(
                    self.store,
                    project_id,
                    source,
                    selected_page_indices=[0, 1],
                    action="add",
                )
        error = save_failure.exception
        self.assertEqual("project_save_failed", error.code)
        self.assertEqual("save", error.phase)
        self.assertIn("simulated atomic save failure", error.detail)
        self.assertTrue(error.to_dict()["ok"] is False)
        self.assertEqual(before_json, project_path.read_bytes())
        self.assertEqual(before_files, files())

    def test_replace_rejects_implicit_or_ambiguous_changes(self) -> None:
        project_id = self._project(7)
        original = _write_three_page_pdf(self.root / "mapping" / "mapping.pdf", "MAP-A")
        initial = commit_pdf_import(
            self.store,
            project_id,
            original,
            selected_page_indices=[0, 1],
            action="add",
        )
        imported = _pdf_pages(initial["project"], initial["importGroupId"])
        revised = _write_three_page_pdf(self.root / "mapping2" / "mapping.pdf", "MAP-B")
        before = self.store.read_path(project_id).read_bytes()

        invalid_calls = [
            ({}, [0], "replace_mapping_required"),
            ({imported[0]["id"]: "not-an-index"}, [0], "invalid_replace_mapping"),
            ({imported[0]["id"]: 0, imported[1]["id"]: 0}, [0], "duplicate_replace_source_page"),
            ({imported[0]["id"]: 0}, [0, 1], "replace_selection_mismatch"),
            ({"missing-page": 0}, [0], "replace_page_not_found"),
        ]
        for mapping, selected, expected_code in invalid_calls:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(PdfPageImportError) as caught:
                    commit_pdf_import(
                        self.store,
                        project_id,
                        revised,
                        selected_page_indices=selected,
                        action="replace",
                        replace_mapping=mapping,
                    )
                self.assertEqual(expected_code, caught.exception.code)
                self.assertEqual(before, self.store.read_path(project_id).read_bytes())


if __name__ == "__main__":
    unittest.main()
