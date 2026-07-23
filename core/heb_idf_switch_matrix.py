"""H-E-B IDF switch-matrix import support.

This module handles the H-E-B workbook layout whose real table columns are:

    Label # | Description | Controller ID | IP Address | IDF# | Switch# | Port#

The source workbook can also contain a title row and an RDM controller-ID legend
outside that seven-column table.  Those cells are reference material and must not
be promoted into published network-table columns.

The builder groups rows by (IDF#, Switch#) and renders at most two switch tables
side by side per drawing page, matching the issued H-E-B network-table layout.
It never changes source values; worksheet-name/source-ID conflicts are reported
as warnings.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from copy import deepcopy
from math import ceil
from typing import Any, Iterable

from core.page_composer import continuation_code

PATCH_MARKER = "S360_HEB_IDF_SWITCH_MATRIX_V1"
TABLE_PROFILE = "heb_idf_switch_matrix"

# Exact published order and labels requested for the H-E-B IDF table.
HEB_HEADERS = [
    "Label #",
    "Description",
    "Controller ID",
    "IP Address",
    "IDF#",
    "Switch#",
    "Port#",
]

# Two 7-column tables fit comfortably in the 1600px Singh360 drawing body.
HEB_COL_WIDTHS = [98, 354, 98, 86, 38, 62, 46]
HEB_FONT_SIZE = 8.0
HEB_HEADER_HEIGHT = 20
HEB_BODY_BUDGET = 690


def _norm(value: Any) -> str:
    """Normalize a header/cell for matching without changing displayed text."""
    text = " ".join(str(value or "").strip().lower().replace("#", " # ").split())
    return text


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", _norm(value))


def _header_map(row: list[Any]) -> dict[str, int | None]:
    low = [_norm(value) for value in row]
    compact = [_compact(value) for value in row]

    def find(kind: str) -> int | None:
        for i, (h, c) in enumerate(zip(low, compact)):
            if kind == "label" and (c in {"label#", "label"} or h.startswith("label #")):
                return i
            if kind == "description" and h == "description":
                return i
            if kind == "controller" and ("controller id" in h or c == "controllerid"):
                return i
            if kind == "ip" and ("ip address" in h or c in {"ipaddress", "ipaddr"}):
                return i
            if kind == "idf" and (c in {"idf#", "idf"} or h.startswith("idf #")):
                return i
            if kind == "switch" and (c in {"switch#", "switch"} or h.startswith("switch #")):
                return i
            if kind == "port" and (c in {"port#", "port"} or h.startswith("port #")):
                return i
        return None

    return {
        "label": find("label"),
        "description": find("description"),
        "controller": find("controller"),
        "ip": find("ip"),
        "idf": find("idf"),
        "switch": find("switch"),
        "port": find("port"),
    }


def find_heb_idf_header_row(grid: list[list[Any]]) -> int | None:
    """Return the real seven-column H-E-B header row, never the title/legend row."""
    fallback: tuple[int, int] | None = None
    for row_index, row in enumerate(grid[:24]):
        mapping = _header_map(row)
        score = sum(index is not None for index in mapping.values())
        if score == 7:
            return row_index
        # Conservative fallback for old files with one slightly renamed column.
        if (
            score >= 6
            and mapping["switch"] is not None
            and mapping["port"] is not None
            and mapping["label"] is not None
        ):
            if fallback is None or score > fallback[0]:
                fallback = (score, row_index)
    return fallback[1] if fallback else None


def is_heb_idf_switch_matrix(grid: list[list[Any]], header_row: int | None = None) -> bool:
    if header_row is None:
        header_row = find_heb_idf_header_row(grid)
    if header_row is None or header_row >= len(grid):
        return False
    mapping = _header_map(grid[header_row])
    return all(mapping[key] is not None for key in mapping)


def _plain_number(value: Any) -> str:
    """Render integer-like Excel values without accidental .0 suffixes."""
    text = str(value or "").strip()
    if re.fullmatch(r"[-+]?\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def _cell(row: list[Any], index: int | None, *, integerish: bool = False) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    value = str(row[index] or "").strip()
    return _plain_number(value) if integerish else value


def _looks_like_repeated_header(row: list[Any]) -> bool:
    mapping = _header_map(row)
    return sum(index is not None for index in mapping.values()) >= 6


def _parse_groups(
    grid: list[list[Any]], header_row: int
) -> tuple[list[str], "OrderedDict[tuple[str, str], list[list[str]]]", list[str]]:
    mapping = _header_map(grid[header_row])
    specs = [
        mapping["label"],
        mapping["description"],
        mapping["controller"],
        mapping["ip"],
        mapping["idf"],
        mapping["switch"],
        mapping["port"],
    ]

    groups: "OrderedDict[tuple[str, str], list[list[str]]]" = OrderedDict()
    warnings: list[str] = []
    current_key: tuple[str, str] | None = None

    for source_row_number, row in enumerate(grid[header_row + 1 :], start=header_row + 2):
        if _looks_like_repeated_header(row):
            continue

        values = [_cell(row, index, integerish=(position in {2, 4, 5, 6})) for position, index in enumerate(specs)]
        if not any(values):
            continue

        label, description, _controller, _ip, idf_no, switch_no, port_no = values

        # A real table row has a port or at least source data in the first four
        # published columns.  This drops decorative/legend-only worksheet rows.
        if not port_no and not any((label, description, _controller, _ip)):
            continue

        key = (idf_no, switch_no)
        if not idf_no and not switch_no and current_key is not None:
            key = current_key
        elif idf_no or switch_no:
            current_key = key

        if not key[1]:
            warnings.append(
                f"Source row {source_row_number} has network data but no Switch#; row was kept in an unnumbered switch group."
            )
        groups.setdefault(key, []).append(values)

    return HEB_HEADERS[:], groups, warnings


def _natural_sort_token(value: str) -> tuple[int, str]:
    text = str(value or "").strip()
    try:
        return (0, f"{int(float(text)):09d}")
    except (TypeError, ValueError):
        return (1, text.lower())


def _worksheet_idf_number(sheet_name: str, groups: Iterable[tuple[str, str]]) -> str:
    match = re.search(r"\bIDF\s*#?\s*(\d+)\b", sheet_name or "", flags=re.IGNORECASE)
    if match:
        return match.group(1)
    source_values = sorted({idf for idf, _switch in groups if idf}, key=_natural_sort_token)
    return source_values[0] if len(source_values) == 1 else ""


def _switch_text(value: str) -> str:
    return str(value or "?").strip() or "?"


def _table_title(idf_no: str, switches: list[str]) -> str:
    idf_label = f"IDF #{idf_no}" if idf_no else "IDF"
    if len(switches) >= 2:
        return f"{idf_label} TABLE (SWITCH {switches[0]} & {switches[1]})"
    if switches:
        return f"{idf_label} TABLE (SWITCH {switches[0]})"
    return f"{idf_label} TABLE"


def _row_height(max_rows: int) -> int:
    if max_rows <= 0:
        return 13
    fitted = int((HEB_BODY_BUDGET - HEB_HEADER_HEIGHT) / max_rows)
    return max(11, min(14, fitted))


def build_heb_idf_network_block(
    ws: dict[str, Any],
    block_id: str,
    *,
    pair_index: int = 0,
    header_row: int | None = None,
) -> dict[str, Any] | None:
    """Build one H-E-B switch-pair drawing block from a worksheet payload."""
    grid = ws.get("grid") or []
    if header_row is None:
        header_row = find_heb_idf_header_row(grid)
    if header_row is None or not is_heb_idf_switch_matrix(grid, header_row):
        return None

    headers, groups, warnings = _parse_groups(grid, header_row)
    group_items = list(groups.items())
    if not group_items:
        return None

    pair_count = ceil(len(group_items) / 2)
    selected_index = max(0, min(int(pair_index or 0), pair_count - 1))
    selected = group_items[selected_index * 2 : selected_index * 2 + 2]

    sheet_name = str(ws.get("sourceSheet") or ws.get("name") or "")
    sheet_idf = _worksheet_idf_number(sheet_name, groups.keys())
    source_idfs = sorted({key[0] for key, _rows in group_items if key[0]}, key=_natural_sort_token)
    if sheet_idf and source_idfs and source_idfs != [sheet_idf]:
        warnings.append(
            f"Worksheet title identifies IDF #{sheet_idf}, but source IDF# values are "
            f"{', '.join(source_idfs)}; source values were preserved."
        )

    switches = [_switch_text(key[1]) for key, _rows in selected]
    max_rows = max((len(rows) for _key, rows in selected), default=0)
    row_height = _row_height(max_rows)
    layout_mode = "two_up" if len(selected) == 2 else "single"

    left_rows = selected[0][1] if len(selected) >= 1 and layout_mode == "two_up" else []
    right_rows = selected[1][1] if len(selected) >= 2 else []
    single_rows = selected[0][1] if layout_mode == "single" else []

    content_width = sum(HEB_COL_WIDTHS) * (2 if layout_mode == "two_up" else 1)
    if layout_mode == "two_up":
        content_width += 18

    return {
        "id": block_id,
        "type": "idfNetworkTable",
        "sourceWorksheetId": ws.get("id", ""),
        "sourceSheet": sheet_name,
        "sourceRange": ws.get("sourceRange", ""),
        "renderMode": "excel_exact",
        "tableProfile": TABLE_PROFILE,
        "layoutMode": layout_mode,
        "sectionTitle": _table_title(sheet_idf, switches),
        "headers": headers,
        "rows": single_rows,
        "leftRows": left_rows,
        "rightRows": right_rows,
        "leftCaption": "",
        "rightCaption": "",
        "portRangeLeft": "",
        "portRangeRight": "",
        "colWidths": HEB_COL_WIDTHS[:],
        "rowHeight": row_height,
        "headerHeight": HEB_HEADER_HEIGHT,
        "fontSize": HEB_FONT_SIZE,
        "contentWidth": content_width,
        "contentHeight": HEB_HEADER_HEIGHT + max_rows * row_height,
        "sourceRowCount": sum(len(rows) for _key, rows in group_items),
        "totalRowCount": sum(len(rows) for _key, rows in group_items),
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
        "pageCount": pair_count,
        "pairIndex": selected_index,
        "switchKeys": switches,
        "scaledUp": False,
        "needsHardSplit": False,
        "hardSplitBoundary": None,
        "patchMarker": PATCH_MARKER,
    }


def sheet_code_key(code: str) -> str:
    return re.sub(r"\s+", "", str(code or "").upper())


def next_available_continuation_code(
    base_code: str,
    start_index: int,
    used_codes: set[str],
) -> str:
    """Return a deterministic continuation code that skips reserved sheet codes."""
    candidate_index = max(1, int(start_index or 1))
    while True:
        candidate = continuation_code(base_code, candidate_index)
        key = sheet_code_key(candidate)
        if key not in used_codes:
            used_codes.add(key)
            return candidate
        candidate_index += 1


def _index_reserved_codes(index_entries: list[dict[str, Any]]) -> set[str]:
    return {
        sheet_code_key(str(entry.get("sheetCodeRaw") or ""))
        for entry in index_entries
        if str(entry.get("sheetCodeRaw") or "").strip()
    }


def replace_heb_idf_pages(
    pages: list[dict[str, Any]],
    worksheets: list[dict[str, Any]],
    index_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace mis-normalized H-E-B IDF pages and add switch-pair continuations.

    Intended for a fresh workbook import before any manual canvas work exists.
    Non-H-E-B pages and all source worksheets are preserved unchanged.
    """
    ws_by_id = {str(ws.get("id") or ""): ws for ws in worksheets}
    ws_by_name = {str(ws.get("name") or "").lower(): ws for ws in worksheets}

    reserved = _index_reserved_codes(index_entries)
    used_codes = set(reserved)
    for page in pages:
        if page.get("generatedContinuation"):
            continue
        code = str(page.get("displaySheetCode") or page.get("sheetCode") or "").strip()
        if code:
            used_codes.add(sheet_code_key(code))

    ordered = sorted(pages, key=lambda page: int(page.get("order") or 0))
    out: list[dict[str, Any]] = []

    for source_page in ordered:
        # If this helper is called twice, discard only continuations it created;
        # the base page is rebuilt in place and keeps its stable page id.
        if source_page.get("generatedBy") == PATCH_MARKER and source_page.get("generatedContinuation"):
            continue
        if source_page.get("generatedContinuation"):
            out.append(source_page)
            continue

        ws = ws_by_id.get(str(source_page.get("linkedWorksheetId") or ""))
        if ws is None:
            ws = ws_by_name.get(str(source_page.get("sheetTab") or "").lower())

        likely_idf = (
            source_page.get("pageFamily") == "idfTable"
            or source_page.get("layoutProfile") == "network_48_port"
            or "idf" in f"{source_page.get('sheetTab', '')} {source_page.get('sheetTitle', '')}".lower()
        )
        header_row = find_heb_idf_header_row((ws or {}).get("grid") or []) if ws else None
        if not likely_idf or ws is None or header_row is None:
            out.append(source_page)
            continue

        first_block = build_heb_idf_network_block(
            ws,
            f"{ws.get('id', 'ws')}_idf_heb_0",
            pair_index=0,
            header_row=header_row,
        )
        if first_block is None:
            out.append(source_page)
            continue

        page_count = int(first_block.get("pageCount") or 1)
        base_page = deepcopy(source_page)
        base_page["blocks"] = [first_block]
        base_page["renderMode"] = "excel_exact"
        base_page["layoutProfile"] = "network_48_port"
        base_page["twoUp"] = first_block.get("layoutMode") == "two_up"
        base_page["splitMode"] = "none"
        base_page["allowContinuation"] = False
        base_page["minScale"] = 1.0
        base_page["scaleMode"] = "fit_body"
        base_page["layoutWarnings"] = list(first_block.get("layoutWarnings") or [])
        base_page["continuationIndex"] = 0
        base_page["continuationOf"] = None
        base_page["generatedContinuation"] = False
        base_page["generatedBy"] = PATCH_MARKER
        base_page["pageGroupId"] = base_page.get("pageGroupId") or base_page.get("id")
        out.append(base_page)

        base_code = str(base_page.get("displaySheetCode") or base_page.get("sheetCode") or "").strip()
        base_title = str(base_page.get("sheetTitle") or "").strip()
        for pair_index in range(1, page_count):
            block = build_heb_idf_network_block(
                ws,
                f"{ws.get('id', 'ws')}_idf_heb_{pair_index}",
                pair_index=pair_index,
                header_row=header_row,
            )
            if block is None:
                continue
            cont = deepcopy(base_page)
            cont["id"] = f"{base_page.get('id', 'page')}_heb_{pair_index}"
            code = next_available_continuation_code(base_code, pair_index, used_codes)
            cont["sheetCode"] = code
            cont["displaySheetCode"] = code
            if "continued" not in base_title.lower():
                cont["sheetTitle"] = f"{base_title} — CONTINUED"
            cont["blocks"] = [block]
            cont["twoUp"] = block.get("layoutMode") == "two_up"
            cont["layoutWarnings"] = list(block.get("layoutWarnings") or [])
            cont["pageGroupId"] = base_page.get("pageGroupId") or base_page.get("id")
            cont["continuationOf"] = base_page.get("id")
            cont["continuationIndex"] = pair_index
            cont["generatedContinuation"] = True
            cont["generatedBy"] = PATCH_MARKER
            out.append(cont)

    for order, page in enumerate(out, start=1):
        page["order"] = order
    return out
