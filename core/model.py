"""core/model.py — the canonical EMS project model.

Every extractor (Emerson dump, EMS worksheet, RDM TDB, panel config, CD
drawings, kWh360 assets, survey photos) normalizes its findings into THIS
model. The document templates read only this model. That decoupling is what
lets one project produce many sheet types and many output formats.

Design rules (shared with the rest of Singh360_SmartDraw):
  * No hallucination — unknown fields stay empty, never invented.
  * Traceability — every node/point carries a `source` provenance string.
  * Deterministic — plain dataclasses, stable ids, JSON round-trippable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------
class NodeKind(str, Enum):
    SITE = "site"
    RDM = "rdm"                  # site data manager
    NETWORK = "network"         # switch / comm trunk
    BOARD = "board"             # controller board / card
    RACK = "rack"               # refrigeration rack
    SUCTION_GROUP = "suction_group"
    CIRCUIT = "circuit"         # case / circuit
    COMPRESSOR = "compressor"
    CONDENSER = "condenser"
    PANEL = "panel"             # WICP / control panel
    RTU = "rtu"
    AIR_CURTAIN = "air_curtain"
    COOLING_TOWER = "cooling_tower"
    LIGHTING = "lighting"
    DEVICE = "device"           # generic networked device


class PointKind(str, Enum):
    RELAY = "relay"             # output relay (NC/NO/C)
    PROBE = "probe"             # sensor / temperature input
    STATUS = "status"           # digital alarm / status input
    ANALOG = "analog"           # 4-20mA / 0-10V / 0-5V signal
    VALVE = "valve"             # EEV / stepper valve output


# --------------------------------------------------------------------------
# Core records
# --------------------------------------------------------------------------
@dataclass
class IOPoint:
    """One wired I/O point on a board (a relay, sensor, alarm, signal, valve)."""

    kind: PointKind
    label: str                          # plain text ("Suction temp", "Oil failure")
    point_no: str = ""                  # e.g. "1)" or relay number
    loc_type: str = ""                  # sensor location/type code (LT1, TB4, P51)
    signal: str = ""                    # "4-20mA" / "0-10V" / "DGT" / "NC/NO/C"
    cable: str = ""                     # cable number
    load: str = ""                      # what a relay drives / what a valve serves
    value: str = ""                     # optional live value
    units: str = ""
    source: str = ""                    # provenance "file:row"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


@dataclass
class Node:
    """A physical/logical thing in the store (controller, rack, case, panel…)."""

    id: str
    kind: NodeKind
    name: str
    parent: str | None = None           # id of the parent node
    attrs: dict[str, str] = field(default_factory=dict)
    points: list[IOPoint] = field(default_factory=list)
    source: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["points"] = [p.to_dict() for p in self.points]
        return d


@dataclass
class Flag:
    """A validation finding — gap, conflict, or note. Never a silent guess."""

    level: str                          # "info" | "review" | "blocked"
    message: str
    where: str = ""                     # node id or source ref

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProjectModel:
    """The whole job: site metadata + every node + validation flags."""

    project_id: str = ""
    store: str = ""
    title: str = "Singh360 EMS Project"
    nodes: dict[str, Node] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)   # files consumed

    # ---- mutation helpers ------------------------------------------------
    def add_node(self, node: Node) -> Node:
        existing = self.nodes.get(node.id)
        if existing:
            # Merge: keep established values, fill blanks, append points.
            for k, v in node.attrs.items():
                if v:
                    existing.attrs.setdefault(k, v)
            if node.parent and not existing.parent:
                existing.parent = node.parent
            existing.points.extend(node.points)
            if node.source and node.source not in existing.source:
                existing.source = (existing.source + "; " + node.source).strip("; ")
            return existing
        self.nodes[node.id] = node
        return node

    def add_point(self, node_id: str, point: IOPoint) -> None:
        node = self.nodes.get(node_id)
        if node is None:
            self.flag("review", f"point '{point.label}' references unknown node {node_id}", node_id)
            return
        node.points.append(point)

    def flag(self, level: str, message: str, where: str = "") -> None:
        self.flags.append(Flag(level=level, message=message, where=where))

    def note_source(self, path: str) -> None:
        if path and path not in self.sources:
            self.sources.append(path)

    # ---- queries ---------------------------------------------------------
    def children(self, node_id: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.parent == node_id]

    def by_kind(self, kind: NodeKind) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind == kind]

    def roots(self) -> list[Node]:
        return [n for n in self.nodes.values() if not n.parent or n.parent not in self.nodes]

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for n in self.nodes.values():
            kinds[n.kind.value] = kinds.get(n.kind.value, 0) + 1
        points = sum(len(n.points) for n in self.nodes.values())
        return {
            "project_id": self.project_id,
            "store": self.store,
            "nodes": len(self.nodes),
            "points": points,
            "by_kind": kinds,
            "flags": len(self.flags),
            "sources": len(self.sources),
        }

    # ---- serialization ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "store": self.store,
            "title": self.title,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "flags": [f.to_dict() for f in self.flags],
            "sources": list(self.sources),
            "summary": self.summary(),
        }

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "ProjectModel":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        m = cls(
            project_id=data.get("project_id", ""),
            store=data.get("store", ""),
            title=data.get("title", "Singh360 EMS Project"),
            sources=list(data.get("sources", [])),
        )
        for nid, nd in data.get("nodes", {}).items():
            points = [
                IOPoint(
                    kind=PointKind(p["kind"]),
                    label=p.get("label", ""),
                    point_no=p.get("point_no", ""),
                    loc_type=p.get("loc_type", ""),
                    signal=p.get("signal", ""),
                    cable=p.get("cable", ""),
                    load=p.get("load", ""),
                    value=p.get("value", ""),
                    units=p.get("units", ""),
                    source=p.get("source", ""),
                )
                for p in nd.get("points", [])
            ]
            m.nodes[nid] = Node(
                id=nd["id"],
                kind=NodeKind(nd["kind"]),
                name=nd.get("name", ""),
                parent=nd.get("parent"),
                attrs=dict(nd.get("attrs", {})),
                points=points,
                source=nd.get("source", ""),
            )
        for f in data.get("flags", []):
            m.flags.append(Flag(level=f.get("level", "info"), message=f.get("message", ""), where=f.get("where", "")))
        return m


def slug(*parts: str) -> str:
    """Stable node id from parts (e.g. slug('rack','A') -> 'rack:a')."""
    cleaned = [str(p).strip().lower().replace(" ", "-") for p in parts if str(p).strip()]
    return ":".join(cleaned)
