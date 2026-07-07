"""Smoke: balanced, non-orphan continuation splitting.

Verifies that when an exact range must split:
  - the split is balanced (pages within ~35% of each other), not 37/11;
  - no continuation page holds fewer than MIN_ORPHAN_DATA_ROWS rows (no RO9-RO12
    orphan tail);
  - a 48-row IDF-style range that fits at min scale stays a single page.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.page_composer import (
    BODY_BUDGET,
    MIN_ORPHAN_DATA_ROWS,
    _split_excel_range_block,
)


def _block(n_data: int, row_h: int, minScale: float, fills: dict | None = None) -> dict:
    grid = [["Point", "Type", "Address", "Notes"]] + [
        [f"RO{r}", "DO", str(r), "x"] for r in range(1, n_data + 1)
    ]
    return {
        "id": "blk",
        "type": "excelRange",
        "grid": grid,
        "rowHeights": [24] + [row_h] * n_data,
        "colWidths": [200] * 4,
        "styles": fills or {},
        "mergedCells": [],
        "repeatRows": [0],
        "headerRowCount": 1,
        "srcRows": list(range(n_data + 1)),
        "splitMode": "auto_rows",
        "allowContinuation": True,
        "minScale": minScale,
    }


def _data_counts(parts: list[dict]) -> list[int]:
    """Data rows per part = grid rows minus the repeated header rows."""
    out = []
    for p in parts:
        hdr = len(p.get("repeatRows") or [])
        out.append(len(p.get("grid") or []) - hdr)
    return out


def main() -> None:
    problems: list[str] = []

    # A) 48-row IDF-style table @ 24px = 1152px fits under min-scale budget (0.42
    #    → ~1952px) → ONE page (prefer one page if readable).
    idf = _split_excel_range_block(_block(48, 24, minScale=0.42))
    if len(idf) != 1:
        problems.append(f"48-row IDF should be one page, got {len(idf)} ({_data_counts(idf)})")

    # B) A range 3x the min-scale budget must split BALANCED (not 37/11).
    big_rows = int((BODY_BUDGET / 0.42) // 24) * 3  # ~ 3 pages worth
    parts = _split_excel_range_block(_block(big_rows, 24, minScale=0.42))
    counts = _data_counts(parts)
    if len(parts) < 2:
        problems.append(f"large range should split, got {len(parts)} ({counts})")
    else:
        if min(counts) < MIN_ORPHAN_DATA_ROWS:
            problems.append(f"orphan tail: a page has {min(counts)} rows < {MIN_ORPHAN_DATA_ROWS} ({counts})")
        spread = max(counts) - min(counts)
        avg = sum(counts) / len(counts)
        if spread > 0.4 * avg:
            problems.append(f"unbalanced split {counts} (spread {spread} > 40% of avg {avg:.0f})")

    # C) The classic orphan case: a range that greedily leaves a 4-row tail must
    #    be rebalanced so no page is a tiny tail.
    tail = _split_excel_range_block(_block(76, 24, minScale=0.48))
    tcounts = _data_counts(tail)
    if len(tail) >= 2 and min(tcounts) < MIN_ORPHAN_DATA_ROWS:
        problems.append(f"orphan tail not rebalanced: {tcounts}")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — balanced continuation passed")
    print(f"  IDF={_data_counts(idf)} big={counts} tail={tcounts}")


if __name__ == "__main__":
    main()
