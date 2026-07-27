"""Smoke: normalized table row/column/cell edits persist with a recoverable backup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _project() -> dict:
    return {
        "id": "3f3f3f3f3f3f3f40",
        "metadata": {"projectName": "3F Table Smoke"},
        "worksheets": [],
        "sources": [],
        "assets": [],
        "pages": [{
            "id": "p_table",
            "order": 1,
            "include": True,
            "sheetCode": "BOM",
            "displaySheetCode": "BOM",
            "sheetTitle": "Bill of Materials",
            "sheetTab": "",
            "pageType": "data-grid",
            "template": "Bill of Materials",
            "templateId": "",
            "notes": "",
            "canvasObjects": [],
            "blocks": [{"id": "b_bom", "type": "table", "headers": ["Part", "Qty"], "rows": [["A", "1"], ["B", "2"]]}],
        }],
    }


def main() -> int:
    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402
    from tests.generated_fixtures import isolate_server_runtime

    runtime = isolate_server_runtime(server)
    client = server.app.test_client()
    pid = "3f3f3f3f3f3f3f40"
    problems: list[str] = []

    if client.post(f"/api/projects/{pid}", json=_project()).status_code != 200:
        print("create failed")
        return 1
    proj = client.get(f"/api/projects/{pid}").get_json()
    block = proj["pages"][0]["blocks"][0]

    # Simulate: edit BOM cell, add row below, duplicate row, delete row, add/clear column.
    block["rows"][0][0] = "Edited Part"
    block["rows"].insert(1, ["Added", "3"])
    block["rows"].insert(2, list(block["rows"][1]))
    block["rows"].pop(3)  # delete original B row
    block["headers"].insert(1, "Manufacturer")
    block["rows"] = [[row[0], "Singh360", row[1]] for row in block["rows"]]
    block["rows"][0][1] = ""  # clear cell

    res = client.post(f"/api/projects/{pid}", json=proj)
    if res.status_code != 200:
        problems.append(f"save failed {res.status_code}")
    reloaded = client.get(f"/api/projects/{pid}").get_json()
    rb = reloaded["pages"][0]["blocks"][0]
    if rb["rows"][0][0] != "Edited Part":
        problems.append("cell edit did not persist")
    if rb["headers"] != ["Part", "Manufacturer", "Qty"]:
        problems.append(f"column add failed: {rb['headers']}")
    if len(rb["rows"]) != 3:
        problems.append(f"row add/duplicate/delete failed: {len(rb['rows'])}")
    if rb["rows"][0][1] != "":
        problems.append("clear cell failed")

    backups = client.get(f"/api/projects/{pid}/backups").get_json().get("backups", [])
    if not backups:
        problems.append("recoverable project backup missing")
    print(f"rows={len(rb['rows'])} cols={len(rb['headers'])} backups={len(backups)}")

    client.delete(f"/api/projects/{pid}?confirm=true")
    runtime.cleanup()
    if problems:
        print("TABLE EDITING PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: table editing smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
