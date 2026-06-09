"""server.py — Flask bridge between the SmartDraw web GUI and main_generator.py.

This is the local execution bridge for the Singh360 SmartDraw Generator web UI
(web/index.html). It serves the GUI and exposes a small JSON API that runs the
existing deterministic CLI (main_generator.py) as a subprocess — reusing the
exact, validated command contract rather than re-implementing the pipeline.

Endpoints
  GET  /                          -> serves web/index.html
  GET  /health                    -> {"ok": true}
  POST /api/generate              -> multipart upload, runs the pipeline,
                                     returns JSON {status, files[], zipHref, report, flags}
  GET  /api/download/<job>/<file> -> a single produced file (path-traversal safe)
  GET  /api/download/<job>.zip    -> all produced files as a ZIP (stdlib zipfile)

Run:  python server.py   (then open http://localhost:8765)

Only one dependency beyond the core tool: Flask (see requirements.txt). Uploads
and outputs live under .jobs/<uuid>/ which is gitignored — code-only repo.
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
import uuid
import zipfile
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

# Bounds: keep a single-user local tool predictable.
MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB total upload ceiling
RUN_TIMEOUT_SEC = 300
VALID_TARGETS = {"vson", "vsdx", "rdmxml"}
JOB_RE = re.compile(r"^[0-9a-f]{32}$")
NAME_SAFE_RE = re.compile(r"[^A-Za-z0-9 _.\-]")

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


if __name__ == "__main__":
    port = 8765
    print(f"Singh360 SmartDraw bridge -> http://localhost:{port}  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=port, debug=False)
