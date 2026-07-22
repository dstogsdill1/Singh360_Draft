from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
import re

import fitz  # PyMuPDF


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ALLOWED_PATTERNS = {
    "solid",
    "outline",
    "double-outline",
    "split-vertical",
    "split-horizontal",
    "diagonal",
    "crosshatch",
}
_ALLOWED_SHAPES = {"auto", "circle", "square", "none"}


def _color(value: Any, fallback: str = "#808080") -> str:
    text = str(value or "").strip()
    return text.upper() if _HEX.fullmatch(text) else fallback


def _text(value: Any, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[:limit]


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:64]):
        if not isinstance(item, dict):
            continue
        count = max(0, int(item.get("included") or item.get("count") or 0))
        if count <= 0:
            continue
        code = _text(item.get("code") or "SYMBOL", 16)
        label = _text(item.get("label") or "Unnamed symbol", 120)
        pattern = str(item.get("pattern") or "solid")
        if pattern not in _ALLOWED_PATTERNS:
            pattern = "solid"
        shape = str(item.get("shape") or "auto")
        if shape not in _ALLOWED_SHAPES:
            shape = "auto"
        if shape == "auto":
            shape = "square" if code.upper() == "CC" else "circle"
        rows.append(
            {
                "id": f"r{index}",
                "code": code,
                "glyph": _text(item.get("glyph") or ("$" if "CLEAN SWITCH" in label.upper() else code), 8),
                "label": label,
                "count": count,
                "color": _color(item.get("color"), "#808080"),
                "color2": _color(item.get("color2"), _color(item.get("color"), "#808080")),
                "pattern": pattern,
                "shape": shape,
            }
        )
    return rows


def _marker_defs(row: dict[str, Any], index: int) -> str:
    c1 = row["color"]
    c2 = row["color2"]
    pattern = row["pattern"]
    if pattern == "split-horizontal":
        return (
            f'<linearGradient id="g{index}" x1="0%" y1="0%" x2="0%" y2="100%">'
            f'<stop offset="0%" stop-color="{c1}"/><stop offset="50%" stop-color="{c1}"/>'
            f'<stop offset="50%" stop-color="{c2}"/><stop offset="100%" stop-color="{c2}"/>'
            "</linearGradient>"
        )
    if pattern == "diagonal":
        return (
            f'<linearGradient id="g{index}" x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="{c1}"/><stop offset="49.5%" stop-color="{c1}"/>'
            f'<stop offset="50.5%" stop-color="{c2}"/><stop offset="100%" stop-color="{c2}"/>'
            "</linearGradient>"
        )
    if pattern == "crosshatch":
        return (
            f'<pattern id="g{index}" width="10" height="10" patternUnits="userSpaceOnUse">'
            f'<rect width="10" height="10" fill="{c1}" fill-opacity="0.24"/>'
            f'<path d="M-2 2 L2 -2 M0 10 L10 0 M8 12 L12 8" stroke="{c2}" stroke-width="2"/>'
            "</pattern>"
        )
    return (
        f'<linearGradient id="g{index}" x1="0%" y1="0%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="{c1}"/><stop offset="50%" stop-color="{c1}"/>'
        f'<stop offset="50%" stop-color="{c2}"/><stop offset="100%" stop-color="{c2}"/>'
        "</linearGradient>"
    )


