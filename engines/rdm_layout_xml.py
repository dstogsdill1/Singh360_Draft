"""engines/rdm_layout_xml.py — deterministic RDM-oriented XML package writer.

This target emits a neutral, traceable XML representation suitable for
Layout-Editor style workflows when an official on-disk vendor schema is not
available in the install tree.

Design goals:
- deterministic ordering (stable output for identical inputs)
- no hallucinations (unknown values stay blank/missing, never invented)
- full provenance (`source`, `source_ref`) for every serialized object
- explicit symbol/library hints derived from discovered RDM image libraries
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import config
from core.data_orchestrator import DiagramGraph, compute_layout

RDM_INSTALL_ROOT = r"C:\Program Files (x86)\RDM Layout Editor 3"

# Deterministic symbol hinting only (metadata), never a hard dependency.
_SYMBOL_HINTS = {
    "lighting": "Images/Light/light.gif",
    "relay": "Library/Pictures/GPDevices/gp_on.png",
    "contactor": "Library/Pictures/GPDevices/twoway_on.png",
    "network": "Library/Pictures/GPDevices/slide_base.png",
    "panel": "Library/Pictures/GPDevices/slide.png",
    "rack": "Images/Refrigeration/PR0282 Pack.png",
    "compressor": "Images/Refrigeration/Compressor.gif",
    "tank": "Images/Tank/tank.gif",
    "ahu": "Images/AHU/Fans.gif",
}


class RdmLayoutXmlGenerator:
    """Compile a DiagramGraph into a deterministic RDM-style XML package."""

    def __init__(
        self,
        page_w: float = config.PAGE_WIDTH_IN,
        page_h: float = config.PAGE_HEIGHT_IN,
        layout_fn=None,
    ) -> None:
        self.page_w = page_w
        self.page_h = page_h
        self.layout_fn = layout_fn or compute_layout

    def render(self, graph: DiagramGraph, out_path: str | Path) -> Path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        coords = self.layout_fn(graph, self.page_w, self.page_h)

        root = ET.Element(
            "RdmLayoutPackage",
            {
                "version": "1.0",
                "profile": "neutral",
                "generator": "Singh360_SmartDraw",
            },
        )

        ET.SubElement(
            root,
            "Metadata",
            {
                "name": graph.name,
                "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "coordinate_units": "in",
                "page_width_in": f"{self.page_w:.4f}",
                "page_height_in": f"{self.page_h:.4f}",
                "rdm_install_root": RDM_INSTALL_ROOT,
                "notes": "Neutral XML target; validate vendor dialect before production import.",
            },
        )

        hints = ET.SubElement(root, "LibraryHints")
        for k, rel in sorted(_SYMBOL_HINTS.items()):
            ET.SubElement(
                hints,
                "Hint",
                {
                    "category_key": k,
                    "relative_path": rel,
                    "absolute_path": str(Path(RDM_INSTALL_ROOT) / rel),
                },
            )

        nodes_el = ET.SubElement(root, "Nodes")
        for nid in sorted(graph.nodes):
            n = graph.nodes[nid]
            cx, cy, w, h = coords.get(
                nid,
                (self.page_w / 2, self.page_h / 2, config.SHAPE_W_IN, config.SHAPE_H_IN),
            )
            hint = _symbol_hint(n.category, n.unit_type, n.group)
            node_el = ET.SubElement(
                nodes_el,
                "Node",
                {
                    "id": n.id,
                    "label": n.label or "",
                    "category": n.category or "",
                    "unit_type": n.unit_type or "",
                    "group": n.group or "",
                    "source": n.source or "",
                    "x_in": f"{cx:.4f}",
                    "y_in": f"{cy:.4f}",
                    "w_in": f"{w:.4f}",
                    "h_in": f"{h:.4f}",
                    "symbol_hint": hint,
                },
            )
            attrs_el = ET.SubElement(node_el, "Attributes")
            for k, v in sorted(n.attrs.items()):
                if v is None:
                    continue
                ET.SubElement(attrs_el, "Attribute", {"name": k, "value": str(v)})

        edges_el = ET.SubElement(root, "Edges")
        for e in sorted(
            graph.edges,
            key=lambda x: (
                x.kind or "",
                x.source or "",
                x.target or "",
                x.label or "",
                x.source_ref or "",
            ),
        ):
            ET.SubElement(
                edges_el,
                "Edge",
                {
                    "source": e.source,
                    "target": e.target,
                    "kind": e.kind or "",
                    "label": e.label or "",
                    "source_ref": e.source_ref or "",
                },
            )

        flags_el = ET.SubElement(root, "Flags")
        for fl in graph.flags:
            ET.SubElement(flags_el, "Flag", {"message": fl})

        ET.indent(root, space="  ")
        out.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode"),
            encoding="utf-8",
        )
        return out


def _symbol_hint(category: str, unit_type: str, group: str) -> str:
    hay = " ".join((category or "", unit_type or "", group or "")).lower()
    for key, rel in _SYMBOL_HINTS.items():
        if key in hay:
            return rel
    return ""


def validate(path: str | Path) -> tuple[bool, list[str]]:
    """Validate structural integrity of a neutral RDM XML package."""
    p = Path(path)
    problems: list[str] = []

    if not p.exists() or not p.is_file():
        return False, [f"missing file: {p}"]

    try:
        root = ET.fromstring(p.read_text(encoding="utf-8"))
    except Exception as ex:  # noqa: BLE001
        return False, [f"XML parse error: {ex}"]

    if root.tag != "RdmLayoutPackage":
        problems.append(f"root tag must be RdmLayoutPackage, got {root.tag!r}")

    meta = root.find("Metadata")
    if meta is None:
        problems.append("missing Metadata element")

    node_ids: set[str] = set()
    for n in root.findall("./Nodes/Node"):
        nid = (n.get("id") or "").strip()
        if not nid:
            problems.append("node with blank id")
            continue
        if nid in node_ids:
            problems.append(f"duplicate node id: {nid}")
        node_ids.add(nid)

    if not node_ids:
        problems.append("no nodes serialized")

    for e in root.findall("./Edges/Edge"):
        src = (e.get("source") or "").strip()
        dst = (e.get("target") or "").strip()
        if not src or not dst:
            problems.append("edge with blank source/target")
            continue
        if src not in node_ids:
            problems.append(f"edge source not found: {src}")
        if dst not in node_ids:
            problems.append(f"edge target not found: {dst}")

    return (len(problems) == 0), problems
