"""Sync title-block sheet codes and normalized Sheet Index from 00_INDEX.

The workbook index Sheet Code column is canonical for SHEET NO. in title blocks.
Physical page order belongs only in "Sheet X of Y". This module repairs pages
whose sheetCode/displaySheetCode drifted to sequential EMS N.0 values and
rebuilds the normalized index block to match included export pages (including
generated continuations; excluding sheets not in the export set).
"""
from __future__ import annotations

import copy
import re
from typing import Any

from core.page_composer import continuation_code
from core.sheet_index_pagination import prepare_sheet_index_pages, split_sheet_index_pages
from core.project_model import recalc_page_numbers
from core.workbook_importer import (
    _INDEX_ALIASES,
    _continuation_index_page_type,
    _continuation_index_title,
    _find_index_header_row,
    _header_map,
    _included,
    _sheet_code_from_tab,
)

_DEFAULT_ROW_PX = 20


def _norm_tab(tab: str) -> str:
    return (tab or "").strip().lower()


def _find_index_worksheet(project: dict[str, Any]) -> dict[str, Any] | None:
    index_page = next(
        (p for p in project.get("pages", []) if p.get("pageType") == "index"),
        None,
    )
    if not index_page:
        return None
    ws_id = index_page.get("linkedWorksheetId")
    if not ws_id:
        return None
    return next((w for w in project.get("worksheets", []) if w.get("id") == ws_id), None)


def _parse_index_grid(grid: list[list[str]]) -> list[dict[str, Any]]:
    if not grid:
        return []
    header_idx = 0
    for i, row in enumerate(grid[:20]):
        low = {str(x).lower() for x in row if x}
        if low & _INDEX_ALIASES["sheet_tab"] and low & _INDEX_ALIASES["sheet_title"]:
            header_idx = i
            break
    header = [str(x) for x in grid[header_idx]]
    col = _header_map(header)
    entries: list[dict[str, Any]] = []
    for row in grid[header_idx + 1 :]:
        tab = row[col["sheet_tab"]] if 0 <= col["sheet_tab"] < len(row) else ""
        title = row[col["sheet_title"]] if 0 <= col["sheet_title"] < len(row) else ""
        include_raw = row[col["include"]] if 0 <= col["include"] < len(row) else ""
        use_source = row[col["use_source"]] if 0 <= col["use_source"] < len(row) else ""
        code = row[col["sheet_code"]] if 0 <= col["sheet_code"] < len(row) else ""
        family = row[col["family"]] if 0 <= col["family"] < len(row) else ""
        page_type = row[col["page_type"]] if 0 <= col["page_type"] < len(row) else ""
        if not tab and not title:
            continue
        entries.append(
            {
                "sheetTab": tab,
                "sheetTitle": title or tab,
                "sheetCodeRaw": str(code or "").strip(),
                "include": _included(include_raw, title or tab, use_source, in_index=True),
                "family": family,
                "pageType": page_type,
            }
        )
    return entries


