"""server.py — Flask backend for Singh360 Draft (Drawing Package Editor).

Serves the modular /app editor build, ingests Excel workbooks, persists project
state JSON, and routes PDF export (Playwright) for 17x11 engineering document
packages. The legacy /editor page is retained only as a fallback.
"""
from __future__ import annotations

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

from core.csv_importer import import_csv_to_grid
from core.export_pdf import export_pdf_via_playwright
from core.pdf_importer import import_pdf
from core.project_model import ensure_project_shape
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
    """Resolve a safe on-disk path for a project JSON file."""
    _safe_id(project_id)
    path = (DOCS_DIR / f"{project_id}.json").resolve()
    # Path-traversal guard
    if DOCS_DIR.resolve() not in path.parents:
        abort(403)
    return path


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
    projects = []
    for p in sorted(DOCS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text("utf-8"))
            projects.append({
                "id":          p.stem,
                "projectName": data.get("projectName", "Untitled Project"),
                "projectNo":   data.get("projectNo", ""),
                "modified":    data.get("modified", ""),
                "status":      data.get("status", "Draft"),
                "preparedBy":  data.get("preparedBy", "Singh360 Inc."),
            })
        except (json.JSONDecodeError, OSError) as exc:
            app.logger.error("Skipping corrupt project file %s: %s", p.name, exc)
            continue
    return jsonify({"projects": projects})


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

        project_state = import_workbook(temp_path, project_id=project_id)
        project_state = ensure_project_shape(project_state)

        out_path = _project_path(project_id)
        out_path.write_text(
            json.dumps(project_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
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
    path = _project_path(project_id)
    if not path.is_file():
        abort(404)
    try:
        return jsonify(json.loads(path.read_text("utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        app.logger.error("Could not read project %s: %s", project_id, exc)
        return jsonify(_err("Project file is corrupt or unreadable.")), 500


@app.post("/api/projects/<project_id>")
def save_project(project_id: str):
    path = _project_path(project_id)
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify(_err("Request body must be valid JSON.")), 400

    data["id"] = project_id
    data = ensure_project_shape(data)
    problems = validate_project(data)
    if problems:
        return jsonify(_err("Project validation failed.", " | ".join(problems[:20]))), 400

    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        app.logger.error("Could not write project %s: %s", project_id, exc)
        return jsonify(_err("Failed to save project.", str(exc))), 500

    return jsonify({"ok": True, "id": project_id, "modified": data["modified"]})


@app.post("/api/projects/<project_id>/pages")
def upsert_pages(project_id: str):
    path = _project_path(project_id)
    if not path.is_file():
        abort(404)
    body = request.get_json(force=True, silent=True) or {}
    pages = body.get("pages")
    if not isinstance(pages, list):
        return jsonify(_err("Request body must include pages as a list.")), 400
    try:
        doc = json.loads(path.read_text("utf-8"))
        doc["pages"] = pages
        doc = ensure_project_shape(doc)
        problems = validate_project(doc)
        if problems:
            return jsonify(_err("Page update failed validation.", " | ".join(problems[:20]))), 400
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
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

    source_dir = DOCS_DIR / "sources" / project_id
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / f"{source_id}{ext}"

    try:
        upload.save(source_path)
        doc = json.loads(path.read_text("utf-8"))
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

        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        app.logger.error("Failed to add source for %s: %s", project_id, exc)
        return jsonify(_err("Failed to import source.", str(exc))), 500

    return jsonify({"ok": True, "id": project_id, "source": source_meta})


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
    path = _project_path(project_id)
    try:
        if path.is_file():
            path.unlink()
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
    path = _project_path(project_id)
    if not path.is_file():
        abort(404)

    pdf_path = DOCS_DIR / f"{project_id}.pdf"
    url = f"http://127.0.0.1:{_SERVER_PORT}/app?project={project_id}&print=1"
    ok, detail = export_pdf_via_playwright(url, pdf_path)
    if not ok:
        app.logger.error("Playwright export failed for %s: %s", project_id, detail)
        return jsonify(_err("PDF export failed.", detail)), 500

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{project_id}.pdf",
    )


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
