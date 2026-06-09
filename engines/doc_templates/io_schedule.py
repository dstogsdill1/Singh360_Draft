"""doc_templates/io_schedule.py — Point-to-Point I/O Schedule sheet.

Walks the ProjectModel's boards and turns each board + its I/O points into a
DiagramGraph: the board is a parent node, each relay/sensor/alarm/signal/valve
is a child node connected to it, labeled in plain English with the cable number.
The existing visio_vsdx / smartdraw_vson engines render the graph.
"""
from __future__ import annotations

from core.model import ProjectModel, NodeKind, PointKind
from core.data_orchestrator import DiagramGraph, Node, Edge

_POINT_CATEGORY = {
    PointKind.RELAY: "Relay",
    PointKind.PROBE: "Refrigeration",
    PointKind.STATUS: "Electrical",
    PointKind.ANALOG: "Energy Monitoring",
    PointKind.VALVE: "Refrigeration",
}
_POINT_WORD = {
    PointKind.RELAY: "Relay",
    PointKind.PROBE: "Sensor",
    PointKind.STATUS: "Alarm",
    PointKind.ANALOG: "Signal",
    PointKind.VALVE: "Valve",
}


def build(model: ProjectModel) -> DiagramGraph:
    g = DiagramGraph(name=f"{model.store or model.title} — I/O Schedule")

    boards = model.by_kind(NodeKind.BOARD) + model.by_kind(NodeKind.RACK)
    if not boards:
        g.flags.append("No controller boards in model — nothing to schedule.")
        return g

    for board in boards:
        bid = f"Board:{board.name}"
        g.add_node(Node(
            id=bid, label=board.name, category="EMS",
            unit_type=board.attrs.get("unit_type", "Controller"),
            group=board.name, source=board.source,
        ))
        for i, p in enumerate(board.points):
            word = _POINT_WORD.get(p.kind, "Point")
            # plain-English label: "Sensor — Suction temp  (cable 601)"
            bits = [p.label or word]
            if p.load:
                bits.append("→ " + p.load)
            if p.cable:
                bits.append(f"(cable {p.cable})")
            label = "  ".join(bits)
            pid = f"{bid}:{p.kind.value}:{i}"
            g.add_node(Node(
                id=pid, label=label,
                category=_POINT_CATEGORY.get(p.kind, "Energy Monitoring"),
                unit_type=word, group=board.name,
                attrs={k: v for k, v in {
                    "signal": p.signal, "location": p.loc_type, "cable": p.cable,
                    "value": (p.value + " " + p.units).strip(),
                }.items() if v},
                source=p.source,
            ))
            g.add_edge(Edge(source=pid, target=bid, kind="control",
                            label=word, source_ref=p.source))

    g.flags.append(f"I/O schedule built from {len(boards)} board(s).")
    return g
