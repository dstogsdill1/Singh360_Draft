from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.cell import get_column_letter

from core.project_model import classify_page_type, default_project, recalc_page_numbers, sanitize_json
from core.page_normalizer import normalize_page

_INDEX_ALIASES = {
    "include": {"include", "inc", "include?", "use?", "selected"},
    "order": {"order", "no", "num", "seq", "sheet no", "sheet no."},
    "sheet_tab": {"sheet tab", "sheet", "worksheet", "tab", "tab name"},
    "sheet_title": {"page title", "title", "sheet title", "page name", "name"},
    "use_source": {"use", "source", "use / source", "use/source", "type"},
    "notes": {"notes", "remarks", "description", "comment"},
}


def _norm(v: Any) -> str:
    if v is None:
        return ""
    text = " ".join(str(v).split()).strip()
    return "" if text.lower() in {"nan", "nat", "<na>", "none"} else text


def _find_index_sheet(workbook) -> str | None:
    for name in workbook.sheetnames:
        key = name.replace(" ", "").replace("_", "").upper()
        if "INDEX" in key:
            return name
    return None


def _header_map(header_row: list[str]) -> dict[str, int]:
    normed = [h.lower() for h in header_row]
    out: dict[str, int] = {}
    for key, aliases in _INDEX_ALIASES.items():
        out[key] = -1
        for i, cell in enumerate(normed):
            if cell in aliases:
                out[key] = i
                break
    return out


def _included(raw: str, sheet_title: str, use_source: str) -> bool:
    text = (raw or "").strip().lower()
    cls_blob = f"{sheet_title} {use_source}".lower()
    if text in {"n", "no", "false", "0", "exclude", "off", "excluded"}:
        return False
    if text in {"y", "yes", "true", "1", "include", "x", "✓"}:
        return True
    if "template" in cls_blob or "utility" in cls_blob:
        return False
    return True


def _cell_fill_hex(cell) -> str | None:
    """Return a solid fill color as #RRGGBB, or None."""
    try:
        fill = cell.fill
        if not fill or fill.patternType != "solid":
            return None
        fg = fill.fgColor
        if fg is None or getattr(fg, "type", None) != "rgb":
            return None
        rgb = fg.rgb
        if not rgb or rgb in ("00000000", "FFFFFFFF"):
            return None
        if len(rgb) == 8:
            return "#" + rgb[2:]
        if len(rgb) == 6:
            return "#" + rgb
    except Exception:
        return None
    return None


def _cell_has_border(cell) -> bool:
    try:
        b = cell.border
        return any(side is not None and side.style for side in (b.left, b.right, b.top, b.bottom))
    except Exception:
        return False


def _worksheet_payload(ws) -> dict[str, Any]:
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    grid: list[list[str]] = []
    formulas: dict[str, str] = {}
    styles: dict[str, dict[str, Any]] = {}

    for r in range(1, max_row + 1):
        row_vals: list[str] = []
        for c in range(1, max_col + 1):
            cell = ws.cell(r, c)
            col_letter = get_column_letter(c)
            value = _norm(cell.value)
            row_vals.append(value)
            if isinstance(cell, MergedCell):
                # Placeholder cell in a merged range — keep grid value, skip style/formula extraction.
                continue
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formulas[f"{col_letter}{r}"] = cell.value
            if cell.has_style:
                s: dict[str, Any] = {
                    "bold": bool(getattr(cell.font, "bold", False)),
                    "italic": bool(getattr(cell.font, "italic", False)),
                    "underline": bool(getattr(cell.font, "underline", None)),
                    "fontSize": getattr(cell.font, "size", None),
                    "hAlign": getattr(cell.alignment, "horizontal", None),
                    "vAlign": getattr(cell.alignment, "vertical", None),
                    "fill": _cell_fill_hex(cell),
                    "border": _cell_has_border(cell),
                }
                if any(v not in (None, False) for v in s.values()):
                    styles[f"{col_letter}{r}"] = s
        grid.append(row_vals)

    while grid and not any(grid[-1]):
        grid.pop()

    merges = []
    for merged in ws.merged_cells.ranges:
        merges.append(
            {
                "startRow": merged.min_row - 1,
                "startCol": merged.min_col - 1,
                "endRow": merged.max_row - 1,
                "endCol": merged.max_col - 1,
            }
        )

    row_heights = {
        str(idx): dim.height
        for idx, dim in ws.row_dimensions.items()
        if dim.height is not None
    }
    column_widths = {
        str(idx): dim.width
        for idx, dim in ws.column_dimensions.items()
        if dim.width is not None
    }

    return {
        "name": ws.title,
        "grid": grid,
        "formulas": formulas,
        "styles": styles,
        "mergedCells": merges,
        "rowHeights": row_heights,
        "columnWidths": column_widths,
    }


