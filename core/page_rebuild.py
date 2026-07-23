"""Page rebuild helpers — mirrors frontend pageRebuild + validation for smoke tests."""
from __future__ import annotations

import re
from typing import Any

from core.heb_idf_switch_matrix import build_heb_idf_network_block, find_heb_idf_header_row  # S360_HEB_IDF_SWITCH_MATRIX_V1
from core.page_composer import BODY_BUDGET, BODY_W
from core.workbook_importer import _build_idf_network_block, _idf_header_row, _is_idf_network_table

_CROP_RE = re.compile(r"scaled/cropped|exceeds one page", re.I)


def is_idf_network_page(page: dict[str, Any]) -> bool:
    if page.get("layoutProfile") == "network_48_port":
        return True
    if page.get("pageFamily") == "idfTable":
        return True
    blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    return bool(blocks and isinstance(blocks[0], dict) and blocks[0].get("type") == "idfNetworkTable")


def rebuild_single_page_from_source(page: dict[str, Any], ws: dict[str, Any]) -> dict[str, Any]:
    """Rebuild one normalized page from its linked worksheet."""
    if is_idf_network_page(page):
        family = page.get("pageFamily") or "idfTable"
        is_idf, header_row = _is_idf_network_table(ws, family)
        if not is_idf or header_row is None:
            header_row = _idf_header_row(ws.get("grid") or [])
        if header_row is None:
            return page
        heb_header = find_heb_idf_header_row(ws.get("grid") or [])
        if heb_header is not None:
            block = build_heb_idf_network_block(
                ws,
                f"{ws['id']}_idf",
                pair_index=int(page.get("continuationIndex") or 0),
                header_row=heb_header,
            )
            if block is None:
                return page
        else:
            block = _build_idf_network_block(
                ws,
                header_row,
                f"{ws['id']}_idf",
                show_terminated_by=bool(page.get("showTerminatedBy")),
            )
        out = dict(page)
        out.update(
            {
                "blocks": [block],
                "renderMode": "excel_exact",
                "layoutProfile": "network_48_port",
                "twoUp": block.get("layoutMode") == "two_up",
                "splitMode": "none",
                "allowContinuation": False,
                "minScale": 1.0,
                "scaleMode": "fit_body",
                "layoutWarnings": block.get("layoutWarnings") or [],
            }
        )
        return out

    return page


def validate_page_rebuild(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (ok, issues) before replacing a live normalized page."""
    issues: list[str] = []
    blocks = after.get("blocks") if isinstance(after.get("blocks"), list) else []
    block = blocks[0] if blocks and isinstance(blocks[0], dict) else None

    if not block:
        issues.append("Page is blank — no content blocks.")
        return False, issues

    warnings = list(after.get("layoutWarnings") or [])
    warnings.extend(block.get("layoutWarnings") or [])
    for w in warnings:
        if _CROP_RE.search(str(w)):
            issues.append(str(w))

    if block.get("type") == "idfNetworkTable":
        left = block.get("leftRows") or []
        right = block.get("rightRows") or []
        rows = block.get("rows") or []
        if not (left or right or rows):
            issues.append("Network table has no data rows.")
        cw = float(block.get("contentWidth") or 0)
        if (left or right) and cw < BODY_W * 0.5:
            issues.append("Network table is too narrow for the page body.")
        font = float(block.get("fontSize") or 9)
        if font < 7:
            issues.append(f"Effective font is {font:.1f}pt (below 7pt readable floor).")

    if block.get("type") == "excelRange":
        grid = block.get("grid") or []
        if not any(str(c or "").strip() for row in grid for c in row):
            issues.append("Page content is empty.")
        for w in warnings:
            if "scaled/cropped" in str(w).lower():
                issues.append(str(w))

    return len(issues) == 0, issues
