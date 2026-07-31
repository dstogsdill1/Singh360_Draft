"""Disposable end-to-end proof for the canonical refrigeration leak sensors."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.leak_sensor_standard import IDS, LSC_HIGHLIGHT_ID, LSC_PLAN_ID, PATHS, SENSORS, apply_leak_sensor_standard
from core.project_store import ProjectStore

PROJECT_ID = "1eak5e4500000001".replace("k", "a")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int) -> dict:
    for _ in range(180):
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                if response.status == 200:
                    return json.load(response)
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("disposable leak-sensor server did not become healthy")


def fixture_project() -> dict:
    page = {
        "id": "leak-sensor-page", "order": 1, "include": True, "publishStatus": "YES",
        "issueStatus": "draft", "sheetCode": "EMS LS.1", "displaySheetCode": "EMS LS.1",
        "sheetTitle": "Leak Sensor Sandbox", "sheetTab": "LEAK SENSOR SANDBOX",
        "pageType": "canvas", "pageFamily": "canvas", "templateId": "blank",
        "blocks": [], "canvasObjects": [], "notes": "", "pageNumber": 1, "pageTotal": 1,
    }
    return {
        "id": PROJECT_ID, "projectDisplayName": "Sanitized Leak Sensor Sandbox",
        "metadata": {"projectName": "Sanitized Leak Sensor Sandbox"},
        "worksheets": [], "pages": [page], "sources": [], "savedAssemblies": [],
        "workbookSync": {"status": "not_linked", "mode": "local-only"},
    }


def seed_old_library(docs: Path) -> None:
    library = docs / "library"
    for rel in (PATHS[("highlight", "LSc")], PATHS[("plan", "LSc")]):
        path = library / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 96 96\"/>", encoding="utf-8")
    records = [
        {"id": LSC_HIGHLIGHT_ID, "sourceFile": PATHS[("highlight", "LSc")], "displayName": "LS₂ old"},
        {"id": LSC_PLAN_ID, "sourceFile": PATHS[("plan", "LSc")], "displayName": "LS₂ old"},
        {"id": IDS[("highlight", "LS")], "sourceFile": PATHS[("highlight", "LS")], "displayName": "LS old"},
        {"id": IDS[("plan", "LS")], "sourceFile": PATHS[("plan", "LS")], "displayName": "LS old"},
        {"id": "s360_rdm_lsc", "sourceFile": "components/symbols_markers/s360_rdm_lsc.svg"},
        {"id": "s360_rdm_ls", "sourceFile": "components/symbols_markers/s360_rdm_ls.svg"},
    ]
    library.mkdir(parents=True, exist_ok=True)
    (library / "manifest.json").write_text(json.dumps({"version": 2, "components": records}), encoding="utf-8")
    (library / "component_builder_export.json").write_text(json.dumps({"components": []}), encoding="utf-8")
    (library / "symbols.json").write_text("[]", encoding="utf-8")
    (library / "library.json").write_text(json.dumps({"components": [], "symbols": []}), encoding="utf-8")
    (library / "aliases.json").write_text(json.dumps({"version": 1, "aliases": {}}), encoding="utf-8")
    legends = library / "legend_templates"
    legends.mkdir()
    fixtures = {
        "singh360-refrigeration-symbols-standard.json": {"rows": [{"code": "LS2"}, {"code": "LI2"}]},
        "singh360-plan-marker-legend.json": {"rows": [{"code": "LS"}, {"code": "LS2"}, {"code": "LI"}]},
        "rdm-wicp-safety-standard.json": {"rows": [{"id": "ls"}, {"id": "lsc"}, {"id": "li"}]},
        "wicp_refrigeration_symbol_legend.json": {"items": [{"symbolId": "sym_ls_hfc"}, {"symbolId": "sym_li"}]},
        "wicp_safety_alarm_legend.json": {"rows": [{"componentId": "wicp_ls_hfc"}, {"componentId": "wicp_lsc_co2"}, {"componentId": "wicp_li"}]},
        "legend_template_index.json": {"templates": []}, "manifest.json": {"version": 1, "templates": []},
    }
    for name, payload in fixtures.items():
        (legends / name).write_text(json.dumps(payload), encoding="utf-8")
    mapper = docs / "symbol_mapper" / "templates"
    mapper.mkdir(parents=True)
    (mapper / "standard.json").write_text(json.dumps({"symbols": [{"code": "LS2", "label": "old"}]}), encoding="utf-8")
    apply_leak_sensor_standard(docs)


def start_server(docs: Path, port: int, evidence: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(ROOT / "server.py")], cwd=ROOT,
        env={**os.environ, "SINGH360_DOCS_DIR": str(docs), "SINGH360_PORT": str(port)},
        stdout=(evidence / "server.out.log").open("a", encoding="utf-8"),
        stderr=(evidence / "server.err.log").open("a", encoding="utf-8"),
    )


def read_project(port: int) -> dict:
    with urlopen(f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}", timeout=20) as response:
        return json.load(response)


def export_pdf(port: int, evidence: Path) -> int:
    request = Request(
        f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}/export/pdf",
        data=json.dumps({"width": 17, "height": 11, "pageIds": ["leak-sensor-page"], "confirmPreflight": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=120) as response:
        payload = response.read()
    if not payload.startswith(b"%PDF"):
        raise AssertionError("disposable leak-sensor PDF export failed")
    (evidence / "leak-sensors.pdf").write_bytes(payload)
    return len(payload)


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = Path(os.environ.get("SINGH360_LEAK_SENSOR_EVIDENCE_DIR", ROOT / "runtime_artifacts" / "leak-sensors")) / stamp
    evidence.mkdir(parents=True)
    report: dict = {"evidence": str(evidence)}
    with tempfile.TemporaryDirectory(prefix="singh360_leak_sensor_") as raw:
        docs = Path(raw) / ".docs"
        seed_old_library(docs)
        ProjectStore(docs).save(PROJECT_ID, fixture_project())
        port = free_port()
        process = start_server(docs, port, evidence)
        failures: list[str] = []
        console_errors: list[str] = []
        browser = None
        try:
            report["health"] = wait_health(port)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=True)
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("response", lambda response: failures.append(f"{response.status} {response.url}") if response.status >= 400 else None)
                url = f"http://127.0.0.1:{port}/app?project={PROJECT_ID}&mode=editor&workflowAudit=1&renderAudit=1"
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.locator(".ribbon").wait_for(timeout=30_000)
                if page.locator(".panel-rail-left").is_visible():
                    page.locator(".panel-rail-left").click()
                page.locator(".nav-section-head").filter(has_text="Components").click()
                browser_panel = page.locator(".libv2-browser")
                browser_panel.wait_for(timeout=30_000)
                page.get_by_text("Component library ready", exact=True).wait_for(timeout=30_000)
                category = page.get_by_role("combobox", name="Component category")
                collection = page.get_by_role("combobox", name="Component collection")
                if category.input_value() != "all":
                    raise AssertionError("All Components did not clear hidden category state")
                collection.select_option(label="Refrigeration Controls Symbols")
                search = browser_panel.get_by_placeholder("Search components…")
                for sensor in SENSORS:
                    for term in (sensor["code"], sensor["part"], sensor["supplier"]):
                        search.fill(term)
                        expected = 4 if term == "LS" else 2 if term in {"EMC", "REF-LK-832"} else 1
                        page.wait_for_function(
                            "count => document.querySelectorAll('.libv2-browser-card').length === count",
                            arg=expected, timeout=15_000,
                        )
                        if not any(sensor["code"] in text for text in browser_panel.locator(".libv2-browser-card").all_inner_texts()):
                            raise AssertionError(f"search {term!r} did not resolve {sensor['code']}")
                for alias in ("LS2", "LS₂"):
                    search.fill(alias)
                    page.wait_for_function("() => document.querySelectorAll('.libv2-browser-card').length === 1", timeout=15_000)
                    if "LSc" not in browser_panel.locator(".libv2-browser-card").inner_text():
                        raise AssertionError(f"legacy alias {alias!r} did not resolve to LSc")
                search.fill("")
                page.wait_for_function("() => document.querySelectorAll('.libv2-browser-card').length === 4", timeout=15_000)
                visible = browser_panel.inner_text()
                if "LS₂" in visible or "LS2 —" in visible:
                    raise AssertionError("legacy LS2 remains visibly named in Component Browser")
                card = browser_panel.locator(".libv2-browser-card").filter(has_text="LSc —")
                if card.locator("img").evaluate("node => getComputedStyle(node).objectFit") != "contain":
                    raise AssertionError("LSc preview is cropped instead of contain-sized")
                card.click()
                lsc_name = next(s for s in SENSORS if s["code"] == "LSc")
                lsc_display = f"LSc — {lsc_name['description']} — {lsc_name['part']} — {lsc_name['supplier']}"
                page.wait_for_function(
                    "name => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).some(item => item.objName === name)",
                    arg=lsc_display, timeout=20_000,
                )
                lsg_card = browser_panel.locator(".libv2-browser-card").filter(has_text="LSg —")
                lsg_card.drag_to(page.locator(".sheet-viewport"), target_position={"x": 800, "y": 480})
                page.wait_for_function(
                    "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).some(item => String(item.objName).startsWith('LSg —'))",
                    timeout=20_000,
                )
                selected = page.evaluate("name => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByNames([name]) || 0", lsc_display)
                if selected != 1:
                    raise AssertionError("could not select inserted LSc for copy/paste")
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Copy", exact=True).click()
                page.get_by_role("button", name="Paste", exact=True).click()
                page.get_by_role("button", name="File", exact=True).click()
                page.get_by_role("button", name="Save Now", exact=True).click()
                page.wait_for_function(
                    "() => !['UNSAVED PROJECT EDITS','SAVING PROJECT…','SAVE FAILED'].includes(document.querySelector('.save-state-control .status-pill')?.textContent || '')",
                    timeout=30_000,
                )
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.locator(".ribbon").wait_for(timeout=30_000)
                page.wait_for_function(
                    "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).filter(item => String(item.objName).startsWith('LSc —')).length >= 2",
                    timeout=30_000,
                )
                page.screenshot(path=evidence / "leak-sensor-sidebar-and-canvas.png", full_page=True)
                report["savedObjects"] = len(read_project(port)["pages"][0]["canvasObjects"])
                report["pdfBytes"] = export_pdf(port, evidence)
                if failures or console_errors:
                    raise AssertionError(f"browser failures={failures}; console errors={console_errors}")
                browser.close()
                browser = None
            process.terminate()
            process.wait(timeout=20)
            process = start_server(docs, port, evidence)
            report["restartHealth"] = wait_health(port)
            restarted = read_project(port)
            names = [str(item.get("objName") or "") for item in restarted["pages"][0]["canvasObjects"]]
            if sum(name.startswith("LSc —") for name in names) < 2 or not any(name.startswith("LSg —") for name in names):
                raise AssertionError(f"server restart lost leak-sensor objects: {names}")
            report["restartNames"] = names
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
        (evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
