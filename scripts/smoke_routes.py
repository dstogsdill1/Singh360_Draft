from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


def main() -> int:
    problems: list[str] = []
    dist_index = server.FRONTEND_DIST_DIR / "index.html"
    print(f"dist index exists: {dist_index.is_file()}")
    if not dist_index.is_file():
        problems.append("frontend build output is missing")

    client = server.app.test_client()

    r_root = client.get("/")
    print(f"GET /            -> status {r_root.status_code} | Location: {r_root.headers.get('Location', '(none)')}")
    if r_root.status_code not in {301, 302, 307, 308} or not str(r_root.headers.get("Location") or "").endswith("/app"):
        problems.append("GET / does not redirect to generic /app Project Home")

    r_app = client.get("/app")
    app_text = r_app.get_data(as_text=True)
    body = app_text[:200].replace("\n", " ")
    print(f"GET /app         -> status {r_app.status_code}")
    print(f"  first 200 chars: {body}")
    if r_app.status_code != 200:
        problems.append(f"GET /app returned {r_app.status_code}")
    if "Singh360 Draft" not in app_text:
        problems.append("GET /app does not contain the Singh360 Draft browser title")

    r_health = client.get("/api/health")
    print(f"GET /api/health  -> status {r_health.status_code}")
    health = r_health.get_json() or {}
    if r_health.status_code != 200 or health.get("ok") is not True:
        problems.append("/api/health is not healthy")
    expected_health = {
        "product": "Singh360 Draft",
        "repository": str(server.HERE.resolve()),
        "configuredPort": server._SERVER_PORT,
        "pid": os.getpid(),
        "ownershipToken": os.environ.get("SINGH360_OWNERSHIP_TOKEN", "").strip(),
    }
    for field, expected in expected_health.items():
        if health.get(field) != expected:
            problems.append(
                f"/api/health {field} is {health.get(field)!r}, expected {expected!r}"
            )

    r_logo = client.get("/static/LOGO-750px.png")
    print(f"GET /static/LOGO-750px.png -> status {r_logo.status_code}")
    if r_logo.status_code != 200:
        problems.append("active Singh360 Draft logo route is broken")

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
        if not data.get("distIndexExists"):
            problems.append("debug route reports missing frontend build")
        if data.get("configuredPort") != 8766:
            problems.append(f"configured port is {data.get('configuredPort')}, expected 8766")
    else:
        problems.append("/api/debug/routes failed")

    if problems:
        print("ROUTE/HEALTH PROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK: routes, health, product title, and active logo passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
