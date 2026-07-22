"""server.py — Flask backend for Singh360 Draft (Drawing Package Editor).

Serves the modular /app editor build, ingests Excel workbooks, persists project
state JSON, and routes PDF export (Playwright) for 17x11 engineering document
packages.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import socket
import sys
import traceback
import uuid
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, request, send_file, send_from_directory

from core.csv_importer import build_csv_worksheet_and_pages, import_csv_to_grid
from core.export_pdf import export_pdf_via_playwright
from core.library_store import LibraryStore
from core.library_v2 import LibraryV2
from core.component_interop import (
    archive_component, restore_component, permanent_delete_component,
    publish_active_library, read_published_map, build_powerpoint_palette,
    build_powerpoint_template,
)
from core.legend_template_store import LegendTemplateStore
from core.page_template_store import PageTemplateStore
from core import pdf_import_v2
from core.symbol_mapper import SymbolMapperError, SymbolMapperStore
from core.drawing_generators import (
    generate_callout_schedule,
    generate_component_stack,
    generate_overall_layout,
)
from core.sheet_numbering import default_sheet_index
from engines.ems_sheet import render_layout_sheet, render_schedule_sheets
from core.page_composer import compose_pages, continuation_summary
from core.pdf_renderer import (
    get_page_thumbnails,
    get_page_previews,
    render_page_to_png,
    render_crop_points,
    is_available as pdf_renderer_available,
)
from core.pdf_importer import import_pdf
from core.project_model import ensure_project_shape, recalc_page_numbers
from core.sheet_index_sync import sync_project_sheet_index
from core.project_store import ProjectStore, slugify
from core.validation import validate_project
from core.vsdx_importer import import_vsdx
from core.workbook_importer import import_workbook

HERE = Path(__file__).resolve().parent
FRONTEND_DIST_DIR = HERE / "frontend" / "dist"
COMPONENT_CATALOG_DIR = HERE / "tools" / "component_catalog"
DOCS_DIR = HERE / ".docs"
DOCS_DIR.mkdir(exist_ok=True)


def _ensure_minimal_runtime_workspace(docs: Path) -> None:
    """Self-heal only the active minimal runtime structure under `.docs/.`"""
    (docs / "projects").mkdir(parents=True, exist_ok=True)
    (docs / "exports").mkdir(parents=True, exist_ok=True)
    (docs / "archive").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "components").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "symbols").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "thumbnails").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "page_templates").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "page_templates" / "thumbnails").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "legend_templates").mkdir(parents=True, exist_ok=True)
    lt_manifest = docs / "library" / "legend_templates" / "manifest.json"
    if not lt_manifest.exists():
        lt_manifest.write_text('{\n  "version": 1,\n  "templates": []\n}\n', encoding="utf-8")
    pt_manifest = docs / "library" / "page_templates" / "manifest.json"
    if not pt_manifest.exists():
        pt_manifest.write_text('{\n  "version": 1,\n  "templates": []\n}\n', encoding="utf-8")
    manifest = docs / "library" / "manifest.json"
    aliases = docs / "library" / "aliases.json"
    connectors = docs / "library" / "connector_styles.json"
    if not manifest.exists():
        manifest.write_text('{\n  "version": 2,\n  "components": []\n}\n', encoding="utf-8")
    if not aliases.exists():
        aliases.write_text('{\n  "version": 1,\n  "aliases": {}\n}\n', encoding="utf-8")
    if not connectors.exists():
        connectors.write_text('{\n  "version": 1,\n  "presets": []\n}\n', encoding="utf-8")


_ensure_minimal_runtime_workspace(DOCS_DIR)
symbol_mapper_store = SymbolMapperStore(
    DOCS_DIR / "symbol_mapper",
    default_template_path=HERE / "defaults" / "symbol_mapper_standard.json",
)

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


_NO_CACHE_PATHS = {"/", "/app", "/component-catalog", "/component-catalog/"}


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
        </div>
    </body>
</html>
"""


@app.get("/")
def root_index():
        if (FRONTEND_DIST_DIR / "index.html").is_file():
                return redirect("/app", code=302)
        return _frontend_build_instructions_html(), 503




@app.get("/app")
def app_modular_index():
    if (FRONTEND_DIST_DIR / "index.html").is_file():
        return send_from_directory(FRONTEND_DIST_DIR, "index.html")
    return _frontend_build_instructions_html(), 503


@app.get("/component-catalog")
@app.get("/component-catalog/")
def component_catalog_index():
    if (COMPONENT_CATALOG_DIR / "index.html").is_file():
        return send_from_directory(COMPONENT_CATALOG_DIR, "index.html")
    abort(404)


@app.get("/published-components")
@app.get("/published-components/")
def published_components_index():
    if (PUBLISHED_COMPONENT_DIR / "index.html").is_file():
        return send_from_directory(PUBLISHED_COMPONENT_DIR, "index.html")
    return redirect("/component-catalog", code=302)


@app.get("/published-components/<path:rel>")
def published_components_asset(rel: str):
    if not PUBLISHED_COMPONENT_DIR.is_dir():
        abort(404)
    return send_from_directory(PUBLISHED_COMPONENT_DIR, rel)

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
    # Serve the master title block from the current repository root.
    candidate = HERE / "title_block.png"
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


@app.post("/api/projects/preview-continuation")
def preview_continuation():
    """Parse an uploaded workbook WITHOUT saving and return per-sheet page counts
    so the UI can show the continuation preview before finalizing the import."""
    if "file" not in request.files:
        return jsonify(_err("No workbook file uploaded.")), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify(_err("Empty filename — please select an .xlsx or .xlsm file.")), 400
    if not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        return jsonify(_err("Only .xlsx and .xlsm workbooks are supported.")), 400

    upload_suffix = Path(upload.filename).suffix.lower()
    temp_path = DOCS_DIR / f"preview_{uuid.uuid4().hex[:16]}{upload_suffix}"
    try:
        upload.save(temp_path)
        # No assets_dir/url_prefix → embedded images are skipped (parse-only).
        project_state = import_workbook(temp_path, project_id="preview")
        summary = continuation_summary(project_state.get("pages", []))
        summary["sourceWorkbookName"] = upload.filename
        return jsonify({"ok": True, "continuation": summary})
    except Exception as exc:
        app.logger.error("Continuation preview failed: %s", exc)
        return jsonify(_err("Failed to preview workbook.", str(exc))), 500
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


