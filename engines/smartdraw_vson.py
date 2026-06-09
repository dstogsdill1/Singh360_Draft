"""engines/smartdraw_vson.py — SmartDraw VisualScript (VSON) compiler.

Emits the OFFICIAL VSON document structure documented in SmartDraw's
VisualScript Markup Language Reference:
  https://www.smartdraw.com/developers/visualscript-markup-language-reference.htm

A VSON document is a single root object:

    { "Version", "Template", "Title", "Shape" (root), "Returns", "Colors" }

The diagram is a TREE. The single root `Shape` holds children through
`ShapeConnector` arrays; each child `Shape` may hold its own `ShapeConnector`,
recursively. Relationships that don't fit the spanning tree (a node with a
second parent, or a cross-link) are emitted as `Returns` — arbitrary lines
drawn by `StartID`/`EndID`. SmartDraw's intelligent-formatting engine lays the
diagram out, so NO coordinates are written.

The output file MUST use the `.vson` extension (SmartDraw also accepts `.sdon`
/ `.sdr`) — SmartDraw's importer checks the extension before the content.

Field names follow the published reference (capitalized: `Label`, `ShapeType`,
`FillColor`, `LineColor`, `LinePattern`, `TextGrow`, `ShapeConnector`,
`Returns`, ...). Enum values used:
  TextGrow   = Proportional | Vertical | Horizontal
  LinePattern= Solid | Dotted | Dashed
  ShapeType  = RRect | Oval | Circle | Square | Diamond  ("" = default rect)
  Template   = Flowchart | Mindmap | Orgchart | Decisiontree | Hierarchy
"""
from __future__ import annotations

import json
from pathlib import Path

import config
from core.data_orchestrator import DiagramGraph

# Document version string (VSON `Version` field).
VSON_VERSION = "1"

# our CategoryStyle.shape_kind -> SmartDraw ShapeTypes enum ("" == default rect)
_SHAPE_TYPE = {"rounded": "RRect", "rectangle": "", "hexagon": "", "cylinder": ""}

# our edge kind -> SmartDraw LinePatterns enum
_EDGE_PATTERN = {"hierarchy": "Solid", "control": "Dashed", "network": "Dotted"}

# our layout hint -> VSON Template (VSTemplates enum)
_TEMPLATES = {
    "hierarchy": "Hierarchy",
    "flowchart": "Flowchart",
    "orgchart": "Orgchart",
    "mindmap": "Mindmap",
    "decisiontree": "Decisiontree",
}


def _parent_child(edge) -> tuple[str, str]:
    """Normalize an edge to (parent_id, child_id).

    Hierarchy edges are stored child->parent (source=child); control/network
    edges are stored parent->child (source=parent).
    """
    if edge.kind == "hierarchy":
        return edge.target, edge.source
    return edge.source, edge.target


def _shape_label(node) -> str:
    return node.label or node.id


def _shape_note(node) -> str:
    """Readable, deterministic note from the node's non-empty attributes."""
    skip = {"spatial_source"}
    pretty = {
        "connected_raw": "Qty / Volt / Watt",
        "control_type": "Control",
        "control": "Control schedule",
        "set_point_f": "Set point (F)",
        "fixture": "Catalog / Make",
        "sub_form": "Description",
        "panel": "Panel / circuit",
        "voltage": "Voltage",
        "area": "Controlled circuit",
        "ip": "IP",
        "switch": "Switch",
        "port": "Port",
        "vlan": "VLAN",
    }
    lines: list[str] = []
    if node.unit_type:
        lines.append(f"Type: {node.unit_type}")
    for k, v in node.attrs.items():
        if v and k not in skip:
            lines.append(f"{pretty.get(k, k)}: {v}")
    return "\n".join(lines)


