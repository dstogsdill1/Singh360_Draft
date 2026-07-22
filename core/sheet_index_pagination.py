"""Automatic multi-page Sheet Index / TOC pagination.

The normalized Sheet Index is generated from the final included package order.
This helper inserts deterministic continuation pages immediately after the base
index page, then splits the generated index rows across those pages. It never
publishes excluded pages and does not change the project's revision value.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any

ROWS_PER_INDEX_PAGE = 46


def _is_generated_index_continuation(page: dict[str, Any]) -> bool:
    return bool(page.get("indexContinuation") or page.get("generatedIndexContinuation"))


def _continuation_suffix(index: int) -> str:
    """1 -> a, 2 -> b, 26 -> z, 27 -> aa."""
    value = max(1, int(index))
    out = ""
    while value:
        value, rem = divmod(value - 1, 26)
        out = chr(ord("a") + rem) + out
    return out


def _continuation_code(base_code: str, index: int) -> str:
    base = str(base_code or "").strip()
    suffix = _continuation_suffix(index)
    return f"{base}{suffix}" if base else suffix


def _clean_continued_title(title: str) -> str:
    value = str(title or "Sheet Index / TOC").strip()
    return re.sub(r"\s*[—-]\s*CONTINUED\s*$", "", value, flags=re.IGNORECASE).strip()


def _index_base_page(project: dict[str, Any]) -> dict[str, Any] | None:
    pages = sorted(project.get("pages") or [], key=lambda page: int(page.get("order") or 0))
    return next(
        (
            page
            for page in pages
            if page.get("pageType") == "index" and not _is_generated_index_continuation(page)
        ),
        None,
    )


def remove_generated_index_continuations(project: dict[str, Any]) -> None:
    pages = [
        page for page in (project.get("pages") or [])
        if not _is_generated_index_continuation(page)
    ]
    for position, page in enumerate(pages, start=1):
        page["order"] = position
    project["pages"] = pages


def _required_index_pages(included_without_generated: int) -> int:
    count = 1
    for _ in range(20):
        total_final_pages = included_without_generated + (count - 1)
        required = max(1, math.ceil(total_final_pages / ROWS_PER_INDEX_PAGE))
        if required == count:
            return count
        count = required
    return count


def prepare_sheet_index_pages(project: dict[str, Any]) -> int:
    """Remove stale generated TOC continuations and insert the exact required count."""
    remove_generated_index_continuations(project)
    pages: list[dict[str, Any]] = project.get("pages") or []
    base = _index_base_page(project)
    if base is None or not base.get("include", True):
        return 0

    included_without_generated = sum(1 for page in pages if page.get("include", True))
    required = _required_index_pages(included_without_generated)
    if required <= 1:
        return 1

    base_id = str(base.get("id") or "sheet_index")
    base_code = str(base.get("displaySheetCode") or base.get("sheetCode") or "")
    base_title = _clean_continued_title(str(base.get("sheetTitle") or "Sheet Index / TOC"))
    base_index = pages.index(base)
    continuations: list[dict[str, Any]] = []
    for index in range(1, required):
        page = copy.deepcopy(base)
        code = _continuation_code(base_code, index)
        page.update(
            {
                "id": f"{base_id}__index_cont_{index}",
                "include": True,
                "sheetCode": code,
                "displaySheetCode": code,
                "sheetTitle": f"{base_title} — CONTINUED",
                "pageType": "index",
                "pageGroupId": base_id,
                "continuationOf": base_id,
                "continuationIndex": index,
                "generatedContinuation": True,
                "indexContinuation": True,
                "generatedIndexContinuation": True,
                "notes": "Generated automatically from the final included package order.",
                "canvasObjects": [],
            }
        )
        continuations.append(page)

    project["pages"] = pages[: base_index + 1] + continuations + pages[base_index + 1 :]
    for position, page in enumerate(project["pages"], start=1):
        page["order"] = position
    return required


def _find_index_header(grid: list[list[Any]]) -> int:
    for index, row in enumerate(grid[:30]):
        values = {str(value or "").strip().upper() for value in row}
        if "PAGE" in values and "SHEET CODE" in values and ("PAGE TITLE" in values or "SHEET TITLE" in values):
            return index
    return 0


def _excel_block(page: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            block for block in (page.get("blocks") or [])
            if isinstance(block, dict) and block.get("type") == "excelRange"
        ),
        None,
    )


def _replace_preamble_values(
    rows: list[list[Any]],
    base_code: str,
    page_code: str,
    base_title: str,
    page_title: str,
) -> list[list[Any]]:
    replaced: list[list[Any]] = []
    for row in rows:
        next_row: list[Any] = []
        for value in row:
            text = str(value or "")
            if text.strip() == base_code:
                next_row.append(page_code)
            elif text.strip().upper() == base_title.upper():
                next_row.append(page_title)
            else:
                next_row.append(value)
        replaced.append(next_row)
    return replaced


def split_sheet_index_pages(project: dict[str, Any]) -> int:
    """Split the complete generated index block across base + continuation pages."""
    base = _index_base_page(project)
    if base is None:
        return 0
    base_block = _excel_block(base)
    if base_block is None:
        return 0
    full_grid = copy.deepcopy(base_block.get("grid") or [])
    if not full_grid:
        return 0

    header_index = _find_index_header(full_grid)
    preamble = full_grid[: header_index + 1]
    body = full_grid[header_index + 1 :]
    chunks = [body[index : index + ROWS_PER_INDEX_PAGE] for index in range(0, len(body), ROWS_PER_INDEX_PAGE)] or [[]]

    index_pages = sorted(
        [
            page for page in (project.get("pages") or [])
            if page.get("pageType") == "index"
            and (page is base or _is_generated_index_continuation(page))
        ],
        key=lambda page: int(page.get("continuationIndex") or 0),
    )
    if len(chunks) != len(index_pages):
        if len(chunks) > len(index_pages):
            raise RuntimeError(
                f"Sheet Index requires {len(chunks)} pages but only {len(index_pages)} were prepared."
            )
        chunks.extend([[] for _ in range(len(index_pages) - len(chunks))])

    row_heights = list(base_block.get("rowHeights") or [])
    default_height = row_heights[-1] if row_heights else 20
    preamble_heights = row_heights[: len(preamble)]
    while len(preamble_heights) < len(preamble):
        preamble_heights.append(default_height)

    base_code = str(base.get("displaySheetCode") or base.get("sheetCode") or "")
    base_title = _clean_continued_title(str(base.get("sheetTitle") or "Sheet Index / TOC"))
    for page, chunk in zip(index_pages, chunks):
        block = _excel_block(page)
        if block is None:
            block = copy.deepcopy(base_block)
            page["blocks"] = [block]
        page_code = str(page.get("displaySheetCode") or page.get("sheetCode") or base_code)
        page_title = str(page.get("sheetTitle") or base_title)
        page_preamble = _replace_preamble_values(preamble, base_code, page_code, base_title, page_title)
        block["grid"] = page_preamble + copy.deepcopy(chunk)
        block["rowHeights"] = preamble_heights + [default_height] * len(chunk)
        block["indexRowsOnPage"] = len(chunk)
        block["indexRowsPerPage"] = ROWS_PER_INDEX_PAGE
        page["indexRowsOnPage"] = len(chunk)
        page["indexPageCount"] = len(index_pages)
    return len(index_pages)