def _marker(row: dict[str, Any], index: int, x: float, y: float, size: float) -> str:
    shape = row["shape"]
    pattern = row["pattern"]
    c1 = row["color"]
    c2 = row["color2"]
    glyph = escape(row["glyph"])
    cx = x + size / 2
    cy = y + size / 2
    r = size / 2 - 2
    split_v = pattern == "split-vertical"
    split_h = pattern == "split-horizontal"
    diagonal = pattern == "diagonal"
    split = split_v or split_h or diagonal
    fill = "white" if pattern in {"outline", "double-outline"} else (f"url(#g{index})" if pattern == "crosshatch" else c1)
    parts: list[str] = []
    clip_id = f"clip{index}"

    def split_fill(rect_x: float, rect_y: float, rect_w: float, rect_h: float, clip: str = "") -> str:
        clip_attr = f' clip-path="url(#{clip})"' if clip else ""
        if split_v:
            return (
                f'<g{clip_attr}><rect x="{rect_x:.2f}" y="{rect_y:.2f}" width="{rect_w/2:.2f}" height="{rect_h:.2f}" fill="{c1}"/>'
                f'<rect x="{rect_x+rect_w/2:.2f}" y="{rect_y:.2f}" width="{rect_w/2:.2f}" height="{rect_h:.2f}" fill="{c2}"/></g>'
            )
        if split_h:
            return (
                f'<g{clip_attr}><rect x="{rect_x:.2f}" y="{rect_y:.2f}" width="{rect_w:.2f}" height="{rect_h/2:.2f}" fill="{c1}"/>'
                f'<rect x="{rect_x:.2f}" y="{rect_y+rect_h/2:.2f}" width="{rect_w:.2f}" height="{rect_h/2:.2f}" fill="{c2}"/></g>'
            )
        return (
            f'<g{clip_attr}><polygon points="{rect_x:.2f},{rect_y:.2f} {rect_x+rect_w:.2f},{rect_y:.2f} {rect_x:.2f},{rect_y+rect_h:.2f}" fill="{c1}"/>'
            f'<polygon points="{rect_x+rect_w:.2f},{rect_y:.2f} {rect_x+rect_w:.2f},{rect_y+rect_h:.2f} {rect_x:.2f},{rect_y+rect_h:.2f}" fill="{c2}"/></g>'
        )

    if shape == "none":
        if split:
            parts.append(split_fill(x, y, size, size))
        else:
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{size:.2f}" height="{size:.2f}" rx="4" fill="{fill}" stroke="none"/>')
    elif shape == "square":
        sx, sy, sw, sh = x + 2, y + 2, size - 4, size - 4
        if split:
            parts.append(split_fill(sx, sy, sw, sh))
        else:
            parts.append(f'<rect x="{sx:.2f}" y="{sy:.2f}" width="{sw:.2f}" height="{sh:.2f}" rx="2" fill="{fill}" stroke="none"/>')
        if split_v:
            mid = x + size / 2
            parts.extend([
                f'<path d="M {mid:.2f} {y+2:.2f} H {x+2:.2f} V {y+size-2:.2f} H {mid:.2f}" fill="none" stroke="{c1}" stroke-width="3"/>',
                f'<path d="M {mid:.2f} {y+2:.2f} H {x+size-2:.2f} V {y+size-2:.2f} H {mid:.2f}" fill="none" stroke="{c2}" stroke-width="3"/>',
                f'<line x1="{mid:.2f}" y1="{y+3:.2f}" x2="{mid:.2f}" y2="{y+size-3:.2f}" stroke="#ffffff" stroke-width="1.4"/>',
            ])
        elif split_h:
            mid = y + size / 2
            parts.extend([
                f'<path d="M {x+2:.2f} {mid:.2f} V {y+2:.2f} H {x+size-2:.2f} V {mid:.2f}" fill="none" stroke="{c1}" stroke-width="3"/>',
                f'<path d="M {x+2:.2f} {mid:.2f} V {y+size-2:.2f} H {x+size-2:.2f} V {mid:.2f}" fill="none" stroke="{c2}" stroke-width="3"/>',
            ])
        else:
            parts.append(f'<rect x="{sx:.2f}" y="{sy:.2f}" width="{sw:.2f}" height="{sh:.2f}" rx="2" fill="none" stroke="{c1}" stroke-width="3"/>')
            if pattern == "double-outline":
                parts.append(f'<rect x="{x+6:.2f}" y="{y+6:.2f}" width="{size-12:.2f}" height="{size-12:.2f}" rx="1" fill="none" stroke="{c1}" stroke-width="1.5"/>')
    else:
        if split_v:
            parts.append(f'<path d="M {cx:.2f} {cy-r:.2f} A {r:.2f} {r:.2f} 0 0 0 {cx:.2f} {cy+r:.2f} L {cx:.2f} {cy-r:.2f} Z" fill="{c1}"/>')
            parts.append(f'<path d="M {cx:.2f} {cy-r:.2f} A {r:.2f} {r:.2f} 0 0 1 {cx:.2f} {cy+r:.2f} L {cx:.2f} {cy-r:.2f} Z" fill="{c2}"/>')
        elif split_h:
            parts.append(f'<path d="M {cx-r:.2f} {cy:.2f} A {r:.2f} {r:.2f} 0 0 1 {cx+r:.2f} {cy:.2f} L {cx-r:.2f} {cy:.2f} Z" fill="{c1}"/>')
            parts.append(f'<path d="M {cx-r:.2f} {cy:.2f} A {r:.2f} {r:.2f} 0 0 0 {cx+r:.2f} {cy:.2f} L {cx-r:.2f} {cy:.2f} Z" fill="{c2}"/>')
        elif diagonal:
            parts.append(f'<defs><clipPath id="{clip_id}"><circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"/></clipPath></defs>')
            parts.append(split_fill(x + 2, y + 2, size - 4, size - 4, clip_id))
        else:
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="none"/>')
        if split_v:
            parts.extend([
                f'<path d="M {cx:.2f} {cy-r:.2f} A {r:.2f} {r:.2f} 0 0 0 {cx:.2f} {cy+r:.2f}" fill="none" stroke="{c1}" stroke-width="3"/>',
                f'<path d="M {cx:.2f} {cy-r:.2f} A {r:.2f} {r:.2f} 0 0 1 {cx:.2f} {cy+r:.2f}" fill="none" stroke="{c2}" stroke-width="3"/>',
                f'<line x1="{cx:.2f}" y1="{cy-r+1:.2f}" x2="{cx:.2f}" y2="{cy+r-1:.2f}" stroke="#ffffff" stroke-width="1.3"/>',
            ])
        elif split_h:
            parts.extend([
                f'<path d="M {cx-r:.2f} {cy:.2f} A {r:.2f} {r:.2f} 0 0 1 {cx+r:.2f} {cy:.2f}" fill="none" stroke="{c1}" stroke-width="3"/>',
                f'<path d="M {cx-r:.2f} {cy:.2f} A {r:.2f} {r:.2f} 0 0 0 {cx+r:.2f} {cy:.2f}" fill="none" stroke="{c2}" stroke-width="3"/>',
            ])
        else:
            parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="none" stroke="{c1}" stroke-width="3"/>')
            if pattern == "double-outline":
                parts.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{max(1, r-4):.2f}" fill="none" stroke="{c1}" stroke-width="1.5"/>')
    parts.append(
        f'<text x="{cx:.2f}" y="{cy + size*0.12:.2f}" text-anchor="middle" '
        f'font-family="Arial, sans-serif" font-size="{size*0.31:.2f}" font-weight="700" fill="#111111">{glyph}</text>'
    )
    return "".join(parts)


