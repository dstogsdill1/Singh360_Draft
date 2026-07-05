"""engines/ems_sheet.py — Milestone 4A professional page templates (Phase 5).

Renders the neutral graph/table output of the Phase 7 generators into clean,
black-and-white SVG sheets that honour the Phase 4 drawing standard:

  * ANSI B / 17x11 landscape default (scales to 8.5x11).
  * No internal body scrolling — table overflow creates continuation sheets
    with a repeated header.
  * Equipment symbols: black stroke / white fill; connectors use presets.
  * Legend rendered top-right.

Deterministic string output — no external fonts or assets. Blank cells stay
blank; nothing is invented.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from core.drawing_style import (
    NEW_STROKE,
    SHEET_SIZES_IN,
    SYMBOL_FILL,
    SYMBOL_STROKE,
    connector_preset,
)

_FONT = "font-family='Arial, Helvetica, sans-serif'"
_PPI = 72.0


def _sheet_px(sheet: str) -> tuple[float, float]:
    w_in, h_in = SHEET_SIZES_IN.get(sheet, SHEET_SIZES_IN["ansi_b"])
    return w_in * _PPI, h_in * _PPI


def _svg_open(w: float, h: float) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{w:.0f}' height='{h:.0f}' "
        f"viewBox='0 0 {w:.0f} {h:.0f}'>"
        f"<rect x='0' y='0' width='{w:.0f}' height='{h:.0f}' fill='#FFFFFF' "
        f"stroke='{SYMBOL_STROKE}' stroke-width='1'/>"
    )


def _text(x: float, y: float, s: str, size: float = 9.0, anchor: str = "start", bold: bool = False) -> str:
    weight = " font-weight='bold'" if bold else ""
    return (f"<text x='{x:.1f}' y='{y:.1f}' text-anchor='{anchor}' fill='{SYMBOL_STROKE}' "
            f"{_FONT} font-size='{size:.1f}'{weight}>{escape(str(s))}</text>")


def _title_strip(w: float, title: str, subtitle: str, sheet_no: str) -> str:
    parts = [f"<line x1='0' y1='30' x2='{w:.0f}' y2='30' stroke='{SYMBOL_STROKE}' stroke-width='1'/>"]
    parts.append(_text(14, 21, title, 15.0, bold=True))
    if subtitle:
        parts.append(_text(w - 14, 21, subtitle, 10.0, anchor="end"))
    if sheet_no:
        parts.append(_text(w - 14, 44, sheet_no, 10.0, anchor="end", bold=True))
    return "".join(parts)


def _legend(w: float, presets: list[dict]) -> str:
    if not presets:
        return ""
    bx = w - 220
    by = 44
    parts = [f"<rect x='{bx:.0f}' y='{by:.0f}' width='206' height='{18 + 16 * len(presets):.0f}' "
             f"fill='#FFFFFF' stroke='{SYMBOL_STROKE}' stroke-width='1'/>"]
    parts.append(_text(bx + 8, by + 14, "LEGEND", 8.5, bold=True))
    y = by + 30
    for p in presets:
        preset = connector_preset(p.get("id", ""))
        dash = f" stroke-dasharray='{preset.dash}'" if preset.dash else ""
        parts.append(f"<line x1='{bx + 8:.0f}' y1='{y:.0f}' x2='{bx + 48:.0f}' y2='{y:.0f}' "
                     f"stroke='{preset.stroke}' stroke-width='{preset.width}'{dash}/>")
        parts.append(_text(bx + 56, y + 3, p.get("label", ""), 7.5))
        y += 16
    return "".join(parts)


def _node_box(node: dict) -> str:
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    label = node.get("label", "")
    parts = [f"<rect x='{x:.1f}' y='{y:.1f}' width='{w:.1f}' height='{h:.1f}' "
             f"fill='{SYMBOL_FILL}' stroke='{NEW_STROKE}' stroke-width='1.3'/>"]
    parts.append(_text(x + w / 2, y + h / 2 + 3, label, 9.0, anchor="middle"))
    return "".join(parts)


def _edge_line(a: dict, b: dict, edge: dict) -> str:
    ax = a["x"] + a["w"] / 2
    ay = a["y"] + a["h"] / 2
    bx = b["x"] + b["w"] / 2
    by = b["y"] + b["h"] / 2
    preset = connector_preset(edge.get("preset", "cat6"))
    dash = f" stroke-dasharray='{preset.dash}'" if preset.dash else ""
    # Orthogonal (L-shaped) polyline routing.
    points = f"{ax:.1f},{ay:.1f} {ax:.1f},{by:.1f} {bx:.1f},{by:.1f}"
    return (f"<polyline points='{points}' fill='none' stroke='{preset.stroke}' "
            f"stroke-width='{preset.width}'{dash}/>")


def render_layout_sheet(graph: dict, *, sheet: str = "ansi_b", sheet_no: str = "", subtitle: str = "") -> str:
    """Render a layout/one-line graph to a single B&W SVG sheet."""
    w, h = _sheet_px(sheet)
    by_id = {n["id"]: n for n in graph.get("nodes", [])}
    parts = [_svg_open(w, h)]
    parts.append(_title_strip(w, graph.get("title", "EMS Layout"), subtitle, sheet_no))
    # edges first (under nodes)
    for e in graph.get("edges", []):
        a, b = by_id.get(e.get("from")), by_id.get(e.get("to"))
        if a and b:
            parts.append(_edge_line(a, b, e))
    for n in graph.get("nodes", []):
        parts.append(_node_box(n))
    parts.append(_legend(w, graph.get("legend", [])))
    for i, note in enumerate(graph.get("notes", [])):
        parts.append(_text(14, h - 14 - i * 14, note, 9.0))
    parts.append("</svg>")
    return "".join(parts)


# --- schedule / table with continuation sheets ----------------------------
def render_schedule_sheets(table: dict, *, sheet: str = "ansi_b", base_sheet_no: str = "") -> list[dict]:
    """Render a table to one or more sheets, splitting on overflow.

    Returns a list of {sheetNo, svg}. The header row repeats on every sheet;
    no sheet body scrolls.
    """
    w, h = _sheet_px(sheet)
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    title = table.get("title", "Schedule")

    top = 60.0                 # below title strip
    bottom_margin = 40.0
    row_h = 18.0
    usable = h - top - bottom_margin
    rows_per_sheet = max(1, int(usable // row_h) - 1)  # -1 for header row

    col_x = _column_positions(w, columns)
    sheets: list[dict] = []
    total = max(1, -(-len(rows) // rows_per_sheet))  # ceil
    for pageno in range(total):
        chunk = rows[pageno * rows_per_sheet:(pageno + 1) * rows_per_sheet]
        sheet_no = _sheet_suffix(base_sheet_no, pageno, total)
        subtitle = f"Sheet {pageno + 1} of {total}" if total > 1 else ""
        sheets.append({"sheetNo": sheet_no, "svg": _render_table_page(
            w, h, title, subtitle, sheet_no, columns, col_x, chunk, top, row_h)})
    return sheets


def _column_positions(w: float, columns: list[str]) -> list[float]:
    left = 16.0
    right = w - 16.0
    n = max(1, len(columns))
    step = (right - left) / n
    return [left + i * step for i in range(n)] + [right]


def _sheet_suffix(base: str, pageno: int, total: int) -> str:
    if not base:
        return "" if total == 1 else chr(ord("a") + pageno)
    if total == 1:
        return base
    return f"{base}{chr(ord('a') + pageno)}"


def _render_table_page(w, h, title, subtitle, sheet_no, columns, col_x, chunk, top, row_h) -> str:
    parts = [_svg_open(w, h)]
    parts.append(_title_strip(w, title, subtitle, sheet_no))
    # header
    hy = top
    parts.append(f"<line x1='16' y1='{hy:.0f}' x2='{w - 16:.0f}' y2='{hy:.0f}' "
                 f"stroke='{SYMBOL_STROKE}' stroke-width='1'/>")
    for i, c in enumerate(columns):
        parts.append(_text(col_x[i] + 4, hy + 13, c, 8.0, bold=True))
    parts.append(f"<line x1='16' y1='{hy + 18:.0f}' x2='{w - 16:.0f}' y2='{hy + 18:.0f}' "
                 f"stroke='{SYMBOL_STROKE}' stroke-width='1'/>")
    # rows
    y = hy + 18
    for row in chunk:
        y += row_h
        for i, c in enumerate(columns):
            parts.append(_text(col_x[i] + 4, y - 5, row.get(c, ""), 7.5))
        parts.append(f"<line x1='16' y1='{y:.0f}' x2='{w - 16:.0f}' y2='{y:.0f}' "
                     f"stroke='#CCCCCC' stroke-width='0.5'/>")
    parts.append("</svg>")
    return "".join(parts)
