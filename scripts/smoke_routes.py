from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


def main() -> int:
    dist_index = server.FRONTEND_DIST_DIR / "index.html"
    print(f"dist index exists: {dist_index.is_file()}")

    client = server.app.test_client()

    r_root = client.get("/")
    print(f"GET /            -> status {r_root.status_code} | Location: {r_root.headers.get('Location', '(none)')}")

    r_app = client.get("/app")
    body = r_app.get_data(as_text=True)[:200].replace("\n", " ")
    print(f"GET /app         -> status {r_app.status_code}")
    print(f"  first 200 chars: {body}")

    r_health = client.get("/api/health")
    print(f"GET /api/health  -> status {r_health.status_code}")

    r_debug = client.get("/api/debug/routes")
    print(f"GET /api/debug/routes -> status {r_debug.status_code}")
    if r_debug.status_code == 200:
        data = r_debug.get_json()
        summary = {
            "distIndexExists": data.get("distIndexExists"),
            "configuredPort": data.get("configuredPort"),
            "pid": data.get("pid"),
            "frontendDist": data.get("frontendDist"),
            "routeCount": len(data.get("urlMap", [])),
        }
        print(f"  debug summary: {json.dumps(summary)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
