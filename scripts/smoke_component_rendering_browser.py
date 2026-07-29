"""Visual browser regression for SVG component and legend insertion.

This smoke is deliberately isolated from customer data.  It creates a
dimensionless V40-style SVG, a saved component record with corrupt crop/bounds,
and an editable legend in a disposable SINGH360_DOCS_DIR.  Passing requires
opaque-pixel and bounding-box evidence after insertion and after local
save/reload; object counts and URLs alone are not sufficient.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.legend_template_store import LegendTemplateStore
from core.library_v2 import LibraryV2
from core.project_store import ProjectStore

PROJECT_ID = "c0ffee40c0ffee40"
COMPONENT_NAME = "V40 Render Fixture"
SOURCE_REL = "components/symbols_markers/plan_markers/v40_render_fixture.svg"
SOURCE_URL = f"/api/lib/asset/{SOURCE_REL}"


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
    raise RuntimeError("isolated component-render server did not become healthy")


def fixture_project() -> dict:
    corrupted = {
        "type": "Image",
        "version": "6.9.1",
        "originX": "left",
        "originY": "top",
        "left": 80,
        "top": 80,
        "width": 1,
        "height": 96,
        "fill": "rgb(0,0,0)",
        "stroke": None,
        "strokeWidth": 0,
        "strokeDashArray": None,
        "strokeLineCap": "butt",
        "strokeDashOffset": 0,
        "strokeLineJoin": "miter",
        "strokeUniform": False,
        "strokeMiterLimit": 4,
        "scaleX": 96,
        "scaleY": 1,
        "angle": 0,
        "flipX": False,
        "flipY": False,
        "opacity": 1,
        "shadow": None,
        "visible": True,
        "backgroundColor": "",
        "fillRule": "nonzero",
        "paintFirst": "fill",
        "globalCompositeOperation": "source-over",
        "skewX": 0,
        "skewY": 0,
        "cropX": 95,
        "cropY": 0,
        "src": SOURCE_URL,
        "crossOrigin": "anonymous",
        "filters": [],
        "sourceUrl": SOURCE_URL,
        "objName": "Existing Clipped V40 Fixture",
        "symCategory": "symbols_markers",
        "symAcronym": "TS",
        "selectable": True,
        "evented": True,
    }
    page = {
        "id": "render-page",
        "order": 1,
        "include": True,
        "publishStatus": "YES",
        "issueStatus": "draft",
        "sheetCode": "EMS V.40",
        "displaySheetCode": "EMS V.40",
        "sheetTitle": "Component Render Regression",
        "sheetTab": "RENDER FIXTURE",
        "pageType": "canvas",
        "templateId": "blank",
        "blocks": [],
        "canvasObjects": [corrupted],
        "notes": "",
        "pageNumber": 1,
        "pageTotal": 1,
    }
    return {
        "id": PROJECT_ID,
        "projectDisplayName": "Sanitized V40 Render Fixture",
        "metadata": {"projectName": "Sanitized V40 Render Fixture"},
        "worksheets": [],
        "pages": [page],
        "sources": [],
        "workbookSync": {"status": "not_linked"},
    }


def create_fixture(docs: Path) -> tuple[dict, str]:
    library = LibraryV2(docs)
    svg_path = library.root / SOURCE_REL
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    # Intentionally no width/height: this exercises intrinsic-dimension
    # normalization at the server boundary.
    svg_path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" """
        """data-renderer="singh360-plan-ring-v40">"""
        """<circle cx="48" cy="48" r="40" fill="#ffffff" stroke="#111827" stroke-width="7"/>"""
        """<path d="M20 48H76M48 20V76" stroke="#dc2626" stroke-width="6"/>"""
        """<circle cx="48" cy="48" r="13" fill="#2563eb"/>"""
        """</svg>""",
        encoding="utf-8",
    )
    library.refresh()
    manifest = library._read_manifest()  # noqa: SLF001 - sanitized fixture setup
    component = next(
        item for item in manifest["components"]
        if str(item.get("sourceFile") or "").replace("\\", "/") == SOURCE_REL
    )
    component.update(
        {
            "displayName": COMPONENT_NAME,
            "defaultLabel": "",
            "shortName": "TS",
            "category": "symbols_markers",
            "categories": ["symbols_markers"],
            "collection": "Singh360 Plan Markers",
            "rendererVersion": "singh360-plan-ring-v40",
            "status": "approved",
            "approved": True,
            "defaultWidth": 96,
            "defaultHeight": 96,
            "source": {
                "file": SOURCE_REL,
                "rendererVersion": "singh360-plan-ring-v40",
                "standardKey": "PLAN|TS|RENDER-FIXTURE",
            },
        }
    )
    library._write_manifest(manifest)  # noqa: SLF001 - sanitized fixture setup

    legend = LegendTemplateStore(docs).save_template(
        name="V40 Visible Render Legend",
        category="symbols_markers",
        title="VISIBLE SYMBOL LEGEND",
        rows=[
            {
                "id": "v40-render-row",
                "key": "PLAN|TS|RENDER-FIXTURE",
                "code": "TS",
                "glyph": "TS",
                "label": "VISIBLE TEST SYMBOL",
                "enabled": True,
                "highlighted": True,
                "shape": "circle",
                "rendererVersion": "singh360-plan-ring-v40",
                "symbolUrl": SOURCE_URL,
                "componentId": component["id"],
            }
        ],
    )
    project = fixture_project()
    ProjectStore(docs).save(PROJECT_ID, project)
    return project, str(legend["id"])


