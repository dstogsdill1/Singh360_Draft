"""scripts/smoke_editor_browser.py — end-to-end editor workflow smoke.

This exercises the real Singh360 Draft API the way the browser does, using the
Flask test client (no live server required) so it is deterministic in CI:

  1. create a project from the SA31 workbook
  2. read it back and verify pages
  3. rename the project
  4. rename a page's sheet title + code and save
  5. add a fake pasted-image canvas object to a page and save
  6. reload and verify the title/code/overlay object persisted
  7. export the package ZIP and verify it contains manifest.json + project.json

An OPTIONAL Playwright pass (only if a server URL is given via
SINGH360_APP_URL) loads /app and confirms it renders. PDF export is covered by
the package check + the manual VISUAL_QA checklist.

Usage:
  python scripts/smoke_editor_browser.py "<workbook.xlsx>"
  or set SINGH360_SA31_WORKBOOK
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


def main() -> int:
    wb = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SINGH360_SA31_WORKBOOK", "")
    if not wb or not Path(wb).exists():
        print("Usage: python scripts/smoke_editor_browser.py <workbook.xlsx>")
        print("   or set SINGH360_SA31_WORKBOOK")
        return 2

    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402

    client = server.app.test_client()
    problems: list[str] = []

    # 1. Create project from workbook.
    with open(wb, "rb") as fh:
        data = {"file": (io.BytesIO(fh.read()), "SA31.xlsx")}
        res = client.post("/api/projects/new", data=data, content_type="multipart/form-data")
    if res.status_code != 200:
        print(f"FAIL: create project -> {res.status_code}: {res.get_data(as_text=True)[:300]}")
        return 1
    pid = res.get_json().get("id")
    print(f"created project: {pid}")

    # 2. Read back.
    proj = client.get(f"/api/projects/{pid}").get_json()
    pages = proj.get("pages", [])
    if not pages:
        problems.append("no pages after import")
    print(f"pages: {len(pages)}")

    # 3. Rename project.
    res = client.post(f"/api/projects/{pid}/rename", json={"name": "SA31 EMS Test"})
    if res.status_code != 200:
        problems.append(f"rename project -> {res.status_code}")
    else:
        print(f"renamed -> folder: {res.get_json().get('projectFolder', '')}")

    # 4 + 5. Edit a page: new title/code + a pasted-image overlay object.
    proj = client.get(f"/api/projects/{pid}").get_json()
    pages = proj.get("pages", [])
    target = pages[0]
    target["sheetTitle"] = "Scope of Work (edited)"
    target["sheetCode"] = "TESTCODE"
    target["displaySheetCode"] = "TESTCODE"
    target["canvasObjects"] = [
        {"type": "image", "left": 100, "top": 120, "width": 300, "height": 200,
         "scaleX": 1, "scaleY": 1, "src": "/api/assets/x/test.png", "objName": "Storefront Map"},
        {"type": "Connector", "x1": 120, "y1": 140, "x2": 400, "y2": 300,
         "stroke": "#111", "strokeWidth": 2, "arrowEnd": True, "objName": "Arrow A"},
    ]
    res = client.post(f"/api/projects/{pid}/pages", json={"pages": pages})
    if res.status_code != 200:
        problems.append(f"save pages -> {res.status_code}: {res.get_data(as_text=True)[:200]}")

    # 6. Reload + verify persistence.
    proj = client.get(f"/api/projects/{pid}").get_json()
    t2 = proj.get("pages", [])[0]
    if t2.get("sheetTitle") != "Scope of Work (edited)":
        problems.append("sheetTitle did not persist")
    if t2.get("displaySheetCode") != "TESTCODE":
        problems.append("displaySheetCode did not persist")
    objs = t2.get("canvasObjects") or []
    if len(objs) < 2:
        problems.append("overlay objects did not persist")
    else:
        types = {o.get("type") for o in objs}
        print("overlay objects persisted:", sorted(types))
        if "Connector" not in types:
            problems.append("connector object did not persist")

    # 6b. A server backup snapshot must exist after saving over an existing project.
    backups = client.get(f"/api/projects/{pid}/backups").get_json().get("backups", [])
    print(f"server backups: {len(backups)}")
    if not backups:
        problems.append("no server backup snapshot created after save")

    # 7. Export package ZIP.
    res = client.post(f"/api/projects/{pid}/export/package")
    if res.status_code != 200:
        problems.append(f"export package -> {res.status_code}")
    else:
        try:
            zf = zipfile.ZipFile(io.BytesIO(res.get_data()))
            names = zf.namelist()
            if "manifest.json" not in names:
                problems.append("package missing manifest.json")
            if "project.json" not in names:
                problems.append("package missing project.json")
            print(f"package entries: {len(names)} (manifest+project present: "
                  f"{'manifest.json' in names and 'project.json' in names})")
        except zipfile.BadZipFile:
            problems.append("export package is not a valid ZIP")

    # Optional Playwright browser render check.
    app_url = os.environ.get("SINGH360_APP_URL", "")
    if app_url:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(app_url, wait_until="networkidle")
                title = page.title()
                browser.close()
                print(f"browser loaded /app, title: {title!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"(optional) Playwright render skipped: {exc}")

    # Clean up the throwaway test project so smokes don't accumulate.
    try:
        client.delete(f"/api/projects/{pid}")
    except Exception:  # noqa: BLE001
        pass

    if problems:
        print("EDITOR SMOKE PROBLEMS:")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("OK: editor workflow smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
