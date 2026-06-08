"""engines/visio_vsdx.py — native Visio (.vsdx) package writer.

Builds a structurally valid Open Packaging Conventions container using only
the Python standard library (`zipfile`, `xml.etree.ElementTree`), per the
Microsoft .vsdx spec:
  [Content_Types].xml, _rels/.rels, docProps/*, visio/document.xml,
  visio/pages/pages.xml, visio/pages/page1.xml + their .rels parts.

Shapes are emitted with real ShapeSheet cells (PinX/PinY/Width/Height) and
rectangle Geometry; connectors are 1-D line shapes glued to their endpoints
with <Connect> rows (FromPart 9=begin / 12=end -> ToPart 3=whole shape). Exact
colors are written as RGB() formulas so they survive regardless of the document
color table.

.vssx masters: MasterLibrary can enumerate masters from a supplied stencil so
category styles may later bind to corporate shapes. When no stencil is given
(the default — no .vssx exists in this workspace) the writer falls back to
inline rectangle geometry. This is flagged, never silently approximated.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import config
from core.data_orchestrator import DiagramGraph, compute_layout

MAIN_NS = "http://schemas.microsoft.com/office/visio/2012/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Visio line-pattern indices for our edge kinds.
_LINE_PATTERN = {"solid": "1", "dash": "2", "dot": "9"}


def _hex_to_rgb(hexcolor: str) -> tuple[int, int, int]:
    h = (hexcolor or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0, 0, 0


def _color_cell(name: str, hexcolor: str) -> str:
    r, g, b = _hex_to_rgb(hexcolor)
    return f'<Cell N="{name}" V="{hexcolor}" F="RGB({r},{g},{b})"/>'


@dataclass
class _Placed:
    sid: int
    cx: float
    cy: float
    w: float
    h: float


class MasterLibrary:
    """Enumerates masters from a .vssx stencil (OPC zip). Optional."""

    def __init__(self, vssx_path: str | Path | None = None) -> None:
        self.path = Path(vssx_path) if vssx_path else None
        self.masters: dict[str, str] = {}  # NameU -> master id
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        with zipfile.ZipFile(self.path) as z:
            try:
                xml = z.read("visio/masters/masters.xml")
            except KeyError:
                return
        root = ET.fromstring(xml)
        for m in root.findall(f"{{{MAIN_NS}}}Master"):
            name = m.get("NameU") or m.get("Name") or ""
            mid = m.get("ID") or ""
            if name:
                self.masters[name] = mid

    def available(self) -> bool:
        return bool(self.masters)


class VsdxWriter:
    """Compiles a DiagramGraph into a .vsdx package."""

    def __init__(
        self,
        page_w: float = config.PAGE_WIDTH_IN,
        page_h: float = config.PAGE_HEIGHT_IN,
        master_library: MasterLibrary | None = None,
    ) -> None:
        self.page_w = page_w
        self.page_h = page_h
        self.masters = master_library
        self.flags: list[str] = []

    # ---- public API -----------------------------------------------------
    def write(self, graph: DiagramGraph, out_path: str | Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        coords = compute_layout(graph, self.page_w, self.page_h)
        # Assign stable integer sheet IDs (nodes first, then connectors).
        node_ids = list(graph.nodes.keys())
        id_map: dict[str, int] = {nid: i + 1 for i, nid in enumerate(node_ids)}
        placed: dict[str, _Placed] = {}
        for nid in node_ids:
            cx, cy, w, h = coords.get(
                nid, (self.page_w / 2, self.page_h / 2, config.SHAPE_W_IN, config.SHAPE_H_IN)
            )
            placed[nid] = _Placed(id_map[nid], cx, cy, w, h)

        if self.masters is None or not self.masters.available():
            self.flags.append(
                "No .vssx master library bound: using inline rectangle geometry."
            )

        page1 = self._page1_xml(graph, placed, id_map)

        parts = {
            "[Content_Types].xml": _CONTENT_TYPES,
            "_rels/.rels": _ROOT_RELS,
            "docProps/core.xml": _core_xml(graph.name),
            "docProps/app.xml": _APP_XML,
            "visio/document.xml": _DOCUMENT_XML,
            "visio/_rels/document.xml.rels": _DOCUMENT_RELS,
            "visio/pages/pages.xml": self._pages_xml(graph.name),
            "visio/pages/_rels/pages.xml.rels": _PAGES_RELS,
            "visio/pages/page1.xml": page1,
        }
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, content in parts.items():
                z.writestr(name, content)
        return out_path

    # ---- XML builders ---------------------------------------------------
    def _pages_xml(self, title: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Pages xmlns="{MAIN_NS}" xmlns:r="{REL_NS}" xml:space="preserve">'
            '<Page ID="0" NameU="Page-1" Name="Page-1" ViewScale="-1" '
            'ViewCenterX="0" ViewCenterY="0">'
            '<PageSheet>'
            f'<Cell N="PageWidth" V="{self.page_w}"/>'
            f'<Cell N="PageHeight" V="{self.page_h}"/>'
            '<Cell N="PageScale" V="1" U="IN"/>'
            '<Cell N="DrawingScale" V="1" U="IN"/>'
            '<Cell N="DrawingScaleType" V="0"/>'
            '<Cell N="InhibitSnap" V="0"/>'
            '</PageSheet>'
            '<Rel r:id="rId1"/>'
            '</Page></Pages>'
        )

    def _page1_xml(
        self,
        graph: DiagramGraph,
        placed: dict[str, _Placed],
        id_map: dict[str, int],
    ) -> str:
        shapes: list[str] = []
        connects: list[str] = []

        # Connectors first (drawn under node boxes).
        next_id = max(id_map.values(), default=0)
        for e in graph.edges:
            s = placed.get(e.source)
            t = placed.get(e.target)
            if not s or not t:
                continue
            next_id += 1
            cid = next_id
            bx, by, ex, ey = _attach_points(s, t)
            if abs(ex - bx) < 1e-6 and abs(ey - by) < 1e-6:
                continue
            est = config.EDGE_STYLES.get(e.kind, config.EDGE_STYLES["hierarchy"])
            pattern = _LINE_PATTERN.get(est["pattern"], "1")
            shapes.append(_connector_shape(cid, bx, by, ex, ey, est["line"], pattern, e.label))
            connects.append(
                f'<Connect FromSheet="{cid}" FromCell="BeginX" FromPart="9" '
                f'ToSheet="{s.sid}" ToCell="PinX" ToPart="3"/>'
            )
            connects.append(
                f'<Connect FromSheet="{cid}" FromCell="EndX" FromPart="12" '
                f'ToSheet="{t.sid}" ToCell="PinX" ToPart="3"/>'
            )

        # Node boxes on top.
        for nid, p in placed.items():
            node = graph.nodes[nid]
            style = config.style_for(node.category)
            shapes.append(
                _node_shape(
                    p.sid,
                    node.label,
                    p.cx,
                    p.cy,
                    p.w,
                    p.h,
                    style.fill,
                    style.line,
                    style.text,
                )
            )

        connects_xml = f"<Connects>{''.join(connects)}</Connects>" if connects else ""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<PageContents xmlns="{MAIN_NS}" xmlns:r="{REL_NS}" xml:space="preserve">'
            f"<Shapes>{''.join(shapes)}</Shapes>"
            f"{connects_xml}"
            '</PageContents>'
        )


def _attach_points(s: _Placed, t: _Placed) -> tuple[float, float, float, float]:
    """Trim a center-to-center segment to the shapes' box edges."""
    dx = t.cx - s.cx
    dy = t.cy - s.cy
    if abs(dy) >= abs(dx):  # mostly vertical
        by = s.cy + (s.h / 2 if dy > 0 else -s.h / 2)
        ey = t.cy + (-t.h / 2 if dy > 0 else t.h / 2)
        return s.cx, by, t.cx, ey
    bx = s.cx + (s.w / 2 if dx > 0 else -s.w / 2)
    ex = t.cx + (-t.w / 2 if dx > 0 else t.w / 2)
    return bx, s.cy, ex, t.cy


