from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils.cell import column_index_from_string, get_column_letter

from core.project_model import classify_page_type, default_project, recalc_page_numbers, sanitize_json
from core.page_normalizer import normalize_page
from core.page_composer import (
    BODY_BUDGET,
    BODY_W,
    EXCEL_EXACT_FAMILIES,
    EXCEL_MIN_SCALE,
    compose_pages,
    log_render_diagnostics,
    page_family,
)
from core.table_style_profile import (
    ABSOLUTE_MIN_FONT_SIZE,
    DENSE_FONT_SIZE,
    RENDER_PROFILE,
    apply_singh360_profile,
)

# Default Singh360 normalized header style applied to every non-cover page.
DEFAULT_HEADER_STYLE = "orange"

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


def _remap_a1_styles(styles: dict[str, Any], row_map: dict[int, int]) -> dict[str, Any]:
    """Copy A1-keyed styles for retained rows, remapping row numbers."""
    out: dict[str, Any] = {}
    for key, val in (styles or {}).items():
        m = re.fullmatch(r"([A-Z]+)(\d+)", key)
        if not m:
            continue
        old_r = int(m.group(2)) - 1
        if old_r not in row_map:
            continue
        out[f"{m.group(1)}{row_map[old_r] + 1}"] = val
    return out


def _filter_index_payload_for_output(ws: dict[str, Any]) -> dict[str, Any]:
    """Return an index worksheet payload containing included rows only.

    Source tabs keep the original workbook unchanged; this filtered payload is
    used only for the normalized/output Sheet Index page.
    """
    grid = ws.get("grid") or []
    if not grid:
        return ws

    header_idx = 0
    for i, row in enumerate(grid[:20]):
        low = {str(x).lower() for x in row if x}
        if low & _INDEX_ALIASES["sheet_tab"] and low & _INDEX_ALIASES["sheet_title"]:
            header_idx = i
            break
    col = _header_map([str(x) for x in grid[header_idx]])
    include_col = col.get("include", -1)
    if include_col < 0:
        return ws

    keep: list[int] = list(range(header_idx + 1))
    for r in range(header_idx + 1, len(grid)):
        row = grid[r]
        include_raw = row[include_col] if include_col < len(row) else ""
        title = row[col["sheet_title"]] if 0 <= col["sheet_title"] < len(row) else ""
        use_source = row[col["use_source"]] if 0 <= col["use_source"] < len(row) else ""
        if _included(include_raw, title, use_source):
            keep.append(r)

    row_map = {old: new for new, old in enumerate(keep)}
    out = dict(ws)
    out["grid"] = [list(grid[r]) for r in keep if r < len(grid)]
    out["styles"] = _remap_a1_styles(ws.get("styles") or {}, row_map)
    out["rowHeightsPx"] = [
        (ws.get("rowHeightsPx") or [])[r] if r < len(ws.get("rowHeightsPx") or []) else _DEFAULT_ROW_PX
        for r in keep
    ]
    # Keep only merges whose full row span survived the filter.
    merges = []
    for m in ws.get("mergedCells") or []:
        rows = range(m.get("startRow", 0), m.get("endRow", 0) + 1)
        if all(r in row_map for r in rows):
            nm = dict(m)
            ns = [row_map[r] for r in rows]
            nm["startRow"], nm["endRow"] = min(ns), max(ns)
            merges.append(nm)
    out["mergedCells"] = merges
    return out


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
    if family == "companyInfo":
        return False
    if page_type in ("cover", "canvas", "hybrid", "underlay"):
        return False
    if not _tabular_enough(ws):
        return False
    if page_type == "index":
        return True
    if family in EXCEL_EXACT_FAMILIES or family == "text":
        return True
    return False


def _looks_company_info(sheet_tab: str, title: str, use_source: str = "") -> bool:
    blob = f"{sheet_tab} {title} {use_source}".lower()
    return "company info" in blob or "singh360 company" in blob or "company/reference" in blob


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
        settings["minScale"] = EXCEL_MIN_SCALE
    elif family == "idfTable":
        # Fallback safety net for IDF-ish sheets that aren't detected as a
        # Port/Label network table (those get the dedicated two-up layout
        # instead); keeps this rare fallback above the 6.5pt readable floor.
        settings["minScale"] = 0.75
    elif family in ("ioSchedule", "panelDetail", "rackLayout"):
        settings["minScale"] = 0.75
    elif page_type == "index" or family == "text":
        settings.update({"splitMode": "none", "allowContinuation": False, "scaleMode": "fit_body"})
    return settings


