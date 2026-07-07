"""Smoke: table cell highlights persist through save/reload/export.

Uses the Flask test client with a synthetic project (no customer files).
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
        "id": "4b4b4b4b4b4b4b4b",
        "metadata": {"projectName": "4B Highlight Smoke"},
        "worksheets": [],
        "sources": [],
        "assets": [],
        "pages": [{
            "id": "p_io",
            "order": 1,
            "include": True,
            "sheetCode": "EMS 5.0",
            "displaySheetCode": "EMS 5.0",
            "sheetTitle": "Controller I/O",
            "sheetTab": "",
            "pageType": "data-grid",
            "template": "Table / Schedule",
            "templateId": "",
            "notes": "",
            "canvasObjects": [],
            "blocks": [{
                "id": "b_io",
                "type": "table",
                "headers": ["RO#", "Relay Output Description", "Type"],
                "rows": [["R1", "Compressor 1", "DO"], ["R2", "Condenser Fan", "DO"]],
                "cellFills": {"-1:0": "#D9D9D9", "0:1": "#FFF2A8"},
            }],
        }],
    }


def main() -> int:
    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402

    client = server.app.test_client()
    pid = "4b4b4b4b4b4b4b4b"
    problems: list[str] = []

    if client.post(f"/api/projects/{pid}", json=_project()).status_code != 200:
        print("create failed")
        return 1

    # Reload and confirm original fills survived.
    doc = client.get(f"/api/projects/{pid}").get_json()
    fills = doc["pages"][0]["blocks"][0].get("cellFills", {})
    if fills.get("-1:0") != "#D9D9D9" or fills.get("0:1") != "#FFF2A8":
        problems.append(f"initial cellFills not persisted: {fills}")

    # Add a highlight (green done) + clear one, save, reload.
    doc["pages"][0]["blocks"][0]["cellFills"] = {"0:2": "#C6E7C6"}
    if client.post(f"/api/projects/{pid}", json=doc).status_code != 200:
        problems.append("second save failed")
    doc2 = client.get(f"/api/projects/{pid}").get_json()
    fills2 = doc2["pages"][0]["blocks"][0].get("cellFills", {})
    if fills2.get("0:2") != "#C6E7C6" or "0:1" in fills2:
        problems.append(f"edited cellFills not persisted/cleared: {fills2}")

    # Export package must include cellFills in project.json.
    pkg = client.post(f"/api/projects/{pid}/export/package")
    if pkg.status_code != 200:
        problems.append("package export failed")
    else:
        zf = zipfile.ZipFile(io.BytesIO(pkg.get_data()))
        exported = json.loads(zf.read("project.json"))
        ef = exported["pages"][0]["blocks"][0].get("cellFills", {})
        if ef.get("0:2") != "#C6E7C6":
            problems.append("export package missed cell highlight")

    print(f"reloadFills={fills} editedFills={fills2}")
    client.delete(f"/api/projects/{pid}")
    if problems:
        print("TABLE HIGHLIGHT EDITING PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: table highlight editing smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
