"""Manifest-driven workbook-to-page compiler for schema-V2 projects."""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime, timezone
from typing import Any


def _stable_id(profile_id: str, recipe: dict[str, Any]) -> str:
    explicit = str(recipe.get("page id") or "").strip()
    if explicit:
        return explicit
    key = "|".join([
        profile_id,
        str(recipe.get("sheet code") or ""),
        str(recipe.get("sheet tab") or ""),
        str(recipe.get("page title") or ""),
    ])
    return f"generated-{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def _sheet(document: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next(
        (item for item in document.get("sheets", []) if item.get("name") == name and not item.get("archived")),
        None,
    )


def _rows(sheet: dict[str, Any] | None, limit: int = 5000) -> list[list[str]]:
    if not sheet:
        return []
    occupied: list[tuple[int, int, str]] = []
    for coord, payload in sheet.get("cells", {}).items():
        match = re.fullmatch(r"([A-Za-z]+)(\d+)", coord)
        if not match:
            continue
        column = 0
        for char in match.group(1).upper():
            column = column * 26 + ord(char) - 64
        value = payload.get("f") or payload.get("v") if isinstance(payload, dict) else payload
        occupied.append((int(match.group(2)), column, "" if value is None else str(value)))
    if not occupied:
        return []
    max_row = min(max(item[0] for item in occupied), limit)
    max_col = min(max(item[1] for item in occupied), 50)
    grid = [["" for _ in range(max_col)] for _ in range(max_row)]
    for row, column, value in occupied:
        if row <= max_row and column <= max_col:
            grid[row - 1][column - 1] = value
    while grid and not any(value.strip() for value in grid[-1]):
        grid.pop()
    return grid


def manifest_recipes(document: dict[str, Any]) -> list[dict[str, Any]]:
    grid = _rows(_sheet(document, "00_INDEX"), limit=10000)
    header_index = -1
    headers: dict[str, int] = {}
    for index, row in enumerate(grid[:75]):
        found = {value.strip().casefold(): col for col, value in enumerate(row) if value.strip()}
        if {"include", "sheet tab", "page title"}.issubset(found):
            header_index, headers = index, found
            break
    if header_index < 0:
        return []
    recipes: list[dict[str, Any]] = []
    for position, row in enumerate(grid[header_index + 1:], start=1):
        recipe = {
            name: row[column].strip() if column < len(row) else ""
            for name, column in headers.items()
        }
        if not any(recipe.get(key) for key in ("sheet code", "sheet tab", "page title", "page id")):
            continue
        try:
            recipe["order"] = int(float(recipe.get("order") or position))
        except ValueError:
            recipe["order"] = position
        recipe["included"] = str(recipe.get("include") or "").upper() in {"YES", "Y", "TRUE", "1", "X"}
        recipes.append(recipe)
    return sorted(recipes, key=lambda item: int(item["order"]))


def _generated_block(page_id: str, source: dict[str, Any] | None) -> list[dict[str, Any]]:
    grid = _rows(source)
    headers = grid[1] if len(grid) > 1 else (grid[0] if grid else [])
    rows = grid[2:] if len(grid) > 2 else []
    return [{
        "id": f"{page_id}-generated",
        "type": "table",
        "styleRole": "generated",
        "headers": headers,
        "rows": rows,
        "editable": False,
    }]


def _color_category(recipe: dict[str, Any]) -> str:
    color = str(recipe.get("color") or "").casefold()
    family = str(recipe.get("family") or "").casefold()
    if not recipe.get("included"):
        return "excluded-archived"
    if "network" in family or color == "blue":
        return "network-data"
    if "lighting" in family or color == "orange":
        return "lighting"
    if "layout" in family or color == "purple" and str(recipe.get("source mode")).casefold() == "manual":
        return "manual-hybrid"
    if "field" in family:
        return "field-instructions"
    if "commission" in family or "closeout" in family or color == "green":
        return "commissioning-closeout"
    if str(recipe.get("page type") or "").casefold() == "sheet index":
        return "page-manifest"
    return "included-front-matter"


