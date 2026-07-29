"""Disposable browser smoke for order, workspace navigation, validation, and tips."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.project_store import ProjectStore
from core.project_workspace import (
    WorkbookDocumentStore,
    drawing_workspace_sequence,
)
from core.workbook_status_sync import sync_project_to_workbook
from tests.test_sync_order_reconciliation import (
    document_for,
    fixture_project,
    write_fixture_workbook,
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int) -> None:
    for _ in range(180):
        try:
            if urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=1
            ).status == 200:
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("disposable sync-order server did not become healthy")


def assert_source_contract() -> None:
    workspace = (
        ROOT / "frontend/src/workspace/DataWorkspace.tsx"
    ).read_text(encoding="utf-8")
    provider = (
        ROOT / "frontend/src/components/help/TooltipProvider.tsx"
    ).read_text(encoding="utf-8")
    tooltip = (
        ROOT / "frontend/src/components/help/AppTooltip.tsx"
    ).read_text(encoding="utf-8")
    host = re.search(
        r'<div\s+ref=\{containerRef\}.*?/>',
        workspace,
        flags=re.DOTALL,
    )
    if not host or "data-help-id" in host.group(0) or "data-tooltip-body" in host.group(0):
        raise AssertionError("Univer grid still has a rich-tooltip target")
    required = [
        "baselineValidationErrorsRef",
        "strictValidationDetail",
        "newly introduced strict-dropdown values",
        "await restoreDocument(confirmed",
        "worksheet.getTabColor()",
        "event.type !== CommandType.COMMAND",
        "TAB_COLOR_COMMAND_IDS.has(event.id)",
        'data-testid="data-workspace-shell"',
        'data-testid="drawing-pages-strip"',
        'data-testid="drawing-page-tab"',
        "data-help-id=\"workspace.discard\"",
        "data-help-id=\"dialog.cancel\"",
        "workspaceSection === 'drawing'",
    ]
    missing = [value for value in required if value not in workspace]
    if missing:
        raise AssertionError(f"workspace repair contract is missing: {missing}")
    if "HOVER_DELAY_MS = 650" not in provider or provider.count("modalIsOpen()") < 3:
        raise AssertionError("tooltip delay/modal suppression contract is missing")
    if '[role="dialog"][aria-modal="true"]' not in tooltip:
        raise AssertionError("AppTooltip does not independently suppress dialogs")


def browser_evidence_dir() -> Path:
    configured = os.environ.get("SINGH360_BROWSER_EVIDENCE_DIR", "").strip()
    return (
        Path(configured)
        if configured
        else ROOT / ".tmp" / "sync_order_workspace_browser_evidence_20260729" / "smoke"
    )


def capture_browser_evidence(
    page,
    *,
    stage: str,
    title: str,
    console_messages: list[dict[str, str]],
    page_errors: list[str],
    api_responses: list[dict[str, Any]],
    detail: str = "",
) -> tuple[Path, dict[str, Any]]:
    evidence = browser_evidence_dir()
    evidence.mkdir(parents=True, exist_ok=True)
    dom: dict[str, Any]
    try:
        dom = page.locator("body").evaluate(
            """() => {
              const shell = document.querySelector('[data-testid="data-workspace-shell"]');
              const strip = document.querySelector('[data-testid="drawing-pages-strip"]');
              const stripTabs = Array.from(
                document.querySelectorAll('[data-testid="drawing-page-tab"]')
              );
              const allTabs = Array.from(document.querySelectorAll('[role="tab"]'));
              return {
                shellExists: Boolean(shell),
                shellState: shell?.getAttribute('data-workspace-state') || '',
                shellOuterHtml: shell?.outerHTML || '',
                stripExists: Boolean(strip),
                stripReady: strip?.getAttribute('data-ready') || '',
                stripTabCount: stripTabs.length,
                stripTabLabels: stripTabs.map((item) => item.textContent?.trim() || ''),
                allRoleTabCount: allTabs.length,
                roleTabsElsewhere: allTabs.some((item) => !strip?.contains(item)),
                univerHostExists: Boolean(document.querySelector('.univer-host')),
                loadingExists: Boolean(document.querySelector('.data-workspace-loading')),
                status: document.querySelector('.workspace-status')?.textContent?.trim() || '',
                message: document.querySelector('.data-message')?.textContent?.trim() || '',
                bodyTextStart: (document.body?.innerText || '').slice(0, 1200),
              };
            }""",
            timeout=2_000,
        )
    except Exception as error:
        dom = {"captureError": str(error)}

    shell_html = str(dom.pop("shellOuterHtml", ""))
    (evidence / f"{stage}_data_workspace_shell.html").write_text(
        shell_html,
        encoding="utf-8",
    )
    screenshot_error = ""
    try:
        page.screenshot(
            path=str(evidence / f"{stage}_full_page.png"),
            full_page=True,
            timeout=5_000,
        )
    except Exception as error:
        screenshot_error = str(error)
    summary = {
        "stage": stage,
        "detail": detail,
        "url": page.url,
        "title": title,
        "dom": dom,
        "consoleMessages": console_messages[-500:],
        "pageErrors": page_errors,
        "apiResponses": api_responses,
        "screenshotError": screenshot_error,
    }
    path = evidence / f"{stage}_diagnostics.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path, summary


def main() -> int:
    assert_source_contract()
    with tempfile.TemporaryDirectory(prefix="s360_sync_order_browser_") as raw:
        runtime = Path(raw)
        docs = runtime / "runtime-docs"
        workbook_path = runtime / "disposable-order.xlsx"
        write_fixture_workbook(workbook_path)
        project = fixture_project(workbook_path)
        project_id = "a1b2c3d4e5f60718"
        project["id"] = project_id
        project["workbookSync"]["workbook"] = str(workbook_path)
        store = ProjectStore(docs)
        store.save(project_id, project)
        project_dir = store.dir_for(project_id, project)
        document_store = WorkbookDocumentStore(project_dir)
        document_store.save(project, 0, document_for(project))

        synced = sync_project_to_workbook(
            project_id,
            project,
            store,
        )
        if not synced.get("workbookSync", {}).get("verified"):
            raise AssertionError("disposable workbook did not complete verification")
        document = document_store.load(synced)
        cover = next(
            sheet for sheet in document["sheets"] if sheet["name"] == "Cover"
        )
        cover["role"] = "source"
        cover["sourceSetup"] = {
            "authority": "00_INDEX",
            "sheetCode": "EMS 0.0",
            "title": "Cover / Project Info",
            "purpose": "Sanitized browser navigation fixture",
            "editableStartRow": 3,
            "metadata": [],
        }
        cover["cells"]["A3"] = {"v": "LEGACY INVALID"}
        cover["dataValidations"] = [
            {
                "id": "strict-cover-choice",
                "ranges": ["A3:A3"],
                "type": "list",
                "formula1": '"YES,NO"',
                "values": ["YES", "NO"],
                "allowBlank": False,
                "showDropdown": True,
                "showErrorMessage": True,
                "strict": True,
            }
        ]
        document_store.save(synced, document["revision"], document)

        port = free_port()
        env = {
            **os.environ,
            "SINGH360_DOCS_DIR": str(docs),
            "SINGH360_PORT": str(port),
        }
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        console_errors: list[str] = []
        console_messages: list[dict[str, str]] = []
        page_errors: list[str] = []
        api_responses: list[dict[str, Any]] = []
        try:
            wait_health(port)
            with sync_playwright() as playwright:
                edge = Path(
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                )
                launch = (
                    {"executable_path": str(edge), "headless": True}
                    if edge.is_file()
                    else {"headless": True}
                )
                browser = playwright.chromium.launch(**launch)
                page = browser.new_page(viewport={"width": 1500, "height": 900})

                def record_console(message) -> None:
                    record = {"type": message.type, "text": message.text}
                    console_messages.append(record)
                    if message.type == "error":
                        console_errors.append(message.text)

                def record_response(response) -> None:
                    if f"/api/projects/{project_id}" not in response.url:
                        return
                    api_responses.append(
                        {
                            "method": response.request.method,
                            "url": response.url,
                            "status": response.status,
                            "statusText": response.status_text,
                        }
                    )

                page.on("console", record_console)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("response", record_response)
                data_url = (
                    f"http://127.0.0.1:{port}/app"
                    f"?project={project_id}&view=data&tooltipAudit=1"
                )
                editor_url = (
                    f"http://127.0.0.1:{port}/app"
                    f"?project={project_id}&mode=editor"
                )
                expected_drawing_pages = [
                    ("page-cover", "EMS 0.0", "Cover"),
                    ("page-index", "EMS 0.1", "00_INDEX"),
                    ("page-gamma", "EMS 3.0", "GAMMA"),
                    ("page-alpha", "EMS 1.0", "ALPHA"),
                    ("page-beta", "EMS 2.0", "BETA"),
                ]
                workspace_open_count = 0

                def open_workspace() -> list[dict[str, str]]:
                    nonlocal workspace_open_count
                    workspace_open_count += 1
                    page.goto(
                        data_url,
                        wait_until="domcontentloaded",
                        timeout=60_000,
                    )
                    title = page.title()
                    ready = page.locator(
                        '[data-testid="data-workspace-shell"][data-workspace-state="ready"] '
                        '[data-testid="drawing-pages-strip"][data-ready="true"]'
                    )
                    try:
                        ready.wait_for(state="visible", timeout=10_000)
                    except PlaywrightTimeoutError as error:
                        evidence_path, summary = capture_browser_evidence(
                            page,
                            stage=f"workspace_{workspace_open_count}_not_ready",
                            title=title,
                            console_messages=console_messages,
                            page_errors=page_errors,
                            api_responses=api_responses,
                            detail=str(error),
                        )
                        raise AssertionError(
                            "Data Workspace Drawing Pages did not reach its semantic ready "
                            f"state. Evidence: {evidence_path}. Diagnostics: "
                            f"{json.dumps(summary, sort_keys=True)[:4000]}"
                        ) from error

                    records = page.get_by_test_id("drawing-pages-strip").evaluate(
                        """(strip) => Array.from(
                          strip.querySelectorAll('[data-testid="drawing-page-tab"]')
                        ).map((tab) => ({
                          pageId: tab.getAttribute('data-page-id') || '',
                          sheetCode: tab.getAttribute('data-sheet-code') || '',
                          sheetTab: tab.getAttribute('data-sheet-tab') || '',
                          order: tab.getAttribute('data-drawing-order') || '',
                          label: tab.textContent?.trim() || '',
                        }))""",
                        timeout=3_000,
                    )
                    actual = [
                        (record["pageId"], record["sheetCode"], record["sheetTab"])
                        for record in records
                    ]
                    if actual != expected_drawing_pages:
                        evidence_path, summary = capture_browser_evidence(
                            page,
                            stage=f"workspace_{workspace_open_count}_order_mismatch",
                            title=title,
                            console_messages=console_messages,
                            page_errors=page_errors,
                            api_responses=api_responses,
                            detail=f"expected={expected_drawing_pages!r}; actual={actual!r}",
                        )
                        raise AssertionError(
                            "Drawing Pages semantic order mismatch. "
                            f"Evidence: {evidence_path}. Diagnostics: "
                            f"{json.dumps(summary, sort_keys=True)[:4000]}"
                        )
                    if any(
                        record["order"] != str(index)
                        for index, record in enumerate(records, start=1)
                    ):
                        raise AssertionError(
                            f"Drawing Pages order attributes are not contiguous: {records}"
                        )
                    return records

                initial_records = open_workspace()
                initial_statuses = {
                    (item["method"], item["url"].split("?")[0]): item["status"]
                    for item in api_responses
                }
                expected_project_url = f"http://127.0.0.1:{port}/api/projects/{project_id}"
                expected_workspace_url = expected_project_url + "/data-workspace"
                if initial_statuses.get(("GET", expected_project_url)) != 200:
                    raise AssertionError(
                        f"project API did not return 200: {api_responses}"
                    )
                if initial_statuses.get(("GET", expected_workspace_url)) != 200:
                    raise AssertionError(
                        f"Data Workspace API did not return 200: {api_responses}"
                    )
                capture_browser_evidence(
                    page,
                    stage="workspace_ready",
                    title=page.title(),
                    console_messages=console_messages,
                    page_errors=page_errors,
                    api_responses=api_responses,
                    detail=f"drawingPages={initial_records!r}",
                )

                project_home = page.get_by_role("button", name="Project Home")
                project_home.hover()
                page.wait_for_timeout(750)
                if page.locator("#s360-app-tooltip").count() != 1:
                    raise AssertionError("normal delayed control tooltip did not appear")
                host = page.locator(".univer-host")
                host.hover(position={"x": 650, "y": 450})
                page.wait_for_timeout(750)
                if page.locator("#s360-app-tooltip").count():
                    raise AssertionError("spreadsheet grid produced a rich tooltip")

                right_note = page.get_by_label("Right-side note")
                right_note.fill("discard candidate")
                page.get_by_role("button", name="Page Editor").click()
                dialog = page.get_by_role("dialog")
                dialog.wait_for(timeout=5_000)
                dialog.get_by_role("button", name="Cancel").hover()
                page.wait_for_timeout(750)
                if page.locator("#s360-app-tooltip").count():
                    raise AssertionError("rich tooltip appeared while a dialog was open")
                dialog.get_by_role("button", name="Cancel").click()
                if right_note.input_value() != "discard candidate":
                    raise AssertionError("Cancel changed in-memory edits")

                page.get_by_role("button", name="Page Editor").click()
                page.get_by_role("dialog").get_by_role(
                    "button", name="Discard"
                ).click()
                page.wait_for_url(editor_url, timeout=30_000)
                open_workspace()
                if page.get_by_label("Right-side note").input_value():
                    raise AssertionError("Discard did not restore the confirmed snapshot")

                right_note = page.get_by_label("Right-side note")
                right_note.fill("failure remains in memory")

                def fail_save(route) -> None:
                    if route.request.method == "PUT":
                        route.fulfill(
                            status=500,
                            content_type="application/json",
                            body=json.dumps(
                                {
                                    "error": "Disposable save failure",
                                    "detail": "Exact generated failure detail",
                                }
                            ),
                        )
                    else:
                        route.continue_()

                page.route("**/api/projects/*/data-workspace", fail_save)
                page.get_by_role("button", name="Page Editor").click()
                page.get_by_role("dialog").get_by_role(
                    "button", name="Save"
                ).click()
                try:
                    page.wait_for_function(
                        """() => document.querySelector('.data-message')?.textContent
                          ?.includes('Exact generated failure detail')""",
                        timeout=10_000,
                    )
                except PlaywrightTimeoutError as error:
                    evidence_path, summary = capture_browser_evidence(
                        page,
                        stage="save_failure_detail_missing",
                        title=page.title(),
                        console_messages=console_messages,
                        page_errors=page_errors,
                        api_responses=api_responses,
                        detail=str(error),
                    )
                    raise AssertionError(
                        "Injected save failure detail was not rendered. "
                        f"Evidence: {evidence_path}. Diagnostics: "
                        f"{json.dumps(summary, sort_keys=True)[:4000]}"
                    ) from error
                if "view=data" not in page.url:
                    raise AssertionError("save failure navigated away from Data Workspace")
                if page.get_by_label("Right-side note").input_value() != "failure remains in memory":
                    raise AssertionError("save failure discarded in-memory edits")
                page.get_by_role("dialog").get_by_role(
                    "button", name="Cancel"
                ).click()
                page.unroute("**/api/projects/*/data-workspace", fail_save)

                page.get_by_role("button", name="Page Editor").click()
                page.get_by_role("dialog").get_by_role(
                    "button", name="Discard"
                ).click()
                page.wait_for_url(editor_url, timeout=30_000)
                open_workspace()

                bottom_note = page.get_by_label("Bottom note")
                bottom_note.fill("saved with legacy invalid dropdown")
                page.get_by_role("button", name="Page Editor").click()
                page.get_by_role("dialog").get_by_role(
                    "button", name="Save"
                ).click()
                try:
                    page.wait_for_url(editor_url, timeout=30_000)
                except PlaywrightTimeoutError as error:
                    evidence_path, summary = capture_browser_evidence(
                        page,
                        stage="final_save_navigation_missing",
                        title=page.title(),
                        console_messages=console_messages,
                        page_errors=page_errors,
                        api_responses=api_responses,
                        detail=str(error),
                    )
                    raise AssertionError(
                        "Final local Save did not navigate after confirmation. "
                        f"Evidence: {evidence_path}. Diagnostics: "
                        f"{json.dumps(summary, sort_keys=True)[:4000]}"
                    ) from error
                open_workspace()
                if (
                    page.get_by_label("Bottom note").input_value()
                    != "saved with legacy invalid dropdown"
                ):
                    raise AssertionError(
                        "pre-existing invalid dropdown blocked a valid unrelated save"
                    )

                capture_browser_evidence(
                    page,
                    stage="success_final",
                    title=page.title(),
                    console_messages=console_messages,
                    page_errors=page_errors,
                    api_responses=api_responses,
                    detail=f"workspaceReloads={workspace_open_count}",
                )
                browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        final_project = store.load(project_id)
        if final_project is None:
            raise AssertionError("disposable project disappeared")
        final_document = WorkbookDocumentStore(
            store.dir_for(project_id, final_project)
        ).load(final_project)
        final_order = [
            item["sheetTab"] for item in drawing_workspace_sequence(final_document)
        ]
        if final_order != ["Cover", "00_INDEX", "GAMMA", "ALPHA", "BETA"]:
            raise AssertionError(f"saved Drawing Pages order drifted: {final_order}")
        unexpected = [
            message
            for message in console_errors
            if "500" not in message and "Disposable save failure" not in message
        ]
        if unexpected:
            raise AssertionError(f"browser console errors: {unexpected}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "disposableDocs": str(docs),
                    "disposableWorkbook": str(workbook_path),
                    "drawingPages": final_order,
                    "navigationActions": ["Save", "Discard", "Cancel"],
                    "legacyInvalidDropdownDidNotBlock": True,
                    "gridTooltipSuppressed": True,
                    "dialogTooltipSuppressed": True,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
