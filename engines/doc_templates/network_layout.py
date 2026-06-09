"""doc_templates/network_layout.py — Network / Comm Layout sheet.

Builds a network diagram from the model: the RDM data manager at the top, the
switch / comm trunk beneath it, and every controller board / device hanging off
the network. Shows how the store ties together.
"""
from __future__ import annotations

from core.model import ProjectModel, NodeKind
from core.data_orchestrator import DiagramGraph, Node, Edge


def build(model: ProjectModel) -> DiagramGraph:
    g = DiagramGraph(name=f"{model.store or model.title} — Network Layout")

    # Site / RDM root
    rdms = model.by_kind(NodeKind.RDM)
    root_id = "Net:RDM"
    root_label = rdms[0].name if rdms else "RDM Data Manager"
    g.add_node(Node(id=root_id, label=root_label, category="EMS",
                    unit_type="RDM", group="Network",
                    source=rdms[0].source if rdms else ""))

    # Comm trunk node
    trunk_id = "Net:Trunk"
    g.add_node(Node(id=trunk_id, label="Comm Trunk (CANBUS)", category="Network",
                    unit_type="Switch", group="Network"))
    g.add_edge(Edge(source=trunk_id, target=root_id, kind="network", label="uplink"))

    # Every board / device on the trunk
    networked = (model.by_kind(NodeKind.BOARD) + model.by_kind(NodeKind.RACK)
                 + model.by_kind(NodeKind.PANEL) + model.by_kind(NodeKind.DEVICE))
    n = 0
    for node in networked:
        if node.attrs.get("kind") in ("drawing", "survey_photo"):
            continue  # not network devices
        nid = f"Net:{node.id}"
        addr = node.attrs.get("nw", "")
        slv = node.attrs.get("slv", "")
        label = node.name + (f"  ({addr}.{slv})" if addr or slv else "")
        g.add_node(Node(id=nid, label=label, category="Network",
                        unit_type=node.kind.value, group="Network",
                        attrs={k: v for k, v in node.attrs.items() if k in ("nw", "slv", "ip", "mac")},
                        source=node.source))
        g.add_edge(Edge(source=nid, target=trunk_id, kind="network",
                        label="", source_ref=node.source))
        n += 1

    g.flags.append(f"Network layout: {n} device(s) on the trunk.")
    return g
