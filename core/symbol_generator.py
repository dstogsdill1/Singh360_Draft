"""core/symbol_generator.py — Milestone 4A black-and-white symbol system (Phase 3).

Technical drawings must not rely on photos. Every library component keeps two
representations:

  1. Reference image  — the PNG/JPG/photo used for the library preview.
  2. Drawing symbol   — a clean black-and-white SVG generated here.

`generate_symbol_svg()` returns a deterministic SVG string for a component,
picking a symbol family from its category (controller, enclosure, device,
siren, marker, logo). Logos never get a device symbol; they are passed through
as a labelled box referencing the reference image name only.

No external fonts, no rasterization, no hallucinated ports — ports come from
the component's manifest (or the category default).
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from core.drawing_style import (
    SYMBOL_FILL,
    SYMBOL_STROKE,
    SYMBOL_STROKE_W_MAX,
    category_default,
)

_FONT = "font-family='Arial, Helvetica, sans-serif'"


def _ports_for(component: dict) -> list[dict]:
    ports = component.get("ports")
    if isinstance(ports, list) and ports:
        return ports
    return category_default(component.get("category", "custom")).ports


def _label_text(component: dict) -> str:
    return str(
        component.get("defaultLabel")
        or component.get("partNumber")
        or component.get("displayName")
        or ""
    ).strip()


def _svg_header(w: float, h: float) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{w:.0f}' height='{h:.0f}' "
        f"viewBox='0 0 {w:.0f} {h:.0f}' fill='none' "
        f"stroke='{SYMBOL_STROKE}' stroke-width='{SYMBOL_STROKE_W_MAX:.1f}'>"
    )


def _port_marks(ports: list[dict], w: float, h: float, body: tuple[float, float, float, float]) -> str:
    """Render small port ticks on the body edges. `body` = (x, y, bw, bh)."""
    bx, by, bw, bh = body
    out: list[str] = []
    for p in ports:
        px = bx + float(p.get("x", 0.5)) * bw
        py = by + float(p.get("y", 0.5)) * bh
        out.append(f"<circle cx='{px:.1f}' cy='{py:.1f}' r='2.4' fill='{SYMBOL_STROKE}' />")
    return "".join(out)


def _label(text: str, w: float, y: float, size: float = 9.0) -> str:
    if not text:
        return ""
    return (
        f"<text x='{w / 2:.1f}' y='{y:.1f}' text-anchor='middle' "
        f"fill='{SYMBOL_STROKE}' stroke='none' {_FONT} font-size='{size:.1f}'>"
        f"{escape(text)}</text>"
    )


def _controller(component: dict) -> str:
    w, h = 140.0, 76.0
    body = (10.0, 8.0, 120.0, 44.0)
    bx, by, bw, bh = body
    parts = [_svg_header(w, h)]
    parts.append(f"<rect x='{bx}' y='{by}' width='{bw}' height='{bh}' rx='4' fill='{SYMBOL_FILL}' />")
    # header strip for the controller face
    parts.append(f"<line x1='{bx}' y1='{by + 12}' x2='{bx + bw}' y2='{by + 12}' />")
    # 3 terminal ticks along the bottom edge of the body (schematic hint)
    for i in range(1, 4):
        tx = bx + bw * i / 4
        parts.append(f"<line x1='{tx:.1f}' y1='{by + bh}' x2='{tx:.1f}' y2='{by + bh + 5}' />")
    parts.append(_port_marks(_ports_for(component), w, h, body))
    parts.append(_label(_label_text(component), w, by + bh + 20, 10.0))
    parts.append("</svg>")
    return "".join(parts)


def _enclosure(component: dict) -> str:
    w, h = 150.0, 128.0
    body = (12.0, 8.0, 126.0, 96.0)
    bx, by, bw, bh = body
    parts = [_svg_header(w, h)]
    parts.append(f"<rect x='{bx}' y='{by}' width='{bw}' height='{bh}' rx='3' fill='{SYMBOL_FILL}' />")
    # inner mounting rectangle
    parts.append(
        f"<rect x='{bx + 8}' y='{by + 8}' width='{bw - 16}' height='{bh - 16}' "
        f"stroke-dasharray='4 3' fill='none' />"
    )
    parts.append(_port_marks(_ports_for(component), w, h, body))
    parts.append(_label(_label_text(component), w, by + bh + 18, 10.0))
    parts.append("</svg>")
    return "".join(parts)


def _device(component: dict) -> str:
    w, h = 120.0, 80.0
    body = (12.0, 10.0, 96.0, 48.0)
    bx, by, bw, bh = body
    parts = [_svg_header(w, h)]
    parts.append(f"<rect x='{bx}' y='{by}' width='{bw}' height='{bh}' fill='{SYMBOL_FILL}' />")
    # IEC-style diagonal (simplified contactor/breaker hint)
    parts.append(f"<line x1='{bx + 10}' y1='{by + bh - 8}' x2='{bx + bw - 10}' y2='{by + 8}' />")
    parts.append(_port_marks(_ports_for(component), w, h, body))
    parts.append(_label(_label_text(component), w, by + bh + 18, 9.5))
    parts.append("</svg>")
    return "".join(parts)


def _siren(component: dict) -> str:
    w, h = 96.0, 96.0
    cx, cy, r = 48.0, 36.0, 26.0
    parts = [_svg_header(w, h)]
    parts.append(f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='{SYMBOL_FILL}' />")
    # radiating strokes (alarm/strobe hint)
    for dx, dy in ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)):
        x1 = cx + dx * (r + 2) * 0.7071 if dx and dy else cx + dx * (r + 2)
        y1 = cy + dy * (r + 2) * 0.7071 if dx and dy else cy + dy * (r + 2)
        x2 = cx + dx * (r + 10) * 0.7071 if dx and dy else cx + dx * (r + 10)
        y2 = cy + dy * (r + 10) * 0.7071 if dx and dy else cy + dy * (r + 10)
        parts.append(f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' />")
    parts.append(_label(_label_text(component), w, cy + r + 26, 9.5))
    parts.append("</svg>")
    return "".join(parts)


def _marker(component: dict) -> str:
    w, h = 84.0, 84.0
    cx, cy, r = 42.0, 34.0, 22.0
    parts = [_svg_header(w, h)]
    # diamond marker for sensors/transducers
    parts.append(
        f"<polygon points='{cx},{cy - r} {cx + r},{cy} {cx},{cy + r} {cx - r},{cy}' "
        f"fill='{SYMBOL_FILL}' />"
    )
    abbr = (_label_text(component)[:3] or "S").upper()
    parts.append(_label(abbr, w, cy + 4, 10.0))
    parts.append(_label(_label_text(component), w, cy + r + 22, 8.5))
    parts.append("</svg>")
    return "".join(parts)


def _logo(component: dict) -> str:
    w, h = 160.0, 68.0
    parts = [_svg_header(w, h)]
    parts.append(f"<rect x='6' y='6' width='{w - 12}' height='{h - 12}' rx='3' fill='{SYMBOL_FILL}' />")
    parts.append(_label(_label_text(component) or "LOGO", w, h / 2 + 4, 11.0))
    parts.append("</svg>")
    return "".join(parts)


_BUILDERS = {
    "controller": _controller,
    "enclosure": _enclosure,
    "device": _device,
    "siren": _siren,
    "marker": _marker,
    "logo": _logo,
    "reference": _logo,
}


def symbol_kind_for(component: dict) -> str:
    """Resolve which symbol family a component uses (category default)."""
    explicit = str(component.get("symbolKind") or "").strip()
    if explicit in _BUILDERS:
        return explicit
    return category_default(component.get("category", "custom")).symbol_kind


def generate_symbol_svg(component: dict) -> str:
    """Return a deterministic black-and-white SVG symbol for a component."""
    kind = symbol_kind_for(component)
    builder = _BUILDERS.get(kind, _device)
    return builder(component)
