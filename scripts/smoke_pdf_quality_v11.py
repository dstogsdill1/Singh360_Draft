"""Regression smoke for Singh360 PDF Quality V11."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.table_layout_profiles import (
    compact_block_for_profile,
    preferred_named_col_widths,
    preferred_row_heights,
    profile_body_font_px,
)


def main() -> int:
    guideline = {
        "grid": [
            ["GUIDELINES", "", "", "", ""],
            ["Topic", "", "", "", "Guideline"],
            ["Scope / Delivery", "", "", "", "Long guidance text that must use most of the sheet width and remain readable."],
        ],
        "styles": {f"{r}:{c}": {"borders": {"bottom": {"style": "thin"}}} for r in range(3) for c in range(5)},
        "mergedCells": [{"startRow": 0, "startCol": 0, "endRow": 0, "endCol": 4}],
        "colWidths": [250, 80, 80, 80, 250],
        "rowHeights": [30, 24, 40],
        "srcRows": [0, 1, 2],
        "headerRowCount": 1,
        "repeatRows": [0],
    }
    compact_block_for_profile(guideline, "guideline_table")
    assert len(guideline["grid"][0]) == 2
    widths = preferred_named_col_widths(guideline["grid"], "guideline_table")
    assert widths and widths[1] > widths[0] * 3
    heights = preferred_row_heights(
        guideline["grid"], widths, guideline["mergedCells"], "guideline_table", 1, font_px=14
    )
    assert max(heights) < 100

    scope = [
        ["Section", "Scope Language", "Status", "Notes"],
        ["Closeout", "A long narrative sentence that must wrap cleanly.", "", "Future note text must remain usable."],
    ]
    scope_w = preferred_named_col_widths(scope, "project_scope_table")
    assert scope_w and scope_w[1] > scope_w[0] and scope_w[3] > 130
    assert profile_body_font_px("guideline_table", 2) == 14
    assert profile_body_font_px("responsibility_matrix", 4) == 13
    assert profile_body_font_px("responsibility_matrix", 10) == 11

    app = (REPO_ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    raw = (REPO_ROOT / "frontend/src/components/renderers/RawGridRenderer.tsx").read_text(encoding="utf-8")
    table = (REPO_ROOT / "frontend/src/model/tableLayoutProfiles.ts").read_text(encoding="utf-8")
    assert "sanitizeCanvasObjectsForPage" in app
    assert "Apply & Preview" in raw
    assert "double-click to auto-fit" in raw
    assert "manualLayout" in table
    print("OK: V11 semantic compaction, readable fonts, manual layout, preview workflow, and cover cleanup are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
