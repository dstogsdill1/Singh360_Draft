"""server.py — Flask bridge between the SmartDraw web GUI and main_generator.py.

This is the local execution bridge for the Singh360 SmartDraw Generator web UI
(web/index.html). It serves the GUI and exposes a small JSON API that runs the
existing deterministic CLI (main_generator.py) as a subprocess — reusing the
exact, validated command contract rather than re-implementing the pipeline.

Endpoints (SmartDraw Generator)
  GET  /                          -> serves web/index.html
  GET  /health                    -> {"ok": true}
  POST /api/generate              -> multipart upload, runs the pipeline,
                                     returns JSON {status, files[], zipHref, report, flags}
  GET  /api/download/<job>/<file> -> a single produced file (path-traversal safe)
  GET  /api/download/<job>.zip    -> all produced files as a ZIP (stdlib zipfile)

Endpoints (Live Document Editor)
  GET  /editor                    -> serves web/editor.html
  GET  /api/docs                  -> list all saved documents [{id, title, modified}]
  POST /api/doc/new               -> create a blank document, returns {ok, id}
  GET  /api/doc/<id>              -> load document JSON state
  POST /api/doc/<id>              -> save document JSON state
  DELETE /api/doc/<id>            -> delete a document
  POST /api/export/pdf/<id>       -> render document to PDF via Playwright (headless)

Run:  python server.py   (then open http://localhost:8765)

Only one dependency beyond the core tool: Flask (see requirements.txt). Uploads
and outputs live under .jobs/<uuid>/ which is gitignored — code-only repo.
Documents are saved under .docs/<id>.json (gitignored, never customer data in repo).
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    request,
    send_file,
    send_from_directory,
)

HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web"
JOBS_DIR = HERE / ".jobs"
JOBS_DIR.mkdir(exist_ok=True)
DOCS_DIR = HERE / ".docs"
DOCS_DIR.mkdir(exist_ok=True)

# Bounds: keep a single-user local tool predictable.
MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB total upload ceiling
RUN_TIMEOUT_SEC = 300
VALID_TARGETS = {"vson", "vsdx", "rdmxml"}
JOB_RE = re.compile(r"^[0-9a-f]{32}$")
DOC_ID_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")
NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9 _.\-]")

_SERVER_PORT = 8765  # used by the PDF export subprocess to construct the URL

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


# --------------------------------------------------------------------------
# Static GUI
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/health")
def health():
    return jsonify(ok=True)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
@app.post("/api/generate")
def generate():
    # --- validate inputs ---------------------------------------------------
    if "assets" not in request.files or not request.files["assets"].filename:
        return jsonify(status="error", error="assets.csv is required."), 400

    raw_targets = (request.form.get("targets") or "vson,vsdx").split(",")
    targets = [t.strip().lower() for t in raw_targets if t.strip().lower() in VALID_TARGETS]
    if not targets:
        return jsonify(status="error", error="Select at least one target (.vson, .vsdx, or .rdm.xml)."), 400

    project_name = (request.form.get("name") or "Singh360 Diagram").strip()
    project_name = NAME_SAFE_RE.sub("", project_name)[:80] or "Singh360 Diagram"

    # --- materialize a job sandbox ----------------------------------------
    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    in_dir = job_dir / "inputs"
    out_dir = job_dir / "output"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fixed, deterministic upload names => stable CLI arguments.
    assets_path = in_dir / "assets.csv"
    request.files["assets"].save(assets_path)

    cmd = [
        sys.executable,
        str(HERE / "main_generator.py"),
        "--assets", str(assets_path),
        "--name", project_name,
        "--out-dir", str(out_dir),
        "--targets", ",".join(targets),
    ]

    if request.files.get("control") and request.files["control"].filename:
        control_path = in_dir / "control_matrix.csv"
        request.files["control"].save(control_path)
        cmd += ["--control", str(control_path)]

    if request.files.get("network") and request.files["network"].filename:
        network_path = in_dir / "network.csv"
        request.files["network"].save(network_path)
        cmd += ["--network", str(network_path)]

    if request.files.get("pdf") and request.files["pdf"].filename:
        pdf_path = in_dir / "blueprint.pdf"
        request.files["pdf"].save(pdf_path)
        pages = (request.form.get("pages") or "1").strip() or "1"
        cmd += ["--pdf", str(pdf_path), "--pages", pages]

    # --- run the deterministic pipeline -----------------------------------
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return jsonify(
            status="error",
            error=f"Generation timed out after {RUN_TIMEOUT_SEC}s.",
        ), 504
    except Exception as exc:  # noqa: BLE001 - surface any spawn failure to the UI
        return jsonify(status="error", error="Failed to launch the pipeline.", detail=str(exc)), 500

    report = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    produced = sorted(
        p
        for p in out_dir.iterdir()
        if p.is_file() and p.name.lower().endswith((".vson", ".vsdx", ".rdm.xml"))
    )

    # main_generator exit codes: 0 = all valid, 2 = produced but a validator
    # flagged a problem, other = hard failure.
    if proc.returncode not in (0, 2) or not produced:
        detail = "\n".join(part for part in (report, stderr) if part) or "No output produced."
        return jsonify(
            status="error",
            error="The pipeline did not complete successfully.",
            detail=detail,
        ), 500

    files_payload = [
        {
            "name": p.name,
            "size": p.stat().st_size,
            "href": f"/api/download/{job_id}/{p.name}",
        }
        for p in produced
    ]

    return jsonify(
        status="warning" if proc.returncode == 2 else "ok",
        jobId=job_id,
        name=project_name,
        report=report,
        flags=_extract_flags(report),
        files=files_payload,
        zipHref=f"/api/download/{job_id}.zip",
    )


# --------------------------------------------------------------------------
# Downloads (path-traversal safe)
# --------------------------------------------------------------------------
@app.get("/api/download/<job_id>/<path:filename>")
def download_file(job_id: str, filename: str):
    out_dir = _safe_job_output(job_id)
    target = (out_dir / filename).resolve()
    # Containment check: the resolved path must stay inside the job output dir.
    if out_dir not in target.parents or not target.is_file():
        abort(404)
    return send_file(target, as_attachment=True, download_name=target.name)


@app.get("/api/download/<job_id>.zip")
def download_zip(job_id: str):
    out_dir = _safe_job_output(job_id)
    files = [p for p in out_dir.iterdir() if p.is_file()]
    if not files:
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, arcname=p.name)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{job_id}.zip",
    )


# --------------------------------------------------------------------------
# Live Document Editor
# --------------------------------------------------------------------------
@app.get("/editor")
def editor():
    return send_from_directory(WEB_DIR, "editor.html")


@app.get("/api/docs")
def list_docs():
    docs = []
    for p in sorted(DOCS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text("utf-8"))
            docs.append({
                "id": p.stem,
                "title": data.get("title", p.stem),
                "modified": data.get("modified", ""),
                "status": data.get("meta", {}).get("status", "Draft"),
                "projectNo": data.get("meta", {}).get("projectNo", ""),
            })
        except Exception:
            pass
    return jsonify(docs=docs)


@app.post("/api/doc/new")
def new_doc():
    doc_id = uuid.uuid4().hex[:16]
    today = datetime.now().strftime("%m/%d/%Y")
    data: dict = {
        "id": doc_id,
        "title": "Untitled Engineering Document",
        "modified": _utcnow(),
        "meta": {
            "projectName": "",
            "projectNo": "",
            "siteAddress": "",
            "date": today,
            "preparedBy": "Singh360 Inc.",
            "status": "Preliminary",
        },
        "scope": "<p>Enter scope of work here.</p>",
        "notes": "",
        "bom": [
            {"item": "1", "desc": "", "qty": "", "unit": "EA", "make": "", "notes": ""},
        ],
        "canvas": None,
    }
    path = DOCS_DIR / f"{doc_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(ok=True, id=doc_id)


@app.get("/api/doc/<doc_id>")
def get_doc(doc_id: str):
    path = _safe_doc_path(doc_id)
    if not path.exists():
        abort(404)
    return jsonify(json.loads(path.read_text("utf-8")))


@app.route("/api/doc/<doc_id>", methods=["POST", "PUT"])
def save_doc(doc_id: str):
    if not DOC_ID_RE.match(doc_id or ""):
        return jsonify(error="Invalid document id."), 400
    path = DOCS_DIR / f"{doc_id}.json"
    data = request.get_json(force=True, silent=True) or {}
    data["id"] = doc_id
    data["modified"] = _utcnow()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify(ok=True, id=doc_id, modified=data["modified"])


@app.delete("/api/doc/<doc_id>")
def delete_doc(doc_id: str):
    path = _safe_doc_path(doc_id)
    if path.exists():
        path.unlink()
    return jsonify(ok=True)


@app.post("/api/export/pdf/<doc_id>")
def export_pdf(doc_id: str):
    path = _safe_doc_path(doc_id)
    if not path.exists():
        abort(404)
    pdf_path = DOCS_DIR / f"{doc_id}.pdf"
    url = f"http://localhost:{_SERVER_PORT}/editor?doc={doc_id}&print=1"
    script = _PLAYWRIGHT_PDF_SCRIPT.format(url=url, out=str(pdf_path).replace("\\", "\\\\"))
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(HERE),
        )
        if proc.returncode != 0:
            return jsonify(
                error="PDF export failed. Ensure Playwright is installed: pip install playwright && playwright install chromium",
                detail=proc.stderr[-2000:] if proc.stderr else "",
            ), 500
    except FileNotFoundError:
        return jsonify(error="Python executable not found."), 500
    except subprocess.TimeoutExpired:
        return jsonify(error="PDF export timed out after 90s."), 504
    except Exception as exc:
        return jsonify(error="PDF export failed.", detail=str(exc)), 500
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{doc_id}.pdf",
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _safe_job_output(job_id: str) -> Path:
    if not JOB_RE.match(job_id or ""):
        abort(404)
    out_dir = (JOBS_DIR / job_id / "output").resolve()
    if not out_dir.is_dir() or JOBS_DIR.resolve() not in out_dir.parents:
        abort(404)
    return out_dir


def _extract_flags(report: str) -> list[str]:
    """Pull the bullet lines under the report's FLAGS: section, if present."""
    flags: list[str] = []
    capture = False
    for line in report.splitlines():
        stripped = line.strip()
        if stripped.startswith("FLAGS:"):
            capture = True
            continue
        if capture:
            if stripped.startswith("!"):
                flags.append(stripped.lstrip("! ").strip())
            elif set(stripped) <= {"-", "="} and stripped:
                break
    return flags


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_doc_path(doc_id: str) -> Path:
    if not DOC_ID_RE.match(doc_id or ""):
        abort(404)
    path = (DOCS_DIR / f"{doc_id}.json").resolve()
    if DOCS_DIR.resolve() not in path.parents:
        abort(404)
    return path


# Playwright snippet executed in a subprocess for PDF export.
# Avoids asyncio conflicts with Flask's WSGI thread.
_PLAYWRIGHT_PDF_SCRIPT = """\
import asyncio, sys
from playwright.async_api import async_playwright

async def go():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={{"width": 1200, "height": 900}})
        await page.goto("{url}", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await page.pdf(
            path=r"{out}",
            format="A3",
            landscape=True,
            print_background=True,
            margin={{"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"}},
        )
        await browser.close()

asyncio.run(go())
"""


if __name__ == "__main__":
    port = _SERVER_PORT
    print(f"Singh360 SmartDraw bridge -> http://localhost:{port}  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=port, debug=False)
