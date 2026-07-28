"""Browser-level Excel Layout control, persistence, rollover, and PDF smoke."""
from __future__ import annotations
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.export_pdf import export_pdf_via_playwright
from core.project_store import ProjectStore
from tests.test_excel_layout_export import layout_page


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int) -> None:
    for _ in range(150):
        try:
            if urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1).status == 200:
                return
        except OSError:
            time.sleep(.2)
    raise RuntimeError("isolated server did not become healthy")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="singh360_excel_layout_browser_") as raw:
        runtime = Path(raw)
        docs = runtime / ".docs"
        page = layout_page()
        page.update({
            "order": 1, "publishStatus": "YES", "issueStatus": "draft", "sheetCode": "EMS T.1",
            "displaySheetCode": "EMS T.1", "sheetTitle": "Neutral Layout Test", "pageType": "canvas",
            "templateId": "blank", "canvasObjects": [{"type": "rect", "name": "preserved-overlay"}],
            "notes": "", "pageNumber": 1, "pageTotal": 1,
        })
        project = {
            "id": "e1e1e1e1e1e1e101", "metadata": {"projectName": "Sanitized Layout Browser"},
            "worksheets": [], "pages": [page], "sources": [],
        }
        ProjectStore(docs).save(project["id"], project)
        port = free_port()
        env = {**os.environ, "SINGH360_DOCS_DIR": str(docs), "SINGH360_PORT": str(port)}
        proc = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            wait_health(port)
            with sync_playwright() as api:
                browser = api.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
                tab = browser.new_page(viewport={"width": 1920, "height": 1080})
                tab.goto(f"http://127.0.0.1:{port}/app?project={project['id']}&mode=editor")
                tab.get_by_test_id("excel-layout-canvas").wait_for(timeout=30000)
                table = tab.locator("[data-table-id='a']")
                table.click()
                # Style, size, independent column geometry, pagination, and repeat controls.
                tab.get_by_label("Title fill").fill("#ff8800")
                tab.locator('[aria-label="Title font color"]').fill("#112233")
                tab.locator('[aria-label="Title font size"]').fill("16")
                tab.locator('[aria-label="Title bold"]').click()
                tab.locator('[aria-label="Title alignment"]').select_option("left")
                tab.locator('[aria-label="Header fill"]').fill("#ddeeff")
                tab.locator('[aria-label="Body fill"]').fill("#ffffff")
                tab.locator('[aria-label="Alternating fill"]').fill("#eeeeee")
                tab.locator('[aria-label="Border style"]').select_option("medium")
                tab.locator('[aria-label="Wrap body cells"]').click()
                tab.locator('[aria-label="Body row height"]').fill("31")
                tab.get_by_label("Table width").fill("920")
                tab.get_by_label("Table height").fill("180")
                before_b = tab.locator("[data-table-id='b'] .excel-layout-row").first.get_attribute("style")
                tab.get_by_label("Column 1 width").fill("333")
                after_b = tab.locator("[data-table-id='b'] .excel-layout-row").first.get_attribute("style")
                if before_b != after_b:
                    raise AssertionError("Table B geometry changed when Table A was resized")
                for label in ("Keep Together", "Split Rows", "Repeat Title", "Repeat Headers"):
                    tab.get_by_label(label).click()
                tab.get_by_role("button", name="Merge Across").click()
                tab.get_by_role("button", name="Unmerge").click()
                tab.get_by_role("button", name="Copy").click()
                tab.get_by_role("button", name="Paste", exact=True).click()
                tab.get_by_role("button", name="Duplicate").click()
                tab.get_by_role("button", name="Delete").click()
                tab.get_by_role("button", name="New Table").click()
                tab.get_by_role("button", name="Undo").click()
                tab.get_by_role("button", name="Redo").click()
                tab.get_by_label("Workbook tab color").fill("#336699")
                # Real TSV clipboard event creates a separate editable table below selection.
                tab.evaluate("""() => window.dispatchEvent(new ClipboardEvent('paste', {
                    clipboardData: new DataTransfer(), bubbles: true, cancelable: true
                }))""")
                # Move selected table beyond printable sheet using the tested position model.
                tab.get_by_label("Table height").fill("1200")
                tab.wait_for_timeout(1500)
                if tab.locator(".excel-layout-page").count() < 2:
                    raise AssertionError("second stacked 11x17 page did not appear")
                tab.reload()
                tab.get_by_test_id("excel-layout-canvas").wait_for(timeout=30000)
                if tab.locator("[data-table-id]").count() < 3:
                    raise AssertionError("layout tables did not survive save/reload")
                browser.close()
            pdf = runtime / "layout.pdf"
            ok, detail = export_pdf_via_playwright(
                f"http://127.0.0.1:{port}/app?project={project['id']}&mode=editor&print=1&pw=17&ph=11", pdf
            )
            if not ok or not pdf.is_file() or pdf.stat().st_size < 1000:
                raise AssertionError(f"PDF export failed: {detail}")
            saved = ProjectStore(docs).load(project["id"])
            if saved["pages"][0]["canvasObjects"][0]["name"] != "preserved-overlay":
                raise AssertionError("manual canvas object was not preserved")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("PASS: isolated browser controls, persistence, rollover, canvas preservation, and PDF export")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