@app.post("/api/projects/new")
def new_project():
    """Bootstrap a project from an uploaded Excel workbook."""
    if "file" not in request.files:
        return jsonify(_err("No workbook file uploaded.")), 400

    upload = request.files["file"]
    if not upload.filename:
        return jsonify(_err("Empty filename — please select an .xlsx or .xlsm file.")), 400

    if not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        return jsonify(_err("Only .xlsx and .xlsm workbooks are supported.")), 400

    project_id = uuid.uuid4().hex[:16]
    upload_suffix = Path(upload.filename).suffix.lower()
    temp_path = DOCS_DIR / f"temp_{project_id}{upload_suffix}"

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

        summary = continuation_summary(project_state.get("pages", []))
        app.logger.info("Project %s created with %d pages.", project_id, len(project_state.get("pages", [])))
        return jsonify({"ok": True, "id": project_id, "continuation": summary})

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
    doc = ensure_project_shape(doc)
    doc = sync_project_sheet_index(doc)
    return jsonify(doc)


@app.post("/api/projects/<project_id>")
def save_project(project_id: str):
    _safe_id(project_id)
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify(_err("Request body must be valid JSON.")), 400

    data["id"] = project_id
    data = ensure_project_shape(data)
    data = sync_project_sheet_index(data)
    problems = validate_project(data)
    if problems:
        return jsonify(_err("Project validation failed.", " | ".join(problems[:20]))), 400

    try:
        store.save(project_id, data)
    except OSError as exc:
        app.logger.error("Could not write project %s: %s", project_id, exc)
        return jsonify(_err("Failed to save project.", str(exc))), 500

    return jsonify(data)


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
        doc = sync_project_sheet_index(doc)
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
    replace_page_id = request.form.get("replacePageId") or None
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
            replace_page_id=replace_page_id,
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
        "pagesAdded": len(new_pages) if not replace_page_id else 0,
        "pageIds": [p["id"] for p in new_pages],
        "renumberSuggested": not bool(replace_page_id),
        "replacedPageId": replace_page_id if replace_page_id else None,
    })


@app.post("/api/projects/<project_id>/export/worksheet")
def export_project_worksheet(project_id: str):
    """Export one linked worksheet as a standalone .xlsx download."""
    _safe_id(project_id)
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    ws_id = str(body.get("worksheetId") or "").strip()
    page_id = str(body.get("pageId") or "").strip()
    worksheets = doc.get("worksheets") if isinstance(doc.get("worksheets"), list) else []
    ws = None
    if ws_id:
        ws = next((w for w in worksheets if isinstance(w, dict) and w.get("id") == ws_id), None)
    elif page_id:
        page = next((p for p in (doc.get("pages") or []) if isinstance(p, dict) and p.get("id") == page_id), None)
        if page:
            link = page.get("linkedWorksheetId")
            ws = next((w for w in worksheets if isinstance(w, dict) and w.get("id") == link), None)
    if not ws:
        return jsonify(_err("Worksheet not found for export.")), 404
    try:
        from core.worksheet_export import export_worksheet_xlsx
        data = export_worksheet_xlsx(ws)
    except Exception as exc:
        app.logger.error("worksheet export failed for %s: %s", project_id, exc)
        return jsonify(_err("Failed to export worksheet.", str(exc))), 500
    title = str(ws.get("name") or ws.get("sourceSheet") or "worksheet")
    safe = re.sub(r"[^\w.\- ]+", "_", title).strip() or "worksheet"
    download = f"{safe}.xlsx"
    buf = BytesIO(data)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=download,
    )


# --------------------------------------------------------------------------
# PHASE E — safe whole-workbook re-upload (preserve manual layout pages)
# --------------------------------------------------------------------------
@app.post("/api/projects/<project_id>/reimport/preview")
def preview_reimport_workbook(project_id: str):
    """Upload a workbook and return a merge plan against the CURRENT project
    (no mutation): which pages will update, which manual pages will be
    preserved by default, which are new, and which are archived."""
    _safe_id(project_id)
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    if "file" not in request.files:
        return jsonify(_err("No workbook file uploaded.")), 400
    upload = request.files["file"]
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        return jsonify(_err("Only .xlsx and .xlsm workbooks are supported.")), 400

    tmp_dir = store.sources_dir(project_id, "tmp")
    tmp_path = tmp_dir / f"reimport_preview_{uuid.uuid4().hex[:8]}_{upload.filename}"
    try:
        upload.save(tmp_path)
        from core.workbook_reimport import plan_reimport
        doc = ensure_project_shape(doc)
        plan = plan_reimport(doc, tmp_path)
    except Exception as exc:
        tb = traceback.format_exc()
        app.logger.error("reimport preview failed for %s:\n%s", project_id, tb)
        return jsonify(_err("Could not preview workbook re-upload.", str(exc))), 400
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
    return jsonify({"ok": True, "plan": plan, "filename": upload.filename})


