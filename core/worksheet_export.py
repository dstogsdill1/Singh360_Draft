"""Export a project worksheet back to a standalone .xlsx file."""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _safe_sheet_title(name: str) -> str:
    t = re.sub(r"[\[\]:*?/\\]", "_", (name or "Sheet").strip())[:31]
    return t or "Sheet"


def _a1_to_rc(key: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"([A-Z]+)(\d+)", (key or "").upper())
    if not m:
        return None
    letters, row_s = m.group(1), m.group(2)
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - 64)
    return int(row_s) - 1, col - 1


def _side(style: dict[str, Any] | None) -> Side | None:
    if not style:
        return None
    return Side(style=style.get("style", "thin"), color=style.get("color", "000000"))


def export_worksheet_xlsx(ws: dict[str, Any]) -> bytes:
    """Write one worksheet dict (grid + styles + merges + sizes) to xlsx bytes."""
    wb = Workbook()
    sheet = wb.active
    sheet.title = _safe_sheet_title(str(ws.get("name") or ws.get("sourceSheet") or "Sheet"))

    grid = ws.get("grid") if isinstance(ws.get("grid"), list) else []
    styles = ws.get("styles") if isinstance(ws.get("styles"), dict) else {}
    col_widths = ws.get("colWidthsPx") if isinstance(ws.get("colWidthsPx"), list) else []
    row_heights = ws.get("rowHeightsPx") if isinstance(ws.get("rowHeightsPx"), list) else []

    for r, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        for c, val in enumerate(row):
            cell = sheet.cell(row=r + 1, column=c + 1, value=val)
            st = styles.get(f"{get_column_letter(c + 1)}{r + 1}")
            if not isinstance(st, dict):
                continue
            font = Font(
                bold=bool(st.get("bold")),
                italic=bool(st.get("italic")),
                underline="single" if st.get("underline") else None,
                size=st.get("fontSize") or 11,
                color=(st.get("fontColor") or "000000").lstrip("#"),
            )
            fill_color = st.get("fill")
            fill = PatternFill("solid", fgColor=fill_color.lstrip("#")) if fill_color else None
            borders = st.get("borders") if isinstance(st.get("borders"), dict) else {}
            border = Border(
                left=_side(borders.get("left")),
                right=_side(borders.get("right")),
                top=_side(borders.get("top")),
                bottom=_side(borders.get("bottom")),
            )
            align = Alignment(
                horizontal=st.get("hAlign") or "general",
                vertical=st.get("vAlign") or "bottom",
                wrap_text=bool(st.get("wrap")),
            )
            cell.font = font
            if fill:
                cell.fill = fill
            cell.border = border
            cell.alignment = align

    for c, w in enumerate(col_widths):
        if w:
            sheet.column_dimensions[get_column_letter(c + 1)].width = max(3, min(80, w / 7))

    for r, h in enumerate(row_heights):
        if h:
            sheet.row_dimensions[r + 1].height = max(12, min(120, h * 0.75))

    for m in ws.get("mergedCells") or []:
        if not isinstance(m, dict):
            continue
        sr, sc = int(m.get("startRow", 0)), int(m.get("startCol", 0))
        er, ec = int(m.get("endRow", sr)), int(m.get("endCol", sc))
        sheet.merge_cells(
            start_row=sr + 1,
            start_column=sc + 1,
            end_row=er + 1,
            end_column=ec + 1,
        )

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
