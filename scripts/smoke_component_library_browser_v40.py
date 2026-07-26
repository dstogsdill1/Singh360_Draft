#!/usr/bin/env python3
"""Browser-level smoke for the curated Singh360 V40 Component Library.

The test uses an isolated CI `.docs` runtime and a synthetic canvas project. It
never reads or writes a customer project or workbook.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Page, expect, sync_playwright

from scripts.install_component_library_v40 import PLAN_MARKERS

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("SINGH360_BROWSER_TEST_PORT", "8770"))
BASE_URL = f"http://127.0.0.1:{PORT}"
PROJECT_ID = "f400000000000001"
EVIDENCE_DIR = ROOT / ".validation" / "browser-v40"
SERVER_LOG = EVIDENCE_DIR / "server.log"
REPORT_PATH = EVIDENCE_DIR / "report.json"

EXPECTED_NAMES = [f"{marker['glyph']} — {marker['label']}" for marker in PLAN_MARKERS]
EXPLICIT_INSERTS = [
    "LS₂ — CO2 REFRIGERANT LEAK SENSOR",
    "LI — REFRIGERANT LEAK INDICATOR",
    "EEPR — ELECTRONIC EVAPORATOR PRESSURE REGULATOR",
    "EPR — MECHANICAL EVAPORATOR PRESSURE REGULATOR",
    "WICP — WALK-IN CONTROL PANEL",
]


def project_payload() -> dict[str, Any]:
    return {
        "id": PROJECT_ID,
        "metadata": {
            "projectName": "V40 Component Browser Smoke",
            "storeNumber": "TEST",
            "client": "Singh360",
            "location": "CI",
            "address": "",
            "createdBy": "Singh360 CI",
            "status": "Draft",
        },
        "projectDisplayName": "V40 Component Browser Smoke",
        "worksheets": [],
        "pages": [
            {
                "id": "page_v40_browser",
                "order": 1,
                "include": True,
                "sheetCode": "T0.1",
                "displaySheetCode": "T0.1",
                "sheetTitle": "V40 COMPONENT BROWSER SMOKE",
                "sheetTab": "T0.1",
                "pageType": "canvas",
                "pageFamily": "Image / Layout",
                "renderMode": "canvas",
                "renderProfile": "canvas",
                "template": "canvas",
                "templateId": "ansi-b-standard",
                "blocks": [],
                "canvasObjects": [],
                "notes": "Isolated V40 browser smoke project.",
                "pageGroupId": "page_v40_browser",
            }
        ],
        "assets": [],
        "workbookSync": {},
    }


def wait_for_health(timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/api/health", timeout=2)
            if response.status_code == 200 and response.json().get("ok") is True:
                return
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"Singh360 server did not become healthy: {last_error}")


def seed_project() -> None:
    response = requests.post(
        f"{BASE_URL}/api/projects/{PROJECT_ID}",
        json=project_payload(),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    pages = payload.get("pages") or []
    if len(pages) != 1 or pages[0].get("pageType") != "canvas":
        raise AssertionError(f"Synthetic browser project was not saved correctly: {payload}")


def project_objects(page: Page) -> list[dict[str, Any]]:
    result = page.evaluate(
        """async (projectId) => {
          const response = await fetch(`/api/projects/${projectId}`, { cache: 'no-store' });
          if (!response.ok) throw new Error(await response.text());
          const project = await response.json();
          return project.pages?.[0]?.canvasObjects ?? [];
        }""",
        PROJECT_ID,
    )
    return list(result or [])


def wait_for_object_count(page: Page, expected: int, timeout_ms: int = 30000) -> list[dict[str, Any]]:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        last = project_objects(page)
        if len(last) >= expected:
            return last
        page.wait_for_timeout(250)
    raise AssertionError(f"Timed out waiting for {expected} persisted objects; last count={len(last)}")


def assert_editor_ready(page: Page) -> None:
    expect(page.get_by_role("button", name="Drawing", exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_role("button", name="Included in Drawing Set", exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_role("button", name=re.compile(r"^1 T0\.1 V40 COMPONENT BROWSER SMOKE$"))).to_be_visible(timeout=30000)


def open_components(page: Page) -> None:
    components = page.get_by_role("button", name=re.compile(r"Components$"))
    if components.count() == 0:
        navigation = page.get_by_role("button", name=re.compile(r"Navigate$"))
        expect(navigation).to_be_visible(timeout=30000)
        navigation.click()
    expect(components).to_be_visible(timeout=30000)
    if components.get_attribute("aria-expanded") != "true":
        components.click()
    plan_button = page.get_by_role("button", name=re.compile(r"^Plan Markers \(24\)$"))
    expect(plan_button).to_be_visible(timeout=30000)
    if plan_button.get_attribute("aria-pressed") != "true":
        plan_button.click()
    expect(page.locator(".libv2-card")).to_have_count(24, timeout=30000)


def assert_library(page: Page) -> None:
    names = [text.strip() for text in page.locator(".libv2-name").all_text_contents()]
    if names != EXPECTED_NAMES:
        raise AssertionError(f"Plan Marker order mismatch:\nexpected={EXPECTED_NAMES}\nactual={names}")
    expect(page.locator(".libv2-card img")).to_have_count(24, timeout=30000)
    expect(page.get_by_role("button", name="Mapper Highlights (15)")).to_be_visible()
    expect(page.get_by_role("button", name="Plan Markers (24)")).to_be_visible()
    expect(page.get_by_text("Symbol Mapper Highlight Legend", exact=True)).to_be_visible()
    expect(page.get_by_text("Singh360 Plan Marker Legend", exact=True)).to_be_visible()
    expect(page.get_by_text("Safety Signage Legend", exact=True)).to_be_visible()


def insert_component(page: Page, display_name: str, expected_count: int) -> list[dict[str, Any]]:
    card = page.locator(".libv2-card").filter(has_text=display_name).first
    expect(card).to_be_visible()
    insert = card.get_by_role("button", name="Insert", exact=True)
    expect(insert).to_be_enabled()
    insert.click()
    return wait_for_object_count(page, expected_count)


def run_browser() -> dict[str, Any]:
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1200}, device_scale_factor=1)
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(f"{BASE_URL}/app?project={PROJECT_ID}&mode=editor", wait_until="domcontentloaded", timeout=60000)
        assert_editor_ready(page)
        open_components(page)
        assert_library(page)
        page.screenshot(path=str(EVIDENCE_DIR / "01-plan-marker-library.png"), full_page=True)

        objects: list[dict[str, Any]] = []
        for expected_count, display_name in enumerate(EXPLICIT_INSERTS, start=1):
            objects = insert_component(page, display_name, expected_count)

        source_urls = [str(obj.get("sourceUrl") or obj.get("src") or "") for obj in objects]
        if len(objects) != len(EXPLICIT_INSERTS):
            raise AssertionError(f"Direct marker insertion count mismatch: {len(objects)}")
        if not all("/plan_markers/" in url for url in source_urls):
            raise AssertionError(f"One or more direct inserts did not use V40 plan-marker SVGs: {source_urls}")
        page.screenshot(path=str(EVIDENCE_DIR / "02-direct-plan-markers.png"), full_page=True)

        saved_legend_card = page.locator(".libv2-saved-legend-card").filter(has_text="Singh360 Plan Marker Legend")
        expect(saved_legend_card).to_be_visible()
        saved_legend_card.click()
        expect(page.get_by_role("heading", name="Build / Insert Symbol Legend")).to_be_visible(timeout=30000)
        exact_previews = page.locator(".symbol-legend-live-preview .symbol-legend-built-marker.exact-canonical img")
        expect(exact_previews).to_have_count(24, timeout=30000)
        page.screenshot(path=str(EVIDENCE_DIR / "03-plan-marker-legend.png"), full_page=True)
        page.get_by_role("button", name="Insert legend", exact=True).click()
        objects = wait_for_object_count(page, len(EXPLICIT_INSERTS) + 1)
        if len(objects) != len(EXPLICIT_INSERTS) + 1:
            raise AssertionError(f"Plan legend did not insert as one grouped object: {len(objects)}")

        page.reload(wait_until="domcontentloaded", timeout=60000)
        assert_editor_ready(page)
        persisted = wait_for_object_count(page, len(EXPLICIT_INSERTS) + 1)
        page.screenshot(path=str(EVIDENCE_DIR / "04-after-reload.png"), full_page=True)
        if len(persisted) != len(EXPLICIT_INSERTS) + 1:
            raise AssertionError(f"Reload persistence changed object count: {len(persisted)}")
        if page_errors:
            raise AssertionError(f"Browser page errors: {page_errors}")
        browser.close()
        return {
            "ok": True,
            "projectId": PROJECT_ID,
            "planMarkerCards": 24,
            "directInsertedObjects": len(EXPLICIT_INSERTS),
            "planLegendRows": 24,
            "objectsAfterLegend": len(EXPLICIT_INSERTS) + 1,
            "objectsAfterReload": len(persisted),
            "screenshots": sorted(path.name for path in EVIDENCE_DIR.glob("*.png")),
        }


def main() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SINGH360_PORT"] = str(PORT)
    with SERVER_LOG.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_for_health()
            seed_project()
            report = run_browser()
            REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
        except BaseException:
            if process.poll() is not None:
                log.flush()
                print("--- Singh360 server log tail ---", file=sys.stderr)
                print(SERVER_LOG.read_text(encoding="utf-8", errors="replace")[-12000:], file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