@app.post("/api/projects/<project_id>/reimport")
def do_reimport_workbook(project_id: str):
    """Apply a Phase E safe reimport into the CURRENT project (same project
    id — never creates a new project). Manual layout pages are preserved by
    default; only page ids in ``replacePageIds`` are fully replaced.

    Form fields:
      file            — the workbook
      replacePageIds  — JSON array of existing page ids to fully replace
                        even though they are classified "manual" (optional)
    """
    _safe_id(project_id)
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    if "file" not in request.files:
        return jsonify(_err("No workbook file uploaded.")), 400
    upload = request.files["file"]
    if not (upload.filename or "").lower().endswith((".xlsx", ".xlsm")):
        return jsonify(_err("Only .xlsx and .xlsm workbooks are supported.")), 400

    import json as _json
    raw_ids = request.form.get("replacePageIds", "[]")
    try:
        replace_page_ids: list[str] = _json.loads(raw_ids)
        if not isinstance(replace_page_ids, list):
            raise ValueError("replacePageIds must be a list")
    except (ValueError, _json.JSONDecodeError) as exc:
        return jsonify(_err("Invalid replacePageIds.", str(exc))), 400

    wb_dir = store.sources_dir(project_id, "workbook")
    wb_path = wb_dir / upload.filename
    try:
        upload.save(wb_path)
        from core.workbook_reimport import apply_reimport
        doc = ensure_project_shape(doc)
        doc, summary = apply_reimport(
            doc,
            wb_path,
            replace_page_ids=replace_page_ids,
            source_filename=upload.filename,
        )
        recalc_page_numbers(doc)
        # store.save() snapshots the pre-reimport project.json into backups/
        # before overwriting, so a bad reimport is always recoverable.
        store.save(project_id, doc)
    except Exception as exc:
        tb = traceback.format_exc()
        app.logger.error("workbook reimport failed for %s:\n%s", project_id, tb)
        return jsonify(_err("Failed to re-import workbook.", str(exc))), 500

    return jsonify({"ok": True, "id": project_id, "summary": summary})


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
        # Best-effort reference screenshots (Phase C blank-page asset match).
        store.dir_for(project_id) / "assets" / "screenshots" / asset_name,
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

# --------------------------------------------------------------------------
# Component Library V2 (Milestone 4A) — clean root .docs/library/components,
# manifest.json source of truth. Endpoints are namespaced under /api/lib.
# --------------------------------------------------------------------------
lib2 = LibraryV2(DOCS_DIR)
lib2.ensure()
page_templates = PageTemplateStore(DOCS_DIR)
page_templates.ensure()
legend_templates = LegendTemplateStore(DOCS_DIR)
legend_templates.ensure()


@app.get("/api/lib")
def lib2_get():
    include_legacy = request.args.get("includeLegacy", "0") in {"1", "true", "True", "yes"}
    include_retired = request.args.get("includeRetired", "0") in {"1", "true", "True", "yes"}
    return jsonify(lib2.load(include_legacy=include_legacy, include_retired=include_retired))


@app.post("/api/lib/refresh")
def lib2_refresh():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(lib2.refresh(dry_run=bool(body.get("dryRun", False))))
    except Exception as exc:  # noqa: BLE001
        app.logger.error("lib2 refresh failed: %s", exc)
        return jsonify(_err("Refresh failed.", str(exc))), 500


@app.post("/api/lib/rebuild-thumbnails")
def lib2_rebuild_thumbnails():
    try:
        return jsonify(lib2.rebuild_thumbnails())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("lib2 rebuild thumbnails failed: %s", exc)
        return jsonify(_err("Rebuild thumbnails failed.", str(exc))), 500


@app.post("/api/lib/clean-duplicates")
def lib2_clean_duplicates():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(lib2.clean_duplicates(dry_run=bool(body.get("dryRun", True))))
    except Exception as exc:  # noqa: BLE001
        app.logger.error("lib2 clean duplicates failed: %s", exc)
        return jsonify(_err("Clean duplicates failed.", str(exc))), 500


@app.post("/api/lib/migrate-legacy")
def lib2_migrate_legacy():
    body = request.get_json(silent=True) or {}
    dry = bool(body.get("dryRun", True))
    try:
        return jsonify(lib2.migrate_legacy(
            dry_run=dry,
            rebuild_thumbnails=bool(body.get("rebuildThumbnails", True)),
            generate_symbols=bool(body.get("generateSymbols", False)),
        ))
    except Exception as exc:  # noqa: BLE001
        app.logger.error("lib2 migrate legacy failed: %s", exc)
        return jsonify(_err("Migrate legacy failed.", str(exc))), 500


@app.post("/api/lib/generate-symbols")
def lib2_generate_symbols():
    try:
        result = lib2.generate_all_symbols()
        return jsonify(result), (200 if result.get("ok") else 400)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("lib2 generate symbols failed: %s", exc)
        return jsonify(_err("Generate symbols failed.", str(exc))), 500


@app.post("/api/lib/clean-physical-duplicates")
def lib2_clean_physical_duplicates():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(lib2.clean_physical_duplicates(dry_run=bool(body.get("dryRun", True))))
    except Exception as exc:  # noqa: BLE001
        app.logger.error("lib2 clean physical duplicates failed: %s", exc)
        return jsonify(_err("Clean physical duplicates failed.", str(exc))), 500



@app.post("/api/lib/add-file")
def lib2_add_file():
    category = (request.form.get("category") or "custom").strip()
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(_err("A file is required.")), 400
    try:
        result = lib2.add_file(category, upload.filename, upload.read())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("lib2 add file failed: %s", exc)
        return jsonify(_err("Add file failed.", str(exc))), 500
    return jsonify(result)


@app.patch("/api/lib/components/<comp_id>")
def lib2_update_component(comp_id: str):
    patch = request.get_json(silent=True) or {}
    result = lib2.update_component(comp_id, patch)
    return jsonify(result), (200 if result.get("ok") else 404)


@app.post("/api/lib/components/batch")
def lib2_batch_update_components():
    body = request.get_json(silent=True) or {}
    updates = body.get("updates") or []
    reason = str(body.get("reason") or "dashboard-batch-edit")
    result = lib2.batch_update_components(updates, reason=reason)
    return jsonify(result), (200 if result.get("ok") else 400)


@app.get("/api/lib/history")
def lib2_history():
    return jsonify({"ok": True, "history": lib2.list_history()})


@app.post("/api/lib/history/<snapshot_name>/restore")
def lib2_restore_history(snapshot_name: str):
    result = lib2.restore_history(snapshot_name)
    return jsonify(result), (200 if result.get("ok") else 404)


@app.post("/api/lib/components/<comp_id>/duplicate")
def lib2_duplicate_component(comp_id: str):
    result = lib2.duplicate_component(comp_id)
    return jsonify(result), (200 if result.get("ok") else 400)


@app.post("/api/lib/components/<comp_id>/replace-asset")
def lib2_replace_asset(comp_id: str):
    target = (request.form.get("target") or "").strip().lower()
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(_err("A replacement file is required.")), 400
    result = lib2.replace_component_asset(comp_id, target, upload.filename, upload.read())
    return jsonify(result), (200 if result.get("ok") else 400)


