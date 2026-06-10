"""engines/svg_diagram.py — render a DiagramGraph into an ACTUAL picture.

Every other engine in this repo emits *data* (tables, .vson, .vsdx, .rdm.xml)
that a person still has to assemble by hand. This one renders the finished
**visual drawing** itself: each component is drawn as a labelled card coloured
by its category, wired to the others with connectors coloured by relationship
(hierarchy / control / network), with a legend and a title strip.

The result is a single self-contained SVG string — a real diagram you can open
in a browser, print to PDF, screenshot, or drop straight onto a SmartDraw /
Visio canvas as the starting drawing. No external assets, no fonts to embed,
nothing to copy-paste. It is deterministic and renders only what the graph
holds (blank stays blank).

Public API:
    build_svg(graph, title="", subtitle="", embed=False) -> str
    render(graph, out_path, title="", subtitle="") -> Path   (writes .svg)
    validate(path) -> tuple[bool, list[str]]
"""
from __future__ import annotations

import html
from pathlib import Path

import config

# ---- geometry (px) -------------------------------------------------------
CARD_W = 210
CARD_H = 92
H_GAP = 46
V_GAP = 70
PAD = 48
HEADER_H = 92            # top title strip
HDR_BAR = 24            # coloured header bar inside each card
LEGEND_H = 132          # reserved band at the bottom for the legend
MAX_ROW_NODES = 6       # wrap long node rows to keep a landscape-friendly aspect
DEPTH_GAP = 18          # extra vertical separation between hierarchy depths