def _parse_index(workbook, index_sheet_name: str | None) -> list[dict[str, Any]]:
    if not index_sheet_name:
        return []

    ws = workbook[index_sheet_name]
    rows = [[_norm(c.value) for c in row] for row in ws.iter_rows()]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []

    header_idx = 0
    for i, row in enumerate(rows[:20]):
        low = {x.lower() for x in row if x}
        if low & _INDEX_ALIASES["sheet_tab"] and low & _INDEX_ALIASES["sheet_title"]:
            header_idx = i
            break

    header = rows[header_idx]
    col = _header_map(header)

    entries = []
    for row in rows[header_idx + 1 :]:
        tab = row[col["sheet_tab"]] if 0 <= col["sheet_tab"] < len(row) else ""
        title = row[col["sheet_title"]] if 0 <= col["sheet_title"] < len(row) else ""
        use_source = row[col["use_source"]] if 0 <= col["use_source"] < len(row) else ""
        notes = row[col["notes"]] if 0 <= col["notes"] < len(row) else ""
        include_raw = row[col["include"]] if 0 <= col["include"] < len(row) else ""
        order_raw = row[col["order"]] if 0 <= col["order"] < len(row) else ""

        if not tab and not title:
            continue

        entries.append(
            {
                "sheetTab": tab,
                "sheetTitle": title or tab,
                "useSource": use_source,
                "notes": notes,
                "orderRaw": order_raw,
                "include": _included(include_raw, title or tab, use_source),
            }
        )

    return entries


def import_workbook(path: str | Path, project_id: str | None = None) -> dict[str, Any]:
    xlsx = Path(path)
    wb = load_workbook(filename=xlsx, data_only=False)

    project = default_project(project_id)
    project["metadata"]["sourceFile"] = xlsx.name

    project["sources"].append(
        {
            "id": f"src_{project['id']}_xlsx",
            "type": "workbook",
            "name": xlsx.name,
            "path": str(xlsx),
        }
    )

    sheet_payloads = [_worksheet_payload(wb[sheet_name]) for sheet_name in wb.sheetnames]

    for i, ws in enumerate(sheet_payloads):
        project["worksheets"].append(
            {
                "id": f"ws_{i+1}",
                "name": ws["name"],
                "sourceId": f"src_{project['id']}_xlsx",
                "visible": True,
                "classHint": "unknown",
                "grid": ws["grid"],
                "formulas": ws["formulas"],
                "styles": ws["styles"],
                "mergedCells": ws["mergedCells"],
                "rowHeights": ws["rowHeights"],
                "columnWidths": ws["columnWidths"],
                "provenance": {"sheet": ws["name"]},
            }
        )

    index_entries = _parse_index(wb, _find_index_sheet(wb))
    index_lookup = {e["sheetTab"].lower(): e for e in index_entries if e.get("sheetTab")}

    pages = []
    order_cursor = 1
    for i, ws in enumerate(project["worksheets"]):
        idx = index_lookup.get(ws["name"].lower())
        title = idx["sheetTitle"] if idx else ws["name"]
        include = idx["include"] if idx else True
        page_type = classify_page_type(ws["name"], title, idx["useSource"] if idx else "")

        blocks = normalize_page(ws, ws["id"], page_type, title)

        page = {
            "id": f"page_{i+1}",
            "order": order_cursor,
            "include": include,
            "sheetCode": idx["orderRaw"] if idx and idx["orderRaw"] else str(order_cursor),
            "sheetTitle": title,
            "sheetTab": ws["name"],
            "pageType": page_type,
            "templateId": "ansi-b-standard",
            "linkedWorksheetId": ws["id"],
            "blocks": blocks,
            "canvasObjects": [],
            "underlays": [],
            "notes": idx["notes"] if idx else "",
            "revisionRows": [],
        }
        pages.append(page)
        order_cursor += 1

    project["pages"] = sorted(pages, key=lambda p: p["order"])
    recalc_page_numbers(project)
    return sanitize_json(project)