@app.post("/api/lib/components/<comp_id>/rename-file")
def lib2_rename_file(comp_id: str):
    result = lib2.rename_file_to_display(comp_id)
    return jsonify(result), (200 if result.get("ok") else 400)


@app.post("/api/lib/components/<comp_id>/symbol")
def lib2_generate_symbol(comp_id: str):
    result = lib2.generate_symbol(comp_id)
    return jsonify(result), (200 if result.get("ok") else 400)


@app.get("/api/lib/asset/<path:rel>")
def lib2_asset(rel: str):
    target = lib2.resolve_asset(rel)
    if target is None:
        abort(404)
    return send_file(str(target))


# S360 INTEROP API
@app.post("/api/lib/components/<comp_id>/archive")
def lib2_archive_component(comp_id: str):
    result = archive_component(lib2, comp_id)
    return jsonify(result), (200 if result.get("ok") else 404)


@app.post("/api/lib/components/<comp_id>/restore")
def lib2_restore_component(comp_id: str):
    result = restore_component(lib2, comp_id)
    return jsonify(result), (200 if result.get("ok") else 404)


@app.delete("/api/lib/components/<comp_id>/permanent")
def lib2_permanent_delete_component(comp_id: str):
    result = permanent_delete_component(lib2, comp_id)
    return jsonify(result), (200 if result.get("ok") else 404)


@app.post("/api/lib/publish-active")
def lib2_publish_active():
    try:
        return jsonify(publish_active_library(lib2, HERE))
    except Exception as exc:
        app.logger.error("component publish failed: %s", exc)
        return jsonify(_err("Component publish failed.", str(exc))), 500


@app.get("/api/lib/published-map")
def lib2_published_map():
    return jsonify(read_published_map(lib2))


@app.get("/api/lib/export/powerpoint-template")
def lib2_powerpoint_template():
    out = DOCS_DIR / "exports" / "powerpoint" / "Singh360_EMS_17x11_Layout_Template.pptx"
    build_powerpoint_template(out)
    return send_file(out, as_attachment=True, download_name=out.name)


@app.get("/api/lib/export/powerpoint-palette/<variant>")
def lib2_powerpoint_palette(variant: str):
    variant = variant.lower()
    if variant not in {"real", "edge"}:
        abort(404)
    out = DOCS_DIR / "exports" / "powerpoint" / f"Singh360_Component_Library_{variant.title()}.pptx"
    build_powerpoint_palette(lib2, out, variant)
    return send_file(out, as_attachment=True, download_name=out.name)

# S360 SYMBOL MAPPER ROUTES START
@app.get("/api/symbol-mapper/template")
def symbol_mapper_get_template():
    try:
        return jsonify({"ok": True, "template": symbol_mapper_store.get_template()})
    except SymbolMapperError as exc:
        return jsonify(_err(str(exc))), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Symbol Mapper template read failed")
        return jsonify(_err("The Symbol Mapper standard could not be read.", str(exc))), 500


@app.put("/api/symbol-mapper/template")
def symbol_mapper_save_template():
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(symbol_mapper_store.save_template(body))
    except SymbolMapperError as exc:
        return jsonify(_err(str(exc))), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Symbol Mapper template save failed")
        return jsonify(_err("The Symbol Mapper standard could not be saved.", str(exc))), 500


@app.post("/api/symbol-mapper/sessions")
def symbol_mapper_create_session():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(_err("A single-page PDF is required.")), 400
    try:
        session = symbol_mapper_store.create_session(upload.filename, upload.read())
        return jsonify(session), 201
    except SymbolMapperError as exc:
        return jsonify(_err(str(exc))), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Symbol Mapper session creation failed")
        return jsonify(_err("Symbol Mapper could not read the PDF.", str(exc))), 500


@app.post("/api/symbol-mapper/sessions/<session_id>/detect")
def symbol_mapper_detect(session_id: str):
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(symbol_mapper_store.detect(session_id, body))
    except SymbolMapperError as exc:
        return jsonify(_err(str(exc))), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Symbol Mapper detection failed for %s", session_id)
        return jsonify(_err("Symbol detection failed.", str(exc))), 500


@app.post("/api/symbol-mapper/sessions/<session_id>/render")
def symbol_mapper_render(session_id: str):
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(symbol_mapper_store.render(session_id, body))
    except SymbolMapperError as exc:
        return jsonify(_err(str(exc))), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Symbol Mapper render failed for %s", session_id)
        return jsonify(_err("Reviewed symbol-map rendering failed.", str(exc))), 500


@app.get("/api/symbol-mapper/sessions/<session_id>/assets/<name>")
def symbol_mapper_asset(session_id: str, name: str):
    try:
        path = symbol_mapper_store.asset_path(session_id, name)
        # Read the completed asset and close the filesystem handle before Flask
        # starts streaming. This prevents Windows from locking final.pdf while
        # the user closes or deletes the temporary Symbol Mapper session.
        payload = path.read_bytes()
    except SymbolMapperError:
        abort(404)
    except OSError as exc:
        app.logger.error("Symbol Mapper asset read failed for %s/%s: %s", session_id, name, exc)
        abort(404)
    mime = "application/pdf" if name.lower().endswith(".pdf") else "image/png"
    return send_file(
        BytesIO(payload),
        mimetype=mime,
        as_attachment=name.lower().endswith(".pdf"),
        download_name=name,
        max_age=0,
    )


@app.delete("/api/symbol-mapper/sessions/<session_id>")
def symbol_mapper_delete_session(session_id: str):
    try:
        symbol_mapper_store.delete_session(session_id)
    except SymbolMapperError as exc:
        return jsonify(_err(str(exc))), 409
    except Exception as exc:  # noqa: BLE001
        app.logger.exception("Symbol Mapper session deletion failed for %s", session_id)
        return jsonify(_err("Symbol Mapper session could not be removed.", str(exc))), 500
    return jsonify({"ok": True})
# S360 SYMBOL MAPPER ROUTES END

