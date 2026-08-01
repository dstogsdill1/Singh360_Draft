from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.page_template_store import PageTemplateStore


def _object_records(objects: list[dict]) -> list[dict]:
    records: list[dict] = []

    def walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        records.append(value)
        walk(value.get("objects"))

    walk(objects)
    return records


class PageIdentityContractTests(unittest.TestCase):
    def test_template_instances_freshen_rich_object_tree_and_detach_source(self) -> None:
        original = {
            "id": "origin-page",
            "order": 8,
            "include": False,
            "sheetCode": "SRC-8",
            "displaySheetCode": "SRC-8",
            "sheetTitle": "Rich source page",
            "sheetTab": "SOURCE TAB",
            "pageType": "hybrid",
            "templateId": "ansi-b-standard",
            "linkedWorksheetId": "worksheet-origin",
            "recipeWorksheetId": "recipe-origin",
            "sourceSheet": "SOURCE TAB",
            "sourceRange": "A1:F20",
            "sourceImport": {
                "id": "import-origin",
                "type": "pdf",
                "sha256": "a" * 64,
                "projectLocalPath": "assets/pdf/origin.pdf",
                "importedAt": "2026-08-01T00:00:00Z",
            },
            "blocks": [{
                "id": "table-content-id",
                "type": "table",
                "sourceWorksheetId": "worksheet-origin",
                "sourceSheet": "SOURCE TAB",
                "sourceRange": "A1:F20",
                "headers": ["Device"],
                "rows": [["Keep this content"]],
            }],
            "canvasObjects": [{
                "type": "Group",
                "objectId": "root-object",
                "assemblyId": "stable-assembly-id",
                "libraryComponentId": "stable-library-component-id",
                "pdfSource": "/api/projects/origin/assets/pdf/origin.pdf",
                "pdfImportId": "import-origin",
                "objects": [{
                    "type": "Rect",
                    "objectId": "child-object",
                    "smartParentId": "root-object",
                    "componentId": "stable-component-id",
                    "text": "Keep child content",
                }, {
                    "type": "Group",
                    "objectId": "nested-group",
                    "objects": [{
                        "type": "Textbox",
                        "objectId": "grandchild-object",
                        "text": "Keep grandchild content",
                    }],
                }],
            }],
            "notes": "Keep page content",
        }
        untouched = deepcopy(original)

        with TemporaryDirectory(prefix="s360-page-identity-") as raw:
            store = PageTemplateStore(Path(raw))
            entry = store.save_template(
                original,
                "Rich independent page",
                template_id="rich-page-template",
            )
            stored = store.get_template(entry["id"])
            self.assertIsNotNone(stored)
            assert stored is not None

            self.assertNotIn("sourceImport", stored)
            self.assertNotIn("linkedWorksheetId", stored)
            self.assertNotIn("recipeWorksheetId", stored)
            self.assertNotIn("sourceWorksheetId", stored["blocks"][0])
            self.assertNotIn("sourceSheet", stored["blocks"][0])
            self.assertNotIn("sourceRange", stored["blocks"][0])
            self.assertNotIn("pdfSource", stored["canvasObjects"][0])
            self.assertNotIn("pdfImportId", stored["canvasObjects"][0])

            first = store.page_from_template(
                entry["id"], new_page_id="new-page-one", sheet_title="First instance"
            )
            second = store.page_from_template(
                entry["id"], new_page_id="new-page-two", sheet_title="Second instance"
            )
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            assert first is not None and second is not None

            first_records = _object_records(first["canvasObjects"])
            second_records = _object_records(second["canvasObjects"])
            first_ids = {record["objectId"] for record in first_records}
            second_ids = {record["objectId"] for record in second_records}
            original_ids = {record["objectId"] for record in _object_records(original["canvasObjects"])}

            self.assertEqual(4, len(first_ids))
            self.assertEqual(4, len(second_ids))
            self.assertTrue(first_ids.isdisjoint(second_ids))
            self.assertTrue(first_ids.isdisjoint(original_ids))
            self.assertTrue(second_ids.isdisjoint(original_ids))
            self.assertEqual(first_records[0]["objectId"], first_records[1]["smartParentId"])
            self.assertEqual("stable-assembly-id", first_records[0]["assemblyId"])
            self.assertEqual(
                "stable-library-component-id", first_records[0]["libraryComponentId"]
            )
            self.assertEqual("stable-component-id", first_records[1]["componentId"])
            self.assertEqual("Keep child content", first_records[1]["text"])
            self.assertEqual("Keep grandchild content", first_records[3]["text"])
            self.assertEqual("Keep this content", first["blocks"][0]["rows"][0][0])
            self.assertEqual("app", first["sourceMode"])
            self.assertEqual("none", first["syncDirection"])

            # Saving and inserting never mutate the source page or stored template.
            self.assertEqual(untouched, original)
            self.assertEqual(stored, store.get_template(entry["id"]))

    def test_frontend_duplicate_and_template_flows_use_identity_helpers(self) -> None:
        root = Path(__file__).resolve().parents[1]
        duplication = (root / "frontend/src/model/pageDuplication.ts").read_text(encoding="utf-8")
        template_modal = (
            root / "frontend/src/components/PageTemplateLibraryModal.tsx"
        ).read_text(encoding="utf-8")
        save_modal = (root / "frontend/src/components/SavePageTemplateModal.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("assignFreshCanvasObjectIds", duplication)
        self.assertIn(
            "const canvasObjects = freshCanvasObjects(detached.canvasObjects);",
            duplication,
        )
        self.assertIn("canvasObjects,", duplication)
        self.assertIn("export function instantiatePageTemplate", duplication)
        self.assertIn("'sourceImport'", duplication)
        self.assertIn("const page = instantiatePageTemplate(", template_modal)
        self.assertIn("preparePageTemplatePayload(portable)", save_modal)


if __name__ == "__main__":
    unittest.main()
