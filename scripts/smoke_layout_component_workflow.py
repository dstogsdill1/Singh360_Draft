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
from urllib.request import urlopen

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


def workflow_objects(project: dict, name: str) -> list[dict]:
    page = next(item for item in project["pages"] if item["sheetTitle"] == "Gamma")
    return [item for item in page.get("canvasObjects") or [] if item.get("objName") == name]


def smart_objects(project: dict, component_type: str) -> list[dict]:
    page = next(item for item in project["pages"] if item["sheetTitle"] == "Gamma")
    return [
        item
        for item in page.get("canvasObjects") or []
        if item.get("smartComponentType") == component_type
    ]


def callout_objects(project: dict, family: str, page_title: str = "Gamma") -> list[dict]:
    page = next(item for item in project["pages"] if item["sheetTitle"] == page_title)
    return [
        item
        for item in page.get("canvasObjects") or []
        if (item.get("calloutConfig") or {}).get("family") == family
    ]


def right_click_canvas_object(page, name: str) -> None:
    point = page.evaluate(
        "(name) => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.screenPointByName(name) || null",
        name,
    )
    if not point:
        raise AssertionError(f"could not resolve the screen point for {name!r}")
    page.mouse.click(point["x"], point["y"], button="right")
    page.locator(".ctx-menu").wait_for(state="visible", timeout=10_000)


def launch_component_tool(page, name: str) -> None:
    """Open one capability kept in the advanced Component Builder workbench."""
    page.get_by_role("button", name="Component Builder", exact=True).click()
    builder = page.get_by_role("dialog", name="Component Builder")
    builder.wait_for(state="visible", timeout=15_000)
    builder.get_by_text("Advanced insertion and library tools", exact=True).click()
    builder.get_by_role("button", name=name, exact=True).click()


