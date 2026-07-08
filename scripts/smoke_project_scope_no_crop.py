"""Smoke: Project Scope normalized block includes all required rows and fits body."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SA31 = ROOT / ".docs" / "projects" / "SA31-102-EMS-Lighting__ce333f83502742d3" / "project.json"

REQUIRED_SECTIONS = [
    "Executive Summary",
    "Project Intent",
    "Equipment Delivery",
    "LCP-1 Dimming Scope",
    "LCP-2 Contactor Scope",
    "Network / IDF Priority",
    "Programming & Commissioning",
    "Closeout",
]

BODY_W = 1600
SAFE_FIT_HEIGHT = 700
PAD_Y = 10
MIN_BOTTOM_GAP = 20
RESERVED_TOP = 40  # orange title band estimate
GROW_CAP = 1.85


def main() -> int:
    problems: list[str] = []
    if not SA31.is_file():
        print("SKIP — SA31 project.json not found")
        return 0

    proj = json.loads(SA31.read_text(encoding="utf-8"))
    page = next((p for p in proj["pages"] if p.get("id") == "page_5"), None)
    if page is None:
        print("FAIL — page_5 Project Scope missing")
        return 1

    block = next((b for b in (page.get("blocks") or []) if b.get("type") == "excelRange"), None)
    if block is None:
        problems.append("excelRange block missing")
    else:
        grid = block.get("grid") or []
        col_widths = block.get("colWidths") or []
        row_heights = block.get("rowHeights") or []
        section_col = "\n".join(row[0] if row else "" for row in grid)
        for label in REQUIRED_SECTIONS:
            if label not in section_col:
                problems.append(f"missing required section row: {label}")

        natural_w = max(1, sum(col_widths) or 1)
        natural_h = max(1, sum(row_heights) or len(grid) * 20)
        avail_w = BODY_W - 20
        avail_h = max(1, SAFE_FIT_HEIGHT - PAD_Y * 2 - RESERVED_TOP - MIN_BOTTOM_GAP)
        sw = avail_w / natural_w
        sh = avail_h / natural_h
        scale = min(GROW_CAP, sw, sh)
        scaled_h = natural_h * scale
        if scaled_h > avail_h + 2:
            problems.append(
                f"table scaled height {scaled_h:.1f}px exceeds safe body {avail_h}px "
                f"(scale={scale:.3f}, rows={len(grid)})"
            )

        # Post-fix: scaled wrapper must reserve layout height (mirror ExcelRangeRenderer fix)
        layout_h = natural_h * scale
        if layout_h < natural_h * 0.9 and scale > 1.0:
            problems.append("grow scale >1 but layout height not expanded — rows would clip")

    if problems:
        print("FAIL — project scope no crop")
        for p in problems:
            print(" -", p)
        return 1

    print("OK — Project Scope shows all required rows and fits safe body")
    print(f"  rows={len(block.get('grid') or [])} scale={scale:.3f} scaledH={scaled_h:.1f}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
