"""engines/smartdraw_vson.py — SmartDraw VisualScript (VSON) compiler.

Builds a hierarchical VisualScript document that mirrors the SmartDraw SDK
object model referenced in the project brief:

    VS.Document()  ->  VSDocument
    VS.Shape()     ->  VSShape          (auto-sizes to text via TextGrow)
    VS.ShapeConnector() -> VSConnector   (data-driven, auto-routed)
    VS.ShapeContainer() -> VSContainer   (groups a category / sub-system)

Layout strategy: we DO NOT hand-place shapes with absolute math. We emit an
`autoLayout` directive plus per-shape `TextGrow` so SmartDraw's router sizes
and arranges the diagram. Computed (cx,cy) hints from core.compute_layout are
attached as `hint` only — SmartDraw may honor or override them.

NOTE / FLAG (no hallucination): SmartDraw's public VisualScript JSON page was
not reachable at build time, so the exact wire field names should be validated
against the live SmartDraw VisualScript SDK / import endpoint for the target
account. The structure here is internally consistent, fully documented, and
round-trips through `validate()`; treat key names as the integration contract
to confirm, not as a vendor-published guarantee.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import config
from core.data_orchestrator import DiagramGraph, compute_layout

VSON_SCHEMA_VERSION = "1.0"


@dataclass
class VSShape:
    """A VisualScript shape. Auto-sizes to its text via `text_grow`."""

    id: str
    text: str
    category: str = ""
    fill: str = "#D0D7DE"
    line: str = "#57606A"
    text_color: str = "#1A1A1A"
    shape_kind: str = "rectangle"
    text_grow: str = "GrowBoth"  # GrowVertical | GrowHorizontal | GrowBoth
    # Custom tracking data embedded directly on the shape (Singh360 asset meta).
    data: list[dict[str, str]] = field(default_factory=list)
    hint: dict[str, float] | None = None  # optional {x,y,w,h} layout hint
    source: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "text": self.text,
            "category": self.category,
            "style": {
                "fillColor": self.fill,
                "lineColor": self.line,
                "textColor": self.text_color,
                "shape": self.shape_kind,
            },
            "textGrow": self.text_grow,
            "data": self.data,
        }
        if self.hint:
            d["hint"] = self.hint
        if self.source:
            d["meta"] = {"source": self.source}
        return d


@dataclass
class VSConnector:
    """A VisualScript connector (auto-routed by SmartDraw)."""

    id: str
    source: str
    target: str
    label: str = ""
    kind: str = "hierarchy"
    line: str = "#57606A"
    pattern: str = "solid"  # solid | dash | dot

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.source,
            "to": self.target,
            "text": self.label,
            "kind": self.kind,
            "style": {"lineColor": self.line, "linePattern": self.pattern},
            "routing": "auto",
        }


@dataclass
class VSContainer:
    """A VisualScript container grouping member shape ids."""

    id: str
    title: str
    members: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "members": list(self.members)}


@dataclass
class VSDocument:
    title: str
    layout: str = "hierarchy"  # SmartDraw auto-layout family
    shapes: list[VSShape] = field(default_factory=list)
    connectors: list[VSConnector] = field(default_factory=list)
    containers: list[VSContainer] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "visualScript": {
                "version": VSON_SCHEMA_VERSION,
                "generator": "Singh360_SmartDraw",
                "document": {
                    "title": self.title,
                    "autoLayout": {"type": self.layout, "direction": "down"},
                    "shapes": [s.to_dict() for s in self.shapes],
                    "connectors": [c.to_dict() for c in self.connectors],
                    "containers": [c.to_dict() for c in self.containers],
                },
                "meta": {
                    "traceability": {s.id: s.source for s in self.shapes if s.source},
                    "flags": self.flags,
                },
            }
        }


class VsonGenerator:
    """Compiles a DiagramGraph into a VSDocument."""

    def __init__(self, layout: str = "hierarchy") -> None:
        self.layout = layout

    def from_graph(self, graph: DiagramGraph) -> VSDocument:
        doc = VSDocument(title=graph.name, layout=self.layout, flags=list(graph.flags))
        hints = compute_layout(graph)

        for nid, node in graph.nodes.items():
            style = config.style_for(node.category)
            # Embed the asset's non-empty attributes as tracking data rows.
            data_rows = [
                {"label": k, "value": v} for k, v in node.attrs.items() if v
            ]
            if node.unit_type:
                data_rows.insert(0, {"label": "Unit/Type", "value": node.unit_type})
            data_rows.insert(0, {"label": "Category", "value": node.category})

            hint = None
            if nid in hints:
                cx, cy, w, h = hints[nid]
                hint = {"x": round(cx, 3), "y": round(cy, 3), "w": round(w, 3), "h": round(h, 3)}

            doc.shapes.append(
                VSShape(
                    id=nid,
                    text=node.label,
                    category=node.category,
                    fill=style.fill,
                    line=style.line,
                    text_color=style.text,
                    shape_kind=style.shape_kind,
                    text_grow="GrowBoth",
                    data=data_rows,
                    hint=hint,
                    source=node.source,
                )
            )

        for i, e in enumerate(graph.edges):
            est = config.EDGE_STYLES.get(e.kind, config.EDGE_STYLES["hierarchy"])
            doc.connectors.append(
                VSConnector(
                    id=f"c{i + 1}",
                    source=e.source,
                    target=e.target,
                    label=e.label,
                    kind=e.kind,
                    line=est["line"],
                    pattern=est["pattern"],
                )
            )

        for title, members in graph.groups().items():
            doc.containers.append(
                VSContainer(
                    id=f"grp::{title}",
                    title=title,
                    members=[m.id for m in members],
                )
            )
        return doc

    def render(self, graph: DiagramGraph, out_path: str | Path) -> Path:
        doc = self.from_graph(graph)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(doc.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return out_path


def validate(vson_path: str | Path) -> tuple[bool, list[str]]:
    """Internal-consistency check: valid JSON, unique ids, resolvable edges.

    This validates the document is well-formed and self-referential, NOT that
    field names match the live SmartDraw endpoint (see module flag).
    """
    problems: list[str] = []
    data = json.loads(Path(vson_path).read_text(encoding="utf-8"))
    try:
        doc = data["visualScript"]["document"]
    except (KeyError, TypeError):
        return False, ["missing visualScript.document root"]

    ids = [s.get("id") for s in doc.get("shapes", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate shape ids present")
    idset = set(ids)
    for c in doc.get("connectors", []):
        if c.get("from") not in idset:
            problems.append(f"connector {c.get('id')} from-id not found: {c.get('from')}")
        if c.get("to") not in idset:
            problems.append(f"connector {c.get('id')} to-id not found: {c.get('to')}")
    return (len(problems) == 0), problems
