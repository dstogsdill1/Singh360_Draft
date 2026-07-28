"""Isolated browser smoke for delegated tooltip coverage and accessibility."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TOOLTIP_TARGET_SELECTOR = (
    'button,[role="button"],[role="tab"],[role="menuitem"],input,select,textarea,'
    '[draggable="true"],[data-action],[data-status-chip],[data-page-pill],[data-resize-handle]'
)

from core.project_store import ProjectStore
from core.project_workspace import WorkbookDocumentStore
from core.legend_template_store import LegendTemplateStore
from core.library_v2 import LibraryV2
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
            time.sleep(0.2)
    raise RuntimeError("isolated tooltip server did not become healthy")


def assert_audit(page: Page, surface: str) -> dict:
    page.wait_for_function("() => typeof window.__S360_TOOLTIP_AUDIT__ === 'function'")
    page.wait_for_timeout(300)
    audit = page.evaluate("() => window.__S360_TOOLTIP_AUDIT__()")
    if audit["totalVisibleTargets"] < 1:
        raise AssertionError(f"{surface}: no visible tooltip audit targets")
    failures = {
        "missing": audit["missingHelpIds"],
        "invalid": audit["invalidRegistryIds"],
        "duplicates": audit["duplicateIds"],
        "inaccessible": audit["inaccessibleControls"],
    }
    if any(failures.values()):
        raise AssertionError(f"{surface}: tooltip audit failed: {json.dumps(failures, indent=2)}")
    if audit["coveredTargets"] != audit["totalVisibleTargets"]:
        raise AssertionError(f"{surface}: coverage is not complete: {audit}")
    return audit


def assert_tooltip_in_viewport(page: Page) -> None:
    bounds = page.locator("#s360-app-tooltip").bounding_box()
    viewport = page.viewport_size
    if not bounds or not viewport:
        raise AssertionError("tooltip bounds unavailable")
    if (
        bounds["x"] < 0
        or bounds["y"] < 0
        or bounds["x"] + bounds["width"] > viewport["width"] + 0.5
        or bounds["y"] + bounds["height"] > viewport["height"] + 0.5
    ):
        raise AssertionError(f"tooltip escaped viewport: {bounds} / {viewport}")


def exercise_tooltip(page: Page, locator, placements: tuple[str, ...] = ("bottom",)) -> None:
    locator.scroll_into_view_if_needed()
    for placement in placements:
        locator.evaluate("(node, value) => node.dataset.tooltipPlacement = value", placement)
        locator.hover()
        expected_help_id = locator.get_attribute("data-help-id")
        page.wait_for_function(
            """helpId => {
              const tooltip = document.querySelector('#s360-app-tooltip');
              return tooltip && tooltip.getAttribute('data-help-id') === helpId;
            }""",
            arg=expected_help_id,
            timeout=2_000,
        )
        assert_tooltip_in_viewport(page)
        described_by = locator.get_attribute("aria-describedby") or ""
        if "s360-app-tooltip" not in described_by:
            raise AssertionError("hover tooltip did not wire aria-describedby")
        page.mouse.move(1, 1)
        page.wait_for_timeout(180)

    locator.focus()
    page.locator("#s360-app-tooltip[data-opened-by='focus']").wait_for(state="visible", timeout=500)
    page.keyboard.press("Escape")
    page.locator("#s360-app-tooltip").wait_for(state="detached", timeout=1_000)


def exercise_all_visible_tooltips(page: Page, surface: str) -> int:
    targets = page.locator(TOOLTIP_TARGET_SELECTOR)
    exercised = 0
    for index in range(targets.count()):
        target = targets.nth(index)
        if not target.is_visible() or target.get_attribute("type") == "hidden":
            continue
        help_id = target.get_attribute("data-help-id")
        if not help_id:
            raise AssertionError(f"{surface}: visible target {index} has no help ID")
        target.evaluate(
            """node => node.dispatchEvent(new FocusEvent('focusin', {
              bubbles: true,
              composed: true,
            }))"""
        )
        try:
            page.wait_for_function(
                """() => Boolean(document.querySelector('#s360-app-tooltip')?.getAttribute('data-help-id'))""",
                timeout=1_000,
            )
        except Exception as exc:
            actual = page.locator("#s360-app-tooltip").get_attribute("data-help-id") \
                if page.locator("#s360-app-tooltip").count() else ""
            raise AssertionError(
                f"{surface}: target {index} ({help_id}) did not open; active={actual!r}"
            ) from exc
        if not page.locator("#s360-app-tooltip").inner_text().strip():
            raise AssertionError(f"{surface}: {help_id} opened an empty tooltip")
        page.keyboard.press("Escape")
        page.locator("#s360-app-tooltip").wait_for(state="detached", timeout=1_000)
        exercised += 1
    return exercised


def sanitized_project() -> dict:
    layout = layout_page()
    layout.update(
        {
            "order": 2,
            "include": True,
            "publishStatus": "YES",
            "issueStatus": "draft",
            "sheetCode": "EMS T.2",
            "displaySheetCode": "EMS T.2",
            "sheetTitle": "Sanitized Tooltip Layout",
            "pageType": "canvas",
            "templateId": "blank",
            "canvasObjects": [],
            "notes": "",
            "pageNumber": 2,
            "pageTotal": 2,
        }
    )
    page = {
        "id": "regular-page",
        "order": 1,
        "include": True,
        "publishStatus": "YES",
        "issueStatus": "draft",
        "sheetCode": "EMS T.1",
        "displaySheetCode": "EMS T.1",
        "sheetTitle": "Sanitized Tooltip Canvas",
        "sheetTab": "SANITIZED CANVAS",
        "pageType": "canvas",
        "templateId": "blank",
        "blocks": [],
        "canvasObjects": [{"type": "rect", "name": "sanitized-overlay"}],
        "notes": "",
        "pageNumber": 1,
        "pageTotal": 2,
    }
    return {
        "id": "7e57001170017e57",
        "metadata": {"projectName": "Sanitized Tooltip Project"},
        "worksheets": [],
        "pages": [page, layout],
        "sources": [],
        "workbookSync": {
            "status": "app_changed",
            "warning": "Sanitized local project save; workbook sync pending.",
            "localProjectSavedAt": "2026-01-01T00:00:00Z",
            "lastSyncUtc": "2025-12-31T00:00:00Z",
        },
    }


def workspace_document() -> dict:
    return {
        "revision": 0,
        "updatedAt": "",
        "sheets": [
            {
                "id": "source-sheet",
                "name": "SRC_SANITIZED",
                "cells": {"A1": {"v": "Locked metadata"}, "A3": {"v": "Editable value"}},
                "styles": {},
                "merges": [],
                "rowHeights": {},
                "columnWidths": {},
                "defaultColumnWidth": 8.43,
                "defaultRowHeight": 15,
                "hiddenRows": [],
                "hiddenColumns": [],
                "archived": False,
                "tabColor": None,
                "role": "source",
                "sourceSetup": {
                    "authority": "00_INDEX",
                    "sheetCode": "SRC T.1",
                    "title": "Sanitized Source",
                    "publish": "YES",
                    "purpose": "Generated tooltip browser fixture",
                    "editableStartRow": 3,
                    "metadata": [],
                },
                "protectedRanges": ["A1:Z2"],
                "dataValidations": [],
                "conditionalFormats": [],
                "tableRegions": [{"id": "table-1", "range": "A3:A3", "label": "Table 1"}],
                "tableLayout": "single",
                "annotations": [],
            }
        ],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="singh360_tooltip_browser_") as raw:
        runtime = Path(raw)
        docs = runtime / ".docs"
        project = sanitized_project()
        store = ProjectStore(docs)
        store.save(project["id"], project)
        project_dir = store.dir_for(project["id"], project)
        WorkbookDocumentStore(project_dir).save(project, 0, workspace_document())
        library = LibraryV2(docs)
        component_path = library.components / "custom" / "Sanitized_Tooltip_Component.svg"
        component_path.parent.mkdir(parents=True, exist_ok=True)
        component_path.write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' width='80' height='48'>"
            "<rect x='2' y='2' width='76' height='44' fill='white' stroke='black'/>"
            "<text x='40' y='28' text-anchor='middle' font-size='10'>TEST</text></svg>",
            encoding="utf-8",
        )
        library.refresh()
        component = next(
            item for item in library.load().get("components", [])
            if item.get("displayName") == "Sanitized Tooltip Component"
        )
        LegendTemplateStore(docs).save_template(
            name="Sanitized Tooltip Legend",
            category="custom",
            title="Sanitized Symbol Legend",
            rows=[
                {
                    "id": "sanitized-row",
                    "label": "TEST — Sanitized fixture",
                    "componentId": component["id"],
                    "enabled": True,
                }
            ],
        )

        port = free_port()
        env = {**os.environ, "SINGH360_DOCS_DIR": str(docs), "SINGH360_PORT": str(port)}
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        results: dict[str, dict] = {}
        try:
            wait_health(port)
            with sync_playwright() as api:
                browser = api.chromium.launch(
                    executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    headless=True,
                )
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                console_errors: list[str] = []
                failed_responses: list[str] = []
                page.on(
                    "console",
                    lambda message: console_errors.append(
                        f"{message.text} @ {message.location}"
                    ) if message.type == "error" else None,
                )
                page.on("response", lambda response: failed_responses.append(f"{response.status} {response.url}") if response.status >= 400 else None)
                base = f"http://127.0.0.1:{port}/app?project={project['id']}"

                # Load the large Data Workspace bundle in a fresh browser
                # before the longer editor interaction pass.
                page.goto(
                    f"{base}&view=data&tooltipAudit=1",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                page.locator(".univer-host").wait_for(timeout=30_000)
                page.wait_for_timeout(1_500)
                results["dataWorkspace"] = assert_audit(page, "Data Workspace")
                results["dataWorkspace"]["exercisedTooltips"] = exercise_all_visible_tooltips(
                    page, "Data Workspace"
                )
                host = page.locator(".univer-host")
                host.hover(position={"x": 40, "y": 40})
                page.locator("#s360-app-tooltip").wait_for(state="visible", timeout=2_000)
                if page.locator("#s360-app-tooltip").count() != 1:
                    raise AssertionError("Data Workspace created per-cell tooltip nodes")
                if "Save Workspace Edits" not in page.locator("#s360-app-tooltip").inner_text():
                    raise AssertionError("dynamic Data Workspace tooltip did not describe local save")
                browser.close()

                browser = api.chromium.launch(
                    executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    headless=True,
                )
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.on(
                    "console",
                    lambda message: console_errors.append(
                        f"{message.text} @ {message.location}"
                    ) if message.type == "error" else None,
                )
                page.on(
                    "response",
                    lambda response: failed_responses.append(
                        f"{response.status} {response.url}"
                    ) if response.status >= 400 else None,
                )
                page.goto(f"{base}&tooltipAudit=1")
                page.get_by_role("heading", name="Project Home").wait_for(timeout=30_000)
                results["projectHome"] = assert_audit(page, "Project Home")
                results["projectHome"]["exercisedTooltips"] = exercise_all_visible_tooltips(page, "Project Home")
                help_button = page.get_by_role("button", name="Quick Help")
                exercise_tooltip(page, help_button, placements=("top", "bottom", "left", "right"))

                manager_button = page.get_by_role("button", name="Review Drawing Pages")
                manager_button.hover()
                page.locator("#s360-app-tooltip").wait_for(state="visible")
                manager_button.click()
                page.get_by_role("dialog").wait_for(timeout=10_000)
                results["pageManagerModal"] = assert_audit(page, "Visual Page Manager")
                results["pageManagerModal"]["exercisedTooltips"] = exercise_all_visible_tooltips(page, "Visual Page Manager")
                modal_button = page.get_by_role("dialog").get_by_role("button").first
                exercise_tooltip(page, modal_button)

                page.goto(f"{base}&mode=editor&tooltipAudit=1")
                page.locator(".ribbon").wait_for(timeout=30_000)
                results["editor"] = assert_audit(page, "Page Editor")
                results["editor"]["exercisedTooltips"] = exercise_all_visible_tooltips(page, "Page Editor")
                project_home = page.get_by_role("button", name="Project Home")
                exercise_tooltip(page, project_home)
                ribbon_results: dict[str, dict] = {}
                for tab_name in ("File", "Home", "Insert", "Symbols", "Draw", "Text", "Arrange", "View", "Export"):
                    page.locator(".ribbon-tabs").get_by_role(
                        "button", name=tab_name, exact=True
                    ).click()
                    page.wait_for_timeout(100)
                    tab_audit = assert_audit(page, f"Page Editor {tab_name} tab")
                    tab_audit["exercisedTooltips"] = exercise_all_visible_tooltips(
                        page, f"Page Editor {tab_name} tab"
                    )
                    ribbon_results[tab_name] = tab_audit
                results["editorRibbonTabs"] = ribbon_results

                page.get_by_role("button", name="Insert", exact=True).click()
                callout = page.get_by_role("button", name="Callout")
                callout.hover()
                disabled_tip = page.locator("#s360-app-tooltip")
                page.wait_for_function(
                    """() => document.querySelector('#s360-app-tooltip')?.getAttribute('data-help-id') === 'insert.callout'""",
                    timeout=2_000,
                )
                if "Unavailable:" not in disabled_tip.inner_text():
                    raise AssertionError("disabled control did not explain why it is unavailable")

                canvas = page.locator(".canvas-wrap")
                canvas.hover(position={"x": 50, "y": 50})
                page.locator("#s360-app-tooltip").wait_for(state="visible", timeout=2_000)
                if page.locator("#s360-app-tooltip").count() != 1:
                    raise AssertionError("canvas created more than one shared tooltip")
                drag_handles = page.locator('[draggable="true"], [data-resize-handle]')
                if drag_handles.count() and drag_handles.first.get_attribute("draggable") == "false":
                    raise AssertionError("tooltip hydration disabled a drag handle")

                # Generated component + saved legend: actual direct insertion,
                # local save, and reload persistence without customer assets.
                page.get_by_role("button", name="Components", exact=False).click()
                component_card = page.locator(".libv2-card").filter(has_text="Sanitized Tooltip Component")
                component_card.wait_for(timeout=10_000)
                component_card.get_by_role("button", name="Insert", exact=True).click()
                saved_legend_card = page.locator(".libv2-saved-legend-card").filter(
                    has_text="Sanitized Tooltip Legend"
                )
                saved_legend_card.wait_for(timeout=10_000)
                saved_legend_card.click()
                page.get_by_role("heading", name="Build / Insert Symbol Legend").wait_for(timeout=10_000)
                results["savedLegendModal"] = assert_audit(page, "Saved Legend modal")
                results["savedLegendModal"]["exercisedTooltips"] = exercise_all_visible_tooltips(
                    page, "Saved Legend modal"
                )
                page.get_by_role("button", name="Insert legend", exact=True).click()
                page.wait_for_function(
                    """() => document.querySelector('.save-state-control .status-pill')?.textContent
                      === 'UNSAVED PROJECT EDITS'""",
                    timeout=20_000,
                )
                page.keyboard.press("Control+s")
                page.wait_for_function(
                    """() => ![
                      'UNSAVED PROJECT EDITS',
                      'SAVING PROJECT…'
                    ].includes(document.querySelector('.save-state-control .status-pill')?.textContent || '')""",
                    timeout=20_000,
                )
                with urlopen(
                    f"http://127.0.0.1:{port}/api/projects/{project['id']}", timeout=10
                ) as response:
                    saved_project = json.load(response)
                saved_objects = saved_project["pages"][0].get("canvasObjects") or []
                if len(saved_objects) < 3:
                    raise AssertionError(
                        f"direct component and saved legend did not persist: {len(saved_objects)} objects"
                    )

                page.locator(".page-tab").filter(has_text="Sanitized Tooltip Layout").click()
                excel_layout = page.get_by_test_id("excel-layout-canvas")
                excel_layout.wait_for(timeout=10_000)
                results["excelLayout"] = assert_audit(page, "Excel Layout")
                results["excelLayout"]["exercisedTooltips"] = exercise_all_visible_tooltips(
                    page, "Excel Layout"
                )
                exercise_tooltip(page, excel_layout)

                if console_errors:
                    raise AssertionError(f"browser console errors: {console_errors}; responses: {failed_responses}")
                browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

        print(json.dumps({"ok": True, "surfaces": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
