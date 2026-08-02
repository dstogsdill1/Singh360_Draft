"""Disposable browser/PDF smoke for explicit Spreadsheet Page Layout recipes."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.export_pdf import export_pdf_via_playwright
from core.project_store import ProjectStore
from core.project_workspace import WorkbookDocumentStore
from tests.test_spreadsheet_page_layout import region, worksheet


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int) -> None:
    for _ in range(200):
        try:
            if urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1).status == 200:
                return
        except OSError:
            time.sleep(.2)
    raise RuntimeError("disposable spreadsheet-layout server did not become healthy")


def workbook_document() -> dict:
    source = worksheet()
    cells = {
        f"{column}{row + 1}": {"v": value}
        for row, values in enumerate(source["grid"])
        for column, value in zip(("A", "B"), values)
        if value
    }
    first = region("first", "ems-16-2", "A1:B5")
    continuation = region("continuation", "ems-16-2a", "A6:B9")
    first["fitMode"] = continuation["fitMode"] = "fit_width"
    sheet = {
        "id": source["id"], "name": source["name"], "cells": cells,
        "styles": source["styles"], "merges": [],
        "rowHeights": {str(index + 1): 21 for index in range(9)},
        "columnWidths": {"A": 16, "B": 75},
        "defaultColumnWidth": 8.43, "defaultRowHeight": 15,
        "hiddenRows": [], "hiddenColumns": [], "archived": False,
        "tabColor": None, "role": None, "sourceSetup": {},
        "protectedRanges": [], "dataValidations": [], "conditionalFormats": [],
        "tableRegions": [], "tableLayout": "single", "annotations": [],
        "pageLayouts": [
            {"pageId": "ems-16-2", "regions": [first]},
            {"pageId": "ems-16-2a", "regions": [continuation]},
        ],
    }
    continued_sheet = {
        **sheet,
        "id": "ws-lighting-cont",
        "name": "Lighting I-O Continued",
        "pageLayouts": [],
    }
    index = {
        "id": "ws-index", "name": "00_INDEX",
        "cells": {
            "A1": {"v": "Include"}, "B1": {"v": "Order"}, "C1": {"v": "Sheet Code"},
            "D1": {"v": "Sheet Tab"}, "E1": {"v": "Page Title"}, "F1": {"v": "Page Type"},
            "A2": {"v": "YES"}, "B2": {"v": 1}, "C2": {"v": "EMS 16.2"},
            "D2": {"v": source["name"]}, "E2": {"v": "Lighting Control I/O"}, "F2": {"v": "data-grid"},
        },
        "styles": {}, "merges": [], "rowHeights": {}, "columnWidths": {},
        "defaultColumnWidth": 8.43, "defaultRowHeight": 15,
        "hiddenRows": [], "hiddenColumns": [], "archived": False,
        "tabColor": None, "role": "control", "sourceSetup": {},
        "protectedRanges": [], "dataValidations": [], "conditionalFormats": [],
        "tableRegions": [], "tableLayout": "single", "annotations": [], "pageLayouts": [],
    }
    return {"revision": 0, "updatedAt": "", "sheets": [index, sheet, continued_sheet]}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="singh360_spreadsheet_layout_") as raw:
        runtime = Path(raw)
        docs = runtime / ".docs"
        source = worksheet()
        pages = [
            {
                "id": "ems-16-2", "order": 1, "include": True, "publishStatus": "YES",
                "sheetCode": "EMS 16.2", "displaySheetCode": "EMS 16.2",
                "sheetTitle": "Lighting Control I/O", "sheetTab": source["name"],
                "pageType": "data-grid", "templateId": "excel-range", "linkedWorksheetId": source["id"],
                "blocks": [], "canvasObjects": [{"type": "rect", "name": "manual-overlay-preserved"}], "notes": "",
            },
            {
                "id": "ems-16-2a", "order": 2, "include": True, "publishStatus": "YES",
                "sheetCode": "EMS 16.2a", "displaySheetCode": "EMS 16.2a",
                "sheetTitle": "Lighting Control I/O Continued", "sheetTab": "Lighting I-O Continued",
                "pageType": "data-grid", "templateId": "excel-range", "linkedWorksheetId": "ws-lighting-cont",
                "blocks": [], "canvasObjects": [], "notes": "",
            },
        ]
        project = {
            "id": "5151515151515151", "metadata": {"projectName": "Sanitized Spreadsheet Layout"},
            "worksheets": [source, {**source, "id": "ws-lighting-cont", "name": "Lighting I-O Continued"}], "pages": pages, "sources": [],
        }
        store = ProjectStore(docs)
        store.save(project["id"], project)
        WorkbookDocumentStore(store.dir_for(project["id"], project)).save(project, 0, workbook_document())
        port = free_port()
        env = {**os.environ, "SINGH360_DOCS_DIR": str(docs), "SINGH360_PORT": str(port)}
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        requests: list[tuple[str, str]] = []
        try:
            wait_health(port)
            with sync_playwright() as api:
                browser = api.chromium.launch(
                    executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    headless=True,
                )
                tab = browser.new_page(viewport={"width": 1900, "height": 1100})
                tab.on("request", lambda request: requests.append((request.method, request.url)))
                base = f"http://127.0.0.1:{port}/app?project={project['id']}"
                tab.goto(f"{base}&view=data", wait_until="domcontentloaded", timeout=60_000)
                tab.get_by_test_id("data-workspace-shell").wait_for(timeout=30_000)
                tab.locator("[data-testid='drawing-page-tab'][data-sheet-tab='Lighting I-O']").click()
                tab.get_by_role("button", name="Page Layout", exact=True).click()
                canvas = tab.get_by_test_id("spreadsheet-page-canvas")
                canvas.wait_for(timeout=20_000)
                if canvas.get_by_text("LCP1", exact=True).count() != 1 or canvas.get_by_text("LCP2", exact=True).count() != 1:
                    raise AssertionError(f"first explicit range did not render LCP1/LCP2 exactly once: {canvas.inner_text()!r}")
                first_region = canvas.locator("[data-region-id='first']")
                before_geometry = first_region.evaluate(
                    "element => [element.offsetLeft, element.offsetTop, element.offsetWidth, element.offsetHeight]"
                )
                move = first_region.get_by_role("button", name="Move Lighting I-O A1:B5")
                move_box = move.bounding_box()
                if not move_box:
                    raise AssertionError("linked range move handle has no browser geometry")
                tab.mouse.move(move_box["x"] + 8, move_box["y"] + 8)
                tab.mouse.down()
                tab.mouse.move(move_box["x"] + 24, move_box["y"] + 20)
                tab.mouse.up()
                tab.wait_for_function(
                    """([selector, left, top]) => {
                      const element = document.querySelector(selector);
                      return element && element.offsetLeft > left && element.offsetTop > top;
                    }""",
                    arg=["[data-region-id='first']", before_geometry[0], before_geometry[1]],
                )
                resize = first_region.get_by_role("button", name="Resize Lighting I-O A1:B5")
                resize_box = resize.bounding_box()
                if not resize_box:
                    raise AssertionError("linked range resize handle has no browser geometry")
                tab.mouse.move(resize_box["x"] + 5, resize_box["y"] + 5)
                tab.mouse.down()
                tab.mouse.move(resize_box["x"] + 25, resize_box["y"] + 17)
                tab.mouse.up()
                after_geometry = first_region.evaluate(
                    "element => [element.offsetLeft, element.offsetTop, element.offsetWidth, element.offsetHeight]"
                )
                if after_geometry[0] <= before_geometry[0] or after_geometry[1] <= before_geometry[1]:
                    raise AssertionError(f"linked range did not move: {before_geometry!r} -> {after_geometry!r}")
                if after_geometry[2] <= before_geometry[2] or after_geometry[3] <= before_geometry[3]:
                    raise AssertionError(f"linked range did not resize: {before_geometry!r} -> {after_geometry!r}")
                first_scale = first_region.get_attribute("data-scale")
                tab.locator(".spreadsheet-layout-sidebar select").first.select_option("ems-16-2a")
                if canvas.get_by_text("LCP1", exact=True).count():
                    raise AssertionError("continuation repeated the section-specific LCP1 header")
                if canvas.get_by_text("LCP3", exact=True).count() != 1 or canvas.get_by_text("LCP4", exact=True).count() != 1:
                    raise AssertionError("second explicit range did not render LCP3/LCP4 exactly once")
                tab.get_by_role("button", name="Print Preview", exact=True).click()
                preview_scale = canvas.locator("[data-region-id='continuation']").get_attribute("data-scale")
                if not preview_scale:
                    raise AssertionError("Print Preview did not reuse the shared region renderer")
                tab.get_by_role("button", name="Page Layout", exact=True).click()
                tab.locator(".spreadsheet-layout-sidebar select").first.select_option("ems-16-2")
                tab.get_by_role("button", name="Update Drawings", exact=True).click()
                tab.locator(".workspace-status").get_by_text("PROJECT SAVED", exact=True).wait_for(timeout=20_000)

                tab.goto(f"{base}&mode=editor", wait_until="domcontentloaded", timeout=60_000)
                tab.get_by_test_id("spreadsheet-page-canvas").wait_for(timeout=30_000)
                editor_scale = tab.locator("[data-region-id='first']").get_attribute("data-scale")
                if editor_scale != first_scale:
                    raise AssertionError(f"Page Layout/editor scale mismatch: {first_scale} != {editor_scale}")
                tab.get_by_text("Advanced Tools", exact=True).click()
                tab.get_by_role("button", name="Insert", exact=True).click()
                tab.on("dialog", lambda dialog: dialog.dismiss())
                tab.get_by_role("button", name="Spreadsheet Table", exact=True).click()
                tab.get_by_test_id("excel-layout-canvas").wait_for(timeout=10_000)
                tab.evaluate("""() => {
                  const transfer = new DataTransfer();
                  transfer.setData('text/html', '<table style="width:600px"><tr style="height:34px"><th colspan="2" style="background-color:#f4b183;font-weight:bold;text-align:center">PASTED SCHEDULE</th></tr><tr><td style="width:180px;background-color:#d9eaf7">POINT</td><td style="width:420px;white-space:normal">Complete pasted description</td></tr></table>');
                  window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
                }""")
                pasted = tab.locator("[data-table-id]").last
                pasted.wait_for(timeout=10_000)
                if "PASTED SCHEDULE" not in pasted.inner_text():
                    raise AssertionError("clipboard HTML was not inserted as one editable table")
                if pasted.locator("td[colspan='2']").count() != 1:
                    raise AssertionError("clipboard merge geometry was not preserved")
                tab.get_by_role("button", name="Fit to Page Width", exact=True).click()
                tab.get_by_role("button", name="Continue on Next Page", exact=True).click()
                tab.get_by_role("button", name="Undo", exact=True).last.click()
                tab.keyboard.press("Control+s")
                tab.wait_for_timeout(1_500)
                browser.close()

            pdf = runtime / "spreadsheet-layout.pdf"
            ok, detail = export_pdf_via_playwright(
                f"http://127.0.0.1:{port}/app?project={project['id']}&mode=editor&print=1&pw=17&ph=11",
                pdf,
            )
            if not ok:
                raise AssertionError(f"PDF export failed: {detail}")
            document = fitz.open(pdf)
            try:
                if len(document) != 2:
                    raise AssertionError(f"expected two explicit pages, got {len(document)}")
                first_text = document[0].get_text()
                second_text = document[1].get_text()
                if first_text.count("LCP1") < 1 or first_text.count("LCP2") < 1:
                    raise AssertionError("PDF first range is incomplete")
                if "LCP1" in second_text or second_text.count("LCP3") < 1 or second_text.count("LCP4") < 1:
                    raise AssertionError("PDF continuation duplicated a header or lost source rows")
                if "Complete fourth controller description" not in second_text:
                    raise AssertionError("wrapped continuation description was clipped from PDF text")
            finally:
                document.close()
            saved = store.load(project["id"])
            objects = saved["pages"][0].get("canvasObjects") or []
            if len(objects) != 1 or str(objects[0].get("type") or "").casefold() != "rect":
                raise AssertionError(f"manual canvas object changed: {objects!r}")
            if any("workbook-link" in url or "write-excel" in url for _, url in requests):
                raise AssertionError("disposable workflow invoked workbook synchronization")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        print("PASS: explicit ranges, no duplicate header, clipboard table, shared preview/editor/PDF, save/reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
