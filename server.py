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
import csv
import re
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote as _urlquote

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
SA31_DIR = HERE / "output" / "SA31"
SA31_SOURCE_DIR = SA31_DIR / "source"

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


def _seed_default_documents() -> None:
    """Ensure the editor always has at least a master template and SA31 template."""
    master_path = DOCS_DIR / "master_template.json"
    if not master_path.exists():
        master = _build_blank_doc("master_template", "Master Engineering Template")
        master["scope"] = (
            "<p><b>Purpose:</b> Use this master as your baseline template for new stores/projects.</p>"
            "<ul>"
            "<li>Edit header fields (project number/title/date/status).</li>"
            "<li>Populate BOM rows.</li>"
            "<li>Use the canvas for linework, arrows, notes, and overlays.</li>"
            "</ul>"
        )
        master["notes"] = (
            "<p><b>How to use:</b></p>"
            "<ol>"
            "<li>Open this template from <i>All Docs</i>.</li>"
            "<li>Change metadata to the new site.</li>"
            "<li>Export PDF when ready.</li>"
            "</ol>"
        )
        master_path.write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")

    sa31_path = DOCS_DIR / "sa31_template.json"
    if not sa31_path.exists():
        sa31_doc = _build_sa31_template_doc()
        sa31_path.write_text(json.dumps(sa31_doc, ensure_ascii=False, indent=2), encoding="utf-8")


# Seed docs after helper builders are defined (see bottom of file).


# --------------------------------------------------------------------------
# Static GUI
# --------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/health")
def health():
    return jsonify(ok=True)


@app.get("/api/source/sa31/<path:filename>")
def download_sa31_source(filename: str):
    target = (SA31_DIR / filename).resolve()
    if SA31_DIR.resolve() not in target.parents or not target.is_file():
        abort(404)
    return send_file(target, as_attachment=False, download_name=target.name)


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
    # Serve new split-pane live editor
    live = WEB_DIR / "editor_live.html"
    if live.exists():
        return send_from_directory(WEB_DIR, "editor_live.html")
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
    req = request.get_json(silent=True) or {}
    template = (request.args.get("template") or request.form.get("template") or req.get("template") or "blank").strip().lower()
    doc_id = uuid.uuid4().hex[:16]

    if template == "sa31":
        data = _build_sa31_template_doc(doc_id=doc_id, as_working_copy=True)
    elif template == "master":
        data = _build_blank_doc(doc_id, "Master Engineering Template")
    else:
        data = _build_blank_doc(doc_id, "Untitled Engineering Document")

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


def _build_blank_doc(doc_id: str, title: str) -> dict:
    today = datetime.now().strftime("%m/%d/%Y")
    return {
        "id": doc_id,
        "title": title,
        "modified": _utcnow(),
        "meta": {
            "projectName": "",
            "projectNo": "",
            "siteAddress": "",
            "date": today,
            "preparedBy": "Singh360 Inc.",
            "status": "Preliminary",
            "sheetTitle": "",
            "sheetNumber": "",
        },
        "scope": "<p>Enter scope of work here.</p>",
        "notes": "",
        "sourceRefs": [],
        "bom": [
            {"item": "1", "desc": "", "qty": "", "unit": "EA", "make": "", "notes": ""},
        ],
        "canvas": None,
    }