def build_symbol_count_legend_svg(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]], int, int]:
    rows = _rows(payload)
    title = _text(payload.get("title") or "SYMBOL COUNT SUMMARY", 100)
    source = _text(payload.get("sourceName") or "Reviewed Symbol Mapper drawing", 140)
    drawing_code = _text(payload.get("drawingCode") or "", 24)
    heading = title if not drawing_code or drawing_code.upper() in title.upper() else f"{title} — {drawing_code}"

    columns = 1 if len(rows) <= 10 else 2
    rows_per_col = max(1, (len(rows) + columns - 1) // columns)
    width = 760 if columns == 1 else 1320
    pad = 24
    header_h = 82
    source_h = 34
    row_h = 58
    footer_h = 22
    height = header_h + source_h + rows_per_col * row_h + footer_h + pad
    col_w = (width - pad * 2 - (20 if columns == 2 else 0)) / columns
    total = sum(row["count"] for row in rows)

    defs = "".join(_marker_defs(row, index) for index, row in enumerate(rows))
    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<defs>{defs}<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.20"/></filter></defs>',
        f'<rect x="4" y="4" width="{width-8}" height="{height-8}" rx="10" fill="#ffffff" stroke="#38424d" stroke-width="2" filter="url(#shadow)"/>',
        f'<rect x="4" y="4" width="{width-8}" height="{header_h}" rx="10" fill="#23272f"/>',
        f'<rect x="4" y="{header_h-8}" width="{width-8}" height="8" fill="#23272f"/>',
        f'<text x="{pad}" y="38" font-family="Arial, sans-serif" font-size="25" font-weight="800" fill="#ffffff">{escape(heading)}</text>',
        f'<text x="{width-pad}" y="38" text-anchor="end" font-family="Arial, sans-serif" font-size="17" font-weight="700" fill="#ffffff">TOTAL {total}</text>',
        f'<text x="{pad}" y="64" font-family="Arial, sans-serif" font-size="12" fill="#dbe2ea">Final reviewed Included counts only</text>',
        f'<rect x="{pad}" y="{header_h+10}" width="{width-pad*2}" height="{source_h-8}" rx="4" fill="#eef1f4"/>',
        f'<text x="{pad+10}" y="{header_h+30}" font-family="Arial, sans-serif" font-size="11" font-weight="700" fill="#3c4651">SOURCE</text>',
        f'<text x="{pad+70}" y="{header_h+30}" font-family="Arial, sans-serif" font-size="11" fill="#23272f">{escape(source)}</text>',
    ]

    if not rows:
        svg.append(
            f'<text x="{width/2:.2f}" y="{header_h+source_h+72}" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" fill="#555">No included symbols were confirmed.</text>'
        )
    for index, row in enumerate(rows):
        column = index // rows_per_col
        row_index = index % rows_per_col
        x = pad + column * (col_w + (20 if columns == 2 else 0))
        y = header_h + source_h + row_index * row_h + 8
        svg.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{col_w:.2f}" height="{row_h-6}" rx="5" fill="#ffffff" stroke="#c9d0d7" stroke-width="1"/>')
        svg.append(_marker(row, index, x + 9, y + 7, 38))
        svg.append(f'<text x="{x+58:.2f}" y="{y+21:.2f}" font-family="Arial, sans-serif" font-size="14" font-weight="800" fill="#111111">{escape(row["code"])}</text>')
        label = escape(row["label"])
        svg.append(f'<text x="{x+58:.2f}" y="{y+40:.2f}" font-family="Arial, sans-serif" font-size="11" fill="#313942">{label}</text>')
        badge_w = 52
        bx = x + col_w - badge_w - 10
        svg.append(f'<rect x="{bx:.2f}" y="{y+8:.2f}" width="{badge_w}" height="{row_h-22}" rx="16" fill="#23272f"/>')
        svg.append(f'<text x="{bx+badge_w/2:.2f}" y="{y+31:.2f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="17" font-weight="800" fill="#ffffff">{row["count"]}</text>')

    svg.append(f'<text x="{pad}" y="{height-12}" font-family="Arial, sans-serif" font-size="10" fill="#66717d">Zero-count, ignored, and unresolved symbols are omitted.</text>')
    svg.append("</svg>")
    return "".join(svg), rows, width, height


