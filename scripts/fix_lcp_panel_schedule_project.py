"""Split a multi-controller LCP panel schedule into stable app pages.

Designed for Singh360 Draft projects that already contain manual edits. It does
not re-import the workbook. It transforms only the matching panel-schedule
worksheet/page group inside the existing project JSON, preserving every other
worksheet, page, overlay, asset, and property.

Current SA31 result:
  EMS 16.0  LCP-1 Dimming Panel & Expansion I/O
  EMS 16.1  LCP-2 Contactor Panel

The splitter is generic:
- each controller header starts a controller group;
- expansion-board sections stay attached to their controller;
- wide merged section headers are atomic and are never cut in half;
- an oversized controller group may continue only between complete section
  blocks, never through a merged header or its table.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_PROJECT_ID = "4acaef6006dd4620"
BODY_WIDTH = 1480
NATURAL_PAGE_HEIGHT = 920  # 720px body / 0.78 readable scale
HEADER_REPEAT_ROWS = 4
DEFAULT_ROW_HEIGHT = 24
MIN_CONTROLLER_ROWS = 3

_CONTROLLER_RE = re.compile(r"\bcontroller\s*id\s*:\s*([A-Za-z0-9._-]+)", re.I)
_LCP_RE = re.compile(r"\bLCP[-\s]*(\d+)\b", re.I)
_SECTION_WORDS = ("expansion", "board id", "controller id", "contactor panel", "dimming panel")


class MigrationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_text(row: Iterable[Any]) -> str:
    return " ".join(str(value or "").strip() for value in row if str(value or "").strip())


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _col_letters_to_index(letters: str) -> int:
    value = 0
    for char in letters.upper():
        value = value * 26 + (ord(char) - 64)
    return value - 1


def _col_index_to_letters(index: int) -> str:
    value = index + 1
    output = ""
    while value > 0:
        remainder = (value - 1) % 26
        output = chr(65 + remainder) + output
        value = (value - 1) // 26
    return output


def _a1_parts(key: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"([A-Z]+)(\d+)", str(key or "").upper())
    if not match:
        return None
    return int(match.group(2)) - 1, _col_letters_to_index(match.group(1))


def _style_for(styles: dict[str, Any], row: int, col: int) -> dict[str, Any]:
    return styles.get(f"{_col_index_to_letters(col)}{row + 1}") or {}


def _is_wide_merge_header(ws: dict[str, Any], row: int) -> bool:
    grid = ws.get("grid") or []
    ncols = max((len(r) for r in grid), default=0)
    if ncols < 2:
        return False
    styles = ws.get("styles") or {}
    for merge in ws.get("mergedCells") or []:
        if int(merge.get("startRow", -1)) != row or int(merge.get("endRow", -1)) != row:
            continue
        span = int(merge.get("endCol", 0)) - int(merge.get("startCol", 0)) + 1
        if span < max(2, ncols // 2):
            continue
        start_col = int(merge.get("startCol", 0))
        style = _style_for(styles, row, start_col)
        aligned = str(style.get("hAlign") or "").lower() == "center"
        filled = bool(style.get("fill"))
        if aligned or filled:
            return True
    return False


def _is_controller_header(ws: dict[str, Any], row: int) -> bool:
    text = _norm(_row_text((ws.get("grid") or [])[row]))
    if "expansion" in text or "board id" in text:
        return False
    return bool(_CONTROLLER_RE.search(text) and ("lcp" in text or "panel" in text))


def _is_section_header(ws: dict[str, Any], row: int) -> bool:
    text = _norm(_row_text((ws.get("grid") or [])[row]))
    if _is_controller_header(ws, row):
        return True
    if ("expansion" in text or "board id" in text) and (_is_wide_merge_header(ws, row) or "pr0663" in text):
        return True
    if _is_wide_merge_header(ws, row) and any(word in text for word in _SECTION_WORDS):
        return True
    return False


def _trim_trailing_blank_rows(ws: dict[str, Any]) -> int:
    grid = ws.get("grid") or []
    styles = ws.get("styles") or {}
    merges = ws.get("mergedCells") or []
    merge_rows = {
        row
        for merge in merges
        for row in range(int(merge.get("startRow", 0)), int(merge.get("endRow", 0)) + 1)
    }

    last = len(grid) - 1
    while last >= 0:
        row = grid[last] if last < len(grid) else []
        if any(str(value or "").strip() for value in row):
            break
        if last in merge_rows:
            break
        has_style = any(
            bool(_style_for(styles, last, col).get("fill"))
            or bool((_style_for(styles, last, col).get("borders") or {}))
            for col in range(max((len(r) for r in grid), default=0))
        )
        if has_style:
            break
        last -= 1
    return max(0, last + 1)


def detect_controller_groups(ws: dict[str, Any]) -> tuple[list[int], list[dict[str, Any]]]:
    grid = ws.get("grid") or []
    if not grid:
        raise MigrationError("The panel-schedule worksheet is empty.")

    end = _trim_trailing_blank_rows(ws)
    controller_rows = [row for row in range(end) if _is_controller_header(ws, row)]
    if len(controller_rows) < 2:
        controller_rows = []
        for row in range(end):
            text = _norm(_row_text(grid[row]))
            if ("lcp-1" in text or "lcp 1" in text) and ("panel" in text or "controller" in text):
                controller_rows.append(row)
            elif ("lcp-2" in text or "lcp 2" in text or "controller id: 602" in text) and (
                "panel" in text or "controller" in text
            ):
                controller_rows.append(row)
        controller_rows = sorted(set(controller_rows))

    if len(controller_rows) < 2:
        raise MigrationError(
            "Could not find at least two controller headers. Expected rows such as "
            "'LCP-1 ... Controller ID: 601' and 'LCP-2 ... Controller ID: 602'."
        )

    first = controller_rows[0]
    preamble = list(range(0, first))

    groups: list[dict[str, Any]] = []
    for index, start in enumerate(controller_rows):
        stop = controller_rows[index + 1] if index + 1 < len(controller_rows) else end
        rows = list(range(start, stop))
        if len(rows) < MIN_CONTROLLER_ROWS:
            continue
        text = _row_text(grid[start])
        controller_match = _CONTROLLER_RE.search(text)
        controller_id = controller_match.group(1) if controller_match else ""
        lcp_match = _LCP_RE.search(text)
        lcp_number = int(lcp_match.group(1)) if lcp_match else index + 1
        section_starts = [row for row in rows if _is_section_header(ws, row)]
        if start not in section_starts:
            section_starts.insert(0, start)
        section_starts = sorted(set(section_starts))

        sections: list[list[int]] = []
        for section_index, section_start in enumerate(section_starts):
            section_stop = section_starts[section_index + 1] if section_index + 1 < len(section_starts) else stop
            section_rows = list(range(section_start, section_stop))
            if section_rows:
                sections.append(section_rows)

        groups.append(
            {
                "start": start,
                "stop": stop,
                "rows": rows,
                "sections": sections,
                "headerText": text,
                "controllerId": controller_id,
                "lcpNumber": lcp_number,
                "hasExpansion": any(
                    "expansion" in _norm(_row_text(grid[row]))
                    or "board id" in _norm(_row_text(grid[row]))
                    for row in rows
                ),
            }
        )
    return preamble, groups


def _row_height(ws: dict[str, Any], row: int) -> int:
    heights = ws.get("rowHeightsPx")
    if isinstance(heights, list) and row < len(heights):
        try:
            return max(18, min(90, int(round(float(heights[row])))))
        except (TypeError, ValueError):
            pass

    legacy = ws.get("rowHeights")
    if isinstance(legacy, dict):
        for key in (str(row + 1), row + 1, str(row), row):
            if key in legacy:
                try:
                    return max(18, min(90, int(round(float(legacy[key])))))
                except (TypeError, ValueError):
                    pass
    elif isinstance(legacy, list) and row < len(legacy):
        try:
            return max(18, min(90, int(round(float(legacy[row])))))
        except (TypeError, ValueError):
            pass
    return DEFAULT_ROW_HEIGHT


def _pack_controller_group(ws: dict[str, Any], preamble: list[int], group: dict[str, Any]) -> list[list[int]]:
    preamble_height = sum(_row_height(ws, row) for row in preamble)
    available = max(240, NATURAL_PAGE_HEIGHT - preamble_height)

    sections = group["sections"]
    if sum(_row_height(ws, row) for row in group["rows"]) <= available:
        return [list(group["rows"])]

    pages: list[list[int]] = []
    current: list[int] = []
    used = 0
    for section in sections:
        section_height = sum(_row_height(ws, row) for row in section)
        if current and used + section_height > available:
            pages.append(current)
            current = []
            used = 0
        current.extend(section)
        used += section_height
    if current:
        pages.append(current)
    return pages or [list(group["rows"])]


def _slice_list(values: Any, rows: list[int]) -> Any:
    if not isinstance(values, list):
        return values
    return [copy.deepcopy(values[row]) for row in rows if 0 <= row < len(values)]


def _slice_styles(styles: dict[str, Any], row_map: dict[int, int]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in (styles or {}).items():
        parsed = _a1_parts(key)
        if not parsed:
            continue
        old_row, col = parsed
        if old_row not in row_map:
            continue
        output[f"{_col_index_to_letters(col)}{row_map[old_row] + 1}"] = copy.deepcopy(value)
    return output


def _slice_merges(merges: list[dict[str, Any]], row_map: dict[int, int]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for merge in merges or []:
        start = int(merge.get("startRow", 0))
        end = int(merge.get("endRow", 0))
        merge_rows = list(range(start, end + 1))
        if not merge_rows or not all(row in row_map for row in merge_rows):
            continue
        mapped = [row_map[row] for row in merge_rows]
        item = copy.deepcopy(merge)
        item["startRow"] = min(mapped)
        item["endRow"] = max(mapped)
        output.append(item)
    return output


def _remap_legacy_row_heights(heights: Any, rows: list[int]) -> Any:
    if isinstance(heights, list):
        return _slice_list(heights, rows)
    if not isinstance(heights, dict):
        return heights
    output: dict[str, Any] = {}
    for new_row, old_row in enumerate(rows):
        value = None
        for key in (str(old_row + 1), old_row + 1, str(old_row), old_row):
            if key in heights:
                value = heights[key]
                break
        if value is not None:
            output[str(new_row + 1)] = copy.deepcopy(value)
    return output


def slice_worksheet(source: dict[str, Any], rows: list[int], *, new_id: str, new_name: str, title_text: str) -> dict[str, Any]:
    rows = sorted(dict.fromkeys(row for row in rows if row >= 0))
    row_map = {old: new for new, old in enumerate(rows)}
    worksheet = copy.deepcopy(source)
    worksheet["id"] = new_id
    worksheet["name"] = new_name
    worksheet["sourceSheet"] = new_name
    worksheet["grid"] = _slice_list(source.get("grid") or [], rows)
    if worksheet["grid"] and worksheet["grid"][0]:
        worksheet["grid"][0][0] = title_text.upper()
    worksheet["formulas"] = _slice_list(source.get("formulas") or [], rows)
    worksheet["styles"] = _slice_styles(source.get("styles") or {}, row_map)
    worksheet["mergedCells"] = _slice_merges(source.get("mergedCells") or [], row_map)
    worksheet["rowHeightsPx"] = _slice_list(source.get("rowHeightsPx") or [], rows)
    worksheet["rowHeights"] = _remap_legacy_row_heights(source.get("rowHeights"), rows)
    last_col = max(0, max((len(row) for row in worksheet["grid"]), default=1) - 1)
    worksheet["sourceRange"] = f"A1:{_col_index_to_letters(last_col)}{len(worksheet['grid'])}"
    worksheet["printArea"] = worksheet["sourceRange"]
    worksheet["provenance"] = {
        **(worksheet.get("provenance") or {}),
        "sheet": new_name,
        "splitFrom": source.get("name"),
        "sourceRows": rows,
    }
    worksheet["manualPageBreaks"] = []
    return worksheet


def _styles_to_rc(styles: dict[str, Any], nrows: int, ncols: int) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in (styles or {}).items():
        parsed = _a1_parts(key)
        if not parsed:
            continue
        row, col = parsed
        if 0 <= row < nrows and 0 <= col < ncols:
            output[f"{row}:{col}"] = copy.deepcopy(value)
    return output


def _preferred_panel_widths(grid: list[list[str]]) -> list[int]:
    ncols = max((len(row) for row in grid), default=0)
    if ncols == 0:
        return []

    header_row = 0
    for row_index in range(min(len(grid), 12)):
        non_empty = [str(value or "").strip() for value in grid[row_index] if str(value or "").strip()]
        if len(non_empty) >= max(4, ncols // 2):
            header_row = row_index
            break
    headers = [str(value or "").strip().lower() for value in grid[header_row]]
    weights: list[float] = []
    minimums: list[int] = []
    for col in range(ncols):
        head = headers[col] if col < len(headers) else ""
        values = [str(row[col] or "") for row in grid if col < len(row)]
        longest = max((len(value) for value in values), default=1)
        if any(word in head for word in ("description", "probe input", "status input")):
            weight = max(2.5, min(5.0, longest / 12))
            minimum = 125
        elif head in {"type", "di#", "ti#", "aio#", "ro#", "di", "ti", "aio"} or "#" in head:
            weight = 0.8
            minimum = 62
        else:
            weight = max(1.0, min(2.5, longest / 10))
            minimum = 76
        weights.append(weight)
        minimums.append(minimum)

    remaining = max(0, BODY_WIDTH - sum(minimums))
    total_weight = sum(weights) or 1
    widths = [minimums[index] + int(round(remaining * weights[index] / total_weight)) for index in range(ncols)]
    if widths:
        widths[max(range(ncols), key=lambda i: widths[i])] += BODY_WIDTH - sum(widths)
    return widths


def _estimated_row_heights(grid: list[list[str]], widths: list[int]) -> list[int]:
    output: list[int] = []
    for row_index, row in enumerate(grid):
        text = _norm(_row_text(row))
        if row_index == 0 or any(word in text for word in _SECTION_WORDS):
            output.append(30)
            continue
        max_lines = 1
        for col, value in enumerate(row):
            string = str(value or "").strip()
            if not string:
                continue
            width = widths[col] if col < len(widths) else 80
            chars = max(7, int((width - 10) / 7))
            words = string.split()
            lines = 1
            current = 0
            for word in words:
                size = len(word)
                if current and current + 1 + size > chars:
                    lines += 1
                    current = size
                else:
                    current = current + (1 if current else 0) + size
            max_lines = max(max_lines, min(lines, 5))
        output.append(max(24, min(72, 18 * max_lines + 8)))
    return output


def build_excel_block(ws: dict[str, Any], block_id: str) -> dict[str, Any]:
    grid = [list(row) for row in (ws.get("grid") or [])]
    nrows = len(grid)
    ncols = max((len(row) for row in grid), default=0)
    grid = [row + [""] * (ncols - len(row)) for row in grid]
    widths = _preferred_panel_widths(grid)
    heights = _estimated_row_heights(grid, widths)
    token_header = grid[5] if len(grid) > 5 else grid[0] if grid else []
    token_columns = [
        index
        for index, head in enumerate([str(value or "").lower() for value in token_header])
        if head in {"ro#", "type", "di#", "ti#", "aio#"} or "#" in head
    ]
    return {
        "id": block_id,
        "type": "excelRange",
        "sourceWorksheetId": ws["id"],
        "sourceSheet": ws.get("name", ""),
        "sourceRange": ws.get("sourceRange", ""),
        "printArea": ws.get("printArea"),
        "renderMode": "excel_exact",
        "grid": grid,
        "styles": _styles_to_rc(ws.get("styles") or {}, nrows, ncols),
        "mergedCells": copy.deepcopy(ws.get("mergedCells") or []),
        "colWidths": widths,
        "rowHeights": heights,
        "srcRows": list(range(nrows)),
        "headerRowCount": 1,
        "repeatRows": [0] if nrows else [],
        "splitMode": "none",
        "manualRanges": [],
        "minScale": 0.78,
        "allowContinuation": False,
        "scaleMode": "fit_body",
        "orientation": "landscape",
        "styleRole": "excel-exact",
        "bodyRowFillMode": "none",
        "gridLines": True,
        "editable": True,
        "bodyFontPx": 12,
        "pageFamily": "panelDetail",
        "layoutProfile": "io_table",
        "renderProfile": "singh360_standard_table",
        "nowrapColumns": token_columns,
        "preventStackedLabels": True,
        "noGrow": False,
        "rowsBeforeTrim": nrows,
        "colsBeforeTrim": ncols,
        "rowsAfterTrim": nrows,
        "colsAfterTrim": ncols,
    }


def _title_for_group(group: dict[str, Any], part_index: int = 0) -> str:
    lcp = group.get("lcpNumber") or ""
    upper = str(group.get("headerText") or "").upper()
    if "DIMMING PANEL" in upper:
        base = f"LCP-{lcp} Dimming Panel"
    elif "CONTACTOR PANEL" in upper:
        base = f"LCP-{lcp} Contactor Panel"
    else:
        base = f"LCP-{lcp} Panel Schedule"
    if group.get("hasExpansion") and part_index == 0:
        base += " & Expansion I/O"
    if part_index > 0:
        base += f" — Continued {part_index}"
    return base


def _code_for(base_code: str, index: int) -> str:
    base = str(base_code or "EMS 16.0").strip()
    match = re.fullmatch(r"(.*?)(\d+)\.(\d+)", base)
    if match:
        return f"{match.group(1)}{match.group(2)}.{index}"
    return base if index == 0 else f"{base}.{index}"


def _find_project_dir(repo: Path, project_id: str) -> Path:
    projects = repo / ".docs" / "projects"
    candidates = []
    if projects.is_dir():
        direct = projects / project_id
        if (direct / "project.json").is_file():
            candidates.append(direct)
        candidates.extend(path for path in projects.glob(f"*__{project_id}") if (path / "project.json").is_file())
    if not candidates:
        raise MigrationError(f"Project {project_id} was not found under {projects}")
    return max(candidates, key=lambda path: (path / "project.json").stat().st_mtime)


def _find_panel_worksheet(project: dict[str, Any]) -> dict[str, Any]:
    worksheets = project.get("worksheets") or []
    exact = [
        ws
        for ws in worksheets
        if "16.0" in _norm(ws.get("name"))
        and "lcp" in _norm(ws.get("name"))
        and "panel" in _norm(ws.get("name"))
        and "schedule" in _norm(ws.get("name"))
        and "copy of" not in _norm(ws.get("name"))
    ]
    if exact:
        return exact[0]
    candidates = [
        ws
        for ws in worksheets
        if "lcp" in _norm(ws.get("name")) and "panel" in _norm(ws.get("name")) and "schedule" in _norm(ws.get("name"))
    ]
    if not candidates:
        raise MigrationError("No LCP panel schedule worksheet was found in the project.")
    return candidates[0]


def _find_base_page(project: dict[str, Any], worksheet_id: str) -> dict[str, Any]:
    pages = project.get("pages") or []
    candidates = [page for page in pages if page.get("linkedWorksheetId") == worksheet_id and not page.get("generatedContinuation")]
    if not candidates:
        candidates = [page for page in pages if "16.0" in _norm(page.get("sheetCode")) and "lcp" in _norm(page.get("sheetTitle"))]
    if not candidates:
        raise MigrationError("No base EMS 16.0 LCP panel schedule page was found.")
    return sorted(candidates, key=lambda page: int(page.get("order") or 0))[0]


def _insert_rows(worksheet: dict[str, Any], at: int, rows: list[list[Any]], style_source_row: int | None = None) -> None:
    if not rows:
        return
    grid = worksheet.setdefault("grid", [])
    count = len(rows)
    ncols = max((len(row) for row in grid), default=max((len(row) for row in rows), default=1))
    normalized = [list(row) + [""] * (ncols - len(row)) for row in rows]
    grid[at:at] = normalized

    for key in ("formulas", "rowHeightsPx"):
        values = worksheet.get(key)
        if isinstance(values, list):
            if key == "formulas":
                inserts = [[""] * ncols for _ in rows]
            else:
                source_height = values[style_source_row] if style_source_row is not None and 0 <= style_source_row < len(values) else DEFAULT_ROW_HEIGHT
                inserts = [copy.deepcopy(source_height) for _ in rows]
            values[at:at] = inserts

    styles = worksheet.get("styles")
    if isinstance(styles, dict):
        shifted: dict[str, Any] = {}
        for key, value in styles.items():
            parsed = _a1_parts(key)
            if not parsed:
                shifted[key] = value
                continue
            row, col = parsed
            new_row = row + count if row >= at else row
            shifted[f"{_col_index_to_letters(col)}{new_row + 1}"] = value
        if style_source_row is not None:
            source_row_after_shift = style_source_row + count if style_source_row >= at else style_source_row
            source_items = [(key, value) for key, value in shifted.items() if (_a1_parts(key) or (-1, -1))[0] == source_row_after_shift]
            for offset in range(count):
                for key, value in source_items:
                    _, col = _a1_parts(key) or (-1, -1)
                    shifted[f"{_col_index_to_letters(col)}{at + offset + 1}"] = copy.deepcopy(value)
        worksheet["styles"] = shifted

    merges = worksheet.get("mergedCells")
    if isinstance(merges, list):
        for merge in merges:
            if int(merge.get("startRow", 0)) >= at:
                merge["startRow"] = int(merge.get("startRow", 0)) + count
                merge["endRow"] = int(merge.get("endRow", 0)) + count
            elif int(merge.get("endRow", 0)) >= at:
                merge["endRow"] = int(merge.get("endRow", 0)) + count


def _update_control_index(worksheet: dict[str, Any], page_specs: list[dict[str, Any]]) -> None:
    grid = worksheet.get("grid")
    if not isinstance(grid, list) or not grid:
        return
    header_index = next(
        (
            index
            for index, row in enumerate(grid[:20])
            if "sheet code" in {_norm(value) for value in row}
            and ("sheet tab" in {_norm(value) for value in row} or "sheet title" in {_norm(value) for value in row})
        ),
        None,
    )
    if header_index is None:
        return
    header = [_norm(value) for value in grid[header_index]]
    mapping = {name: index for index, name in enumerate(header)}
    code_col = mapping.get("sheet code", -1)
    tab_col = mapping.get("sheet tab", -1)
    title_col = mapping.get("page title", mapping.get("sheet title", -1))
    include_col = mapping.get("include", -1)
    order_col = mapping.get("order", -1)
    family_col = mapping.get("family", -1)
    page_type_col = mapping.get("page type", -1)
    check_col = mapping.get("check", -1)
    status_col = mapping.get("status", -1)

    target_rows = [
        index
        for index in range(header_index + 1, len(grid))
        if (
            (code_col >= 0 and _norm(grid[index][code_col] if code_col < len(grid[index]) else "").startswith("ems 16."))
            or (
                tab_col >= 0
                and "lcp" in _norm(grid[index][tab_col] if tab_col < len(grid[index]) else "")
                and "panel" in _norm(grid[index][tab_col] if tab_col < len(grid[index]) else "")
            )
        )
    ]
    if not target_rows:
        return

    first = target_rows[0]
    for index in reversed(target_rows):
        grid.pop(index)
        for key in ("formulas", "rowHeightsPx"):
            values = worksheet.get(key)
            if isinstance(values, list) and index < len(values):
                values.pop(index)

    template_row = [""] * max(len(header), max((len(row) for row in grid), default=len(header)))
    new_rows = []
    for spec in page_specs:
        row = list(template_row)
        if include_col >= 0:
            row[include_col] = "YES"
        if code_col >= 0:
            row[code_col] = spec["code"]
        if tab_col >= 0:
            row[tab_col] = spec["worksheetName"]
        if title_col >= 0:
            row[title_col] = spec["title"]
        if family_col >= 0:
            row[family_col] = "Lighting"
        if page_type_col >= 0:
            row[page_type_col] = "I/O Table"
        if check_col >= 0:
            row[check_col] = "✓"
        if status_col >= 0:
            row[status_col] = "Active"
        new_rows.append(row)

    _insert_rows(worksheet, first, new_rows, style_source_row=max(header_index + 1, first - 1))

    if order_col >= 0:
        order = 1
        for row in grid[header_index + 1 :]:
            include = _norm(row[include_col] if include_col >= 0 and include_col < len(row) else "yes")
            if include not in {"no", "false", "0", "off"}:
                while len(row) <= order_col:
                    row.append("")
                row[order_col] = order
                order += 1


def _update_display_index(worksheet: dict[str, Any], page_specs: list[dict[str, Any]]) -> None:
    grid = worksheet.get("grid")
    if not isinstance(grid, list) or not grid:
        return
    header_index = next(
        (
            index
            for index, row in enumerate(grid[:20])
            if "sheet code" in {_norm(value) for value in row} and "sheet title" in {_norm(value) for value in row}
        ),
        None,
    )
    if header_index is None:
        return
    header = [_norm(value) for value in grid[header_index]]
    mapping = {name: index for index, name in enumerate(header)}
    code_col = mapping.get("sheet code", -1)
    title_col = mapping.get("sheet title", -1)
    page_col = mapping.get("page", -1)
    family_col = mapping.get("family", -1)
    type_col = mapping.get("page type", -1)
    notes_col = mapping.get("notes", -1)

    target_rows = [
        index
        for index in range(header_index + 1, len(grid))
        if code_col >= 0 and _norm(grid[index][code_col] if code_col < len(grid[index]) else "").startswith("ems 16.")
    ]
    if not target_rows:
        return
    first = target_rows[0]
    for index in reversed(target_rows):
        grid.pop(index)
        for key in ("formulas", "rowHeightsPx"):
            values = worksheet.get(key)
            if isinstance(values, list) and index < len(values):
                values.pop(index)

    width = max(len(header), max((len(row) for row in grid), default=len(header)))
    rows = []
    for spec in page_specs:
        row = [""] * width
        if code_col >= 0:
            row[code_col] = spec["code"]
        if title_col >= 0:
            row[title_col] = spec["title"]
        if page_col >= 0:
            row[page_col] = ""
        if family_col >= 0:
            row[family_col] = "Lighting"
        if type_col >= 0:
            row[type_col] = "I/O Table"
        if notes_col >= 0:
            row[notes_col] = ""
        rows.append(row)
    _insert_rows(worksheet, first, rows, style_source_row=max(header_index + 1, first - 1))


def _rebuild_index_page_block(project: dict[str, Any], worksheet: dict[str, Any]) -> None:
    for page in project.get("pages") or []:
        if page.get("linkedWorksheetId") != worksheet.get("id"):
            continue
        if page.get("pageType") != "index" and "index" not in _norm(page.get("sheetTitle")):
            continue
        page["blocks"] = [build_excel_block(worksheet, f"{worksheet['id']}_xr")]
        page["sourceRevision"] = int(page.get("sourceRevision") or 0) + 1


def _resequence(project: dict[str, Any]) -> None:
    pages = project.get("pages") or []
    for order, page in enumerate(pages, start=1):
        page["order"] = order
    included = [page for page in pages if page.get("include", True)]
    total = len(included)
    number = 0
    for page in pages:
        if page.get("include", True):
            number += 1
            page["pageNumber"] = number
            page["pageTotal"] = total
        else:
            page["pageNumber"] = None
            page["pageTotal"] = total


def _stamp_display_index_pages(project: dict[str, Any]) -> None:
    code_to_page = {
        str(page.get("displaySheetCode") or page.get("sheetCode") or "").strip(): page.get("pageNumber")
        for page in project.get("pages") or []
        if page.get("include", True)
    }
    for worksheet in project.get("worksheets") or []:
        if "sheet index" not in _norm(worksheet.get("name")):
            continue
        grid = worksheet.get("grid") or []
        header_index = next(
            (
                index
                for index, row in enumerate(grid[:20])
                if "sheet code" in {_norm(value) for value in row} and "page" in {_norm(value) for value in row}
            ),
            None,
        )
        if header_index is None:
            continue
        header = [_norm(value) for value in grid[header_index]]
        mapping = {name: index for index, name in enumerate(header)}
        code_col = mapping.get("sheet code", -1)
        page_col = mapping.get("page", -1)
        if code_col < 0 or page_col < 0:
            continue
        for row in grid[header_index + 1 :]:
            code = str(row[code_col] if code_col < len(row) else "").strip()
            if code in code_to_page:
                while len(row) <= page_col:
                    row.append("")
                row[page_col] = code_to_page[code]
        _rebuild_index_page_block(project, worksheet)


def migrate_project(project: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    original = _find_panel_worksheet(project)
    preamble, groups = detect_controller_groups(original)
    base_page = _find_base_page(project, original["id"])
    base_code = str(base_page.get("displaySheetCode") or base_page.get("sheetCode") or "EMS 16.0")
    base_order = int(base_page.get("order") or 1)
    base_group_id = base_page.get("pageGroupId") or base_page.get("id")

    page_specs: list[dict[str, Any]] = []
    new_worksheets: list[dict[str, Any]] = []
    page_index = 0
    for group in groups:
        chunks = _pack_controller_group(original, preamble, group)
        for chunk_index, chunk in enumerate(chunks):
            rows = preamble + chunk
            code = _code_for(base_code, page_index)
            title = _title_for_group(group, chunk_index)
            worksheet_name = f"{code} LCP-{group.get('lcpNumber') or page_index + 1} Panel"
            if chunk_index > 0:
                worksheet_name += f" Cont {chunk_index}"
            worksheet_id = original["id"] if page_index == 0 else f"{original['id']}_panel_{page_index}"
            worksheet = slice_worksheet(
                original,
                rows,
                new_id=worksheet_id,
                new_name=worksheet_name[:31],
                title_text=title,
            )
            new_worksheets.append(worksheet)
            page_specs.append(
                {
                    "code": code,
                    "title": title,
                    "worksheetId": worksheet_id,
                    "worksheetName": worksheet["name"],
                    "controllerId": group.get("controllerId"),
                    "sourceRows": rows,
                }
            )
            page_index += 1

    if len(page_specs) < 2:
        raise MigrationError("The panel schedule did not produce at least two stable pages.")

    worksheets = project.get("worksheets") or []
    original_position = next((index for index, worksheet in enumerate(worksheets) if worksheet.get("id") == original.get("id")), len(worksheets))
    related_worksheet_ids = {
        worksheet.get("id")
        for worksheet in worksheets
        if (
            worksheet.get("id") == original.get("id")
            or (
                "16." in _norm(worksheet.get("name"))
                and "lcp" in _norm(worksheet.get("name"))
                and "panel" in _norm(worksheet.get("name"))
                and "schedule" in _norm(worksheet.get("name"))
            )
        )
    }
    project["worksheets"] = [worksheet for worksheet in worksheets if worksheet.get("id") not in related_worksheet_ids]
    project["worksheets"][original_position:original_position] = new_worksheets

    pages = project.get("pages") or []
    related_pages = [
        page
        for page in pages
        if (
            page.get("linkedWorksheetId") in related_worksheet_ids
            or page.get("pageGroupId") == base_group_id
            or page.get("continuationOf") == base_group_id
            or ("ems 16." in _norm(page.get("sheetCode")) and "lcp" in _norm(page.get("sheetTitle")))
        )
    ]
    overlay_pages = sorted(related_pages, key=lambda page: int(page.get("order") or 0))
    insertion_position = next((index for index, page in enumerate(pages) if page in related_pages), max(0, base_order - 1))
    remaining_pages = [page for page in pages if page not in related_pages]

    new_pages: list[dict[str, Any]] = []
    for index, spec in enumerate(page_specs):
        previous = overlay_pages[index] if index < len(overlay_pages) else None
        page_id = base_page["id"] if index == 0 else f"{base_page['id']}_panel_{index}"
        template = copy.deepcopy(base_page)
        template.update(
            {
                "id": page_id,
                "order": base_order + index,
                "sheetCode": spec["code"],
                "displaySheetCode": spec["code"],
                "sheetTitle": spec["title"],
                "sheetTab": spec["worksheetName"],
                "pageType": "data-grid",
                "pageFamily": "panelDetail",
                "layoutProfile": "io_table",
                "renderMode": "excel_exact",
                "renderProfile": "singh360_standard_table",
                "normalizedHeaderStyle": "orange",
                "sourceSheet": spec["worksheetName"],
                "sourceRange": "",
                "printArea": None,
                "splitMode": "none",
                "repeatRows": [0],
                "minScale": 0.78,
                "allowContinuation": False,
                "scaleMode": "fit_body",
                "trimBlankRows": True,
                "trimBlankColumns": True,
                "orientation": "landscape",
                "linkedWorksheetId": spec["worksheetId"],
                "blocks": [
                    build_excel_block(
                        next(ws for ws in new_worksheets if ws["id"] == spec["worksheetId"]),
                        f"{spec['worksheetId']}_xr",
                    )
                ],
                "canvasObjects": copy.deepcopy((previous or {}).get("canvasObjects") or []),
                "assets": copy.deepcopy((previous or {}).get("assets") or []),
                "underlays": copy.deepcopy((previous or {}).get("underlays") or []),
                "pageGroupId": page_id,
                "continuationOf": None,
                "continuationIndex": 0,
                "generatedContinuation": False,
                "layoutWarnings": [],
                "sourceRevision": int((previous or base_page).get("sourceRevision") or 0) + 1,
            }
        )
        new_pages.append(template)

    project["pages"] = remaining_pages
    project["pages"][insertion_position:insertion_position] = new_pages

    for worksheet in project.get("worksheets") or []:
        name = _norm(worksheet.get("name"))
        if name == "00_index" or name.startswith("00_index"):
            _update_control_index(worksheet, page_specs)
        elif "sheet index" in name:
            _update_display_index(worksheet, page_specs)

    _resequence(project)
    _stamp_display_index_pages(project)
    _resequence(project)

    project["paginationLocked"] = True
    project["modified"] = _now()
    project["lastSavedAt"] = _now()
    project.setdefault("migrationHistory", []).append(
        {
            "kind": "lcp-panel-section-split",
            "timestamp": _now(),
            "sourceWorksheet": original.get("name"),
            "pages": [
                {
                    "sheetCode": spec["code"],
                    "title": spec["title"],
                    "controllerId": spec["controllerId"],
                    "worksheetId": spec["worksheetId"],
                    "sourceRows": spec["sourceRows"],
                }
                for spec in page_specs
            ],
        }
    )

    report = verify_migration(project)
    return project, report


def verify_migration(project: dict[str, Any]) -> dict[str, Any]:
    pages = [
        page
        for page in project.get("pages") or []
        if _norm(page.get("sheetCode")).startswith("ems 16.") and "lcp" in _norm(page.get("sheetTitle"))
    ]
    pages = sorted(pages, key=lambda page: int(page.get("order") or 0))
    if len(pages) < 2:
        raise MigrationError(f"Expected at least two EMS 16.x LCP pages, found {len(pages)}.")

    texts = []
    for page in pages:
        block = next((block for block in page.get("blocks") or [] if block.get("type") == "excelRange"), None)
        if not block:
            raise MigrationError(f"Page {page.get('sheetCode')} has no excelRange block.")
        text = _norm(" ".join(_row_text(row) for row in block.get("grid") or []))
        texts.append(text)

    if "controller id: 601" not in texts[0]:
        raise MigrationError("EMS 16.0 does not contain Controller ID 601 after migration.")
    lcp2_index = next((index for index, text in enumerate(texts) if "controller id: 602" in text), None)
    if lcp2_index is None:
        raise MigrationError("No EMS 16.x page contains Controller ID 602 after migration.")
    if lcp2_index == 0:
        raise MigrationError("Controller 602 was not separated from the EMS 16.0 LCP-1 page.")
    if "controller id: 602" in texts[0]:
        raise MigrationError("EMS 16.0 still contains Controller ID 602.")

    duplicate_full = [
        page
        for page in pages
        if "controller id: 601"
        in _norm(" ".join(_row_text(row) for block in page.get("blocks") or [] for row in (block.get("grid") or [])))
        and "controller id: 602"
        in _norm(" ".join(_row_text(row) for block in page.get("blocks") or [] for row in (block.get("grid") or [])))
    ]
    if duplicate_full:
        raise MigrationError("A migrated LCP page still contains both controllers.")

    return {
        "ok": True,
        "pageCount": len(pages),
        "pages": [
            {
                "sheetCode": page.get("sheetCode"),
                "sheetTitle": page.get("sheetTitle"),
                "pageNumber": page.get("pageNumber"),
                "linkedWorksheetId": page.get("linkedWorksheetId"),
            }
            for page in pages
        ],
    }


def _synthetic_project() -> dict[str, Any]:
    grid = [
        ["LCP PANEL SCHEDULE"] + [""] * 11,
        [""] * 12,
        [""] * 12,
        [""] * 12,
        ["LCP-1 DIMMING PANEL — PR0650CD-TDB — Controller ID: 601"] + [""] * 11,
        ["RO#", "Relay Output Description", "Type", "DI#", "Status Input", "Type", "TI#", "Probe Input", "Type", "AIO#", "Analog I/O Description", "Type"],
    ]
    for number in range(1, 13):
        grid.append([f"RO{number}" if number <= 5 else number, f"Dimming {number}", "NO", number, "", "DI", number, "", "", number, f"Zone {number}", "0-10VDC"])
    grid.extend([
        ["Expansion I/O Device — PR0663 — Board ID: 0"] + [""] * 11,
        ["RO#", "Relay Output Description", "Type", "DI#", "Status Input", "Type", "TI#", "Probe Input", "Type", "AIO#", "Analog I/O Description", "Type"],
    ])
    for number in range(1, 7):
        grid.append([number, f"Spare relay {number}", "", number, "", "", number, "", "", number, f"Spare {number}", "0-10VDC"])
    grid.extend([
        ["LCP-2 CONTACTOR PANEL — PR0650CD-TDB — Controller ID: 602"] + [""] * 11,
        ["RO#", "Relay Output Description", "Type", "DI#", "Status Input", "Type", "TI#", "Probe Input", "Type", "AIO#", "Analog I/O Description", "Type"],
    ])
    for number in range(1, 13):
        grid.append([f"RO{number}" if number <= 10 else number, f"C{number} Existing Lighting Contactor", "NO*", number, "", "", number, "", "", number, "", ""])

    styles = {
        "A1": {"bold": True, "fill": "#F5B000", "hAlign": "center"},
        "A5": {"bold": True, "fill": "#F5B000", "hAlign": "center"},
        "A19": {"bold": True, "fill": "#F5B000", "hAlign": "center"},
        "A27": {"bold": True, "fill": "#F5B000", "hAlign": "center"},
    }
    merges = [
        {"startRow": 0, "startCol": 0, "endRow": 0, "endCol": 11},
        {"startRow": 4, "startCol": 0, "endRow": 4, "endCol": 11},
        {"startRow": 18, "startCol": 0, "endRow": 18, "endCol": 11},
        {"startRow": 26, "startCol": 0, "endRow": 26, "endCol": 11},
    ]
    ws = {
        "id": "ws_21",
        "name": "EMS 16.0 LCP Panel Schedule",
        "grid": grid,
        "formulas": [[""] * 12 for _ in grid],
        "styles": styles,
        "mergedCells": merges,
        "rowHeightsPx": [24] * len(grid),
        "colWidthsPx": [70, 180, 70, 70, 120, 70, 70, 160, 70, 70, 220, 90],
        "sourceSheet": "EMS 16.0 LCP Panel Schedule",
        "sourceRange": f"A1:L{len(grid)}",
    }
    base_block = build_excel_block(ws, "ws_21_xr")
    return {
        "id": "test",
        "metadata": {},
        "worksheets": [
            {
                "id": "ws_index",
                "name": "00_INDEX",
                "grid": [
                    ["SHEET INDEX"],
                    ["Include", "Order", "Sheet Code", "Sheet Tab", "Page Title", "Family", "Page Type", "Notes", "Check", "Status"],
                    ["YES", 1, "EMS 15.1", "EMS 15.1 Lighting Schedule", "Lighting Schedule", "Lighting", "Table / Schedule", "", "✓", "Active"],
                    ["YES", 2, "EMS 16.0", "EMS 16.0 LCP Panel Schedule", "LCP Panel Schedule", "Lighting", "I/O Table", "", "✓", "Active"],
                    ["YES", 3, "EMS 17.0", "EMS 17.0 Field Instructions", "Field Instructions", "Field", "Text", "", "✓", "Active"],
                ],
                "styles": {},
                "mergedCells": [],
                "rowHeightsPx": [24] * 5,
            },
            ws,
        ],
        "pages": [
            {
                "id": "p15",
                "order": 1,
                "include": True,
                "sheetCode": "EMS 15.1",
                "displaySheetCode": "EMS 15.1",
                "sheetTitle": "Lighting Schedule",
                "sheetTab": "EMS 15.1 Lighting Schedule",
                "pageType": "data-grid",
                "linkedWorksheetId": "none",
                "blocks": [],
                "canvasObjects": [],
            },
            {
                "id": "p16",
                "order": 2,
                "include": True,
                "sheetCode": "EMS 16.0",
                "displaySheetCode": "EMS 16.0",
                "sheetTitle": "LCP Panel Schedule",
                "sheetTab": ws["name"],
                "pageType": "data-grid",
                "pageFamily": "panelDetail",
                "renderMode": "excel_exact",
                "linkedWorksheetId": ws["id"],
                "blocks": [base_block],
                "canvasObjects": [{"type": "text", "text": "manual overlay"}],
                "pageGroupId": "p16",
            },
            {
                "id": "p16_c1",
                "order": 3,
                "include": True,
                "sheetCode": "EMS 16.0a",
                "displaySheetCode": "EMS 16.0a",
                "sheetTitle": "LCP Panel Schedule — Continued",
                "sheetTab": ws["name"],
                "pageType": "data-grid",
                "pageFamily": "panelDetail",
                "renderMode": "excel_exact",
                "linkedWorksheetId": ws["id"],
                "blocks": [copy.deepcopy(base_block)],
                "canvasObjects": [],
                "pageGroupId": "p16",
                "continuationOf": "p16",
                "generatedContinuation": True,
            },
            {
                "id": "p17",
                "order": 4,
                "include": True,
                "sheetCode": "EMS 17.0",
                "displaySheetCode": "EMS 17.0",
                "sheetTitle": "Field Instructions",
                "sheetTab": "EMS 17.0 Field Instructions",
                "pageType": "data-grid",
                "linkedWorksheetId": "none2",
                "blocks": [],
                "canvasObjects": [],
            },
        ],
        "sources": [],
    }


def self_test() -> None:
    project = _synthetic_project()
    migrated, report = migrate_project(project)
    assert report["ok"]
    assert [page["sheetCode"] for page in migrated["pages"] if page["sheetCode"].startswith("EMS 16.")] == ["EMS 16.0", "EMS 16.1"]
    assert migrated["pages"][1]["canvasObjects"] == [{"type": "text", "text": "manual overlay"}]
    ws_names = [ws["name"] for ws in migrated["worksheets"]]
    assert any(name.startswith("EMS 16.0") for name in ws_names)
    assert any(name.startswith("EMS 16.1") for name in ws_names)
    print("[OK] Synthetic LCP panel migration self-test")


def apply_to_repo(repo: Path, project_id: str) -> dict[str, Any]:
    project_dir = _find_project_dir(repo, project_id)
    project_path = project_dir / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = repo / ".docs" / "patch_backups" / f"lcp_panel_split_{project_id}_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project_path, backup_dir / "project.json")

    migrated, report = migrate_project(project)
    temp = project_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(migrated, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(project_path)

    report.update(
        {
            "projectId": project_id,
            "projectPath": str(project_path),
            "backupPath": str(backup_dir / "project.json"),
            "timestamp": _now(),
        }
    )
    (backup_dir / "migration_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
    if args.apply:
        report = apply_to_repo(Path(args.repo), args.project)
        print(f"[OK] Migrated project {report['projectId']}")
        for page in report["pages"]:
            print(f"     {page['sheetCode']} — {page['sheetTitle']} — page {page['pageNumber']}")
        print(f"[OK] Project backup: {report['backupPath']}")
    if not args.self_test and not args.apply:
        parser.error("Choose --self-test and/or --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