def render_audit(page: Page) -> list[dict]:
    page.wait_for_function(
        "() => typeof window.__S360_CANVAS_RENDER_AUDIT__ === 'function'",
        timeout=30_000,
    )
    return page.evaluate("() => window.__S360_CANVAS_RENDER_AUDIT__()")


def assert_visible(item: dict, stage: str) -> None:
    if float(item["width"]) < 20 or float(item["height"]) < 20:
        raise AssertionError(f"{stage}: collapsed rendered bounds: {item}")
    if float(item["cropX"]) != 0 or float(item["cropY"]) != 0:
        raise AssertionError(f"{stage}: stale crop remains: {item}")
    rendered_area = float(item["width"]) * float(item["height"])
    if int(item["pixelCount"]) < max(120, rendered_area * 0.25):
        raise AssertionError(f"{stage}: too few visible pixels for its rendered size: {item}")
    if float(item["pixelWidthRatio"]) < 0.75 or float(item["pixelHeightRatio"]) < 0.75:
        raise AssertionError(f"{stage}: clipped pixel bounds: {item}")


def matching(items: list[dict], name_fragment: str) -> dict:
    try:
        return next(item for item in items if name_fragment in str(item.get("name") or ""))
    except StopIteration as exc:
        raise AssertionError(f"render audit missing {name_fragment!r}: {items}") from exc


def read_project(port: int) -> dict:
    with urlopen(f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}", timeout=10) as response:
        return json.load(response)


