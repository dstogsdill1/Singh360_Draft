"""scripts/smoke_sheet_import.py — verify single worksheet import into an existing project.

Flow tested:
  1. Create a sanitized in-memory project with at least one page.
  2. Build a minimal sanitized XLSX in a temp directory using openpyxl.
  3. Preview workbook sheets (no project mutation).
  4. Import one sheet after the first page.
  5. Verify:
     - page count increases by 1
     - new page has importedFrom provenance
     - new page has a unique id not in the old page list
     - project.renumberSuggested is True
     - importHistory is recorded
     - save + reload preserves the imported page
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_synthetic_workbook(path: Path) -> None:
    try:
        from openpyxl import Workbook
    except ImportError:
        raise RuntimeError("openpyxl not installed — run: pip install openpyxl")
    wb = Workbook()
    ws = wb.active
    ws.title = "Equipment Schedule"
    ws.append(["Tag", "Description", "Qty"])
    ws.append(["PR-01", "Pressure Regulator", "2"])
    ws.append(["TC-01", "Temperature Controller", "4"])
    wb2 = wb.create_sheet("BACnet Points")
    wb2.append(["Object Name", "Object Type", "Present Value"])
    wb2.append(["AI-001", "AI", "72.3"])
    wb.save(path)


def main() -> int:
    problems: list[str] = []

    import server
    from core.sheet_importer import preview_workbook_sheets, import_workbook_sheets

    c = server.app.test_client()

    # --- 1. Create a minimal project ---
    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "sanitized.xlsx"
        _make_synthetic_workbook(xlsx)
        source_name = xlsx.name

        # Create a project with a CSV upload.
        pid = "b0b0b0b0b0b00001"
        proj = {
            "id": pid,
            "pages": [{"id": "page_001", "sheetTitle": "Original", "sheetCode": "1.0",
                        "displaySheetCode": "1.0", "sheetTab": "", "pageType": "data-grid",
                        "order": 1, "include": True, "blocks": [], "canvasObjects": [],
                        "notes": "", "revisionRows": [], "pageGroupId": "pg_001",
                        "continuationOf": None, "continuationIndex": 0,
                        "generatedContinuation": False, "layoutWarnings": []}],
            "worksheets": [],
            "sources": [],
            "metadata": {"projectName": "Import Test"},
            "projectDisplayName": "Import Test",
        }
        save = c.post(f"/api/projects/{pid}", json=proj)
        if save.status_code != 200:
            problems.append(f"project save failed ({save.status_code})")
            return _report(problems)

        # --- 2. Preview ---
        prev = preview_workbook_sheets(xlsx)
        if not prev:
            problems.append("preview returned no sheets")
            return _report(problems)
        first_sheet = prev[0]["sheetName"]
        print(f"preview: {[s['sheetName'] for s in prev]}")

        # --- 3. Import one sheet ---
        doc_before = c.get(f"/api/projects/{pid}").get_json()
        old_ids = {p["id"] for p in doc_before.get("pages", [])}
        old_count = len(doc_before.get("pages", []))

        doc_before_raw, _ = import_workbook_sheets(
            doc_before,
            xlsx,
            [first_sheet],
            insert_after_page_id="page_001",
            source_filename=source_name,
        )
        save2 = c.post(f"/api/projects/{pid}", json=doc_before_raw)
        if save2.status_code != 200:
            problems.append(f"save after import failed ({save2.status_code})")
            return _report(problems)

        # --- 4. Verify ---
        doc_after = c.get(f"/api/projects/{pid}").get_json()
        new_pages = doc_after.get("pages", [])
        if len(new_pages) != old_count + 1:
            problems.append(f"page count after import: {len(new_pages)} (expected {old_count + 1})")

        new_page = next((p for p in new_pages if p["id"] not in old_ids), None)
        if not new_page:
            problems.append("imported page not found in reloaded project")
        else:
            if not new_page.get("importedFrom"):
                problems.append("imported page missing importedFrom provenance")
            if new_page.get("sheetTitle") != first_sheet:
                problems.append(f"imported sheetTitle mismatch: {new_page.get('sheetTitle')} vs {first_sheet}")

        if not doc_before_raw.get("renumberSuggested"):
            problems.append("renumberSuggested should be True after import")

        hist = doc_before_raw.get("importHistory", [])
        if not hist:
            problems.append("importHistory not recorded")
        elif hist[-1].get("sheetNames") != [first_sheet]:
            problems.append("importHistory sheet name mismatch")

        # Existing original page must be preserved.
        if not any(p["id"] == "page_001" for p in new_pages):
            problems.append("original page_001 was removed (should not have happened)")

        print(f"pages: {old_count} -> {len(new_pages)} | imported: {new_page['id'] if new_page else 'MISSING'}")

        # --- Cleanup ---
        c.delete(f"/api/projects/{pid}")

    return _report(problems)


def _report(problems: list[str]) -> int:
    if problems:
        print("SHEET IMPORT PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: sheet import checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