def _build_sa31_template_doc(doc_id: str = "sa31_template", as_working_copy: bool = False) -> dict:
    title = "SA31 Lighting Template" if not as_working_copy else "SA31 Lighting Working Copy"
    doc = _build_blank_doc(doc_id, title)
    doc["meta"].update({
        "projectName": "H-E-B SA #31 — HEB 102",
        "projectNo": "SA-31",
        "siteAddress": "8503 NW Military Highway, San Antonio, TX 78231",
        "date": "06/11/2026",
        "sheetTitle": "LIGHT DIMMING & EMS INTEGRATION (SA31-HEB 102)",
        "preparedBy": "Singh360 Engineer Team",
        "status": "For Construction",
    })
    doc["scope"] = (
        "<p><b>1. Executive Summary &amp; Scope of Work</b></p>"
        "<p>Singh360 is delivering a comprehensive, turn-key light dimming control system solution "
        "for the SA31-HEB 102 project. The scope of work encompasses the complete engineering, hardware "
        "provisioning, and field deployment of a light dimming system integrated with a Resource Data "
        "Management (RDM) Energy Management System (EMS). Singh360 will supply fully pre-configured "
        "control panels and all essential ancillary components required to deliver a fully operational, "
        "end-to-end system.</p>"
        "<p><b>2. Logistics &amp; Equipment Delivery Protocols</b></p>"
        "<p>Prefabricated Assemblies: Singh360 will drop-ship all pre-assembled Lighting Controls Panel "
        "(LCP-x) and modular lighting components directly to the designated electrical subcontractor, "
        "Eldridge, at project commencement. No components will be delivered directly to the store job site.</p>"
        "<p><b>3. Critical Path Milestones &amp; Network Integration</b></p>"
        "<p>Immediate Milestone (Priority 1): The primary critical path objective requires the immediate "
        "mounting, power deployment, and network patching of the RDM IDF (provided by H-E-B EM) to H-E-B MDT. "
        "The RDM Data Manager is existing on-site. All network infrastructure integration and localized "
        "field terminations must be actively coordinated with H-E-B Electrical Maintenance (EM) Management.</p>"
        "<p><b>4. Control Loop Installation &amp; Programming</b></p>"
        "<p>Subcontractor Biesenbach Inc. will execute the physical installation of the localized light "
        "dimming control loop. Every lighting zone must be independently wired back to its designated "
        "dimming control module inside LCP-1. Each individual zone will be independently programmed with "
        "distinct scheduling algorithms. Upon successful deployment, a custom dynamic graphic will be "
        "deployed to the RDM Data Manager to visually illustrate real-time zone status and operational metrics.</p>"
    )

    refs: list[dict[str, str]] = []
    if SA31_SOURCE_DIR.exists():
        refs.extend([
            {"label": "SA31 assets.csv", "path": str(SA31_SOURCE_DIR / "assets.csv"), "href": "/api/source/sa31/source/assets.csv"},
            {"label": "SA31 control_matrix.csv", "path": str(SA31_SOURCE_DIR / "control_matrix.csv"), "href": "/api/source/sa31/source/control_matrix.csv"},
            {"label": "SA31 network.csv", "path": str(SA31_SOURCE_DIR / "network.csv"), "href": "/api/source/sa31/source/network.csv"},
        ])

    # Gather all available drawing images with URL-encoded paths
    all_images = _get_sa31_preview_images()
    doc["previewImages"] = all_images
    if all_images:
        doc["previewImageHref"] = all_images[0]["href"]  # backward compat
        refs.append({
            "label": "SA31 drawing preview image",
            "path": str(SA31_DIR / all_images[0]["label"]),
            "href": all_images[0]["href"],
        })

    editable_pdf = SA31_DIR / "HEB_SA31_Lighting_Editable (2).pdf"
    if editable_pdf.exists():
        refs.append({
            "label": "SA31 reference PDF",
            "path": str(editable_pdf),
            "href": "/api/source/sa31/HEB_SA31_Lighting_Editable%20(2).pdf",
        })

    bom_rows: list[dict[str, str]] = []
    assets_csv = SA31_SOURCE_DIR / "assets.csv"
    if assets_csv.exists():
        try:
            with assets_csv.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader, start=1):
                    name = (row.get("Name") or "").strip()
                    if not name:
                        continue
                    desc = (row.get("Issue-Desc") or "").strip() or (row.get("Connected/Area Served/Refrigerant/Number Of Racks") or "").strip()
                    unit = (row.get("Unit/Type") or "").strip() or "EA"
                    make = (row.get("Fixture Type/Rack Type/Suction Temp/Make") or "").strip()
                    notes = (row.get("Control Type") or "").strip()
                    bom_rows.append({
                        "item": str(i),
                        "desc": name if not desc else f"{name} — {desc}",
                        "qty": "1",
                        "unit": unit,
                        "make": make,
                        "notes": notes,
                    })
        except Exception:
            pass

    if not bom_rows:
        bom_rows = doc["bom"]

    doc["bom"] = bom_rows
    doc["sourceRefs"] = refs
    doc["notes"] = (
        "<p><b>SA31 Project Notes:</b></p>"
        "<p>Store: HEB 102, 8503 NW Military Hwy, San Antonio, TX 78231 — Located in Alon Town Market.</p>"
        "<p>Panel Hub Source: Panel HA (277V Line Voltage Feed). "
        "EMS Hardware Mapping: PR0650CD-TDB Unit ID: 601.</p>"
        "<p>Sales Floor Sq Ft: 92,657. H-E-B San Antonio 31 / 102.</p>"
        "<p>Note: All images are for illustrative purposes only and are not drawn to scale (N.T.S.).</p>"
    )
    return doc


def _pick_sa31_preview_image() -> Path | None:
    """Return the first available SA31 preview image path, or None."""
    if not SA31_DIR.exists():
        return None
    preferred_names = [
        "Lighting Control Ecosystem-1-5.png",
        "Lighting Control Ecosystem-6-10.png",
        "RDM Lighting Control.png",
    ]
    for name in preferred_names:
        p = SA31_DIR / name
        if p.exists():
            return p
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        found = sorted(SA31_DIR.glob(ext))
        if found:
            return found[0]
    return None


def _get_sa31_preview_images() -> list[dict[str, str]]:
    """Return all available SA31 drawing images as [{label, href}] with URL-encoded paths."""
    if not SA31_DIR.exists():
        return []
    preferred = [
        "Lighting Control Ecosystem-1-5.png",
        "Lighting Control Ecosystem-6-10.png",
        "RDM Lighting Control.png",
    ]
    images: list[dict[str, str]] = []
    seen: set[str] = set()
    for name in preferred:
        p = SA31_DIR / name
        if p.exists():
            rel = p.relative_to(SA31_DIR).as_posix()
            images.append({"label": p.stem, "href": f"/api/source/sa31/{_urlquote(rel, safe='/')}"})
            seen.add(name)
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for p in sorted(SA31_DIR.glob(ext)):
            if p.name not in seen:
                rel = p.relative_to(SA31_DIR).as_posix()
                images.append({"label": p.stem, "href": f"/api/source/sa31/{_urlquote(rel, safe='/')}"})
                seen.add(p.name)
    return images


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


_seed_default_documents()


if __name__ == "__main__":
    port = _SERVER_PORT
    print(f"Singh360 SmartDraw bridge -> http://localhost:{port}  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=port, debug=False)
