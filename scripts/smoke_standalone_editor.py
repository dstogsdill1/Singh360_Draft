"""Disposable end-to-end smoke test for the standalone Singh360 editor.

The test launches this checkout on an unused port with a temporary
``SINGH360_DOCS_DIR``.  It exercises standalone project creation, persistence,
archive/restore, managed PDF import/replacement, restart persistence, and the
final ANSI-B PDF export without touching live projects or source workbooks.

Optional evidence can be retained outside the disposable runtime:

    python scripts/smoke_standalone_editor.py --evidence-dir C:\\temp\\s360-smoke
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import fitz
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
ANSI_B_WIDTH_PT = 17 * 72
ANSI_B_HEIGHT_PT = 11 * 72
SERVER_WAIT_SECONDS = 75
REQUEST_TIMEOUT_SECONDS = 45
PDF_TIMEOUT_SECONDS = 300
FORBIDDEN_REQUEST_PARTS = ("workbook-link", "workbook-quality")


class SmokeFailure(AssertionError):
    """An acceptance assertion failed with actionable evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def error_text(error: BaseException) -> str:
    return str(error).strip() or error.__class__.__name__


@dataclass
class RequestRecord:
    method: str
    path: str
    status: int | None
    elapsedMs: int
    error: str = ""


class HttpProbe:
    """HTTP client that records every application request made by this smoke."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.records: list[RequestRecord] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: Iterable[int] = (200,),
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        **kwargs: Any,
    ) -> requests.Response:
        started = time.monotonic()
        normalized = path if path.startswith("/") else f"/{path}"
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{normalized}",
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            self.records.append(
                RequestRecord(
                    method=method.upper(),
                    path=normalized,
                    status=None,
                    elapsedMs=round((time.monotonic() - started) * 1000),
                    error=error_text(exc),
                )
            )
            raise SmokeFailure(
                f"{method.upper()} {normalized} could not reach the disposable server: {error_text(exc)}"
            ) from exc

        self.records.append(
            RequestRecord(
                method=method.upper(),
                path=normalized,
                status=response.status_code,
                elapsedMs=round((time.monotonic() - started) * 1000),
            )
        )
        accepted = set(expected)
        if response.status_code not in accepted:
            detail = response.text[:2000].replace("\n", " ")
            raise SmokeFailure(
                f"{method.upper()} {normalized} returned {response.status_code}; "
                f"expected {sorted(accepted)}. Response: {detail}"
            )
        return response

    def json(
        self,
        method: str,
        path: str,
        *,
        expected: Iterable[int] = (200,),
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = self.request(
            method,
            path,
            expected=expected,
            timeout=timeout,
            **kwargs,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SmokeFailure(
                f"{method.upper()} {path} returned non-JSON content: {response.text[:1000]}"
            ) from exc
        require(isinstance(payload, dict), f"{method.upper()} {path} returned a non-object JSON payload.")
        return payload


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def python_executable() -> Path:
    current = Path(sys.executable)
    if current.is_file():
        return current
    windows_venv = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if windows_venv.is_file():
        return windows_venv
    raise SmokeFailure("No usable Python interpreter was found for the disposable server.")


def start_server(
    *,
    port: int,
    docs_dir: Path,
    server_log: Path,
) -> tuple[subprocess.Popen[str], Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONUNBUFFERED": "1",
            "SINGH360_DOCS_DIR": str(docs_dir),
            "SINGH360_PORT": str(port),
            "SINGH360_OWNERSHIP_TOKEN": "standalone-editor-smoke",
        }
    )
    server_log.parent.mkdir(parents=True, exist_ok=True)
    stream = server_log.open("a", encoding="utf-8", buffering=1)
    stream.write(f"\n--- server start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    process = subprocess.Popen(
        [str(python_executable()), str(REPO_ROOT / "server.py")],
        cwd=str(REPO_ROOT),
        env=environment,
        stdout=stream,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, stream


def stop_server(process: subprocess.Popen[str] | None, stream: Any | None) -> None:
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    if stream is not None:
        stream.flush()
        stream.close()


def server_log_tail(path: Path, lines: int = 80) -> str:
    if not path.is_file():
        return "(server log was not created)"
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def wait_for_server(probe: HttpProbe, process: subprocess.Popen[str], server_log: Path) -> dict[str, Any]:
    deadline = time.monotonic() + SERVER_WAIT_SECONDS
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeFailure(
                f"Disposable server exited with code {process.returncode}.\n{server_log_tail(server_log)}"
            )
        try:
            return probe.json("GET", "/api/health")
        except SmokeFailure as exc:
            last_error = error_text(exc)
            time.sleep(0.25)
    raise SmokeFailure(
        f"Disposable server did not become healthy within {SERVER_WAIT_SECONDS}s. "
        f"Last error: {last_error}\n{server_log_tail(server_log)}"
    )


def create_fixture_pdf(path: Path, *, revision: str) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    tokens = [f"{revision} PDF PAGE {index}" for index in range(1, 4)]
    document = fitz.open()
    try:
        for index, token in enumerate(tokens, start=1):
            page = document.new_page(width=ANSI_B_WIDTH_PT, height=ANSI_B_HEIGHT_PT)
            background = (0.95, 0.97, 0.99) if revision == "ORIGINAL" else (0.94, 0.99, 0.95)
            page.draw_rect(page.rect, color=(0.05, 0.12, 0.2), fill=background, width=3)
            page.draw_rect(fitz.Rect(54, 54, ANSI_B_WIDTH_PT - 54, 150), color=(0.9, 0.35, 0.05), width=4)
            page.insert_text((78, 112), token, fontsize=30, fontname="helv", color=(0.05, 0.1, 0.18))
            page.insert_text(
                (78, 205),
                f"Standalone managed PDF fixture • source page {index} of 3",
                fontsize=16,
                fontname="helv",
                color=(0.12, 0.2, 0.28),
            )
            page.insert_text((78, 255), f"CONTENT TOKEN {revision}-{index}", fontsize=22, fontname="cour")
            for row in range(7):
                y = 330 + row * 42
                page.draw_line((84, y), (ANSI_B_WIDTH_PT - 84, y), color=(0.25, 0.35, 0.45), width=1)
                page.insert_text((95, y - 10), f"Fixture row {row + 1} / revised content {index}", fontsize=12)
            page.insert_text(
                (ANSI_B_WIDTH_PT - 245, ANSI_B_HEIGHT_PT - 44),
                f"{revision} {index}/3",
                fontsize=13,
                fontname="helv",
            )
        document.save(path)
    finally:
        document.close()
    require(path.is_file() and path.stat().st_size > 2_000, f"Generated PDF is missing or too small: {path}")
    return tokens


def page_by_managed(project: dict[str, Any], kind: str) -> dict[str, Any]:
    matches = [page for page in project.get("pages", []) if page.get("managedPage") == kind]
    require(len(matches) == 1, f"Expected exactly one managed {kind} page, found {len(matches)}.")
    return matches[0]


def page_by_id(project: dict[str, Any], page_id: str) -> dict[str, Any]:
    matches = [page for page in project.get("pages", []) if page.get("id") == page_id]
    require(len(matches) == 1, f"Expected exactly one page {page_id}, found {len(matches)}.")
    return matches[0]


def imported_pages(project: dict[str, Any], group_id: str) -> list[dict[str, Any]]:
    return [
        page
        for page in project.get("pages", [])
        if isinstance(page.get("sourceImport"), dict)
        and page["sourceImport"].get("type") == "pdf"
        and page["sourceImport"].get("importGroupId") == group_id
    ]


def pdf_overlays(page: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(obj)
        for obj in page.get("canvasObjects", [])
        if isinstance(obj, dict) and obj.get("pdfBase") is not True
    ]


def pdf_base(page: dict[str, Any]) -> dict[str, Any]:
    matches = [
        obj
        for obj in page.get("canvasObjects", [])
        if isinstance(obj, dict) and obj.get("pdfBase") is True
    ]
    require(len(matches) == 1, f"Managed PDF page {page.get('id')} must contain exactly one PDF base object.")
    return matches[0]


def get_project(probe: HttpProbe, project_id: str) -> dict[str, Any]:
    return probe.json("GET", f"/api/projects/{project_id}")


def save_project(probe: HttpProbe, project_id: str, project: dict[str, Any]) -> dict[str, Any]:
    return probe.json("POST", f"/api/projects/{project_id}", json=project)


def project_directory(docs_dir: Path, project_id: str) -> Path:
    matches = [path for path in (docs_dir / "projects").glob(f"*__{project_id}") if path.is_dir()]
    require(len(matches) == 1, f"Expected one disposable package folder for {project_id}, found {matches}.")
    return matches[0]


def verify_local_pdf_assets(
    probe: HttpProbe,
    project_dir: Path,
    pages: list[dict[str, Any]],
    *,
    expected_original_name: str = "smoke-source.pdf",
) -> None:
    for page in pages:
        source = page.get("sourceImport") or {}
        require(source.get("originalFileName") == expected_original_name, f"Wrong original PDF name on {page.get('id')}: {source}")
        require(int(source.get("renderDpi") or 0) >= 300, f"PDF page {page.get('id')} rendered below 300 DPI.")
        local_source = project_dir / str(source.get("projectLocalPath") or "")
        require(local_source.is_file(), f"Project-local PDF source is missing: {local_source}")
        render_asset = project_dir / str(source.get("renderAssetPath") or "")
        require(render_asset.is_file(), f"Project-local PDF render is missing: {render_asset}")
        pixmap = fitz.Pixmap(str(render_asset))
        try:
            require(
                pixmap.width >= 3000 and pixmap.height >= 1900,
                f"PDF render is unexpectedly low resolution: {render_asset} = {pixmap.width}x{pixmap.height}",
            )
        finally:
            pixmap = None
        asset_url = str(source.get("renderAssetUrl") or "")
        require(asset_url.startswith("/api/assets/"), f"PDF render URL is not project-local: {asset_url}")
        response = probe.request("GET", asset_url)
        require(len(response.content) > 1_000, f"PDF render asset response is too small: {asset_url}")


def project_snapshot(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "sheetCode": page.get("sheetCode"),
        "displaySheetCode": page.get("displaySheetCode"),
        "sheetTitle": page.get("sheetTitle"),
        "include": page.get("include"),
        "publishStatus": page.get("publishStatus"),
        "order": page.get("order"),
        "notes": page.get("notes"),
        "pdfPlacementMode": page.get("pdfPlacementMode"),
        "suppressTitleBlock": page.get("suppressTitleBlock"),
        "overlays": pdf_overlays(page),
        "baseObjectId": pdf_base(page).get("objectId"),
    }


def assert_project_snapshot(page: dict[str, Any], expected: dict[str, Any]) -> None:
    actual = project_snapshot(page)
    require(actual == expected, f"Replacement changed preserved page state for {page.get('id')}.\nExpected: {expected}\nActual: {actual}")


def nonwhite_pixel_count(page: fitz.Page) -> int:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY, alpha=False)
    return sum(1 for value in pixmap.samples if value < 248)


def inspect_export(
    pdf_bytes: bytes,
    project: dict[str, Any],
    revised_tokens: list[str],
) -> dict[str, Any]:
    expected_pages = [page for page in project.get("pages", []) if page.get("include", True)]
    require(pdf_bytes.startswith(b"%PDF-"), "Export response is not a PDF file.")
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_audit: list[dict[str, Any]] = []
    try:
        require(
            document.page_count == len(expected_pages),
            f"Export page count mismatch: expected {len(expected_pages)}, got {document.page_count}.",
        )
        for index, (rendered, expected) in enumerate(zip(document, expected_pages), start=1):
            width = float(rendered.rect.width)
            height = float(rendered.rect.height)
            require(
                abs(width - ANSI_B_WIDTH_PT) <= 2 and abs(height - ANSI_B_HEIGHT_PT) <= 2,
                f"Export page {index} has wrong media size {width:.2f}x{height:.2f} points.",
            )
            nonwhite = nonwhite_pixel_count(rendered)
            require(nonwhite > 250, f"Export page {index} is blank or nearly blank ({nonwhite} non-white pixels).")
            text = rendered.get_text("text")
            expected_token = ""
            if expected.get("pageType") == "pdf":
                source_index = int((expected.get("sourceImport") or {}).get("sourcePageIndex") or 0)
                expected_token = revised_tokens[source_index]
                require(
                    expected_token in text,
                    f"Export page {index} is stale, clipped, missing, or out of order; "
                    f"expected vector text {expected_token!r}, got {text[:500]!r}.",
                )
                folio = f"Page {index} of {len(expected_pages)}"
                require(
                    folio.casefold() in text.casefold(),
                    f"Full-sheet export page {index} is missing its current package folio {folio!r}.",
                )
            elif expected.get("managedPage") == "cover":
                expected_token = "Standalone HTTP Smoke"
                require(expected_token.casefold() in text.casefold(), f"Cover page {index} does not contain current project settings.")
            elif expected.get("managedPage") == "index":
                expected_token = "Sheet Index"
                require(expected_token.casefold() in text.casefold(), f"Sheet Index page {index} is missing its heading.")
                for listed_page in project.get("pages", []):
                    listed_title = str(listed_page.get("sheetTitle") or "").strip()
                    if not listed_title:
                        continue
                    if listed_page.get("include", True):
                        require(
                            listed_title.casefold() in text.casefold(),
                            f"Sheet Index page {index} is missing included title {listed_title!r}.",
                        )
                    else:
                        require(
                            listed_title.casefold() not in text.casefold(),
                            f"Sheet Index page {index} incorrectly lists excluded title {listed_title!r}.",
                        )
            else:
                expected_token = str(expected.get("sheetTitle") or "")
                require(expected_token.casefold() in text.casefold(), f"Export page {index} is missing title {expected_token!r}.")
            page_audit.append(
                {
                    "pageNumber": index,
                    "projectPageId": expected.get("id"),
                    "sheetCode": expected.get("sheetCode"),
                    "title": expected.get("sheetTitle"),
                    "expectedToken": expected_token,
                    "mediaBoxPoints": [round(width, 2), round(height, 2)],
                    "nonwhitePixels": nonwhite,
                    "textCharacters": len(text),
                }
            )
    finally:
        document.close()
    return {"pageCount": len(page_audit), "pages": page_audit}


def access_log_requests(server_log: Path) -> list[dict[str, Any]]:
    if not server_log.is_file():
        return []
    pattern = re.compile(r'"([A-Z]+) ([^ ]+) HTTP/[0-9.]+" ([0-9]{3})')
    results = []
    for match in pattern.finditer(server_log.read_text(encoding="utf-8", errors="replace")):
        results.append({"method": match.group(1), "path": match.group(2), "status": int(match.group(3))})
    return results


def forbidden_path(path: str) -> bool:
    normalized = path.split("?", 1)[0].casefold()
    return any(part in normalized for part in FORBIDDEN_REQUEST_PARTS) or normalized.endswith("/sync")


def assert_no_forbidden_requests(probe: HttpProbe, server_log: Path) -> list[dict[str, Any]]:
    scripted = [asdict(record) for record in probe.records if forbidden_path(record.path)]
    server_access = [record for record in access_log_requests(server_log) if forbidden_path(str(record["path"]))]
    require(not scripted, f"Smoke client made forbidden workbook-authority requests: {scripted}")
    require(not server_access, f"Browser/server workflow made forbidden workbook-authority requests: {server_access}")
    return access_log_requests(server_log)


def persist_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_smoke(*, workspace: Path, evidence_dir: Path | None) -> dict[str, Any]:
    docs_dir = workspace / "docs"
    external_dir = workspace / "external-sources"
    artifacts = evidence_dir or (workspace / "evidence")
    docs_dir.mkdir(parents=True, exist_ok=True)
    external_dir.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    server_log = artifacts / "server.log"
    request_log_path = artifacts / "request-log.json"
    before_restart_path = artifacts / "project-before-restart.json"
    after_restart_path = artifacts / "project-after-restart.json"
    export_path = artifacts / "standalone-smoke-export.pdf"
    export_audit_path = artifacts / "standalone-smoke-export-audit.json"

    port = available_port()
    probe = HttpProbe(f"http://127.0.0.1:{port}")
    process: subprocess.Popen[str] | None = None
    stream: Any | None = None
    project_id = ""
    first_pid = 0
    second_pid = 0
    success = False
    try:
        process, stream = start_server(port=port, docs_dir=docs_dir, server_log=server_log)
        health = wait_for_server(probe, process, server_log)
        first_pid = int(health.get("pid") or 0)
        require(health.get("ok") is True, f"Health response was not ok: {health}")
        require(int(health.get("configuredPort") or 0) == port, f"Health reported the wrong port: {health}")
        require(Path(str(health.get("repository") or "")).resolve() == REPO_ROOT.resolve(), f"Health reported the wrong checkout: {health}")

        build = probe.json("GET", "/api/debug/routes")
        require(build.get("distIndexExists") is True, f"Compiled frontend index is missing: {build}")
        require(Path(str(build.get("frontendDist") or "")).resolve() == (REPO_ROOT / "frontend" / "dist").resolve(), f"Wrong frontend build served: {build}")
        app_response = probe.request("GET", "/app")
        asset_paths = sorted(set(re.findall(r'(?:src|href)="([^"]*/assets/[^"]+)"', app_response.text)))
        require(asset_paths, "The served /app HTML references no compiled frontend assets.")
        for asset_path in asset_paths:
            asset_response = probe.request("GET", asset_path)
            require(len(asset_response.content) > 100, f"Served build asset is empty: {asset_path}")

        created = probe.json(
            "POST",
            "/api/projects/new",
            expected=(201,),
            json={"projectName": "Standalone HTTP Smoke"},
        )
        project_id = str(created.get("id") or "")
        require(re.fullmatch(r"[a-f0-9]{16}", project_id) is not None, f"New project returned invalid ID: {created}")
        project = get_project(probe, project_id)
        require(project.get("projectMode") == "standalone_layout", f"Project is not standalone: {project.get('projectMode')}")
        require((project.get("workbookSync") or {}).get("enabled") is False, "Standalone project did not disable external synchronization.")
        require(len(project.get("pages", [])) == 3, f"New full project should contain cover, index, and blank page: {project.get('pages')}")
        cover = page_by_managed(project, "cover")
        index = page_by_managed(project, "index")
        blank = next((page for page in project["pages"] if page.get("pageType") == "canvas"), None)
        require(blank is not None, "New project did not create its managed initial blank layout page.")
        require(project["pages"][0]["id"] == cover["id"] and project["pages"][1]["id"] == index["id"], "Cover and Sheet Index are not first.")
        require(cover.get("appManaged") is True and index.get("appManaged") is True, "Cover or Sheet Index is not app-managed.")

        project["metadata"].update(
            {
                "projectName": "Standalone HTTP Smoke",
                "client": "Sanitized Client",
                "storeNumber": "TEST-001",
                "location": "Disposable Runtime",
                "drawingSetTitle": "Standalone Acceptance Set",
                "revision": "A",
                "drawingPackageFileName": "standalone_smoke_initial",
                "notes": "Generated only by the disposable standalone smoke.",
            }
        )
        blank.update(
            {
                "sheetCode": "A-101",
                "displaySheetCode": "A-101",
                "sheetTitle": "Smoke Blank Layout",
                "sheetTab": "Smoke Blank Layout",
                "notes": "Blank layout metadata persists.",
                "order": 4,
                "include": True,
            }
        )
        now = "2026-08-01T12:00:00Z"
        notes_page = {
            "id": "page_smoke_notes_01",
            "order": 3,
            "include": False,
            "publishStatus": "NO",
            "sheetCode": "A-100",
            "displaySheetCode": "A-100",
            "sheetTitle": "Smoke Notes Excluded",
            "sheetTab": "Smoke Notes Excluded",
            "pageType": "canvas",
            "pageFamily": "drawing",
            "renderMode": "canvas",
            "templateId": "ansi-b-standard",
            "blocks": [],
            "canvasObjects": [{"type": "textbox", "objectId": "smoke_note_object", "text": "Excluded smoke note", "left": 140, "top": 120}],
            "notes": "Used to prove reorder and include/exclude persistence.",
            "createdAt": now,
            "modifiedAt": now,
        }
        project["pages"] = [cover, index, notes_page, blank]
        saved = save_project(probe, project_id, project)
        reloaded = get_project(probe, project_id)
        require(reloaded["metadata"]["client"] == "Sanitized Client", "Project Settings did not survive save/reload.")
        require([page["id"] for page in reloaded["pages"][:4]] == [cover["id"], index["id"], notes_page["id"], blank["id"]], "Page reorder did not survive save/reload.")
        require(page_by_id(reloaded, notes_page["id"])["include"] is False, "Excluded page became included after reload.")
        require(page_by_id(reloaded, blank["id"])["sheetTitle"] == "Smoke Blank Layout", "Blank page metadata did not persist.")
        managed_index = page_by_managed(reloaded, "index")
        require(managed_index.get("standaloneIndex") is True, "Sheet Index is not driven by standalone project pages.")
        included_ids = [page["id"] for page in reloaded["pages"] if page.get("include", True)]
        require(blank["id"] in included_ids, "Included blank page is missing from the standalone package order.")
        require(notes_page["id"] not in included_ids, "Excluded notes page remained in the standalone package order.")
        require(
            managed_index.get("indexRowsOnPage") == len(included_ids),
            f"Automatic Sheet Index row count is stale: expected {len(included_ids)}, got {managed_index.get('indexRowsOnPage')}.",
        )

        archived = probe.json("POST", f"/api/projects/{project_id}/archive", json={"reason": "Disposable archive smoke"})
        require((archived.get("project") or {}).get("archived") is True, f"Archive response did not mark project archived: {archived}")
        listed = probe.json("GET", "/api/projects")
        require(project_id not in {item.get("id") for item in listed.get("projects", [])}, "Archived project remained in Active Projects.")
        require(project_id in {item.get("id") for item in listed.get("archivedProjects", [])}, "Archived project is missing from Archived Projects.")
        restored = probe.json("POST", f"/api/projects/{project_id}/restore")
        require((restored.get("project") or {}).get("archived") is False, f"Restore response still marks project archived: {restored}")
        listed = probe.json("GET", "/api/projects")
        require(project_id in {item.get("id") for item in listed.get("projects", [])}, "Restored project did not return to Active Projects.")

        source_pdf = external_dir / "smoke-source.pdf"
        original_tokens = create_fixture_pdf(source_pdf, revision="ORIGINAL")
        with source_pdf.open("rb") as handle:
            preview = probe.json(
                "POST",
                f"/api/projects/{project_id}/pdf/import-preview",
                files={"file": (source_pdf.name, handle, "application/pdf")},
                timeout=PDF_TIMEOUT_SECONDS,
            )
        require(preview.get("pageCount") == 3, f"PDF preview did not report three pages: {preview}")
        require([page.get("pageNumber") for page in preview.get("pages", [])] == [1, 2, 3], "PDF preview changed source page order.")
        require(not preview.get("existingGroups"), f"First PDF preview unexpectedly found an existing group: {preview.get('existingGroups')}")
        committed = probe.json(
            "POST",
            f"/api/projects/{project_id}/pdf/import-commit",
            json={
                "previewId": preview["previewId"],
                "selectedPages": [0, 1, 2],
                "action": "add",
                "placementMode": "full_sheet",
                "titlePrefix": "Imported Smoke",
                "firstSheetCode": "P-101",
                "insertAfterPageId": blank["id"],
            },
            timeout=PDF_TIMEOUT_SECONDS,
        )
        committed_progress = committed.get("progress") or {}
        require(
            committed_progress.get("completed") == 3
            and committed_progress.get("total") == 3
            and committed_progress.get("phase") == "complete"
            and committed_progress.get("message") == "PDF import complete",
            f"PDF import progress was not exact: {committed.get('progress')}",
        )
        page_ids = [str(value) for value in committed.get("pageIds", [])]
        require(len(page_ids) == len(set(page_ids)) == 3, f"PDF import did not create three stable unique pages: {page_ids}")
        group_id = str(committed.get("importGroupId") or "")
        require(group_id, f"PDF import returned no import group: {committed}")
        project = get_project(probe, project_id)
        group_pages = imported_pages(project, group_id)
        require(len(group_pages) == 3, f"Project contains {len(group_pages)} pages in the PDF group, expected 3.")
        require({page["id"] for page in group_pages} == set(page_ids), "PDF group IDs differ from commit response IDs.")
        require({(page.get("sourceImport") or {}).get("sourcePageIndex") for page in group_pages} == {0, 1, 2}, "PDF source page indices were not preserved.")
        project_dir = project_directory(docs_dir, project_id)
        verify_local_pdf_assets(probe, project_dir, group_pages)
        source_pdf.unlink()
        require(not source_pdf.exists(), "Generated external PDF could not be removed for independence test.")
        for page in group_pages:
            require(original_tokens[int(page["sourceImport"]["sourcePageIndex"])] != "", "Generated source token is blank.")

        by_source_index = {int(page["sourceImport"]["sourcePageIndex"]): page for page in group_pages}
        custom_order = [by_source_index[2], by_source_index[0], by_source_index[1]]
        non_pdf_pages = [page for page in project["pages"] if page.get("pageType") != "pdf"]
        for position, page in enumerate(custom_order, start=len(non_pdf_pages) + 1):
            source_index = int(page["sourceImport"]["sourcePageIndex"])
            page.update(
                {
                    "order": position,
                    "sheetCode": f"P-{source_index + 1:03d}",
                    "displaySheetCode": f"P-{source_index + 1:03d}",
                    "sheetTitle": f"Preserved PDF {source_index + 1}",
                    "sheetTab": f"Preserved PDF {source_index + 1}",
                    "include": True,
                    "publishStatus": "YES",
                    "notes": f"Preserved PDF notes {source_index + 1}",
                }
            )
        annotated_page = by_source_index[0]
        annotated_page["canvasObjects"].append(
            {
                "type": "textbox",
                "objectId": "overlay_smoke_annotation",
                "text": "SMOKE ANNOTATION PRESERVED",
                "left": 340,
                "top": 190,
                "width": 420,
                "height": 60,
                "fontSize": 24,
                "fill": "#b00020",
            }
        )
        project["pages"] = [*non_pdf_pages, *custom_order]
        project["metadata"]["drawingPackageFileName"] = "standalone_smoke_package_latest"
        saved = save_project(probe, project_id, project)
        project = get_project(probe, project_id)
        expected_sequence = [page["id"] for page in project["pages"]]
        preserved = {page["id"]: project_snapshot(page) for page in imported_pages(project, group_id)}
        require(
            any(obj.get("objectId") == "overlay_smoke_annotation" for obj in pdf_overlays(page_by_id(project, annotated_page["id"]))),
            "PDF annotation did not survive save/reload before replacement.",
        )
        persist_json(before_restart_path, project)

        revised_tokens = create_fixture_pdf(source_pdf, revision="REVISED")
        revised_upload_name = "renamed-smoke-revision.pdf"
        with source_pdf.open("rb") as handle:
            revised_preview = probe.json(
                "POST",
                f"/api/projects/{project_id}/pdf/import-preview",
                files={"file": (revised_upload_name, handle, "application/pdf")},
                timeout=PDF_TIMEOUT_SECONDS,
            )
        groups = revised_preview.get("existingGroups") or []
        matching_groups = [item for item in groups if item.get("groupId") == group_id]
        require(len(matching_groups) == 1, f"Renamed revised PDF did not offer exactly one existing group: {groups}")
        require(matching_groups[0].get("sameName") is False, f"Renamed revision was incorrectly marked as a same-filename match: {matching_groups[0]}")
        require(len(matching_groups[0].get("pageFingerprints", [])) == 3, f"Existing PDF fingerprints are missing: {matching_groups[0]}")
        require(set(matching_groups[0].get("pageIds", [])) == set(page_ids), f"Revised preview group IDs changed: {matching_groups[0]}")
        mapping = [
            {"existingPageId": page["id"], "pageIndex": int(page["sourceImport"]["sourcePageIndex"])}
            for page in imported_pages(project, group_id)
        ]
        before_page_count = len(project["pages"])
        replaced = probe.json(
            "POST",
            f"/api/projects/{project_id}/pdf/import-commit",
            json={
                "previewId": revised_preview["previewId"],
                "selectedPages": [item["pageIndex"] for item in mapping],
                "action": "replace",
                "replaceGroupId": group_id,
                "mapping": mapping,
            },
            timeout=PDF_TIMEOUT_SECONDS,
        )
        require(set(replaced.get("replacedPageIds", [])) == set(page_ids), f"Explicit replace changed target IDs: {replaced}")
        require(not replaced.get("pageIds"), f"Explicit replace silently added pages: {replaced.get('pageIds')}")
        replaced_progress = replaced.get("progress") or {}
        require(
            replaced_progress.get("completed") == 3
            and replaced_progress.get("total") == 3
            and replaced_progress.get("phase") == "complete"
            and replaced_progress.get("message") == "PDF import complete",
            f"Replace progress was not exact: {replaced.get('progress')}",
        )
        project = get_project(probe, project_id)
        require(len(project["pages"]) == before_page_count, "Revised PDF replacement changed total project page count.")
        require([page["id"] for page in project["pages"]] == expected_sequence, "Revised PDF replacement changed project page order.")
        after_group = imported_pages(project, group_id)
        require(len(after_group) == 3, "Revised PDF replacement duplicated or removed managed pages.")
        for page in after_group:
            assert_project_snapshot(page, preserved[page["id"]])
            source = page.get("sourceImport") or {}
            require(int(source.get("revision") or 0) == 2, f"Revised PDF page has wrong revision metadata: {source}")
            require(source.get("previousSha256"), f"Revised PDF page lacks prior-source compatibility metadata: {source}")
        verify_local_pdf_assets(
            probe,
            project_dir,
            after_group,
            expected_original_name=revised_upload_name,
        )
        source_pdf.unlink()
        require(not source_pdf.exists(), "Revised external PDF could not be removed.")

        stop_server(process, stream)
        process, stream = None, None
        process, stream = start_server(port=port, docs_dir=docs_dir, server_log=server_log)
        restarted_health = wait_for_server(probe, process, server_log)
        second_pid = int(restarted_health.get("pid") or 0)
        require(first_pid and second_pid and first_pid != second_pid, f"Server restart did not produce a new process: {first_pid} -> {second_pid}")
        project = get_project(probe, project_id)
        require([page["id"] for page in project["pages"]] == expected_sequence, "Server restart changed saved project page order.")
        for page in imported_pages(project, group_id):
            assert_project_snapshot(page, preserved[page["id"]])
        require(str(external_dir) not in json.dumps(project, ensure_ascii=False), "Project retained an external temporary PDF path.")
        verify_local_pdf_assets(
            probe,
            project_dir,
            imported_pages(project, group_id),
            expected_original_name=revised_upload_name,
        )
        persist_json(after_restart_path, project)

        export_response = probe.request(
            "POST",
            f"/api/projects/{project_id}/export/pdf",
            # Legacy callers may still send a partial page list or different
            # paper size. Standalone export must ignore both and regenerate the
            # complete included 17x11 drawing set from saved project state.
            json={
                "confirmPreflight": True,
                "width": 8.5,
                "height": 11,
                "pageIds": [page_ids[0]],
            },
            timeout=PDF_TIMEOUT_SECONDS,
        )
        content_disposition = export_response.headers.get("Content-Disposition", "")
        require("latest" in content_disposition.casefold(), f"Export used a stale filename: {content_disposition}")
        require("initial" not in content_disposition.casefold(), f"Export reused the old filename: {content_disposition}")
        require("no-store" in export_response.headers.get("Cache-Control", "").casefold(), f"Export response permits stale caching: {dict(export_response.headers)}")
        export_path.write_bytes(export_response.content)
        export_audit = inspect_export(export_response.content, project, revised_tokens)
        persist_json(export_audit_path, export_audit)

        stop_server(process, stream)
        process, stream = None, None
        access_requests = assert_no_forbidden_requests(probe, server_log)
        request_evidence = {
            "scriptRequests": [asdict(record) for record in probe.records],
            "serverAccessRequests": access_requests,
            "forbiddenScriptRequests": [],
            "forbiddenServerRequests": [],
        }
        persist_json(request_log_path, request_evidence)
        success = True
        return {
            "ok": True,
            "repository": str(REPO_ROOT),
            "docsDir": str(docs_dir),
            "port": port,
            "initialPid": first_pid,
            "restartedPid": second_pid,
            "projectId": project_id,
            "projectMode": project.get("projectMode"),
            "pageCount": len(project.get("pages", [])),
            "includedPageCount": len([page for page in project.get("pages", []) if page.get("include", True)]),
            "pdfImportGroupId": group_id,
            "pdfPageIds": page_ids,
            "export": export_audit,
            "requestCount": len(probe.records),
            "serverAccessRequestCount": len(access_requests),
            "forbiddenRequestCount": 0,
            "evidenceDir": str(artifacts) if evidence_dir else "",
            "evidence": {
                "serverLog": str(server_log) if evidence_dir else "",
                "requestLog": str(request_log_path) if evidence_dir else "",
                "projectBeforeRestart": str(before_restart_path) if evidence_dir else "",
                "projectAfterRestart": str(after_restart_path) if evidence_dir else "",
                "exportPdf": str(export_path) if evidence_dir else "",
                "exportAudit": str(export_audit_path) if evidence_dir else "",
            },
        }
    finally:
        stop_server(process, stream)
        if not success:
            try:
                persist_json(
                    request_log_path,
                    {
                        "scriptRequests": [asdict(record) for record in probe.records],
                        "serverAccessRequests": access_log_requests(server_log),
                    },
                )
            except OSError:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(os.environ["SINGH360_EVIDENCE_DIR"]) if os.environ.get("SINGH360_EVIDENCE_DIR") else None,
        help="Optional directory for server logs, project snapshots, request logs, and the exported PDF.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else None
    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="singh360-standalone-smoke-") as raw_workspace:
            result = run_smoke(workspace=Path(raw_workspace), evidence_dir=evidence_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"STANDALONE EDITOR SMOKE FAILED: {error_text(exc)}", file=sys.stderr)
        if evidence_dir:
            print(f"Evidence retained at: {evidence_dir}", file=sys.stderr)
            print(server_log_tail(evidence_dir / "server.log"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