# ---- PDF underlay import (Phase 6) ----
@app.post("/api/lib/pdf/info")
def lib2_pdf_info():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(_err("A PDF file is required.")), 400
    tmp_dir = DOCS_DIR / "exports" / "pdf_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{uuid.uuid4().hex}.pdf"
    tmp.write_bytes(upload.read())
    try:
        return jsonify(pdf_import_v2.get_pdf_info(tmp))
    finally:
        try:
            tmp.unlink()
        except Exception:  # noqa: BLE001
            pass


@app.post("/api/lib/pdf/import")
def lib2_pdf_import():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(_err("A PDF file is required.")), 400
    try:
        page_index = int(request.form.get("page", "0"))
        dpi = int(request.form.get("dpi", str(pdf_import_v2.DPI_STANDARD)))
    except ValueError:
        return jsonify(_err("Invalid page or dpi.")), 400
    autocrop = request.form.get("autocrop", "1") not in ("0", "false", "False")
    out_dir = DOCS_DIR / "exports" / "underlays"
    tmp_dir = DOCS_DIR / "exports" / "pdf_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{uuid.uuid4().hex}.pdf"
    tmp.write_bytes(upload.read())
    try:
        result = pdf_import_v2.import_pdf_page(tmp, page_index, out_dir, dpi=dpi, autocrop=autocrop)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("PDF import failed: %s", exc)
        return jsonify(_err("PDF import failed.", str(exc))), 500
    finally:
        try:
            tmp.unlink()
        except Exception:  # noqa: BLE001
            pass
    return jsonify(result), (200 if result.get("ok") else 400)


# ---- Data-driven generators (Phase 7) ----
@app.post("/api/lib/generate/overall-layout")
def lib2_gen_overall():
    body = request.get_json(silent=True) or {}
    graph = generate_overall_layout(body.get("assets") or [], title=body.get("title") or "EMS Controls Overall Layout")
    sheet = body.get("sheet") or "ansi_b"
    return jsonify({"ok": True, "graph": graph,
                    "svg": render_layout_sheet(graph, sheet=sheet, sheet_no=body.get("sheetNo", "EMS 1.0"))})


@app.post("/api/lib/generate/component-stack")
def lib2_gen_stack():
    body = request.get_json(silent=True) or {}
    graph = generate_component_stack(body.get("components") or [], title=body.get("title") or "Component Rack / Stack")
    sheet = body.get("sheet") or "ansi_b"
    return jsonify({"ok": True, "graph": graph,
                    "svg": render_layout_sheet(graph, sheet=sheet, sheet_no=body.get("sheetNo", ""))})


@app.post("/api/lib/generate/callout-schedule")
def lib2_gen_callout():
    body = request.get_json(silent=True) or {}
    table = generate_callout_schedule(body.get("placed") or [], title=body.get("title") or "Callout Schedule")
    sheet = body.get("sheet") or "ansi_b"
    sheets = render_schedule_sheets(table, sheet=sheet, base_sheet_no=body.get("sheetNo", ""))
    return jsonify({"ok": True, "table": table, "sheets": sheets})


# --------------------------------------------------------------------------
# Page Templates (PHASE F) — user-saved reusable layout pages
# --------------------------------------------------------------------------


@app.get("/api/lib/page-templates")
def list_page_templates():
    return jsonify({"ok": True, "templates": page_templates.list_templates()})


@app.post("/api/lib/page-templates")
def save_page_template():
    body = request.get_json(force=True, silent=True) or {}
    page = body.get("page")
    name = (body.get("name") or "").strip()
    if not isinstance(page, dict):
        return jsonify(_err("page payload is required.")), 400
    if not name:
        name = page.get("sheetTitle") or "Page Template"
    thumb_bytes = None
    data_url = body.get("thumbnailDataUrl") or ""
    if data_url:
        thumb_bytes = PageTemplateStore.decode_thumbnail_data_url(str(data_url))
    try:
        entry = page_templates.save_template(page, name, thumbnail_png=thumb_bytes)
    except Exception as exc:
        app.logger.error("save page template failed: %s", exc)
        return jsonify(_err("Failed to save page template.", str(exc))), 500
    return jsonify({"ok": True, "template": entry})


@app.get("/api/lib/page-templates/<template_id>")
def get_page_template(template_id: str):
    payload = page_templates.get_template(template_id)
    if payload is None:
        abort(404)
    return jsonify({"ok": True, "template": payload})


@app.delete("/api/lib/page-templates/<template_id>")
def delete_page_template(template_id: str):
    if not page_templates.delete_template(template_id):
        abort(404)
    return jsonify({"ok": True})


@app.post("/api/lib/page-templates/<template_id>/rename")
def rename_page_template(template_id: str):
    body = request.get_json(force=True, silent=True) or {}
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return jsonify(_err("New template name is required.")), 400
    if not page_templates.rename_template(template_id, new_name):
        abort(404)
    return jsonify({"ok": True, "name": new_name})


@app.get("/api/lib/page-templates/<template_id>/thumbnail")
def page_template_thumbnail(template_id: str):
    thumb = page_templates.thumb_dir / f"{template_id}.png"
    if not thumb.is_file():
        abort(404)
    return send_file(thumb, mimetype="image/png")


# --------------------------------------------------------------------------
# Symbol Legend Templates — editable symbol legend row presets
# --------------------------------------------------------------------------


@app.get("/api/lib/legend-templates")
def list_legend_templates():
    return jsonify({"ok": True, "templates": legend_templates.list_templates()})


@app.post("/api/lib/legend-templates")
def save_legend_template():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify(_err("Template name is required.")), 400
    rows = body.get("rows")
    if not isinstance(rows, list):
        return jsonify(_err("rows array is required.")), 400
    try:
        entry = legend_templates.save_template(
            name=name,
            category=(body.get("category") or "custom"),
            title=(body.get("title") or "Symbol Legend"),
            rows=rows,
            template_id=(body.get("id") or None),
        )
    except Exception as exc:
        app.logger.error("save legend template failed: %s", exc)
        return jsonify(_err("Failed to save legend template.", str(exc))), 500
    return jsonify({"ok": True, "template": entry})