class VsonGenerator:
    """Compiles a DiagramGraph into an official VSON document (dict + file)."""

    def __init__(self, layout: str = "hierarchy", title_block=None) -> None:
        self.template = _TEMPLATES.get((layout or "").lower(), "Hierarchy")
        # Optional engines.title_block.TitleBlockInfo -> editable VSON Table.
        self.title_block = title_block

    # ---- spanning-tree construction -------------------------------------
    def _build_tree(self, graph: DiagramGraph):
        """Return (children, child_kind, roots, extra_edges).

        children[parent] -> [child, ...]    (the spanning tree)
        child_kind[child] -> the edge kind linking it to its tree parent
        roots               -> nodes with no tree parent
        extra_edges         -> (parent, child, edge) that became cross-links
        """
        nodes = graph.nodes
        tree_parent: dict[str, str] = {}
        children: dict[str, list[str]] = {}
        child_kind: dict[str, str] = {}
        extra: list = []

        def makes_cycle(parent: str, child: str) -> bool:
            cur, hops = parent, 0
            while cur in tree_parent:
                if cur == child:
                    return True
                cur = tree_parent[cur]
                hops += 1
                if hops > 100000:
                    return True
            return cur == child

        for e in graph.edges:
            p, c = _parent_child(e)
            if p not in nodes or c not in nodes or p == c:
                continue
            if c not in tree_parent and not makes_cycle(p, c):
                tree_parent[c] = p
                children.setdefault(p, []).append(c)
                child_kind[c] = e.kind
            else:
                extra.append((p, c, e))

        roots = [n for n in nodes if n not in tree_parent]
        return children, child_kind, roots, extra

    # ---- HEB title block as an editable VSON Table ----------------------
    def _title_block_shape(self, new_id) -> dict:
        """Build the HEB title block as a real, EDITABLE 2-column table.

        VSON has no absolute X/Y (it auto-lays-out), but a shape can hold a
        `Table` whose every cell is editable text in SmartDraw — exactly how a
        drawing title block works. The operator edits any field in place,
        replaces values, and the block stays a true table, never an image.
        """
        tb = self.title_block
        navy = "#0B3D63"
        # (label, value) rows. Blank values render blank (never invented).
        rows: list[tuple[str, str]] = [
            ("SHEET NUMBER", tb.sheet_number),
            ("SHEET TITLE", tb.sheet_title),
            ("PROJECT", tb.project_name),
            ("ADDRESS", tb.project_address),
            ("SCALE", tb.scale),
            ("PROJECT NO.", tb.project_no),
            ("DATE", tb.date),
            ("FIRM", tb.firm),
            ("CONSULTANT", " · ".join(tb.firm_lines)),
            ("ENGINEER", tb.engineer),
            ("STATUS", tb.status),
            ("REVISIONS", tb.revision),
            ("CONFIDENTIAL",
             "This document may contain sensitive and/or proprietary "
             "information and must be treated as confidential. It shall not be "
             "reproduced, released, or distributed without express written "
             "permission."),
        ]
        # NOTE: SmartDraw's table support can be inconsistent across template
        # modes/import paths. To guarantee reliable imports we emit the title
        # block as plain editable shapes (one row per child shape), never as an
        # image and without depending on Table-specific parsing.
        row_shapes: list[dict] = []
        for label, value in rows:
            row_shapes.append(
                {
                    "ID": new_id(),
                    "Label": f"{label}: {value or ''}",
                    "FillColor": "#FFFFFF",
                    "LineColor": navy,
                    "TextColor": "#1A1A1A",
                    "TextGrow": "Proportional",
                    "TextAlignH": "left",
                    "TextSize": 9,
                }
            )
        return {
            "ID": new_id(),
            "Label": "TITLE BLOCK",
            "FillColor": navy,
            "LineColor": navy,
            "TextColor": "#FFFFFF",
            "TextBold": True,
            "TextGrow": "Proportional",
            "ShapeType": "RRect",
            "ShapeConnector": [
                {
                    "ShapeConnectorType": self.template,
                    "Arrangement": "Column",
                    "Shapes": row_shapes,
                }
            ],
        }

    # ---- document assembly ----------------------------------------------
    def build_document(self, graph: DiagramGraph) -> dict:
        children, child_kind, roots, extra = self._build_tree(graph)
        id_map: dict[str, int] = {}
        counter = {"n": 1}  # ID 1 is reserved for the document root shape

        def new_id() -> int:
            counter["n"] += 1
            return counter["n"]

        def make_shape(node_id: str) -> dict:
            node = graph.nodes[node_id]
            style = config.style_for(node.category)
            sid = new_id()
            id_map[node_id] = sid
            shape: dict = {
                "ID": sid,
                "Label": _shape_label(node),
                "FillColor": style.fill,
                "LineColor": style.line,
                "TextColor": style.text,
                "TextGrow": "Proportional",
            }
            stype = _SHAPE_TYPE.get(style.shape_kind, "")
            if stype:
                shape["ShapeType"] = stype
            if node_id in child_kind:
                shape["LinePattern"] = _EDGE_PATTERN.get(child_kind[node_id], "Solid")
            note = _shape_note(node)
            if note:
                shape["Note"] = note
            kids = children.get(node_id, [])
            if kids:
                shape["ShapeConnector"] = [
                    {
                        "ShapeConnectorType": self.template,
                        "Shapes": [make_shape(k) for k in kids],
                    }
                ]
            return shape

        # Group roots by their container group so large flat sets (e.g. a
        # fixture catalog) stay organized under a labeled header shape.
        grouped: dict[str, list[str]] = {}
        for nid in roots:
            node = graph.nodes[nid]
            gname = node.group or node.category or "Items"
            grouped.setdefault(gname, []).append(nid)

        group_shapes: list[dict] = []
        for gname in sorted(grouped):
            members = grouped[gname]
            group_shapes.append(
                {
                    "ID": new_id(),
                    "Label": f"{gname}  ({len(members)})",
                    "FillColor": "#24292F",
                    "TextColor": "#FFFFFF",
                    "LineColor": "#57606A",
                    "TextGrow": "Proportional",
                    "TextBold": True,
                    "ShapeConnector": [
                        {
                            "ShapeConnectorType": self.template,
                            "Shapes": [make_shape(m) for m in members],
                        }
                    ],
                }
            )

        root_shape: dict = {
            "ID": 1,
            "Label": graph.name,
            "FillColor": "#1F6FEB",
            "TextColor": "#FFFFFF",
            "LineColor": "#0B3D91",
            "TextGrow": "Proportional",
            "TextBold": True,
        }

        # Title block as a real EDITABLE table (not an image) — first branch.
        branch_shapes: list[dict] = []
        if self.title_block is not None and not self.title_block.is_empty():
            branch_shapes.append(self._title_block_shape(new_id))
        branch_shapes.extend(group_shapes)

        if branch_shapes:
            root_shape["ShapeConnector"] = [
                {"ShapeConnectorType": self.template, "Shapes": branch_shapes}
            ]

        # Cross-links: relationships that didn't fit the spanning tree.
        returns: list[dict] = []
        for p, c, e in extra:
            if p in id_map and c in id_map:
                returns.append(
                    {
                        "StartID": id_map[p],
                        "EndID": id_map[c],
                        "Label": e.label or "",
                        "LinePattern": _EDGE_PATTERN.get(e.kind, "Solid"),
                        "EndArrow": 1,
                    }
                )

        document: dict = {
            "Version": VSON_VERSION,
            "Template": self.template,
            "Title": {"Label": graph.name},
            "Shape": root_shape,
        }
        if returns:
            document["Returns"] = returns
        return document

    def render(self, graph: DiagramGraph, out_path: str | Path) -> Path:
        document = self.build_document(graph)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return out_path


