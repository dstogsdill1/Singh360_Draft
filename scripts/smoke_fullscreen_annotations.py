"""Disposable Edge browser/PDF smoke for fullscreen and page annotations.

The workflow never opens a customer project or linked workbook. It creates
three sanitized page types in a temporary SINGH360_DOCS_DIR, drives the real
editor in Microsoft Edge, restarts the isolated server, and inspects two proof
PDFs (annotations included, then one page excluded).
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import fitz
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.project_store import ProjectStore

PROJECT_ID = "360a660a660a660a"
BODY_W = 1598
BODY_H = 866
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def require(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def native_path(value: Path) -> Path:
    """Translate a WSL /mnt/<drive>/ path when this script runs in Windows Python."""
    text = str(value).replace("\\", "/")
    if os.name == "nt" and text.startswith("/mnt/") and len(text) > 7 and text[6] == "/":
        return Path(f"{text[5].upper()}:/{text[7:]}")
    return value


def send_os_escape() -> str:
    """Send a real Windows Escape key so browser chrome receives it."""
    user32 = ctypes.windll.user32
    candidates: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def collect(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if "Singh360 Draft" in title:
            candidates.append((int(hwnd), title))
        return True

    callback = callback_type(collect)
    user32.EnumWindows(callback, 0)
    require(candidates, "could not find the visible Singh360 Draft Edge window for OS Escape")
    hwnd, title = candidates[0]
    activation = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "$shell = New-Object -ComObject WScript.Shell; "
                f"if (-not $shell.AppActivate('{title.replace("'", "''")}')) {{ exit 3 }}; "
                "Start-Sleep -Milliseconds 350; $shell.SendKeys('{ESC}')"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    require(activation.returncode == 0, f"Windows could not activate the Edge window for Escape: {activation.stderr}")
    time.sleep(0.35)
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)
    user32.keybd_event(0x1B, 0, 0, 0)
    user32.keybd_event(0x1B, 0, 0x0002, 0)
    return title


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int) -> dict[str, Any]:
    for _ in range(240):
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                if response.status == 200:
                    return json.load(response)
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("isolated fullscreen/annotation server did not become healthy")


def stop_server(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def start_server(docs: Path, port: int, log_path: Path) -> tuple[subprocess.Popen[str], Any]:
    stream = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "server.py")],
        cwd=ROOT,
        env={
            **os.environ,
            "SINGH360_DOCS_DIR": str(docs),
            "SINGH360_PORT": str(port),
            "SINGH360_OWNERSHIP_TOKEN": "fullscreen-annotation-smoke",
        },
        stdout=stream,
        stderr=subprocess.STDOUT,
        text=True,
    )
    wait_health(port)
    return process, stream


def normal_rect(object_id: str, *, left: int, top: int, fill: str) -> dict[str, Any]:
    return {
        "type": "Rect",
        "version": "6.0.0",
        "objectId": object_id,
        "originX": "left",
        "originY": "top",
        "left": left,
        "top": top,
        "width": 180,
        "height": 100,
        "fill": fill,
        "stroke": "#111827",
        "strokeWidth": 2,
        "scaleX": 1,
        "scaleY": 1,
        "angle": 0,
        "opacity": 1,
        "visible": True,
    }


def fixture_project() -> dict[str, Any]:
    worksheet = {
        "id": "ws-annotation-smoke",
        "name": "Disposable Schedule",
        "grid": [
            ["DISPOSABLE SPREADSHEET PAGE", "STATUS", "OWNER"],
            ["Annotation overlay contract", "TEST", "Singh360"],
            ["Underlying cells remain editable", "PASS", "Disposable"],
            ["Workbook write-back", "FORBIDDEN", "Not linked"],
        ],
        "styles": {
            "A1": {"fontSize": 14, "bold": True, "fill": "#F4B183"},
            "A2": {"fontSize": 11},
            "B2": {"fontSize": 11, "bold": True},
        },
        "mergedCells": [],
        "colWidthsPx": [520, 220, 300],
        "rowHeightsPx": [40, 34, 34, 34],
        "hiddenRows": [],
        "hiddenColumns": [],
    }
    image_svg = (
        "data:image/svg+xml;utf8,"
        "%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='650' viewBox='0 0 1200 650'%3E"
        "%3Crect width='1200' height='650' fill='%23eef3f8'/%3E"
        "%3Crect x='60' y='60' width='1080' height='530' fill='%23ffffff' stroke='%2318273b' stroke-width='8'/%3E"
        "%3Cpath d='M120 190H1080M120 320H1080M120 450H1080' stroke='%23788496' stroke-width='4'/%3E"
        "%3Ctext x='600' y='130' text-anchor='middle' font-family='Arial' font-size='44' fill='%2318273b'%3E"
        "DISPOSABLE IMAGE BACKING%3C/text%3E%3C/svg%3E"
    )
    pages = [
        {
            "id": "spreadsheet-page",
            "order": 1,
            "include": True,
            "publishStatus": "YES",
            "issueStatus": "draft",
            "sheetCode": "SS-1",
            "displaySheetCode": "SS-1",
            "sheetTitle": "Spreadsheet Annotation Proof",
            "sheetTab": worksheet["name"],
            "pageType": "data-grid",
            "templateId": "excel-range",
            "renderMode": "page_local_spreadsheet",
            "linkedWorksheetId": worksheet["id"],
            "drawingRange": "A1:C4",
            "blocks": [],
            "canvasObjects": [normal_rect("normal-spreadsheet-rect", left=1160, top=620, fill="#dbeafe")],
            "notes": "",
            "pageNumber": 1,
            "pageTotal": 3,
        },
        {
            "id": "image-page",
            "order": 2,
            "include": True,
            "publishStatus": "YES",
            "issueStatus": "draft",
            "sheetCode": "IMG-1",
            "displaySheetCode": "IMG-1",
            "sheetTitle": "Image Annotation Proof",
            "sheetTab": "IMAGE PROOF",
            "pageType": "canvas",
            "templateId": "blank",
            "sourceImport": {"type": "image", "originalFileName": "generated-smoke.svg"},
            "blocks": [{
                "id": "image-base",
                "type": "imagePlaceholder",
                "url": image_svg,
                "filename": "generated-smoke.svg",
                "text": "Disposable image backing",
            }],
            "canvasObjects": [normal_rect("normal-image-rect", left=1050, top=650, fill="#dcfce7")],
            "notes": "",
            "pageNumber": 2,
            "pageTotal": 3,
        },
        {
            "id": "drawing-page",
            "order": 3,
            "include": True,
            "publishStatus": "YES",
            "issueStatus": "draft",
            "sheetCode": "DWG-1",
            "displaySheetCode": "DWG-1",
            "sheetTitle": "Normal Drawing Annotation Proof",
            "sheetTab": "DRAWING PROOF",
            "pageType": "text",
            "templateId": "blank",
            "blocks": [{
                "id": "normal-base-text",
                "type": "paragraph",
                "text": "NORMAL DRAWING BASE TOKEN — annotations stay above this editable page content.",
            }],
            "canvasObjects": [normal_rect("normal-drawing-rect", left=980, top=610, fill="#f3e8ff")],
            "notes": "",
            "pageNumber": 3,
            "pageTotal": 3,
        },
    ]
    return {
        "id": PROJECT_ID,
        "schemaVersion": 1,
        "projectMode": "standalone_layout",
        "managedPagePolicy": "preserve_existing",
        "projectDisplayName": "Disposable Fullscreen Annotation Proof",
        "metadata": {
            "projectName": "Disposable Fullscreen Annotation Proof",
            "drawingPackageFileName": "fullscreen_annotation_proof",
        },
        "worksheets": [worksheet],
        "pages": pages,
        "sources": [],
        "workbookSync": {"mode": "none", "status": "not_linked", "workbook": ""},
    }


def get_project(port: int) -> dict[str, Any]:
    with urlopen(f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}", timeout=15) as response:
        return json.load(response)


def export_pdf(port: int, destination: Path) -> int:
    request = Request(
        f"http://127.0.0.1:{port}/api/projects/{PROJECT_ID}/export/pdf",
        data=json.dumps({"width": 17, "height": 11, "confirmPreflight": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            payload = response.read()
    except HTTPError as error:
        raise AssertionError(f"PDF export HTTP {error.code}: {error.read().decode('utf-8', 'replace')}") from error
    require(payload.startswith(b"%PDF"), "export response was not a PDF")
    destination.write_bytes(payload)
    return len(payload)


def active_page_id(page: Page) -> str:
    return page.locator(".annotation-layer").get_attribute("data-page-id") or ""


def wait_annotation_page(page: Page, page_id: str) -> None:
    page.wait_for_function(
        """expected => {
          const layer = document.querySelector('.annotation-layer');
          return layer?.getAttribute('data-page-id') === expected
            && layer.querySelector('.annotation-canvas-wrap')?.getAttribute('data-annotation-hydrated') === '1'
            && window.__S360_ANNOTATION_AUDIT__;
        }""",
        arg=page_id,
        timeout=30_000,
    )


def audit_objects(page: Page) -> list[dict[str, Any]]:
    return page.evaluate("() => window.__S360_ANNOTATION_AUDIT__.objects()")


def annotation_bounds(page: Page) -> dict[str, float]:
    return page.evaluate("() => window.__S360_ANNOTATION_AUDIT__.canvasBounds()")


def scene_to_client(bounds: dict[str, float], x: float, y: float) -> tuple[float, float]:
    return (
        bounds["left"] + x / BODY_W * bounds["width"],
        bounds["top"] + y / BODY_H * bounds["height"],
    )


def drag_scene(page: Page, start: tuple[float, float], end: tuple[float, float], *, steps: int = 8) -> None:
    bounds = annotation_bounds(page)
    x1, y1 = scene_to_client(bounds, *start)
    x2, y2 = scene_to_client(bounds, *end)
    page.mouse.move(x1, y1)
    page.mouse.down()
    page.mouse.move(x2, y2, steps=steps)
    page.mouse.up()


def click_scene(page: Page, point: tuple[float, float], *, count: int = 1) -> None:
    bounds = annotation_bounds(page)
    x, y = scene_to_client(bounds, *point)
    page.mouse.click(x, y, click_count=count)


def toolbar(page: Page):
    return page.get_by_test_id("annotation-toolbar")


def choose_tool(page: Page, name: str) -> None:
    button = toolbar(page).get_by_role("button", name=name, exact=True)
    button.click()
    page.wait_for_function(
        """label => document.querySelector(`[data-testid="annotation-toolbar"] [aria-label="${label}"]`)?.getAttribute('aria-pressed') === 'true'""",
        arg=name,
        timeout=10_000,
    )
    if name != "Select Annotation":
        page.wait_for_function("() => !document.querySelector('[data-testid=\"annotation-properties\"]')", timeout=10_000)
    page.wait_for_timeout(180)


def select_type(page: Page, annotation_type: str) -> dict[str, Any]:
    require(
        page.evaluate("kind => window.__S360_ANNOTATION_AUDIT__.selectByType(kind)", annotation_type),
        f"could not select annotation type {annotation_type}",
    )
    page.get_by_test_id("annotation-properties").wait_for(timeout=10_000)
    return next(item for item in audit_objects(page) if item.get("annotationType") == annotation_type)


def set_control(page: Page, aria_label: str, value: str) -> None:
    control = page.get_by_role("slider", name=aria_label, exact=True) if "opacity" in aria_label.lower() or "width" in aria_label.lower() or "smoothing" in aria_label.lower() else page.get_by_label(aria_label, exact=True)
    control.evaluate(
        """(element, next) => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          setter.call(element, next);
          element.dispatchEvent(new Event('input', { bubbles: true }));
          element.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )
    page.wait_for_timeout(80)


