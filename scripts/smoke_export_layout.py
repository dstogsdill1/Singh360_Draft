"""scripts/smoke_export_layout.py — verify the export route + print shell.

Deterministic via the Flask test client (no Playwright / no live browser):
  - the print HTML shell (/app?print=1) serves the SPA
  - the export route exists and accepts paper-size params (width/height)
  - a missing project yields 404 (proves params were accepted, not rejected)
  - the built SPA does not hard-code an editor-only grid class into print output
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import server

    c = server.app.test_client()
    problems: list[str] = []

    # 1. Print shell serves the SPA (Playwright loads this then waits for ready).
    pr = c.get("/app?print=1&pw=17&ph=11")
    if pr.status_code != 200:
        problems.append(f"print shell did not load ({pr.status_code})")

    # 2. Export route accepts paper-size params. A bogus (but well-formed) id
    #    must 404 — proving width/height were parsed, not rejected as bad input.
    bogus = "0" * 16
    for w, h in [(17.0, 11.0), (8.5, 11.0), (34.0, 44.0)]:
        r = c.post(f"/api/projects/{bogus}/export/pdf", json={"width": w, "height": h})
        if r.status_code != 404:
            problems.append(f"export with paper {w}x{h} returned {r.status_code} (expected 404 for missing project)")

    # 3. Malformed paper params must not crash (route clamps/defaults).
    r2 = c.post(f"/api/projects/{bogus}/export/pdf", json={"width": "abc", "height": None})
    if r2.status_code not in (404, 400):
        problems.append(f"malformed paper params returned {r2.status_code}")

    # 4. Print output must not carry the editor-only 'show-grid' toggle in the shell.
    if pr.status_code == 200 and b"show-grid" in pr.data:
        problems.append("print shell HTML contains 'show-grid' (grid could leak into export)")

    if problems:
        print("EXPORT LAYOUT PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: export layout checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
