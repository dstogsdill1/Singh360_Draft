"""extractors/ems_worksheet.py — EMS point-to-point I/O worksheet (.xlsx).

The engineer's I/O list. Layout varies, so we read by HEADER TEXT, not fixed
columns: we scan for a header row containing the I/O signature (a "board" or
"controller" column plus "relay"/"probe"/"point"/"cable"), then turn each data
row into an IOPoint attached to its board node. Empty cells stay blank
(pandas NaN -> "" — never the literal "nan").
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from core.model import ProjectModel, Node, IOPoint, NodeKind, PointKind, slug

# header tokens -> our point kind
_KIND_TOKENS = {
    PointKind.RELAY: ("relay", "output", "load"),
    PointKind.PROBE: ("probe", "sensor", "temp", "input"),
    PointKind.STATUS: ("status", "alarm", "digital"),
    PointKind.ANALOG: ("universal", "analog", "pressure", "signal", "4-20", "0-10"),
    PointKind.VALVE: ("valve", "eev", "stepper"),
}


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if v.is_integer():
            v = int(v)
    t = re.sub(r"\s+", " ", str(v)).strip()
    return "" if t.lower() in ("nan", "none") else t


def extract(path: str | Path, model: ProjectModel) -> None:
    path = Path(path)
    model.note_source(str(path))
    try:
        import pandas as pd
    except ImportError:
        model.flag("blocked", "pandas/openpyxl required for EMS worksheet extraction", path.name)
        return

    try:
        xl = pd.ExcelFile(path)
    except Exception as exc:  # noqa: BLE001
        model.flag("blocked", f"could not open {path.name}: {exc}", path.name)
        return

    total_points = 0
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, header=None, dtype=str)
        grid = [[_norm(c) for c in row] for row in df.itertuples(index=False, name=None)]
        total_points += _parse_sheet(grid, sheet, model, f"{path.name}:{sheet}")

    if total_points == 0:
        model.flag(
            "review",
            f"{path.name}: no I/O rows recognized — worksheet layout may need a custom map",
            path.name,
        )
    else:
        model.flag("info", f"EMS worksheet: {total_points} I/O points extracted", path.name)


def _find_header(grid: list[list[str]]) -> int:
    for i, row in enumerate(grid):
        cells = [c.lower() for c in row]
        has_point = any(any(t in c for t in ("relay", "probe", "point", "input", "output")) for c in cells)
        has_cable = any("cable" in c or "cbl" in c for c in cells)
        if has_point and has_cable:
            return i
    return -1


def _col(header: list[str], *aliases: str) -> int:
    cells = [c.lower() for c in header]
    for a in aliases:
        for ci, c in enumerate(cells):
            if a in c:
                return ci
    return -1


def _kind_for_header(header_text: str) -> PointKind:
    low = header_text.lower()
    for kind, toks in _KIND_TOKENS.items():
        if any(t in low for t in toks):
            return kind
    return PointKind.PROBE


def _parse_sheet(grid: list[list[str]], sheet: str, model: ProjectModel, ref: str) -> int:
    hi = _find_header(grid)
    if hi < 0:
        return 0
    header = grid[hi]
    c_board = _col(header, "board", "controller", "panel")
    c_point = _col(header, "point", "relay", "input", "output", "description", "label")
    c_loc = _col(header, "location", "loc", "type")
    c_cable = _col(header, "cable", "cbl")
    c_load = _col(header, "load", "served", "device")

    # board node for this sheet (sheet name is a decent board label fallback)
    board_name = sheet.strip() or "Board"
    board_id = slug("board", board_name)
    model.add_node(Node(id=board_id, kind=NodeKind.BOARD, name=board_name, source=ref))

    def cell(row, ci):
        return row[ci] if 0 <= ci < len(row) else ""

    n = 0
    for r in grid[hi + 1:]:
        label = cell(r, c_point)
        cable = cell(r, c_cable)
        if not label and not cable:
            continue
        kind = _kind_for_header(label)
        model.add_point(board_id, IOPoint(
            kind=kind,
            label=label or "(point)",
            loc_type=cell(r, c_loc),
            cable=cable,
            load=cell(r, c_load),
            source=ref,
        ))
        n += 1
    return n