def build_page(profile_id: str, recipe: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any]:
    page_id = _stable_id(profile_id, recipe)
    source_mode = str(recipe.get("source mode") or "canonical").casefold()
    manual = source_mode == "manual" or str(recipe.get("render profile") or "").casefold() == "manual_hybrid"
    result = {
        "id": page_id,
        "order": int(recipe["order"]) - 1,
        "include": bool(recipe["included"]),
        "issueStatus": str(recipe.get("issue status") or "draft").casefold(),
        "sheetCode": recipe.get("sheet code", ""),
        "displaySheetCode": recipe.get("sheet code", ""),
        "sheetTitle": recipe.get("page title", ""),
        "sheetTab": recipe.get("sheet tab", ""),
        "pageType": recipe.get("page type", "data-grid"),
        "pageFamily": recipe.get("page title") or recipe.get("family", ""),
        "layoutProfile": recipe.get("render profile", "front_matter_table"),
        "splitMode": recipe.get("split mode", "auto"),
        "sourceMode": recipe.get("source mode", "canonical"),
        "syncDirection": recipe.get("sync direction", "app_to_workbook"),
        "colorCategory": _color_category(recipe),
        "dataState": recipe.get("data state", ""),
        "required": str(recipe.get("required") or "").upper() == "YES",
        "template": "singh360-standard",
        "templateId": "manifest-v2",
        "sourceSheet": source.get("name") if source else recipe.get("sheet tab"),
        "blocks": [] if manual else _generated_block(page_id, source),
        "canvasObjects": [],
        "assets": [],
        "notes": recipe.get("notes", ""),
        "protectedManual": manual,
    }
    if not manual:
        result["generation"] = {
            "profileRecipeId": recipe.get("page id") or page_id,
            "entityKey": "base",
            "layerVersion": 2,
        }
    return result


def preview_compile(project: dict[str, Any], document: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    recipes = manifest_recipes(document)
    existing = {page.get("id"): page for page in project.get("pages", [])}
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []
    for recipe in recipes:
        page_id = _stable_id(profile["id"], recipe)
        source_name = str(recipe.get("sheet tab") or "")
        if str(recipe.get("source mode") or "").casefold() not in {"manual", "workbook"} and not _sheet(document, source_name):
            warnings.append(f"{recipe.get('sheet code')}: source worksheet {source_name} is unavailable.")
        operations.append({
            "action": "update" if page_id in existing else "add",
            "pageId": page_id,
            "sheetCode": recipe.get("sheet code"),
            "family": recipe.get("page title") or recipe.get("family"),
            "sourceSheet": source_name,
            "included": recipe["included"],
        })
    manifest_ids = {_stable_id(profile["id"], recipe) for recipe in recipes}
    for page in project.get("pages", []):
        if page.get("id") not in manifest_ids:
            operations.append({
                "action": "unchanged" if not page.get("generation") else "exclude",
                "pageId": page.get("id"),
                "sheetCode": page.get("sheetCode", ""),
            })
    return {
        "projectId": project["id"],
        "operations": operations,
        "warnings": warnings,
        "previewedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def apply_compile(project: dict[str, Any], document: dict[str, Any], profile: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    preview = preview_compile(project, document, profile)
    existing = {page.get("id"): page for page in project.get("pages", [])}
    pages: list[dict[str, Any]] = []
    manifest_ids: set[str] = set()
    for recipe in manifest_recipes(document):
        page_id = _stable_id(profile["id"], recipe)
        manifest_ids.add(page_id)
        source = _sheet(document, str(recipe.get("sheet tab") or ""))
        fresh = build_page(profile["id"], recipe, source)
        old = existing.get(page_id)
        if old:
            preserved = copy.deepcopy(old)
            for key, value in fresh.items():
                if key not in {"canvasObjects", "assets", "blocks", "notes"}:
                    preserved[key] = value
            if fresh.get("generation"):
                preserved["blocks"] = fresh["blocks"]
                preserved["generation"] = fresh["generation"]
            pages.append(preserved)
        else:
            pages.append(fresh)
    for page in project.get("pages", []):
        if page.get("id") in manifest_ids:
            continue
        preserved = copy.deepcopy(page)
        if preserved.get("generation"):
            preserved["include"] = False
        pages.append(preserved)
    pages.sort(key=lambda item: int(item.get("order", 999999)))
    result = copy.deepcopy(project)
    result["pages"] = pages
    result["lastCompile"] = {
        "appliedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workbookRevision": document.get("revision"),
        "operations": preview["operations"],
    }
    result["compileWarnings"] = preview["warnings"]
    return result, preview
