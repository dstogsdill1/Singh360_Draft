"""server.py — Flask backend for Singh360 Draft (Drawing Package Editor).

Serves the modular /app editor build, ingests Excel workbooks, persists project
state JSON, and routes PDF export (Playwright) for 17x11 engineering document
packages. The legacy /editor page is retained only as a fallback.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import socket
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, request, send_file, send_from_directory

from core.csv_importer import build_csv_worksheet_and_pages, import_csv_to_grid
from core.export_pdf import export_pdf_via_playwright
from core.library_store import LibraryStore
from core.page_composer import compose_pages
from core.pdf_renderer import get_page_thumbnails, render_page_to_png, is_available as pdf_renderer_available
from core.pdf_importer import import_pdf
from core.project_model import ensure_project_shape, recalc_page_numbers
from core.project_store import ProjectStore, slugify
from core.validation import validate_project
from core.vsdx_importer import import_vsdx
from core.workbook_importer import import_workbook

HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web"
FRONTEND_DIST_DIR = HERE / "frontend" / "dist"
DOCS_DIR = HERE / ".docs"
DOCS_DIR.mkdir(exist_ok=True)

PROJECT_ID_RE = re.compile(r"^[a-f0-9]{16}$")
_DEFAULT_PORT = 8765


def _configured_port() -> int:
    """Resolve the runtime port from SINGH360_PORT (default 8765)."""
    raw = os.environ.get("SINGH360_PORT", "").strip()
    if not raw:
        return _DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        return _DEFAULT_PORT
    return port if 1 <= port <= 65535 else _DEFAULT_PORT


_SERVER_PORT = _configured_port()

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB


_NO_CACHE_PATHS = {"/", "/app", "/editor"}


@app.after_request
def _apply_no_cache_headers(response: Response) -> Response:
    """Apply no-cache headers to HTML shell routes so the editor never goes stale."""
    if request.path in _NO_CACHE_PATHS:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Use Python's standard logging — app.logger is a stdlib Logger instance.
# Never call app.error(...); Flask has no such method.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_id(project_id: str) -> str:
    """Validate and return the project_id, or 404 if it looks malformed."""
    if not PROJECT_ID_RE.match(project_id):
        abort(404)
    return project_id


def _project_path(project_id: str) -> Path:
    """Resolve a safe on-disk path for a project JSON file (legacy flat layout)."""
    _safe_id(project_id)
    path = (DOCS_DIR / f"{project_id}.json").resolve()
    # Path-traversal guard
    if DOCS_DIR.resolve() not in path.parents:
        abort(403)
    return path


# Project package store (folder-per-project with legacy fallback).
store = ProjectStore(DOCS_DIR)


def _load_doc(project_id: str) -> dict | None:
    _safe_id(project_id)
    return store.load(project_id)


def _save_doc(project_id: str, data: dict) -> None:
    _safe_id(project_id)
    store.save(project_id, data)


def _err(message: str, detail: str = "") -> dict:
    """Build a consistent JSON error body as a plain dict (no kwarg conflicts)."""
    payload: dict = {"ok": False, "error": message}
    if detail:
        payload["detail"] = detail
    return payload


# --------------------------------------------------------------------------
# Static GUI
# --------------------------------------------------------------------------

def _frontend_build_instructions_html() -> str:
        return """
