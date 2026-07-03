"""server.py — Flask backend for Singh360 Draft.

Serves the static web UI, ingests Excel workbooks, persists project state JSON,
and routes PDF export (Playwright) for 11x17 engineering document packages.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from core.excel_parser import parse_workbook

HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web"
DOCS_DIR = HERE / ".docs"
DOCS_DIR.mkdir(exist_ok=True)

PROJECT_ID_RE = re.compile(r"^[a-f0-9]{16}$")
_SERVER_PORT = 8765

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB

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

@app.get("/")
@app.get("/editor")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/health")
def health():
    return jsonify({"ok": True})


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

        project_state = parse_workbook(temp_path)
        project_state["id"] = project_id
        project_state["modified"] = _utcnow()

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
        app.logger.error("parse_workbook failed for project %s:\n%s", project_id, tb)
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
    data["modified"] = _utcnow()

    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        app.logger.error("Could not write project %s: %s", project_id, exc)
        return jsonify(_err("Failed to save project.", str(exc))), 500

    return jsonify({"ok": True, "id": project_id, "modified": data["modified"]})


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
def export_pdf(project_id: str):
    path = _project_path(project_id)
    if not path.is_file():
        abort(404)

    pdf_path = DOCS_DIR / f"{project_id}.pdf"
    url = f"http://127.0.0.1:{_SERVER_PORT}/editor?project={project_id}&print=1"

    # Executed in a subprocess to avoid async-loop conflicts with Flask's WSGI thread.
    script = f"""\
import asyncio
from playwright.async_api import async_playwright

async def run_export():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={{"width": 1632, "height": 1056}})
        await page.goto("{url}", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.pdf(
            path=r"{pdf_path}",
            width="17in",
            height="11in",
            landscape=True,
            print_background=True,
            margin={{"top": "0in", "bottom": "0in", "left": "0in", "right": "0in"}},
        )
        await browser.close()

asyncio.run(run_export())
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(HERE),
        )
        if proc.returncode != 0:
            stderr_tail = (proc.stderr or "Subprocess exited non-zero.")[-2000:]
            app.logger.error("Playwright export failed for %s:\n%s", project_id, stderr_tail)
            return jsonify(_err("PDF export failed.", stderr_tail)), 500

    except subprocess.TimeoutExpired:
        app.logger.error("Playwright export timed out for project %s", project_id)
        return jsonify(_err("PDF export timed out after 120 s.")), 504

    except OSError as exc:
        app.logger.error("Could not launch Playwright subprocess: %s", exc)
        return jsonify(_err("PDF export failed — could not start renderer.", str(exc))), 500

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{project_id}.pdf",
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Singh360 Draft  ->  http://127.0.0.1:{_SERVER_PORT}  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=_SERVER_PORT, debug=False)
