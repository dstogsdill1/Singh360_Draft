"""Smoke: PDF export rewrites ngrok/localhost asset URLs to the local Playwright origin."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.export_pdf import export_pdf_via_playwright


def main() -> int:
    problems: list[str] = []
    out = ROOT / "output" / "smoke_export_asset_rewrite.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    url = "http://127.0.0.1:8766/app?project=ce333f83502742d3&print=1&pw=17&ph=11"
    ok, detail = export_pdf_via_playwright(url, out)
    if not ok:
        problems.append(detail)
    elif not out.is_file() or out.stat().st_size < 1000:
        problems.append(f"PDF missing or too small: {out}")

    if problems:
        print("FAIL — export pdf asset rewrite")
        for p in problems:
            print(" -", p[:500])
        return 1

    print(f"OK — export pdf asset rewrite ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