<!doctype html>
<html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>Singh360 Modular Editor Build Required</title>
        <style>
            body { font-family: Arial, Helvetica, sans-serif; margin: 24px; background: #f5f7fa; color: #111; }
            .box { max-width: 920px; background: #fff; border: 2px solid #111; padding: 16px; }
            h1 { margin-top: 0; }
            pre { background: #111; color: #fff; padding: 12px; overflow: auto; }
            a { color: #0b3d91; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>Modular Editor Build Required</h1>
            <p>The modular editor build was not found at <code>frontend/dist/index.html</code>.</p>
            <p>Run these commands in Windows PowerShell:</p>
            <pre>cd frontend
npm install
npm run build
cd ..
python server.py</pre>
            <p>Then open <a href="/app">/app</a>.</p>
            <p>Legacy fallback editor remains available at <a href="/editor">/editor</a>.</p>
        </div>
    </body>
</html>
"""


@app.get("/")
def root_index():
        if (FRONTEND_DIST_DIR / "index.html").is_file():
                return redirect("/app", code=302)
        return _frontend_build_instructions_html(), 503


@app.get("/editor")
def legacy_editor_index():
        return send_from_directory(WEB_DIR, "index.html")


@app.get("/app")
def app_modular_index():
    if (FRONTEND_DIST_DIR / "index.html").is_file():
        return send_from_directory(FRONTEND_DIST_DIR, "index.html")
    return _frontend_build_instructions_html(), 503


@app.get("/assets/<path:asset_path>")
def app_modular_assets(asset_path: str):
    if not FRONTEND_DIST_DIR.is_dir():
        abort(404)
    return send_from_directory(FRONTEND_DIST_DIR / "assets", asset_path)


@app.get("/health")
@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/debug/routes")
def debug_routes():
    """Report runtime paths, port, and the full Flask URL map for diagnostics."""
    dist_index = FRONTEND_DIST_DIR / "index.html"
    url_map = sorted(
        (
            {
                "rule": str(rule),
                "methods": sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"}),
                "endpoint": rule.endpoint,
            }
            for rule in app.url_map.iter_rules()
        ),
        key=lambda r: r["rule"],
    )
    return jsonify(
        {
            "here": str(HERE),
            "serverFile": str(Path(__file__).resolve()),
            "frontendDist": str(FRONTEND_DIST_DIR),
            "distIndexExists": dist_index.is_file(),
            "pid": os.getpid(),
            "pythonExecutable": sys.executable,
            "configuredPort": _SERVER_PORT,
            "urlMap": url_map,
        }
    )


@app.get("/static/title_block.png")
def serve_title_block():
    """Serve the master title block image from the project root (or web fallback)."""
    for candidate in (HERE / "title_block.png", WEB_DIR / "title_block_placeholder.png"):
        if candidate.is_file():
            return send_file(candidate)
    abort(404)


@app.get("/static/LOGO-750px.png")
def serve_firm_logo():
    """Serve the Singh360 firm logo (Box 3 of the architectural title block)."""
    path = HERE / "LOGO-750px.png"
    if not path.is_file():
        abort(404)
    return send_file(path)


# --------------------------------------------------------------------------
# Project state API
# --------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects():
    return jsonify({"projects": store.list_projects()})


@app.post("/api/workspace/reset")
def workspace_reset():
    """Archive-first local cleanup. Never deletes; moves data to .docs/_archive/.

    The component library is preserved unless the caller explicitly opts in with
    resetLibrary=true AND confirmResetLibrary=true (still archived, not deleted).
    """
    from core.workspace_reset import run_reset

    body = request.get_json(force=True, silent=True) or {}
    reset_library = bool(body.get("resetLibrary")) and bool(body.get("confirmResetLibrary"))
    if bool(body.get("resetLibrary")) and not bool(body.get("confirmResetLibrary")):
        return jsonify(_err("Library reset requires an explicit confirmation.")), 400
    try:
        plan = run_reset(
            DOCS_DIR,
            archive_projects=bool(body.get("archiveProjects", True)),
            archive_exports=bool(body.get("archiveExports", True)),
            archive_tmp=bool(body.get("archiveTmp", True)),
            archive_debug=bool(body.get("archiveTmp", True)),
            include_legacy_flat_json=bool(body.get("includeLegacyFlatJson", False)),
            reset_library=reset_library,
            dry_run=bool(body.get("dryRun", False)),
        )
    except Exception as exc:
        app.logger.error("workspace reset failed: %s", exc)
        return jsonify(_err("Workspace reset failed.", str(exc))), 500
    return jsonify({"ok": True, **plan.to_dict()})


@app.post("/api/projects/new")
def new_project():
    """Bootstrap a project from an uploaded Excel workbook."""
    if "file" not in request.files:
        return jsonify(_err("No workbook file uploaded.")), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify(_err("Empty filename — please select an .xlsx file.")), 400

    if not upload.filename.lower().endswith(".xlsx"):
        return jsonify(_err("Only .xlsx workbooks are supported.")), 400

    project_id = uuid.uuid4().hex[:16]
    temp_path = DOCS_DIR / f"temp_{project_id}.xlsx"

    try:
        upload.save(temp_path)
        app.logger.info("Parsing workbook for new project %s", project_id)

        project_state = import_workbook(temp_path, project_id=project_id, assets_dir=store.assets_excel_dir(project_id), asset_url_prefix=f"/api/assets/{project_id}")
        project_state["sourceWorkbookName"] = upload.filename
        project_state["projectDisplayName"] = project_state.get("metadata", {}).get("projectName") or Path(upload.filename).stem
        project_state = ensure_project_shape(project_state)

        # Persist under the project folder, and keep a copy of the source workbook.
        store.save(project_id, project_state)
        try:
            wb_copy = store.sources_dir(project_id, "workbook") / upload.filename
            wb_copy.write_bytes(temp_path.read_bytes())
        except OSError as exc:
            app.logger.error("Could not copy source workbook for %s: %s", project_id, exc)

        app.logger.info("Project %s created with %d pages.", project_id, len(project_state.get("pages", [])))
        return jsonify({"ok": True, "id": project_id})

    except FileNotFoundError as exc:
        app.logger.error("Workbook not found during parse: %s", exc)
        return jsonify(_err("Uploaded file could not be read.", str(exc))), 500

    except Exception as exc:
        tb = traceback.format_exc()
        app.logger.error("workbook import failed for project %s:\n%s", project_id, tb)
        return jsonify(_err("Failed to parse Excel workbook.", str(exc))), 500

    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError as exc:
            app.logger.error("Could not remove temp file %s: %s", temp_path, exc)


@app.get("/api/projects/<project_id>")
def get_project(project_id: str):
    try:
        doc = _load_doc(project_id)
    except (json.JSONDecodeError, OSError) as exc:
        app.logger.error("Could not read project %s: %s", project_id, exc)
        return jsonify(_err("Project file is corrupt or unreadable.")), 500
    if doc is None:
        abort(404)
    return jsonify(doc)


@app.post("/api/projects/<project_id>")
def save_project(project_id: str):
    _safe_id(project_id)
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify(_err("Request body must be valid JSON.")), 400

    data["id"] = project_id
    data = ensure_project_shape(data)
    problems = validate_project(data)
    if problems:
        return jsonify(_err("Project validation failed.", " | ".join(problems[:20]))), 400

    try:
        store.save(project_id, data)
    except OSError as exc:
        app.logger.error("Could not write project %s: %s", project_id, exc)
        return jsonify(_err("Failed to save project.", str(exc))), 500

    return jsonify({"ok": True, "id": project_id, "modified": data["modified"], "projectFolder": data.get("projectFolder", "")})


@app.post("/api/projects/<project_id>/pages")
def upsert_pages(project_id: str):
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    body = request.get_json(force=True, silent=True) or {}
    pages = body.get("pages")
    if not isinstance(pages, list):
        return jsonify(_err("Request body must include pages as a list.")), 400
    try:
        doc["pages"] = pages
        doc = ensure_project_shape(doc)
        problems = validate_project(doc)
        if problems:
            return jsonify(_err("Page update failed validation.", " | ".join(problems[:20]))), 400
        store.save(project_id, doc)
    except Exception as exc:
        app.logger.error("Page update failed for %s: %s", project_id, exc)
        return jsonify(_err("Failed to update pages.", str(exc))), 500
    return jsonify({"ok": True, "id": project_id, "pageCount": len(doc.get("pages", []))})


@app.post("/api/projects/<project_id>/sources")
def add_source_to_project(project_id: str):
    path = _project_path(project_id)
    if not path.is_file():
        abort(404)

    if "file" not in request.files:
        return jsonify(_err("No source file uploaded.")), 400

    upload = request.files["file"]
    source_kind = (request.form.get("type") or "").strip().lower()
    if not upload.filename:
        return jsonify(_err("Empty filename.")), 400

    source_id = uuid.uuid4().hex[:16]
    ext = Path(upload.filename).suffix.lower()
    if not source_kind:
        source_kind = {
            ".xlsx": "workbook",
            ".csv": "csv",
            ".pdf": "pdf",
            ".vsdx": "vsdx",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".webp": "image",
        }.get(ext, "asset")

    source_dir = store.sources_dir(project_id, source_kind if source_kind in {"workbook", "csv", "pdf", "vsdx"} else "csv")
    source_path = source_dir / f"{source_id}{ext}"

    try:
        upload.save(source_path)
        doc = _load_doc(project_id)
        if doc is None:
            abort(404)
        doc = ensure_project_shape(doc)

        source_meta: dict = {
            "id": source_id,
            "type": source_kind,
            "name": upload.filename,
            "path": str(source_path),
            "importedAt": _utcnow(),
        }

        if source_kind == "csv":
            grid = import_csv_to_grid(source_path)
            ws_id = f"ws_{len(doc['worksheets']) + 1}"
            doc["worksheets"].append(
                {
                    "id": ws_id,
                    "name": upload.filename,
                    "sourceId": source_id,
                    "visible": True,
                    "classHint": "data-grid",
                    "grid": grid,
                    "formulas": {},
                    "styles": {},
                    "mergedCells": [],
                    "rowHeights": {},
                    "columnWidths": {},
                    "provenance": {"sheet": upload.filename},
                }
            )
        elif source_kind == "pdf":
            source_meta.update(import_pdf(source_path))
        elif source_kind == "vsdx":
            source_meta.update(import_vsdx(source_path))

        doc["sources"].append(source_meta)
        doc = ensure_project_shape(doc)

        problems = validate_project(doc)
        if problems:
            return jsonify(_err("Source import failed validation.", " | ".join(problems[:20]))), 400

        store.save(project_id, doc)
    except Exception as exc:
        app.logger.error("Failed to add source for %s: %s", project_id, exc)
        return jsonify(_err("Failed to import source.", str(exc))), 500

    return jsonify({"ok": True, "id": project_id, "source": source_meta})


@app.post("/api/projects/<project_id>/import/csv")
def attach_csv_structured(project_id: str):
    """Attach a CSV as a structured source: raw worksheet + Equipment Summary
    and per-category inventory output pages."""
    if _load_doc(project_id) is None:
        abort(404)
    if "file" not in request.files:
        return jsonify(_err("No CSV uploaded.")), 400

    upload = request.files["file"]
    if not (upload.filename or "").lower().endswith(".csv"):
        return jsonify(_err("Only .csv is supported for this endpoint.")), 400

    source_id = uuid.uuid4().hex[:16]
    csv_path = store.sources_dir(project_id, "csv") / f"{source_id}.csv"

    try:
        upload.save(csv_path)
        doc = _load_doc(project_id)
        doc = ensure_project_shape(doc)

        ws_id = f"ws_csv_{source_id}"
        worksheet, new_pages = build_csv_worksheet_and_pages(
            csv_path, ws_id, source_id, upload.filename, len(doc.get("pages", [])) + 1
        )
        # Paginate any oversized CSV tables.
        new_pages = compose_pages(new_pages)

        doc["worksheets"].append(worksheet)
        doc["sources"].append(
            {
                "id": source_id,
                "type": "csv",
                "name": upload.filename,
                "path": str(csv_path),
                "importedAt": _utcnow(),
            }
        )
        doc["pages"].extend(new_pages)
        doc = ensure_project_shape(doc)
        recalc_page_numbers(doc)

        problems = validate_project(doc)
        if problems:
            return jsonify(_err("CSV import failed validation.", " | ".join(problems[:20]))), 400

        store.save(project_id, doc)
    except Exception as exc:
        app.logger.error("CSV structured import failed for %s: %s", project_id, exc)
        return jsonify(_err("Failed to import CSV.", str(exc))), 500

    return jsonify({"ok": True, "id": project_id, "worksheetId": ws_id, "pagesAdded": len(new_pages)})


@app.post("/api/projects/<project_id>/import/workbook-sheet/preview")
def preview_import_workbook_sheet(project_id: str):
    """Upload a workbook and return sheet names + row/col counts (no project mutation)."""
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    if "file" not in request.files:
        return jsonify(_err("No workbook file uploaded.")), 400
    upload = request.files["file"]
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm", ".xls")):
        return jsonify(_err("Only .xlsx/.xlsm/.xls workbooks are supported.")), 400

    # Store temporarily in project tmp (auto-expires on next cleanup).
    tmp_dir = store.sources_dir(project_id, "tmp")
    tmp_path = tmp_dir / f"preview_{uuid.uuid4().hex[:8]}_{upload.filename}"
    try:
        upload.save(tmp_path)
        from core.sheet_importer import preview_workbook_sheets
        sheets = preview_workbook_sheets(tmp_path)
    except Exception as exc:
        return jsonify(_err("Could not read workbook.", str(exc))), 400
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
    return jsonify({"ok": True, "sheets": sheets, "filename": upload.filename})


@app.post("/api/projects/<project_id>/import/workbook-sheet")
def do_import_workbook_sheet(project_id: str):
    """Import selected worksheet(s) from an uploaded XLSX into the project.

    Form fields:
      file          — the workbook
      sheetNames    — JSON array of sheet name strings
      insertAfterPageId — page id to insert after (optional; default: append)
      templateOverride  — page template hint (optional)
    """
    _safe_id(project_id)
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    if "file" not in request.files:
        return jsonify(_err("No workbook file uploaded.")), 400
    upload = request.files["file"]
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm", ".xls")):
        return jsonify(_err("Only .xlsx/.xlsm/.xls workbooks are supported.")), 400

    import json as _json
    raw_names = request.form.get("sheetNames", "[]")
    try:
        sheet_names: list[str] = _json.loads(raw_names)
        if not isinstance(sheet_names, list) or not sheet_names:
            raise ValueError("sheetNames must be a non-empty list")
    except (ValueError, _json.JSONDecodeError) as exc:
        return jsonify(_err("Invalid sheetNames.", str(exc))), 400

    insert_after_id = request.form.get("insertAfterPageId") or None
    template_override = request.form.get("templateOverride") or None

    # Save the workbook permanently to the project sources directory.
    wb_dir = store.sources_dir(project_id, "workbook")
    wb_path = wb_dir / upload.filename
    try:
        upload.save(wb_path)
        from core.sheet_importer import import_workbook_sheets
        doc = ensure_project_shape(doc)
        doc, new_pages = import_workbook_sheets(
            doc,
            wb_path,
            sheet_names,
            insert_after_page_id=insert_after_id,
            template_override=template_override,
            assets_dir=store.assets_excel_dir(project_id, doc),
            asset_url_prefix=f"/api/assets/{project_id}",
            source_filename=upload.filename,
        )
        recalc_page_numbers(doc)
        store.save(project_id, doc)
    except Exception as exc:
        tb = traceback.format_exc()
        app.logger.error("workbook-sheet import failed for %s:\n%s", project_id, tb)
        return jsonify(_err("Failed to import worksheet(s).", str(exc))), 500

    return jsonify({
        "ok": True,
        "id": project_id,
        "pagesAdded": len(new_pages),
        "pageIds": [p["id"] for p in new_pages],
        "renumberSuggested": True,
    })


# --------------------------------------------------------------------------
# Image assets (pasted screenshots / dropped image files)
# --------------------------------------------------------------------------

_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}


@app.post("/api/projects/<project_id>/assets")
def add_asset(project_id: str):
    """Store an image asset for a project. Accepts either a multipart 'file' or
    a JSON body {"dataUrl": "data:image/png;base64,...", "name": "..."}.
    Returns the asset id + URL to reference from a canvas image object.
    """
    _safe_id(project_id)
    doc = _load_doc(project_id)
    assets_dir = store.assets_images_dir(project_id, doc or {})
    asset_id = uuid.uuid4().hex[:16]

    try:
        if "file" in request.files:
            upload = request.files["file"]
            ext = Path(upload.filename or "").suffix.lower().lstrip(".") or "png"
            if ext not in _IMAGE_EXTS:
                return jsonify(_err("Unsupported image type.", ext)), 400
            name = upload.filename or f"{asset_id}.{ext}"
            asset_path = assets_dir / f"{asset_id}.{ext}"
            upload.save(asset_path)
        else:
            body = request.get_json(force=True, silent=True) or {}
            data_url = body.get("dataUrl", "")
            name = body.get("name") or f"{asset_id}.png"
            m = re.match(r"^data:image/(png|jpe?g|webp|gif);base64,(.+)$", data_url, re.IGNORECASE)
            if not m:
                return jsonify(_err("Invalid image dataUrl.")), 400
            ext = m.group(1).lower().replace("jpeg", "jpg")
            raw = base64.b64decode(m.group(2))
            asset_path = assets_dir / f"{asset_id}.{ext}"
            asset_path.write_bytes(raw)
    except Exception as exc:
        app.logger.error("Asset store failed for %s: %s", project_id, exc)
        return jsonify(_err("Failed to store asset.", str(exc))), 500

    return jsonify(
        {
            "ok": True,
            "asset": {
                "id": asset_id,
                "name": name,
                "url": f"/api/assets/{project_id}/{asset_path.name}",
            },
        }
    )


@app.get("/api/assets/<project_id>/<asset_name>")
def get_asset(project_id: str, asset_name: str):
    _safe_id(project_id)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}\.(png|jpg|jpeg|webp|gif)", asset_name):
        abort(404)
    candidates = [
        store.assets_images_dir(project_id) / asset_name,
        store.assets_excel_dir(project_id) / asset_name,
        DOCS_DIR / "assets" / project_id / asset_name,  # legacy
    ]
    for cand in candidates:
        resolved = cand.resolve()
        if resolved.is_file() and DOCS_DIR.resolve() in resolved.parents:
            return send_file(resolved)
    abort(404)


# --------------------------------------------------------------------------
# Component Library (local .docs/library, seeded from the seed folder)
# --------------------------------------------------------------------------
library = LibraryStore(DOCS_DIR, HERE)


@app.get("/api/library")
def get_library():
    return jsonify(library.load())


@app.post("/api/library/import-seed")
def import_library_seed():
    try:
        result = library.import_seed()
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Library seed import failed: %s", exc)
        return jsonify(_err("Failed to import seed library.", str(exc))), 500
    return jsonify(result if result.get("ok") else _err(result.get("error", "Seed import failed"))), (200 if result.get("ok") else 400)


@app.post("/api/library/auto-categorize")
def auto_categorize_library():
    try:
        return jsonify(library.auto_categorize())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Auto-categorize failed: %s", exc)
        return jsonify(_err("Auto-categorize failed.", str(exc))), 500


@app.post("/api/library/rescan-inbox")
def rescan_library_inbox():
    try:
        return jsonify(library.rescan_inbox())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Inbox rescan failed: %s", exc)
        return jsonify(_err("Inbox rescan failed.", str(exc))), 500


@app.post("/api/library/rescan-library")
def rescan_library_assets():
    try:
        return jsonify(library.rescan_library_assets())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Library rescan failed: %s", exc)
        return jsonify(_err("Library rescan failed.", str(exc))), 500


@app.post("/api/library/import-rdm-folder")
def import_rdm_library_folder():
    """Import official RDM Layout Editor image folder into local .docs library."""
    body = request.get_json(silent=True) or {}
    folder = str(body.get("path") or "").strip()
    if not folder:
        return jsonify(_err("Path is required.")), 400
    dry_run = bool(body.get("dryRun", False))
    source_name = str(body.get("sourceName") or "RDM Layout Editor 3").strip() or "RDM Layout Editor 3"
    no_auto = bool(body.get("noAutoApprove", False))
    reset_rdm = bool(body.get("resetRdmImport", False))
    try:
        result = library.import_rdm_folder(
            folder,
            dry_run=dry_run,
            source_name=source_name,
            auto_approve=not no_auto,
            reset_rdm_import=reset_rdm,
        )
    except Exception as exc:  # noqa: BLE001
        app.logger.error("RDM folder import failed: %s", exc)
        return jsonify(_err("RDM folder import failed.", str(exc))), 500
    if not result.get("ok"):
        return jsonify(_err(result.get("error", "RDM import failed"))), 400
    return jsonify(result)


@app.post("/api/library/components/bulk")
def bulk_update_library_components():
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or []
    patch = body.get("patch") or {}
    if not isinstance(ids, list) or not isinstance(patch, dict):
        return jsonify(_err("ids(list) and patch(object) are required.")), 400
    ids = [x for x in ids if isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,80}", x)]
    try:
        return jsonify(library.bulk_update(ids, patch))
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Bulk library update failed: %s", exc)
        return jsonify(_err("Bulk library update failed.", str(exc))), 500


@app.post("/api/library/add-component")
def add_library_component():
    if "file" not in request.files:
        return jsonify(_err("No file uploaded.")), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify(_err("Filename is required.")), 400
    ext = Path(upload.filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}:
        return jsonify(_err("Unsupported image type.")), 400
    temp_name = f"temp_{uuid.uuid4().hex[:16]}{ext}"
    temp_path = DOCS_DIR / temp_name
    try:
        upload.save(temp_path)
        display_name = (request.form.get("displayName") or "").strip() or Path(upload.filename).stem
        category = (request.form.get("category") or "review").strip()
        part_number = (request.form.get("partNumber") or "").strip()
        approve = (request.form.get("approve") or "").strip().lower() in {"1", "true", "yes", "on"}
        result = library.add_component_upload(
            temp_path,
            display_name=display_name,
            category=category,
            part_number=part_number,
            approve=approve,
        )
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Add component failed: %s", exc)
        return jsonify(_err("Failed to add component.", str(exc))), 500
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return jsonify(result)


@app.get("/api/library/assets/<path:rel>")
def get_library_asset(rel: str):
    target = library.asset_path(rel)
    if target is None:
        abort(404)
    return send_file(target)


@app.post("/api/library/components/<comp_id>/retire")
def retire_library_component(comp_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", comp_id):
        abort(404)
    if not library.retire_component(comp_id):
        return jsonify(_err("Component not found.")), 404
    return jsonify({"ok": True, "id": comp_id, "status": "retired"})


@app.post("/api/library/components/<comp_id>/restore")
def restore_library_component(comp_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", comp_id):
        abort(404)
    if not library.restore_component(comp_id):
        return jsonify(_err("Component not found.")), 404
    return jsonify({"ok": True, "id": comp_id, "status": "approved"})


@app.patch("/api/library/components/<comp_id>")
def patch_library_component(comp_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", comp_id):
        abort(404)
    patch = request.get_json(silent=True) or {}
    if not isinstance(patch, dict):
        return jsonify(_err("Body must be a JSON object.")), 400
    updated = library.update_component(comp_id, patch)
    if updated is None:
        return jsonify(_err("Component not found.")), 404
    return jsonify({"ok": True, "component": updated})


@app.delete("/api/library/components/<comp_id>")
def delete_library_component(comp_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", comp_id):
        abort(404)
    # Safe delete: require an explicit confirm flag.
    confirm = request.args.get("confirm") == "1" or (request.get_json(silent=True) or {}).get("confirm") is True
    if not confirm:
        return jsonify(_err("Deletion requires confirm=1.", "This removes the library entry (assets on disk are kept).")), 400
    usage = library.find_usage(DOCS_DIR, comp_id)
    if usage:
        return jsonify(_err("Component is used in existing projects.", f"Retire it instead. Usages: {usage}")), 409
    if not library.delete_component(comp_id):
        return jsonify(_err("Component not found.")), 404
    return jsonify({"ok": True, "id": comp_id, "deleted": True})


@app.post("/api/import/workbook")
def import_workbook_route():
    return new_project()


@app.post("/api/import/csv")
def import_csv_route():
    if "file" not in request.files:
        return jsonify(_err("No CSV uploaded.")), 400
    upload = request.files["file"]
    if not upload.filename.lower().endswith(".csv"):
        return jsonify(_err("Only .csv is supported for this endpoint.")), 400
    temp_id = uuid.uuid4().hex[:16]
    temp_path = DOCS_DIR / f"temp_{temp_id}.csv"
    try:
        upload.save(temp_path)
        grid = import_csv_to_grid(temp_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return jsonify({"ok": True, "name": upload.filename, "grid": grid})


@app.post("/api/import/pdf")
def import_pdf_route():
    if "file" not in request.files:
        return jsonify(_err("No PDF uploaded.")), 400
    upload = request.files["file"]
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify(_err("Only .pdf is supported for this endpoint.")), 400
    temp_id = uuid.uuid4().hex[:16]
    temp_path = DOCS_DIR / f"temp_{temp_id}.pdf"
    try:
        upload.save(temp_path)
        meta = import_pdf(temp_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return jsonify({"ok": True, "source": meta})


# --------------------------------------------------------------------------
# PDF Page renderer (PyMuPDF backend — high-DPI per-page render + thumbnails)
# --------------------------------------------------------------------------

@app.post("/api/projects/<project_id>/pdf-thumbnails")
def pdf_page_thumbnails(project_id: str):
    """Upload a PDF and return base64 thumbnail images for each page so the
    user can choose which page(s) to insert."""
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    if not pdf_renderer_available():
        return jsonify(_err("PDF rendering not available.", "Install PyMuPDF (pip install pymupdf).")), 501
    if "file" not in request.files:
        return jsonify(_err("No PDF uploaded.")), 400
    upload = request.files["file"]
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify(_err("Only .pdf files are supported.")), 400

    # Save PDF as a project source asset so we can render it later.
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", upload.filename)[:80] or "uploaded.pdf"
    sources_dir = store.sources_dir(project_id, "pdf")
    sources_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = sources_dir / safe_name
    upload.save(pdf_path)

    thumbs = get_page_thumbnails(pdf_path)
    return jsonify({
        "ok": True,
        "pdfFile": safe_name,
        "pdfPath": f"sources/{safe_name}",
        "pageCount": len(thumbs),
        "pages": thumbs,
    })


@app.post("/api/projects/<project_id>/render-pdf-page")
def render_pdf_page_route(project_id: str):
    """Render a previously-uploaded PDF page to a high-resolution PNG and store
    it as a project asset.  Returns the asset URL and metadata."""
    _safe_id(project_id)
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    if not pdf_renderer_available():
        return jsonify(_err("PDF rendering not available.", "Install PyMuPDF (pip install pymupdf).")), 501

    body = request.get_json(silent=True) or {}
    pdf_file = str(body.get("pdfFile") or "").strip()
    if not pdf_file or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", pdf_file):
        return jsonify(_err("pdfFile is required and must be a safe filename.")), 400

    page_index = int(body.get("pageIndex", 0))
    quality = str(body.get("quality") or "high").lower()
    dpi_map = {"standard": 150, "high": 200, "print": 300, "crisp": 300}
    dpi = dpi_map.get(quality, 200)
    crop = body.get("crop")  # optional {"x": 0, "y": 0, "w": 1, "h": 1}

    sources_dir = store.sources_dir(project_id, "pdf")
    pdf_path = (sources_dir / pdf_file).resolve()
    # Path-traversal guard.
    if sources_dir.resolve() not in pdf_path.parents and pdf_path != sources_dir.resolve():
        abort(403)
    if not pdf_path.is_file():
        return jsonify(_err(f"PDF not found: {pdf_file}. Upload it first via /api/projects/<id>/pdf-thumbnails.")), 404

    asset_id = uuid.uuid4().hex[:16]
    assets_dir = store.assets_images_dir(project_id)
    assets_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"{asset_id}_pdf_p{page_index}.png"
    out_path = assets_dir / out_name

    result = render_page_to_png(pdf_path, page_index, out_path, dpi=dpi, crop=crop)
    if not result.get("ok"):
        return jsonify(_err("Render failed.", result.get("error", ""))), 500

    asset_url = f"/api/assets/{project_id}/{out_name}"
    return jsonify({
        "ok": True,
        "asset": {
            "id": asset_id,
            "name": out_name,
            "url": asset_url,
        },
        "meta": {
            "sourcePdf": pdf_file,
            "pageIndex": page_index,
            "quality": quality,
            "renderDpi": result["renderDpi"],
            "pageWidth": result["pageWidth"],
            "pageHeight": result["pageHeight"],
            "outputWidth": result["outputWidth"],
            "outputHeight": result["outputHeight"],
        },
    })


@app.post("/api/import/vsdx")
def import_vsdx_route():
    if "file" not in request.files:
        return jsonify(_err("No VSDX uploaded.")), 400
    upload = request.files["file"]
    if not upload.filename.lower().endswith(".vsdx"):
        return jsonify(_err("Only .vsdx is supported for this endpoint.")), 400
    temp_id = uuid.uuid4().hex[:16]
    temp_path = DOCS_DIR / f"temp_{temp_id}.vsdx"
    try:
        upload.save(temp_path)
        meta = import_vsdx(temp_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return jsonify({"ok": True, "source": meta})


@app.delete("/api/projects/<project_id>")
def delete_project(project_id: str):
    _safe_id(project_id)
    try:
        pdir = store.find_dir(project_id)
        if pdir and pdir.is_dir():
            import shutil
            shutil.rmtree(pdir, ignore_errors=True)
        legacy = _project_path(project_id)
        if legacy.is_file():
            legacy.unlink()
        pdf_path = DOCS_DIR / f"{project_id}.pdf"
        if pdf_path.is_file():
            pdf_path.unlink()
    except OSError as exc:
        app.logger.error("Error deleting project %s: %s", project_id, exc)
        return jsonify(_err("Failed to delete project.", str(exc))), 500

    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# PDF export — 11x17 Tabloid via Playwright headless Chromium
# --------------------------------------------------------------------------

@app.post("/api/export/pdf/<project_id>")
@app.post("/api/projects/<project_id>/export/pdf")
def export_pdf(project_id: str):
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)

    body = request.get_json(silent=True) or {}
    try:
        width_in = float(body.get("width", 17.0))
        height_in = float(body.get("height", 11.0))
    except (TypeError, ValueError):
        width_in, height_in = 17.0, 11.0
    # Clamp to sane paper bounds (inches).
    width_in = max(3.0, min(60.0, width_in))
    height_in = max(3.0, min(60.0, height_in))

    pdf_path = store.exports_pdf_dir(project_id, doc) / f"{project_id}.pdf"
    url = f"http://127.0.0.1:{_SERVER_PORT}/app?project={project_id}&print=1&pw={width_in}&ph={height_in}"
    ok, detail = export_pdf_via_playwright(url, pdf_path, width_in=width_in, height_in=height_in)
    if not ok:
        app.logger.error("Playwright export failed for %s: %s", project_id, detail)
        return jsonify(_err("PDF export failed.", detail)), 500

    download = f"{(doc.get('projectDisplayName') or project_id)}.pdf"
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download,
    )


@app.post("/api/projects/<project_id>/rename")
def rename_project(project_id: str):
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    body = request.get_json(force=True, silent=True) or {}
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return jsonify(_err("New project name is required.")), 400
    try:
        store.rename(project_id, new_name)
        doc = _load_doc(project_id)
    except Exception as exc:
        app.logger.error("Rename failed for %s: %s", project_id, exc)
        return jsonify(_err("Failed to rename project.", str(exc))), 500
    return jsonify({"ok": True, "id": project_id, "projectFolder": doc.get("projectFolder", ""), "projectDisplayName": doc.get("projectDisplayName", "")})


@app.get("/api/projects/<project_id>/duplicate-folders")
def duplicate_folders(project_id: str):
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    dups = store.detect_duplicate_folders(project_id)
    canonical = store.find_dir(project_id)
    return jsonify({
        "ok": True,
        "id": project_id,
        "canonicalFolder": str(canonical) if canonical else "",
        "duplicateFolders": dups,
    })


@app.post("/api/projects/<project_id>/archive-duplicate-folders")
def archive_duplicate_folders(project_id: str):
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    try:
        moved = store.archive_duplicate_folders(project_id)
    except Exception as exc:
        app.logger.error("Archive dup folders failed for %s: %s", project_id, exc)
        return jsonify(_err("Failed to archive duplicate folders.", str(exc))), 500
    return jsonify({"ok": True, "id": project_id, "archived": moved})


@app.post("/api/projects/<project_id>/archive")
def archive_project(project_id: str):
    """Archive (not delete) the whole project folder to .docs/_archive/<ts>/projects/."""
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_root = DOCS_DIR / "_archive" / ts / "projects"
    archive_root.mkdir(parents=True, exist_ok=True)
    project_dir = store.find_dir(project_id)
    if not project_dir:
        return jsonify(_err("Project folder not found.")), 404
    dest = archive_root / project_dir.name
    try:
        import shutil
        shutil.move(str(project_dir), str(dest))
    except Exception as exc:
        app.logger.error("archive_project failed for %s: %s", project_id, exc)
        return jsonify(_err("Failed to archive project.", str(exc))), 500
    return jsonify({"ok": True, "id": project_id, "archivedTo": str(dest)})
def export_package(project_id: str):
    """Build a ZIP package: project.json + sources + assets + latest PDF + manifest."""
    import io
    import zipfile

    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    pdir = store.dir_for(project_id, doc)
    store.ensure_folders(pdir)

    included = [p for p in doc.get("pages", []) if p.get("include", True)]
    source_names = [s.get("name", "") for s in doc.get("sources", [])]
    manifest = {
        "projectId": project_id,
        "projectName": doc.get("projectDisplayName") or doc.get("metadata", {}).get("projectName", ""),
        "created": doc.get("metadata", {}).get("createdDate", ""),
        "modified": doc.get("modified", ""),
        "pageCount": len(doc.get("pages", [])),
        "includedPageCount": len(included),
        "sourceFiles": source_names,
        "assetCount": len(doc.get("assets", [])),
        "generatedAt": _utcnow(),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(doc, ensure_ascii=False, indent=2))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for folder in ("sources", "assets", "exports"):
            base = pdir / folder
            if not base.is_dir():
                continue
            for f in base.rglob("*"):
                if f.is_file():
                    zf.write(f, arcname=str(f.relative_to(pdir)))
    buf.seek(0)

    download = f"{store._display_name(doc, project_id)}_package.zip"
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=download)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _print_startup_banner() -> None:
    dist_index = FRONTEND_DIST_DIR / "index.html"
    print("=" * 68)
    print("  Singh360 Draft — Drawing Package Editor")
    print("=" * 68)
    print(f"  Singh360 Draft URL : http://127.0.0.1:{_SERVER_PORT}/app")
    print(f"  Legacy fallback    : http://127.0.0.1:{_SERVER_PORT}/editor")
    print(f"  PID                : {os.getpid()}")
    print(f"  Working directory  : {Path.cwd()}")
    print(f"  server.py path     : {Path(__file__).resolve()}")
    print(f"  FRONTEND_DIST_DIR  : {FRONTEND_DIST_DIR}")
    print(f"  dist index exists  : {dist_index.is_file()}")
    print("  URL map:")
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
        methods = ",".join(sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"}))
        print(f"    {str(rule):45s} [{methods}]")
    print("=" * 68)


if __name__ == "__main__":
    if _port_in_use("127.0.0.1", _SERVER_PORT):
        print(f"Port {_SERVER_PORT} is already in use.")
        print("Inspect the listener with this PowerShell command:")
        print(f"  Get-NetTCPConnection -LocalPort {_SERVER_PORT} -State Listen")
        print("Start on an alternate port instead:")
        print("  $env:SINGH360_PORT=8766")
        print("  python server.py")
        sys.exit(1)

    _print_startup_banner()
    app.run(host="127.0.0.1", port=_SERVER_PORT, debug=False)
