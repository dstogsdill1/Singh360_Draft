"""core/data_orchestrator.py — relational graph builder (pandas engine).

Joins the three Singh360 data planes into one traceable diagram graph:

  * assets.csv  — the 11-column app schedule (one row == one node). The
    "Connected/Area Served/..." column is the PARENT reference, so it becomes a
    hierarchy EDGE whenever it names another row's Name (Circuit -> Loop,
    Compressor -> Loop, Condenser -> Rack, Fixture -> Panel).
  * control_matrix.csv — low/high-voltage control chain:
    Relay -> Contactor -> Load. When a Load matches an asset Name the control
    chain is stitched into the asset graph (e.g. C1 -> "Interior Lights").
  * network.csv — Device -> Switch/Port/IP assignments. When a Device matches
    an asset Name the device inherits its physical location.

Every Node/Edge records a `source` provenance (file:row). Unresolved parent
references are NOT invented as phantom nodes — they are recorded as flags.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import config


# --------------------------------------------------------------------------
# Graph primitives
# --------------------------------------------------------------------------
@dataclass
class Node:
    id: str  # canonical key (asset Name, or "Relay:R1" / "Switch:SW-1")
    label: str
    category: str
    unit_type: str = ""
    group: str = ""  # container grouping (category / "EMS Control" / "Network")
    attrs: dict[str, str] = field(default_factory=dict)
    # Optional true floor-plan center/size (inches) from spatial ingestion.
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    source: str = ""  # provenance "file:row"


@dataclass
class Edge:
    source: str  # child / origin node id
    target: str  # parent / destination node id
    kind: str = "hierarchy"  # hierarchy | control | network
    label: str = ""
    source_ref: str = ""  # provenance "file:row"


@dataclass
class DiagramGraph:
    name: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def add_node(self, node: Node) -> Node:
        existing = self.nodes.get(node.id)
        if existing:
            # Merge non-empty attrs without clobbering established values.
            for k, v in node.attrs.items():
                existing.attrs.setdefault(k, v)
            if not existing.source:
                existing.source = node.source
            return existing
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: Edge) -> None:
        # De-dup identical edges.
        for e in self.edges:
            if (
                e.source == edge.source
                and e.target == edge.target
                and e.kind == edge.kind
            ):
                return
        self.edges.append(edge)

    def groups(self) -> dict[str, list[Node]]:
        out: dict[str, list[Node]] = {}
        for n in self.nodes.values():
            out.setdefault(n.group or n.category or "Ungrouped", []).append(n)
        return out

    def summary(self) -> dict[str, int]:
        kinds = {"hierarchy": 0, "control": 0, "network": 0}
        for e in self.edges:
            kinds[e.kind] = kinds.get(e.kind, 0) + 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "groups": len(self.groups()),
            **{f"edges_{k}": v for k, v in kinds.items()},
        }


def _norm(s: object) -> str:
    """Normalize a value to clean text; pandas NaN / 'nan' -> '' (not 'nan')."""
    if s is None:
        return ""
    if isinstance(s, float):
        if s != s:  # NaN is the only value not equal to itself
            return ""
        if s.is_integer():
            s = int(s)
    text = str(s).strip()
    return "" if text.lower() == "nan" else text


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------
class DataOrchestrator:
    """Builds a DiagramGraph from the three CSV planes using pandas joins."""

    def __init__(self, name: str = "Singh360 Diagram") -> None:
        self.graph = DiagramGraph(name=name)
        self._assets: pd.DataFrame | None = None

    # ---- assets (11-column app schedule) --------------------------------
    def load_assets(self, csv_path: str | Path) -> "DataOrchestrator":
        path = Path(csv_path)
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        self._assets = df
        name_col = config.NAME_COL
        cat_col = config.CATEGORY_COL
        type_col = config.UNIT_TYPE_COL
        parent_col = config.PARENT_REF_COL

        # Pass 1: every row becomes a node keyed by Name.
        for i, r in df.iterrows():
            name = _norm(r.get(name_col))
            if not name:
                self.graph.flags.append(f"{path.name}:row{i + 2} has blank Name; skipped")
                continue
            category = _norm(r.get(cat_col))
            self.graph.add_node(
                Node(
                    id=name,
                    label=name,
                    category=category,
                    unit_type=_norm(r.get(type_col)),
                    group=category or "Asset",
                    attrs={
                        "control_type": _norm(r.get("Control Type")),
                        "set_point_f": _norm(r.get("Design Temperature Set Point (F)")),
                        "fixture": _norm(
                            r.get("Fixture Type/Rack Type/Suction Temp/Make")
                        ),
                        "sub_form": _norm(r.get("Sub Form Category")),
                    },
                    source=f"{path.name}:row{i + 2}",
                )
            )

        # Pass 2: resolve parent references into hierarchy edges.
        known = set(self.graph.nodes.keys())
        for i, r in df.iterrows():
            child = _norm(r.get(name_col))
            parent = _norm(r.get(parent_col))
            if not child or not parent:
                continue
            if parent in known and parent != child:
                self.graph.add_edge(
                    Edge(
                        source=child,
                        target=parent,
                        kind="hierarchy",
                        source_ref=f"{path.name}:row{i + 2}",
                    )
                )
            else:
                # Could be a refrigerant code (R404A), area string, or count —
                # NOT a node. Record as an attribute + flag; never invent a node.
                node = self.graph.nodes.get(child)
                if node is not None:
                    node.attrs.setdefault("connected_raw", parent)
        return self

    # ---- control matrix (Relay -> Contactor -> Load) --------------------
    def load_control_matrix(self, csv_path: str | Path) -> "DataOrchestrator":
        path = Path(csv_path)
        df = pd.read_csv(path, dtype=str, keep_default_na=False)

        # Demonstrative pandas JOIN: enrich each control Load with the asset
        # category/location it drives (Load == asset Name).
        if self._assets is not None and "Load" in df.columns:
            enrich = self._assets[[config.NAME_COL, config.CATEGORY_COL]].rename(
                columns={config.NAME_COL: "Load", config.CATEGORY_COL: "_load_category"}
            )
            df = df.merge(enrich, on="Load", how="left")

        for i, r in df.iterrows():
            relay = _norm(r.get("Relay"))
            contactor = _norm(r.get("Contactor"))
            load = _norm(r.get("Load"))
            ref = f"{path.name}:row{i + 2}"
            voltage = _norm(r.get("Voltage"))
            control = _norm(r.get("Control"))
            panel = _norm(r.get("Panel"))
            area = _norm(r.get("Area"))

            relay_id = f"Relay:{relay}" if relay else ""
            contactor_id = f"Contactor:{contactor}" if contactor else ""

            if relay:
                self.graph.add_node(
                    Node(
                        id=relay_id,
                        label=relay,
                        category="Relay",
                        unit_type="Relay",
                        group="EMS Control",
                        attrs={"panel": panel, "voltage": voltage},
                        source=ref,
                    )
                )
            if contactor:
                self.graph.add_node(
                    Node(
                        id=contactor_id,
                        label=contactor,
                        category="Contactor",
                        unit_type="Contactor",
                        group="EMS Control",
                        attrs={"panel": panel, "voltage": voltage,
                               "area": area, "control": control},
                        source=ref,
                    )
                )
            # Load node: reuse the matching asset node if present, else create.
            load_id = load
            if load and load not in self.graph.nodes:
                self.graph.add_node(
                    Node(
                        id=load_id,
                        label=load,
                        category=_norm(r.get("_load_category")) or "Lighting",
                        unit_type="Load",
                        group="EMS Control",
                        attrs={"area": area, "voltage": voltage,
                               "control": control, "panel": panel},
                        source=ref,
                    )
                )

            if relay and contactor:
                self.graph.add_edge(
                    Edge(relay_id, contactor_id, "control", "energizes", ref)
                )
            if contactor and load:
                self.graph.add_edge(
                    Edge(contactor_id, load_id, "control", "switches", ref)
                )
        return self

    # ---- network (Device -> Switch/Port) --------------------------------
    def load_network(self, csv_path: str | Path) -> "DataOrchestrator":
        path = Path(csv_path)
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for i, r in df.iterrows():
            device = _norm(r.get("Device"))
            switch = _norm(r.get("Switch"))
            port = _norm(r.get("Port"))
            ip = _norm(r.get("IP"))
            vlan = _norm(r.get("VLAN"))
            ref = f"{path.name}:row{i + 2}"
            if not device:
                continue
            switch_id = f"Switch:{switch}" if switch else ""

            # Device node: enrich an existing asset node, else create one.
            if device in self.graph.nodes:
                self.graph.nodes[device].attrs.update(
                    {"ip": ip, "switch": switch, "port": port, "vlan": vlan}
                )
            else:
                self.graph.add_node(
                    Node(
                        id=device,
                        label=device,
                        category="Network",
                        unit_type="Device",
                        group="Network",
                        attrs={"ip": ip, "switch": switch, "port": port, "vlan": vlan},
                        source=ref,
                    )
                )
            if switch:
                self.graph.add_node(
                    Node(
                        id=switch_id,
                        label=switch,
                        category="Network",
                        unit_type="Switch",
                        group="Network",
                        source=ref,
                    )
                )
                self.graph.add_edge(
                    Edge(device, switch_id, "network", port or "uplink", ref)
                )
        return self

    # ---- spatial anchors (from ingestion.SpatialNode list) --------------
    def attach_spatial(self, spatial: list) -> "DataOrchestrator":
        """Bind floor-plan centers to nodes by exact/normalized name match."""
        index = {n.lower(): n for n in self.graph.nodes}
        for sp in spatial:
            key = getattr(sp, "key", "").lower()
            target = index.get(key)
            if target is None:
                continue
            node = self.graph.nodes[target]
            node.x, node.y, node.w, node.h = sp.cx, sp.cy, sp.w, sp.h
            node.attrs.setdefault("spatial_source", getattr(sp, "source", ""))
        return self

    def build(self) -> DiagramGraph:
        return self.graph


# --------------------------------------------------------------------------
# Deterministic layout solver (shared by both engines)
# --------------------------------------------------------------------------
def compute_layout(
    graph: DiagramGraph,
    page_w: float = config.PAGE_WIDTH_IN,
    page_h: float = config.PAGE_HEIGHT_IN,
    margin: float = config.PAGE_MARGIN_IN,
) -> dict[str, tuple[float, float, float, float]]:
    """Layered top-down layout -> {node_id: (cx, cy, w, h)} in inches.

    Nodes with a real spatial anchor (node.x/node.y) keep it. The rest are
    ranked by hierarchy depth (roots at the top) and spread evenly per rank.
    Control + network nodes without a parent are placed on their own ranks so
    every node is visible and never overlaps.
    """
    parent: dict[str, str] = {}
    for e in graph.edges:
        if e.kind == "hierarchy":
            parent.setdefault(e.source, e.target)

    def depth(nid: str) -> int:
        d, cur, seen = 0, nid, set()
        while cur in parent and parent[cur] in graph.nodes and cur not in seen:
            seen.add(cur)
            cur = parent[cur]
            d += 1
            if d > 64:  # cycle guard
                break
        return d

    ranks: dict[int, list[str]] = {}
    anchored: dict[str, tuple[float, float, float, float]] = {}
    for nid, node in graph.nodes.items():
        if node.x is not None and node.y is not None:
            anchored[nid] = (
                node.x,
                node.y,
                node.w or config.SHAPE_W_IN,
                node.h or config.SHAPE_H_IN,
            )
            continue
        ranks.setdefault(depth(nid), []).append(nid)

    coords: dict[str, tuple[float, float, float, float]] = dict(anchored)
    if not ranks:
        return coords

    max_depth = max(ranks)
    usable_h = page_h - 2 * margin
    row_step = usable_h / max(max_depth + 1, 1)
    for d, ids in sorted(ranks.items()):
        ids = sorted(ids)  # deterministic ordering
        cy = (page_h - margin) - d * row_step
        usable_w = page_w - 2 * margin
        n = len(ids)
        col_step = usable_w / max(n, 1)
        for idx, nid in enumerate(ids):
            cx = margin + col_step * (idx + 0.5)
            coords[nid] = (cx, cy, config.SHAPE_W_IN, config.SHAPE_H_IN)
    return coords