def _node_shape(
    sid: int,
    label: str,
    cx: float,
    cy: float,
    w: float,
    h: float,
    fill: str,
    line: str,
    text: str,
) -> str:
    return (
        f'<Shape ID="{sid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">'
        f'<Cell N="PinX" V="{cx:.4f}"/>'
        f'<Cell N="PinY" V="{cy:.4f}"/>'
        f'<Cell N="Width" V="{w:.4f}"/>'
        f'<Cell N="Height" V="{h:.4f}"/>'
        f'<Cell N="LocPinX" V="{w / 2:.4f}" F="Width*0.5"/>'
        f'<Cell N="LocPinY" V="{h / 2:.4f}" F="Height*0.5"/>'
        '<Cell N="Angle" V="0"/>'
        f'{_color_cell("FillForegnd", fill)}'
        '<Cell N="FillPattern" V="1"/>'
        f'{_color_cell("LineColor", line)}'
        '<Cell N="LineWeight" V="0.0104"/>'
        '<Cell N="Rounding" V="0.0625"/>'
        '<Section N="Character"><Row IX="0">'
        f'{_color_cell("Color", text)}'
        '<Cell N="Size" V="0.1111"/></Row></Section>'
        '<Section N="Geometry" IX="0">'
        '<Cell N="NoFill" V="0"/><Cell N="NoLine" V="0"/>'
        '<Row T="RelMoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
        '<Row T="RelLineTo" IX="2"><Cell N="X" V="1"/><Cell N="Y" V="0"/></Row>'
        '<Row T="RelLineTo" IX="3"><Cell N="X" V="1"/><Cell N="Y" V="1"/></Row>'
        '<Row T="RelLineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="1"/></Row>'
        '<Row T="RelLineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
        '</Section>'
        f'<Text>{escape(label)}</Text>'
        '</Shape>'
    )


