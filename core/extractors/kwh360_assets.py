"""extractors/kwh360_assets.py — the kWh360 input.csv asset inventory.

The clean 11-column asset list (same schema as Singh360_Parser bulk upload).
Each row becomes a node of the right kind, and the "Connected/Area Served"
column becomes the parent link when it names another asset.
"""
from __future__ import annotations

import csv
from pathlib import Path

from core.model import ProjectModel, Node, NodeKind, slug

# Category -> NodeKind (best-fit; unknown categories become DEVICE).
_CAT_KIND = {
    "EMS": NodeKind.RDM,
    "HVAC": NodeKind.RTU,
    "Refrigeration": NodeKind.CIRCUIT,
    "Lighting": NodeKind.LIGHTING,
    "Electrical": NodeKind.PANEL,
    "Energy Monitoring": NodeKind.DEVICE,
}

# Unit/Type refinements within a category.
_TYPE_KIND = {
    "RDM": NodeKind.RDM,
    "Rack": NodeKind.RACK,
    "Suction Group": NodeKind.SUCTION_GROUP,
    "Suction Circuit": NodeKind.CIRCUIT,
    "Self Contained": NodeKind.CIRCUIT,
    "Compressor": NodeKind.COMPRESSOR,
    "Condenser": NodeKind.CONDENSER,
    "RTU": NodeKind.RTU,
    "Aircurtain": NodeKind.AIR_CURTAIN,
    "Panel Testing": NodeKind.PANEL,
    "Exterior": NodeKind.LIGHTING,
    "Interior": NodeKind.LIGHTING,
}

NAME_COL = "Name"
CAT_COL = "Category"
TYPE_COL = "Unit/Type"
PARENT_COL = "Connected/Area Served/Refrigerant/Number Of Racks"
FIXTURE_COL = "Fixture Type/Rack Type/Suction Temp/Make"
CONTROL_COL = "Control Type"


def _kind_for(category: str, unit_type: str) -> NodeKind:
    if unit_type in _TYPE_KIND:
        return _TYPE_KIND[unit_type]
    return _CAT_KIND.get(category, NodeKind.DEVICE)


def extract(path: str | Path, model: ProjectModel) -> None:
    path = Path(path)
    model.note_source(str(path))
    try:
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    except OSError as exc:
        model.flag("blocked", f"could not read {path.name}: {exc}", path.name)
        return

    name_to_id: dict[str, str] = {}
    pending_parent: list[tuple[str, str, str]] = []
    n = 0
    for i, r in enumerate(rows):
        name = (r.get(NAME_COL) or "").strip()
        if not name:
            continue
        category = (r.get(CAT_COL) or "").strip()
        unit_type = (r.get(TYPE_COL) or "").strip()
        kind = _kind_for(category, unit_type)
        nid = slug(kind.value, name)
        ref = f"{path.name}:row{i + 2}"

        attrs = {
            "category": category,
            "unit_type": unit_type,
            "make": (r.get(FIXTURE_COL) or "").strip(),
            "control_type": (r.get(CONTROL_COL) or "").strip(),
        }
        model.add_node(Node(id=nid, kind=kind, name=name, attrs={k: v for k, v in attrs.items() if v}, source=ref))
        name_to_id[name.lower()] = nid

        parent_ref = (r.get(PARENT_COL) or "").strip()
        if parent_ref:
            pending_parent.append((nid, parent_ref, ref))
        n += 1

    # Resolve parent links: only when the value names another asset.
    for nid, parent_ref, ref in pending_parent:
        pid = name_to_id.get(parent_ref.lower())
        node = model.nodes.get(nid)
        if node is None:
            continue
        if pid and pid != nid:
            node.parent = pid
        else:
            # Not a node — keep as an attribute (area served / refrigerant / count).
            node.attrs.setdefault("connected", parent_ref)

    model.flag("info", f"kWh360 assets: {n} assets imported from {path.name}", path.name)
