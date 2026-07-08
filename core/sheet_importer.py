"""core/sheet_importer.py — import one or more worksheets from an XLSX file into
an existing project WITHOUT rebuilding the whole package.

Exported API:
  preview_workbook_sheets(xlsx_path)  → list of sheet descriptors
  import_workbook_sheets(project, xlsx_path, sheet_names, ...)  → updated project + new pages
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from core.project_model import classify_page_type, sanitize_json
from core.page_normalizer import normalize_page
from core.page_composer import page_family
from core.workbook_importer import _worksheet_payload, _extract_embedded_images, _safe_name


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id(prefix: str = "p") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def preview_workbook_sheets(xlsx_path: str | Path) -> list[dict[str, Any]]:
    """Return sheet descriptors for all sheets in the workbook (no file storage)."""
    wb = load_workbook(filename=str(xlsx_path), data_only=False, read_only=True)
    out: list[dict[str, Any]] = []
    for name in wb.sheetnames:
        ws = wb[name]
        # Sample the first 3 rows to estimate row/column counts.
        rows_seen = 0
        cols_seen = 0
        for row in ws.iter_rows(max_row=5):
            rows_seen += 1
            cols_seen = max(cols_seen, sum(1 for c in row if c.value is not None))
        detected_type = classify_page_type(name, name, "")
        out.append({
            "sheetName": name,
            "rowEstimate": ws.max_row or 0,
            "colEstimate": ws.max_column or 0,
            "detectedPageType": detected_type,
        })
    wb.close()
    return out


def import_workbook_sheets(
    project: dict[str, Any],
    xlsx_path: str | Path,
    sheet_names: list[str],
    *,
    insert_after_page_id: str | None = None,
    replace_page_id: str | None = None,
    append: bool = False,
    template_override: str | None = None,
    assets_dir=None,
    asset_url_prefix: str | None = None,
    source_filename: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Import selected worksheets into the project.

    Returns the mutated project (caller must save) and the list of new or updated page dicts.
    When ``replace_page_id`` is set, the first selected sheet replaces the linked source
    on that existing page — no duplicate output page is created.
    """
    xlsx_path = Path(xlsx_path)
    wb = load_workbook(filename=str(xlsx_path), data_only=False)
    src_filename = source_filename or xlsx_path.name

    # Register the workbook as a new source entry in the project.
    src_id = _new_id("src")
    project.setdefault("sources", []).append({
        "id": src_id,
        "type": "imported-workbook",
        "name": src_filename,
        "path": str(xlsx_path),
        "importedAt": _ts(),
    })

    # Register the worksheets in project.worksheets so they are available in
    # Source View alongside the original workbook tabs.
    existing_ws_names = {ws["name"] for ws in project.get("worksheets", [])}
    ws_id_by_name: dict[str, str] = {}
    for sheet_name in sheet_names:
        if sheet_name not in wb.sheetnames:
            continue
        payload = _worksheet_payload(wb[sheet_name])
        embedded = _extract_embedded_images(
            wb[sheet_name], assets_dir, asset_url_prefix or "", sheet_name
        )
        ws_id = _new_id("ws")
        ws_id_by_name[sheet_name] = ws_id
        unique_name = sheet_name
        if unique_name in existing_ws_names:
            unique_name = f"{sheet_name} (imported {_ts()[:10]})"
        project.setdefault("worksheets", []).append({
            "id": ws_id,
            "name": unique_name,
            "sourceId": src_id,
            "visible": True,
            "classHint": "imported",
            "grid": payload["grid"],
            "formulas": payload.get("formulas", {}),
            "styles": payload.get("styles", {}),
            "mergedCells": payload.get("mergedCells", []),
            "rowHeights": payload.get("rowHeights", {}),
            "columnWidths": payload.get("columnWidths", {}),
            "embeddedImages": embedded,
            "provenance": {
                "sheet": sheet_name,
                "sourceFile": src_filename,
                "importedAt": _ts(),
            },
        })
        existing_ws_names.add(unique_name)

    pages: list[dict[str, Any]] = project.get("pages", [])

    # Replace the linked source on an existing output page (no new page tab).
    if replace_page_id:
        if len(sheet_names) != 1:
            wb.close()
            raise ValueError("replace_page_id requires exactly one sheet name")
        sheet_name = sheet_names[0]
        ws_id = ws_id_by_name.get(sheet_name)
        ws_data = next((w for w in project.get("worksheets", []) if w.get("id") == ws_id), None)
        target_idx = next((i for i, p in enumerate(pages) if p.get("id") == replace_page_id), None)
        if target_idx is None or not ws_data:
            wb.close()
            raise ValueError(f"replace page {replace_page_id!r} or worksheet not found")
        target = pages[target_idx]
        group_id = target.get("pageGroupId") or target.get("id")
        # Drop stale generated continuations for this page group.
        pages = [
            p for p in pages
            if not (
                p.get("generatedContinuation")
                and (p.get("continuationOf") == group_id or p.get("pageGroupId") == group_id)
                and p.get("id") != replace_page_id
            )
        ]
        target_idx = next((i for i, p in enumerate(pages) if p.get("id") == replace_page_id), None)
        page_type = template_override or target.get("pageType") or classify_page_type(sheet_name, sheet_name, "")
        blocks = normalize_page(ws_data, ws_id, page_type, sheet_name)
        updated = {
            **target,
            "linkedWorksheetId": ws_id,
            "blocks": blocks,
            "importedFrom": {
                "sourceFile": src_filename,
                "sheetName": sheet_name,
                "importedAt": _ts(),
                "replacedPageId": replace_page_id,
            },
        }
        pages[target_idx] = updated
        for i, p in enumerate(pages):
            p["order"] = i + 1
        project["pages"] = pages
        project.setdefault("importHistory", []).append({
            "sourceFile": src_filename,
            "sheetNames": sheet_names,
            "importedAt": _ts(),
            "pagesAdded": 0,
            "replacedPageId": replace_page_id,
        })
        wb.close()
        return sanitize_json(project), [updated]

    # Compute the insertion index in pages.
    if insert_after_page_id:
        ref_idx = next(
            (i for i, p in enumerate(pages) if p.get("id") == insert_after_page_id), None
        )
        insert_at = (ref_idx + 1) if ref_idx is not None else len(pages)
    else:
        insert_at = len(pages)  # append

    new_pages: list[dict[str, Any]] = []
    for sheet_name in sheet_names:
        if sheet_name not in wb.sheetnames:
            continue
        ws_id = ws_id_by_name.get(sheet_name)
        ws_data = next((w for w in project.get("worksheets", []) if w.get("id") == ws_id), None)
        if not ws_data:
            continue
        page_type = template_override or classify_page_type(sheet_name, sheet_name, "")
        blocks = normalize_page(ws_data, ws_id, page_type, sheet_name)
        page = {
            "id": _new_id("page"),
            "order": 0,  # will be fixed below
            "include": True,
            "sheetCode": "NEW",
            "displaySheetCode": "NEW",
            "sheetTitle": sheet_name,
            "sheetTab": sheet_name,
            "pageType": page_type,
            "pageFamily": page_family(sheet_name, sheet_name, ""),
            "templateId": "ansi-b-standard",
            "linkedWorksheetId": ws_id,
            "blocks": blocks,
            "canvasObjects": [],
            "assets": [],
            "underlays": [],
            "notes": "",
            "revisionRows": [],
            "pageGroupId": _new_id("pg"),
            "continuationOf": None,
            "continuationIndex": 0,
            "generatedContinuation": False,
            "layoutWarnings": [],
            "importedFrom": {
                "sourceFile": src_filename,
                "sheetName": sheet_name,
                "importedAt": _ts(),
            },
        }
        new_pages.append(page)

    # Splice new pages into the page list and re-assign order values.
    for i, p in enumerate(new_pages):
        pages.insert(insert_at + i, p)
    for i, p in enumerate(pages):
        p["order"] = i + 1

    project["pages"] = pages
    project.setdefault("importHistory", []).append({
        "sourceFile": src_filename,
        "sheetNames": sheet_names,
        "importedAt": _ts(),
        "pagesAdded": len(new_pages),
    })
    project["renumberSuggested"] = True

    wb.close()
    return sanitize_json(project), new_pages
