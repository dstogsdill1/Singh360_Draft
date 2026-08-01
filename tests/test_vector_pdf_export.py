from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from core.vector_pdf_export import (
    VectorPlacement,
    _destination_rect,
    apply_vector_pdf_underlays,
    audit_export_preview_exclusion,
    build_selected_export_document,
    prepare_vector_export_clone,
)


class VectorPdfExportGeometryTests(unittest.TestCase):
    def _placement(self, width: float, height: float) -> VectorPlacement:
        return VectorPlacement(
            export_page_index=0,
            project_page_id="pdf-page",
            source_pdf="source.pdf",
            source_page_index=0,
            clip=(0.0, 0.0, width, height),
            left=0.0,
            top=0.0,
            width=1598.0,
            height=866.0,
            object_name="managed PDF base",
            coordinate_space="sheet",
            strict_base=True,
        )

    def test_full_sheet_vector_is_contained_without_aspect_distortion(self) -> None:
        document = fitz.open()
        page = document.new_page(width=17 * 72, height=11 * 72)
        try:
            source_clip = fitz.Rect(0, 0, 6 * 72, 4 * 72)
            destination = _destination_rect(
                page,
                self._placement(source_clip.width, source_clip.height),
                source_clip=source_clip,
            )
            self.assertAlmostEqual(source_clip.width / source_clip.height, destination.width / destination.height)
            self.assertAlmostEqual(page.rect.height, destination.height)
            self.assertAlmostEqual((page.rect.width - destination.width) / 2, destination.x0)
            self.assertGreater(destination.x0, 0)
            self.assertEqual(destination, destination & page.rect)
        finally:
            document.close()

    def test_ansi_b_source_uses_the_complete_ansi_b_media_box(self) -> None:
        document = fitz.open()
        page = document.new_page(width=17 * 72, height=11 * 72)
        try:
            source_clip = fitz.Rect(0, 0, 17 * 72, 11 * 72)
            destination = _destination_rect(
                page,
                self._placement(source_clip.width, source_clip.height),
                source_clip=source_clip,
            )
            self.assertAlmostEqual(page.rect.x0, destination.x0)
            self.assertAlmostEqual(page.rect.y0, destination.y0)
            self.assertAlmostEqual(page.rect.x1, destination.x1)
            self.assertAlmostEqual(page.rect.y1, destination.y1)
        finally:
            document.close()


class StandaloneExportAuthorityTests(unittest.TestCase):
    def test_legacy_index_snapshot_cannot_rewrite_saved_standalone_sheet_code(self) -> None:
        project = {
            "id": "standalone-authority",
            "projectMode": "standalone_layout",
            "managedPagePolicy": "preserve_existing",
            "pages": [
                {
                    "id": "index",
                    "order": 1,
                    "include": True,
                    "pageType": "index",
                    "sheetTitle": "Sheet Index",
                    "sheetCode": "EMS 2.0",
                    "linkedWorksheetId": "legacy-index",
                },
                {
                    "id": "drawing",
                    "order": 2,
                    "include": True,
                    "pageType": "canvas",
                    "sheetTab": "DRAWING",
                    "sheetTitle": "Current Drawing",
                    "sheetCode": "CURRENT",
                    "displaySheetCode": "CURRENT",
                },
            ],
            "worksheets": [
                {
                    "id": "legacy-index",
                    "grid": [
                        ["Sheet Tab", "Sheet Title", "Include", "Sheet Code"],
                        ["DRAWING", "Stale Drawing", "YES", "LEGACY"],
                    ],
                }
            ],
        }

        exported = build_selected_export_document(project, None)

        drawing = next(page for page in exported["pages"] if page["id"] == "drawing")
        self.assertEqual("CURRENT", drawing["sheetCode"])
        self.assertEqual("CURRENT", drawing["displaySheetCode"])
        self.assertEqual("CURRENT", project["pages"][1]["sheetCode"])


class VectorPreviewExclusionTests(unittest.TestCase):
    def test_orthogonal_pdf_preview_is_removed_and_vectorized_once(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source_dir = root / "sources" / "pdf"
            source_dir.mkdir(parents=True)
            source_path = source_dir / "source.pdf"
            source = fitz.open()
            page = source.new_page(width=500, height=500)
            page.insert_text((30, 50), "IN CROP", fontsize=18)
            page.insert_text((350, 400), "OUTSIDE CROP", fontsize=18)
            for index in range(300):
                y = 200 + (index % 250)
                page.draw_line((250, y), (490, y), color=(0, 0, 0), width=0.2)
            source.save(source_path)
            source.close()

            project = {
                "pages": [{
                    "id": "rotated",
                    "order": 1,
                    "include": True,
                    "pageType": "canvas",
                    "canvasObjects": [{
                        "type": "image",
                        "src": "/api/assets/project/source-preview-400dpi.png",
                        "pdfSource": "source.pdf",
                        "pdfPage": 0,
                        "pdfDpi": 72,
                        "pdfCrop": "0,0,120,120",
                        "left": 200,
                        "top": 100,
                        "width": 120,
                        "height": 120,
                        "scaleX": 1,
                        "scaleY": 1,
                        "originX": "left",
                        "originY": "top",
                        "angle": 90,
                    }],
                }],
            }
            clone, placements = prepare_vector_export_clone(project, source_pdf_dir=source_dir)
            self.assertEqual(1, len(placements))
            self.assertEqual(90, placements[0].rotation)
            self.assertAlmostEqual(80.0, placements[0].left)
            self.assertAlmostEqual(100.0, placements[0].top)
            self.assertEqual(1, audit_export_preview_exclusion(clone, placements)["excludedPreviewObjects"])

            obj = clone["pages"][0]["canvasObjects"][0]
            self.assertFalse(obj["visible"])
            self.assertTrue(obj["excludeFromExport"])
            self.assertTrue(obj["src"].startswith("data:image/gif"))

            output_path = root / "output.pdf"
            output = fitz.open()
            output.new_page(width=1224, height=792)
            output.save(output_path)
            output.close()
            audit = apply_vector_pdf_underlays(output_path, source_pdf_dir=source_dir, placements=placements)
            self.assertTrue(audit["allVectorBasesInsertedExactlyOnce"])
            self.assertEqual(1, audit["prunedSourceVariants"])
            result = fitz.open(output_path)
            try:
                text = result[0].get_text("text")
                self.assertIn("IN CROP", text)
                self.assertNotIn("OUTSIDE CROP", text)
                self.assertGreaterEqual(len(result[0].get_xobjects()), 1)
            finally:
                result.close()

if __name__ == "__main__":
    unittest.main()
