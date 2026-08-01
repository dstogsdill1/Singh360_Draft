from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

from openpyxl import Workbook
from PIL import Image

from core.csv_importer import build_csv_worksheet_and_pages
from core.page_template_store import PageTemplateStore
from core.project_store import ProjectStore
from core.sheet_importer import import_workbook_sheets
from core.standalone_project import (
    archive_page,
    create_standalone_project,
    normalize_standalone_project,
    restore_page,
)


CREATED = "2026-08-01T09:00:00Z"
EDITED = "2026-08-01T10:00:00Z"
ARCHIVED = "2026-08-01T11:00:00Z"
RESTORED = "2026-08-01T12:00:00Z"


def _page(
    page_id: str,
    order: int,
    title: str,
    code: str,
    page_type: str,
    *,
    include: bool = True,
) -> dict:
    return {
        "id": page_id,
        "order": order,
        "include": include,
        "sheetCode": code,
        "displaySheetCode": code,
        "sheetTitle": title,
        "sheetTab": "",
        "pageType": page_type,
        "pageFamily": "drawing" if page_type in {"canvas", "image"} else "table",
        "templateId": "ansi-b-standard",
        "blocks": [],
        "canvasObjects": [],
        "notes": "",
        "createdAt": CREATED,
        "modifiedAt": CREATED,
    }


def _index_partitions(project: dict) -> list[list[str]]:
    """Model the generated index renderer's persisted paging contract."""
    included = sorted(
        (page for page in project["pages"] if page.get("include", True)),
        key=lambda page: int(page.get("order") or 0),
    )
    index_pages = sorted(
        (page for page in included if page.get("managedPage") == "index"),
        key=lambda page: int(page.get("continuationIndex") or 0),
    )
    result: list[list[str]] = []
    for page in index_pages:
        rows_per_page = int(page["indexRowsPerPage"])
        start = int(page.get("continuationIndex") or 0) * rows_per_page
        count = int(page["indexRowsOnPage"])
        result.append([row["id"] for row in included[start : start + count]])
    return result


class StandalonePageTypePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = tempfile.TemporaryDirectory(prefix="s360_page_type_persistence_")
        self.root = Path(self.runtime.name)
        self.docs = self.root / ".docs"
        self.project_id = "standalone-page-types"
        self.store = ProjectStore(self.docs)
        self.project = create_standalone_project(
            self.project_id,
            {"projectName": "Disposable Page Type Persistence"},
            profile="minimal",
            now=CREATED,
            rows_per_index_page=4,
        )
        self.store.save(self.project_id, self.project)

    def tearDown(self) -> None:
        self.runtime.cleanup()

    def test_all_supported_page_types_survive_source_independent_reload(self) -> None:
        external = self.root / "disconnected-originals"
        external.mkdir()
        original_xlsx = external / "Original Schedule.xlsx"
        original_csv = external / "Original Schedule.csv"
        original_image = external / "Original Screenshot.png"

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Imported Schedule"
        worksheet.append(["Tag", "Description", "Quantity"])
        worksheet.append(["CTRL-01", "Disposable Controller", 2])
        workbook.save(original_xlsx)
        workbook.close()
        original_csv.write_text(
            "Category,Tag,Description\nLighting,LGT-01,Disposable Lighting Relay\n",
            encoding="utf-8",
        )
        Image.new("RGB", (48, 27), "#f4b183").save(original_image, format="PNG")

        project = self.store.load(self.project_id)
        self.assertIsNotNone(project)
        package = self.store.find_dir(self.project_id)
        self.assertIsNotNone(package)

        local_xlsx = self.store.sources_dir(self.project_id, "workbook") / "source_schedule.xlsx"
        local_csv = self.store.sources_dir(self.project_id, "csv") / "source_schedule.csv"
        local_image = self.store.assets_images_dir(self.project_id) / "source_screenshot.png"
        shutil.copy2(original_xlsx, local_xlsx)
        shutil.copy2(original_csv, local_csv)
        shutil.copy2(original_image, local_image)
        xlsx_sha = hashlib.sha256(local_xlsx.read_bytes()).hexdigest()
        csv_sha = hashlib.sha256(local_csv.read_bytes()).hexdigest()
        image_sha = hashlib.sha256(local_image.read_bytes()).hexdigest()

        project, workbook_pages = import_workbook_sheets(
            project,
            local_xlsx,
            ["Imported Schedule"],
            insert_after_page_id=project["pages"][1]["id"],
            preserve_exact=True,
            source_filename=original_xlsx.name,
            source_sha256=xlsx_sha,
            project_local_path="sources/workbook/source_schedule.xlsx",
        )
        self.assertEqual(1, len(workbook_pages))
        workbook_page = next(
            page for page in project["pages"] if page["id"] == workbook_pages[0]["id"]
        )
        workbook_page["sourceImport"]["originalPath"] = str(original_xlsx)

        csv_source_id = "source-csv-stable"
        csv_worksheet, csv_pages = build_csv_worksheet_and_pages(
            local_csv,
            "worksheet-csv-stable",
            csv_source_id,
            original_csv.name,
            len(project["pages"]) + 1,
        )
        csv_import = {
            "sourceId": csv_source_id,
            "sourceType": "csv",
            "originalFileName": original_csv.name,
            "originalPath": str(original_csv),
            "sha256": csv_sha,
            "selectedWorksheet": "Original Schedule",
            "importMode": "one_time_editable_table",
            "projectLocalPath": "sources/csv/source_schedule.csv",
            "importedAt": CREATED,
        }
        csv_worksheet["provenance"].update(csv_import)
        project["worksheets"].append(csv_worksheet)
        project["sources"].append({
            "id": csv_source_id,
            "type": "csv",
            **csv_import,
        })
        for page in csv_pages:
            page["sourceImport"] = deepcopy(csv_import)
            page["createdAt"] = CREATED
            page["modifiedAt"] = CREATED
        project["pages"].extend(csv_pages)

        blank = _page("page-blank-stable", 0, "Blank Layout", "B-1", "canvas")
        blank["canvasObjects"] = [{"objectId": "blank-note", "type": "textbox", "text": "Initial"}]
        image = _page(
            "page-image-stable",
            0,
            "Project-local Screenshot",
            "IMG-1",
            "image",
            include=False,
        )
        image["canvasObjects"] = [{
            "objectId": "image-object-stable",
            "type": "image",
            "src": "/api/assets/standalone-page-types/source_screenshot.png",
            "width": 48,
            "height": 27,
            "scaleX": 1,
            "scaleY": 1,
        }]
        image["sourceImport"] = {
            "sourceId": "source-image-stable",
            "sourceType": "image",
            "originalFileName": original_image.name,
            "originalPath": str(original_image),
            "sha256": image_sha,
            "importMode": "one_time_project_asset",
            "projectLocalPath": "assets/images/source_screenshot.png",
            "placementMode": "fit_body",
            "importedAt": CREATED,
        }
        project["sources"].append({"id": "source-image-stable", "type": "image", **image["sourceImport"]})

        text_table = _page("page-text-table-stable", 0, "Editable Notes", "N-1", "data-grid")
        text_table["blocks"] = [
            {"id": "notes-paragraph", "type": "paragraph", "text": "Initial scope", "editable": True},
            {
                "id": "notes-table",
                "type": "table",
                "headers": ["Item", "Status"],
                "rows": [["Disposable item", "Draft"]],
                "editable": True,
            },
        ]

        template_seed = deepcopy(text_table)
        template_seed["id"] = "template-seed-page"
        template_seed["blocks"][1]["sourceWorksheetId"] = "must-not-remain-linked"
        template_store = PageTemplateStore(self.docs)
        entry = template_store.save_template(
            template_seed,
            "Disposable Notes Template",
            template_id="template-persistence-stable",
        )
        template_page = template_store.page_from_template(
            entry["id"],
            new_page_id="page-template-stable",
            order=0,
            sheet_code="TPL-1",
            sheet_title="Template-derived Notes",
        )
        self.assertIsNotNone(template_page)
        template_page["createdAt"] = CREATED
        template_page["modifiedAt"] = CREATED
        self.assertNotIn("sourceWorksheetId", template_page["blocks"][1])

        project["pages"].extend([blank, image, text_table, template_page])
        for order, page in enumerate(project["pages"], start=1):
            page["order"] = order
            if not page.get("appManaged"):
                page["createdAt"] = CREATED
                page["modifiedAt"] = CREATED

        # Exercise normal user edits before the durable Save Project operation.
        project["metadata"]["notes"] = "Edited entirely inside Singh360"
        blank["sheetTitle"] = "Edited Blank Layout"
        blank["canvasObjects"][0]["text"] = "Persisted local edit"
        blank["modifiedAt"] = EDITED
        image["notes"] = "Contained project-local image edit"
        image["modifiedAt"] = EDITED
        workbook_page["blocks"][0]["grid"][1][1] = "Edited after one-time import"
        workbook_page["modifiedAt"] = EDITED
        csv_pages[0]["blocks"][0]["rows"][0][2] = "Edited CSV description"
        csv_pages[0]["modifiedAt"] = EDITED
        text_table["blocks"][1]["rows"][0][1] = "Issued"
        text_table["modifiedAt"] = EDITED
        template_page["blocks"][0]["text"] = "Template instance edit"
        template_page["modifiedAt"] = EDITED

        project = normalize_standalone_project(project, now=EDITED, rows_per_index_page=4)
        expected_page_state = {
            page["id"]: (
                page["order"],
                page.get("include", True),
                page.get("createdAt"),
                page.get("modifiedAt"),
            )
            for page in project["pages"]
        }
        self.store.save(self.project_id, project)

        # Simulate a disconnected source drive before a new server/store opens.
        original_xlsx.unlink()
        original_csv.unlink()
        original_image.unlink()
        restarted_store = ProjectStore(self.docs)
        reloaded = restarted_store.load(self.project_id)
        self.assertIsNotNone(reloaded)
        self.assertEqual("Edited entirely inside Singh360", reloaded["metadata"]["notes"])
        self.assertEqual(
            expected_page_state,
            {
                page["id"]: (
                    page["order"],
                    page.get("include", True),
                    page.get("createdAt"),
                    page.get("modifiedAt"),
                )
                for page in reloaded["pages"]
            },
        )

        by_id = {page["id"]: page for page in reloaded["pages"]}
        self.assertEqual("Persisted local edit", by_id[blank["id"]]["canvasObjects"][0]["text"])
        self.assertEqual(
            "Edited after one-time import",
            by_id[workbook_page["id"]]["blocks"][0]["grid"][1][1],
        )
        self.assertEqual(
            "Edited CSV description",
            by_id[csv_pages[0]["id"]]["blocks"][0]["rows"][0][2],
        )
        self.assertEqual("Issued", by_id[text_table["id"]]["blocks"][1]["rows"][0][1])
        self.assertEqual("Template instance edit", by_id[template_page["id"]]["blocks"][0]["text"])
        self.assertFalse(by_id[image["id"]]["include"])

        for page_id in (
            blank["id"],
            image["id"],
            workbook_page["id"],
            csv_pages[0]["id"],
            text_table["id"],
            template_page["id"],
        ):
            self.assertEqual(EDITED, by_id[page_id]["modifiedAt"])
            self.assertGreater(by_id[page_id]["modifiedAt"], by_id[page_id]["createdAt"])

        package = restarted_store.find_dir(self.project_id)
        self.assertEqual(local_xlsx.read_bytes(), (package / "sources/workbook/source_schedule.xlsx").read_bytes())
        self.assertEqual(local_csv.read_bytes(), (package / "sources/csv/source_schedule.csv").read_bytes())
        self.assertEqual(local_image.read_bytes(), (package / "assets/images/source_screenshot.png").read_bytes())
        self.assertEqual(
            "sources/workbook/source_schedule.xlsx",
            by_id[workbook_page["id"]]["sourceImport"]["projectLocalPath"],
        )
        self.assertEqual(
            "sources/csv/source_schedule.csv",
            by_id[csv_pages[0]["id"]]["sourceImport"]["projectLocalPath"],
        )
        self.assertEqual(
            "assets/images/source_screenshot.png",
            by_id[image["id"]]["sourceImport"]["projectLocalPath"],
        )
        self.assertFalse(any(external.iterdir()))

    def test_duplicate_archive_and_neighbor_restore_survive_fresh_stores(self) -> None:
        project = self.store.load(self.project_id)
        pages = [
            _page("page-a", 3, "Page A", "A", "canvas"),
            _page("page-b", 4, "Page B", "B", "data-grid"),
            _page("page-c", 5, "Page C", "C", "canvas"),
        ]
        pages[1]["blocks"] = [{
            "id": "page-b-table",
            "type": "table",
            "headers": ["Name"],
            "rows": [["Original"]],
            "editable": True,
        }]
        project["pages"].extend(pages)
        project = normalize_standalone_project(project, now=CREATED)

        source = next(page for page in project["pages"] if page["id"] == "page-b")
        duplicate = deepcopy(source)
        duplicate.update({
            "id": "page-b-copy",
            "sheetCode": "B-COPY",
            "displaySheetCode": "B-COPY",
            "sheetTitle": "Page B Copy",
            "order": source["order"] + 0.5,
            "createdAt": EDITED,
            "modifiedAt": EDITED,
        })
        duplicate["blocks"][0]["rows"][0][0] = "Independent copy"
        project["pages"].append(duplicate)
        project = normalize_standalone_project(project, now=EDITED)
        self.store.save(self.project_id, project)

        restarted = ProjectStore(self.docs).load(self.project_id)
        by_id = {page["id"]: page for page in restarted["pages"]}
        self.assertEqual("Original", by_id["page-b"]["blocks"][0]["rows"][0][0])
        self.assertEqual("Independent copy", by_id["page-b-copy"]["blocks"][0]["rows"][0][0])
        self.assertNotEqual(by_id["page-b"]["id"], by_id["page-b-copy"]["id"])

        archived = archive_page(restarted, "page-b", reason="Disposable archive proof", now=ARCHIVED)
        self.store.save(self.project_id, archived)
        archived_reload = ProjectStore(self.docs).load(self.project_id)
        retired = next(page for page in archived_reload["archivedPages"] if page["id"] == "page-b")
        self.assertEqual("page-a", retired["archivedPreviousPageId"])
        self.assertEqual("page-b-copy", retired["archivedNextPageId"])
        self.assertEqual(ARCHIVED, retired["archivedAt"])
        self.assertFalse(retired["include"])

        restored = restore_page(archived_reload, "page-b", now=RESTORED)
        self.store.save(self.project_id, restored)
        restored_reload = ProjectStore(self.docs).load(self.project_id)
        user_ids = [
            page["id"]
            for page in restored_reload["pages"]
            if not page.get("appManaged")
        ]
        self.assertEqual(["page-a", "page-b", "page-b-copy", "page-c"], user_ids)
        restored_page = next(page for page in restored_reload["pages"] if page["id"] == "page-b")
        self.assertEqual("Original", restored_page["blocks"][0]["rows"][0][0])
        self.assertEqual(ARCHIVED, restored_page["lastArchivedAt"])
        self.assertEqual("Disposable archive proof", restored_page["lastArchivedReason"])
        self.assertEqual(RESTORED, restored_page["restoredAt"])

    def test_automatic_index_updates_continuations_and_omits_excluded_pages(self) -> None:
        project = self.store.load(self.project_id)
        project["pages"].extend(
            _page(
                f"drawing-{number}",
                number + 2,
                f"Drawing {number}",
                f"D-{number}",
                "canvas",
                include=number != 4,
            )
            for number in range(1, 9)
        )
        first = normalize_standalone_project(project, now=CREATED, rows_per_index_page=3)
        self.store.save(self.project_id, first)
        first_reload = ProjectStore(self.docs).load(self.project_id)
        first_index = [page for page in first_reload["pages"] if page.get("managedPage") == "index"]
        self.assertEqual(4, len(first_index))
        self.assertEqual([3, 3, 3, 3], [page["indexRowsOnPage"] for page in first_index])
        first_rows = [page_id for partition in _index_partitions(first_reload) for page_id in partition]
        self.assertNotIn("drawing-4", first_rows)
        self.assertEqual(
            [page["id"] for page in first_reload["pages"] if page.get("include", True)],
            first_rows,
        )
        stable_continuation_ids = [page["id"] for page in first_index]

        drawing_2 = next(page for page in first_reload["pages"] if page["id"] == "drawing-2")
        drawing_2["sheetTitle"] = "Updated Drawing Two"
        drawing_2["sheetCode"] = "D-2-UPDATED"
        drawing_2["displaySheetCode"] = "D-2-UPDATED"
        drawing_2["modifiedAt"] = EDITED
        drawing_4 = next(page for page in first_reload["pages"] if page["id"] == "drawing-4")
        drawing_4["include"] = True
        drawing_4["modifiedAt"] = EDITED

        updated = normalize_standalone_project(first_reload, now=EDITED, rows_per_index_page=3)
        self.store.save(self.project_id, updated)
        updated_reload = ProjectStore(self.docs).load(self.project_id)
        updated_index = [page for page in updated_reload["pages"] if page.get("managedPage") == "index"]
        self.assertEqual(5, len(updated_index))
        self.assertEqual([3, 3, 3, 3, 2], [page["indexRowsOnPage"] for page in updated_index])
        self.assertEqual(stable_continuation_ids, [page["id"] for page in updated_index[:4]])

        updated_rows = [page_id for partition in _index_partitions(updated_reload) for page_id in partition]
        self.assertIn("drawing-4", updated_rows)
        self.assertEqual(
            [page["id"] for page in updated_reload["pages"] if page.get("include", True)],
            updated_rows,
        )
        persisted_drawing_2 = next(page for page in updated_reload["pages"] if page["id"] == "drawing-2")
        self.assertEqual("Updated Drawing Two", persisted_drawing_2["sheetTitle"])
        self.assertEqual("D-2-UPDATED", persisted_drawing_2["displaySheetCode"])
        self.assertEqual(CREATED, persisted_drawing_2["createdAt"])
        self.assertEqual(EDITED, persisted_drawing_2["modifiedAt"])


if __name__ == "__main__":
    unittest.main()