def _layout_profile_for(family: str, page_type: str, blob: str) -> str:
    """Rendering-options profile per page type (TABLE STYLE 4F, Phase D)."""
    if family == "companyInfo":
        return "company_info"
    if family == "idfTable":
        return "network_48_port"
    if family in ("matrix", "ioSchedule", "panelDetail", "rackLayout"):
        return "io_table"
    if family == "text" and "instruction" in blob:
        return "instruction_table"
    return "front_matter_table"


# --------------------------------------------------------------------------
# RDM / IDF network table — special two-up layout (TABLE STYLE 4F, Phase B).
#
# Default is always ONE full-width table (no rotation). Only when the real
# port count makes a single stack unreadable does the layout switch to a
# two-up (ports 1-N / N+1-total) side-by-side layout with essential columns
# only. Never invents data: a column with no source match renders blank.
# --------------------------------------------------------------------------
_IDF_TARGET_FONT = DENSE_FONT_SIZE  # 7.0pt
_IDF_MIN_FONT = ABSOLUTE_MIN_FONT_SIZE  # 6.5pt
_IDF_ROW_H = 20
_IDF_HEADER_H = 24
_IDF_COL_W = {
    "Port": 46,
    "Label": 72,
    "Device / Drop": 170,
    "From": 92,
    "To": 92,
    "Path": 170,
    "Cable": 90,
    "Notes": 220,
    "Controller / IP": 140,
    "Controller ID": 90,
    "IP Address": 100,
    "Network": 90,
}


def _idf_col_index(headers: list[str], *keys: str) -> int | None:
    low = [str(h or "").strip().lower() for h in headers]
    for i, h in enumerate(low):
        if any(k in h for k in keys):
            return i
    return None


def _idf_header_row(grid: list[list[str]]) -> int | None:
    """First row (within the leading 6) that looks like a Port/Label header."""
    for r, row in enumerate(grid[:6]):
        low = [str(c or "").strip().lower() for c in row]
        has_port = any("port" in c for c in low)
        has_id = any(("label" in c) or ("device" in c) or ("drop" in c) for c in low)
        if has_port and has_id:
            return r
    return None


def _is_idf_network_table(ws: dict[str, Any], family: str) -> tuple[bool, int | None]:
    if family != "idfTable":
        return False, None
    header_row = _idf_header_row(ws.get("grid") or [])
    return header_row is not None, header_row


def _idf_columns(headers: list[str]) -> list[tuple[str, tuple[int, ...]]]:
    """Map source headers onto the essential RDM/IDF network columns, only
    combining optional detail columns (Controller ID + IP Address, Network +
    Cable, From + To) when needed to keep the column count readable."""
    idx = {
        "port": _idf_col_index(headers, "port"),
        "label": _idf_col_index(headers, "label"),
        "device": _idf_col_index(headers, "device", "drop", "location"),
        "from": _idf_col_index(headers, "from"),
        "to": _idf_col_index(headers, "to"),
        "cable": _idf_col_index(headers, "cable"),
        "notes": _idf_col_index(headers, "notes", "remark", "comment"),
        "controllerId": _idf_col_index(headers, "controller id", "controller"),
        "ip": _idf_col_index(headers, "ip address", "ip addr", "ip"),
        "network": _idf_col_index(headers, "network", "vlan"),
    }
    cols: list[tuple[str, tuple[int, ...]]] = [
        ("Port", (idx["port"],) if idx["port"] is not None else ()),
        ("Label", (idx["label"],) if idx["label"] is not None else ()),
        ("Device / Drop", (idx["device"],) if idx["device"] is not None else ()),
        ("From", (idx["from"],) if idx["from"] is not None else ()),
        ("To", (idx["to"],) if idx["to"] is not None else ()),
        ("Cable", (idx["cable"],) if idx["cable"] is not None else ()),
        ("Notes", (idx["notes"],) if idx["notes"] is not None else ()),
    ]
    cols = [c for c in cols if c[1] or c[0] in ("Port", "Label", "Device / Drop")]

    detail: list[tuple[str, tuple[int, ...]]] = []
    if idx["controllerId"] is not None and idx["ip"] is not None:
        detail.append(("Controller / IP", (idx["controllerId"], idx["ip"])))
    elif idx["controllerId"] is not None:
        detail.append(("Controller ID", (idx["controllerId"],)))
    elif idx["ip"] is not None:
        detail.append(("IP Address", (idx["ip"],)))
    if idx["network"] is not None:
        detail.append(("Network", (idx["network"],)))
    cols = cols + detail

    # Only combine From/To -> Path if the column count is still too wide.
    if len(cols) > 9 and idx["from"] is not None and idx["to"] is not None:
        cols = [c for c in cols if c[0] not in ("From", "To")]
        cols.insert(3, ("Path", (idx["from"], idx["to"])))
    return cols


