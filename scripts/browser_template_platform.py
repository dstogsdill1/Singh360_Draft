"""Chromium smoke for template-platform UI routes and controls."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
PROJECT_ID = "bfd764c27a25488d"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".docs" / "projects" / f"Template-Platform-E2E__{PROJECT_ID}" / "debug"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"projectId": PROJECT_ID, "routes": {}, "consoleErrors": [], "pageErrors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("console", lambda message: report["consoleErrors"].append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: report["pageErrors"].append(str(error)))
        checks = [
            ("wizard", f"{BASE}/app?view=new", ["New Project", "Project Profile", "EMS Full"]),
            ("sources", f"{BASE}/app?project={PROJECT_ID}&view=sources", ["Sources", "sanitized_source.pdf", "Data", "Drawings"]),
            ("data", f"{BASE}/app?project={PROJECT_ID}&view=data", ["Data Workspace", "SAVE + WRITE EXCEL", "Update Drawings"]),
            ("drawings", f"{BASE}/app?project={PROJECT_ID}&mode=editor", ["SINGH360", "SAVE + WRITE EXCEL"]),
            ("home", f"{BASE}/app?project={PROJECT_ID}", ["Project Home", "Sources", "Data", "Drawings", "Review / QA"]),
        ]
        for name, url, labels in checks:
            response = page.goto(url, wait_until="networkidle", timeout=120_000)
            page.wait_for_timeout(1500)
            body = page.locator("body").inner_text()
            missing = [label for label in labels if label not in body]
            if missing:
                raise AssertionError(f"{name} missing visible labels: {missing}")
            screenshot = OUTPUT / f"browser_{name}.png"
            page.screenshot(path=str(screenshot), full_page=name != "data")
            route_result = {"status": response.status if response else None, "labels": labels, "screenshot": str(screenshot)}
            if name == "data":
                route_result["univerCanvasCount"] = page.locator("canvas").count()
                route_result["univerHostBox"] = page.locator(".univer-host").bounding_box()
                fixtures = [
                    ("excelHtml", '<table><tr><td style="background-color:#f47c20;font-weight:bold" colspan="2">Excel Alpha</td></tr><tr><td>=1+1</td><td>Excel Beta</td></tr></table>', "Excel Alpha"),
                    ("googleHtml", '<table><tbody><tr><td style="background-color:rgb(38,38,38);color:white">Google Alpha</td><td style="font-style:italic">Google Beta</td></tr></tbody></table>', "Google Alpha"),
                    ("tsv", "", "TSV Alpha"),
                ]
                clipboard_results = {}
                for fixture_name, html, marker in fixtures:
                    plain = "TSV Alpha\tTSV Beta" if fixture_name == "tsv" else marker
                    page.evaluate("""([html, plain]) => {
                      const transfer = new DataTransfer();
                      transfer.setData('text/html', html);
                      transfer.setData('text/plain', plain);
                      window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
                    }""", [html, plain])
                    page.get_by_role("button", name="Save", exact=True).click()
                    page.wait_for_timeout(800)
                    document = page.evaluate(f"fetch('/api/projects/{PROJECT_ID}/workbook').then(response => response.json())")
                    values = [str(cell.get("v") or cell.get("f") or "") for sheet in document["sheets"] for cell in sheet["cells"].values()]
                    found = marker in values
                    if not found:
                        raise AssertionError(f"{fixture_name} clipboard marker did not persist")
                    clipboard_results[fixture_name] = {"marker": marker, "persisted": found, "revision": document["revision"]}
                route_result["clipboard"] = clipboard_results
            report["routes"][name] = route_result
        browser.close()
    ignored = ("favicon.ico",)
    report["consoleErrors"] = [item for item in report["consoleErrors"] if not any(part in item for part in ignored)]
    data_route = report["routes"].get("data", {})
    if report["consoleErrors"] or report["pageErrors"] or data_route.get("univerCanvasCount", 0) < 1:
        raise AssertionError(json.dumps(report, indent=2))
    report_path = OUTPUT / "template_platform_browser_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
