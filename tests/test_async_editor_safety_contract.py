from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AsyncEditorSafetyContractTests(unittest.TestCase):
    def test_async_mutations_are_gated_reconciled_and_resaved(self) -> None:
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        modal = (ROOT / "frontend/src/components/AddImportPageModal.tsx").read_text(
            encoding="utf-8"
        )
        settings = (ROOT / "frontend/src/components/ProjectSettingsModal.tsx").read_text(
            encoding="utf-8"
        )
        warnings = (ROOT / "frontend/src/components/ExportWarningsModal.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("rawNext.projectMode === 'standalone_layout'", app)
        self.assertIn("rawNext.managedPagePolicy === 'automatic'", app)
        self.assertIn("reconcilePdfImportResult(latest, imported, pageIds)", app)
        self.assertIn("reconcileLayoutRebuildResult(", app)
        self.assertIn("layoutRebuildBusyRef.current = true", app)
        self.assertIn("const openProjectSettings = async ()", app)
        self.assertIn("const saved = await ensureSavedBeforeNavigation();", app)
        self.assertIn("setProjectSync((latest) =>", app)
        self.assertIn("if (!await captureAndSave()) return;", app)
        self.assertIn("await fetchExportWarnings(latest.id, pending.pageIds)", app)
        self.assertNotIn("let proj = project;", app)
        self.assertIn("revisionHistory: [...(latest.revisionHistory ?? [])", app)

        self.assertIn("onProjectImported: (project: ProjectModel, pageIds: string[]) => Promise<boolean>", modal)
        self.assertIn("const saved = await onProjectImported(", modal)
        save_progress = "await showProgressAfterPaint({\n        phase: 'save'"
        complete_progress = "await showProgressAfterPaint({\n        phase: 'complete'"
        self.assertIn(save_progress, modal)
        self.assertIn(complete_progress, modal)
        self.assertLess(modal.index(save_progress), modal.index("const saved = await onProjectImported("))
        self.assertLess(modal.index("const saved = await onProjectImported("), modal.index(complete_progress))
        self.assertLess(modal.index(complete_progress), modal.index("closeAfterComplete = true;"))
        self.assertIn("await waitForBrowserPaint();", modal)
        self.assertNotIn("setPdfCropOpen(false);\n            return true;", app)
        self.assertIn('disabled={busy}>×</button>', modal)
        self.assertIn("setPdfCommitted(true)", modal)
        self.assertIn("onImage: (file: File) => Promise<boolean>", modal)
        self.assertIn("const imported = await onImage(file)", modal)

        self.assertIn("onSave: (update: ProjectSettingsUpdate) => Promise<boolean>", settings)
        self.assertNotIn("onSave({\n        ...project,", settings)
        self.assertIn("disabled={saving}>×</button>", settings)
        self.assertIn("onExportAnyway: () => Promise<void>", warnings)
        self.assertIn("Saving and Rechecking…", warnings)

    @unittest.skipUnless(
        shutil.which("node")
        and (ROOT / "frontend/node_modules/typescript/lib/typescript.js").is_file(),
        "Node/TypeScript frontend dependencies are not installed",
    )
    def test_runtime_async_merge_contract(self) -> None:
        completed = subprocess.run(
            [shutil.which("node") or "node", str(ROOT / "scripts/smoke_async_project_merge.mjs")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("PASS: delayed PDF imports and layout rebuilds", completed.stdout)

    def test_archive_navigation_keeps_the_pre_archive_active_page_identity(self) -> None:
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        delete_page = app[app.index("const deletePage = async"):app.index("const restoreArchivedPage = async")]

        captured = "const activePageIdBeforeArchive = activePageRef.current?.id ?? null;"
        archive_update = "const normalizedArchivedProject = setProjectSync(archivedProject)"
        saved = "const saved = await confirmLatestProjectSaved(15_000);"
        selection = "if (activePageIdBeforeArchive && groupIds.has(activePageIdBeforeArchive))"

        self.assertIn(captured, delete_page)
        self.assertLess(delete_page.index(captured), delete_page.index(archive_update))
        self.assertLess(delete_page.index(saved), delete_page.index(selection))
        self.assertNotIn(
            "if (activePageRef.current?.id && groupIds.has(activePageRef.current.id))",
            delete_page,
        )


if __name__ == "__main__":
    unittest.main()