def build_symbol_mapper_package(session_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    session_dir = Path(session_dir)
    final_pdf = session_dir / "final.pdf"
    if not final_pdf.is_file():
        raise FileNotFoundError("The reviewed highlighted PDF does not exist yet.")

    svg, rows, width, height = build_symbol_count_legend_svg(payload)
    svg_path = session_dir / "count_legend.svg"
    png_path = session_dir / "count_legend.png"
    package_path = session_dir / "package.pdf"
    svg_path.write_text(svg, encoding="utf-8")

    with fitz.open(stream=svg.encode("utf-8"), filetype="svg") as svg_doc:
        pix = svg_doc[0].get_pixmap(matrix=fitz.Matrix(2.4, 2.4), alpha=True)
        pix.save(png_path)
        legend_pdf_bytes = svg_doc.convert_to_pdf()

    with fitz.open(final_pdf) as highlighted, fitz.open() as output:
        if highlighted.page_count != 1:
            raise ValueError("Symbol Mapper output must contain exactly one highlighted page.")
        output.insert_pdf(highlighted)
        page_rect = highlighted[0].rect
        summary_page = output.new_page(width=page_rect.width, height=page_rect.height)
        with fitz.open(stream=legend_pdf_bytes, filetype="pdf") as legend_doc:
            legend_rect = legend_doc[0].rect
            max_w = page_rect.width * 0.62
            max_h = page_rect.height * 0.72
            scale = min(max_w / max(1, legend_rect.width), max_h / max(1, legend_rect.height), 1.8)
            target_w = legend_rect.width * scale
            target_h = legend_rect.height * scale
            target = fitz.Rect(
                (page_rect.width - target_w) / 2,
                (page_rect.height - target_h) / 2,
                (page_rect.width + target_w) / 2,
                (page_rect.height + target_h) / 2,
            )
            summary_page.show_pdf_page(target, legend_doc, 0, keep_proportion=True, overlay=True)
        output.save(package_path, garbage=4, deflate=True)

    return {
        "ok": True,
        "pdfName": "highlighted_with_symbol_counts.pdf",
        "pdfAsset": "package.pdf",
        "legendPngAsset": "count_legend.png",
        "legendSvgAsset": "count_legend.svg",
        "pageCount": 2,
        "listedRows": len(rows),
        "totalIncluded": sum(row["count"] for row in rows),
        "legendWidth": width,
        "legendHeight": height,
    }
