"""core/export_qa.py — PDF export QA warnings (non-blocking).

Scans project page render diagnostics before export and returns a structured
warning list. The export endpoint always generates the PDF unless the project
is missing, has no pages, or the render engine fails — layout/index warnings
are surfaced for user review with an optional override in the UI.
"""
from __future__ import annotations

import re
from typing import Any

from core.page_identity import is_sheet_index_page
from core.page_composer import BODY_W, page_render_diagnostics

# Contextual readable font floors (pt) — match each family's established floor.
_TEXT_FONT_FLOOR = 7.5
_DENSE_FONT_FLOOR = 6.5
_TEXT_FAMILIES = {"text"}
_DENSE_FAMILIES = {"matrix", "idfTable", "ioSchedule", "panelDetail", "rackLayout"}


def _font_floor_for_page(page: dict[str, Any]) -> float:
    family = page.get("pageFamily", "table")
    if family in _TEXT_FAMILIES:
        return _TEXT_FONT_FLOOR
    if family in _DENSE_FAMILIES:
        return _DENSE_FONT_FLOOR
    return 7.0


def _effective_font_pt(page: dict[str, Any], diag: dict[str, Any]) -> float:
    """Best-effort effective font size after scale-to-fit."""
    base = float(diag.get("fontSize") or 8.0)
    scale = float(diag.get("bestScale") or 1.0)
    blocks = page.get("blocks") or []
    for b in blocks:
        if b.get("type") == "excelRange" and b.get("bodyFontPt"):
            base = float(b["bodyFontPt"])
            break
        if b.get("type") == "idfNetworkTable" and b.get("fontSize"):
            return float(b["fontSize"])
    return base * scale


def _page_has_visible_content(page: dict[str, Any]) -> bool:
    if page.get("blankPagePlaceholder"):
        return True
    for b in page.get("blocks") or []:
        t = b.get("type")
        if t == "excelRange" and b.get("grid"):
            return True
        if t == "idfNetworkTable" and (b.get("leftRows") or b.get("rightRows") or b.get("rows")):
            return True
        if t in ("table", "matrix") and b.get("rows"):
            return True
        if t in ("paragraph", "bulletList", "sectionHeading", "cover", "companyInfo") and (
            b.get("text") or b.get("rows")
        ):
            return True
        if t in ("imagePlaceholder", "underlayPlaceholder", "canvas"):
            return True
    if page.get("canvasObjects"):
        return True
    return False


