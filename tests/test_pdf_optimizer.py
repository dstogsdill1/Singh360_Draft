from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from core.pdf_optimizer import analyze_pdf, optimize_pdf_atomic


class PdfOptimizerTests(unittest.TestCase):
    def _source(self, path: Path) -> None:
        document = fitz.open()
        for index in range(3):
            page = document.new_page(width=1224, height=792)
            page.insert_text((60, 80), f"PAGE {index + 1}", fontsize=22)
            for offset in range(100):
                page.draw_line((60, 120 + offset), (1160, 120 + offset), width=0.2)
        document.save(path)
        document.close()

    def test_optimized_pdf_is_linearized_reopened_and_diagnosed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.pdf"
            final = root / "final.pdf"
            self._source(source)

            result = optimize_pdf_atomic(source, final, expected_page_count=3, render_dpi=72)

            self.assertTrue(final.is_file())
            self.assertTrue(result["publishedAtomically"])
            self.assertTrue(result["linearized"])
            self.assertEqual(3, result["pageCount"])
            self.assertEqual(3, len(result["pages"]))
            self.assertGreater(result["totalBytes"], 0)
            self.assertFalse(list(root.glob("*.optimizing.pdf")))
            reopened = analyze_pdf(final, render_dpi=72)
            self.assertTrue(reopened["linearized"])
            self.assertEqual(3, reopened["pageCount"])

    def test_failure_never_replaces_existing_final_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.pdf"
            final = root / "final.pdf"
            self._source(source)
            final.write_bytes(b"previous-good-export")

            with self.assertRaisesRegex(RuntimeError, "page count mismatch"):
                optimize_pdf_atomic(source, final, expected_page_count=4, render_dpi=72)

            self.assertEqual(b"previous-good-export", final.read_bytes())
            self.assertFalse(list(root.glob("*.optimizing.pdf")))


if __name__ == "__main__":
    unittest.main()