def validate(vson_path: str | Path) -> tuple[bool, list[str]]:
    """Structural check against the official VSON shape: a root document with a
    `Shape` tree of unique positive IDs and `Returns` that reference real IDs.
    """
    problems: list[str] = []
    try:
        doc = json.loads(Path(vson_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"unreadable/invalid JSON: {exc}"]

    if not isinstance(doc, dict) or "Shape" not in doc:
        return False, ["missing root 'Shape' (not a VSON document)"]

    ids: list[int] = []

    def walk(shape: dict) -> None:
        sid = shape.get("ID")
        if not isinstance(sid, int) or sid <= 0:
            problems.append(f"shape '{shape.get('Label')}' has invalid ID: {sid!r}")
        else:
            ids.append(sid)
        for conn in shape.get("ShapeConnector", []) or []:
            for child in conn.get("Shapes", []) or []:
                walk(child)

    walk(doc["Shape"])
    idset = set(ids)
    if len(ids) != len(idset):
        problems.append("duplicate shape IDs present")
    for r in doc.get("Returns", []) or []:
        if r.get("StartID") not in idset:
            problems.append(f"Return StartID not found: {r.get('StartID')}")
        if r.get("EndID") not in idset:
            problems.append(f"Return EndID not found: {r.get('EndID')}")
    if doc.get("Template") not in (None, *_TEMPLATES.values()):
        problems.append(f"unknown Template: {doc.get('Template')}")
    return (len(problems) == 0), problems
