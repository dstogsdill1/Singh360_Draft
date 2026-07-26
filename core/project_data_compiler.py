"""Deterministic workbook-to-page compiler for schema-V2 projects."""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from typing import Any

FAMILY_SHEET_MAP = {
    "Cover": "00_PROJECT_META",
    "Sheet Index / TOC": "00_INDEX",
    "Guidelines": "00_STYLE_GUIDE",
    "Abbreviations / Symbol Key": "00_STYLE_GUIDE",
    "Project Directory": "04_PROJECT_DIRECTORY",
    "Project Scope": "03_SCOPE_AND_PLAN",
    "Workflow / Milestones": "06_WORKFLOW_MILESTONES",
    "Responsibility Matrix": "05_RESPONSIBILITY_MATRIX",
    "Bill of Materials": "19_BILL_OF_MATERIALS",
    "RDM / IDF Network Table": "11_NETWORK_PORTS",
    "Panel / WICP Summary": "12_PANELS",
    "Panel / WICP I/O": "13_PANEL_IO",
    "Refrigeration Circuit Schedule": "14_REFRIG_CIRCUITS",
    "Rack I/O / Description": "15_RACKS",
    "HVAC Equipment / I/O": "16_HVAC_EQUIPMENT",
    "Lighting Output Matrix": "17_LIGHTING_OUTPUTS",
    "Cable Pull / Termination Schedule": "18_CABLE_SCHEDULE",
    "Commissioning / Point-to-Point": "20_COMMISSIONING",
    "Company Info": "00_PROJECT_META",
}
PAGE_TYPE = {"Cover": "cover", "Sheet Index / TOC": "index"}


def _stable_id(profile_id: str, family: str, entity_key: str = "base") -> str:
    digest = hashlib.sha256(f"{profile_id}|{family}|{entity_key}".encode()).hexdigest()[:20]
    return f"generated-{digest}"


def _sheet(document: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((item for item in document.get("sheets", []) if item.get("name") == name and not item.get("archived")), None)


def _rows(sheet: dict[str, Any] | None) -> list[list[str]]:
    if not sheet:
        return []
    cells = sheet.get("cells", {})
    occupied: list[tuple[int, int, str]] = []
    for coord, payload in cells.items():
        letters = "".join(ch for ch in coord if ch.isalpha())
        digits = "".join(ch for ch in coord if ch.isdigit())
        if not letters or not digits:
            continue
        col = 0
        for char in letters.upper():
            col = col * 26 + ord(char) - 64
        value = payload.get("f") or payload.get("v") if isinstance(payload, dict) else payload
        occupied.append((int(digits), col, "" if value is None else str(value)))
    if not occupied:
        return []
    max_row = min(max(item[0] for item in occupied), 500)
    max_col = min(max(item[1] for item in occupied), 30)
    grid = [["" for _ in range(max_col)] for _ in range(max_row)]
    for row, col, value in occupied:
        if row <= max_row and col <= max_col:
            grid[row - 1][col - 1] = value
    while grid and not any(value.strip() for value in grid[-1]):
        grid.pop()
    return grid


def build_generated_page(profile_id: str, family: str, sheet: dict[str, Any] | None, order: int) -> dict[str, Any]:
    grid = _rows(sheet)
    headers = grid[1] if len(grid) > 1 else (grid[0] if grid else [])
    rows = grid[2:] if len(grid) > 2 else []
    page_id = _stable_id(profile_id, family)
    return {
        "id": page_id, "order": order, "include": True, "issueStatus": "draft",
        "sheetCode": "", "displaySheetCode": "", "sheetTitle": family,
        "sheetTab": sheet.get("name", family[:31]) if sheet else family[:31],
        "pageType": PAGE_TYPE.get(family, "data-grid"), "pageFamily": family,
        "layoutProfile": "network_48_port" if family == "RDM / IDF Network Table" else "front_matter_table",
        "template": "singh360-standard", "templateId": "generated-v1",
        "sourceSheet": sheet.get("name") if sheet else None,
        "blocks": [{
            "id": f"{page_id}-generated", "type": "table", "styleRole": "generated",
            "headers": headers, "rows": rows, "editable": False,
        }],
        "canvasObjects": [], "assets": [], "notes": "",
        "generation": {"profileRecipeId": family, "entityKey": "base", "layerVersion": 1},
    }


def preview_compile(project: dict[str, Any], document: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    existing = {page.get("id"): page for page in project.get("pages", [])}
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []
    families = profile.get("defaultIncludedFamilies", [])
    for order, family in enumerate(families):
        source_name = FAMILY_SHEET_MAP.get(family)
        source = _sheet(document, source_name) if source_name else None
        page_id = _stable_id(profile["id"], family)
        if not source:
            warnings.append(f"{family}: source worksheet {source_name or 'not configured'} is unavailable; page remains available but blank.")
        operations.append({"action": "update" if page_id in existing else "add", "pageId": page_id, "family": family, "sourceSheet": source_name})
    generated_ids = {item["pageId"] for item in operations}
    for page in project.get("pages", []):
        if page.get("generation") and page.get("id") not in generated_ids:
            operations.append({"action": "exclude", "pageId": page["id"], "family": page.get("pageFamily", "")})
        elif not page.get("generation"):
            operations.append({"action": "unchanged", "pageId": page.get("id"), "family": page.get("pageFamily", "Manual")})
    return {"projectId": project["id"], "operations": operations, "warnings": warnings, "previewedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def apply_compile(project: dict[str, Any], document: dict[str, Any], profile: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    preview = preview_compile(project, document, profile)
    existing = {page.get("id"): page for page in project.get("pages", [])}
    generated: list[dict[str, Any]] = []
    for order, family in enumerate(profile.get("defaultIncludedFamilies", [])):
        source_name = FAMILY_SHEET_MAP.get(family)
        new_page = build_generated_page(profile["id"], family, _sheet(document, source_name) if source_name else None, order)
        old = existing.get(new_page["id"])
        if old:
            # Generated blocks are authoritative; every manual/page-specific field survives.
            preserved = copy.deepcopy(old)
            preserved["blocks"] = new_page["blocks"]
            preserved["sourceSheet"] = new_page["sourceSheet"]
            preserved["generation"] = new_page["generation"]
            preserved["include"] = True
            preserved["order"] = order
            generated.append(preserved)
        else:
            generated.append(new_page)
    generated_ids = {page["id"] for page in generated}
    manual = [copy.deepcopy(page) for page in project.get("pages", []) if page.get("id") not in generated_ids and not page.get("generation")]
    retired = [copy.deepcopy(page) for page in project.get("pages", []) if page.get("id") not in generated_ids and page.get("generation")]
    for page in retired:
        page["include"] = False
    pages = generated + manual + retired
    cover = next((page for page in pages if page.get("pageFamily") == "Cover"), None)
    index = next((page for page in pages if page.get("pageFamily") == "Sheet Index / TOC"), None)
    ordered = [item for item in (cover, index) if item]
    ordered.extend(page for page in pages if page not in ordered)
    for position, page in enumerate(ordered):
        page["order"] = position
    result = copy.deepcopy(project)
    result["pages"] = ordered
    result["lastCompile"] = {"appliedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "workbookRevision": document.get("revision"), "operations": preview["operations"]}
    result["compileWarnings"] = preview["warnings"]
    return result, preview
