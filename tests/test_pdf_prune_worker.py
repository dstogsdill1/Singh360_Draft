from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz
import pikepdf

from core.pdf_prune_worker import _deduplicate_redundant_strokes


class PdfPruneWorkerTests(unittest.TestCase):
    def test_exact_repeat_strokes_are_removed_without_removing_text_or_distinct_lines(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.pdf"
            filtered = root / "filtered.pdf"
            document = fitz.open()
            document.new_page(width=200, height=100)
            document.save(source)
            document.close()
            with pikepdf.Pdf.open(source, allow_overwriting_input=True) as pdf:
                pdf.pages[0].Contents = pdf.make_stream(
                    b"BT /F1 10 Tf (VECTOR TEXT) Tj ET\n"
                    b"0 0 m 10 0 l S\n"
                    b"0 0 m 10 0 l S\n"
                    b"0 0 m 10 0 l S\n"
                    b"0 1 m 10 1 l S\n"
                )
                pdf.save(source)

            audit = _deduplicate_redundant_strokes(source, 0, filtered)

            self.assertEqual(2, audit["deduplicatedVectorStrokes"])
            self.assertEqual(2, audit["uniqueStrokeSignatures"])
            with pikepdf.Pdf.open(filtered) as pdf:
                operations = pikepdf.parse_content_stream(pdf.pages[0])
            self.assertEqual(2, sum(str(item.operator) == "S" for item in operations))
            self.assertTrue(any(str(item.operator) == "Tj" for item in operations))


if __name__ == "__main__":
    unittest.main()