def _e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def _trunc(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "\u2026"


def _readable_text(fill_hex: str) -> str:
    """Pick black or white text for a coloured header, by luminance."""
    h = (fill_hex or "#888888").lstrip("#")
    if len(h) != 6:
        return "#ffffff"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#1a2733" if lum > 150 else "#ffffff"


# Attribute keys worth showing inside a card body (in priority order).
_BODY_ATTRS = [
    ("control", "Ctrl"),
    ("panel", "Panel"),
    ("area", "Area"),
    ("voltage", "Volt"),
    ("set_point_f", "Set °F"),
    ("fixture", "Make"),
    ("ip", "IP"),
    ("switch", "Switch"),
]


def _hierarchy_parent(graph) -> dict[str, str]:
    parent: dict[str, str] = {}
    for e in graph.edges:
        if e.kind == "hierarchy":
            parent.setdefault(e.source, e.target)
    return parent


def _depth(nid: str, parent: dict[str, str], nodes) -> int:
    d, cur, seen = 0, nid, set()
    while cur in parent and parent[cur] in nodes and cur not in seen:
        seen.add(cur)
        cur = parent[cur]
        d += 1
        if d > 64:
            break
    return d


def _layout(graph) -> tuple[dict[str, tuple[int, int]], int, int]:
    """Landscape-friendly rank layout with row wrapping.

    The original pure-rank layout can become extremely wide/short when many nodes
    share one depth. This wrapped layout keeps the drawing printable and visually
    readable in landscape by chunking each depth into multiple centered rows.
    """
    parent = _hierarchy_parent(graph)
    ranks: dict[int, list[str]] = {}
    for nid in graph.nodes:
        ranks.setdefault(_depth(nid, parent, graph.nodes), []).append(nid)

    # Order each rank by group then label so siblings cluster.
    for d in ranks:
        ranks[d].sort(
            key=lambda i: (
                graph.nodes[i].group or graph.nodes[i].category or "",
                graph.nodes[i].label.lower(),
            )
        )

    wrapped_rows: list[tuple[int, list[str]]] = []
    for d in sorted(ranks):
        ids = ranks[d]
        for i in range(0, len(ids), MAX_ROW_NODES):
            wrapped_rows.append((d, ids[i:i + MAX_ROW_NODES]))

    max_row = max((len(ids) for _, ids in wrapped_rows), default=1)
    canvas_w = PAD * 2 + max(max_row, 1) * (CARD_W + H_GAP) - H_GAP

    # Height is based on wrapped rows, with extra spacing when moving to a
    # deeper hierarchy rank.
    row_blocks = len(wrapped_rows)
    depth_jumps = 0
    prev_depth = None
    for d, _ in wrapped_rows:
        if prev_depth is not None and d != prev_depth:
            depth_jumps += 1
        prev_depth = d
    canvas_h = (
        HEADER_H
        + PAD
        + row_blocks * (CARD_H + V_GAP)
        - (V_GAP if row_blocks else 0)
        + depth_jumps * DEPTH_GAP
        + PAD
        + LEGEND_H
    )

    pos: dict[str, tuple[int, int]] = {}
    y = HEADER_H + PAD
    prev_depth = None
    for d, ids in wrapped_rows:
        if prev_depth is not None and d != prev_depth:
            y += DEPTH_GAP
        row_w = len(ids) * (CARD_W + H_GAP) - H_GAP
        x0 = (canvas_w - row_w) // 2  # centre each rank
        for i, nid in enumerate(ids):
            pos[nid] = (x0 + i * (CARD_W + H_GAP), y)
        y += CARD_H + V_GAP
        prev_depth = d
    return pos, canvas_w, canvas_h


def _card_centres(pos: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    return {nid: (x + CARD_W // 2, y + CARD_H // 2) for nid, (x, y) in pos.items()}


def _edge_svg(graph, centres) -> str:
    out = []
    for e in graph.edges:
        a = centres.get(e.source)
        b = centres.get(e.target)
        if not a or not b:
            continue
        st = config.EDGE_STYLES.get(e.kind, {"line": "#57606A", "pattern": "solid"})
        col = st["line"]
        dash = {"dash": "8 5", "dot": "2 5"}.get(st["pattern"], "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        # Elbow: leave from source, drop to a mid-y, slide across, into target.
        (x1, y1), (x2, y2) = a, b
        midy = (y1 + y2) // 2
        path = f"M {x1} {y1} L {x1} {midy} L {x2} {midy} L {x2} {y2}"
        out.append(
            f'<path d="{path}" fill="none" stroke="{col}" stroke-width="2"'
            f'{dash_attr} marker-end="url(#arrow-{e.kind})" opacity="0.9"/>'
        )
        if e.label:
            lx, ly = (x1 + x2) // 2, midy
            lbl = _e(_trunc(e.label, 22))
            w = max(28, len(lbl) * 6 + 10)
            out.append(
                f'<rect x="{lx - w // 2}" y="{ly - 9}" width="{w}" height="18" rx="4" '
                f'fill="#ffffff" stroke="{col}" stroke-width="1" opacity="0.95"/>'
                f'<text x="{lx}" y="{ly + 4}" text-anchor="middle" '
                f'font-size="10" fill="{col}">{lbl}</text>'
            )
    return "\n".join(out)


def build_svg(graph, title: str = "", subtitle: str = "", embed: bool = False) -> str:
    """Render the whole graph to a self-contained SVG string."""
    pos, cw, ch = _layout(graph)
    centres = _card_centres(pos)
    title = title or getattr(graph, "name", "Singh360 Drawing")

    # Arrow markers, one per edge kind (coloured to match).
    defs = ['<defs>']
    for kind, st in config.EDGE_STYLES.items():
        defs.append(
            f'<marker id="arrow-{kind}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{st["line"]}"/></marker>'
        )
    defs.append(
        '<filter id="cardshadow" x="-10%" y="-10%" width="120%" height="130%">'
        '<feDropShadow dx="0" dy="1.5" stdDeviation="1.6" flood-color="#0b3d63" '
        'flood-opacity="0.18"/></filter>')
    defs.append('</defs>')

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cw} {ch}" '
        f'width="{cw}" height="{ch}" font-family="Segoe UI, Arial, sans-serif">',
        "".join(defs),
        f'<rect x="0" y="0" width="{cw}" height="{ch}" fill="#ffffff"/>',
    ]

    # Title strip.
    parts.append(
        f'<rect x="0" y="0" width="{cw}" height="{HEADER_H}" fill="#0b3d63"/>'
        f'<text x="{PAD}" y="40" font-size="22" font-weight="700" fill="#ffffff">{_e(title)}</text>'
    )
    if subtitle:
        parts.append(
            f'<text x="{PAD}" y="66" font-size="13" fill="#bcd6ea">{_e(subtitle)}</text>'
        )
    parts.append(
        f'<text x="{cw - PAD}" y="40" text-anchor="end" font-size="12" '
        f'fill="#7fb0d4">Singh360_SmartDraw — auto-rendered drawing</text>'
    )

    # Edges first (so cards sit on top).
    parts.append(_edge_svg(graph, centres))

    # Cards.
    for nid, (x, y) in pos.items():
        node = graph.nodes[nid]
        style = config.style_for(node.category)
        hdr_text = _readable_text(style.fill)
        label = _e(_trunc(node.label, 26))
        cat = _e(_trunc(node.category or node.group or "", 24))

        # Body lines from the most useful attributes present.
        body = []
        if node.unit_type:
            body.append(_e(_trunc(node.unit_type, 30)))
        for key, lbl in _BODY_ATTRS:
            val = (node.attrs or {}).get(key, "")
            if val and len(body) < 3:
                body.append(f"{lbl}: " + _e(_trunc(str(val), 24)))
            if len(body) >= 3:
                break

        parts.append(f'<g filter="url(#cardshadow)">')
        parts.append(
            f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="8" '
            f'fill="#ffffff" stroke="{style.line}" stroke-width="1.5"/>'
        )
        # Left accent stripe.
        parts.append(
            f'<rect x="{x}" y="{y}" width="6" height="{CARD_H}" rx="3" fill="{style.fill}"/>'
        )
        # Header bar.
        parts.append(
            f'<path d="M{x+8} {y} h{CARD_W-16} a8 8 0 0 1 8 8 v{HDR_BAR-8} h-{CARD_W} '
            f'v-{HDR_BAR-8} a8 8 0 0 1 8 -8 z" fill="{style.fill}"/>'
        )
        parts.append(
            f'<text x="{x+14}" y="{y+16}" font-size="12" font-weight="700" '
            f'fill="{hdr_text}">{label}</text>'
        )
        # Body.
        ty = y + HDR_BAR + 16
        if cat:
            parts.append(
                f'<text x="{x+14}" y="{ty}" font-size="10.5" font-weight="600" '
                f'fill="{style.line}">{cat}</text>'
            )
            ty += 15
        for line in body:
            parts.append(
                f'<text x="{x+14}" y="{ty}" font-size="10.5" fill="#42505e">{line}</text>'
            )
            ty += 14
        parts.append("</g>")

    # Legend.
    parts.append(_legend_svg(graph, cw, ch))

    parts.append("</svg>")
    svg = "\n".join(p for p in parts if p)
    if embed:
        return svg
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg


def _legend_svg(graph, cw: int, ch: int) -> str:
    ly = ch - LEGEND_H + 16
    lx = PAD
    out = [
        f'<rect x="{lx-12}" y="{ly-12}" width="{cw - 2*(PAD-12)}" height="{LEGEND_H-24}" '
        f'rx="8" fill="#f6f9fc" stroke="#d7dee6"/>',
        f'<text x="{lx}" y="{ly+6}" font-size="12" font-weight="700" fill="#0b3d63">LEGEND</text>',
    ]
    # Edge kinds.
    ex = lx
    ey = ly + 26
    kind_label = {"hierarchy": "Serves / parent", "control": "Control chain", "network": "Network"}
    for kind, st in config.EDGE_STYLES.items():
        dash = {"dash": "8 5", "dot": "2 5"}.get(st["pattern"], "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(
            f'<line x1="{ex}" y1="{ey}" x2="{ex+34}" y2="{ey}" stroke="{st["line"]}" '
            f'stroke-width="2.5"{dash_attr}/>'
            f'<text x="{ex+42}" y="{ey+4}" font-size="11" fill="#42505e">'
            f'{_e(kind_label.get(kind, kind))}</text>'
        )
        ex += 190
    # Category swatches (only categories present).
    cats = []
    for n in graph.nodes.values():
        c = n.category or n.group or ""
        if c and c not in cats:
            cats.append(c)
    cx = lx
    cy = ly + 56
    for c in cats[:8]:
        style = config.style_for(c)
        out.append(
            f'<rect x="{cx}" y="{cy-11}" width="16" height="16" rx="3" '
            f'fill="{style.fill}" stroke="{style.line}"/>'
            f'<text x="{cx+22}" y="{cy+2}" font-size="11" fill="#42505e">{_e(_trunc(c,18))}</text>'
        )
        cx += 150
        if cx > cw - 200:
            cx = lx
            cy += 24
    return "\n".join(out)


def render(graph, out_path: str | Path, title: str = "", subtitle: str = "") -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_svg(graph, title=title, subtitle=subtitle), encoding="utf-8")
    return out_path


def validate(path: str | Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    try:
        txt = Path(path).read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        return False, [f"unreadable: {exc}"]
    if "<svg" not in txt:
        problems.append("missing <svg> root")
    if "</svg>" not in txt:
        problems.append("unclosed <svg>")
    if "viewBox" not in txt:
        problems.append("missing viewBox")
    return (not problems), problems
