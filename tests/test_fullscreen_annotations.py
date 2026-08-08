from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.page_template_store import PageTemplateStore
from core.workbook_status_sync import project_hash


class FullscreenAnnotationContractTests(unittest.TestCase):
    def test_project_hash_tracks_annotations_without_canvas_coupling(self) -> None:
        project = {
            "metadata": {"projectName": "Disposable annotation fixture"},
            "pages": [{
                "id": "page-1",
                "order": 1,
                "include": True,
                "sheetCode": "A-1",
                "sheetTitle": "Fixture",
                "canvasObjects": [{"objectId": "drawing-1", "type": "rect"}],
            }],
            "worksheets": [],
        }
        original_hash = project_hash(project)
        original_canvas = list(project["pages"][0]["canvasObjects"])
        project["pages"][0]["annotationObjects"] = [
            {"objectId": "annotation-1", "annotationType": "rectangle", "type": "Rect"}
        ]
        self.assertNotEqual(original_hash, project_hash(project))
        self.assertEqual(original_canvas, project["pages"][0]["canvasObjects"])
        with_objects_hash = project_hash(project)
        project["pages"][0]["annotationSettings"] = {
            "visible": True,
            "locked": False,
            "includeInExport": False,
        }
        self.assertNotEqual(with_objects_hash, project_hash(project))

    def test_template_instance_freshens_annotation_ids_independently(self) -> None:
        with tempfile.TemporaryDirectory(prefix="singh360_annotation_templates_") as raw:
            store = PageTemplateStore(Path(raw))
            source = {
                "id": "source-page",
                "order": 1,
                "include": True,
                "sheetCode": "A-1",
                "sheetTitle": "Template",
                "pageType": "canvas",
                "canvasObjects": [{"objectId": "drawing-1", "type": "rect"}],
                "annotationObjects": [{
                    "objectId": "annotation-1",
                    "annotationType": "rectangle",
                    "type": "Rect",
                    "objects": [{"objectId": "annotation-child-1", "type": "Line"}],
                }],
                "annotationSettings": {
                    "visible": True,
                    "locked": False,
                    "includeInExport": True,
                },
            }
            saved = store.save_template(source, "Annotation fixture")
            first = store.page_from_template(saved["id"], new_page_id="copy-1")
            second = store.page_from_template(saved["id"], new_page_id="copy-2")
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            first_ids = {
                first["annotationObjects"][0]["objectId"],
                first["annotationObjects"][0]["objects"][0]["objectId"],
            }
            second_ids = {
                second["annotationObjects"][0]["objectId"],
                second["annotationObjects"][0]["objects"][0]["objectId"],
            }
            self.assertTrue(first_ids.isdisjoint(second_ids))
            self.assertNotIn("annotation-1", first_ids | second_ids)
            self.assertEqual("drawing-1", source["canvasObjects"][0]["objectId"])
            self.assertEqual("annotation-1", source["annotationObjects"][0]["objectId"])

    def test_frontend_contract_keeps_fullscreen_state_out_of_project_data(self) -> None:
        root = Path(__file__).resolve().parents[1]
        types = (root / "frontend/src/model/types.ts").read_text(encoding="utf-8")
        layer = (root / "frontend/src/components/AnnotationLayer.tsx").read_text(encoding="utf-8")
        fullscreen = (root / "frontend/src/hooks/useFullscreen.ts").read_text(encoding="utf-8")
        app = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
        self.assertIn("annotationObjects?: Record<string, unknown>[]", types)
        self.assertIn("serialized={page.annotationObjects ?? []}", (root / "frontend/src/components/PageRenderer.tsx").read_text(encoding="utf-8"))
        self.assertIn("onSerializedRef.current(objects)", layer)
        self.assertNotIn("canvasObjects", layer)
        self.assertIn("target.requestFullscreen()", fullscreen)
        self.assertIn("fullscreenchange", fullscreen)
        self.assertIn("fullscreenerror", fullscreen)
        self.assertNotIn("ProjectModel", fullscreen)
        self.assertIn("if (document.fullscreenElement) return;", app)


if __name__ == "__main__":
    unittest.main()
