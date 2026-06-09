"""extractors/cad_worksheet.py — HEB CAD Worksheet (.xlsx) point-to-point I/O.

The CAD Worksheet is the real wiring source (vs. the EM Worksheet, which is a
procurement tracker). Each board sheet (Rack A, Rack B, IDF#1, CONDENSER,
WI-PR0751, HVAC Control, Lighting-TDB, DATAMANGER, BACNet) holds a MATRIX with
up to four I/O columns side by side, repeated per board block:

  RO# | Output Relay Desc | Contact | DI# | Status Input Name | Contact |
  PI# | Probe Input Name | Type | UIO# | Universal I/O Desc | Signal

One spreadsheet row = one terminal slot across all four I/O types. We read by
HEADER TEXT (so column shifts don't break it), split each row into up to four
IOPoints, and attach them to a board node named after the sheet (and any
"Intuitive Controller" / "Expansion Board" sub-block header).

Skipped non-I/O sheets: Sheet1, TOC, BOM, Panel Details.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from core.model import ProjectModel, Node, IOPoint, NodeKind, PointKind, slug

_SKIP_SHEETS = {"sheet1", "toc", "bom", "panel details", "notes"}

# header token -> (column-trio start matcher). We locate each I/O block by its
# leading number-column header (RO#, DI#, PI#, UIO#).
_BLOCKS = [
    ("relay", PointKind.RELAY, ("ro#", "ro #", "relay#"), ("output relay", "relay desc", "output")),
    ("status", PointKind.STATUS, ("di#", "di #", "status#"), ("status input", "status")),
    ("probe", PointKind.PROBE, ("pi#", "pi #", "probe#"), ("probe input", "probe")),
    ("analog", PointKind.ANALOG, ("uio#", "ui#", "uo#", "uio #"), ("universal", "i/o", "analog")),
]


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
        model.flag("blocked", "pandas/openpyxl required for CAD worksheet extraction", path.name)
        return
    try:
        xl = pd.ExcelFile(path)
    except Exception as exc:  # noqa: BLE001
        model.flag("blocked", f"could not open {path.name}: {exc}", path.name)
        return

    total = 0
    boards = 0
    for sheet in xl.sheet_names:
        if sheet.strip().lower() in _SKIP_SHEETS:
            continue
        df = pd.read_excel(path, sheet_name=sheet, header=None, dtype=str)
        grid = [[_norm(c) for c in row] for row in df.itertuples(index=False, name=None)]
        n = _parse_sheet(grid, sheet, model, f"{path.name}:{sheet}")
        if n:
            boards += 1
            total += n

    if total:
        model.flag("info", f"CAD worksheet: {total} I/O points across {boards} board sheet(s)", path.name)
    else:
        model.flag("review", f"{path.name}: no I/O matrix recognized — check sheet layout", path.name)


def _find_io_header_rows(grid: list[list[str]]) -> list[int]:
    """Rows that look like the I/O matrix header (contain RO#/DI#/PI#/UIO#)."""
    out = []
    for i, row in enumerate(grid):
        low = [c.lower() for c in row]
        joined = " ".join(low)
        hits = sum(1 for _b, _k, nums, _d in _BLOCKS if any(t in joined for t in nums))
        if hits >= 2:  # at least two I/O block headers on this row
            out.append(i)
    return out


def _locate_blocks(header: list[str]) -> list[tuple[PointKind, int, int]]:
    """Return [(kind, num_col, desc_col)] located by header text in this row."""
    low = [c.lower() for c in header]
    found = []
    for _b, kind, nums, descs in _BLOCKS:
        num_col = -1
        for ci, c in enumerate(low):
            if any(c == t or c.startswith(t) for t in nums):
                num_col = ci
                break
        if num_col < 0:
            continue
        # description column = first matching desc header at/after num_col
        desc_col = -1
        for ci in range(num_col + 1, min(num_col + 4, len(low))):
            if any(t in low[ci] for t in descs):
                desc_col = ci
                break
        if desc_col < 0:
            desc_col = num_col + 1
        found.append((kind, num_col, desc_col))
    return found


def _board_name_above(grid: list[list[str]], header_row: int, sheet: str) -> str:
    """Find a sub-block title just above the header (e.g. 'Intuitive Controller',
    'Expansion Board'); fall back to the sheet name."""
    for r in range(header_row - 1, max(-1, header_row - 3), -1):
        if r < 0:
            break
        text = " ".join(c for c in grid[r] if c).strip()
        if text and not any(k in text.lower() for k in ("ro#", "di#", "pi#", "uio#")):
            return f"{sheet} — {text[:40]}"
    return sheet


def _parse_sheet(grid: list[list[str]], sheet: str, model: ProjectModel, ref: str) -> int:
    header_rows = _find_io_header_rows(grid)
    if not header_rows:
        return 0

    n_points = 0
    for hi in header_rows:
        blocks = _locate_blocks(grid[hi])
        if not blocks:
            continue
        board_name = _board_name_above(grid, hi, sheet)
        board_id = slug("board", board_name)
        model.add_node(Node(id=board_id, kind=NodeKind.BOARD, name=board_name, source=ref))

        # data rows until the next header row or a fully blank row
        end = len(grid)
        for nxt in header_rows:
            if nxt > hi:
                end = nxt
                break
        for r in range(hi + 1, end):
            row = grid[r]
            if not any(row):
                continue
            for kind, num_col, desc_col in blocks:
                num = row[num_col] if num_col < len(row) else ""
                desc = row[desc_col] if desc_col < len(row) else ""
                # the 3rd column of each block is Contact/Type/Signal
                extra = row[desc_col + 1] if desc_col + 1 < len(row) else ""
                if not num and not desc:
                    continue
                if not desc:  # a bare slot number with no description = empty slot
                    continue
                model.add_point(board_id, IOPoint(
                    kind=kind,
                    label=desc,
                    point_no=num,
                    signal=extra,
                    source=ref,
                ))
                n_points += 1
    return n_points
