"""Import exactly selected worksheets into an existing Singh360 project.

The one-sheet workflow preserves the worksheet's Excel geometry and styling and
never rebuilds the full project package.  The source workbook remains untouched.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

from core.project_model import classify_page_type, sanitize_json
from core.page_normalizer import normalize_page
from core.page_composer import page_family
from core.workbook_importer import (
    _extract_embedded_images,
    _parse_index,
    _safe_name,
    _worksheet_payload,
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str = "p") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def preview_workbook_sheets(xlsx_path: str | Path) -> list[dict[str, Any]]:
    wb = load_workbook(filename=str(xlsx_path), data_only=False, read_only=True)
    out: list[dict[str, Any]] = []
    try:
        index_name = next((n for n in wb.sheetnames if re.sub(r"[^a-z0-9]", "", n.lower()) in {"00index", "index"}), None)
        index_entries = _parse_index(wb, index_name) if index_name else []
        by_tab = {str(item.get("sheetTab") or "").strip().lower(): item for item in index_entries}
        for name in wb.sheetnames:
            ws = wb[name]
            meta = by_tab.get(name.strip().lower(), {})
            out.append({
                "sheetName": name,
                "rowEstimate": ws.max_row or 0,
                "colEstimate": ws.max_column or 0,
                "detectedPageType": classify_page_type(name, str(meta.get("sheetTitle") or name), ""),
                "sheetCode": str(meta.get("sheetCodeRaw") or "").strip(),
                "pageTitle": str(meta.get("sheetTitle") or name).strip(),
                "listedInIndex": bool(meta),
                "printArea": str(getattr(ws, "print_area", "") or ""),
            })
    finally:
        wb.close()
    return out


def _index_meta(wb, sheet_name: str) -> dict[str, Any]:
    index_name = next((n for n in wb.sheetnames if re.sub(r"[^a-z0-9]", "", n.lower()) in {"00index", "index"}), None)
    if not index_name:
        return {}
    for item in _parse_index(wb, index_name):
        if str(item.get("sheetTab") or "").strip().lower() == sheet_name.strip().lower():
            return item
    return {}


def _parse_print_area(value: Any) -> tuple[int, int, int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    # Use the first area only.  Sheet names may be quoted and are discarded.
    text = text.split(",", 1)[0]
    if "!" in text:
        text = text.split("!", 1)[1]
    text = text.replace("$", "")
    if ":" not in text:
        return None
    start, end = text.split(":", 1)
    try:
        scol, srow = coordinate_from_string(start)
        ecol, erow = coordinate_from_string(end)
        return srow - 1, column_index_from_string(scol) - 1, erow - 1, column_index_from_string(ecol) - 1
    except Exception:
        return None


def _slice_payload_to_print_area(payload: dict[str, Any]) -> dict[str, Any]:
    area = _parse_print_area(payload.get("printArea"))
    if area is None:
        return payload
    sr, sc, er, ec = area
    grid = payload.get("grid") or []
    if not grid:
        return payload
    er = min(er, len(grid) - 1)
    ec = min(ec, max((len(row) for row in grid), default=1) - 1)
    if er < sr or ec < sc:
        return payload
    out = dict(payload)
    out["grid"] = [list(row[sc : ec + 1]) for row in grid[sr : er + 1]]
    out["colWidthsPx"] = list((payload.get("colWidthsPx") or [])[sc : ec + 1])
    out["rowHeightsPx"] = list((payload.get("rowHeightsPx") or [])[sr : er + 1])

    styles: dict[str, Any] = {}
    for key, style in (payload.get("styles") or {}).items():
        match = re.fullmatch(r"([A-Z]+)(\d+)", str(key))
        if not match:
            continue
        col = column_index_from_string(match.group(1)) - 1
        row = int(match.group(2)) - 1
        if sr <= row <= er and sc <= col <= ec:
            # Small local A1 converter.
            n = col - sc + 1
            letters = ""
            while n:
                n, rem = divmod(n - 1, 26)
                letters = chr(65 + rem) + letters
            styles[f"{letters}{row - sr + 1}"] = style
    out["styles"] = styles

    merges: list[dict[str, int]] = []
    for merge in payload.get("mergedCells") or []:
        msr = int(merge.get("startRow", 0)); msc = int(merge.get("startCol", 0))
        mer = int(merge.get("endRow", msr)); mec = int(merge.get("endCol", msc))
        if msr >= sr and msc >= sc and mer <= er and mec <= ec:
            merges.append({
                "startRow": msr - sr, "startCol": msc - sc,
                "endRow": mer - sr, "endCol": mec - sc,
            })
    out["mergedCells"] = merges
    out["sourceRange"] = f"PRINT_AREA:{payload.get('printArea')}"
    return out


def _exact_excel_block(ws_data: dict[str, Any], ws_id: str) -> dict[str, Any]:
    data = _slice_payload_to_print_area(ws_data)
    return {
        "id": f"{ws_id}_excel_exact",
        "type": "excelRange",
        "sourceWorksheetId": ws_id,
        "sourceSheet": data.get("sourceSheet") or data.get("name") or "",
        "sourceRange": data.get("sourceRange") or "",
        "grid": data.get("grid") or [],
        "styles": data.get("styles") or {},
        "mergedCells": data.get("mergedCells") or [],
        "colWidths": data.get("colWidthsPx") or [],
        "rowHeights": data.get("rowHeightsPx") or [],
        "renderMode": "excel_exact",
        "splitMode": "none",
        "allowContinuation": False,
        "scaleMode": "fit_body",
        "minScale": 0.35,
        "trimBlankRows": False,
        "trimBlankColumns": False,
        "editable": True,
        "layoutProfile": "single_sheet_excel_exact",
    }


def import_workbook_sheets(
    project: dict[str, Any],
    xlsx_path: str | Path,
    sheet_names: list[str],
    *,
    insert_after_page_id: str | None = None,
    replace_page_id: str | None = None,
    append: bool = False,
    template_override: str | None = None,
    preserve_exact: bool = True,
    assets_dir=None,
    asset_url_prefix: str | None = None,
    source_filename: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Import only the requested worksheets; never rebuild the full package."""
    if preserve_exact and len(sheet_names) != 1:
        raise ValueError("Add One Formatted Sheet requires exactly one worksheet.")

    xlsx_path = Path(xlsx_path)
    keep_vba = xlsx_path.suffix.lower() == ".xlsm"
    wb = load_workbook(filename=str(xlsx_path), data_only=False, keep_vba=keep_vba)
    wb_values = load_workbook(filename=str(xlsx_path), data_only=True, keep_vba=keep_vba)
    src_filename = source_filename or xlsx_path.name
    try:
        src_id = _new_id("src")
        project.setdefault("sources", []).append({
            "id": src_id,
            "type": "imported-workbook",
            "name": src_filename,
            "path": str(xlsx_path),
            "importedAt": _ts(),
        })

        existing_ws_names = {str(ws.get("name") or "") for ws in project.get("worksheets", [])}
        ws_id_by_name: dict[str, str] = {}
        meta_by_name: dict[str, dict[str, Any]] = {}
        for sheet_name in sheet_names:
            if sheet_name not in wb.sheetnames:
                continue
            payload = _worksheet_payload(wb[sheet_name], wb_values[sheet_name])
            embedded = _extract_embedded_images(wb[sheet_name], assets_dir, asset_url_prefix or "", sheet_name)
            ws_id = _new_id("ws")
            ws_id_by_name[sheet_name] = ws_id
            meta_by_name[sheet_name] = _index_meta(wb, sheet_name)
            unique_name = sheet_name
            if unique_name in existing_ws_names:
                unique_name = f"{sheet_name} (imported {_ts()[:10]})"
            project.setdefault("worksheets", []).append({
                "id": ws_id,
                "name": unique_name,
                "sourceId": src_id,
                "visible": True,
                "classHint": "excel_exact" if preserve_exact else "imported",
                **payload,
                "embeddedImages": embedded,
                "provenance": {
                    "sheet": sheet_name,
                    "sourceFile": src_filename,
                    "sourcePath": str(xlsx_path),
                    "importedAt": _ts(),
                },
            })
            existing_ws_names.add(unique_name)

        pages: list[dict[str, Any]] = project.get("pages", [])

        def build_page(sheet_name: str, ws_id: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
            ws_data = next(w for w in project.get("worksheets", []) if w.get("id") == ws_id)
            meta = meta_by_name.get(sheet_name) or {}
            title = str(meta.get("sheetTitle") or (target or {}).get("sheetTitle") or sheet_name).strip()
            code = str(meta.get("sheetCodeRaw") or (target or {}).get("displaySheetCode") or (target or {}).get("sheetCode") or "NEW").strip()
            detected = template_override or classify_page_type(sheet_name, title, "")
            # A deliberately formatted worksheet is a worksheet page, even when
            # its title contains words such as Layout or Location.
            page_type = detected if detected in {"cover", "index"} else ("data-grid" if preserve_exact else detected)
            family = page_family(sheet_name, title, "")
            blocks = [_exact_excel_block(ws_data, ws_id)] if preserve_exact else normalize_page(ws_data, ws_id, page_type, title)
            base = dict(target or {})
            base.update({
                "linkedWorksheetId": ws_id,
                "sheetCode": code or "NEW",
                "displaySheetCode": code or "NEW",
                "sheetTitle": title,
                "sheetTab": sheet_name,
                "pageType": page_type,
                "pageFamily": family,
                "renderMode": "excel_exact" if preserve_exact else base.get("renderMode", "normalized"),
                "layoutProfile": "single_sheet_excel_exact" if preserve_exact else base.get("layoutProfile", ""),
                "splitMode": "none" if preserve_exact else base.get("splitMode", "auto_rows"),
                "allowContinuation": False if preserve_exact else base.get("allowContinuation", True),
                "scaleMode": "fit_body",
                "trimBlankRows": False if preserve_exact else base.get("trimBlankRows", True),
                "trimBlankColumns": False if preserve_exact else base.get("trimBlankColumns", True),
                "blocks": blocks,
                "notes": str(meta.get("notes") or base.get("notes") or ""),
                "importedFrom": {
                    "sourceFile": src_filename,
                    "sheetName": sheet_name,
                    "importedAt": _ts(),
                    "preservedExcelStyle": bool(preserve_exact),
                },
            })
            return base

        if replace_page_id:
            sheet_name = sheet_names[0]
            ws_id = ws_id_by_name.get(sheet_name)
            target_idx = next((i for i, page in enumerate(pages) if page.get("id") == replace_page_id), None)
            if target_idx is None or not ws_id:
                raise ValueError("The current page or selected worksheet could not be found.")
            target = pages[target_idx]
            group_id = target.get("pageGroupId") or target.get("id")
            pages = [p for p in pages if not (p.get("generatedContinuation") and (p.get("continuationOf") == group_id or p.get("pageGroupId") == group_id) and p.get("id") != replace_page_id)]
            target_idx = next(i for i, page in enumerate(pages) if page.get("id") == replace_page_id)
            updated = build_page(sheet_name, ws_id, pages[target_idx])
            pages[target_idx] = updated
            for i, page in enumerate(pages): page["order"] = i + 1
            project["pages"] = pages
            project.setdefault("importHistory", []).append({"sourceFile": src_filename, "sheetNames": sheet_names, "importedAt": _ts(), "pagesAdded": 0, "replacedPageId": replace_page_id})
            return sanitize_json(project), [updated]

        if insert_after_page_id:
            ref_idx = next((i for i, page in enumerate(pages) if page.get("id") == insert_after_page_id), None)
            insert_at = ref_idx + 1 if ref_idx is not None else len(pages)
        else:
            insert_at = len(pages)

        new_pages: list[dict[str, Any]] = []
        for sheet_name in sheet_names:
            ws_id = ws_id_by_name.get(sheet_name)
            if not ws_id:
                continue
            page = build_page(sheet_name, ws_id)
            page.update({
                "id": _new_id("page"), "order": 0, "include": True,
                "templateId": "ansi-b-standard", "canvasObjects": [], "assets": [], "underlays": [],
                "revisionRows": [], "pageGroupId": _new_id("pg"), "continuationOf": None,
                "continuationIndex": 0, "generatedContinuation": False, "layoutWarnings": [],
            })
            new_pages.append(page)

        for i, page in enumerate(new_pages): pages.insert(insert_at + i, page)
        for i, page in enumerate(pages): page["order"] = i + 1
        project["pages"] = pages
        project.setdefault("importHistory", []).append({"sourceFile": src_filename, "sheetNames": sheet_names, "importedAt": _ts(), "pagesAdded": len(new_pages), "preservedExcelStyle": bool(preserve_exact)})
        project["renumberSuggested"] = any((page.get("displaySheetCode") or "NEW") == "NEW" for page in new_pages)
        return sanitize_json(project), new_pages
    finally:
        wb.close()
        wb_values.close()
