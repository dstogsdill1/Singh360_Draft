from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PdfFrontendContractTests(unittest.TestCase):
    def test_replacement_mapping_uses_the_required_deterministic_pass_order(self) -> None:
        modal = (ROOT / "frontend" / "src" / "components" / "AddImportPageModal.tsx").read_text(
            encoding="utf-8"
        )
        fingerprint_pass = modal.index("// Pass 1: unchanged pages")
        source_index_pass = modal.index("// Pass 2: revised content")
        remaining_pass = modal.index("// Pass 3: pair the remaining pages")
        self.assertLess(fingerprint_pass, source_index_pass)
        self.assertLess(source_index_pass, remaining_pass)
        self.assertIn("group.pageFingerprints", modal)
        self.assertIn("group.pageIndices", modal)
        self.assertNotIn("Replace Existing Pages requires exactly", modal)
        self.assertIn("Math.min(remainingPages.length, remainingPositions.length)", modal)
        self.assertIn("unmatched existing page", modal)
        self.assertIn("will not be imported; choose Add as New Pages", modal)
        self.assertIn("new Set(mapping.map((item) => item.pageIndex)).size", modal)
        self.assertIn("pdfImportRequestSelection(action, selectedPages, mapping)", modal)
        self.assertIn("selectedPages: requestPages", modal)

        selection = (ROOT / "frontend" / "src" / "model" / "pdfImportSelection.ts").read_text(
            encoding="utf-8"
        )
        smoke = (ROOT / "scripts" / "smoke_async_project_merge.mjs").read_text(encoding="utf-8")
        self.assertIn("return (mapping ?? []).map((item) => item.pageIndex)", selection)
        self.assertIn("pdfImportRequestSelection('replace', [0, 1, 2]", smoke)
        self.assertIn("pdfImportRequestSelection('add', [0, 1, 2]", smoke)

    def test_renamed_revisions_can_choose_any_existing_pdf_group(self) -> None:
        modal = (ROOT / "frontend" / "src" / "components" / "AddImportPageModal.tsx").read_text(
            encoding="utf-8"
        )
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        self.assertIn("next.existingGroups.find((item) => item.sameName) ?? next.existingGroups[0]", modal)
        self.assertIn("preview.existingGroups.map((group)", modal)
        self.assertIn("pageFingerprints: string[]", client)
        self.assertIn("sameName: boolean", client)

    def test_pdf_import_uses_observable_page_counted_background_progress(self) -> None:
        modal = (ROOT / "frontend" / "src" / "components" / "AddImportPageModal.tsx").read_text(
            encoding="utf-8"
        )
        client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
        server = (ROOT / "server.py").read_text(encoding="utf-8")
        core = (ROOT / "core" / "pdf_page_import.py").read_text(encoding="utf-8")

        self.assertIn("background: true", client)
        self.assertIn("/pdf/import-jobs/${started.jobId}", client)
        self.assertIn("onProgress?.(job.progress)", client)
        self.assertIn("throw new Singh360ApiError", client)
        self.assertIn('<progress max={progress.total} value={progress.completed}', modal)
        self.assertIn("{progress.completed} of {progress.total} pages", modal)
        self.assertIn("data-phase={progress.phase}", modal)
        self.assertIn("PDF page: ${pageIndex + 1}", modal)
        self.assertIn("Error code: ${code}", modal)
        for phase in ("validate", "render", "install", "compose", "save", "complete"):
            self.assertIn(f'phase="{phase}"', core)
        self.assertIn("def pdf_import_job_status", server)
        self.assertIn('job["error"] = exc.to_dict()', server)


if __name__ == "__main__":
    unittest.main()
