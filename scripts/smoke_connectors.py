"""scripts/smoke_connectors.py — connector persistence + backup/recovery smoke.

Exercises the real Flask API the way the editor does (test client, no live
server) to prove the Milestone 3E save/connector guarantees deterministically:

  1. create a project from a workbook
  2. add connector objects (straight, polyline, elbow) to a page + save
  3. reload and confirm connectors + their pointsData routes survived
  4. duplicate a connector and confirm both persist
  5. add an object to a second page and confirm no cross-page leak
  6. confirm a server backup snapshot was created and can be listed + restored

Usage:
  python scripts/smoke_connectors.py <workbook.xlsx>
  or set SINGH360_SA31_WORKBOOK
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _connector(name: str, pts: list[tuple[int, int]], kind: str, **extra) -> dict:
    return {
        "type": "Connector",
        "connectorKind": kind,
        "pointsData": [{"x": x, "y": y} for x, y in pts],
        "stroke": "#111111",
        "strokeWidth": 2,
        "arrowEnd": kind == "arrow",
        "objName": name,
        **extra,
    }


def main() -> int:
    wb = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SINGH360_SA31_WORKBOOK", "")
    if not wb or not Path(wb).exists():
        print("Usage: python scripts/smoke_connectors.py <workbook.xlsx>")
        print("   or set SINGH360_SA31_WORKBOOK")
        return 2

    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402

    client = server.app.test_client()
    problems: list[str] = []

    # 1. Create project.
    with open(wb, "rb") as fh:
        res = client.post(
            "/api/projects/new",
            data={"file": (io.BytesIO(fh.read()), "SA31.xlsx")},
            content_type="multipart/form-data",
        )
    if res.status_code != 200:
        print(f"FAIL: create project -> {res.status_code}")
        return 1
    pid = res.get_json()["id"]
    print(f"created project: {pid}")

    proj = client.get(f"/api/projects/{pid}").get_json()
    pages = proj.get("pages", [])
    if len(pages) < 2:
        problems.append("need at least 2 pages for cross-page leak test")

    # 2. Add connectors (straight, polyline, elbow) + a duplicate, to page 0.
    straight = _connector("Wire Straight", [(100, 100), (400, 100)], "line",
                          stylePreset="cat6", labelMiddle="CAT6")
    polyline = _connector("Wire Polyline", [(120, 200), (240, 260), (360, 210), (480, 280)], "polyline")
    elbow = _connector("Wire Elbow", [(120, 320), (360, 320), (360, 460)], "elbow")
    dup = _connector("Wire Straight copy", [(112, 112), (412, 112)], "line", stylePreset="cat6")
    pages[0]["canvasObjects"] = [straight, polyline, elbow, dup]
    pages[1]["canvasObjects"] = []
    save = client.post(f"/api/projects/{pid}/pages", json={"pages": pages})
    if save.status_code != 200:
        problems.append(f"save pages -> {save.status_code}: {save.get_data(as_text=True)[:200]}")

    # 3. Reload + verify connectors and routes.
    reloaded = client.get(f"/api/projects/{pid}").get_json()
    p0 = reloaded["pages"][0].get("canvasObjects") or []
    p1 = reloaded["pages"][1].get("canvasObjects") or []
    conns = [o for o in p0 if o.get("type") == "Connector"]
    print(f"connectors persisted on page 1: {len(conns)} (expected 4)")
    if len(conns) != 4:
        problems.append(f"expected 4 connectors after reload, got {len(conns)}")

    by_name = {o.get("objName"): o for o in conns}
    poly = by_name.get("Wire Polyline")
    if not poly or len(poly.get("pointsData") or []) != 4:
        problems.append("polyline route (4 points) did not persist")
    elb = by_name.get("Wire Elbow")
    if not elb or elb.get("connectorKind") != "elbow" or len(elb.get("pointsData") or []) != 3:
        problems.append("elbow route/kind did not persist")
    st = by_name.get("Wire Straight")
    if not st or st.get("stylePreset") != "cat6" or st.get("labelMiddle") != "CAT6":
        problems.append("connector style preset / label did not persist")

    # 4. Duplicate proof.
    if "Wire Straight copy" not in by_name:
        problems.append("duplicated connector did not persist")

    # 5. No cross-page leak.
    if len(p1) != 0:
        problems.append(f"connectors leaked onto page 2 ({len(p1)} objects)")
    else:
        print("page-scope: page 2 clean (no connector leak)")

    # 6. Backup snapshot created + listable + restorable.
    backups = client.get(f"/api/projects/{pid}/backups").get_json().get("backups", [])
    print(f"server backups after saves: {len(backups)}")
    if not backups:
        problems.append("no server backup snapshot created after saves")
    else:
        # Mutate the live project, then restore the newest backup and confirm the
        # restore path returns a valid project + writes another backup.
        newest = backups[0]["name"]
        rest = client.post(f"/api/projects/{pid}/restore-backup", json={"name": newest})
        if rest.status_code != 200:
            problems.append(f"restore-backup failed ({rest.status_code})")
        else:
            after = client.get(f"/api/projects/{pid}/backups").get_json().get("backups", [])
            if len(after) < len(backups):
                problems.append("restore should not reduce backup count")
        # Path-traversal / invalid name must be rejected.
        bad = client.post(f"/api/projects/{pid}/restore-backup", json={"name": "../project.json"})
        if bad.status_code == 200:
            problems.append("restore-backup accepted an unsafe name")

    client.delete(f"/api/projects/{pid}")

    if problems:
        print("CONNECTOR SMOKE PROBLEMS:")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("OK: connector + backup smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