def _connector_shape(
    cid: int,
    bx: float,
    by: float,
    ex: float,
    ey: float,
    line: str,
    pattern: str,
    label: str,
) -> str:
    w = ex - bx
    h = ey - by
    cx = (bx + ex) / 2
    cy = (by + ey) / 2
    text = f'<Text>{escape(label)}</Text>' if label else ""
    return (
        f'<Shape ID="{cid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">'
        f'<Cell N="BeginX" V="{bx:.4f}"/><Cell N="BeginY" V="{by:.4f}"/>'
        f'<Cell N="EndX" V="{ex:.4f}"/><Cell N="EndY" V="{ey:.4f}"/>'
        f'<Cell N="PinX" V="{cx:.4f}"/><Cell N="PinY" V="{cy:.4f}"/>'
        f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
        f'<Cell N="LocPinX" V="{w / 2:.4f}" F="Width*0.5"/>'
        f'<Cell N="LocPinY" V="{h / 2:.4f}" F="Height*0.5"/>'
        f'{_color_cell("LineColor", line)}'
        f'<Cell N="LinePattern" V="{pattern}"/>'
        '<Cell N="LineWeight" V="0.0138"/>'
        '<Cell N="EndArrow" V="4"/>'
        '<Section N="Geometry" IX="0">'
        '<Cell N="NoFill" V="1"/>'
        '<Row T="MoveTo" IX="1"><Cell N="X" V="0" F="Width*0"/>'
        '<Cell N="Y" V="0" F="Height*0"/></Row>'
        '<Row T="LineTo" IX="2"><Cell N="X" F="Width*1"/>'
        '<Cell N="Y" F="Height*1"/></Row>'
        '</Section>'
        f'{text}'
        '</Shape>'
    )


def _core_xml(title: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title>{escape(title)}</dc:title>'
        '<dc:creator>Singh360_SmartDraw</dc:creator>'
        '<cp:lastModifiedBy>Singh360_SmartDraw</cp:lastModifiedBy>'
        '</cp:coreProperties>'
    )


# --- static OPC parts -----------------------------------------------------
_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>'
    '<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>'
    '<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    '</Types>'
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.microsoft.com/visio/2010/relationships/document" '
    'Target="visio/document.xml"/>'
    '<Relationship Id="rId2" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/core-properties" '
    'Target="docProps/core.xml"/>'
    '<Relationship Id="rId3" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
    'Target="docProps/app.xml"/>'
    '</Relationships>'
)

_APP_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
    '<Application>Singh360_SmartDraw</Application>'
    '<Company>Singh360</Company>'
    '</Properties>'
)

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f'<VisioDocument xmlns="{MAIN_NS}" xmlns:r="{REL_NS}" xml:space="preserve">'
    '<DocumentSettings TopPage="0" DefaultTextStyle="0" DefaultLineStyle="0" '
    'DefaultFillStyle="0" DefaultGuideStyle="0">'
    '<GlueSettings>9</GlueSettings>'
    '<SnapSettings>65847</SnapSettings>'
    '</DocumentSettings>'
    '</VisioDocument>'
)

_DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.microsoft.com/visio/2010/relationships/pages" '
    'Target="pages/pages.xml"/>'
    '</Relationships>'
)

_PAGES_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.microsoft.com/visio/2010/relationships/page" '
    'Target="page1.xml"/>'
    '</Relationships>'
)


def validate_vsdx(path: str | Path) -> tuple[bool, list[str]]:
    """Deterministic structural proof: required parts exist, every XML part
    parses, and every relationship target resolves inside the package."""
    problems: list[str] = []
    required = {
        "[Content_Types].xml",
        "_rels/.rels",
        "visio/document.xml",
        "visio/_rels/document.xml.rels",
        "visio/pages/pages.xml",
        "visio/pages/_rels/pages.xml.rels",
        "visio/pages/page1.xml",
    }
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for part in required:
            if part not in names:
                problems.append(f"missing required part: {part}")
        for name in names:
            if name.endswith(".xml") or name.endswith(".rels"):
                try:
                    ET.fromstring(z.read(name))
                except ET.ParseError as exc:
                    problems.append(f"malformed XML in {name}: {exc}")
        # Resolve relationship targets.
        for rels_name in [n for n in names if n.endswith(".rels")]:
            base = rels_name.rsplit("_rels/", 1)[0]
            root = ET.fromstring(z.read(rels_name))
            for rel in root:
                target = rel.get("Target", "")
                if target.startswith("http"):
                    continue
                resolved = _normalize_join(base, target)
                if resolved not in names:
                    problems.append(f"{rels_name}: unresolved target {target}")
    return (len(problems) == 0), problems


def _normalize_join(base: str, target: str) -> str:
    parts = (base + target).split("/")
    out: list[str] = []
    for p in parts:
        if p in ("", "."):
            continue
        if p == "..":
            if out:
                out.pop()
        else:
            out.append(p)
    return "/".join(out)
