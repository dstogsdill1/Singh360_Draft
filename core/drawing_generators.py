"""core/drawing_generators.py — Milestone 4A data-driven generators (Phase 7).

Three deterministic generators that turn structured project data into drawing
graphs. They never invent nodes, edges, addresses, or coordinates — blanks stay
blank and every produced node/edge carries a `source` string.

Output shape (neutral, engine-agnostic):

    {
      "title": str,
      "sheetKind": str,
      "nodes":   [{"id","label","type","x","y","w","h","source", ...}],
      "edges":   [{"from","to","preset","label","source"}],
      "legend":  [{"id","label","note"}],       # connector presets used
      "notes":   [str],                          # e.g. "N.T.S."
    }

Coordinates are in points (72 pt/in), top-left origin, ready for the SVG /
page templates in Phase 5.
"""
from __future__ import annotations

from core.drawing_style import CONNECTOR_PRESETS, connector_preset, category_default

# --- layout constants (points) -------------------------------------------
_MARGIN = 54.0
_COL_W = 190.0
_ROW_H = 130.0
_NODE_W = 150.0
_NODE_H = 60.0


def _legend_for(preset_ids: set[str]) -> list[dict]:
    out = []
    for p in CONNECTOR_PRESETS:
        if p.id in preset_ids:
            out.append({"id": p.id, "label": p.label, "note": p.note})
    return out


def _node(nid: str, label: str, ntype: str, col: int, row: int, source: str) -> dict:
    return {
        "id": nid,
        "label": label,
        "type": ntype,
        "x": _MARGIN + col * _COL_W,
        "y": _MARGIN + row * _ROW_H,
        "w": _NODE_W,
        "h": _NODE_H,
        "source": source,
    }


# --------------------------------------------------------------------------
# A) Overall EMS Controls Layout
# --------------------------------------------------------------------------
# Deterministic role → (column, row) placement for the backbone. Missing roles
# are simply omitted; discovered assets fill the lower rows.
_BACKBONE = [
    ("data_manager", "Data Manager", "network", 1, 0),
    ("rdm_idf", "RDM IDF", "network", 0, 1),
    ("mdf", "MDF", "network", 2, 1),
]


def generate_overall_layout(assets: list[dict] | None = None, *, title: str = "EMS Controls Overall Layout") -> dict:
    """Build the Overall EMS Controls Layout from discovered assets.

    `assets` is a list of dicts with at least {name, category}. Recognised
    backbone roles (Data Manager, RDM IDF, MDF, LCP1/2, panels, sensors,
    dimming modules) are placed; everything else lands in a device band.
    Connectors use presets; an N.T.S. note and a legend are added.
    """
    assets = assets or []
    nodes: list[dict] = []
    edges: list[dict] = []
    presets_used: set[str] = set()

    have: dict[str, dict] = {}
    for nid, label, ntype, col, row in _BACKBONE:
        n = _node(nid, label, ntype, col, row, "generator:backbone")
        nodes.append(n)
        have[nid] = n

    # Backbone links (only between nodes that exist).
    def link(a: str, b: str, preset: str) -> None:
        if a in have and b in have:
            edges.append({"from": a, "to": b, "preset": preset,
                          "label": connector_preset(preset).label, "source": "generator:backbone"})
            presets_used.add(preset)

    link("rdm_idf", "data_manager", "cat6")
    link("data_manager", "mdf", "fiber")

    # Discovered assets → device band. Deterministic ordering by name.
    band_row = 2
    col = 0
    max_cols = 5
    for i, a in enumerate(sorted(assets, key=lambda x: str(x.get("name", "")))):
        name = str(a.get("name", "")).strip()
        if not name:
            continue
        category = str(a.get("category", "")).strip().lower()
        ntype = _asset_type(category, name)
        nid = f"asset_{i}"
        nodes.append(_node(nid, name, ntype, col, band_row, a.get("source", "generator:asset")))
        # Panels/LCPs connect back to the Data Manager on control wiring.
        if ntype in ("panel", "device") and "data_manager" in have:
            edges.append({"from": nid, "to": "data_manager", "preset": "control",
                          "label": connector_preset("control").label, "source": "generator:asset"})
            presets_used.add("control")
        col += 1
        if col >= max_cols:
            col = 0
            band_row += 1

    return {
        "title": title,
        "sheetKind": "layout",
        "nodes": nodes,
        "edges": edges,
        "legend": _legend_for(presets_used),
        "notes": ["N.T.S."],
    }


def _asset_type(category: str, name: str) -> str:
    n = name.lower()
    if "lcp" in n or "panel" in n or category in ("panels_enclosures", "electrical_power"):
        return "panel"
    if "sensor" in n or category == "sensors_transducers":
        return "sensor"
    if "dimm" in n or category == "lighting":
        return "device"
    if category:
        return category_default(category).type
    return "device"


# --------------------------------------------------------------------------
# B) Component Rack / Stack
# --------------------------------------------------------------------------
def generate_component_stack(components: list[dict], *, title: str = "Component Rack / Stack") -> dict:
    """Stack selected components vertically with consistent spacing + labels."""
    nodes: list[dict] = []
    x = _MARGIN + _COL_W
    y = _MARGIN
    gap = 18.0
    for i, comp in enumerate(components):
        label = str(comp.get("defaultLabel") or comp.get("partNumber") or comp.get("displayName") or f"Item {i+1}")
        w = float(comp.get("defaultWidth") or _NODE_W)
        h = float(comp.get("defaultHeight") or _NODE_H)
        nodes.append({
            "id": comp.get("id") or f"stack_{i}",
            "label": label,
            "type": comp.get("type", "device"),
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "source": comp.get("source") or "generator:stack",
        })
        y += h + gap
    return {
        "title": title,
        "sheetKind": "layout",
        "nodes": nodes,
        "edges": [],
        "legend": [],
        "notes": [],
    }


# --------------------------------------------------------------------------
# C) Callout Schedule (from placed components)
# --------------------------------------------------------------------------
CALLOUT_COLUMNS = ["Callout", "Device ID", "Part No.", "Address", "Location", "Notes"]


def generate_callout_schedule(placed: list[dict], *, title: str = "Callout Schedule") -> dict:
    """Build a callout schedule table from placed components.

    Blank cells stay blank (never invented). Callouts are sequential integers
    in placement order.
    """
    rows: list[dict] = []
    for i, comp in enumerate(placed, start=1):
        rows.append({
            "Callout": str(i),
            "Device ID": str(comp.get("deviceId") or comp.get("id") or ""),
            "Part No.": str(comp.get("partNumber") or ""),
            "Address": str(comp.get("address") or ""),
            "Location": str(comp.get("location") or ""),
            "Notes": str(comp.get("notes") or ""),
            "_source": str(comp.get("source") or "generator:callout"),
        })
    return {
        "title": title,
        "sheetKind": "schedule",
        "columns": CALLOUT_COLUMNS,
        "rows": rows,
        "notes": [],
    }