def _index_included_codes(project: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (sheetCode, sheetTab, sheetTitle) for each YES row in 00_INDEX."""
    from core.workbook_importer import _INDEX_ALIASES, _included, _header_map

    entries: list[tuple[str, str, str]] = []
    index_ws = None
    for ws in project.get("worksheets") or []:
        key = (ws.get("name") or "").replace(" ", "").replace("_", "").upper()
        if key in ("00INDEX", "INDEX") or (
            "INDEX" in key and "APPINDEX" not in key and "PROJECTMETA" not in key
        ):
            if key in ("00INDEX", "INDEX"):
                index_ws = ws
                break
            if index_ws is None:
                index_ws = ws
    if index_ws is None:
        return entries

    grid = index_ws.get("grid") or []
    if not grid:
        return entries

    header_idx = 0
    for i, row in enumerate(grid[:20]):
        low = {str(x).lower() for x in row if x}
        if low & _INDEX_ALIASES["sheet_tab"] and low & _INDEX_ALIASES["sheet_title"]:
            header_idx = i
            break
    col = _header_map([str(x) for x in grid[header_idx]])

    for row in grid[header_idx + 1 :]:
        tab = row[col["sheet_tab"]] if 0 <= col["sheet_tab"] < len(row) else ""
        title = row[col["sheet_title"]] if 0 <= col["sheet_title"] < len(row) else ""
        use_source = row[col["use_source"]] if 0 <= col["use_source"] < len(row) else ""
        include_raw = row[col["include"]] if 0 <= col["include"] < len(row) else ""
        code_raw = row[col["sheet_code"]] if 0 <= col["sheet_code"] < len(row) else ""
        if not _included(str(include_raw), str(title or tab), str(use_source)):
            continue
        code = str(code_raw).strip() or ""
        entries.append((code, str(tab).strip(), str(title or tab).strip()))
    return entries


def _is_generated_continuation(page: dict[str, Any]) -> bool:
    """True for auto-generated continuation pages (EMS 16.0a, 17.0a, …)."""
    if page.get("generatedContinuation"):
        return True
    code = (page.get("displaySheetCode") or page.get("sheetCode") or "").strip()
    if page.get("continuationOf"):
        return True
    # Continuation codes end with a single lowercase letter suffix (EMS 16.0a).
    if code and re.search(r"[a-z]$", code) and re.search(r"\d", code):
        base = re.sub(r"[a-z]$", "", code, flags=re.IGNORECASE)
        if base != code:
            return True
    return False


def _index_codes_from_rendered_page(project: dict[str, Any]) -> set[str]:
    """Sheet codes listed on the exported Sheet Index page grid (includes continuations)."""
    from core.workbook_importer import _find_index_header_row, _header_map, _index_row_sheet_code

    index_page = next(
        (p for p in project.get("pages", []) if is_sheet_index_page(p) and p.get("include", True)),
        None,
    )
    if not index_page:
        return set()
    block = next((b for b in (index_page.get("blocks") or []) if b.get("type") == "excelRange"), None)
    if not block:
        return set()
    grid = block.get("grid") or []
    if not grid:
        return set()
    header_idx = _find_index_header_row(grid)
    col = _header_map([str(x) for x in grid[header_idx]])
    code_col = col.get("sheet_code", -1)
    include_col = col.get("include", -1)
    codes: set[str] = set()
    for row in grid[header_idx + 1 :]:
        if include_col >= 0 and include_col < len(row):
            from core.workbook_importer import _included

            if not _included(str(row[include_col]), "", ""):
                continue
        code = _index_row_sheet_code(row, code_col)
        if code:
            codes.add(code)
    return codes


def compute_export_warnings(project: dict[str, Any]) -> list[dict[str, str]]:
    """Return export QA warnings: pageCode, pageTitle, issue, suggestedFix."""
    pages = [p for p in project.get("pages", []) if p.get("include", True)]
    diag_by_order = {d.get("outputOrder"): d for d in page_render_diagnostics(pages)}
    warnings: list[dict[str, str]] = []

    for page in pages:
        code = (page.get("displaySheetCode") or page.get("sheetCode") or "").strip()
        title = page.get("sheetTitle", "")
        diag = diag_by_order.get(page.get("order"), {})

        for lw in page.get("layoutWarnings") or []:
            if "TABLE OVERFLOW" in str(lw):
                warnings.append(
                    {
                        "pageCode": code,
                        "pageTitle": title,
                        "issue": str(lw),
                        "suggestedFix": "Widen the table to body width, enable continuation, or split the source range into logical sections.",
                    }
                )

        # Generated Sheet Index pages use their own fixed 46-row renderer; the
        # generic excel-range scale diagnostic describes the source worksheet,
        # not the published TOC chunk.
        if diag.get("clipping") and not is_sheet_index_page(page):
            warnings.append(
                {
                    "pageCode": code,
                    "pageTitle": title,
                    "issue": "Content may clip or render below the readable minimum scale.",
                    "suggestedFix": "Reduce row count, widen columns, or allow continuation pages for this sheet.",
                }
            )

        floor = _font_floor_for_page(page)
        eff_font = _effective_font_pt(page, diag)
        if not is_sheet_index_page(page) and eff_font < floor - 0.05:
            warnings.append(
                {
                    "pageCode": code,
                    "pageTitle": title,
                    "issue": f"Effective font {eff_font:.1f}pt is below the {floor}pt readable floor.",
                    "suggestedFix": "Split onto continuation pages or reduce content density so text stays readable.",
                }
            )

        # Narrow strip: table natural width far below body width at scale 1.
        content_w = int(diag.get("contentWidth") or 0)
        if content_w and content_w < int(BODY_W * 0.55) and page.get("pageFamily") == "text":
            warnings.append(
                {
                    "pageCode": code,
                    "pageTitle": title,
                    "issue": f"Table width {content_w}px is far below body width — may render as a tiny strip.",
                    "suggestedFix": "Ensure instruction/guideline tables expand to full body width in import geometry.",
                }
            )

        if not _page_has_visible_content(page):
            warnings.append(
                {
                    "pageCode": code,
                    "pageTitle": title,
                    "issue": "Page has no visible table or layout content.",
                    "suggestedFix": "Add content, link a source worksheet, or exclude this page from export.",
                }
            )

    # Index ↔ export sync.
    index_entries = _index_included_codes(project)
    if index_entries:
        page_codes = {
            (p.get("displaySheetCode") or p.get("sheetCode") or "").strip()
            for p in pages
        }
        index_codes = {e[0] for e in index_entries if e[0]}
        for code, tab, ititle in index_entries:
            if code and code not in page_codes:
                warnings.append(
                    {
                        "pageCode": code,
                        "pageTitle": ititle or tab,
                        "issue": f"Sheet Index lists {code!r} as included but no matching export page exists.",
                        "suggestedFix": "Ensure the worksheet is included in 00_INDEX with Include=YES and exists in the workbook.",
                    }
                )
        rendered_index_codes = _index_codes_from_rendered_page(project)
        effective_index_codes = index_codes | rendered_index_codes

        for p in pages:
            pcode = (p.get("displaySheetCode") or p.get("sheetCode") or "").strip()
            tab = (p.get("sheetTab") or "").strip().lower()
            if pcode and effective_index_codes and pcode not in effective_index_codes:
                # The index page itself is often absent from its own table.
                if is_sheet_index_page(p) or tab in ("00_index", "index"):
                    continue
                # Auto-generated continuations (EMS 16.0a) are not source rows.
                if _is_generated_continuation(p):
                    continue
                warnings.append(
                    {
                        "pageCode": pcode,
                        "pageTitle": p.get("sheetTitle", ""),
                        "issue": f"Export page {pcode!r} is missing from the included Sheet Index rows.",
                        "suggestedFix": "Add this sheet to 00_INDEX or exclude it from export.",
                    }
                )

        # Title block vs index sheet code mismatch (by tab).
        index_by_tab = {tab.lower(): code for code, tab, _ in index_entries if tab and code}
        for p in pages:
            if _is_generated_continuation(p):
                continue
            tab = (p.get("sheetTab") or "").strip().lower()
            pcode = (p.get("displaySheetCode") or p.get("sheetCode") or "").strip()
            icode = index_by_tab.get(tab)
            if icode and pcode and icode != pcode:
                warnings.append(
                    {
                        "pageCode": pcode,
                        "pageTitle": p.get("sheetTitle", ""),
                        "issue": f"Title block shows {pcode!r} but 00_INDEX assigns {icode!r} for tab {p.get('sheetTab')!r}.",
                        "suggestedFix": "Sync sheet codes from 00_INDEX or update the index Sheet Code column.",
                    }
                )

    return warnings
