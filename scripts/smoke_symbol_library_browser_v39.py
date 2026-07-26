#!/usr/bin/env python3
"""Browser-level smoke for the exact V39 refrigeration Component Library.

This test uses an isolated CI `.docs` workspace and a synthetic canvas project.
It never reads or writes a customer workbook or live project package.
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

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("SINGH360_BROWSER_TEST_PORT", "8766"))
BASE_URL = f"http://127.0.0.1:{PORT}"
PROJECT_ID = "f390000000000001"
EVIDENCE_DIR = ROOT / ".validation" / "browser-v39"
SERVER_LOG = EVIDENCE_DIR / "server.log"
REPORT_PATH = EVIDENCE_DIR / "report.json"

EXPECTED_NAMES = [
    "TS — TEMPERATURE SENSOR",
    "DA — DOOR ALARM",
    "LS — REFRIGERANT LEAK DETECTION SENSOR",
    "LS₂ — CO2 REFRIGERANT LEAK SENSOR",
    "LI — REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM",
    "LI₂ — CO2 REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM",
    "CC — RDM CASE CONTROLLER",
    "DTS — DUAL TEMPERATURE SWITCH",
    "HT — HIGH TEMPERATURE ALARM STROBE (AMBER)",
    "ES — WALK-IN FREEZER ENTRAPMENT SWITCH",
    "AS — ALARM STROBE (RED)",
    "EA — ENTRAPMENT ALARM",
    "S — LIQUID LINE SOLENOID VALVE 120V",
    "DT — DEFROST TERMINATION SENSOR",
    "$ — CLEAN SWITCH",
]

EXPLICIT_INSERTS = [
    ("DA — DOOR ALARM", "02-da-inserted.png"),
    ("LS — REFRIGERANT LEAK DETECTION SENSOR", "03-ls-inserted.png"),
    ("LS₂ — CO2 REFRIGERANT LEAK SENSOR", "04-ls2-inserted.png"),
    ("LI — REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM", "05-li-inserted.png"),
    ("LI₂ — CO2 REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM", "06-li2-inserted.png"),
    ("CC — RDM CASE CONTROLLER", "07-cc-inserted.png"),
    ("$ — CLEAN SWITCH", "08-clean-switch-inserted.png"),
]

ALIAS_EXPECTATIONS = {
    "LS₂": "LS₂ — CO2 REFRIGERANT LEAK SENSOR",
    "LS2": "LS₂ — CO2 REFRIGERANT LEAK SENSOR",
    "LSC": "LS₂ — CO2 REFRIGERANT LEAK SENSOR",
    "CO2 LEAK SENSOR": "LS₂ — CO2 REFRIGERANT LEAK SENSOR",
    "CO₂ LEAK SENSOR": "LS₂ — CO2 REFRIGERANT LEAK SENSOR",
    "LI₂": "LI₂ — CO2 REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM",
    "LI2": "LI₂ — CO2 REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM",
    "CO2 LEAK INDICATOR": "LI₂ — CO2 REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM",
    "CO₂ LEAK INDICATOR": "LI₂ — CO2 REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM",
}


def _project_payload() -> dict[str, Any]:
    return {
        "id": PROJECT_ID,
        "metadata": {
            "projectName": "V39 Browser Smoke",
            "storeNumber": "TEST",
            "client": "Singh360",
            "location": "CI",
            "address": "",
            "createdBy": "Singh360 CI",
            "status": "Draft",
        },
        "projectDisplayName": "V39 Browser Smoke",
        "worksheets": [],
        "pages": [
            {
                "id": "page_v39_browser",
                "order": 1,
                "include": True,
                "sheetCode": "T0.1",
                "displaySheetCode": "T0.1",
                "sheetTitle": "V39 SYMBOL BROWSER SMOKE",
                "sheetTab": "T0.1",
                "pageType": "canvas",
                "pageFamily": "Image / Layout",
                "renderMode": "canvas",
                "renderProfile": "canvas",
                "template": "canvas",
                "templateId": "ansi-b-standard",
                "blocks": [],
                "canvasObjects": [],
                "notes": "Isolated browser smoke project.",
                "pageGroupId": "page_v39_browser",
            }
        ],
        "assets": [],
        "workbookSync": {},
    }


def _wait_for_health(timeout_seconds: float = 30.0) -> None:
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


def _seed_project() -> None:
    response = requests.post(
        f"{BASE_URL}/api/projects/{PROJECT_ID}",
        json=_project_payload(),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    pages = payload.get("pages") or []
    if len(pages) != 1 or pages[0].get("pageType") != "canvas":
        raise AssertionError(f"Synthetic browser project was not saved correctly: {payload}")


def _project_objects(page: Page) -> list[dict[str, Any]]:
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


def _wait_for_object_count(page: Page, expected: int, timeout_ms: int = 30000) -> list[dict[str, Any]]:
    page.wait_for_function(
        """async ({ projectId, expected }) => {
          const response = await fetch(`/api/projects/${projectId}`, { cache: 'no-store' });
          if (!response.ok) return false;
          const project = await response.json();
          return (project.pages?.[0]?.canvasObjects?.length ?? 0) >= expected;
        }""",
        arg={"projectId": PROJECT_ID, "expected": expected},
        timeout=timeout_ms,
    )
    return _project_objects(page)


def _assert_editor_ready(page: Page) -> None:
    expect(page.get_by_role("button", name="Drawing", exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_role("button", name="Included in Drawing Set", exact=True)).to_be_visible(timeout=30000)
    expect(
        page.get_by_role("button", name=re.compile(r"^1 T0\.1 V39 SYMBOL BROWSER SMOKE$"))
    ).to_be_visible(timeout=30000)


def _open_components(page: Page) -> None:
    components = page.get_by_role("button", name=re.compile(r"Components$"))
    if components.count() == 0:
        navigation = page.get_by_role("button", name=re.compile(r"Navigate$"))
        expect(navigation).to_be_visible(timeout=30000)
        navigation.click()
    expect(components).to_be_visible(timeout=30000)
    if components.get_attribute("aria-expanded") != "true":
        components.click()
    filter_button = page.get_by_role("button", name=re.compile(r"^Refrigeration Symbols \(15\)$"))
    expect(filter_button).to_be_visible(timeout=30000)
    if filter_button.get_attribute("aria-pressed") != "true":
        filter_button.click()
    expect(page.locator(".libv2-card")).to_have_count(15, timeout=30000)


def _assert_library(page: Page) -> None:
    names = [text.strip() for text in page.locator(".libv2-name").all_text_contents()]
    if names != EXPECTED_NAMES:
        raise AssertionError(f"Canonical card order mismatch:\nexpected={EXPECTED_NAMES}\nactual={names}")
    if page.locator(".libv2-card img").count() != 15:
        raise AssertionError("Every canonical card must display its exact SVG preview.")
    expect(page.get_by_text("Saved Symbol Legends", exact=True)).to_be_visible()
    expect(page.get_by_text("Singh360 Refrigeration Symbols", exact=True)).to_be_visible()
    health = page.locator(".libv2-health").inner_text().strip()
    if not health.startswith("15 shown · 15 total"):
        raise AssertionError(f"Unexpected Component Library health text: {health}")


def _assert_aliases(page: Page) -> None:
    search = page.get_by_placeholder("Search components…")
    for alias, expected_name in ALIAS_EXPECTATIONS.items():
        search.fill(alias)
        expect(page.locator(".libv2-card")).to_have_count(1, timeout=10000)
        expect(page.locator(".libv2-name")).to_have_text(expected_name)
    search.fill("")
    expect(page.locator(".libv2-card")).to_have_count(15, timeout=10000)


def _insert_component(page: Page, display_name: str, screenshot_name: str, expected_count: int) -> list[dict[str, Any]]:
    card = page.locator(".libv2-card").filter(has_text=display_name).first
    expect(card).to_be_visible()
    insert = card.get_by_role("button", name="Insert", exact=True)
    expect(insert).to_be_enabled()
    insert.click()
    objects = _wait_for_object_count(page, expected_count)
    page.screenshot(path=str(EVIDENCE_DIR / screenshot_name), full_page=True)
    return objects


def _run_browser() -> dict[str, Any]:
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1200}, device_scale_factor=1)
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(f"{BASE_URL}/app?project={PROJECT_ID}&mode=editor", wait_until="domcontentloaded", timeout=60000)
        _assert_editor_ready(page)

        _open_components(page)
        _assert_library(page)
        _assert_aliases(page)
        page.screenshot(path=str(EVIDENCE_DIR / "01-corrected-component-library.png"), full_page=True)

        expected_count = 0
        objects: list[dict[str, Any]] = []
        for display_name, screenshot_name in EXPLICIT_INSERTS:
            expected_count += 1
            objects = _insert_component(page, display_name, screenshot_name, expected_count)

        source_urls = [str(obj.get("sourceUrl") or "") for obj in objects]
        required_fragments = [
            "__da__door-alarm.svg",
            "__ls__refrigerant-leak-detection-sensor.svg",
            "__ls2__co2-refrigerant-leak-sensor.svg",
            "__li__refrigerant-leak-indicator-audio-visual-alarm.svg",
            "__li2__co2-refrigerant-leak-indicator-audio-visual-alarm.svg",
            "__cc__rdm-case-controller.svg",
            "__s__clean-switch.svg",
        ]
        for fragment in required_fragments:
            if not any(fragment in url for url in source_urls):
                raise AssertionError(f"Inserted project objects are missing canonical source SVG: {fragment}")
        if len(objects) != 7:
            raise AssertionError(f"Direct insertion must add exactly seven independent objects, got {len(objects)}")

        saved_legend_card = page.locator(".libv2-saved-legend-card").filter(has_text="Singh360 Refrigeration Symbols")
        expect(saved_legend_card).to_be_visible()
        saved_legend_card.click()
        expect(page.get_by_role("heading", name="Build / Insert Symbol Legend")).to_be_visible(timeout=30000)
        exact_preview_count = page.locator(".symbol-legend-built-marker.exact-canonical img").count()
        if exact_preview_count < 15:
            raise AssertionError(f"Saved legend must render all 15 exact canonical SVG previews; got {exact_preview_count}")
        page.screenshot(path=str(EVIDENCE_DIR / "09-saved-full-legend.png"), full_page=True)

        page.get_by_role("button", name="Insert legend", exact=True).click()
        objects = _wait_for_object_count(page, 8)
        page.screenshot(path=str(EVIDENCE_DIR / "10-saved-legend-inserted.png"), full_page=True)
        if len(objects) != 8:
            raise AssertionError(f"Saved legend insertion must add one grouped object, got {len(objects)} total objects")

        page.reload(wait_until="domcontentloaded", timeout=60000)
        _assert_editor_ready(page)
        persisted = _wait_for_object_count(page, 8)
        page.screenshot(path=str(EVIDENCE_DIR / "11-after-reload-persistence.png"), full_page=True)
        if len(persisted) != 8:
            raise AssertionError(f"Reload persistence changed the object count: {len(persisted)}")
        if page_errors:
            raise AssertionError(f"Browser page errors: {page_errors}")

        browser.close()
        return {
            "ok": True,
            "projectId": PROJECT_ID,
            "canonicalCards": 15,
            "aliasQueries": list(ALIAS_EXPECTATIONS),
            "directInsertedObjects": 7,
            "savedLegendRows": 15,
            "objectsAfterLegend": 8,
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
            _wait_for_health()
            _seed_project()
            report = _run_browser()
            REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
        except BaseException:
            if process.poll() is not None:
                log.flush()
                tail = SERVER_LOG.read_text(encoding="utf-8", errors="replace")[-12000:]
                print("--- Singh360 server log tail ---", file=sys.stderr)
                print(tail, file=sys.stderr)
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
