"""Smoke: export one worksheet to xlsx bytes."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.worksheet_export import export_worksheet_xlsx


def main() -> int:
    ws = {
        "id": "ws_smoke",
        "name": "Guidelines",
        "grid": [
            ["Section", "Text"],
            ["A", "Short"],
            ["B", "A much longer guideline paragraph for wrap testing"],
        ],
        "styles": {
            "A1": {"bold": True, "fill": "#FFFF00"},
            "B3": {"wrap": True, "hAlign": "left"},
        },
        "mergedCells": [{"startRow": 0, "startCol": 0, "endRow": 0, "endCol": 1}],
        "colWidthsPx": [120, 200],
        "rowHeightsPx": [22, 22, 40],
    }
    data = export_worksheet_xlsx(ws)
    if not data or data[:2] != b"PK":
        print("FAIL — export did not produce xlsx zip bytes")
        return 1
    tmp = Path(tempfile.mkdtemp()) / "guidelines.xlsx"
    tmp.write_bytes(data)
    if tmp.stat().st_size < 1000:
        print("FAIL — xlsx too small")
        return 1
    print(f"OK — worksheet export ({tmp.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
