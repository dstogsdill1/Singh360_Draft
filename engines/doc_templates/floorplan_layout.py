"""doc_templates/floorplan_layout.py — 2D floor-plan / equipment layout sheet.

Reverse-engineered from the HEB gold EMS .vsdx: an Arch D (42x30) sheet that
places equipment at absolute positions on a 2D canvas (not a tree), grouped
into spatial zones and wired with glued connectors.

This template just shapes the DiagramGraph; the spatial PLACEMENT is done by
engines.spatial_layout via the VsdxWriter(layout_fn=...). See pipeline_cli /
main_generator for wiring.
"""
from __future__ import annotations

from core.model import ProjectModel, NodeKind
from core.data_orchestrator import DiagramGraph, Node, Edge

# group equipment into the zones the gold sheets use
_ZONE = {
    NodeKind.RDM: "Head End",
    NodeKind.NETWORK: "Head End",
    NodeKind.BOARD: "Controllers",
    NodeKind.RACK: "Refrigeration",
    NodeKind.SUCTION_GROUP: "Refrigeration",
    NodeKind.CIRCUIT: "Refrigeration",
    NodeKind.COMPRESSOR: "Refrigeration",
    NodeKind.CONDENSER: "Refrigeration",
    NodeKind.PANEL: "Panels",
    NodeKind.RTU: "HVAC",
    NodeKind.AIR_CURTAIN: "HVAC",
    NodeKind.COOLING_TOWER: "HVAC",
    NodeKind.LIGHTING: "Lighting",
    NodeKind.DEVICE: "Devices",
}
_CATEGORY = {
    NodeKind.RDM: "EMS", NodeKind.NETWORK: "Network", NodeKind.BOARD: "EMS",
    NodeKind.RACK: "Refrigeration", NodeKind.SUCTION_GROUP: "Refrigeration",
    NodeKind.CIRCUIT: "Refrigeration", NodeKind.COMPRESSOR: "Refrigeration",
    NodeKind.CONDENSER: "Refrigeration", NodeKind.PANEL: "Electrical",
    NodeKind.RTU: "HVAC", NodeKind.AIR_CURTAIN: "HVAC",
    NodeKind.COOLING_TOWER: "HVAC", NodeKind.LIGHTING: "Lighting",
    NodeKind.DEVICE: "Energy Monitoring",
}


def build(model: ProjectModel) -> DiagramGraph:
    g = DiagramGraph(name=f"{model.store or model.title} — Equipment Layout")

    skip = {"drawing", "survey_photo"}
    placed = 0
    anchored = 0
    for nid, node in model.nodes.items():
        if node.attrs.get("kind") in skip:
            continue
        zone = _ZONE.get(node.kind, "Devices")
        # Pull any real floor-plan anchor (inches, bottom-left origin) the
        # lighting_plan / spatial extractors stamped into attrs. Absolute X/Y
        # always wins over zone-clustering — true to the gold sheet placement.
        ax = _as_float(node.attrs.get("x"))
        ay = _as_float(node.attrs.get("y"))
        if ax is not None and ay is not None:
            anchored += 1
        g.add_node(Node(
            id=nid, label=node.name,
            category=_CATEGORY.get(node.kind, "Energy Monitoring"),
            unit_type=node.kind.value, group=zone,
            attrs={k: v for k, v in node.attrs.items() if k in ("nw", "slv", "ip", "make", "control_type", "lcp", "zones", "fixture_type")},
            x=ax, y=ay,
            source=node.source,
        ))
        placed += 1

    # parent links become connectors (refrigeration topology etc.)
    for nid, node in model.nodes.items():
        if node.parent and node.parent in model.nodes and nid in g.nodes:
            g.add_edge(Edge(source=nid, target=node.parent, kind="hierarchy",
                            source_ref=node.source))

    if anchored:
        g.flags.append(
            f"Equipment layout: {placed} items placed; {anchored} at ABSOLUTE "
            f"floor-plan X/Y (true coordinates), rest packed into zones."
        )
    else:
        g.flags.append(f"Equipment layout: {placed} items placed on the 2D canvas.")
    return g


def _as_float(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