def _idf_cell_value(row: list[str], spec: tuple[int, ...]) -> str:
    parts = [str(row[i]).strip() for i in spec if i < len(row) and str(row[i] or "").strip()]
    return " / ".join(parts)


def _build_idf_network_block(ws: dict[str, Any], header_row: int, block_id: str) -> dict[str, Any]:
    """Build the special RDM/IDF network table block (single full-width table
    by default; two-up ports 1-N / N+1-total only when a single stack would
    fall below the readable font floor)."""
    grid = ws.get("grid") or []
    headers_src = grid[header_row] if header_row < len(grid) else []
    cols = _idf_columns(headers_src)
    headers = [c[0] for c in cols]
    col_widths = [_IDF_COL_W.get(h, 90) for h in headers]

    data_rows: list[list[str]] = []
    for row in grid[header_row + 1:]:
        vals = [_idf_cell_value(row, spec) for _, spec in cols]
        if any(v for v in vals):
            data_rows.append(vals)
    n = len(data_rows)

    title_lines = []
    for row in grid[:header_row]:
        line = " ".join(str(c).strip() for c in row if str(c or "").strip())
        if line:
            title_lines.append(line)
    section_title = " — ".join(title_lines)

    single_w = sum(col_widths)
    usable_w = BODY_W - 80
    single_h = _IDF_HEADER_H + n * _IDF_ROW_H
    half = (n + 1) // 2 if n else 0
    two_up_h = _IDF_HEADER_H + half * _IDF_ROW_H

    warnings: list[str] = []
    if single_w <= usable_w and single_h <= BODY_BUDGET:
        layout_mode = "single"
        font_size = _IDF_TARGET_FONT
    else:
        layout_mode = "two_up"
        font_size = _IDF_TARGET_FONT
        if two_up_h > BODY_BUDGET:
            font_size = _IDF_MIN_FONT
            warnings.append(
                f"Network table has {n} rows; two-up layout is dense at the {_IDF_MIN_FONT}pt floor."
            )

    left_rows = data_rows[:half] if layout_mode == "two_up" else []
    right_rows = data_rows[half:] if layout_mode == "two_up" else []
    port_left = f"1–{half}" if half else ""
    port_right = f"{half + 1}–{n}" if n > half else ""

    return {
        "id": block_id,
        "type": "idfNetworkTable",
        "sourceWorksheetId": ws["id"],
        "sourceSheet": ws.get("sourceSheet") or ws.get("name", ""),
        "sourceRange": ws.get("sourceRange", ""),
        "renderMode": "excel_exact",
        "layoutMode": layout_mode,
        "sectionTitle": section_title,
        "headers": headers,
        "rows": data_rows if layout_mode == "single" else [],
        "leftRows": left_rows,
        "rightRows": right_rows,
        "portRangeLeft": port_left,
        "portRangeRight": port_right,
        "colWidths": col_widths,
        "fontSize": font_size,
        "contentWidth": single_w if layout_mode == "single" else single_w,
        "contentHeight": single_h if layout_mode == "single" else two_up_h,
        "sourceRowCount": n,
        "bodyRowFillMode": "none",
        "gridLines": True,
        "styleRole": "network-two-up",
        "splitMode": "none",
        "allowContinuation": False,
        "minScale": 1.0,
        "scaleMode": "fit_body",
        "orientation": "landscape",
        "editable": False,
        "layoutWarnings": warnings,
    }


def _preferred_col_widths(grid: list[list[str]], family: str, page_type: str) -> list[int]:
    """Deterministic normalized column sizing before placement/export."""
    n_cols = max((len(r) for r in grid), default=0)
    if not n_cols:
        return []
    target = BODY_W - (96 if family not in ("ioSchedule", "panelDetail", "idfTable") else 48)
    min_w = 52 if family in ("ioSchedule", "panelDetail", "idfTable") else 76
    max_w = 360 if family in ("text", "index") else 300
    weights: list[float] = []
    header = grid[0] if grid else []
    for c in range(n_cols):
        values = [str(row[c]) if c < len(row) else "" for row in grid]
        max_len = max((len(v) for v in values), default=1)
        head = (str(header[c]) if c < len(header) else "").lower()
        weight = max(6.0, min(float(max_len), 48.0))
        if any(k in head for k in ("description", "notes", "instruction", "scope", "remarks", "location")):
            weight *= 1.9
        elif any(k in head for k in ("no", "#", "id", "qty", "type", "addr", "i/o", "io", "point", "ckt")):
            weight *= 0.75
        weights.append(weight)
    total = sum(weights) or 1.0
    raw = [int(round(target * w / total)) for w in weights]
    widths = [max(min_w, min(max_w, w)) for w in raw]
    # Distribute leftover width so small tables use the page instead of floating.
    diff = target - sum(widths)
    guard = 0
    while diff > 0 and guard < 2000:
        changed = False
        for i in sorted(range(n_cols), key=lambda x: weights[x], reverse=True):
            if widths[i] < max_w:
                widths[i] += 1
                diff -= 1
                changed = True
                if diff <= 0:
                    break
        if not changed:
            break
        guard += 1
    return widths


