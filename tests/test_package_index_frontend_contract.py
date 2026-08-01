from __future__ import annotations

from copy import deepcopy
import json
import shutil
import subprocess
from pathlib import Path
import unittest

from core.standalone_project import create_standalone_project, normalize_standalone_project


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "src" / "model" / "packageIndex.ts"
SMOKE = ROOT / "scripts" / "smoke_package_index_client.mjs"
TYPESCRIPT = ROOT / "frontend" / "node_modules" / "typescript" / "lib" / "typescript.js"


class PackageIndexFrontendContractTests(unittest.TestCase):
    def test_source_exposes_recoverable_project_level_normalizer(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("export function normalizePackageManifest(", source)
        self.assertIn("archivedPages: PageModel[]", source)
        self.assertIn("requiredIndexPageCount", source)
        self.assertIn("generatedIndexContinuation: true", source)
        self.assertNotIn("arranged.push({ ...cover, include: true })", source)

    @unittest.skipUnless(shutil.which("node") and TYPESCRIPT.is_file(), "Node/TypeScript frontend dependencies are not installed")
    def test_runtime_sheet_index_contract(self) -> None:
        completed = subprocess.run(
            [shutil.which("node") or "node", str(SMOKE)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stdout)
        self.assertIn("PASS: client Sheet Index pagination, imported page labels", completed.stdout)

    @unittest.skipUnless(shutil.which("node") and TYPESCRIPT.is_file(), "Node/TypeScript frontend dependencies are not installed")
    def test_client_archive_and_revive_match_server_manifest(self) -> None:
        initial = create_standalone_project(
            "client-server-parity",
            {"projectName": "Sanitized Client Server Parity"},
            profile="minimal",
            now="2026-08-01T12:00:00Z",
            rows_per_index_page=3,
        )
        initial["coverSettings"]["include"] = False
        initial["pages"].extend(
            {
                "id": f"drawing-{number}",
                "order": number + 2,
                "include": True,
                "sheetCode": f"D-{number}",
                "displaySheetCode": f"D-{number}",
                "sheetTitle": f"Drawing {number}",
                "sheetTab": f"Drawing {number}",
                "pageType": "canvas",
                "templateId": "ansi-b-standard",
                "blocks": [],
                "canvasObjects": [{"id": f"object-{number}"}],
                "notes": "",
            }
            for number in range(1, 4)
        )
        expanded = normalize_standalone_project(
            initial,
            now="2026-08-01T12:00:00Z",
            rows_per_index_page=3,
        )
        continuation = next(
            page for page in expanded["pages"] if page.get("generatedIndexContinuation")
        )
        continuation["canvasObjects"] = [{"id": "preserved-overlay"}]
        contracted_input = deepcopy(expanded)
        for page in contracted_input["pages"]:
            if page["id"] in {"drawing-2", "drawing-3"}:
                page["include"] = False

        timestamp = "2026-08-01T12:01:00Z"
        server = normalize_standalone_project(
            contracted_input,
            now=timestamp,
            rows_per_index_page=3,
        )
        client = self._normalize_in_node(contracted_input, timestamp, 3)
        self.assertEqual(self._comparable_pages(server["pages"]), self._comparable_pages(client["pages"]))
        self.assertEqual(server["archivedPages"], client["archivedPages"])

        reexpanded_input = deepcopy(server)
        for page in reexpanded_input["pages"]:
            if page["id"] in {"drawing-2", "drawing-3"}:
                page["include"] = True
        timestamp = "2026-08-01T12:02:00Z"
        server = normalize_standalone_project(
            reexpanded_input,
            now=timestamp,
            rows_per_index_page=3,
        )
        client = self._normalize_in_node(reexpanded_input, timestamp, 3)
        self.assertEqual(self._comparable_pages(server["pages"]), self._comparable_pages(client["pages"]))
        self.assertEqual(server["archivedPages"], client["archivedPages"])

    @staticmethod
    def _comparable_pages(pages: list[dict]) -> list[dict]:
        comparable = deepcopy(pages)
        for page in comparable:
            # The Python JSON sanitizer represents an excluded page number as
            # an empty string; the typed browser model uses null.
            if page.get("pageNumber") in {"", None}:
                page["pageNumber"] = None
        return comparable

    def _normalize_in_node(self, project: dict, timestamp: str, rows_per_page: int) -> dict:
        completed = subprocess.run(
            [shutil.which("node") or "node", str(SMOKE), "--normalize-stdin"],
            cwd=ROOT,
            input=json.dumps(
                {
                    "pages": project["pages"],
                    "archivedPages": project["archivedPages"],
                    "options": {
                        "now": timestamp,
                        "indexRowsPerPage": rows_per_page,
                        "coverIncluded": project["coverSettings"]["include"],
                        "automaticManagedPages": project.get("managedPagePolicy") == "automatic",
                    },
                }
            ),
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        return json.loads(completed.stdout)


if __name__ == "__main__":
    unittest.main()
