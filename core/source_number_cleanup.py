"""Safe cleanup of integer identifier columns in saved Singh360 projects."""
from __future__ import annotations

import re
from typing import Any

INTEGER_COLUMN_HEADERS = {
    "qty",
    "quantity",
    "port",
    "step",
    "marker",
    "order",
    "# poles",
    "poles",
    "di#",
    "di #",
    "ti#",
    "ti #",
    "aio#",
    "aio #",
}

_INTEGER_FLOAT_RE = re.compile(r"^([+-]?\d+)\.0+$")


def normalized_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def strip_trailing_zero_decimal(value: Any) -> Any:
    text = str(value or "").strip()
    match = _INTEGER_FLOAT_RE.fullmatch(text)
    return match.group(1) if match else value


def clean_integer_columns_in_grid(grid: list[list[str]]) -> tuple[list[list[str]], int]:
    if not grid:
        return grid, 0

    columns: set[int] = set()
    for row in grid:
        for col, value in enumerate(row):
            if normalized_header(value) in INTEGER_COLUMN_HEADERS:
                columns.add(col)

    if not columns:
        return grid, 0

    next_grid = [list(row) for row in grid]
    changed = 0
    for row_index, row in enumerate(next_grid):
        for col in columns:
            if col >= len(row):
                continue
            header = normalized_header(row[col])
            if header in INTEGER_COLUMN_HEADERS:
                continue
            cleaned = strip_trailing_zero_decimal(row[col])
            if cleaned != row[col]:
                row[col] = str(cleaned)
                changed += 1

    return next_grid, changed


def clean_project_integer_columns(project: dict[str, Any]) -> int:
    worksheets = project.get("worksheets")
    if not isinstance(worksheets, list):
        return 0

    changed = 0
    for worksheet in worksheets:
        if not isinstance(worksheet, dict):
            continue
        grid = worksheet.get("grid")
        if not isinstance(grid, list):
            continue
        cleaned, count = clean_integer_columns_in_grid(grid)
        if count:
            worksheet["grid"] = cleaned
            changed += count
    return changed
