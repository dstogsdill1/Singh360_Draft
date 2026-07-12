
import os, json, pathlib, urllib.parse, mimetypes, webbrowser, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from component_canonical_tools import repo_root, load_library, save_components, apply_canonical_first_pass, backup_library, resolve_path, missing_required

ROOT = repo_root()
PACK_ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML_PATH = PACK_ROOT / "_s360_library_manager" / "component_library_review_board.html"
REQUIRED_PATH = PACK_ROOT / "canonical" / "required_components.json"
PORT = int(os.environ.get("S360_LIBRARY_MANAGER_PORT", "8799"))

def json_response(handler, payload, code=200):
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)

def read_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ["/", "/index.html", "/component_library_review_board.html"]:
            data = HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/library":
            state = load_library(ROOT)
            required = json.loads(REQUIRED_PATH.read_text(encoding="utf-8"))
            comps = state["components"]
            for c in comps:
                # Lightweight preview path pass-through; front-end will call /api/asset.
                pass
            payload = {
                "repoRoot": str(ROOT),
                "librarySource": state["source"],
                "componentCount": len(comps),
                "components": comps,
                "missingRequired": missing_required(ROOT, comps, required),
            }
            json_response(self, payload)
            return

        if path == "/api/asset":
            qs = urllib.parse.parse_qs(parsed.query)
            rel = qs.get("path", [""])[0]
            if not rel:
                self.send_error(404); return
            target = resolve_path(ROOT, rel)
            try:
                target = target.resolve()
                if not str(target).startswith(str(ROOT.resolve())):
                    self.send_error(403); return
                if not target.exists() or not target.is_file():
                    self.send_error(404); return
                data = target.read_bytes()
                ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_error(500, str(e))
            return

        self.send_error(404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/backup":
                b = backup_library(ROOT)
                json_response(self, {"ok": True, "backup": str(b)})
                return
            if path == "/api/apply-first-pass":
                body = read_body(self)
                dry = bool(body.get("dryRun", False))
                result = apply_canonical_first_pass(ROOT, dry_run=dry)
                json_response(self, {"ok": True, **result})
                return
            if path == "/api/save":
                body = read_body(self)
                comps = body.get("components")
                if not isinstance(comps, list):
                    json_response(self, {"ok": False, "error": "components must be an array"}, 400)
                    return
                result = save_components(ROOT, comps)
                json_response(self, {"ok": True, **result})
                return
        except Exception as e:
            json_response(self, {"ok": False, "error": str(e)}, 500)
            return
        self.send_error(404)

def main():
    print("Singh360 Component Library Manager V4")
    print("Repo root:", ROOT)
    print(f"Open: http://127.0.0.1:{PORT}")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    def open_browser():
        time.sleep(1)
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down...")

if __name__ == "__main__":
    main()
