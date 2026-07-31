"""Controlled live Layout Sandbox verification for the leak-sensor standard.

This intentionally refuses to run without the explicit safety flag. It saves
only the local Layout Sandbox project and never calls a workbook-link route.
The caller must restore the backed-up project.json after collecting evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "a214bea233ee4dcc"
PAGE_ID = "p_ms6p8xy8_3010hz"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def api_json(url: str) -> dict:
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def export_pdf(base: str, evidence: Path) -> int:
    request = Request(
        f"{base}/api/projects/{PROJECT_ID}/export/pdf",
        data=json.dumps({"width": 17, "height": 11, "pageIds": [PAGE_ID], "confirmPreflight": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=180) as response:
        payload = response.read()
    if not payload.startswith(b"%PDF"):
        raise AssertionError("live Layout Sandbox PDF export did not return a PDF")
    (evidence / "layout-wicp7-leak-sensors.pdf").write_bytes(payload)
    return len(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live-layout-sandbox", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    if not args.allow_live_layout_sandbox:
        raise SystemExit("Refusing live mutation without --allow-live-layout-sandbox")
    project_path = ROOT / ".docs" / "projects" / "Layout-Sandbox__a214bea233ee4dcc" / "project.json"
    workbook_paths = sorted(project_path.parent.joinpath("sources", "workbook").glob("*.xlsx"))
    before = {str(path): digest(path) for path in [project_path, *workbook_paths]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = ROOT / "runtime_artifacts" / "leak-sensors-live" / stamp
    evidence.mkdir(parents=True)
    requests: list[tuple[str, str]] = []
    failures: list[str] = []
    console_errors: list[str] = []
    report: dict = {"evidence": str(evidence), "before": before}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
        page = browser.new_page(viewport={"width": 1700, "height": 1050})
        page.on("request", lambda request: requests.append((request.method, request.url)))
        page.on("response", lambda response: failures.append(f"{response.status} {response.url}") if response.status >= 400 else None)
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.goto(f"{args.base_url}/app?project={PROJECT_ID}&mode=editor&workflowAudit=1&renderAudit=1", wait_until="domcontentloaded", timeout=60_000)
        page.locator(".ribbon").wait_for(timeout=30_000)
        page.locator(".page-tab").filter(has_text="WICP7").click()
        page.wait_for_function("() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects", timeout=30_000)
        page.locator(".page-tab.active").filter(has_text="WICP7").wait_for(timeout=30_000)
        page.wait_for_function(
            "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).some(item => item.libraryComponentId === 'symbols_markers_s360_7a7d4d97334a')",
            timeout=30_000,
        )
        repaired = page.evaluate(
            "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).filter(item => item.libraryComponentId === 'symbols_markers_s360_7a7d4d97334a').map(item => ({name:item.objName, acronym:item.symAcronym, id:item.libraryComponentId}))"
        )
        if not repaired or any(item["acronym"] != "LSc" or not item["name"].startswith("LSc —") for item in repaired):
            raise AssertionError(f"saved LS2 stable-ID objects did not hydrate as LSc: {repaired}")
        if page.locator(".panel-rail-left").is_visible():
            page.locator(".panel-rail-left").click()
        page.locator(".nav-section-head").filter(has_text=re.compile("Components", re.IGNORECASE)).click()
        panel = page.locator(".libv2-browser")
        panel.wait_for(timeout=30_000)
        page.get_by_text("Component library ready", exact=True).wait_for(timeout=30_000)
        collection = page.get_by_role("combobox", name="Component collection")
        collection.select_option(label="Refrigeration Controls Symbols")
        search = panel.get_by_placeholder("Search components…")
        for alias in ("LS2", "LS₂"):
            search.fill(alias)
            page.wait_for_function("() => document.querySelectorAll('.libv2-browser-card').length === 1", timeout=15_000)
            if "LSc —" not in panel.locator(".libv2-browser-card").inner_text():
                raise AssertionError(f"live alias {alias} did not resolve to LSc")
        search.fill("")
        page.wait_for_function("() => document.querySelectorAll('.libv2-browser-card').length > 4", timeout=15_000)
        all_names = panel.locator(".libv2-browser-card-name").all_inner_texts()
        visible_names = [name for name in all_names if name.split(" —", 1)[0] in {"LSc", "LSg", "LS", "LSb"}]
        if {name.split(" —", 1)[0] for name in visible_names} != {"LSc", "LSg", "LS", "LSb"} or len(visible_names) != 4:
            raise AssertionError(f"unexpected live leak-sensor cards: {visible_names}")
        if any("LS₂" in name or name.startswith("LS2") for name in all_names):
            raise AssertionError(f"legacy LS2 remains visible: {all_names}")
        before_names = page.evaluate("() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).map(item => item.objName)")
        panel.locator(".libv2-browser-card").filter(has_text="LSc —").click()
        page.wait_for_function(
            "count => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).length > count",
            arg=len(before_names), timeout=20_000,
        )
        panel.locator(".libv2-browser-card").filter(has_text="LSg —").drag_to(page.locator(".sheet-viewport"), target_position={"x": 900, "y": 500})
        page.wait_for_function(
            "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).some(item => String(item.objName).startsWith('LSg —'))",
            timeout=20_000,
        )
        page.get_by_role("button", name="Component Builder", exact=True).click()
        builder = page.get_by_role("dialog", name="Component Builder")
        builder.get_by_placeholder("Search existing components…").fill("LSc —")
        builder.locator(".libv2-builder-picker-list > button").filter(has_text="LSc —").first.click()
        builder.get_by_text("Advanced insertion and library tools", exact=True).click()
        for representation in ("Source", "Edge", "B/W"):
            builder.get_by_role("button", name=representation, exact=True).click()
            builder.get_by_role("button", name="Insert Selected", exact=True).click()
        builder.get_by_role("button", name="Close", exact=True).click()
        page.get_by_role("button", name="File", exact=True).click()
        page.get_by_role("button", name="Save Now", exact=True).click()
        page.wait_for_function(
            "() => !['UNSAVED PROJECT EDITS','SAVING PROJECT…','SAVE FAILED'].includes(document.querySelector('.save-state-control .status-pill')?.textContent || '')",
            timeout=30_000,
        )
        page.reload(wait_until="domcontentloaded", timeout=60_000)
        page.locator(".ribbon").wait_for(timeout=30_000)
        page.locator(".page-tab").filter(has_text="WICP7").click()
        page.wait_for_function(
            "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).some(item => String(item.objName).startsWith('LSg —'))",
            timeout=30_000,
        )
        page.screenshot(path=evidence / "layout-wicp7-live.png", full_page=True)
        report["pdfBytes"] = export_pdf(args.base_url, evidence)
        report["hydratedStableIdObjects"] = repaired
        report["finalCanvasNames"] = page.evaluate("() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).map(item => item.objName)")
        browser.close()
    if any("/workbook-link/" in url for _, url in requests):
        raise AssertionError("live browser invoked a forbidden workbook-link route")
    if failures or console_errors:
        raise AssertionError(f"live browser failures={failures}; console errors={console_errors}")
    report["requests"] = len(requests)
    report["workbookLinkRequests"] = 0
    report["after"] = {str(path): digest(path) for path in [project_path, *workbook_paths]}
    report["workbooksUnchanged"] = all(report["after"][str(path)] == before[str(path)] for path in workbook_paths)
    report["liveLibrary"] = api_json(f"{args.base_url}/api/lib")["counts"]
    (evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