def set_custom_color(page: Page, value: str) -> None:
    control = page.get_by_label("Custom annotation color", exact=True)
    control.evaluate(
        """(element, next) => {
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          setter.call(element, next);
          element.dispatchEvent(new Event('input', { bubbles: true }));
          element.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )
    page.wait_for_timeout(80)


def object_by_type(items: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [item for item in items if item.get("annotationType") == kind]
    require(len(matches) == 1, f"expected exactly one {kind}, found {matches!r}")
    return matches[0]


def wait_saved(page: Page) -> None:
    page.locator("button.status-pill", has_text="PROJECT SAVED").wait_for(timeout=30_000)


def switch_page(page: Page, code: str, expected_id: str) -> None:
    page.locator(".page-tab", has=page.locator(".pt-code", has_text=code)).click()
    wait_annotation_page(page, expected_id)


def draw_spreadsheet_annotations(page: Page, report: dict[str, Any]) -> None:
    choose_tool(page, "Rectangle")
    drag_scene(page, (120, 120), (420, 315))
    choose_tool(page, "Text")
    click_scene(page, (500, 120))
    page.keyboard.type("Initial red text")
    page.keyboard.press("Escape")
    choose_tool(page, "Select Annotation")

    text = object_by_type(audit_objects(page), "text")
    click_scene(page, (float(text.get("left", 500)) + 30, float(text.get("top", 120)) + 20), count=2)
    page.wait_for_function("() => window.__S360_ANNOTATION_AUDIT__.isTextEditing()")
    page.keyboard.press("Control+A")
    page.keyboard.type("Edited red text")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !window.__S360_ANNOTATION_AUDIT__.isTextEditing()")

    choose_tool(page, "Arrow")
    drag_scene(page, (530, 285), (860, 390))
    choose_tool(page, "Highlight")
    drag_scene(page, (120, 470), (690, 470))
    choose_tool(page, "Pen")
    bounds = annotation_bounds(page)
    pen_points = [(760, 500), (800, 450), (850, 520), (900, 455), (960, 510)]
    first = scene_to_client(bounds, *pen_points[0])
    page.mouse.move(*first)
    page.mouse.down()
    for point in pen_points[1:]:
        page.mouse.move(*scene_to_client(bounds, *point), steps=4)
    page.mouse.up()

    defaults = {item["annotationType"]: item for item in audit_objects(page)}
    require(set(defaults) == {"rectangle", "text", "arrow", "highlight", "pen"}, f"five annotation tools did not serialize: {defaults}")
    require(str(defaults["rectangle"].get("stroke", "")).lower() == "#d71920", "rectangle default was not red")
    require(str(defaults["text"].get("fill", "")).lower() == "#d71920", "text default was not red")
    require(str(defaults["arrow"].get("stroke", "")).lower() == "#d71920", "arrow default was not red")
    require(str(defaults["highlight"].get("stroke", "")).lower() == "#ffe600", "highlight default was not yellow")
    require(0.24 <= float(defaults["highlight"].get("opacity", 0)) <= 0.36, "highlight default opacity was not translucent")
    require(str(defaults["pen"].get("stroke", "")).lower() == "#d71920", "pen default was not red")
    report["defaultToolObjects"] = defaults

    select_type(page, "rectangle")
    set_custom_color(page, "#12539b")
    set_control(page, "Annotation stroke width", "9")
    set_control(page, "Rectangle fill opacity", "0.35")

    select_type(page, "text")
    set_custom_color(page, "#6f42c1")
    page.get_by_label("Annotation font size", exact=True).fill("24")
    page.get_by_test_id("annotation-properties").get_by_role("button", name="Bold", exact=True).click()

    select_type(page, "arrow")
    set_custom_color(page, "#16803a")
    set_control(page, "Annotation opacity", "0.75")
    set_control(page, "Annotation stroke width", "7")
    arrowhead = page.get_by_test_id("annotation-properties").get_by_role("button", name="Arrowhead", exact=True)
    arrowhead.click()
    arrowhead.click()

    select_type(page, "highlight")
    set_control(page, "Annotation opacity", "0.45")
    set_control(page, "Annotation stroke width", "30")

    select_type(page, "pen")
    set_custom_color(page, "#ff8c00")
    set_control(page, "Annotation stroke width", "8")
    set_control(page, "Pen smoothing", "5")

    objects = audit_objects(page)
    require(object_by_type(objects, "text").get("text") == "Edited red text", "double-click text edit did not persist")
    require(float(object_by_type(objects, "rectangle").get("strokeWidth", 0)) == 9, "rectangle width property did not apply")
    require(float(object_by_type(objects, "text").get("fontSize", 0)) == 24, "text font size did not apply")
    require(float(object_by_type(objects, "arrow").get("opacity", 0)) == 0.75, "arrow opacity did not apply")
    require(float(object_by_type(objects, "highlight").get("opacity", 0)) == 0.45, "highlight opacity did not apply")
    require(float(object_by_type(objects, "pen").get("annotationSmoothing", 0)) == 5, "pen smoothing did not apply")
    ids = [str(item.get("objectId") or "") for item in objects]
    require(all(ids) and len(ids) == len(set(ids)), f"annotation IDs were not unique: {ids}")
    report["spreadsheetObjectsAfterProperties"] = objects


def draw_colored_rectangle(page: Page, color: str, *, start: tuple[int, int], end: tuple[int, int]) -> None:
    choose_tool(page, "Rectangle")
    drag_scene(page, start, end)
    select_type(page, "rectangle")
    set_custom_color(page, color)
    set_control(page, "Annotation opacity", "1")
    set_control(page, "Annotation stroke width", "18")


def verify_saved_contract(project: dict[str, Any]) -> None:
    by_id = {item["id"]: item for item in project["pages"]}
    require(len(by_id["spreadsheet-page"].get("annotationObjects") or []) == 5, "spreadsheet annotations were not persisted")
    require(len(by_id["image-page"].get("annotationObjects") or []) == 1, "image annotations were not persisted")
    require(len(by_id["drawing-page"].get("annotationObjects") or []) == 1, "drawing annotations were not persisted")
    expected_canvas_ids = {
        "spreadsheet-page": "normal-spreadsheet-rect",
        "image-page": "normal-image-rect",
        "drawing-page": "normal-drawing-rect",
    }
    for page_id, expected in expected_canvas_ids.items():
        canvas_ids = [str(item.get("objectId") or "") for item in by_id[page_id].get("canvasObjects") or []]
        require(expected in canvas_ids, f"normal canvas object changed on {page_id}: {canvas_ids}")
        annotation_ids = [str(item.get("objectId") or "") for item in by_id[page_id].get("annotationObjects") or []]
        require(expected not in annotation_ids, f"normal object leaked into annotation layer on {page_id}")


def count_color(page: fitz.Page, color: tuple[int, int, int], tolerance: int = 36) -> int:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
    data = pixmap.samples
    channels = pixmap.n
    count = 0
    for offset in range(0, len(data), channels):
        if all(abs(data[offset + index] - target) <= tolerance for index, target in enumerate(color)):
            count += 1
    return count


def inspect_pdf(path: Path, *, expect_image_annotation: bool, prior_image_count: int | None = None) -> dict[str, Any]:
    document = fitz.open(path)
    try:
        require(len(document) == 3, f"expected three proof pages, got {len(document)}")
        texts = [page.get_text() for page in document]
        combined = "\n".join(texts)
        require("DISPOSABLE SPREADSHEET PAGE" in texts[0], "spreadsheet base text was lost/rasterized")
        require("NORMAL DRAWING BASE TOKEN" in texts[2], "normal drawing base text was lost/rasterized")
        forbidden = ["Markup", "Annotations", "Enter Fullscreen", "Exit Fullscreen", "Delete All Annotations"]
        require(not any(token in combined for token in forbidden), f"editor UI leaked into PDF text: {combined!r}")
        spreadsheet_blue = count_color(document[0], (18, 83, 155))
        image_cyan = count_color(document[1], (0, 183, 195))
        drawing_magenta = count_color(document[2], (255, 0, 170))
        require(spreadsheet_blue > 25, f"spreadsheet annotation color missing from PDF: {spreadsheet_blue}")
        require(drawing_magenta > 25, f"drawing annotation color missing from PDF: {drawing_magenta}")
        if expect_image_annotation:
            require(image_cyan > 25, f"image annotation color missing from included PDF: {image_cyan}")
        else:
            require(prior_image_count is not None and image_cyan < max(10, prior_image_count * 0.15), f"excluded image annotation remained in PDF: {prior_image_count} -> {image_cyan}")
        return {
            "pageCount": len(document),
            "bytes": path.stat().st_size,
            "spreadsheetBluePixels": spreadsheet_blue,
            "imageCyanPixels": image_cyan,
            "drawingMagentaPixels": drawing_magenta,
            "textLengths": [len(value) for value in texts],
            "editorUiAbsent": True,
        }
    finally:
        document.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--headless", action="store_true", help="Use headless Edge (fullscreen may be unavailable there).")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_root = native_path(args.evidence_dir) if args.evidence_dir else Path(tempfile.mkdtemp(prefix="singh360_fullscreen_annotations_evidence_"))
    evidence = evidence_root / stamp
    evidence.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "projectId": PROJECT_ID,
        "evidence": str(evidence),
        "startedAt": stamp,
        "browser": "Microsoft Edge",
        "headless": args.headless,
    }

    require(EDGE.is_file(), f"Microsoft Edge executable not found: {EDGE}")
    with tempfile.TemporaryDirectory(prefix="singh360_fullscreen_annotations_") as raw:
        runtime = Path(raw)
        docs = runtime / ".docs"
        source = fixture_project()
        ProjectStore(docs).save(PROJECT_ID, source)
        port = free_port()
        process: subprocess.Popen[str] | None = None
        stream = None
        browser = None
        requests: list[dict[str, str]] = []
        try:
            process, stream = start_server(docs, port, evidence / "server-initial.log")
            report["initialHealth"] = wait_health(port)
            base = f"http://127.0.0.1:{port}/app?project={PROJECT_ID}&mode=editor&annotationAudit=1"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=str(EDGE),
                    headless=args.headless,
                    args=["--start-maximized"],
                )
                context = browser.new_context(viewport={"width": 1900, "height": 1050})
                page = context.new_page()
                page.on("request", lambda item: requests.append({"method": item.method, "url": item.url}))
                page.goto(base, wait_until="domcontentloaded", timeout=60_000)
                page.get_by_test_id("fullscreen-toggle").wait_for(timeout=30_000)
                page.get_by_test_id("annotations-toggle").click()
                wait_annotation_page(page, "spreadsheet-page")
                page.get_by_role("button", name="100%", exact=True).last.click()
                choose_tool(page, "Rectangle")

                fullscreen_start = len(requests)
                page.evaluate(
                    """() => {
                      const shell = document.querySelector('.app-shell');
                      window.__S360_FULLSCREEN_CALLS__ = 0;
                      const original = shell.requestFullscreen;
                      shell.requestFullscreen = function(...args) {
                        window.__S360_FULLSCREEN_CALLS__ += 1;
                        return original.apply(this, args);
                      };
                    }"""
                )
                state_before = page.evaluate(
                    """() => ({
                      url: location.href,
                      activeTab: document.querySelector('.page-tab.active')?.textContent,
                      zoom: document.querySelector('.vt-zoom')?.textContent,
                      annotationTool: document.querySelector('[aria-label="Rectangle"]')?.getAttribute('aria-pressed'),
                      bodyClass: document.querySelector('.app-body')?.className,
                    })"""
                )
                require(page.get_by_test_id("fullscreen-toggle").get_attribute("aria-label") == "Enter Fullscreen", "fullscreen button started in wrong state")
                page.get_by_test_id("fullscreen-toggle").click()
                page.wait_for_function("() => document.fullscreenElement?.classList.contains('app-shell') === true", timeout=15_000)
                page.wait_for_function(
                    "() => document.querySelector('[data-testid=\"fullscreen-toggle\"]')?.getAttribute('aria-label') === 'Exit Fullscreen'",
                    timeout=15_000,
                )
                require(page.get_by_test_id("fullscreen-toggle").get_attribute("aria-label") == "Exit Fullscreen", "fullscreenchange did not update Exit state")
                shell_bounds = page.locator(".app-shell").bounding_box()
                viewport = page.evaluate("() => ({ width: innerWidth, height: innerHeight })")
                require(shell_bounds is not None and abs(shell_bounds["width"] - viewport["width"]) < 2 and abs(shell_bounds["height"] - viewport["height"]) < 2, f"app shell did not fill fullscreen viewport: {shell_bounds}, {viewport}")
                page.screenshot(path=str(evidence / "edge-fullscreen.png"), full_page=False)
                page.get_by_test_id("fullscreen-toggle").click()
                page.wait_for_function("() => !document.fullscreenElement", timeout=15_000)
                page.wait_for_function(
                    "() => document.querySelector('[data-testid=\"fullscreen-toggle\"]')?.getAttribute('aria-label') === 'Enter Fullscreen'",
                    timeout=15_000,
                )
                require(page.get_by_test_id("fullscreen-toggle").get_attribute("aria-label") == "Enter Fullscreen", "button exit did not update fullscreen state")
                page.get_by_test_id("fullscreen-toggle").click()
                page.wait_for_function("() => !!document.fullscreenElement", timeout=15_000)
                page.bring_to_front()
                escape_window_title = send_os_escape()
                escape_exit_observed = True
                try:
                    page.wait_for_function("() => !document.fullscreenElement", timeout=3_000)
                except PlaywrightTimeoutError:
                    # Edge launched under automation accepts Fullscreen API entry,
                    # but its browser chrome does not consume automated OS Escape.
                    # Exercise the same browser-controlled fullscreenchange exit so
                    # the app-state assertion can continue without faking CSS.
                    escape_exit_observed = False
                    page.evaluate("() => document.exitFullscreen()")
                    page.wait_for_function("() => !document.fullscreenElement", timeout=15_000)
                page.wait_for_function(
                    "() => document.querySelector('[data-testid=\"fullscreen-toggle\"]')?.getAttribute('aria-label') === 'Enter Fullscreen'",
                    timeout=15_000,
                )
                require(page.get_by_test_id("fullscreen-toggle").get_attribute("aria-label") == "Enter Fullscreen", "Esc exit did not update fullscreen state")
                state_after = page.evaluate(
                    """() => ({
                      url: location.href,
                      activeTab: document.querySelector('.page-tab.active')?.textContent,
                      zoom: document.querySelector('.vt-zoom')?.textContent,
                      annotationTool: document.querySelector('[aria-label="Rectangle"]')?.getAttribute('aria-pressed'),
                      bodyClass: document.querySelector('.app-body')?.className,
                    })"""
                )
                require(state_before == state_after, f"fullscreen changed editor state: {state_before!r} -> {state_after!r}")
                require(page.evaluate("() => window.__S360_FULLSCREEN_CALLS__") == 2, "requestFullscreen was called outside the two button clicks")
                fullscreen_requests = requests[fullscreen_start:]
                require(not any(item["method"] not in {"GET", "OPTIONS"} for item in fullscreen_requests), f"fullscreen triggered a save/mutation: {fullscreen_requests}")
                report["fullscreen"] = {
                    "requestCalls": 2,
                    "buttonExit": True,
                    "escapeExit": escape_exit_observed,
                    "externalFullscreenExitStateSync": True,
                    "escapeWindowTitle": escape_window_title,
                    "shellBounds": shell_bounds,
                    "viewport": viewport,
                    "statePreserved": state_before,
                    "mutationRequests": [],
                }

                page.evaluate(
                    """() => {
                      const shell = document.querySelector('.app-shell');
                      shell.requestFullscreen = () => Promise.reject(new Error('SMOKE FULLSCREEN REJECTION'));
                    }"""
                )
                page.get_by_test_id("fullscreen-toggle").click()
                page.get_by_role("status").filter(has_text="SMOKE FULLSCREEN REJECTION").wait_for(timeout=10_000)
                require(page.locator(".app-shell").count() == 1, "fullscreen rejection broke the app shell")
                page.evaluate("() => document.dispatchEvent(new Event('fullscreenerror'))")
                page.get_by_role("status").filter(has_text="rejected fullscreen").wait_for(timeout=10_000)
                report["fullscreen"]["rejectionHandled"] = True
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.get_by_test_id("annotation-toolbar").wait_for(timeout=30_000)
                wait_annotation_page(page, "spreadsheet-page")

                draw_spreadsheet_annotations(page, report)
                page.screenshot(path=str(evidence / "spreadsheet-annotations.png"), full_page=False)
                switch_page(page, "IMG-1", "image-page")
                draw_colored_rectangle(page, "#00b7c3", start=(220, 180), end=(720, 450))
                page.screenshot(path=str(evidence / "image-annotations.png"), full_page=False)
                switch_page(page, "DWG-1", "drawing-page")
                draw_colored_rectangle(page, "#ff00aa", start=(180, 190), end=(780, 520))
                page.screenshot(path=str(evidence / "drawing-annotations.png"), full_page=False)

                page.get_by_role("button", name="Save Project", exact=True).click()
                wait_saved(page)
                saved = get_project(port)
                verify_saved_contract(saved)
                report["savedCounts"] = {
                    item["id"]: len(item.get("annotationObjects") or []) for item in saved["pages"]
                }

                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.get_by_test_id("annotation-toolbar").wait_for(timeout=30_000)
                for code, page_id, expected in [
                    ("SS-1", "spreadsheet-page", 5),
                    ("IMG-1", "image-page", 1),
                    ("DWG-1", "drawing-page", 1),
                ]:
                    if active_page_id(page) != page_id:
                        switch_page(page, code, page_id)
                    require(len(audit_objects(page)) == expected, f"reload lost annotations on {page_id}")
                report["reloadPersistence"] = True

                stop_server(process)
                process = None
                if stream:
                    stream.close()
                    stream = None
                process, stream = start_server(docs, port, evidence / "server-restart.log")
                report["restartHealth"] = wait_health(port)
                page.goto(base, wait_until="domcontentloaded", timeout=60_000)
                page.get_by_test_id("annotation-toolbar").wait_for(timeout=30_000)
                wait_annotation_page(page, "spreadsheet-page")
                for code, page_id, expected in [
                    ("SS-1", "spreadsheet-page", 5),
                    ("IMG-1", "image-page", 1),
                    ("DWG-1", "drawing-page", 1),
                ]:
                    if active_page_id(page) != page_id:
                        switch_page(page, code, page_id)
                    require(len(audit_objects(page)) == expected, f"restart lost annotations on {page_id}")
                report["restartPersistence"] = True

                if active_page_id(page) != "drawing-page":
                    switch_page(page, "DWG-1", "drawing-page")
                toolbar(page).get_by_role("button", name="Hide Annotations", exact=True).click()
                page.wait_for_function("() => getComputedStyle(document.querySelector('.annotation-layer')).visibility === 'hidden'")
                require(len(audit_objects(page)) == 1, "hide deleted an annotation")
                toolbar(page).get_by_role("button", name="Show Annotations", exact=True).click()
                toolbar(page).get_by_role("button", name="Lock Annotations", exact=True).click()
                page.wait_for_function("() => getComputedStyle(document.querySelector('.annotation-layer')).pointerEvents === 'none'")
                require(toolbar(page).get_by_role("button", name="Rectangle", exact=True).is_disabled(), "lock did not disable creation tools")
                toolbar(page).get_by_role("button", name="Unlock Annotations", exact=True).click()
                report["visibilityAndLock"] = {"hidePreservedObjects": True, "lockBlockedPointerEvents": True}
                page.get_by_role("button", name="Save Project", exact=True).click()
                wait_saved(page)

                included_pdf = evidence / "annotations-included.pdf"
                report["includedPdfBytes"] = export_pdf(port, included_pdf)
                included_audit = inspect_pdf(included_pdf, expect_image_annotation=True)
                report["includedPdf"] = included_audit

                switch_page(page, "IMG-1", "image-page")
                toolbar(page).get_by_role("button", name="Exclude Annotations from Export", exact=True).click()
                page.get_by_role("button", name="Save Project", exact=True).click()
                wait_saved(page)
                excluded_pdf = evidence / "annotations-image-excluded.pdf"
                report["excludedPdfBytes"] = export_pdf(port, excluded_pdf)
                report["excludedPdf"] = inspect_pdf(
                    excluded_pdf,
                    expect_image_annotation=False,
                    prior_image_count=included_audit["imageCyanPixels"],
                )
                final_project = get_project(port)
                verify_saved_contract(final_project)
                image_page = next(item for item in final_project["pages"] if item["id"] == "image-page")
                require(image_page.get("annotationSettings", {}).get("includeInExport") is False, "export exclusion setting did not persist")
                report["exportTogglePersisted"] = True

                unsupported_context = browser.new_context(viewport={"width": 1200, "height": 800})
                unsupported_context.add_init_script(
                    "Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, get: () => false });"
                )
                unsupported = unsupported_context.new_page()
                unsupported.goto(base, wait_until="domcontentloaded", timeout=60_000)
                unsupported.get_by_test_id("fullscreen-toggle").wait_for(timeout=30_000)
                require(unsupported.get_by_test_id("fullscreen-toggle").is_disabled(), "unsupported fullscreen button was not gracefully disabled")
                require(unsupported.locator(".app-shell").count() == 1, "unsupported fullscreen crashed the app")
                unsupported_context.close()
                report["unsupportedFullscreenDisabled"] = True
                context.close()
                browser.close()
                browser = None

            require(not any("workbook-link" in item["url"] or "write-excel" in item["url"] for item in requests), "browser smoke invoked workbook synchronization")
            verify_saved_contract(get_project(port))
            report["requestCount"] = len(requests)
            report["workbookWriteRequests"] = []
            report["completedAt"] = datetime.now(timezone.utc).isoformat()
            (evidence / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({
                "status": "PASS",
                "evidence": str(evidence),
                "fullscreen": report["fullscreen"],
                "savedCounts": report["savedCounts"],
                "includedPdf": report["includedPdf"],
                "excludedPdf": report["excludedPdf"],
            }, indent=2))
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            stop_server(process)
            if stream is not None:
                stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
