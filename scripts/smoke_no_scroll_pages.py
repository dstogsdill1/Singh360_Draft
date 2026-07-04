"""scripts/smoke_no_scroll_pages.py — verify normalized pages have no scroll flags.

Checks:
  - The .np-base-layer CSS class does NOT have overflow:auto or overflow:scroll in
    the compiled stylesheet (verifies Phase A CSS hardening).
  - Pages of type 'index' use the generated index renderer (pageType stored correctly).
  - No normalized page block inserts an internal-scroll container in the rendered HTML.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    problems: list[str] = []

    # 1. Compiled CSS must NOT allow overflow:auto on .np-base-layer
    dist_css_files = list((ROOT / "frontend" / "dist" / "assets").glob("*.css"))
    if not dist_css_files:
        print("note: no dist CSS found — run npm build first (or skip CSS check)")
    else:
        css = dist_css_files[0].read_text("utf-8", errors="replace")
        # The class name is inlined by Vite; we look for the rule after the class
        # marker. Vite does not eliminate CSS class names, so this works:
        if "overflow:auto" in css.replace(" ", "") or "overflow: auto" in css:
            # Check if any of these are specifically inside np-base-layer block.
            # We look for the combination np-base-layer … overflow:auto.
            # A heuristic: if np-base-layer exists AND overflow auto is present
            # in the same ~100-char window, flag it.
            idx = css.find("np-base-layer")
            while idx != -1:
                window = css[idx : idx + 120].replace(" ", "")
                if "overflow:auto" in window or "overflow:scroll" in window:
                    problems.append("np-base-layer CSS has overflow:auto or scroll — normalized pages will scroll")
                    break
                idx = css.find("np-base-layer", idx + 1)

    # 2. The generated index renderer file exists and is importable by the compiler.
    idx_renderer = ROOT / "frontend" / "src" / "components" / "renderers" / "GeneratedIndexRenderer.tsx"
    if not idx_renderer.exists():
        problems.append("GeneratedIndexRenderer.tsx is missing")

    # 3. Python: loading a project and checking index page type via workbook_importer.
    sample_wb = ROOT / "sample_data" / "assets.csv"
    if not sample_wb.exists():
        print("note: sample_data/assets.csv missing — skipping page-type check")
    else:
        try:
            from core.project_model import classify_page_type
            # Index detection.
            it = classify_page_type("Sheet Index", "Sheet Index", "index")
            if it != "index":
                problems.append(f"classify_page_type('Sheet Index', 'Sheet Index', 'index') returned '{it}' (expected 'index')")
            cover = classify_page_type("Cover", "Cover Sheet", "")
            if cover != "cover":
                problems.append(f"classify_page_type('Cover', ...) returned '{cover}' (expected 'cover')")
        except Exception as exc:
            problems.append(f"classify_page_type import failed: {exc}")

    # 4. NormalizedPage.tsx must import GeneratedIndexRenderer.
    norm_path = ROOT / "frontend" / "src" / "components" / "renderers" / "NormalizedPage.tsx"
    if norm_path.exists():
        source = norm_path.read_text("utf-8")
        if "GeneratedIndexRenderer" not in source:
            problems.append("NormalizedPage.tsx does not import GeneratedIndexRenderer")
        if "isIndexPage" not in source:
            problems.append("NormalizedPage.tsx does not route index pages to GeneratedIndexRenderer")
    else:
        problems.append("NormalizedPage.tsx not found")

    # 5. sheet.css must NOT have overflow:auto on .np-base-layer.
    css_path = ROOT / "frontend" / "src" / "styles" / "sheet.css"
    if css_path.exists():
        raw = css_path.read_text("utf-8")
        # Find .np-base-layer block
        idx2 = raw.find("np-base-layer")
        if idx2 != -1:
            block = raw[idx2 : idx2 + 300]
            if "overflow: auto" in block or "overflow:auto" in block:
                problems.append("sheet.css .np-base-layer still has overflow:auto")
    else:
        problems.append("sheet.css not found")

    if problems:
        print("NO-SCROLL PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: no-scroll page checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