@app.get("/api/lib/legend-templates/<template_id>")
def get_legend_template(template_id: str):
    payload = legend_templates.get_template(template_id)
    if payload is None:
        abort(404)
    return jsonify({"ok": True, "template": payload})


@app.delete("/api/lib/legend-templates/<template_id>")
def delete_legend_template(template_id: str):
    if not legend_templates.delete_template(template_id):
        abort(404)
    return jsonify({"ok": True})


@app.post("/api/lib/legend-templates/<template_id>/rename")
def rename_legend_template(template_id: str):
    body = request.get_json(force=True, silent=True) or {}
    new_name = (body.get("name") or "").strip()
    if not new_name:
        return jsonify(_err("New template name is required.")), 400
    if not legend_templates.rename_template(template_id, new_name):
        abort(404)
    return jsonify({"ok": True, "name": new_name})


@app.get("/api/lib/sheet-index")
def lib2_sheet_index():
    return jsonify({"ok": True, "sheets": default_sheet_index()})


@app.get("/api/library")
def get_library():
    return jsonify(library.load())


@app.get("/api/library/root")
def get_library_root():
    return jsonify({"ok": True, "path": library.get_master_root()})


@app.post("/api/library/root")
def set_library_root():
    body = request.get_json(silent=True) or {}
    path = str(body.get("path") or "").strip()
    if not path:
        return jsonify(_err("Path is required.")), 400
    result = library.set_master_root(path)
    if not result.get("ok"):
        return jsonify(_err(result.get("error", "Failed to set library root."))), 400
    return jsonify({"ok": True, "path": result.get("libraryRoot", path), "mode": "folder-master"})


@app.post("/api/library/refresh")
def refresh_library_from_root():
    body = request.get_json(silent=True) or {}
    dry_run = bool(body.get("dryRun", False))
    reset_clean = bool(body.get("resetClean", False))
    try:
        result = library.refresh_from_master_root(dry_run=dry_run, reset_clean=reset_clean)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Refresh library from root failed: %s", exc)
        return jsonify(_err("Refresh library failed.", str(exc))), 500
    if not result.get("ok"):
        return jsonify(_err(result.get("error", "Refresh library failed"))), 400
    return jsonify(result)


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


@app.post("/api/library/import-local-folder")
def import_local_library_folder_route():
    body = request.get_json(silent=True) or {}
    folder = str(body.get("path") or "").strip()
    if not folder:
        return jsonify(_err("Path is required.")), 400
    dry_run = bool(body.get("dryRun", False))
    reset_clean = bool(body.get("resetClean", False))
    source_name = str(body.get("sourceName") or "Local Library Folder").strip() or "Local Library Folder"
    try:
        result = library.import_local_folder(folder, dry_run=dry_run, reset_clean=reset_clean, source_name=source_name)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Local library import failed: %s", exc)
        return jsonify(_err("Local library import failed.", str(exc))), 500
    if not result.get("ok"):
        return jsonify(_err(result.get("error", "Local library import failed"))), 400
    return jsonify(result)


@app.post("/api/library/sync-names")
def sync_library_names():
    try:
        return jsonify(library.sync_names_from_files())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Sync names failed: %s", exc)
        return jsonify(_err("Sync names failed.", str(exc))), 500


@app.post("/api/library/rebuild-thumbnails")
def rebuild_library_thumbnails():
    try:
        return jsonify(library.rebuild_thumbnails())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Rebuild thumbnails failed: %s", exc)
        return jsonify(_err("Rebuild thumbnails failed.", str(exc))), 500


@app.post("/api/library/cleanup-duplicates")
def cleanup_library_duplicates():
    body = request.get_json(silent=True) or {}
    dry_run = bool(body.get("dryRun", True))
    archive_duplicates = bool(body.get("archiveDuplicates", False))
    dedupe_category = body.get("dedupeCategory")
    dedupe_all = bool(body.get("dedupeAll", True))
    try:
        result = library.cleanup_duplicates(
            dry_run=dry_run,
            archive_duplicates=archive_duplicates,
            dedupe_category=dedupe_category if isinstance(dedupe_category, str) and dedupe_category.strip() else None,
            dedupe_all=dedupe_all,
        )
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Cleanup duplicates failed: %s", exc)
        return jsonify(_err("Cleanup duplicates failed.", str(exc))), 500
    if not result.get("ok"):
        return jsonify(_err(result.get("error", "Cleanup duplicates failed"))), 400
    return jsonify(result)


@app.post("/api/library/archive-dirty")
def archive_dirty_library_assets():
    try:
        return jsonify(library.archive_dirty_extracted_assets())
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Archive dirty assets failed: %s", exc)
        return jsonify(_err("Archive dirty assets failed.", str(exc))), 500


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


@app.post("/api/library/add-file")
def add_library_file_to_root():
    if "file" not in request.files:
        return jsonify(_err("No file uploaded.")), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify(_err("Filename is required.")), 400
    ext = Path(upload.filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".pdf"}:
        return jsonify(_err("Unsupported file type.")), 400
    category = (request.form.get("category") or "custom").strip().lower()
    conflict_mode = (request.form.get("conflictMode") or "rename").strip().lower()
    root = Path(library.get_master_root())
    if not root.exists() or not root.is_dir():
        return jsonify(_err("Library root is not valid. Set Library Root first.")), 400
    cat_dir = root / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    fname = Path(upload.filename).name
    dst = cat_dir / fname
    # Duplicate prevention by hash.
    temp_name = f"temp_add_{uuid.uuid4().hex[:10]}{ext}"
    temp_path = DOCS_DIR / temp_name
    try:
        upload.save(temp_path)
        dup = library.find_existing_by_hash(temp_path)
        if dup is not None:
            temp_path.unlink(missing_ok=True)
            return jsonify({
                "ok": True,
                "duplicate": True,
                "message": f"Already exists as {dup.get('displayName')} in {dup.get('category')}",
                "component": dup,
            })
        if dst.exists():
            if conflict_mode == "skip":
                temp_path.unlink(missing_ok=True)
                return jsonify({"ok": True, "skipped": True, "message": "File exists; skipped."})
            if conflict_mode == "replace":
                shutil.copy2(temp_path, dst)
            else:
                dst = cat_dir / f"{dst.stem}_{uuid.uuid4().hex[:6]}{dst.suffix.lower()}"
                shutil.copy2(temp_path, dst)
        else:
            shutil.copy2(temp_path, dst)
        temp_path.unlink(missing_ok=True)
        result = library.refresh_from_master_root(dry_run=False, reset_clean=False)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Add file to library root failed: %s", exc)
        return jsonify(_err("Add file failed.", str(exc))), 500
    return jsonify({"ok": True, "savedTo": str(dst), "refresh": result})


