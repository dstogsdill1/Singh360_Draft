"""Browser regression for workbook-detached page duplication and local saving.

The fixture is generated in a disposable SINGH360_DOCS_DIR. It deliberately
starts in workbook conflict and never invokes workbook synchronization.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.project_store import ProjectStore
from core.project_workspace import WorkbookDocumentStore
from core.workbook_link_manager import claim_workbook_for_project
from tests.generated_fixtures import write_workbook

PROJECT_ID = "d00bd00bd00bd00b"


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
    raise RuntimeError("isolated duplicate-page server did not become healthy")


def canvas_objects() -> list[dict]:
    return [
        {
            "type": "Rect",
            "version": "6.9.1",
            "left": 110,
            "top": 90,
            "width": 180,
            "height": 80,
            "fill": "#f7941d",
            "stroke": "#1f2937",
            "strokeWidth": 3,
            "scaleX": 1,
            "scaleY": 1,
            "angle": 0,
            "opacity": 1,
            "visible": True,
            "objName": "Sanitized WICP1 panel",
        },
        {
            "type": "Textbox",
            "version": "6.9.1",
            "left": 140,
            "top": 115,
            "width": 130,
            "height": 28,
            "text": "WICP1 fixture",
            "fontSize": 22,
            "fill": "#111827",
            "scaleX": 1,
            "scaleY": 1,
            "angle": 0,
            "opacity": 1,
            "visible": True,
            "objName": "Sanitized WICP1 label",
        },
        {
            "type": "Line",
            "version": "6.9.1",
            "left": 320,
            "top": 130,
            "x1": 0,
            "y1": 0,
            "x2": 140,
            "y2": 65,
            "stroke": "#2563eb",
            "strokeWidth": 5,
            "scaleX": 1,
            "scaleY": 1,
            "angle": 0,
            "opacity": 1,
            "visible": True,
            "objName": "Sanitized WICP1 connection",
        },
    ]


def fixture_project(workbook: Path) -> dict:
    source_objects = canvas_objects()
    worksheet_id = "ws_wicp1"
    index = {
        "id": "ws_index",
        "name": "00_INDEX",
        "sourceSheet": "00_INDEX",
        "grid": [[
            "Include",
            "Sheet Code",
            "Sheet Tab",
            "Page Title",
            "Page ID",
            "Worksheet ID",
            "Order",
        ], ["YES", "TBD", "Layout 1", "WICP1", "page_wicp1", worksheet_id, 1]],
        "styles": {},
        "formulas": {},
        "mergedCells": [],
        "rowHeights": {},
        "columnWidths": {},
        "hiddenRows": [],
        "hiddenColumns": [],
        "role": "index",
    }
    worksheet = {
        "id": worksheet_id,
        "name": "Layout 1",
        "sourceSheet": "Layout 1",
        "grid": [],
        "styles": {},
        "formulas": {},
        "mergedCells": [],
        "rowHeights": {},
        "columnWidths": {},
        "hiddenRows": [],
        "hiddenColumns": [],
        "role": "drawing",
        "sourceSetup": {"authority": "00_INDEX", "sheetCode": "TBD", "title": "WICP1"},
    }
    page = {
        "id": "page_wicp1",
        "order": 1,
        "include": True,
        "publishStatus": "YES",
        "issueStatus": "draft",
        "sourceMode": "workbook",
        "syncDirection": "Both",
        "sheetCode": "TBD",
        "displaySheetCode": "TBD",
        "sheetTitle": "WICP1",
        "sheetTab": "Layout 1",
        "sourceSheet": "Layout 1",
        "sourceRange": "",
        "printArea": "",
        "pageType": "canvas",
        "pageFamily": "canvas",
        "templateId": "blank",
        "linkedWorksheetId": worksheet_id,
        "blocks": [],
        "canvasObjects": source_objects,
        "notes": "",
        "pageNumber": 1,
        "pageTotal": 1,
        "pageGroupId": "page_wicp1",
        "continuationOf": None,
        "continuationIndex": 0,
        "generatedContinuation": False,
    }
    return {
        "id": PROJECT_ID,
        "projectDisplayName": "Sanitized Duplicate Save Regression",
        "metadata": {"projectName": "Sanitized Duplicate Save Regression"},
        "worksheets": [worksheet, index],
        "pages": [page],
        "sources": [],
        "workbookSync": {
            "mode": "external",
            "workbook": str(workbook),
            "workbookHash": "0" * 64,
            "appHash": "0" * 64,
            "status": "conflict",
            "state": "conflict",
            "warning": "Generated two-sided conflict for local-save regression.",
        },
    }


def read_project(port: int) -> dict:
    with urlopen(f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}", timeout=15) as response:
        return json.load(response)


def assert_saved_copy(project: dict, expected_objects: list[dict]) -> dict:
    pages = project.get("pages") or []
    source = next(page for page in pages if page.get("sheetTitle") == "WICP1")
    copy = next(page for page in pages if page.get("sheetTitle") == "WICP1 Copy")
    if source["id"] == copy["id"] or source.get("pageGroupId") == copy.get("pageGroupId"):
        raise AssertionError("duplicate retained the source page or continuation-group identity")
    if source.get("linkedWorksheetId") == copy.get("linkedWorksheetId"):
        raise AssertionError("duplicate retained the source worksheet identity")
    if source.get("sheetTab", "").casefold() == copy.get("sheetTab", "").casefold():
        raise AssertionError("duplicate retained the source worksheet tab")
    if copy.get("sourceMode") != "app":
        raise AssertionError(f"duplicate is not app-managed: {copy.get('sourceMode')!r}")
    if copy.get("continuationOf") or copy.get("generatedContinuation"):
        raise AssertionError("duplicate retained continuation identity")
    expected_names = [item.get("objName") for item in expected_objects]
    source_objects = source.get("canvasObjects") or []
    copy_objects = copy.get("canvasObjects") or []
    if len(source_objects) != len(expected_objects) or [
        item.get("objName") for item in source_objects
    ] != expected_names:
        raise AssertionError("source WICP1 lost or replaced canvas objects")
    if copy_objects != source_objects:
        raise AssertionError("duplicate did not preserve the saved source canvas payload")
    if project.get("workbookSync", {}).get("status") != "conflict":
        raise AssertionError("local save cleared the workbook conflict")
    tabs = [str(page.get("sheetTab") or "").casefold() for page in pages]
    if len(tabs) != len(set(tabs)):
        raise AssertionError(f"duplicate worksheet tabs remain after local save: {tabs}")
    matching = [
        worksheet for worksheet in project.get("worksheets") or []
        if worksheet.get("id") == copy.get("linkedWorksheetId")
    ]
    if len(matching) != 1 or matching[0].get("name") != copy.get("sheetTab"):
        raise AssertionError("copy does not have one matching project worksheet")
    return copy


def export_pdf(port: int) -> int:
    body = json.dumps({
        "pageIds": [],
        "width": 17,
        "height": 11,
        "confirmPreflight": True,
    }).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}/export/pdf",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        payload = response.read()
        if response.status != 200 or not payload.startswith(b"%PDF"):
            raise AssertionError("disposable duplicate-page PDF export failed")
        return len(payload)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="singh360_duplicate_save_") as raw:
        runtime = Path(raw)
        docs = runtime / ".docs"
        workbook = write_workbook(runtime / "protected-conflict-clone.xlsx")
        claim_workbook_for_project(workbook, PROJECT_ID)
        initial = fixture_project(workbook)
        expected_objects = initial["pages"][0]["canvasObjects"]
        store = ProjectStore(docs)
        store.save(PROJECT_ID, initial)
        project_dir = store.dir_for(PROJECT_ID, initial)
        WorkbookDocumentStore(project_dir).save(
            initial,
            0,
            {"revision": 0, "updatedAt": "", "sheets": []},
        )

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
        requests: list[tuple[str, str]] = []
        project_responses: list[int] = []
        evidence = Path(os.environ["SINGH360_EVIDENCE_DIR"]) if os.environ.get("SINGH360_EVIDENCE_DIR") else runtime
        evidence.mkdir(parents=True, exist_ok=True)
        try:
            health = wait_health(port)
            with sync_playwright() as api:
                browser = api.chromium.launch(
                    executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    headless=True,
                )
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                console_errors: list[str] = []
                page.on("request", lambda request: requests.append((request.method, request.url)))
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on(
                    "response",
                    lambda response: project_responses.append(response.status)
                    if response.request.method == "POST"
                    and response.url.endswith(f"/api/projects/{PROJECT_ID}")
                    else None,
                )
                page.on("dialog", lambda dialog: dialog.dismiss())
                page.goto(
                    f"http://127.0.0.1:{port}/app?project={PROJECT_ID}&mode=editor",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                source_item = page.locator(".page-tab").filter(has_text="WICP1").first
                try:
                    source_item.wait_for(state="visible", timeout=30_000)
                except Exception as exc:
                    page.screenshot(path=str(evidence / "duplicate-load-failure.png"), full_page=True)
                    raise AssertionError(
                        f"fixture editor did not show WICP1: url={page.url}; "
                        f"body={page.locator('body').inner_text()[:2000]!r}; "
                        f"console={console_errors}; requests={requests[-30:]}"
                    ) from exc
                source_item.click(button="right")
                page.get_by_role("button", name="Duplicate Sheet", exact=True).click()

                page.locator(".page-tab").filter(has_text="WICP1 Copy").wait_for(
                    state="visible", timeout=15_000
                )
                page.get_by_role("button", name="File", exact=True).click()
                page.get_by_role("button", name="Save Now", exact=True).click()
                page.wait_for_function(
                    """() => document.querySelector('.save-state-control .status-pill')
                      ?.textContent === 'PROJECT / WORKBOOK CONFLICT'""",
                    timeout=20_000,
                )
                page.screenshot(path=str(evidence / "duplicate-before-reload.png"), full_page=True)

                saved = assert_saved_copy(read_project(port), expected_objects)
                if not project_responses or any(status != 200 for status in project_responses):
                    raise AssertionError(f"local project POST responses were not all 200: {project_responses}")
                if any("/workbook-link/" in url for _, url in requests):
                    raise AssertionError("local duplicate/save invoked workbook synchronization")

                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="WICP1").first.wait_for(
                    state="visible", timeout=30_000
                )
                page.locator(".page-tab").filter(has_text="WICP1 Copy").wait_for(
                    state="visible", timeout=30_000
                )
                page.screenshot(path=str(evidence / "duplicate-after-reload.png"), full_page=True)
                reloaded_copy = assert_saved_copy(read_project(port), expected_objects)
                if reloaded_copy["id"] != saved["id"]:
                    raise AssertionError("reloaded duplicate changed page identity")
                browser.close()

            pdf_bytes = export_pdf(port)
            print(json.dumps({
                "ok": True,
                "health": health,
                "projectId": PROJECT_ID,
                "sourceObjectCount": len(expected_objects),
                "copyObjectCount": len(reloaded_copy["canvasObjects"]),
                "localProjectPostStatuses": project_responses,
                "workbookSyncRequests": [
                    url for _, url in requests if "/workbook-link/" in url
                ],
                "copyPageId": reloaded_copy["id"],
                "copyPageGroupId": reloaded_copy["pageGroupId"],
                "copySheetTab": reloaded_copy["sheetTab"],
                "copyWorksheetId": reloaded_copy["linkedWorksheetId"],
                "pdfBytes": pdf_bytes,
                "evidence": str(evidence),
            }, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            if process.returncode not in {0, -15, 1}:
                raise AssertionError(f"isolated server exited {process.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
