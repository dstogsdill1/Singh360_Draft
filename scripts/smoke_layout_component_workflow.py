"""Disposable browser proof for the Layout Sandbox component workflow."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.project_store import ProjectStore
from core.project_workspace import WorkbookDocumentStore
from core.workbook_status_sync import sync_project_to_workbook
from tests.test_sync_order_reconciliation import document_for, fixture_project, write_fixture_workbook

PROJECT_ID = "1a90a7a90a7a90a7"


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
    raise RuntimeError("disposable Layout Sandbox server did not become healthy")


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def read_project(port: int) -> dict:
    with urlopen(f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}", timeout=30) as response:
        return json.load(response)


def recursive_ids(value: dict) -> list[str]:
    result = [str(value.get("objectId") or "")]
    for child in value.get("objects") or []:
        result.extend(recursive_ids(child))
    return result


def workflow_groups(project: dict, name: str) -> list[dict]:
    page = next(item for item in project["pages"] if item["sheetTitle"] == "Gamma")
    return [item for item in page.get("canvasObjects") or [] if item.get("objName") == name]


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
    with urlopen(request, timeout=180) as response:
        payload = response.read()
        if response.status != 200 or not payload.startswith(b"%PDF"):
            raise AssertionError("Layout Sandbox PDF export did not return a PDF")
        return len(payload)


def main() -> int:
    evidence = Path(
        os.environ.get("SINGH360_BROWSER_EVIDENCE_DIR")
        or ROOT / ".tmp" / "layout_component_workflow"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="s360_layout_component_") as raw:
        runtime = Path(raw)
        docs = runtime / "runtime-docs"
        signage_dir = docs / "library" / "symbols" / "symbols_markers"
        signage_dir.mkdir(parents=True, exist_ok=True)
        for index, filename in enumerate([
            "rdm_sign_leak_dne.svg",
            "rdm_sign_person_trapped.svg",
            "rdm_sign_help_trapped.svg",
        ], start=1):
            signage_dir.joinpath(filename).write_text(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                    '<rect x="3" y="3" width="90" height="90" rx="8" fill="#fff8cc" stroke="#b91c1c" stroke-width="6"/>'
                    f'<text x="48" y="58" text-anchor="middle" font-size="28" font-family="Arial">{index}</text>'
                    '</svg>'
                ),
                encoding="utf-8",
            )
        source_template = runtime / "generated-layout-template.xlsx"
        workbook_copy = runtime / "generated-layout-workbook-copy.xlsx"
        write_fixture_workbook(source_template)
        shutil.copy2(source_template, workbook_copy)
        source_hash = file_hash(source_template)

        project = fixture_project(workbook_copy)
        project["id"] = PROJECT_ID
        project["projectDisplayName"] = "Layout Sandbox"
        project["metadata"]["projectName"] = "Layout Sandbox"
        project["sourceWorkbookName"] = "Singh360_Layout_Only_Generated.xlsx"
        project["workbookSync"]["workbook"] = str(workbook_copy)
        for page in project["pages"]:
            if page["sheetTitle"] in {"Gamma", "Alpha"}:
                page["pageType"] = "canvas"
                page["pageFamily"] = "canvas"
                page["templateId"] = "blank"
                page["blocks"] = []
                page["canvasObjects"] = []

        store = ProjectStore(docs)
        store.save(PROJECT_ID, project)
        project_dir = store.dir_for(PROJECT_ID, project)
        document_store = WorkbookDocumentStore(project_dir)
        document_store.save(project, 0, document_for(project))
        synced = sync_project_to_workbook(PROJECT_ID, project, store)
        if synced.get("workbookSync", {}).get("verified") is not True:
            raise AssertionError("generated workbook copy did not establish a verified baseline")

        port = free_port()
        stdout = (evidence / "server.stdout.log").open("w", encoding="utf-8")
        stderr = (evidence / "server.stderr.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")],
            cwd=ROOT,
            env={**os.environ, "SINGH360_DOCS_DIR": str(docs), "SINGH360_PORT": str(port)},
            stdout=stdout,
            stderr=stderr,
        )
        api_failures: list[str] = []
        page_errors: list[str] = []
        console_errors: list[str] = []
        requests: list[str] = []
        try:
            health = wait_health(port)
            with sync_playwright() as playwright:
                edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
                browser = playwright.chromium.launch(
                    executable_path=str(edge) if edge.is_file() else None,
                    headless=True,
                )
                page = browser.new_page(viewport={"width": 1700, "height": 1050})
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("request", lambda request: requests.append(request.url))
                page.on(
                    "response",
                    lambda response: api_failures.append(f"{response.status} {response.url}: {response.text()[:500]}")
                    if response.status >= 400 and f"/api/projects/{PROJECT_ID}" in response.url
                    else None,
                )

                editor = (
                    f"http://127.0.0.1:{port}/app?project={PROJECT_ID}"
                    "&mode=editor&workflowAudit=1&tooltipAudit=1"
                )
                page.goto(editor, wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="Gamma").click()
                try:
                    if page.locator(".panel-rail-left").is_visible():
                        page.locator(".panel-rail-left").click()
                    components_section = page.get_by_role("button", name="Components", exact=False)
                    components_section.wait_for(state="visible", timeout=30_000)
                    components_section.click()
                except Exception:
                    page.screenshot(path=str(evidence / "components-section-failure.png"), full_page=True)
                    raise AssertionError(
                        "Components section was unavailable after opening Gamma; "
                        f"url={page.url!r}, headings={page.locator('.nav-section-head').all_inner_texts()!r}, "
                        f"body={page.locator('body').inner_text()[:3000]!r}"
                    )
                page.get_by_role("button", name="WICP Annotation Pack", exact=True).click()
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Copy", exact=True).click()
                page.get_by_role("button", name="Paste", exact=True).click()
                page.wait_for_timeout(1_400)

                saved = read_project(port)
                groups = workflow_groups(saved, "WICP Annotation Pack")
                if len(groups) != 2:
                    raise AssertionError(f"copy/paste did not immediately save two groups: {len(groups)}")
                ids = [recursive_ids(group) for group in groups]
                if any(not value for row in ids for value in row):
                    raise AssertionError("pasted group or one of its children has no objectId")
                if set(ids[0]) & set(ids[1]):
                    raise AssertionError("pasted group retained one or more source object IDs")

                page.locator(".page-tab").filter(has_text="Alpha").click()
                page.locator(".page-tab").filter(has_text="Gamma").click()
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="Gamma").wait_for(timeout=30_000)
                if len(workflow_groups(read_project(port), "WICP Annotation Pack")) != 2:
                    raise AssertionError("copy/paste groups did not survive page switching and reload")
                page.goto(f"http://127.0.0.1:{port}/app?project={PROJECT_ID}", wait_until="domcontentloaded")
                page.get_by_role("button", name="Page Editor", exact=False).first.wait_for(timeout=20_000)
                page.goto(editor, wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="Gamma").click()
                page.locator(".nav-section-head").filter(has_text="Components").click()
                section_labels = page.locator(".libv2-section-nav > button > span").all_inner_texts()
                if section_labels != [
                    "Recently Used",
                    "Favorites",
                    "Highlighted Symbols",
                    "Plan Markers",
                    "Saved Assemblies",
                    "Callouts",
                    "Safety Signage",
                    "LCP Components",
                    "All Components",
                    "Manage Library",
                ]:
                    raise AssertionError(f"component section order is wrong: {section_labels!r}")

                selected_count = page.evaluate(
                    "() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectAllByName('WICP Annotation Pack') || 0"
                )
                if selected_count != 2:
                    raise AssertionError(f"multi-select did not select both pasted groups: {selected_count}")
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Group", exact=True).click()
                page.get_by_role("button", name="Ungroup", exact=True).click()

                page.get_by_role("button", name="Signage Legend", exact=True).click()
                page.wait_for_function(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                      .some((item) => item.objName === 'Signage Legend')""",
                    timeout=20_000,
                )

                page.get_by_role("button", name="Signage Marker Trio", exact=True).click()
                page.wait_for_function(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                      .some((item) => item.objName === 'Signage Marker Trio')""",
                    timeout=20_000,
                )
                page.evaluate(
                    """() => {
                      window.__assemblyPromptCalls = [];
                      window.prompt = (...args) => {
                        window.__assemblyPromptCalls.push(args);
                        return 'Saved Signage Assembly';
                      };
                    }"""
                )
                page.get_by_role("button", name="Save Selection as Assembly", exact=True).last.click()
                dialog_trace = page.evaluate(
                    "() => ({ prompts: window.__assemblyPromptCalls })"
                )
                if not dialog_trace["prompts"]:
                    raise AssertionError(f"save selection did not reach the naming prompt: {dialog_trace!r}")
                page.wait_for_timeout(1_200)
                page.get_by_role("button", name=re.compile(r"^Saved Assemblies: \d+$")).click()
                saved_card = page.get_by_role("button", name="Saved Signage Assembly", exact=False)
                try:
                    saved_card.wait_for(state="visible", timeout=15_000)
                except Exception:
                    page.screenshot(path=str(evidence / "saved-assembly-failure.png"), full_page=True)
                    raise AssertionError(
                        f"saved assembly card was absent; project assemblies="
                        f"{read_project(port).get('savedAssemblies')!r}"
                    )
                saved_card.click()

                page.get_by_role("button", name="Callout Block", exact=True).click()
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Ungroup", exact=True).click()
                selected = page.evaluate(
                    "() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByName('Callout Note') || false"
                )
                if not selected:
                    raise AssertionError("callout note was not independently editable after ungroup")
                if page.locator(".panel-rail-right").is_visible():
                    page.locator(".panel-rail-right").click()
                page.locator("#sel-text").fill("EDITED DISPOSABLE CALLOUT NOTE")

                page.get_by_role("button", name="File", exact=True).hover()
                page.wait_for_timeout(800)
                if page.locator(".s360-app-tooltip").count():
                    raise AssertionError("canvas tooltip remained visible while an object was selected")

                page.get_by_role("button", name="Generated Symbol Key", exact=True).click()
                page.get_by_role("button", name="File", exact=True).click()
                page.get_by_role("button", name="Save Now", exact=True).click()
                page.wait_for_timeout(1_500)
                page.screenshot(path=str(evidence / "layout-workflow-before-sync.png"), full_page=True)

                persisted = read_project(port)
                if not any(item["name"] == "Saved Signage Assembly" for item in persisted.get("savedAssemblies") or []):
                    raise AssertionError("saved assembly was not persisted in the project")
                gamma = next(item for item in persisted["pages"] if item["sheetTitle"] == "Gamma")
                flat = json.dumps(gamma.get("canvasObjects") or [])
                for marker in [
                    "Saved Signage Assembly",
                    "EDITED DISPOSABLE CALLOUT NOTE",
                    "Signage Legend",
                    "Generated Symbol Key",
                ]:
                    if marker not in flat:
                        raise AssertionError(f"persistent workflow object missing after local save: {marker}")

                page.goto(f"http://127.0.0.1:{port}/app?project={PROJECT_ID}", wait_until="domcontentloaded")
                page.get_by_text("GENERATED WORKBOOK UPDATE PENDING", exact=True).wait_for(timeout=20_000)
                displayed_path = page.get_by_test_id("generated-workbook-path").inner_text()
                if Path(displayed_path) != workbook_copy:
                    raise AssertionError(f"wrong generated workbook path: {displayed_path!r}")
                for label in ["Open Workbook", "Open Folder", "Copy Path"]:
                    page.get_by_role("button", name=label, exact=True).wait_for()
                page.context.grant_permissions(
                    ["clipboard-read", "clipboard-write"],
                    origin=f"http://127.0.0.1:{port}",
                )
                page.get_by_role("button", name="Copy Path", exact=True).click()
                copied_path = page.evaluate("() => navigator.clipboard.readText()")
                if Path(copied_path) != workbook_copy:
                    raise AssertionError(f"Copy Path copied the wrong value: {copied_path!r}")

                page.goto(editor, wait_until="domcontentloaded")
                with page.expect_response(
                    lambda response: response.request.method == "POST"
                    and response.url.endswith(f"/api/projects/{PROJECT_ID}/workbook-link/resolve"),
                    timeout=180_000,
                ) as sync_response:
                    page.get_by_role("button", name="SAVE + WRITE EXCEL", exact=True).click()
                if sync_response.value.status != 200:
                    raise AssertionError(
                        f"copied-workbook sync failed: {sync_response.value.status} {sync_response.value.text()}"
                    )
                page.get_by_text("PROJECT SAVED · WORKBOOK SYNCED", exact=True).wait_for(timeout=30_000)
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="Gamma").wait_for(timeout=30_000)
                page.locator(".page-tab").filter(has_text="Gamma").click()
                page.wait_for_function(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                      .some((item) => item.objName === 'Generated Symbol Key')""",
                    timeout=30_000,
                )
                page.screenshot(path=str(evidence / "layout-workflow-after-sync-reload.png"), full_page=True)
                browser.close()

            pdf_bytes = export_pdf(port)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            stdout.close()
            stderr.close()

        if file_hash(source_template) != source_hash:
            raise AssertionError("the generated source template changed; only its copied workbook was writable")
        if api_failures:
            raise AssertionError(f"browser API failures: {api_failures}")
        if page_errors:
            raise AssertionError(f"browser page errors: {page_errors}")
        if console_errors:
            raise AssertionError(f"browser console errors: {console_errors}")
        final_project = store.load(PROJECT_ID)
        print(json.dumps({
            "ok": True,
            "projectId": PROJECT_ID,
            "health": health,
            "workbookCopy": str(workbook_copy),
            "sourceTemplateHashUnchanged": True,
            "copyPasteGroups": 2,
            "savedAssemblies": len(final_project.get("savedAssemblies") or []),
            "pdfBytes": pdf_bytes,
            "workbookSyncRequests": [url for url in requests if "/workbook-link/resolve" in url],
            "evidence": str(evidence),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
