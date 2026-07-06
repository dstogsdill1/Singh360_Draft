"""Smoke: selection-related persisted data for locks, groups, duplicates, connectors."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCK = {"lockMovementX": True, "lockMovementY": True, "lockScalingX": True, "lockScalingY": True, "lockRotation": True, "editable": False}


def _project() -> dict:
    return {
        "id": "3f3f3f3f3f3f3f41",
        "metadata": {"projectName": "3F Selection Smoke"},
        "worksheets": [],
        "sources": [],
        "assets": [],
        "pages": [{
            "id": "p_select",
            "order": 1,
            "include": True,
            "sheetCode": "EMS SEL",
            "displaySheetCode": "EMS SEL",
            "sheetTitle": "Selection",
            "sheetTab": "",
            "pageType": "canvas",
            "templateId": "",
            "notes": "",
            "blocks": [],
            "canvasObjects": [
                {"type": "rect", "left": 10, "top": 10, "width": 40, "height": 30, "objName": "Unlocked A"},
                {"type": "rect", "left": 70, "top": 10, "width": 40, "height": 30, "objName": "Unlocked B"},
                {"type": "image", "left": 130, "top": 10, "src": "/api/assets/fake.png", "objName": "Locked Underlay", **LOCK},
                {"type": "group", "left": 200, "top": 20, "objName": "Grouped Copy", "objects": [
                    {"type": "rect", "left": -20, "top": -10, "width": 20, "height": 20, "objName": "Group Member 1"},
                    {"type": "textbox", "left": 10, "top": -10, "text": "G", "objName": "Group Member 2"},
                ]},
                {"type": "Connector", "connectorKind": "polyline", "pointsData": [{"x": 10, "y": 100}, {"x": 80, "y": 130}, {"x": 160, "y": 100}], "stroke": "#12539b", "strokeWidth": 4, "stylePreset": "bacnet", "labelMiddle": "MS/TP", "objName": "Selected Connector"},
            ],
        }],
    }


def main() -> int:
    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402

    client = server.app.test_client()
    pid = "3f3f3f3f3f3f3f41"
    problems: list[str] = []

    res = client.post(f"/api/projects/{pid}", json=_project())
    if res.status_code != 200:
        print(res.get_data(as_text=True))
        return 1
    reloaded = client.get(f"/api/projects/{pid}").get_json()
    objs = reloaded["pages"][0]["canvasObjects"]
    by_name = {o.get("objName"): o for o in objs}

    locked = by_name.get("Locked Underlay", {})
    if not locked.get("lockMovementX") or locked.get("editable") is not False:
        problems.append("lock state did not persist")
    grp = by_name.get("Grouped Copy", {})
    if grp.get("type") != "group" or len(grp.get("objects", [])) != 2:
        problems.append("group state/member count did not persist")
    conn = by_name.get("Selected Connector", {})
    if conn.get("connectorKind") != "polyline" or len(conn.get("pointsData", [])) != 3:
        problems.append("connector route did not persist")
    if conn.get("strokeWidth") != 4 or conn.get("labelMiddle") != "MS/TP":
        problems.append("connector property edit did not persist")

    snaps = client.get(f"/api/projects/{pid}/page-snapshots").get_json().get("snapshots", [])
    if not snaps or snaps[0].get("counts", {}).get("connectors") != 1:
        problems.append("selection page snapshot connector count missing")
    print(f"objects={len(objs)} groups={sum(1 for o in objs if o.get('type') == 'group')} snapshots={len(snaps)}")

    client.delete(f"/api/projects/{pid}")
    if problems:
        print("SELECTION EDITING PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: selection editing smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
