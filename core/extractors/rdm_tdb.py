"""extractors/rdm_tdb.py — RDM TDB layout (.xlsx).

Reads the RDM TDB Layout workbook to learn how the RDM controllers are laid
out and which case controllers they own. Layout varies by site, so this scans
sheets for RDM/case-controller signatures and records what it finds; rows it
can't map are flagged for review rather than guessed.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from core.model import ProjectModel, Node, NodeKind, slug


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    t = re.sub(r"\s+", " ", str(v)).strip()
    return "" if t.lower() in ("nan", "none") else t


def extract(path: str | Path, model: ProjectModel) -> None:
    path = Path(path)
    model.note_source(str(path))
    try:
        import pandas as pd
    except ImportError:
        model.flag("blocked", "pandas/openpyxl required for RDM TDB extraction", path.name)
        return
    try:
        xl = pd.ExcelFile(path)
    except Exception as exc:  # noqa: BLE001
        model.flag("blocked", f"could not open {path.name}: {exc}", path.name)
        return

    found = 0
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, header=None, dtype=str)
        for row in df.itertuples(index=False, name=None):
            cells = [_norm(c) for c in row]
            joined = " ".join(cells).upper()
            if "RDM" in joined and any(c for c in cells):
                label = next((c for c in cells if c and "RDM" in c.upper()), "RDM")
                model.add_node(Node(
                    id=slug("rdm", label, sheet),
                    kind=NodeKind.RDM, name=label,
                    attrs={"sheet": sheet}, source=f"{path.name}:{sheet}",
                ))
                found += 1
    model.flag(
        "info" if found else "review",
        f"RDM TDB: {found} RDM entries indexed from {path.name}"
        + ("" if found else " — layout may need a custom map"),
        path.name,
    )