@app.get("/api/library/assets/<path:rel>")
def get_library_asset(rel: str):
    target = library.asset_path(rel)
    if target is None:
        abort(404)
    return send_file(target)


@app.get("/api/library/asset/<comp_id>")
def get_library_component_asset(comp_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", comp_id):
        abort(404)
    p = library.get_component_asset_path(comp_id)
    if p is None:
        abort(404)
    return send_file(p)


@app.get("/api/library/thumbnail/<comp_id>")
def get_library_component_thumbnail(comp_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", comp_id):
        abort(404)
    p = library.get_component_thumbnail_path(comp_id)
    if p is None:
        abort(404)
    return send_file(p)


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


# --------------------------------------------------------------------------
# Insert PDF Crop — high-DPI region importer (PyMuPDF)
# --------------------------------------------------------------------------

_PDF_CROP_DPI = {300, 400, 500, 600}
_PDF_FILE_RE = re.compile(r"[A-Za-z0-9._-]{1,120}\.pdf$", re.IGNORECASE)


def _project_pdf_path(project_id: str, pdf_file: str):
    """Resolve + guard a project-relative source PDF path, or None if invalid."""
    if not pdf_file or not _PDF_FILE_RE.fullmatch(pdf_file):
        return None
    sources_dir = store.sources_dir(project_id, "pdf")
    pdf_path = (sources_dir / pdf_file).resolve()
    if sources_dir.resolve() not in pdf_path.parents:
        return None
    return pdf_path if pdf_path.is_file() else None


@app.post("/api/projects/<project_id>/pdf/upload-preview")
def pdf_upload_preview(project_id: str):
    """Upload a PDF into the project and return page dimensions (points + inches)
    plus a crop-selection preview image per page."""
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    if not pdf_renderer_available():
        return jsonify(_err("PDF rendering requires PyMuPDF. Run: python -m pip install pymupdf")), 501
    if "file" not in request.files:
        return jsonify(_err("No PDF uploaded.")), 400
    upload = request.files["file"]
    if not (upload.filename or "").lower().endswith(".pdf"):
        return jsonify(_err("Only .pdf files are supported.")), 400

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", upload.filename)[:80] or "uploaded.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    sources_dir = store.sources_dir(project_id, "pdf")
    sources_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = sources_dir / safe_name
    upload.save(pdf_path)

    try:
        previews = get_page_previews(pdf_path)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("PDF preview render failed for %s: %s", project_id, exc)
        return jsonify(_err("Could not render PDF preview.", str(exc))), 500

    return jsonify({
        "ok": True,
        "pdfFile": safe_name,
        "pageCount": len(previews),
        "pages": previews,
    })


@app.post("/api/projects/<project_id>/pdf/render-page")
def pdf_render_page(project_id: str):
    """Render a full PDF page at 300/400/600 DPI into project assets/images."""
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    if not pdf_renderer_available():
        return jsonify(_err("PDF rendering requires PyMuPDF. Run: python -m pip install pymupdf")), 501

    body = request.get_json(silent=True) or {}
    pdf_file = str(body.get("pdfFile") or "").strip()
    pdf_path = _project_pdf_path(project_id, pdf_file)
    if pdf_path is None:
        return jsonify(_err("PDF not found. Upload it first via /pdf/upload-preview.")), 404

    page_index = int(body.get("page", body.get("pageIndex", 0)))
    dpi = int(body.get("dpi", 300))
    if dpi not in _PDF_CROP_DPI:
        dpi = 300

    asset_id = uuid.uuid4().hex[:16]
    assets_dir = store.assets_images_dir(project_id)
    out_name = f"{asset_id}_pdf_p{page_index + 1}_{dpi}dpi.png"
    out_path = assets_dir / out_name
    result = render_page_to_png(pdf_path, page_index, out_path, dpi=dpi)
    if not result.get("ok"):
        return jsonify(_err("Render failed.", result.get("error", ""))), 500

    return jsonify({
        "ok": True,
        "asset": {"id": asset_id, "name": out_name, "url": f"/api/assets/{project_id}/{out_name}"},
        "meta": {
            "sourcePdf": pdf_file,
            "page": page_index,
            "dpi": dpi,
            "outputWidth": result["outputWidth"],
            "outputHeight": result["outputHeight"],
        },
    })


@app.post("/api/projects/<project_id>/pdf/render-crop")
def pdf_render_crop(project_id: str):
    """Render a crop rectangle (PDF point coordinates) at 300/400/600 DPI into
    project assets/images. Optionally trims residual white margins."""
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    if not pdf_renderer_available():
        return jsonify(_err("PDF rendering requires PyMuPDF. Run: python -m pip install pymupdf")), 501

    body = request.get_json(silent=True) or {}
    pdf_file = str(body.get("pdfFile") or "").strip()
    pdf_path = _project_pdf_path(project_id, pdf_file)
    if pdf_path is None:
        return jsonify(_err("PDF not found. Upload it first via /pdf/upload-preview.")), 404

    page_index = int(body.get("page", body.get("pageIndex", 0)))
    dpi = int(body.get("dpi", 400))
    if dpi not in _PDF_CROP_DPI:
        dpi = 400
    clip = body.get("clip") or {}
    if not isinstance(clip, dict):
        return jsonify(_err("clip must be an object with x0,y0,x1,y1 in PDF points.")), 400
    autocrop = bool(body.get("autocrop", False))

    asset_id = uuid.uuid4().hex[:16]
    assets_dir = store.assets_images_dir(project_id)
    out_name = f"{asset_id}_pdfcrop_p{page_index + 1}_{dpi}dpi.png"
    out_path = assets_dir / out_name
    try:
        result = render_crop_points(pdf_path, page_index, out_path, dpi=dpi, clip_points=clip)
    except Exception as exc:  # noqa: BLE001
        app.logger.error("PDF crop render failed for %s: %s", project_id, exc)
        return jsonify(_err("Crop render failed.", str(exc))), 500
    if not result.get("ok"):
        return jsonify(_err("Crop render failed.", result.get("error", ""))), 500

    crop_meta = {}
    if autocrop:
        try:
            crop_meta = pdf_import_v2._autocrop_png(out_path)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            crop_meta = {}
        # Re-read output dims after autocrop.
        try:
            from PIL import Image as _PILImage
            with _PILImage.open(out_path) as _im:
                result["outputWidth"], result["outputHeight"] = _im.size
        except Exception:  # noqa: BLE001
            pass

    return jsonify({
        "ok": True,
        "asset": {"id": asset_id, "name": out_name, "url": f"/api/assets/{project_id}/{out_name}"},
        "meta": {
            "sourcePdf": pdf_file,
            "page": page_index,
            "dpi": dpi,
            "cropPoints": result.get("cropPoints"),
            "cropWidthIn": result.get("cropWidthIn"),
            "cropHeightIn": result.get("cropHeightIn"),
            "autocropped": bool(crop_meta.get("cropped")),
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
    # Permanently delete every active folder for one project ID.
    # The endpoint requires ?confirm=true in addition to the UI confirmation.
    _safe_id(project_id)
    confirmed = request.args.get("confirm", "").strip().lower() in {"1", "true", "yes", "delete"}
    if not confirmed:
        return jsonify(_err("Permanent project deletion requires confirm=true.")), 400

    removed: list[str] = []
    try:
        for pdir in store.find_all_dirs(project_id):
            if not pdir.is_dir():
                continue
            shutil.rmtree(pdir)
            if pdir.exists():
                raise OSError(f"Project folder still exists after deletion: {pdir}")
            removed.append(str(pdir))

        legacy = _project_path(project_id)
        if legacy.is_file():
            legacy.unlink()
            removed.append(str(legacy))

        pdf_path = DOCS_DIR / f"{project_id}.pdf"
        if pdf_path.is_file():
            pdf_path.unlink()
            removed.append(str(pdf_path))
    except OSError as exc:
        app.logger.error("Error deleting project %s: %s", project_id, exc)
        return jsonify(_err("Failed to delete project.", str(exc))), 500

    return jsonify({"ok": True, "deleted": removed})



# --------------------------------------------------------------------------
# PDF export — 11x17 Tabloid via Playwright headless Chromium
# --------------------------------------------------------------------------

@app.get("/api/projects/<project_id>/export/warnings")
def export_warnings_preview(project_id: str):
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    from core.export_qa import compute_export_warnings

    doc = ensure_project_shape(doc)
    doc = sync_project_sheet_index(doc)
    store.save(project_id, doc)
    return jsonify({"ok": True, "warnings": compute_export_warnings(doc)})


@app.post("/api/export/pdf/<project_id>")
@app.post("/api/projects/<project_id>/export/pdf")
def export_pdf(project_id: str):
    doc = _load_doc(project_id)
    if doc is None:
        abort(404)

    doc = ensure_project_shape(doc)
    doc = sync_project_sheet_index(doc)
    store.save(project_id, doc)
    pages = [p for p in doc.get("pages", []) if p.get("include", True)]
    if not pages:
        return jsonify(_err("No included pages to export.")), 400

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


@app.get("/api/projects/<project_id>/backups")
def list_project_backups(project_id: str):
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    return jsonify({"ok": True, "id": project_id, "backups": store.list_backups(project_id)})


@app.post("/api/projects/<project_id>/restore-backup")
def restore_project_backup(project_id: str):
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        return jsonify(_err("Backup name is required.")), 400
    restored = store.restore_backup(project_id, name)
    if restored is None:
        return jsonify(_err("Backup not found or could not be restored.")), 404
    return jsonify({"ok": True, "id": project_id, "restored": name, "project": restored})


@app.get("/api/projects/<project_id>/page-snapshots")
def list_project_page_snapshots(project_id: str):
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    return jsonify({"ok": True, "id": project_id, "snapshots": store.list_page_snapshots(project_id)})


@app.post("/api/projects/<project_id>/restore-page-snapshot")
def restore_project_page_snapshot(project_id: str):
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    page_id = str(body.get("pageId") or "").strip()
    name = str(body.get("name") or "").strip()
    if not page_id or not name:
        return jsonify(_err("Page id and snapshot name are required.")), 400
    restored = store.restore_page_snapshot(project_id, page_id, name)
    if restored is None:
        return jsonify(_err("Page snapshot not found or could not be restored.")), 404
    return jsonify({"ok": True, "id": project_id, "pageId": page_id, "restored": name, "project": restored})


@app.post("/api/projects/<project_id>/page-rebuild-backup")
def save_page_rebuild_backup(project_id: str):
    """Snapshot the current page before a toolbar rebuild (project history/backups)."""
    _safe_id(project_id)
    if _load_doc(project_id) is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    page_id = str(body.get("pageId") or "").strip()
    page = body.get("page")
    if not page_id or not isinstance(page, dict):
        return jsonify(_err("Page id and page payload are required.")), 400
    name = store.save_pre_rebuild_page_snapshot(project_id, page_id, page)
    if not name:
        return jsonify(_err("Could not save page rebuild backup.")), 500
    return jsonify({"ok": True, "id": project_id, "pageId": page_id, "name": name})


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


@app.post("/api/projects/<project_id>/export/package")
def export_package(project_id: str):
    """Build a ZIP package: project.json + sources + assets + latest PDF + manifest."""
    import io
    import zipfile

    doc = _load_doc(project_id)
    if doc is None:
        abort(404)
    # Keep the generated Sheet Index current for package export even when
    # the revision value itself was not changed.
    doc = sync_project_sheet_index(ensure_project_shape(doc))
    store.save(project_id, doc)
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
