"""Live PDF export smoke using an isolated generated project and runtime."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.export_pdf import export_pdf_via_playwright
from core.project_store import ProjectStore
from core.workbook_importer import import_workbook
from core.workbook_status_sync import file_hash, project_hash
from tests.generated_fixtures import write_workbook


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.2)
    raise RuntimeError(f"isolated test server did not become healthy on port {port}")


def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="singh360_live_pdf_export_") as raw:
        runtime = Path(raw)
        docs = runtime / ".docs"
        workbook = write_workbook(runtime / "sanitized.xlsx")
        project_id = "a0a0a0a0a0a00001"
        project = import_workbook(workbook, project_id=project_id)
        project["id"] = project_id
        project["projectDisplayName"] = "Sanitized PDF Export"
        project.setdefault("metadata", {})["projectName"] = "Sanitized PDF Export"
        project["workbookSync"] = {
            "mode": "external-workbook-link",
            "workbook": str(workbook),
            "status": "in_sync",
            "authority": "workbook",
            "workbookHash": file_hash(workbook),
            "appHash": project_hash(project),
        }
        ProjectStore(docs).save(project_id, project)

        port = _free_port()
        env = {
            **os.environ,
            "SINGH360_DOCS_DIR": str(docs),
            "SINGH360_PORT": str(port),
        }
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_for_health(port)
            out = runtime / "sanitized-export.pdf"
            url = (
                f"http://127.0.0.1:{port}/app"
                f"?project={project_id}&mode=editor&print=1&pw=17&ph=11"
            )
            ok, detail = export_pdf_via_playwright(url, out)
            if not ok:
                problems.append(detail)
            elif not out.is_file() or out.stat().st_size < 1000:
                problems.append(f"PDF missing or too small: {out}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    if problems:
        print("FAIL — isolated live PDF export")
        for p in problems:
            print(" -", p[:500])
        return 1

    print("OK — isolated generated-project PDF export passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
