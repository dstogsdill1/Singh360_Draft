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
    for nid, node in model.nodes.items():
        if node.attrs.get("kind") in skip:
            continue
        zone = _ZONE.get(node.kind, "Devices")
        g.add_node(Node(
            id=nid, label=node.name,
            category=_CATEGORY.get(node.kind, "Energy Monitoring"),
            unit_type=node.kind.value, group=zone,
            attrs={k: v for k, v in node.attrs.items() if k in ("nw", "slv", "ip", "make", "control_type")},
            # carry any real floor-plan anchor straight through
            x=None, y=None,
            source=node.source,
        ))
        placed += 1

    # parent links become connectors (refrigeration topology etc.)
    for nid, node in model.nodes.items():
        if node.parent and node.parent in model.nodes and nid in g.nodes:
            g.add_edge(Edge(source=nid, target=node.parent, kind="hierarchy",
                            source_ref=node.source))

    g.flags.append(f"Equipment layout: {placed} items placed on the 2D canvas.")
    return g