def _tab_to_code(entries: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in entries:
        tab = _norm_tab(e.get("sheetTab") or "")
        code = (e.get("sheetCodeRaw") or "").strip()
        if tab and code:
            out[tab] = code
    return out


def _looks_like_physical_order_code(code: str) -> bool:
    """True when code is EMS {n}.0 matching sequential package order, not index EMS 0.x / 1.x."""
    c = (code or "").strip()
    m = re.fullmatch(r"EMS\s+(\d+)\.0(?:[a-z])?", c, re.IGNORECASE)
    if not m:
        return False
    n = int(m.group(1))
    return n >= 1


def sync_sheet_codes_from_index(project: dict[str, Any]) -> None:
    """Apply canonical index Sheet Code values to output pages (in place)."""
    ws = _find_index_worksheet(project)
    if not ws:
        return
    entries = _parse_index_grid(ws.get("grid") or [])
    if not entries:
        return
    tab_codes = _tab_to_code(entries)
    pages: list[dict[str, Any]] = project.get("pages", [])
    group_to_code: dict[str, str] = {}

    for page in pages:
        if not page.get("include", True):
            continue
        if page.get("continuationOf") or page.get("generatedContinuation"):
            continue
        tab = _norm_tab(page.get("sheetTab") or "")
        code = tab_codes.get(tab) or _sheet_code_from_tab(page.get("sheetTab") or "")
        if not code:
            existing = (page.get("displaySheetCode") or page.get("sheetCode") or "").strip()
            if existing and not _looks_like_physical_order_code(existing):
                code = existing
        if code:
            page["sheetCode"] = code
            page["displaySheetCode"] = code
            group_to_code[page.get("id") or ""] = code
            gid = page.get("pageGroupId") or page.get("id") or ""
            group_to_code[gid] = code

    for page in pages:
        if not page.get("include", True):
            continue
        if not (page.get("continuationOf") or page.get("generatedContinuation")):
            continue
        base_id = page.get("continuationOf") or page.get("pageGroupId") or ""
        base_code = group_to_code.get(base_id, "")
        if not base_code:
            base = next(
                (
                    p
                    for p in pages
                    if p.get("id") == base_id
                    or (p.get("pageGroupId") == base_id and not p.get("generatedContinuation"))
                ),
                None,
            )
            if base:
                base_code = (base.get("displaySheetCode") or base.get("sheetCode") or "").strip()
        if not base_code:
            continue
        ci = int(page.get("continuationIndex") or 1)
        code = continuation_code(base_code, ci)
        page["sheetCode"] = code
        page["displaySheetCode"] = code


def rebuild_normalized_index_block(project: dict[str, Any]) -> None:
    """Rewrite the normalized Sheet Index excel block to match exported pages."""
    index_page = next(
        (p for p in project.get("pages", []) if p.get("pageType") == "index" and p.get("renderMode") == "excel_exact"),
        None,
    )
    if not index_page:
        return
    block = next((b for b in (index_page.get("blocks") or []) if b.get("type") == "excelRange"), None)
    if not block:
        return
    grid = block.get("grid") or []
    if not grid:
        return

    header_idx = _find_index_header_row(grid)
    header = [str(x) for x in grid[header_idx]]
    col = _header_map(header)
    n_cols = max(len(header), max((len(r) for r in grid), default=0))

    ws = _find_index_worksheet(project)
    tab_meta: dict[str, dict[str, Any]] = {}
    if ws:
        for e in _parse_index_grid(ws.get("grid") or []):
            tab_meta[_norm_tab(e.get("sheetTab") or "")] = e

    preamble = [list(r) + [""] * (n_cols - len(r)) for r in grid[: header_idx + 1]]
    included = sorted(
        [p for p in project.get("pages", []) if p.get("include", True)],
        key=lambda p: int(p.get("order") or 0),
    )

    body: list[list[str]] = []
    for i, page in enumerate(included, start=1):
        row = [""] * n_cols
        code = (page.get("displaySheetCode") or page.get("sheetCode") or "").strip()
        tab = page.get("sheetTab") or ""
        title = re.sub(r"\s*[—-]\s*CONTINUED\s*$", "", page.get("sheetTitle") or "", flags=re.IGNORECASE).strip()
        meta = tab_meta.get(_norm_tab(tab), {})

        if col.get("order", -1) >= 0:
            row[col["order"]] = str(i)
        if col.get("sheet_code", -1) >= 0:
            row[col["sheet_code"]] = code
        if col.get("sheet_tab", -1) >= 0:
            row[col["sheet_tab"]] = tab
        if col.get("sheet_title", -1) >= 0:
            row[col["sheet_title"]] = _continuation_index_title(page) if page.get("generatedContinuation") else title
        if col.get("include", -1) >= 0:
            row[col["include"]] = "YES"
        if col.get("family", -1) >= 0:
            fam = page.get("pageFamily") or meta.get("family") or ""
            row[col["family"]] = str(fam)
        if col.get("page_type", -1) >= 0:
            if page.get("generatedContinuation"):
                row[col["page_type"]] = _continuation_index_page_type(page)
            else:
                row[col["page_type"]] = page.get("pageType") or meta.get("pageType") or ""
        body.append(row)

    block["grid"] = preamble + body
    row_heights = list(block.get("rowHeights") or [])
    default_h = row_heights[-1] if row_heights else _DEFAULT_ROW_PX
    preamble_h = row_heights[: len(preamble)] if row_heights else [_DEFAULT_ROW_PX] * len(preamble)
    while len(preamble_h) < len(preamble):
        preamble_h.append(default_h)
    block["rowHeights"] = preamble_h + [default_h] * len(body)


def sync_project_sheet_index(project: dict[str, Any]) -> dict[str, Any]:
    """Repair page sheet codes + normalized index from the source index worksheet."""
    # Rebuild deterministic TOC continuation pages before generating rows.
    prepare_sheet_index_pages(project)
    sync_sheet_codes_from_index(project)
    rebuild_normalized_index_block(project)
    # Split the complete TOC across EMS 2.0, EMS 2.0a, and later pages.
    split_sheet_index_pages(project)
    recalc_page_numbers(project)
    return project
