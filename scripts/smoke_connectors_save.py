"""scripts/smoke_connectors_save.py — connector persistence and save-reliability smoke.

Verifies that canvasObjects survive:
  1.  explicit save → reload
  2.  duplicate connector persists
  3.  page-level objects don't leak cross-page
  4.  server backup created after write
  5.  backup can be listed and restored

Uses the Flask test client (no live server required).
"""
from __future__ import annotations

import io
import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKBOOK = ROOT / "sample_data" / "S360_EMS_Simple_Workbook.xlsx"


def _conn(name: str, pts: list, kind: str = "line", **kw) -> dict:
    return {
        "type": "Connector",
        "connectorKind": kind,
        "pointsData": [{"x": x, "y": y} for x, y in pts],
        "stroke": "#111111",
        "strokeWidth": 2,
        "arrowEnd": kind == "arrow",
        "objName": name,
        **kw,
    }


def _image(name: str, url: str) -> dict:
    return {
        "type": "image",
        "src": url,
        "left": 120, "top": 140,
        "scaleX": 0.5, "scaleY": 0.5,
        "objName": name,
    }


def main() -> int:
    if not WORKBOOK.exists():
        print(f"ERROR: sample workbook not found: {WORKBOOK}")
        return 2

    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa

    c = server.app.test_client()
    problems: list[str] = []

    # 1. Create project.
    with open(WORKBOOK, "rb") as fh:
        res = c.post(
            "/api/projects/new",
            data={"file": (io.BytesIO(fh.read()), "S360.xlsx")},
            content_type="multipart/form-data",
        )
    if res.status_code != 200:
        print(f"FAIL create project {res.status_code}")
        return 1
    pid = res.get_json()["id"]
    print(f"project: {pid}")

    proj = c.get(f"/api/projects/{pid}").get_json()
    pages = proj["pages"]
    if len(pages) < 2:
        problems.append("need ≥2 pages")

    # 2. Put connector + image on page 0, leave page 1 empty.
    page0_objects = [
        _conn("Straight Line", [(100, 100), (400, 100)], "line",
              stylePreset="cat6", labelMiddle="CAT6"),
        _conn("Elbow Route", [(120, 220), (360, 220), (360, 400)], "elbow"),
        _conn("Polyline", [(80, 320), (200, 370), (340, 330), (460, 380)], "polyline"),
        _image("PR0650 crop", "/api/assets/fake/fake.png"),
    ]
    pages[0]["canvasObjects"] = page0_objects
    pages[1]["canvasObjects"] = []
    sp = c.post(f"/api/projects/{pid}/pages", json={"pages": pages})
    if sp.status_code != 200:
        problems.append(f"save pages {sp.status_code}")

    # 3. Reload and assert objects + routes survive.
    reloaded = c.get(f"/api/projects/{pid}").get_json()
    p0 = reloaded["pages"][0].get("canvasObjects", [])
    p1 = reloaded["pages"][1].get("canvasObjects", []) if len(reloaded["pages"]) > 1 else []
    conns = [o for o in p0 if o.get("type") == "Connector"]
    imgs  = [o for o in p0 if o.get("type") == "image"]

    print(f"page 0 connectors: {len(conns)}  images: {len(imgs)}")
    if len(conns) != 3:
        problems.append(f"expected 3 connectors on page 0, got {len(conns)}")
    if len(imgs) != 1:
        problems.append(f"expected 1 image on page 0, got {len(imgs)}")
    if len(p1) != 0:
        problems.append(f"objects leaked to page 1: {len(p1)}")

    by_name = {o.get("objName"): o for o in p0}
    elb = by_name.get("Elbow Route")
    if not elb or elb.get("connectorKind") != "elbow" or len(elb.get("pointsData") or []) != 3:
        problems.append("elbow connectorKind / route not preserved")
    poly = by_name.get("Polyline")
    if not poly or len(poly.get("pointsData") or []) != 4:
        problems.append("polyline 4-point route not preserved")
    straight = by_name.get("Straight Line")
    if not straight or straight.get("stylePreset") != "cat6" or straight.get("labelMiddle") != "CAT6":
        problems.append("straight connector preset/label not preserved")

    # 4. Add a duplicate and re-save.
    dup = {**_conn("Straight Line copy", [(112, 112), (412, 112)], "line"), "stylePreset": "cat6"}
    pages2 = reloaded["pages"]
    pages2[0]["canvasObjects"] = p0 + [dup]
    c.post(f"/api/projects/{pid}/pages", json={"pages": pages2})
    reloaded2 = c.get(f"/api/projects/{pid}").get_json()
    p0_2 = reloaded2["pages"][0].get("canvasObjects", [])
    dup_found = any(o.get("objName") == "Straight Line copy" for o in p0_2)
    if not dup_found:
        problems.append("duplicated connector not persisted")
    else:
        print("duplicate connector: OK")

    # 5. Backup created after writes.
    backups = c.get(f"/api/projects/{pid}/backups").get_json().get("backups", [])
    print(f"server backups: {len(backups)}")
    if not backups:
        problems.append("no server backup created after save")
    else:
        # Restore newest backup and confirm valid project comes back.
        newest = backups[0]["name"]
        rr = c.post(f"/api/projects/{pid}/restore-backup", json={"name": newest})
        if rr.status_code != 200:
            problems.append(f"restore-backup failed {rr.status_code}")
        else:
            restored = rr.get_json().get("project", {})
            if not restored.get("pages"):
                problems.append("restore-backup returned empty project")
            else:
                print(f"backup restore: OK ({len(restored['pages'])} pages)")
        # Reject unsafe name.
        bad = c.post(f"/api/projects/{pid}/restore-backup", json={"name": "../foo.json"})
        if bad.status_code == 200:
            problems.append("restore-backup accepted unsafe name")

    # 6. project.json must include latest canvasObjects (save must not be stale).
    proj_dir = server.store.find_dir(pid)
    if proj_dir and (proj_dir / "project.json").exists():
        on_disk = json.loads((proj_dir / "project.json").read_text("utf-8"))
        disk_p0 = on_disk["pages"][0].get("canvasObjects", [])
        disk_conns = [o for o in disk_p0 if o.get("type") == "Connector"]
        if len(disk_conns) < 3:
            problems.append(f"project.json on disk has only {len(disk_conns)} connectors — save may be stale")
        else:
            print(f"disk project.json connectors: {len(disk_conns)} OK")

    c.delete(f"/api/projects/{pid}")

    if problems:
        print("CONNECTOR/SAVE PROBLEMS:")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("OK: connector save smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
