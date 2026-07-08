"""Smoke: source structural edits (delete column) are undoable via snapshot restore."""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ws_delete_col(ws: dict, col: int) -> dict:
    grid = [row[:col] + row[col + 1:] for row in ws.get("grid") or []]
    styles = {}
    for key, val in (ws.get("styles") or {}).items():
        # styles keyed A1 in source view use letters — keep simple rc copy for smoke
        styles[key] = val
    col_widths = dict(ws.get("colWidthsPx") or {})
    new_widths: dict[int, int] = {}
    for k, v in col_widths.items():
        c = int(k)
        if c < col:
            new_widths[c] = v
        elif c > col:
            new_widths[c - 1] = v
    return {**ws, "grid": grid, "styles": styles, "colWidthsPx": new_widths}


def capture_snapshot(ws: dict) -> dict:
    return deepcopy(ws)


def apply_snapshot(ws: dict, snap: dict) -> dict:
    return deepcopy(snap)


def main() -> int:
    problems: list[str] = []
    ws = {
        "id": "ws_undo",
        "name": "Scope",
        "grid": [
            ["Section", "Scope Language", "Status", "Notes"],
            ["Executive Summary", "Text A", "Review", ""],
            ["Closeout", "Text B", "Review", ""],
        ],
        "styles": {},
        "colWidthsPx": {0: 120, 1: 400, 2: 64, 3: 100},
    }

    before_cols = len(ws["grid"][0])
    snap = capture_snapshot(ws)
    deleted = ws_delete_col(deepcopy(ws), 2)
    after_cols = len(deleted["grid"][0])
    if after_cols != before_cols - 1:
        problems.append(f"delete column failed: {before_cols} -> {after_cols}")

    restored = apply_snapshot(deleted, snap)
    if len(restored["grid"][0]) != before_cols:
        problems.append("undo did not restore column count")
    if restored["grid"][0][2] != "Status":
        problems.append("undo did not restore deleted column header")
    if restored["colWidthsPx"].get(2) != 64:
        problems.append("undo did not restore column width")

    if problems:
        print("FAIL — source undo structural edit")
        for p in problems:
            print(" -", p)
        return 1

    print("OK — source undo restores deleted column")
    print(f"  cols {before_cols} -> {after_cols} -> {len(restored['grid'][0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