def open_saved_assembly_card(page, name: str):
    """Open one saved assembly card in the advanced workbench."""
    page.get_by_role("button", name="Component Builder", exact=True).click()
    builder = page.get_by_role("dialog", name="Component Builder")
    builder.wait_for(state="visible", timeout=15_000)
    builder.get_by_text("Advanced insertion and library tools", exact=True).click()
    card = builder.locator(".libv2-saved-assembly-card").filter(has_text=name)
    card.wait_for(state="visible", timeout=15_000)
    return card


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
        disposable_components = [
            ("fixture-round-callout", "Disposable Round Callout", "Round Callouts", []),
            ("fixture-square-callout", "Disposable Square Callout", "Square Callouts", []),
            ("fixture-callout-block", "Disposable Callout List", "Callout Blocks / Lists", []),
            ("fixture-signage", "Disposable Signage Marker", "Safety Signage", []),
            (
                "fixture-highlighted",
                "Disposable Highlighted Symbol",
                "Refrigeration Controls Symbols",
                [],
            ),
            (
                "fixture-plan-marker",
                "Disposable Plan Marker",
                "Singh360 Plan Markers",
                [],
            ),
            ("fixture-lcp", "Disposable LCP Component", "LCP Components", ["lcp"]),
        ]
        docs.joinpath("library", "manifest.json").write_text(
            json.dumps({
                "version": 2,
                "components": [
                    {
                        "id": component_id,
                        "displayName": display_name,
                        "category": "symbols_markers",
                        "categories": ["symbols_markers"],
                        "collection": collection,
                        "tags": tags,
                        "defaultLabel": display_name,
                        "defaultWidth": 96,
                        "defaultHeight": 96,
                        "sourceFile": "symbols/symbols_markers/rdm_sign_leak_dne.svg",
                        "approved": True,
                        "status": "active",
                    }
                    for component_id, display_name, collection, tags in disposable_components
                ],
            }, indent=2),
            encoding="utf-8",
        )
        public_catalog = ROOT / "docs" / "component-library" / "catalog.json"
        public_catalog_hash = file_hash(public_catalog)
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
        workbook_hash_before_browser = file_hash(workbook_copy)

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
        requests: list[tuple[str, str]] = []
        try:
            health = wait_health(port)
            with sync_playwright() as playwright:
                edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
                browser = playwright.chromium.launch(
                    executable_path=str(edge) if edge.is_file() else None,
                    headless=True,
                )
                page = browser.new_page(viewport={"width": 1700, "height": 1050})
                page.context.grant_permissions(
                    ["clipboard-read", "clipboard-write"],
                    origin=f"http://127.0.0.1:{port}",
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("request", lambda request: requests.append((request.method, request.url)))
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
                component_browser = page.locator(".libv2-browser")
                component_browser.wait_for(state="visible", timeout=30_000)
                page.get_by_text("Component library ready", exact=True).wait_for(timeout=30_000)
                expected_sidebar_controls = ["Component Builder", "Manage Library"]
                actual_sidebar_controls = component_browser.locator(".libv2-browser-footer button").all_inner_texts()
                if actual_sidebar_controls != expected_sidebar_controls:
                    raise AssertionError(f"Component Browser footer is wrong: {actual_sidebar_controls!r}")
                if page.locator(".libv2-section-nav").count():
                    raise AssertionError("legacy shortcut/count tiles remain in the normal sidebar")

                page.get_by_role("button", name="Component Builder", exact=True).click()
                builder = page.get_by_role("dialog", name="Component Builder")
                builder.get_by_text("Advanced insertion and library tools", exact=True).click()
                for smart_name in [
                    "Panel Enclosure",
                    "Contactor Bank",
                    "Relay Bank",
                    "Power Monitor Pack",
                    "Terminal Bank",
                    "Labeled Device Block",
                ]:
                    builder.get_by_role("button", name=smart_name, exact=True).wait_for()
                builder.get_by_role("button", name="Close", exact=True).click()

                launch_component_tool(page, "Round Callout")
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Round Callouts — Round Callout 1')""",
                    timeout=20_000,
                )

                launch_component_tool(page, "Generate Round Callouts")
                page.get_by_label("Callout set name", exact=True).fill("Round Range 1-10")
                page.get_by_role("tab", name="Numeric Range", exact=True).click()
                page.get_by_label("Callout range start", exact=True).fill("1")
                page.get_by_label("Callout range end", exact=True).fill("10")
                page.get_by_role("button", name="Append to Current Rows", exact=True).click()
                page.get_by_role("button", name="Insert New", exact=True).click()
                page.wait_for_function(
                    """() => {
                      const object = (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                        .find((item) => item.objName === 'Round Callouts — Round Range 1-10');
                      return object?.calloutConfig?.entries?.length === 10;
                    }""",
                    timeout=20_000,
                )

                launch_component_tool(page, "Square Callout")
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Square Callouts — Square Callout 1')""",
                    timeout=20_000,
                )

                launch_component_tool(page, "Callout Block / List")
                canvas_count_before_block = page.evaluate(
                    "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).length"
                )
                page.get_by_label("Callout set name", exact=True).fill("Electrical Room Callouts")
                page.get_by_label("Callout list title", exact=True).fill(
                    "EQUIPMENT CALLOUTS CUSTOM"
                )

                # One-column Excel clipboard data maps to Label and preserves
                # row order and leading/trailing spaces.
                page.get_by_role("tab", name="Excel Paste", exact=True).click()
                page.evaluate(
                    "() => navigator.clipboard.writeText('MDP\\n Rack A \\nOAU-01')"
                )
                page.get_by_role("button", name="Paste from Clipboard", exact=True).click()
                page.wait_for_function(
                    """() => document.querySelector('[aria-label="Row 1 Label"]')?.value
                      === 'MDP'""",
                    timeout=10_000,
                )
                if page.get_by_label("Row 1 Label", exact=True).input_value() != "MDP":
                    raise AssertionError("one-column Excel paste did not map to Label")
                if page.get_by_label("Row 2 Label", exact=True).input_value() != " Rack A ":
                    raise AssertionError("one-column Excel paste did not preserve spaces")

                # Undo returns to the pre-paste editable row without losing the
                # separate Excel draft.
                page.get_by_role("button", name="Undo", exact=True).click()
                if page.get_by_label("Row 1 Label", exact=True).input_value() != "":
                    raise AssertionError("callout grid Undo did not restore the prior draft")
                if page.get_by_label("Row 2 Label", exact=True).count():
                    raise AssertionError("callout grid Undo retained pasted rows")

                # Ctrl+V directly in a grid editor maps 3 columns and must not
                # bubble into the canvas as an extra raw-text object.
                page.evaluate(
                    "() => navigator.clipboard.writeText("
                    "'1\\tMDP\\tMain Distribution Panel\\n"
                    "2\\tRack A\\tNetwork Rack A\\n"
                    "2\\tRack A\\tDuplicate  Rack A\\n"
                    "3\\tOAU-01\\tOutdoor Air Unit')"
                )
                page.get_by_label("Row 1 Label", exact=True).focus()
                page.keyboard.press("Control+V")
                page.get_by_label("Row 3 Description", exact=True).wait_for()
                if page.get_by_label("Row 1 Callout", exact=True).input_value() != "1":
                    raise AssertionError("three-column Excel paste did not map Callout")
                if (
                    page.get_by_label("Row 2 Label", exact=True).input_value() != "Rack A"
                    or page.get_by_label("Row 3 Label", exact=True).input_value() != "Rack A"
                ):
                    raise AssertionError("duplicate Excel labels were not preserved in order")
                if page.get_by_label("Row 3 Description", exact=True).input_value() != "Duplicate  Rack A":
                    raise AssertionError("three-column Excel paste did not preserve Description spaces")
                if page.evaluate(
                    "() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || []).length"
                ) != canvas_count_before_block:
                    raise AssertionError("pasting in the callout grid created a canvas object")

                # The explicit plain-text action appends one-column Label rows,
                # including duplicates.
                page.get_by_role("button", name="Paste Plain Text", exact=True).click()
                page.get_by_label("Plain text callout data", exact=True).fill("SPARE\nSPARE")
                page.get_by_role("button", name="Add Plain Text Rows", exact=True).click()
                if (
                    page.get_by_label("Row 5 Label", exact=True).input_value() != "SPARE"
                    or page.get_by_label("Row 6 Label", exact=True).input_value() != "SPARE"
                ):
                    raise AssertionError("plain-text duplicate labels were not retained")

                # Numeric generation is additive. A canceled destructive replace
                # leaves all current rows alone, and Undo removes only the last
                # successful append.
                page.get_by_role("tab", name="Numeric Range", exact=True).click()
                page.get_by_label("Callout range start", exact=True).fill("10")
                page.get_by_label("Callout range end", exact=True).fill("11")
                page.get_by_label("Callout range prefix", exact=True).fill("C-")
                page.get_by_role("button", name="Append to Current Rows", exact=True).click()
                if page.get_by_label("Row 8 Callout", exact=True).input_value() != "C-11":
                    raise AssertionError("numeric generator did not append to current rows")
                page.evaluate("() => { window.confirm = () => false; }")
                page.get_by_label("Callout range start", exact=True).fill("1")
                page.get_by_label("Callout range end", exact=True).fill("2")
                page.get_by_label("Callout range prefix", exact=True).fill("R-")
                page.get_by_role("button", name="Replace Rows", exact=True).click()
                if page.get_by_label("Row 8 Callout", exact=True).input_value() != "C-11":
                    raise AssertionError("canceled numeric replace changed current rows")
                if "canceled" not in page.locator(".callout-editor-status").inner_text().lower():
                    raise AssertionError("canceled numeric replace was not reported")
                page.get_by_role("button", name="Undo", exact=True).click()
                if page.get_by_label("Row 7 Callout", exact=True).count():
                    raise AssertionError("Undo did not remove the numeric append")
                page.get_by_label("Callout range start", exact=True).fill("10")
                page.get_by_label("Callout range end", exact=True).fill("11")
                page.get_by_label("Callout range prefix", exact=True).fill("C-")
                page.get_by_role("button", name="Append to Current Rows", exact=True).click()

                # Source tabs are views, not destructive modes.
                for source_name in ["Manual", "Excel Paste", "Numeric Range"]:
                    page.get_by_role("tab", name=source_name, exact=True).click()
                    if page.get_by_label("Row 8 Callout", exact=True).input_value() != "C-11":
                        raise AssertionError(
                            f"switching to {source_name} erased entered callout rows"
                        )
                page.get_by_label("Callout marker style", exact=True).select_option("pill")
                page.get_by_label("Callout layout", exact=True).select_option("vertical")
                page.get_by_label("Callout spacing", exact=True).fill("11")

                # Cancel/reopen proves per-project/page dialog draft autosave.
                page.get_by_role("button", name="Cancel", exact=True).click()
                launch_component_tool(page, "Callout Block / List")
                if page.get_by_label("Row 8 Callout", exact=True).input_value() != "C-11":
                    raise AssertionError("callout dialog draft did not restore for the active project/page")
                if page.get_by_label("Callout list title", exact=True).input_value() != "EQUIPMENT CALLOUTS CUSTOM":
                    raise AssertionError("editable callout title was not restored")
                page.get_by_role("button", name="Insert New", exact=True).click()
                block_name = "Callout Blocks / Lists — Electrical Room Callouts"
                page.wait_for_function(
                    """() => {
                      const object = (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                        .find((item) => item.objName === 'Callout Blocks / Lists — Electrical Room Callouts');
                      const config = object?.calloutConfig;
                      return config?.title === 'EQUIPMENT CALLOUTS CUSTOM'
                        && config?.markerShape === 'pill'
                        && config?.layout === 'vertical'
                        && config?.spacing === 11
                        && config?.entries?.map((entry) => entry.callout).join('|')
                          === '1|2|2|3|||C-10|C-11'
                        && config?.entries?.map((entry) => entry.label).join('|')
                          === 'MDP|Rack A|Rack A|OAU-01|SPARE|SPARE||';
                    }""",
                    timeout=20_000,
                )
                canvas_after_callout_insert = page.evaluate(
                    """() => {
                      const objects = window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [];
                      return {
                        count: objects.length,
                        rawText: objects.filter((item) =>
                          !item.calloutConfig
                          && JSON.stringify(item).includes('Main Distribution Panel')
                        ).length,
                      };
                    }"""
                )
                if canvas_after_callout_insert != {
                    "count": canvas_count_before_block + 1,
                    "rawText": 0,
                }:
                    raise AssertionError(
                        "Excel paste created a duplicate raw-text canvas object: "
                        f"{canvas_after_callout_insert!r}"
                    )
                block_id_before_edit = page.evaluate(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .find((item) => item.objName
                        === 'Callout Blocks / Lists — Electrical Room Callouts')?.objectId"""
                )
                right_click_canvas_object(page, block_name)
                placed_context_actions = page.locator(".ctx-menu .ctx-item").all_inner_texts()
                if placed_context_actions[:7] != [
                    "Edit Callout Block",
                    "Rename",
                    "Duplicate",
                    "Delete",
                    "Move to Category",
                    "Add to Favorites",
                    "Save as Assembly",
                ]:
                    raise AssertionError(
                        f"placed-symbol context actions are incomplete: {placed_context_actions!r}"
                    )
                page.locator(".ctx-menu").get_by_role(
                    "button", name="Edit Callout Block", exact=True
                ).click()
                page.get_by_role("dialog", name="Edit Callout Blocks / Lists").wait_for()
                page.get_by_role("button", name="Insert New", exact=True).wait_for()
                page.get_by_role("button", name="Update Selected", exact=True).wait_for()
                if page.get_by_label("Callout marker style", exact=True).input_value() != "pill":
                    raise AssertionError("right-click edit did not prefill callout marker style")
                if page.get_by_label("Callout spacing", exact=True).input_value() != "11":
                    raise AssertionError("right-click edit did not prefill callout spacing")
                page.get_by_label("Callout set name", exact=True).fill("Electrical Room Callouts Revised")
                page.get_by_label("Row 3 Description", exact=True).fill(
                    "Network Rack A - EDITED"
                )
                page.get_by_role("button", name="Update Selected", exact=True).click()
                revised_block_name = "Callout Blocks / Lists — Electrical Room Callouts Revised"
                page.wait_for_function(
                    """() => JSON.stringify(window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .includes('Network Rack A - EDITED')""",
                    timeout=20_000,
                )
                block_id_after_edit = page.evaluate(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .find((item) => item.objName
                        === 'Callout Blocks / Lists — Electrical Room Callouts Revised')?.objectId"""
                )
                if block_id_after_edit != block_id_before_edit:
                    raise AssertionError("Update Selected replaced the callout block identity")
                page.evaluate(
                    """() => {
                      window.prompt = () => 'Electrical Room Markers Renamed';
                    }"""
                )
                right_click_canvas_object(page, revised_block_name)
                page.locator(".ctx-menu").get_by_role("button", name="Rename", exact=True).click()
                renamed_block_name = "Callout Blocks / Lists — Electrical Room Markers Renamed"
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName
                        === 'Callout Blocks / Lists — Electrical Room Markers Renamed')""",
                    timeout=20_000,
                )
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Copy", exact=True).click()
                page.get_by_role("button", name="Paste", exact=True).click()
                page.evaluate("() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.deselect()")
                page.wait_for_timeout(1_400)
                pasted_blocks = callout_objects(read_project(port), "block")
                if len(pasted_blocks) != 2:
                    raise AssertionError(
                        f"editable callout copy/paste did not immediately persist: {len(pasted_blocks)}"
                    )
                pasted_block_ids = [recursive_ids(group) for group in pasted_blocks]
                if set(pasted_block_ids[0]) & set(pasted_block_ids[1]):
                    raise AssertionError("pasted callout block retained source group or child IDs")

                page.get_by_role("combobox", name="Component collection").select_option(
                    label="Safety Signage",
                )
                signage_card = page.locator(".libv2-browser-card").filter(
                    has_text="Disposable Signage Marker",
                )
                signage_card.wait_for(state="visible", timeout=15_000)
                page.get_by_role("button", name="Component Builder", exact=True).click()
                builder = page.get_by_role("dialog", name="Component Builder")
                builder.get_by_placeholder("Search existing components…").fill(
                    "Disposable Signage Marker"
                )
                builder.locator(".libv2-builder-picker-list > button").filter(
                    has_text="Disposable Signage Marker",
                ).click()
                builder.get_by_label("Component name", exact=True).fill(
                    "Disposable Signage Marker Renamed"
                )
                builder.get_by_role("button", name="Save Component", exact=True).click()
                builder.get_by_role("button", name="Close", exact=True).click()
                page.get_by_role("combobox", name="Component collection").select_option(
                    label="Safety Signage",
                )
                renamed_signage_card = page.locator(".libv2-browser-card").filter(
                    has_text="Disposable Signage Marker Renamed",
                )
                renamed_signage_card.wait_for(state="visible", timeout=15_000)
                renamed_signage_card.click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Disposable Signage Marker Renamed')""",
                    timeout=20_000,
                )
                right_click_canvas_object(page, "Disposable Signage Marker Renamed")
                placed_symbol_actions = page.locator(".ctx-menu .ctx-item").all_inner_texts()
                if placed_symbol_actions[:7] != [
                    "Edit",
                    "Rename",
                    "Duplicate",
                    "Delete",
                    "Move to Category",
                    "Add to Favorites",
                    "Save as Assembly",
                ]:
                    raise AssertionError(
                        f"placed library symbol actions are incomplete: {placed_symbol_actions!r}"
                    )
                page.locator(".ctx-menu").get_by_role("button", name="Edit", exact=True).click()
                page.get_by_role("dialog", name="Symbol and component editor").wait_for()
                page.get_by_label("Placed symbol name", exact=True).fill(
                    "Edited Disposable Signage"
                )
                page.get_by_label("Placed symbol label", exact=True).fill("EDITED SYMBOL")
                page.get_by_label("Placed symbol category", exact=True).fill("custom-markers")
                page.get_by_label("Favorite placed symbol", exact=True).check()
                page.get_by_role("button", name="Save Symbol Changes", exact=True).click()
                page.wait_for_function(
                    """() => JSON.stringify(window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .includes('EDITED SYMBOL')""",
                    timeout=20_000,
                )
                page.evaluate("() => { window.prompt = () => 'Renamed Editable Signage'; }")
                right_click_canvas_object(page, "Edited Disposable Signage")
                page.locator(".ctx-menu").get_by_role("button", name="Rename", exact=True).click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Renamed Editable Signage')""",
                    timeout=20_000,
                )
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Copy", exact=True).click()
                page.get_by_role("button", name="Paste", exact=True).click()
                page.evaluate("() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.deselect()")
                page.wait_for_timeout(1_400)
                placed_symbol_copies = workflow_objects(
                    read_project(port),
                    "Renamed Editable Signage",
                )
                if len(placed_symbol_copies) != 2:
                    raise AssertionError(
                        f"placed symbol copy/paste did not immediately persist: "
                        f"{len(placed_symbol_copies)}"
                    )
                placed_symbol_ids = [recursive_ids(group) for group in placed_symbol_copies]
                if set(placed_symbol_ids[0]) & set(placed_symbol_ids[1]):
                    raise AssertionError("pasted placed symbol retained source group or child IDs")

                launch_component_tool(page, "Panel Enclosure")
                page.get_by_label("Panel type", exact=True).select_option("WICP")
                page.get_by_label("Panel title", exact=True).fill("WICP-7")
                page.get_by_label("Panel header", exact=True).fill("WEST LIGHTING CONTROL PANEL")
                page.get_by_label("Panel width", exact=True).fill("620")
                page.get_by_label("Panel height", exact=True).fill("440")
                page.get_by_label("Device grid rows", exact=True).fill("2")
                page.get_by_label("Device grid columns", exact=True).fill("3")
                page.get_by_label("Device grid labels", exact=True).fill(
                    "PS24\nCONTACTORS\nRELAYS\nTERMINALS\nROUTER\nSPARE"
                )
                page.get_by_role("button", name="Insert Panel Enclosure", exact=True).click()
                if page.locator(".panel-rail-right").is_visible():
                    page.locator(".panel-rail-right").click()
                page.get_by_role("button", name="Edit Smart Component", exact=True).wait_for()
                page.get_by_role("button", name="Edit Smart Component", exact=True).click()
                page.get_by_label("Panel title", exact=True).fill("WICP-7A")
                page.get_by_role("button", name="Apply Smart Component Changes", exact=True).click()

                launch_component_tool(page, "Contactor Bank")
                page.get_by_label("Contactor prefix", exact=True).fill("C")
                page.get_by_label("Contactor start number", exact=True).fill("1")
                page.get_by_label("Numbered contactors count", exact=True).fill("10")
                page.get_by_label("Spare contactors count", exact=True).fill("2")
                if page.get_by_label("Spare contactor label", exact=True).input_value() != "SPARE":
                    raise AssertionError("default contactor spare label is not SPARE")
                if page.get_by_label("Total contactor quantity", exact=True).input_value() != "12":
                    raise AssertionError("contactor total did not calculate numbered + spare counts")
                page.get_by_label("Physical poles", exact=True).select_option("2P")
                page.get_by_label("Scheduled poles", exact=True).fill("SCHEDULED 3P")
                page.get_by_label("Bank layout", exact=True).select_option("grid")
                page.get_by_label("Grid columns", exact=True).fill("3")
                page.get_by_label("Bank spacing", exact=True).fill("22")
                page.get_by_role("button", name="Insert Contactor Bank", exact=True).click()
                generated_contactor_name = "Contactor Bank C1–C10 + 2 SPARE"
                page.wait_for_function(
                    """() => {
                      const object = (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                        .find((item) => item.objName === 'Contactor Bank C1–C10 + 2 SPARE');
                      const config = object?.smartConfig;
                      const names = (object?.objects || []).map((item) => item.objName);
                      return config?.numberedCount === 10
                        && config?.spareCount === 2
                        && config?.spareLabel === 'SPARE'
                        && config?.quantity === 12
                        && names.join('|') === [
                          'Contactor C1', 'Contactor C2', 'Contactor C3', 'Contactor C4',
                          'Contactor C5', 'Contactor C6', 'Contactor C7', 'Contactor C8',
                          'Contactor C9', 'Contactor C10', 'Contactor SPARE', 'Contactor SPARE'
                        ].join('|');
                    }""",
                    timeout=20_000,
                )
                contactor_id_before_edit = page.evaluate(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .find((item) => item.objName
                        === 'Contactor Bank C1–C10 + 2 SPARE')?.objectId"""
                )
                right_click_canvas_object(page, generated_contactor_name)
                page.locator(".ctx-menu").get_by_role(
                    "button", name="Edit Smart Component", exact=True
                ).click()
                if page.get_by_label("Numbered contactors count", exact=True).input_value() != "10":
                    raise AssertionError("right-click edit did not restore numbered contactor count")
                if page.get_by_label("Spare contactors count", exact=True).input_value() != "2":
                    raise AssertionError("right-click edit did not restore spare contactor count")
                if page.get_by_label("Physical poles", exact=True).input_value() != "2P":
                    raise AssertionError("right-click edit did not restore physical poles")
                if page.get_by_label("Bank layout", exact=True).input_value() != "grid":
                    raise AssertionError("right-click edit did not restore bank layout")
                page.get_by_label("Numbered contactors count", exact=True).fill("4")
                page.get_by_label("Spare contactors count", exact=True).fill("2")
                page.get_by_label("Spare contactor label", exact=True).fill("AVAILABLE")
                page.get_by_label("Grid columns", exact=True).fill("2")
                page.get_by_label("Physical poles", exact=True).select_option("3P")
                page.get_by_label("Scheduled poles", exact=True).fill("SCHEDULED 2P")
                page.get_by_label("Bank spacing", exact=True).fill("14")
                page.get_by_label("Custom contactor labels", exact=True).fill(
                    "C1\nC1\nC2\nSPARE\nSPARE"
                )
                if page.get_by_label("Total contactor quantity", exact=True).input_value() != "5":
                    raise AssertionError("custom contactor labels did not control total quantity")
                page.get_by_label("Bank layout", exact=True).select_option("vertical")
                page.get_by_role("button", name="Apply Smart Component Changes", exact=True).click()
                custom_contactor_name = "Contactor Bank C1…SPARE (5)"
                page.wait_for_function(
                    """() => {
                      const object = (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                        .find((item) => item.objName === 'Contactor Bank C1…SPARE (5)');
                      const config = object?.smartConfig;
                      const names = (object?.objects || []).map((item) => item.objName);
                      return config?.numberedCount === 4
                        && config?.spareCount === 2
                        && config?.spareLabel === 'AVAILABLE'
                        && config?.quantity === 5
                        && config?.customLabels?.join('|') === 'C1|C1|C2|SPARE|SPARE'
                        && config?.physicalPoles === '3P'
                        && config?.scheduledPoles === 'SCHEDULED 2P'
                        && config?.layout === 'vertical'
                        && config?.gridColumns === 2
                        && config?.spacing === 14
                        && names.join('|') === [
                          'Contactor C1', 'Contactor C1', 'Contactor C2',
                          'Contactor SPARE', 'Contactor SPARE'
                        ].join('|');
                    }""",
                    timeout=20_000,
                )
                contactor_id_after_edit = page.evaluate(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .find((item) => item.objName
                        === 'Contactor Bank C1…SPARE (5)')?.objectId"""
                )
                if contactor_id_after_edit != contactor_id_before_edit:
                    raise AssertionError("editing the Contactor Bank replaced its root object ID")

                launch_component_tool(page, "Relay Bank")
                page.get_by_label("Relay prefix", exact=True).fill("R")
                page.get_by_label("Relay start number", exact=True).fill("10")
                page.get_by_label("Relay quantity", exact=True).fill("5")
                page.get_by_label("Bank layout", exact=True).select_option("vertical")
                page.get_by_label("Bank spacing", exact=True).fill("14")
                page.get_by_role("button", name="Insert Relay Bank", exact=True).click()

                launch_component_tool(page, "Power Monitor Pack")
                page.get_by_label("Power monitor model", exact=True).select_option("PS24")
                page.get_by_label("Power monitor mount", exact=True).select_option("DIN")
                page.get_by_label("Power monitor terminal bank", exact=True).select_option("L")
                page.get_by_label("CT quantity", exact=True).fill("8")
                page.get_by_label("CT type", exact=True).select_option("Solid-core")
                page.get_by_role("button", name="Insert Power Monitor Pack", exact=True).click()

                launch_component_tool(page, "Terminal Bank")
                page.get_by_label("Terminal bank label", exact=True).fill("TERMINAL BANK A")
                page.get_by_label("Terminal prefix", exact=True).fill("A")
                page.get_by_label("Terminal start number", exact=True).fill("1")
                page.get_by_label("Terminal quantity", exact=True).fill("6")
                page.get_by_label("Terminal bank layout", exact=True).select_option("vertical")
                page.get_by_label("Terminal spacing", exact=True).fill("6")
                page.get_by_role("button", name="Insert Terminal Bank", exact=True).click()

                launch_component_tool(page, "Labeled Device Block")
                page.get_by_label("Device label", exact=True).fill("LCP AUXILIARY DEVICE")
                page.get_by_label("Device secondary label", exact=True).fill("EDITABLE VECTOR BLOCK")
                page.get_by_label("Device width", exact=True).fill("210")
                page.get_by_label("Device height", exact=True).fill("120")
                page.get_by_label("Device terminal count", exact=True).fill("4")
                page.get_by_role("button", name="Insert Labeled Device Block", exact=True).click()

                page.wait_for_function(
                    """() => {
                      const objects = window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [];
                      return new Set(objects.map((item) => item.smartComponentType)).size >= 6;
                    }""",
                    timeout=20_000,
                )

                launch_component_tool(page, "WICP Annotation Pack")
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Copy", exact=True).click()
                page.get_by_role("button", name="Paste", exact=True).click()
                page.wait_for_timeout(1_400)

                saved = read_project(port)
                groups = workflow_objects(saved, "WICP Annotation Pack")
                if len(groups) != 2:
                    raise AssertionError(f"copy/paste did not immediately save two groups: {len(groups)}")
                ids = [recursive_ids(group) for group in groups]
                if any(not value for row in ids for value in row):
                    raise AssertionError("pasted group or one of its children has no objectId")
                if set(ids[0]) & set(ids[1]):
                    raise AssertionError("pasted group retained one or more source object IDs")

                selected = page.evaluate(
                    "() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByName('Contactor Bank C1…SPARE (5)') || false"
                )
                if not selected:
                    raise AssertionError("smart contactor bank could not be selected for copy/paste")
                page.get_by_role("button", name="Copy", exact=True).click()
                page.get_by_role("button", name="Paste", exact=True).click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .filter((item) => item.smartComponentType === 'contactor-bank').length === 2""",
                    timeout=20_000,
                )
                page.evaluate("() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.deselect()")
                page.wait_for_timeout(1_400)
                contactor_groups = smart_objects(read_project(port), "contactor-bank")
                if len(contactor_groups) != 2:
                    raise AssertionError(
                        f"smart copy/paste did not persist after deselect: {len(contactor_groups)}"
                    )
                contactor_ids = [recursive_ids(group) for group in contactor_groups]
                if any(not value for row in contactor_ids for value in row):
                    raise AssertionError("smart pasted group or one of its children has no objectId")
                if set(contactor_ids[0]) & set(contactor_ids[1]):
                    raise AssertionError("smart pasted group retained source group or child IDs")
                for group in contactor_groups:
                    config = group.get("smartConfig") or {}
                    if config.get("physicalPoles") != "3P":
                        raise AssertionError(f"physical poles were not persisted: {config!r}")
                    if config.get("scheduledPoles") != "SCHEDULED 2P":
                        raise AssertionError(f"scheduled-poles text was not persisted separately: {config!r}")
                    if config.get("numberedCount") != 4 or config.get("spareCount") != 2:
                        raise AssertionError(f"numbered/spare contactor counts were not persisted: {config!r}")
                    if config.get("spareLabel") != "AVAILABLE":
                        raise AssertionError(f"edited spare label was not persisted: {config!r}")
                    if config.get("customLabels") != ["C1", "C1", "C2", "SPARE", "SPARE"]:
                        raise AssertionError(f"duplicate custom contactor labels were not persisted: {config!r}")
                    if config.get("quantity") != 5:
                        raise AssertionError(f"automatic custom-label total was not persisted: {config!r}")
                    if config.get("layout") != "vertical" or config.get("gridColumns") != 2:
                        raise AssertionError(f"edited contactor layout/columns were not persisted: {config!r}")
                    if config.get("spacing") != 14:
                        raise AssertionError(f"edited contactor spacing was not persisted: {config!r}")

                page.locator(".page-tab").filter(has_text="Alpha").click()
                page.locator(".page-tab").filter(has_text="Gamma").click()
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="Gamma").wait_for(timeout=30_000)
                if len(workflow_objects(read_project(port), "WICP Annotation Pack")) != 2:
                    raise AssertionError("copy/paste groups did not survive page switching and reload")
                reloaded = read_project(port)
                expected_smart_counts = {
                    "panel-enclosure": 1,
                    "contactor-bank": 2,
                    "relay-bank": 1,
                    "power-monitor-pack": 1,
                    "terminal-bank": 1,
                    "labeled-device": 1,
                }
                for component_type, expected_count in expected_smart_counts.items():
                    actual_count = len(smart_objects(reloaded, component_type))
                    if actual_count != expected_count:
                        raise AssertionError(
                            f"{component_type} did not survive page switch/reload: "
                            f"expected {expected_count}, got {actual_count}"
                        )
                for group in smart_objects(reloaded, "contactor-bank"):
                    config = group.get("smartConfig") or {}
                    if (
                        config.get("customLabels")
                        != ["C1", "C1", "C2", "SPARE", "SPARE"]
                        or config.get("quantity") != 5
                        or config.get("numberedCount") != 4
                        or config.get("spareCount") != 2
                    ):
                        raise AssertionError(
                            "edited Contactor Bank data did not survive page switch/reload: "
                            f"{config!r}"
                        )
                expected_callout_counts = {"round": 2, "square": 1, "block": 2}
                for family, expected_count in expected_callout_counts.items():
                    actual_count = len(callout_objects(reloaded, family))
                    if actual_count != expected_count:
                        raise AssertionError(
                            f"{family} callouts did not survive page switch/reload: "
                            f"expected {expected_count}, got {actual_count}"
                        )
                if len(workflow_objects(reloaded, "Renamed Editable Signage")) != 2:
                    raise AssertionError(
                        "edited placed-symbol copies did not survive page switching and reload"
                    )
                page.goto(f"http://127.0.0.1:{port}/app?project={PROJECT_ID}", wait_until="domcontentloaded")
                page.get_by_role("button", name="Page Editor", exact=False).first.wait_for(timeout=20_000)
                page.goto(editor, wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="Gamma").click()
                page.locator(".nav-section-head").filter(has_text="Components").click()
                page.get_by_text("Component library ready", exact=True).wait_for(timeout=30_000)
                sidebar_controls = page.locator(".libv2-browser-footer button").all_inner_texts()
                if sidebar_controls != expected_sidebar_controls:
                    raise AssertionError(f"Component Browser controls changed after reload: {sidebar_controls!r}")

                selected_count = page.evaluate(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByNames([
                      'Panel Enclosure — WICP-7A',
                      'Contactor Bank C1…SPARE (5)'
                    ]) || 0"""
                )
                if selected_count != 3:
                    raise AssertionError(f"panel-center selection was incomplete: {selected_count}")
                page.get_by_role("button", name="Arrange", exact=True).click()
                page.get_by_role("button", name="◎ Panel", exact=True).click()

                selected_count = page.evaluate(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByNames([
                      'Relay Bank R10–R14',
                      'Power Monitor Pack PS24',
                      'TERMINAL BANK A'
                    ]) || 0"""
                )
                if selected_count != 3:
                    raise AssertionError(f"arrange-control selection was incomplete: {selected_count}")
                page.get_by_role("button", name="↔ Horiz", exact=True).click()
                page.get_by_role("button", name="= H Gaps", exact=True).click()
                page.get_by_role("button", name="◎ Both", exact=True).click()

                selected = page.evaluate(
                    "() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByName('Contactor Bank C1…SPARE (5)') || false"
                )
                if not selected:
                    raise AssertionError("contactor bank was unavailable for explode/regroup")
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Ungroup", exact=True).click()
                page.get_by_role("button", name="Group", exact=True).click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .filter((item) => item.smartComponentType === 'contactor-bank').length === 2""",
                    timeout=20_000,
                )

                selected = page.evaluate(
                    "() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByName('LCP AUXILIARY DEVICE') || false"
                )
                if not selected:
                    raise AssertionError("labeled device was unavailable for single-object assembly proof")
                page.get_by_role("button", name="Ungroup", exact=True).click()
                selected = page.evaluate(
                    "() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByName('Device Label') || false"
                )
                if not selected:
                    raise AssertionError("exploded device label was not independently selectable")
                page.evaluate(
                    """() => {
                      window.__assemblyPromptCalls = [];
                      window.prompt = (...args) => {
                        window.__assemblyPromptCalls.push(args);
                        return 'Saved Editable Device Label';
                      };
                    }"""
                )
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Save Selection as Assembly", exact=True).last.click()
                page.wait_for_timeout(1_200)
                single_saved_card = open_saved_assembly_card(
                    page, "Saved Editable Device Label"
                )
                single_saved_card.click()
                if page.locator(".panel-rail-right").is_visible():
                    page.locator(".panel-rail-right").click()
                page.locator("#sel-text").fill("EDITABLE ASSEMBLY AFTER INSERT")

                selected_count = page.evaluate(
                    "() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectAllByName('WICP Annotation Pack') || 0"
                )
                if selected_count != 2:
                    raise AssertionError(f"multi-select did not select both pasted groups: {selected_count}")
                page.get_by_role("button", name="Home", exact=True).click()
                page.get_by_role("button", name="Group", exact=True).click()
                page.get_by_role("button", name="Ungroup", exact=True).click()
                page.evaluate(
                    """() => {
                      window.__assemblyPromptCalls = [];
                      window.prompt = (...args) => {
                        window.__assemblyPromptCalls.push(args);
                        return 'Saved WICP Pair Assembly';
                      };
                    }"""
                )
                page.get_by_role("button", name="Save Selection as Assembly", exact=True).last.click()
                page.wait_for_timeout(1_200)
                pair_saved_card = open_saved_assembly_card(
                    page, "Saved WICP Pair Assembly"
                )
                pair_saved_card.click(button="right")
                saved_assembly_actions = page.locator(".ctx-menu .ctx-item").all_inner_texts()
                if saved_assembly_actions != [
                    "Edit",
                    "Rename",
                    "Duplicate",
                    "Delete",
                    "Move to Category",
                    "Add to Favorites",
                    "Save as Assembly",
                ]:
                    raise AssertionError(
                        f"saved-assembly context actions are incomplete: {saved_assembly_actions!r}"
                    )
                page.locator(".ctx-backdrop").click(position={"x": 4, "y": 4})
                pair_saved_card.click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Saved WICP Pair Assembly')""",
                    timeout=20_000,
                )
                page.locator(".page-tab").filter(has_text="Alpha").click()
                open_saved_assembly_card(page, "Saved WICP Pair Assembly").click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Saved WICP Pair Assembly')""",
                    timeout=20_000,
                )
                page.evaluate("() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.deselect()")
                page.wait_for_timeout(1_400)
                alpha = next(
                    item for item in read_project(port)["pages"]
                    if item["sheetTitle"] == "Alpha"
                )
                if not any(
                    item.get("objName") == "Saved WICP Pair Assembly"
                    for item in alpha.get("canvasObjects") or []
                ):
                    raise AssertionError("saved assembly did not persist after cross-page insertion")
                page.locator(".page-tab").filter(has_text="Gamma").click()

                launch_component_tool(page, "Signage Legend")
                page.wait_for_function(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                      .some((item) => item.objName === 'Signage Legend')""",
                    timeout=20_000,
                )

                launch_component_tool(page, "Signage Marker Trio")
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
                try:
                    saved_card = open_saved_assembly_card(page, "Saved Signage Assembly")
                except Exception:
                    page.screenshot(path=str(evidence / "saved-assembly-failure.png"), full_page=True)
                    raise AssertionError(
                        f"saved assembly card was absent; project assemblies="
                        f"{read_project(port).get('savedAssemblies')!r}"
                    )
                saved_card.click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Saved Signage Assembly')""",
                    timeout=20_000,
                )

                selected = page.evaluate(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.selectByName(
                      'Callout Blocks / Lists — Electrical Room Markers Renamed'
                    ) || false"""
                )
                if not selected:
                    raise AssertionError("saved callout block was unavailable for later in-place editing")
                page.wait_for_timeout(150)
                page.locator(".sheet-viewport").evaluate(
                    """(element) => {
                      const rect = element.getBoundingClientRect();
                      element.dispatchEvent(new MouseEvent('contextmenu', {
                        bubbles: true,
                        cancelable: true,
                        button: 2,
                        clientX: rect.left + 20,
                        clientY: rect.top + 20,
                      }));
                    }"""
                )
                page.locator(".ctx-menu").get_by_role(
                    "button", name="Edit Callout Block", exact=True
                ).click()
                page.wait_for_timeout(500)
                later_callout_entry = page.get_by_label("Row 3 Description", exact=True)
                if not later_callout_entry.is_visible():
                    later_callout_debug = page.evaluate(
                        """() => ({
                          objects: (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                            .filter((item) => item.objName
                              === 'Callout Blocks / Lists — Electrical Room Markers Renamed')
                            .map((item) => ({
                              objectId: item.objectId,
                              calloutComponentType: item.calloutComponentType,
                              family: item.calloutConfig?.family,
                              setName: item.calloutConfig?.setName,
                            })),
                          dialogs: Array.from(document.querySelectorAll('[role="dialog"]'))
                            .map((element) => element.getAttribute('aria-label')),
                        })"""
                    )
                    raise AssertionError(
                        "later callout edit opened the wrong editor: "
                        f"{later_callout_debug!r}"
                    )
                later_callout_entry.fill("EDITED CALLOUT LATER")
                page.get_by_role("button", name="Update Selected", exact=True).click()

                page.get_by_role("button", name="File", exact=True).hover()
                page.wait_for_timeout(800)
                if page.locator(".s360-app-tooltip").count():
                    raise AssertionError("canvas tooltip remained visible while an object was selected")

                launch_component_tool(page, "Generated Symbol Key")
                page.get_by_role("button", name="File", exact=True).click()
                page.get_by_role("button", name="Save Now", exact=True).click()
                page.wait_for_timeout(1_500)
                page.screenshot(path=str(evidence / "layout-workflow-before-reopen.png"), full_page=True)

                persisted = read_project(port)
                if not any(item["name"] == "Saved Signage Assembly" for item in persisted.get("savedAssemblies") or []):
                    raise AssertionError("saved assembly was not persisted in the project")
                if not any(item["name"] == "Saved Editable Device Label" for item in persisted.get("savedAssemblies") or []):
                    raise AssertionError("single editable object was not persisted as an assembly")
                if not any(item["name"] == "Saved WICP Pair Assembly" for item in persisted.get("savedAssemblies") or []):
                    raise AssertionError("completed multi-selection was not persisted as an assembly")
                gamma = next(item for item in persisted["pages"] if item["sheetTitle"] == "Gamma")
                flat = json.dumps(gamma.get("canvasObjects") or [])
                for marker in [
                    "Saved Signage Assembly",
                    "Saved WICP Pair Assembly",
                    "EDITABLE ASSEMBLY AFTER INSERT",
                    "EDITED CALLOUT LATER",
                    "Electrical Room Markers Renamed",
                    "Round Range 1-10",
                    "Square Callout 1",
                    "MDP",
                    "Rack A",
                    "OAU-01",
                    "Renamed Editable Signage",
                    "EDITED SYMBOL",
                    "Signage Legend",
                    "Generated Symbol Key",
                    "WICP-7A",
                    "SCHEDULED 2P",
                    "PS24",
                    "TERMINAL BANK A",
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

                page.goto(editor, wait_until="domcontentloaded", timeout=60_000)
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.locator(".page-tab").filter(has_text="Gamma").wait_for(timeout=30_000)
                page.locator(".page-tab").filter(has_text="Gamma").click()
                page.wait_for_function(
                    """() => window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                      .some((item) => item.objName === 'Generated Symbol Key')
                      && window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                        .some((item) => item.smartComponentType === 'panel-enclosure')
                      && window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                        .some((item) => item.calloutConfig?.family === 'block')
                      && window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects()
                        .some((item) => item.objName === 'Renamed Editable Signage')
                      && JSON.stringify(window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects())
                        .includes('EDITABLE ASSEMBLY AFTER INSERT')""",
                    timeout=30_000,
                )
                page.locator(".page-tab").filter(has_text="Alpha").click()
                page.wait_for_function(
                    """() => (window.__S360_LAYOUT_WORKFLOW_AUDIT__?.objects() || [])
                      .some((item) => item.objName === 'Saved WICP Pair Assembly')""",
                    timeout=20_000,
                )
                page.locator(".page-tab").filter(has_text="Gamma").click()
                page.screenshot(path=str(evidence / "layout-workflow-after-reopen.png"), full_page=True)
                browser.close()

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
            raise AssertionError("the generated source template changed")
        if file_hash(workbook_copy) != workbook_hash_before_browser:
            raise AssertionError("the disposable linked workbook changed without an authorized Excel write")
        if file_hash(public_catalog) != public_catalog_hash:
            raise AssertionError("the checked-in component catalog changed during disposable testing")
        if api_failures:
            raise AssertionError(f"browser API failures: {api_failures}")
        if page_errors:
            raise AssertionError(f"browser page errors: {page_errors}")
        if console_errors:
            raise AssertionError(f"browser console errors: {console_errors}")
        workbook_write_requests = [
            f"{method} {url}"
            for method, url in requests
            if "/workbook-link/resolve" in url
        ]
        if workbook_write_requests:
            raise AssertionError(f"unexpected workbook write requests: {workbook_write_requests}")
        library_mutation_requests = [
            f"{method} {url}" for method, url in requests
            if any(token in url for token in ["/api/lib/rebuild", "/api/lib/refresh", "/api/lib/migrate"])
        ]
        if library_mutation_requests:
            raise AssertionError(f"unexpected library rebuild/migration requests: {library_mutation_requests}")
        library_edit_requests = [
            f"{method} {url}" for method, url in requests
            if method == "PATCH" and "/api/lib/components/fixture-signage" in url
        ]
        if not library_edit_requests:
            raise AssertionError("right-click library rename/edit did not issue a disposable PATCH")
        final_project = store.load(PROJECT_ID)
        final_gamma = next(
            page for page in final_project["pages"] if page["sheetTitle"] == "Gamma"
        )
        final_ids = [
            object_id
            for project_page in final_project.get("pages") or []
            if project_page.get("pageType") == "canvas"
            for item in project_page.get("canvasObjects") or []
            for object_id in recursive_ids(item)
        ]
        if any(not object_id for object_id in final_ids):
            raise AssertionError("one or more final canvas group/child IDs are blank")
        if len(final_ids) != len(set(final_ids)):
            raise AssertionError("one or more final canvas group/child IDs are duplicated")
        final_callout_counts = {
            family: len(callout_objects(final_project, family))
            for family in ["round", "square", "block"]
        }
        if final_callout_counts != {"round": 2, "square": 1, "block": 2}:
            raise AssertionError(
                f"callouts did not survive project reopen: {final_callout_counts!r}"
            )
        final_contactors = smart_objects(final_project, "contactor-bank")
        if len(final_contactors) != 2:
            raise AssertionError("copied Contactor Banks did not survive project reopen")
        for group in final_contactors:
            config = group.get("smartConfig") or {}
            if (
                config.get("customLabels") != ["C1", "C1", "C2", "SPARE", "SPARE"]
                or config.get("quantity") != 5
                or config.get("physicalPoles") != "3P"
                or config.get("layout") != "vertical"
                or config.get("spacing") != 14
            ):
                raise AssertionError(
                    f"edited Contactor Bank configuration did not survive reopen: {config!r}"
                )
        if len(workflow_objects(final_project, "Renamed Editable Signage")) != 2:
            raise AssertionError("placed-symbol copies did not survive project reopen")
        final_alpha = next(
            page for page in final_project["pages"] if page["sheetTitle"] == "Alpha"
        )
        if not any(
            item.get("objName") == "Saved WICP Pair Assembly"
            for item in final_alpha.get("canvasObjects") or []
        ):
            raise AssertionError("cross-page saved assembly did not survive project reopen")
        print(json.dumps({
            "ok": True,
            "projectId": PROJECT_ID,
            "health": health,
            "workbookCopy": str(workbook_copy),
            "sourceTemplateHashUnchanged": True,
            "linkedWorkbookHashUnchanged": True,
            "publicComponentCatalogHashUnchanged": True,
            "copyPasteGroups": 2,
            "smartCopyPasteGroups": 2,
            "calloutCounts": final_callout_counts,
            "placedSymbolCopies": len(
                workflow_objects(final_project, "Renamed Editable Signage")
            ),
            "testedSmartComponentTypes": [
                "contactor-bank",
                "labeled-device",
                "panel-enclosure",
                "power-monitor-pack",
                "relay-bank",
                "terminal-bank",
            ],
            "remainingGroupedSmartComponentTypes": sorted({
                item.get("smartComponentType")
                for item in final_gamma.get("canvasObjects") or []
                if item.get("smartComponentType")
            }),
            "uniqueCanvasObjectIds": len(final_ids),
            "savedAssemblies": len(final_project.get("savedAssemblies") or []),
            "workbookSyncRequests": workbook_write_requests,
            "libraryMutationRequests": library_mutation_requests,
            "disposableLibraryEditRequests": library_edit_requests,
            "evidence": str(evidence),
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