def walk_objects(items: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for item in items:
        flattened.append(item)
        if isinstance(item.get("objects"), list):
            flattened.extend(walk_objects(item["objects"]))
    return flattened


def export_pdf(port: int, page_id: str) -> int:
    request = Request(
        f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}/export/pdf",
        data=json.dumps(
            {
                "width": 17,
                "height": 11,
                "pageIds": [page_id],
                "confirmPreflight": True,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        payload = response.read()
        if response.status != 200 or not payload.startswith(b"%PDF"):
            raise AssertionError("disposable component-render PDF export failed")
        return len(payload)


def main() -> int:
    evidence_root = Path(
        os.environ.get("SINGH360_RENDER_EVIDENCE_DIR", ROOT / "runtime_artifacts" / "component-rendering")
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence = evidence_root / stamp
    evidence.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix="singh360_component_render_") as raw:
        runtime = Path(raw)
        docs = runtime / ".docs"
        project, legend_id = create_fixture(docs)
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
            stdout=(evidence / "server.out.log").open("w", encoding="utf-8"),
            stderr=(evidence / "server.err.log").open("w", encoding="utf-8"),
        )
        browser = None
        console_errors: list[str] = []
        failed_responses: list[str] = []
        report: dict = {"evidence": str(evidence), "projectId": PROJECT_ID}
        try:
            report["health"] = wait_health(port)
            with urlopen(f"http://127.0.0.1:{port}{SOURCE_URL}", timeout=10) as response:
                served_svg = response.read().decode("utf-8")
            if '<svg width="96" height="96"' not in served_svg:
                raise AssertionError(f"served SVG has no intrinsic dimensions: {served_svg[:180]}")
            report["servedIntrinsicDimensions"] = True

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    headless=True,
                )
                page = browser.new_page(viewport={"width": 1440, "height": 960})
                page.on(
                    "console",
                    lambda message: console_errors.append(
                        f"{message.text} @ {message.location}"
                    ) if message.type == "error" else None,
                )
                page.on(
                    "response",
                    lambda response: failed_responses.append(f"{response.status} {response.url}")
                    if response.status >= 400 else None,
                )
                base = (
                    f"http://127.0.0.1:{port}/app?project={PROJECT_ID}"
                    "&mode=editor&renderAudit=1"
                )
                page.goto(base, wait_until="domcontentloaded", timeout=60_000)
                page.locator(".ribbon").wait_for(timeout=30_000)

                initial = render_audit(page)
                existing = matching(initial, "Existing Clipped V40 Fixture")
                assert_visible(existing, "existing saved component repair")
                if abs(float(existing["width"]) - 96) > 0.1 or abs(float(existing["height"]) - 96) > 0.1:
                    raise AssertionError(f"saved component display size changed: {existing}")
                page.screenshot(path=evidence / "01-existing-saved-repaired.png", full_page=True)

                page.locator(".panel-rail-left").click()
                page.locator(".panel-left").wait_for(timeout=10_000)
                page.locator(".nav-section-head").filter(has_text=re.compile("Components", re.IGNORECASE)).click()
                card = page.locator(".libv2-card").filter(has_text=COMPONENT_NAME)
                card.wait_for(timeout=15_000)
                preview = card.locator("img").first
                if preview.count() and preview.evaluate("(node) => getComputedStyle(node).objectFit") != "contain":
                    raise AssertionError("component library preview is not contain-sized")
                card.get_by_role("button", name="Insert", exact=True).click()
                page.wait_for_function(
                    """name => (window.__S360_CANVAS_RENDER_AUDIT__?.() || [])
                      .some(item => item.name.includes(name))""",
                    arg=COMPONENT_NAME,
                    timeout=20_000,
                )
                direct = matching(render_audit(page), COMPONENT_NAME)
                assert_visible(direct, "direct insertion")
                page.screenshot(path=evidence / "02-direct-insert-visible.png", full_page=True)

                saved_card = page.locator(".libv2-saved-legend-card").filter(
                    has_text="V40 Visible Render Legend"
                )
                saved_card.wait_for(timeout=15_000)
                saved_card.click()
                page.get_by_role("heading", name="Build / Insert Symbol Legend").wait_for(timeout=15_000)
                page.get_by_role("button", name="Insert legend", exact=True).click()
                page.wait_for_function(
                    """() => (window.__S360_CANVAS_RENDER_AUDIT__?.() || [])
                      .some(item => item.name.includes('Legend TS'))""",
                    timeout=20_000,
                )
                legend = matching(render_audit(page), "Legend TS")
                assert_visible(legend, "legend insertion")
                page.screenshot(path=evidence / "03-legend-insert-visible.png", full_page=True)

                page.get_by_role("button", name="Save Now", exact=True).click()
                page.wait_for_function(
                    """() => !['UNSAVED PROJECT EDITS', 'SAVING PROJECT…', 'SAVE FAILED']
                      .includes(document.querySelector('.save-state-control .status-pill')
                      ?.textContent || '')""",
                    timeout=30_000,
                )
                saved = read_project(port)
                saved_objects = walk_objects(saved["pages"][0].get("canvasObjects") or [])
                repaired = matching(
                    [
                        {
                            "name": item.get("objName"),
                            **item,
                        }
                        for item in saved_objects
                    ],
                    "Existing Clipped V40 Fixture",
                )
                if (
                    float(repaired.get("left") or 0) != 80
                    or float(repaired.get("top") or 0) != 80
                    or float(repaired.get("cropX") or 0) != 0
                    or float(repaired.get("cropY") or 0) != 0
                    or abs(float(repaired.get("width") or 0) * float(repaired.get("scaleX") or 0) - 96) > 0.1
                    or abs(float(repaired.get("height") or 0) * float(repaired.get("scaleY") or 0) - 96) > 0.1
                ):
                    raise AssertionError(f"serialized repair did not preserve placement/size: {repaired}")

                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.locator(".ribbon").wait_for(timeout=30_000)
                reloaded = render_audit(page)
                for fragment in ("Existing Clipped V40 Fixture", COMPONENT_NAME, "Legend TS"):
                    assert_visible(matching(reloaded, fragment), f"reload {fragment}")
                page.screenshot(path=evidence / "04-save-reload-visible.png", full_page=True)

                report["initialAudit"] = initial
                report["afterReloadAudit"] = reloaded
                report["savedObjectCount"] = len(saved_objects)
                report["legendTemplateId"] = legend_id
                if console_errors or failed_responses:
                    raise AssertionError(
                        f"browser errors={console_errors}; failed responses={failed_responses}"
                    )
                browser.close()
                browser = None

            report["pdfBytes"] = export_pdf(port, project["pages"][0]["id"])
            report["ok"] = True
            (evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    # The Playwright context may already have closed while
                    # propagating the primary test failure.
                    pass
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
