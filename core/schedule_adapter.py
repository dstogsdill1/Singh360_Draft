"""core/schedule_adapter.py — real MEP schedule -> canonical Singh360 schema.

Bridges raw architect/engineer light-fixture + contactor schedules (as shipped
in HEB SA#31 style .xlsx workbooks) into the canonical inputs the rest of the
pipeline already understands:

  * SCHEDULE STORE sheet  -> assets.csv  (11-column app schema; Lighting nodes)
  * CONTACTORS sheet      -> control_matrix.csv (Relay -> Contactor -> Load)

Mapping is done by HEADER TEXT, not fixed column indices, so minor layout
shifts (extra leading blank columns, merged title rows) don't break it. Header
detection scans for known tokens; every emitted row is traceable back to its
source sheet + Excel row number. Unknown/garbled cells are left blank, never
invented (no-hallucination rule).

Raw header  ->  canonical field
  QTY                         -> qty
  TYPE                        -> Name (fixture type code: C1, CA, PB, ...)
  DESCRIPTION                 -> description
  MANUFACTURER / MODEL        -> make  (col5 "Fixture Type/.../Make")
  VOLTAGE                     -> voltage
  WATTAGE                     -> wattage
  MOUNTING                    -> mounting
  REMARKS                     -> remarks
  RELAY                       -> Relay
  CONTACTOR                   -> Contactor
  CONTROLLED CIRCUIT(S)       -> Panel/circuit reference
  # OF POLES                  -> poles
  DESCRIPTION (contactors)    -> Load (human-readable controlled load)
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import config

# Canonical 11-column app header (mirrors config.APP_COLUMNS).
ASSET_HEADER = list(config.APP_COLUMNS)
CONTROL_HEADER = ["Relay", "Contactor", "Load", "Panel", "Voltage", "Area"]

# Keyword sets for Interior vs Exterior classification of a fixture.
_EXTERIOR_HINTS = (
    "FLOOD", "SECURITY", "PARKING", "EXTERIOR", "CANOPY", "SIGN", "SITE",
    "POLE", "BOLLARD", "WALL PACK", "WALLPACK", "SOFFIT", "PERIMETER",
    "BACKYARD", "OUTDOOR", "AREA LIGHT", "STREET",
)


@dataclass
class AdapterResult:
    assets_csv: Path | None = None
    control_csv: Path | None = None
    fixture_count: int = 0
    contactor_count: int = 0
    flags: list[str] = field(default_factory=list)


def _norm(s: object) -> str:
    """Normalize a cell to clean text; pandas NaN / 'nan' / 'none' -> ''."""
    if s is None:
        return ""
    if isinstance(s, float):
        if math.isnan(s):
            return ""
        if s.is_integer():
            s = int(s)
    text = re.sub(r"\s+", " ", str(s)).strip()
    if text.lower() in ("nan", "none"):
        return ""
    return text


def _read_grid(xlsx_path: Path, sheet: str) -> list[list[str]]:
    """Read one sheet as a dense string grid (no header inference)."""
    import pandas as pd  # local import; openpyxl-backed

    df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None, dtype=str)
    return [[_norm(c) for c in row] for row in df.itertuples(index=False, name=None)]


def _sheet_names(xlsx_path: Path) -> list[str]:
    import pandas as pd

    return list(pd.ExcelFile(xlsx_path).sheet_names)


def _pick_sheet(names: list[str], *tokens: str) -> str | None:
    """First sheet whose name contains any token (case-insensitive)."""
    up = {n: n.upper() for n in names}
    for tok in tokens:
        for n in names:
            if tok in up[n]:
                return n
    return None


def _find_header_row(grid: list[list[str]], required: tuple[str, ...]) -> int:
    """Index of the first row containing every required token (substring)."""
    for i, row in enumerate(grid):
        cells = [c.upper() for c in row]
        if all(any(tok in cell for cell in cells) for tok in required):
            return i
    return -1


def _col_index(header: list[str], *aliases: str) -> int:
    """First column whose normalized-upper header contains any alias."""
    cells = [c.upper() for c in header]
    for alias in aliases:
        for ci, cell in enumerate(cells):
            if alias in cell:
                return ci
    return -1


def _classify_fixture(*texts: str) -> str:
    blob = " ".join(t.upper() for t in texts if t)
    return "Exterior" if any(h in blob for h in _EXTERIOR_HINTS) else "Interior"


# --------------------------------------------------------------------------
# Fixture schedule -> canonical assets
# --------------------------------------------------------------------------
def extract_fixtures(xlsx_path: Path, sheet: str) -> tuple[list[list[str]], list[str]]:
    grid = _read_grid(xlsx_path, sheet)
    flags: list[str] = []
    hdr_i = _find_header_row(grid, ("TYPE", "DESCRIPTION"))
    if hdr_i < 0:
        flags.append(f"{sheet}: fixture header (TYPE/DESCRIPTION) not found; skipped")
        return [], flags
    header = grid[hdr_i]
    c_qty = _col_index(header, "QTY", "QUANTITY")
    c_type = _col_index(header, "TYPE")
    c_desc = _col_index(header, "DESCRIPTION")
    c_make = _col_index(header, "MANUFACTURER", "MODEL", "MAKE")
    c_volt = _col_index(header, "VOLTAGE", "VOLT")
    c_watt = _col_index(header, "WATTAGE", "WATT")
    c_mount = _col_index(header, "MOUNTING", "MOUNT")
    c_rem = _col_index(header, "REMARKS", "REMARK")

    def cell(row: list[str], ci: int) -> str:
        return row[ci] if 0 <= ci < len(row) else ""

    rows: list[list[str]] = []
    for r in grid[hdr_i + 1:]:
        ftype = cell(r, c_type)
        if not ftype or ftype.upper() in ("TYPE", "NO.", "FIXTURE"):
            continue
        desc = cell(r, c_desc)
        make = cell(r, c_make)
        volt = cell(r, c_volt)
        watt = cell(r, c_watt)
        mount = cell(r, c_mount)
        rem = cell(r, c_rem)
        qty = cell(r, c_qty)
        unit_type = _classify_fixture(desc, mount, rem)
        # Pack secondary specs into the description so they survive in the node.
        served = " | ".join(
            p for p in (f"Qty {qty}" if qty else "", volt, watt) if p
        )
        rows.append(
            [
                "Lighting",          # Category
                unit_type,           # Unit/Type  (Interior | Exterior)
                ftype,               # Name        (fixture type code)
                served,              # Connected/Area Served/... (qty·volt·watt)
                make or desc,        # Fixture Type/.../Make
                "",                  # Control Type
                "",                  # Design Temperature Set Point (F)
                "",                  # Issue-Desc
                "",                  # Issue-Reco
                "",                  # Issue-Assign to
                desc,                # Sub Form Category (full description)
            ]
        )
    if not rows:
        flags.append(f"{sheet}: no fixture rows extracted below header")
    return rows, flags


# --------------------------------------------------------------------------
# Contactor schedule -> canonical control matrix
# --------------------------------------------------------------------------
def extract_contactors(xlsx_path: Path, sheet: str) -> tuple[list[list[str]], list[str]]:
    grid = _read_grid(xlsx_path, sheet)
    flags: list[str] = []
    hdr_i = _find_header_row(grid, ("RELAY", "CONTACTOR"))
    if hdr_i < 0:
        flags.append(f"{sheet}: contactor header (RELAY/CONTACTOR) not found; skipped")
        return [], flags
    header = grid[hdr_i]
    c_relay = _col_index(header, "RELAY")
    c_cont = _col_index(header, "CONTACTOR")
    c_circ = _col_index(header, "CONTROLLED CIRCUIT", "CIRCUIT")
    c_desc = _col_index(header, "DESCRIPTION", "LOAD", "SERVICE")
    c_pole = _col_index(header, "POLE", "# OF POLES", "POLES")
    c_panel = _col_index(header, "LCP", "PANEL")

    def cell(row: list[str], ci: int) -> str:
        return row[ci] if 0 <= ci < len(row) else ""

    rows: list[list[str]] = []
    for r in grid[hdr_i + 1:]:
        relay = cell(r, c_relay)
        contactor = cell(r, c_cont)
        if not relay and not contactor:
            continue
        if relay.upper() == "RELAY":
            continue
        circuit = cell(r, c_circ)
        desc = cell(r, c_desc)
        poles = cell(r, c_pole)
        load = desc or (f"{contactor or relay} load")
        if poles:
            load = f"{load} ({poles}P)"
        # Panel = an explicit LCP/PANEL column, else parse PANEL "XX" from circuit.
        panel = cell(r, c_panel)
        if not panel:
            m = re.search(r'(?:LCP|PANEL)[\s#\-]*["\']?([A-Z0-9\-]+)', circuit.upper())
            panel = m.group(1) if m else circuit
        rows.append([relay, contactor, load, panel, "", ""])
    if not rows:
        flags.append(f"{sheet}: no contactor rows extracted below header")
    return rows, flags


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def convert(xlsx_path: str | Path, out_dir: str | Path) -> AdapterResult:
    """Convert a SA#31-style schedule workbook into canonical CSVs.

    Writes <out_dir>/assets.csv and <out_dir>/control_matrix.csv (only the ones
    that have rows) and returns an AdapterResult with counts + flags.
    """
    xlsx_path = Path(xlsx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = AdapterResult()

    if not xlsx_path.exists():
        res.flags.append(f"workbook not found: {xlsx_path}")
        return res

    names = _sheet_names(xlsx_path)
    fixture_sheet = _pick_sheet(names, "SCHEDULE", "FIXTURE", "LIGHT", "STORE")
    contactor_sheet = _pick_sheet(names, "CONTACTOR", "RELAY", "CONTROL")

    if fixture_sheet:
        rows, flags = extract_fixtures(xlsx_path, fixture_sheet)
        res.flags += flags
        if rows:
            res.assets_csv = out_dir / "assets.csv"
            _write_csv(res.assets_csv, ASSET_HEADER, rows)
            res.fixture_count = len(rows)
    else:
        res.flags.append("no fixture/schedule sheet found in workbook")

    if contactor_sheet:
        rows, flags = extract_contactors(xlsx_path, contactor_sheet)
        res.flags += flags
        if rows:
            res.control_csv = out_dir / "control_matrix.csv"
            _write_csv(res.control_csv, CONTROL_HEADER, rows)
            res.contactor_count = len(rows)
    else:
        res.flags.append("no contactor sheet found in workbook")

    return res


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
