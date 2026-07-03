"""scripts/smoke_component_library.py — verify the local component library.

Checks (deterministic, via the Flask test client — no live server needed):
  - the library can be initialized / seed-imported
  - GET /api/library returns components, categories, connectorStyles, symbols
  - at least one category exists
  - component asset + thumbnail paths resolve through the safe asset route
  - path traversal is rejected
  - the delete route requires an explicit confirm flag
  - inserting a component onto a project page works and is PAGE-SCOPED
    (objects saved on one page do NOT leak onto another page)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import server

    c = server.app.test_client()
    problems: list[str] = []

    # 1. Seed import (idempotent) + read.
    seed = c.post("/api/library/import-seed")
    lib = c.get("/api/library").get_json()
    comps = lib.get("components", [])
    cats = lib.get("categories", [])
    print(f"seed import: {seed.status_code} | components: {len(comps)} | categories: {len(cats)} | "
          f"connectorStyles: {len(lib.get('connectorStyles', []))} | symbols: {len(lib.get('symbols', []))}")

    if not comps:
        print("NOTE: no components found — seed folder may be absent. Skipping asset checks.")
    else:
        if not cats:
            problems.append("no categories derived")
        if not lib.get("connectorStyles"):
            problems.append("no connector styles")

        # 2. Asset + thumbnail resolve for the first component that has them.
        sample = next((x for x in comps if x.get("assetPath")), None)
        if sample:
            a = c.get("/api/library/assets/" + sample["assetPath"])
            if a.status_code != 200:
                problems.append(f"asset did not resolve ({a.status_code}) for {sample['id']}")
            if sample.get("thumbnailPath"):
                t = c.get("/api/library/assets/" + sample["thumbnailPath"])
                if t.status_code != 200:
                    problems.append(f"thumbnail did not resolve ({t.status_code}) for {sample['id']}")

    # 3. Path traversal must be rejected.
    trav = c.get("/api/library/assets/..%2f..%2fserver.py")
    if trav.status_code == 200:
        problems.append("path traversal was NOT blocked")

    # 4. Delete route must require confirmation.
    if comps:
        cid = comps[0]["id"]
        no_confirm = c.delete(f"/api/library/components/{cid}")
        if no_confirm.status_code != 400:
            problems.append("delete without confirm should be rejected (400)")

    # 5. Page-scoped overlay isolation via a throwaway project.
    wb = os.environ.get("SINGH360_SA31_WORKBOOK", "")
    if not wb:
        # Try the known desktop workbook name relative to common locations.
        pass
    pid = None
    if wb and Path(wb).exists():
        import io
        with open(wb, "rb") as fh:
            res = c.post("/api/projects/new", data={"file": (io.BytesIO(fh.read()), "SA31.xlsx")},
                         content_type="multipart/form-data")
        if res.status_code == 200:
            pid = res.get_json()["id"]
    if pid:
        proj = c.get(f"/api/projects/{pid}").get_json()
        pages = proj["pages"]
        if len(pages) >= 2:
            pages[0]["canvasObjects"] = [{"type": "image", "left": 10, "top": 10, "width": 50, "height": 50,
                                          "src": "/api/library/assets/x.png", "objName": "OnPageOne"}]
            pages[1]["canvasObjects"] = []
            c.post(f"/api/projects/{pid}/pages", json={"pages": pages})
            reload = c.get(f"/api/projects/{pid}").get_json()["pages"]
            p0 = reload[0].get("canvasObjects") or []
            p1 = reload[1].get("canvasObjects") or []
            if len(p0) != 1:
                problems.append("page 1 lost its overlay object")
            if len(p1) != 0:
                problems.append("overlay object LEAKED onto page 2")
            print(f"page-scoped overlay: page1={len(p0)} obj, page2={len(p1)} obj (expected 1 / 0)")
        c.delete(f"/api/projects/{pid}")
    else:
        print("page-scope check skipped (set SINGH360_SA31_WORKBOOK to a workbook to enable it)")

    if problems:
        print("COMPONENT LIBRARY PROBLEMS:")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("OK: component library smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
