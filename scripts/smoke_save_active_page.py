"""Smoke: active page save persists objects, connectors, table edits, backups, snapshots.

Uses Flask test client and a synthetic project so no customer workbook is needed.
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _project() -> dict:
    return {
        "id": "3f3f3f3f3f3f3f3f",
        "metadata": {"projectName": "3F Save Smoke", "sourceFile": "synthetic.xlsx"},
        "worksheets": [],
        "sources": [],
        "assets": [],
        "pages": [
            {
                "id": "p_save_a",
                "order": 1,
                "include": True,
                "sheetCode": "EMS 1.0",
                "displaySheetCode": "EMS 1.0",
                "sheetTitle": "Active Page",
                "sheetTab": "",
                "pageType": "data-grid",
                "template": "Table / Schedule",
                "templateId": "",
                "notes": "edited note",
                "blocks": [{"id": "b_table", "type": "table", "headers": ["Device", "Qty"], "rows": [["Panel", "1"], ["Sensor", "2"]]}],
                "canvasObjects": [
                    {"type": "rect", "left": 10, "top": 20, "width": 30, "height": 40, "objName": "Component A"},
                    {"type": "textbox", "left": 80, "top": 20, "text": "Label", "objName": "Inserted Label"},
                    {"type": "Connector", "connectorKind": "line", "pointsData": [{"x": 10, "y": 10}, {"x": 120, "y": 10}], "stroke": "#111", "strokeWidth": 2, "objName": "Line 1"},
                    {"type": "Connector", "connectorKind": "arrow", "pointsData": [{"x": 10, "y": 40}, {"x": 120, "y": 40}], "stroke": "#111", "strokeWidth": 2, "arrowEnd": True, "objName": "Line 2"},
                    {"type": "Connector", "connectorKind": "polyline", "pointsData": [{"x": 10, "y": 70}, {"x": 80, "y": 90}, {"x": 120, "y": 70}], "stroke": "#111", "strokeWidth": 2, "objName": "Line 3"},
                ],
            },
            {
                "id": "p_save_b",
                "order": 2,
                "include": True,
                "sheetCode": "EMS 2.0",
                "displaySheetCode": "EMS 2.0",
                "sheetTitle": "Other Page",
                "sheetTab": "",
                "pageType": "canvas",
                "templateId": "",
                "notes": "",
                "blocks": [],
                "canvasObjects": [],
            },
        ],
    }


def main() -> int:
    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402

    client = server.app.test_client()
    pid = "3f3f3f3f3f3f3f3f"
    problems: list[str] = []

    res = client.post(f"/api/projects/{pid}", json=_project())
    if res.status_code != 200:
        print(res.get_data(as_text=True))
        return 1

    # Second save forces a project backup and another page snapshot.
    proj = client.get(f"/api/projects/{pid}").get_json()
    proj["pages"][0]["blocks"][0]["rows"][0][1] = "99"
    proj["pages"][0]["canvasObjects"].append({"type": "circle", "left": 140, "top": 140, "radius": 20, "objName": "Component B"})
    res = client.post(f"/api/projects/{pid}", json=proj)
    if res.status_code != 200:
        problems.append(f"save failed {res.status_code}")

    reloaded = client.get(f"/api/projects/{pid}").get_json()
    page = reloaded["pages"][0]
    objs = page.get("canvasObjects", [])
    conns = [o for o in objs if o.get("type") == "Connector"]
    if len(objs) != 6:
        problems.append(f"expected 6 canvas objects after reload, got {len(objs)}")
    if len(conns) != 3:
        problems.append(f"expected 3 connectors after reload, got {len(conns)}")
    if page["blocks"][0]["rows"][0][1] != "99":
        problems.append("table edit did not persist")
    if reloaded["pages"][1].get("canvasObjects"):
        problems.append("page switch isolation failed: objects leaked to page 2")

    backups = client.get(f"/api/projects/{pid}/backups").get_json().get("backups", [])
    snaps = client.get(f"/api/projects/{pid}/page-snapshots").get_json().get("snapshots", [])
    print(f"objects={len(objs)} connectors={len(conns)} backups={len(backups)} pageSnapshots={len(snaps)}")
    if not backups:
        problems.append("project backup missing")
    if not any(s.get("pageId") == "p_save_a" and s.get("counts", {}).get("tableBlocks") == 1 for s in snaps):
        problems.append("page snapshot/count metadata missing")

    pkg = client.post(f"/api/projects/{pid}/export/package")
    if pkg.status_code != 200:
        problems.append(f"package export failed {pkg.status_code}")
    else:
        zf = zipfile.ZipFile(io.BytesIO(pkg.get_data()))
        exported = json.loads(zf.read("project.json"))
        if exported["pages"][0]["blocks"][0]["rows"][0][1] != "99":
            problems.append("export package missed latest table edit")

    client.delete(f"/api/projects/{pid}")
    if problems:
        print("ACTIVE PAGE SAVE PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: active page save smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
