"""Smoke: source→normalized workflow must not create duplicate output pages."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _workbook(path: Path) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "EMS 0.4 Scope"
    ws.append(["Section", "Scope Language"])
    ws.append(["Executive Summary", "No duplicate smoke"])
    wb.save(path)


def main() -> int:
    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402
    from core.sheet_importer import import_workbook_sheets

    client = server.app.test_client()
    pid = "b2b2b2b2b2b2b2b2"
    page_id = "page_scope"
    problems: list[str] = []

    proj = {
        "id": pid,
        "metadata": {"projectName": "No Dup Smoke"},
        "worksheets": [{
            "id": "ws_scope",
            "name": "EMS 0.4 Scope",
            "grid": [["Section", "Scope Language"], ["Executive Summary", "Before edit"]],
            "styles": {},
        }],
        "pages": [{
            "id": page_id,
            "order": 1,
            "include": True,
            "sheetCode": "5.0",
            "displaySheetCode": "5.0",
            "sheetTitle": "Project Scope",
            "sheetTab": "EMS 0.4 Scope",
            "pageType": "data-grid",
            "linkedWorksheetId": "ws_scope",
            "blocks": [{"id": "b1", "type": "table", "headers": ["Section"], "rows": [["Executive Summary"]]}],
        }],
    }
    client.post(f"/api/projects/{pid}", json=proj)
    doc = client.get(f"/api/projects/{pid}").get_json()
    initial_count = len(doc["pages"])
    initial_new = sum(1 for p in doc["pages"] if str(p.get("sheetCode", "")).startswith("NEW"))

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "scope.xlsx"
        _workbook(xlsx)
        # Replace (simulates user on Project Scope → Import → Replace current page source)
        doc2, _ = import_workbook_sheets(doc, xlsx, ["EMS 0.4 Scope"], replace_page_id=page_id)
        client.post(f"/api/projects/{pid}", json=doc2)
        after = client.get(f"/api/projects/{pid}").get_json()

    if len(after["pages"]) != initial_count:
        problems.append(f"page count {initial_count} -> {len(after['pages'])}")
    new_pages = [p for p in after["pages"] if str(p.get("sheetCode", "")).startswith("NEW")]
    if len(new_pages) > initial_new:
        problems.append(f"NEW duplicate page(s): {[p.get('sheetTitle') for p in new_pages]}")
    scope_pages = [p for p in after["pages"] if "Scope" in (p.get("sheetTitle") or "")]
    if len(scope_pages) != 1:
        problems.append(f"expected 1 Project Scope page, found {len(scope_pages)}")

    client.delete(f"/api/projects/{pid}")

    if problems:
        print("FAIL — source to normalized no duplicate")
        for p in problems:
            print(" -", p)
        return 1

    print("OK — source/normalized replace creates no duplicate page")
    print(f"  pages={len(after['pages'])} scopePages={len(scope_pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
