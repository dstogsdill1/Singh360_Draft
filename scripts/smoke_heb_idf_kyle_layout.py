"""Smoke: Kyle-style H-E-B IDF widths, page pairing, and no automatic green fill."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_WIDTHS = [98, 354, 98, 86, 38, 62, 46]
EXPECTED_ONE = 782
EXPECTED_TWO = 1582


def fail(message: str) -> None:
    raise SystemExit("FAIL — " + message)


def main() -> None:
    py = (ROOT / "core" / "heb_idf_switch_matrix.py").read_text(encoding="utf-8")
    ts = (ROOT / "frontend" / "src" / "model" / "idfNetworkTable.ts").read_text(encoding="utf-8")
    renderer = (ROOT / "frontend" / "src" / "components" / "renderers" / "NetworkTwoUpRenderer.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "src" / "styles" / "sheet.css").read_text(encoding="utf-8")

    py_match = re.search(r"HEB_COL_WIDTHS\s*=\s*\[([^]]+)\]", py)
    ts_match = re.search(r"HEB_COL_WIDTHS\s*=\s*\[([^]]+)\]", ts)
    if not py_match or not ts_match:
        fail("H-E-B width constants missing")
    py_widths = [int(v.strip()) for v in py_match.group(1).split(",")]
    ts_widths = [int(v.strip()) for v in ts_match.group(1).split(",")]
    if py_widths != EXPECTED_WIDTHS or ts_widths != EXPECTED_WIDTHS:
        fail(f"wrong widths: python={py_widths}, frontend={ts_widths}")
    if sum(EXPECTED_WIDTHS) != EXPECTED_ONE or EXPECTED_ONE * 2 + 18 != EXPECTED_TWO:
        fail("internal width arithmetic is wrong")
    if "HEB_FONT_SIZE = 8.0" not in py or "HEB_FONT_SIZE = 8.0" not in ts:
        fail("H-E-B font size is not synchronized at 8.0")
    if "isHebActiveRow" in renderer or "np-idf-active-row" in renderer:
        fail("renderer still applies automatic active-row highlighting")
    if "tr.np-idf-active-row" in css or "#66bd63" in css.lower():
        fail("automatic green fill CSS still exists")
    if "np-idf-single-slot" not in renderer or "width: 782px" not in css:
        fail("single-switch pages are not locked to the same Kyle column width")
    if "S360_HEB_IDF_KYLE_LAYOUT_V4" not in css:
        fail("V4 CSS marker missing")
    print("OK — Kyle-style H-E-B IDF layout and no-auto-highlight checks passed")


if __name__ == "__main__":
    main()