def _estimated_row_heights(grid: list[list[str]], col_widths: list[int], family: str, header_rows: int) -> list[int]:
    font_px = 12 if family in ("matrix", "idfTable", "ioSchedule", "panelDetail", "rackLayout") else 13
    line_h = int(round(font_px * 1.22))
    out: list[int] = []
    for r, row in enumerate(grid):
        max_lines = 1
        for c, val in enumerate(row):
            text = " ".join(str(val or "").split())
            if not text:
                continue
            w = max(36, (col_widths[c] if c < len(col_widths) else _DEFAULT_COL_PX) - 8)
            chars = max(7, int(w / max(5.5, font_px * 0.48)))
            words = text.split()
            lines = 1
            cur = 0
            for word in words:
                wl = len(word)
                if cur and cur + 1 + wl > chars:
                    lines += 1
                    cur = wl
                else:
                    cur = cur + (1 if cur else 0) + wl
            max_lines = max(max_lines, min(lines, 8))
        base = 28 if r < header_rows else 24
        out.append(max(base, line_h * max_lines + 8))
    return out


def _apply_table_geometry(block: dict[str, Any], family: str, page_type: str) -> None:
    """Auto-size columns and rows for normalized/output table geometry."""
    grid = block.get("grid") or []
    if not grid:
        return
    widths = _preferred_col_widths(grid, family, page_type)
    if widths:
        block["colWidths"] = widths
    header_rows = int(block.get("headerRowCount") or 1)
    block["rowHeights"] = _estimated_row_heights(grid, block.get("colWidths") or widths, family, header_rows)
    block["pageFamily"] = family
    block["bodyRowFillMode"] = "none"
    block["gridLines"] = True


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
        "bodyRowFillMode": "none",
        "gridLines": True,
        "editable": True,
    }


def _company_info_block(ws: dict[str, Any], block_id: str) -> dict[str, Any]:
    rows = []
    for row in ws.get("grid") or []:
        vals = [str(c).strip() for c in row if str(c).strip()]
        if vals:
            rows.append(vals)
    return {
        "id": block_id,
        "type": "companyInfo",
        "sourceWorksheetId": ws["id"],
        "sourceSheet": ws.get("sourceSheet") or ws.get("name", ""),
        "rows": rows,
        "text": "Singh360 Company Info",
        "styleRole": "company-info",
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
        if _looks_company_info(ws["name"], title, use_source):
            family = "companyInfo"

        use_exact = _should_use_excel_exact(page_type, family, ws)
        split_settings = _split_settings_for_page(family, page_type, use_exact)
        is_idf_network, idf_header_row = _is_idf_network_table(ws, family)
        layout_profile = _layout_profile_for(family, page_type, f"{ws['name']} {title} {use_source}".lower())

        # Cover keeps its own look; every other page gets the Singh360 profile.
        header_style = "source" if page_type == "cover" else DEFAULT_HEADER_STYLE

        if family == "companyInfo":
            exact_block = None
            blocks = [_company_info_block(ws, f"{ws['id']}_company")]
        elif is_idf_network and idf_header_row is not None:
            split_settings = {"splitMode": "none", "allowContinuation": False, "minScale": 1.0, "scaleMode": "fit_body"}
            exact_block = _build_idf_network_block(ws, idf_header_row, f"{ws['id']}_idf")
            use_exact = True
            blocks = [exact_block]
        elif use_exact:
            render_ws = _filter_index_payload_for_output(ws) if page_type == "index" else ws
            exact_block = _excel_range_block(render_ws, f"{ws['id']}_xr", split_settings)
            if "lighting" in f"{ws['name']} {title}".lower():
                exact_block["minScale"] = max(float(exact_block.get("minScale") or EXCEL_MIN_SCALE), 0.58)
            _apply_table_geometry(exact_block, family, page_type)
            apply_singh360_profile(exact_block, header_style)
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
            "layoutProfile": layout_profile,
            "twoUp": bool(exact_block and exact_block.get("layoutMode") == "two_up"),
            "renderMode": "excel_exact" if use_exact else "normalized",
            "renderProfile": RENDER_PROFILE,
            "normalizedHeaderStyle": header_style,
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
    try:
        log_render_diagnostics(project["pages"])
    except Exception:
        pass
    return sanitize_json(project)
