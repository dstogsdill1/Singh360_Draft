"""Smoke: Import Worksheet replace mode updates current page, no duplicate tab."""
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
    ws.append(["Executive Summary", "Replace smoke marker"])
    wb.save(path)


def main() -> int:
    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402
    from core.sheet_importer import import_workbook_sheets
    from tests.generated_fixtures import isolate_server_runtime

    runtime = isolate_server_runtime(server)
    client = server.app.test_client()
    pid = "a1a1a1a1a1a1a1a1"
    page_id = "page_scope"
    ws_old = "ws_old"
    proj = {
        "id": pid,
        "metadata": {"projectName": "Replace Smoke"},
        "worksheets": [{
            "id": ws_old,
            "name": "Old Scope",
            "grid": [["Section", "Scope Language"], ["Old", "Stale text"]],
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
            "linkedWorksheetId": ws_old,
            "blocks": [{"id": "b1", "type": "table", "headers": ["Section"], "rows": [["Old"]]}],
            "canvasObjects": [],
        }],
    }
    problems: list[str] = []

    res = client.post(f"/api/projects/{pid}", json=proj)
    if res.status_code != 200:
        print(res.get_data(as_text=True))
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        xlsx = Path(tmp) / "scope.xlsx"
        _workbook(xlsx)
        doc = client.get(f"/api/projects/{pid}").get_json()
        before_count = len(doc["pages"])
        before_ids = {p["id"] for p in doc["pages"]}

        doc2, updated = import_workbook_sheets(
            doc,
            xlsx,
            ["EMS 0.4 Scope"],
            replace_page_id=page_id,
            source_filename="scope.xlsx",
        )
        client.post(f"/api/projects/{pid}", json=doc2)
        reloaded = client.get(f"/api/projects/{pid}").get_json()

    if len(reloaded["pages"]) != before_count:
        problems.append(f"page count changed {before_count} -> {len(reloaded['pages'])}")
    if {p["id"] for p in reloaded["pages"]} != before_ids:
        problems.append("page ids changed after replace import")
    page = next(p for p in reloaded["pages"] if p["id"] == page_id)
    if page.get("sheetCode") != "5.0":
        problems.append(f"sheetCode changed to {page.get('sheetCode')!r}")
    if page.get("sheetTitle") != "Project Scope":
        problems.append(f"sheetTitle changed to {page.get('sheetTitle')!r}")
    if page.get("linkedWorksheetId") == ws_old:
        problems.append("linkedWorksheetId not updated")
    block_text = str(page.get("blocks"))
    if "Replace smoke marker" not in block_text:
        problems.append("replaced blocks missing imported source text")
    if any(p.get("sheetCode") == "NEW" for p in reloaded["pages"]):
        problems.append("duplicate NEW page appeared")

    client.delete(f"/api/projects/{pid}?confirm=true")
    runtime.cleanup()

    if problems:
        print("FAIL — import replace current page")
        for p in problems:
            print(" -", p)
        return 1

    print("OK — import replace current page source")
    print(f"  pageId={page_id} pages={len(reloaded['pages'])} ws={page.get('linkedWorksheetId')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
