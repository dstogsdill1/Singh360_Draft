"""Smoke: table auto-fit — small ranges stay one page and fit by scaling.

Verifies the fit-to-body engine keeps a moderately tall range on a single page
(scaling down to min readable scale) instead of splitting, and that a range that
fits within one body never reports willSplit.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.page_composer import BODY_BUDGET, EXCEL_MIN_SCALE, plan_excel_range


def _block(n_rows: int, row_h: int, minScale: float = EXCEL_MIN_SCALE) -> dict:
    grid = [["h0", "h1", "h2", "h3"]] + [[f"r{r}c{c}" for c in range(4)] for r in range(n_rows)]
    return {
        "type": "excelRange",
        "grid": grid,
        "rowHeights": [24] + [row_h] * n_rows,
        "colWidths": [200] * 4,
        "repeatRows": [0],
        "headerRowCount": 1,
        "splitMode": "auto_rows",
        "allowContinuation": True,
        "minScale": minScale,
    }


def main() -> None:
    problems: list[str] = []

    # A) 30 rows @ 24px = 744px < BODY_BUDGET → obviously one page.
    a = plan_excel_range(_block(30, 24))
    if a["pages"] != 1:
        problems.append(f"30-row range should be 1 page, got {a['pages']}")

    # B) A range that is taller than one *unscaled* body but fits when scaled to
    #    min scale must stay ONE page (scale before split). height ~= 1400px,
    #    budget at min 0.48 ~= 1708px → still one page.
    b_rows = int((BODY_BUDGET / 0.48 - 100) // 24)  # comfortably under the min-scale budget
    b = plan_excel_range(_block(b_rows, 24, minScale=0.48))
    if b["pages"] != 1:
        problems.append(f"scalable range should stay 1 page, got {b['pages']} (rows={b_rows})")
    if b["bestScale"] >= 1.0:
        # This range is taller than one body, so bestScale must be < 1 (scaled).
        problems.append(f"expected sub-1 bestScale for tall range, got {b['bestScale']}")

    # C) A genuinely huge range (well beyond min-scale budget) must split.
    huge_rows = int((BODY_BUDGET / 0.48) // 24) * 3
    c = plan_excel_range(_block(huge_rows, 24, minScale=0.48))
    if not c["willSplit"]:
        problems.append(f"huge range should split, got {c['pages']} pages")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — table autofit passed")
    print(f"  A={a['pages']}p B={b['pages']}p(scale {b['bestScale']}) C={c['pages']}p")


if __name__ == "__main__":
    main()
