from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.cell import column_index_from_string, get_column_letter

from core.project_model import classify_page_type, default_project, recalc_page_numbers, sanitize_json
from core.page_normalizer import normalize_page
from core.page_composer import EXCEL_EXACT_FAMILIES, EXCEL_MIN_SCALE, compose_pages, page_family

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


def _included(raw: str, sheet_title: str, use_source: str, *, in_index: bool = True) -> bool:
    """Index include column is law: only explicit YES/TRUE/include renders output."""
    text = (raw or "").strip().lower()
    cls_blob = f"{sheet_title} {use_source}".lower()
    if text in {"n", "no", "false", "0", "exclude", "off", "excluded", "disabled"}:
        return False
    if text in {"y", "yes", "true", "1", "include", "x", "✓", "on"}:
        return True
    if "disabled" in cls_blob or "not included" in cls_blob or "optional" in cls_blob:
        return False
    if "template" in cls_blob or "utility" in cls_blob:
        return False
    if in_index:
        # Blank or unrecognized include cell on an index row → excluded.
        return False
    return False


# Excel unit conversion. Column width is in "characters" of the default font;
# the classic Excel/openpyxl approximation is px ~= width * 7 + 5. Row height is
# in points; CSS px = pt * 96/72. Defaults mirror Excel's out-of-the-box sheet.
_DEFAULT_COL_PX = 64
_DEFAULT_ROW_PX = 20


def _col_width_px(width: float | None) -> int:
    if not width or width <= 0:
        return _DEFAULT_COL_PX
    return max(8, int(round(width * 7 + 5)))


def _row_height_px(height: float | None) -> int:
    if not height or height <= 0:
        return _DEFAULT_ROW_PX
    return max(8, int(round(height * 4 / 3)))


def _color_hex(color) -> str | None:
    """Return an ARGB/RGB openpyxl color as #RRGGBB, or None for default/none."""
    try:
        if color is None or getattr(color, "type", None) != "rgb":
            return None
        rgb = color.rgb
        if not rgb or not isinstance(rgb, str):
            return None
        if rgb in ("00000000", "FFFFFFFF"):
            return None
        if len(rgb) == 8:
            return "#" + rgb[2:]
        if len(rgb) == 6:
            return "#" + rgb
    except Exception:
        return None
    return None


def _cell_fill_hex(cell) -> str | None:
    """Return a solid fill color as #RRGGBB, or None."""
    try:
        fill = cell.fill
        if not fill or fill.patternType != "solid":
            return None
        return _color_hex(fill.fgColor)
    except Exception:
        return None


def _side_spec(side) -> dict[str, str] | None:
    """Return {style,color} for a single border side, or None when absent."""
    try:
        if side is None or not side.style:
            return None
        return {"style": side.style, "color": _color_hex(side.color) or "#000000"}
    except Exception:
        return None


def _cell_borders(cell) -> dict[str, Any] | None:
    """Return per-side border specs (top/right/bottom/left), or None."""
    try:
        b = cell.border
        out: dict[str, Any] = {}
        for name, side in (("top", b.top), ("right", b.right), ("bottom", b.bottom), ("left", b.left)):
            spec = _side_spec(side)
            if spec:
                out[name] = spec
        return out or None
    except Exception:
        return None


def _cell_style(cell) -> dict[str, Any]:
    """Full per-cell style for exact-range rendering. Falsy/None keys pruned."""
    font = cell.font
    align = cell.alignment
    raw: dict[str, Any] = {
        "bold": bool(getattr(font, "bold", False)),
        "italic": bool(getattr(font, "italic", False)),
        "underline": bool(getattr(font, "underline", None)),
        "fontSize": getattr(font, "size", None),
        "fontName": getattr(font, "name", None),
        "fontColor": _color_hex(getattr(font, "color", None)),
        "hAlign": getattr(align, "horizontal", None),
        "vAlign": getattr(align, "vertical", None),
        "wrap": bool(getattr(align, "wrapText", False)),
        "rotation": int(getattr(align, "textRotation", 0) or 0),
        "indent": int(getattr(align, "indent", 0) or 0),
        "fill": _cell_fill_hex(cell),
        "borders": _cell_borders(cell),
    }
    return {k: v for k, v in raw.items() if v not in (None, False, 0, "")}


