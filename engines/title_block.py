"""engines/title_block.py — HEB-standard drawing title block (templated).

Reverse-engineered from the completed HEB 109 bid set (ProjectMates):
`109 EMS-1.1 EMS PARTIAL PLAN.pdf`. Every HEB sheet carries a right-edge title
block strip with a fixed stack of cells (bottom -> top):

    sheet number   ->  "EMS-1.1"            (big)
    scale/proj/date small rows
    sheet title    ->  "EMS PARTIAL PLAN"
    project name   ->  "H.E.B. HOUSTON 54 #109"
    project address
    H-E-B logo
    firm block     ->  consultant of record (Singh360 Inc.)
    engineer seal
    confidentiality notice
    revision block
    status checkboxes (preliminary / permit / construction)

This module emits that block as native Visio shapes (rectangles + text) on the
HEB `TB-ANNO` layer, parameterized by a TitleBlockInfo so EVERY future project
reuses the same frame — only the field values change. No values are invented:
unknown fields render blank, never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import config

# Title block geometry (inches). Right-edge strip, full sheet height.
TB_WIDTH_IN = 6.5
_TB_LAYER_IX = config.HEB_LAYER_INDEX.get("TB-ANNO", 8)


@dataclass
class TitleBlockInfo:
    """Everything the HEB title block frame needs. Blank = render blank."""

    project_name: str = ""          # "H.E.B. HOUSTON 54 #109"
    project_address: str = ""       # "9710 KATY FREEWAY, HOUSTON, TEXAS 77055"
    sheet_number: str = ""          # "EMS-1.1"
    sheet_title: str = ""           # "EMS PARTIAL PLAN"
    scale: str = "AS INDICATED"
    project_no: str = ""            # "26061"
    date: str = ""                  # "05/22/26"
    firm: str = "SINGH360 INC."
    firm_lines: list[str] = field(default_factory=lambda: [
        "Mechanical & Electrical EMS Consultants",
        "Medina, MN · Minnesota Corp.",
        "www.singh360.com",
    ])
    engineer: str = ""              # "R. S. Pitzer · TX PE 65986"
    revision: str = ""              # "PLAN MODIFICATION #21: FRESH INITIATIVE"
    status: str = "RELEASED FOR CONSTRUCTION"  # checkbox to tick

    def is_empty(self) -> bool:
        return not any((self.project_name, self.sheet_number, self.sheet_title))


# --------------------------------------------------------------------------
# Shape helpers (mirror visio_vsdx geometry so the block is real Visio shapes)
# --------------------------------------------------------------------------
def _rgb(hexcolor: str) -> str:
    h = (hexcolor or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 0, 0, 0
    return f"RGB({r},{g},{b})"


def _cell_shape(
    sid: int,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    text: str = "",
    font: float = 0.12,
    bold: bool = False,
    fill: str = "#FFFFFF",
    line: str = "#1A1A1A",
    text_color: str = "#1A1A1A",
    align: int = 1,           # 0 left, 1 center, 2 right
    line_weight: float = 0.01,
    no_line: bool = False,
) -> str:
    """One title-block cell: a rectangle (x,y = bottom-left) with centered text."""
    cx = x + w / 2.0
    cy = y + h / 2.0
    bold_xml = '<Cell N="Style" V="1"/>' if bold else ""
    return (
        f'<Shape ID="{sid}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">'
        f'<Cell N="PinX" V="{cx:.4f}"/><Cell N="PinY" V="{cy:.4f}"/>'
        f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
        f'<Cell N="LocPinX" V="{w / 2:.4f}" F="Width*0.5"/>'
        f'<Cell N="LocPinY" V="{h / 2:.4f}" F="Height*0.5"/>'
        '<Cell N="Angle" V="0"/>'
        f'<Cell N="LayerMember" V="{_TB_LAYER_IX}"/>'
        f'<Cell N="FillForegnd" V="{fill}" F="{_rgb(fill)}"/>'
        f'<Cell N="FillPattern" V="{0 if no_line else 1}"/>'
        f'<Cell N="LineColor" V="{line}" F="{_rgb(line)}"/>'
        f'<Cell N="LineWeight" V="{line_weight:.4f}"/>'
        f'<Cell N="LinePattern" V="{0 if no_line else 1}"/>'
        '<Section N="Character"><Row IX="0">'
        f'<Cell N="Color" V="{text_color}" F="{_rgb(text_color)}"/>'
        f'<Cell N="Size" V="{font:.4f}"/>'
        f'{bold_xml}'
        '</Row></Section>'
        '<Section N="Paragraph"><Row IX="0">'
        f'<Cell N="HorzAlign" V="{align}"/></Row></Section>'
        '<Section N="Geometry" IX="0">'
        '<Cell N="NoFill" V="0"/>'
        f'<Cell N="NoLine" V="{1 if no_line else 0}"/>'
        '<Row T="RelMoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
        '<Row T="RelLineTo" IX="2"><Cell N="X" V="1"/><Cell N="Y" V="0"/></Row>'
        '<Row T="RelLineTo" IX="3"><Cell N="X" V="1"/><Cell N="Y" V="1"/></Row>'
        '<Row T="RelLineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="1"/></Row>'
        '<Row T="RelLineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
        '</Section>'
        f'<Text>{escape(text)}</Text>'
        '</Shape>'
    )


def render_shapes(
    start_id: int,
    page_w: float,
    page_h: float,
    info: TitleBlockInfo,
) -> tuple[str, int]:
    """Return (xml, next_id) for the HEB title block on the right-edge strip."""
    if info.is_empty():
        return "", start_id

    sid = start_id
    parts: list[str] = []
    x0 = page_w - TB_WIDTH_IN
    w = TB_WIDTH_IN
    navy = "#0b3d63"

    def add(**kw) -> None:
        nonlocal sid
        parts.append(_cell_shape(sid, **kw))
        sid += 1

    # Outer frame (full strip).
    add(x=x0, y=0.0, w=w, h=page_h, fill="#FFFFFF", line="#1A1A1A",
        line_weight=0.02)

    # --- bottom: sheet number (big) -------------------------------------
    add(x=x0, y=0.0, w=w, h=1.9, text=info.sheet_number, font=0.55, bold=True,
        text_color=navy)

    # scale / proj no / date row band
    band_y = 1.9
    add(x=x0, y=band_y, w=w / 3, h=0.7, text=f"SCALE\n{info.scale}", font=0.1,
        align=0)
    add(x=x0 + w / 3, y=band_y, w=w / 3, h=0.7,
        text=f"PROJ. NO.\n{info.project_no}", font=0.1, align=0)
    add(x=x0 + 2 * w / 3, y=band_y, w=w / 3, h=0.7,
        text=f"DATE\n{info.date}", font=0.1, align=0)

    # --- sheet title + project name + address ---------------------------
    add(x=x0, y=2.6, w=w, h=1.0, text=info.sheet_title, font=0.28, bold=True,
        text_color="#1A1A1A")
    add(x=x0, y=3.6, w=w, h=1.6, text=info.project_name, font=0.34, bold=True,
        text_color=navy)
    add(x=x0, y=5.2, w=w, h=0.8, text=info.project_address, font=0.13)

    # --- H-E-B logo (oval-ish boxed wordmark) ---------------------------
    logo_y = 6.2
    add(x=x0 + w / 2 - 1.1, y=logo_y, w=2.2, h=1.1, text="H-E-B", font=0.4,
        bold=True, fill="#FFFFFF", line=navy, line_weight=0.03,
        text_color=navy)

    # --- firm / consultant of record ------------------------------------
    firm_y = 7.6
    firm_txt = info.firm + "\n" + "\n".join(info.firm_lines)
    add(x=x0, y=firm_y, w=w, h=1.8, text=firm_txt, font=0.12, align=0,
        bold=False, text_color="#1A1A1A")

    # --- engineer seal placeholder --------------------------------------
    seal_y = 9.6
    seal_txt = info.engineer or "PROFESSIONAL SEAL"
    add(x=x0 + w / 2 - 1.0, y=seal_y, w=2.0, h=1.6, text=seal_txt, font=0.11,
        line=navy, line_weight=0.015, text_color=navy)

    # --- confidentiality notice -----------------------------------------
    conf_y = 11.4
    conf = (
        "PLEASE BE ADVISED: THIS DOCUMENT MAY CONTAIN SENSITIVE AND/OR "
        "PROPRIETARY INFORMATION AND MUST BE TREATED AS CONFIDENTIAL. "
        "ACCEPTANCE CONSTITUTES AGREEMENT THAT THIS DOCUMENT AND ITS "
        "INFORMATION SHALL NOT BE REPRODUCED, RELEASED, OR DISTRIBUTED "
        "WITHOUT EXPRESS WRITTEN PERMISSION."
    )
    add(x=x0, y=conf_y, w=w, h=3.6, text=conf, font=0.105, align=0)

    # --- revision block --------------------------------------------------
    rev_y = 15.2
    add(x=x0, y=rev_y, w=w, h=0.5, text="REVISIONS", font=0.13, bold=True,
        fill="#0b3d63", text_color="#FFFFFF")
    add(x=x0, y=rev_y + 0.5, w=w, h=2.5,
        text=(info.revision or "") + (f"\n{info.date}" if info.date else ""),
        font=0.12, align=0)

    # --- status checkboxes (top) ----------------------------------------
    st_y = page_h - 2.2
    options = ["IN PRELIMINARY REVIEW", "RELEASED FOR PERMIT",
               "RELEASED FOR CONSTRUCTION"]
    row_h = 0.6
    for i, opt in enumerate(options):
        oy = st_y + (len(options) - 1 - i) * row_h
        ticked = opt.strip().upper() == (info.status or "").strip().upper()
        box_fill = navy if ticked else "#FFFFFF"
        add(x=x0 + 0.15, y=oy + 0.12, w=0.36, h=0.36, text="",
            fill=box_fill, line="#1A1A1A", line_weight=0.012)
        add(x=x0 + 0.6, y=oy, w=w - 0.7, h=row_h, text=opt, font=0.13,
            align=0, no_line=True, bold=ticked,
            text_color=navy if ticked else "#1A1A1A")

    return "".join(parts), sid
