from __future__ import annotations

import unittest

import fitz

from core.vector_pdf_export import (
    VectorPlacement,
    _destination_rect,
    build_selected_export_document,
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

if __name__ == "__main__":
    unittest.main()