def _worksheet_payload(ws, ws_data=None) -> dict[str, Any]:
    """Extract a worksheet into a render-ready payload.

    ``ws`` is loaded with formulas (data_only=False); ``ws_data`` (data_only=True)
    supplies cached calculated values so formulas display as values.
    """
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
            raw_value = cell.value
            display = raw_value
            if isinstance(raw_value, str) and raw_value.startswith("="):
                formulas[f"{col_letter}{r}"] = raw_value
                cached = ws_data.cell(r, c).value if ws_data is not None else None
                display = cached if cached is not None else ""
            value = _norm(display)
            row_vals.append(value)
            if isinstance(cell, MergedCell):
                # Placeholder cell in a merged range — keep grid value, skip style extraction.
                continue
            if cell.has_style:
                s = _cell_style(cell)
                if s:
                    styles[f"{col_letter}{r}"] = s
        grid.append(row_vals)

    while grid and not any(grid[-1]):
        grid.pop()

    n_rows = len(grid)
    n_cols = max((len(r) for r in grid), default=0)

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

    default_col = getattr(getattr(ws, "sheet_format", None), "defaultColWidth", None)
    default_row = getattr(getattr(ws, "sheet_format", None), "defaultRowHeight", None)

    col_widths_px: list[int] = []
    for c in range(1, n_cols + 1):
        dim = ws.column_dimensions.get(get_column_letter(c))
        width = dim.width if dim and dim.width else default_col
        col_widths_px.append(_col_width_px(width))

    row_heights_px: list[int] = []
    for r in range(1, n_rows + 1):
        dim = ws.row_dimensions.get(r)
        height = dim.height if dim and dim.height else default_row
        row_heights_px.append(_row_height_px(height))

    # Legacy dict forms (kept for back-compat) plus px arrays for exact rendering.
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

    print_area = None
    try:
        print_area = ws.print_area or None
        if isinstance(print_area, (list, tuple)):
            print_area = print_area[0] if print_area else None
    except Exception:
        print_area = None

    source_range = f"A1:{get_column_letter(max(n_cols, 1))}{max(n_rows, 1)}" if n_rows else ""

    return {
        "name": ws.title,
        "grid": grid,
        "formulas": formulas,
        "styles": styles,
        "mergedCells": merges,
        "rowHeights": row_heights,
        "columnWidths": column_widths,
        "colWidthsPx": col_widths_px,
        "rowHeightsPx": row_heights_px,
        "sourceSheet": ws.title,
        "sourceRange": source_range,
        "printArea": print_area,
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


def _safe_name(text: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", (text or "sheet").strip())
    return out[:40] or "sheet"


def _extract_embedded_images(ws, assets_dir, url_prefix: str, sheet_name: str) -> list[dict[str, Any]]:
    """Extract embedded worksheet images to disk; return metadata list.

    Never raises — unsupported/unknown image types are skipped.
    """
    if assets_dir is None or not url_prefix:
        return []
    out: list[dict[str, Any]] = []
    images = getattr(ws, "_images", None) or []
    for i, img in enumerate(images):
        try:
            data = None
            getter = getattr(img, "_data", None)
            if callable(getter):
                data = getter()
            if not data:
                ref = getattr(img, "ref", None)
                if hasattr(ref, "read"):
                    data = ref.read()
            if not data:
                continue
            fmt = (getattr(img, "format", None) or "png").lower()
            if fmt not in ("png", "jpg", "jpeg", "gif", "bmp", "webp"):
                fmt = "png"
            fname = f"{_safe_name(sheet_name)}_{i + 1}.{fmt}"
            (Path(assets_dir) / fname).write_bytes(data)
            anchor_cell = ""
            try:
                frm = img.anchor._from  # type: ignore[attr-defined]
                anchor_cell = f"{get_column_letter(frm.col + 1)}{frm.row + 1}"
            except Exception:
                anchor_cell = ""
            out.append(
                {
                    "id": f"xlimg_{_safe_name(sheet_name)}_{i + 1}",
                    "sheetName": sheet_name,
                    "anchorCell": anchor_cell,
                    "width": getattr(img, "width", None),
                    "height": getattr(img, "height", None),
                    "name": fname,
                    "url": f"{url_prefix}/{fname}",
                }
            )
        except Exception:
            continue
    return out


def _tabular_enough(ws: dict[str, Any]) -> bool:
    """True when a worksheet has a real grid worth rendering as an exact range."""
    grid = ws.get("grid") or []
    if len(grid) < 2:
        return False
    ncols = max((len(r) for r in grid), default=0)
    if ncols < 2:
        return False
    filled = sum(1 for row in grid for c in row if (c or "").strip())
    return filled >= 3


def _should_use_excel_exact(page_type: str, family: str, ws: dict[str, Any]) -> bool:
    """Render the worksheet range verbatim (excel_exact) for all tabular EMS pages."""
    if page_type in ("cover", "canvas", "hybrid", "underlay"):
        return False
    if not _tabular_enough(ws):
        return False
    if page_type == "index":
        return True
    if family in EXCEL_EXACT_FAMILIES or family == "text":
        return True
    return False


def _split_settings_for_page(family: str, page_type: str, use_exact: bool) -> dict[str, Any]:
    """Default continuation/pagination settings per page family.

    Index/cover/scope/workflow never auto-split. Dense tables (matrix, IDF) prefer
    scaling down to minScale before row-splitting."""
    if not use_exact:
        return {
            "splitMode": "none",
            "allowContinuation": False,
            "minScale": EXCEL_MIN_SCALE,
            "scaleMode": "fit_body",
        }

    settings: dict[str, Any] = {
        "splitMode": "auto_rows",
        "allowContinuation": True,
        "minScale": EXCEL_MIN_SCALE,
        "scaleMode": "fit_body",
    }
    if family == "matrix":
        settings["minScale"] = 0.45
    elif family == "idfTable":
        settings["minScale"] = 0.42
    elif family in ("ioSchedule", "panelDetail", "rackLayout"):
        settings["minScale"] = 0.48
    elif page_type == "index" or family == "text":
        settings.update({"splitMode": "none", "allowContinuation": False, "scaleMode": "fit_body"})
    return settings


def _excel_range_block(ws: dict[str, Any], block_id: str, split_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a self-contained excel_exact block (grid + 0-based styles + dims)."""
    grid = [list(r) for r in (ws.get("grid") or [])]
    n_rows = len(grid)
    n_cols = max((len(r) for r in grid), default=0)
    grid = [r + [""] * (n_cols - len(r)) for r in grid]

    # A1-keyed source styles -> 0-based "r:c" keys (slice/render friendly).
    styles_rc: dict[str, Any] = {}
    for key, val in (ws.get("styles") or {}).items():
        m = re.fullmatch(r"([A-Z]+)(\d+)", key)
        if not m:
            continue
        col = column_index_from_string(m.group(1)) - 1
        row = int(m.group(2)) - 1
        if 0 <= row < n_rows and 0 <= col < n_cols:
            styles_rc[f"{row}:{col}"] = val

    col_widths = list(ws.get("colWidthsPx") or [])
    col_widths = (col_widths + [64] * n_cols)[:n_cols]
    row_heights = list(ws.get("rowHeightsPx") or [])
    row_heights = (row_heights + [20] * n_rows)[:n_rows]

    # Header band: leading consecutive rows that are bold or filled (the yellow
    # controller / gray column headers). Repeated on continuation pages.
    header_rows = 0
    for r in range(min(n_rows, 4)):
        styled = any(
            (styles_rc.get(f"{r}:{c}", {}).get("bold") or styles_rc.get(f"{r}:{c}", {}).get("fill"))
            for c in range(n_cols)
        )
        has_text = any((grid[r][c] or "").strip() for c in range(n_cols))
        if styled and has_text:
            header_rows = r + 1
        else:
            break
    if header_rows == 0 and n_rows:
        header_rows = 1

    ss = split_settings or {}

    return {
        "id": block_id,
        "type": "excelRange",
        "sourceWorksheetId": ws["id"],
        "sourceSheet": ws.get("sourceSheet") or ws.get("name", ""),
        "sourceRange": ws.get("sourceRange", ""),
        "printArea": ws.get("printArea"),
        "renderMode": "excel_exact",
        "grid": grid,
        "styles": styles_rc,
        "mergedCells": ws.get("mergedCells") or [],
        "colWidths": col_widths,
        "rowHeights": row_heights,
        "srcRows": list(range(n_rows)),
        "headerRowCount": header_rows,
        "repeatRows": list(range(header_rows)),
        "splitMode": ss.get("splitMode", "auto_rows"),
        "minScale": ss.get("minScale", EXCEL_MIN_SCALE),
        "allowContinuation": ss.get("allowContinuation", True),
        "scaleMode": ss.get("scaleMode", "fit_body"),
        "orientation": "landscape",
        "styleRole": "excel-exact",
        "editable": True,
    }


def import_workbook(
    path: str | Path,
    project_id: str | None = None,
    assets_dir=None,
    asset_url_prefix: str | None = None,
) -> dict[str, Any]:
    xlsx = Path(path)
    wb = load_workbook(filename=xlsx, data_only=False)
    try:
        wb_data = load_workbook(filename=xlsx, data_only=True)
    except Exception:
        wb_data = None

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

    sheet_payloads = [
        _worksheet_payload(
            wb[sheet_name],
            wb_data[sheet_name] if wb_data is not None and sheet_name in wb_data.sheetnames else None,
        )
        for sheet_name in wb.sheetnames
    ]
    embedded_by_sheet: dict[str, list[dict[str, Any]]] = {}
    for sheet_name in wb.sheetnames:
        embedded_by_sheet[sheet_name] = _extract_embedded_images(
            wb[sheet_name], assets_dir, asset_url_prefix or "", sheet_name
        )

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
                "colWidthsPx": ws["colWidthsPx"],
                "rowHeightsPx": ws["rowHeightsPx"],
                "sourceSheet": ws["sourceSheet"],
                "sourceRange": ws["sourceRange"],
                "printArea": ws["printArea"],
                "embeddedImages": embedded_by_sheet.get(ws["name"], []),
                "provenance": {"sheet": ws["name"]},
            }
        )

    index_entries = _parse_index(wb, _find_index_sheet(wb))
    index_sheet_name = _find_index_sheet(wb)
    has_index = bool(index_sheet_name and index_entries)
    index_lookup = {e["sheetTab"].lower(): e for e in index_entries if e.get("sheetTab")}

    pages = []
    order_cursor = 1
    for i, ws in enumerate(project["worksheets"]):
        idx = index_lookup.get(ws["name"].lower())
        title = idx["sheetTitle"] if idx else ws["name"]
        include = idx["include"] if idx else (not has_index)
        use_source = idx["useSource"] if idx else ""

        # Index include/exclude is law: no output page/tab/PDF for excluded sheets.
        if not include:
            continue

        page_type = classify_page_type(ws["name"], title, use_source)
        family = page_family(ws["name"], title, use_source)

        use_exact = _should_use_excel_exact(page_type, family, ws)
        split_settings = _split_settings_for_page(family, page_type, use_exact)

        if use_exact:
            exact_block = _excel_range_block(ws, f"{ws['id']}_xr", split_settings)
            blocks = [exact_block]
        else:
            exact_block = None
            blocks = normalize_page(ws, ws["id"], page_type, title)

            # Embedded workbook images → real image blocks (rendered, not placeholders).
            for j, emb in enumerate(ws.get("embeddedImages", []) or []):
                blocks.append(
                    {
                        "id": f"{ws['id']}_emb_{j}",
                        "type": "imagePlaceholder",
                        "sourceWorksheetId": ws["id"],
                        "sourceRange": emb.get("anchorCell", ""),
                        "filename": emb.get("name", ""),
                        "url": emb.get("url", ""),
                        "text": emb.get("name", ""),
                        "styleRole": "note",
                        "editable": False,
                    }
                )

        page = {
            "id": f"page_{i+1}",
            "order": order_cursor,
            "include": include,
            "sheetCode": idx["orderRaw"] if idx and idx["orderRaw"] else str(order_cursor),
            "displaySheetCode": idx["orderRaw"] if idx and idx["orderRaw"] else str(order_cursor),
            "sheetTitle": title,
            "sheetTab": ws["name"],
            "pageType": page_type,
            "pageFamily": family,
            "renderMode": "excel_exact" if use_exact else "normalized",
            "sourceSheet": ws.get("sourceSheet") or ws["name"],
            "sourceRange": ws.get("sourceRange", "") if use_exact else "",
            "printArea": ws.get("printArea") if use_exact else None,
            "splitMode": split_settings.get("splitMode", "none"),
            "repeatRows": (exact_block.get("repeatRows", []) if exact_block else []),
            "minScale": split_settings.get("minScale", EXCEL_MIN_SCALE),
            "allowContinuation": split_settings.get("allowContinuation", False),
            "scaleMode": split_settings.get("scaleMode", "fit_width"),
            "orientation": "landscape",
            "templateId": "ansi-b-standard",
            "linkedWorksheetId": ws["id"],
            "blocks": blocks,
            "canvasObjects": [],
            "assets": [],
            "underlays": [],
            "notes": idx["notes"] if idx else "",
            "revisionRows": [],
            "pageGroupId": f"page_{i+1}",
            "continuationOf": None,
            "continuationIndex": 0,
            "generatedContinuation": False,
            "layoutWarnings": [],
        }
        pages.append(page)
        order_cursor += 1

    pages = sorted(pages, key=lambda p: p["order"])
    project["pages"] = compose_pages(pages)
    project["paginationLocked"] = True
    recalc_page_numbers(project)
    return sanitize_json(project)
