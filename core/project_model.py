from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


PROJECT_SCHEMA_VERSION = 1


def _clean_scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:
            return ""
    if isinstance(value, str):
        txt = value.strip()
        return "" if txt.lower() in {"nan", "nat", "<na>", "undefined"} else value
    return value


def sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_json(v) for v in value]
    return _clean_scalar(value)


def classify_page_type(sheet_tab: str, title: str, use_source: str = "") -> str:
    text = f"{sheet_tab} {title} {use_source}".lower()
    if any(k in text for k in ("cover", "title sheet")):
        return "cover"
    if "index" in text:
        return "index"
    if any(k in text for k in ("bom", "material", "matrix", "schedule", "table", "notes", "guideline")):
        return "data-grid"
    # I/O schedules and rack/network tables sometimes carry "layout" or
    # "location" in their tab/title (e.g. SA38's "Rack A I/O & Layout") but
    # are real tabular content, not a blank drawing/floor-plan page — check
    # for tabular-I/O keywords before the canvas fallback below. Mirrors the
    # more complete family mapping in core/page_composer.py::page_family
    # (see docs/PAGE_TYPE_MAPPING.md); without this a real 200+ row I/O
    # schedule silently renders as an empty canvas page.
    if any(k in text for k in ("i/o", "io schedule", "points list", "bacnet", "rack", "condenser", "idf", "network frame")):
        return "data-grid"
    if any(k in text for k in ("one-line", "oneline", "layout", "diagram", "schematic", "wiring", "location")):
        return "canvas"
    return "data-grid"


def default_template() -> dict[str, Any]:
    return {
        "id": "ansi-b-standard",
        "name": "ANSI B 17x11 Landscape",
        "sheet": {"width": 1632, "height": 1056, "unit": "px"},
        "body": {"x": 16, "y": 16, "width": 1600, "height": 880},
        "titleBlock": {"x": 16, "y": 896, "width": 1600, "height": 144},
    }


def default_project(project_id: str | None = None) -> dict[str, Any]:
    created = utcnow_iso()
    return {
        "id": project_id or uuid4().hex[:16],
        "schemaVersion": PROJECT_SCHEMA_VERSION,
        "metadata": {
            "projectName": "",
            "storeNumber": "",
            "client": "",
            "location": "",
            "address": "",
            "createdBy": "Singh360 Inc.",
            "createdDate": created,
            "sourceFile": "",
            "version": "",
            "templateVersion": "",
            "revision": "",
            "status": "Draft",
            "purpose": "",
        },
        "sources": [],
        "worksheets": [],
        "pages": [],
        "templates": [default_template()],
        "assets": [],
        "revisionLog": [],
        "revisionHistory": [],
        "projectDisplayName": "",
        "projectProfile": "ems",
        "projectFolder": "",
        "projectRoot": "",
        "linkedProjectRoot": "",
        "projectFilesMode": "",
        "sourceWorkbookName": "",
        "modified": created,
        "importWarnings": [],
        "archivedPages": [],
        "workbookSync": {},
    }


def recalc_page_numbers(project: dict[str, Any]) -> None:
    pages = project.get("pages", [])
    included = [p for p in pages if p.get("include", True)]
    total = len(included)
    n = 0
    for page in pages:
        if page.get("include", True):
            n += 1
            page["pageNumber"] = n
            page["pageTotal"] = total
        else:
            page["pageNumber"] = None
            page["pageTotal"] = total


def ensure_project_shape(project: dict[str, Any]) -> dict[str, Any]:
    base = default_project(project.get("id"))
    merged = deepcopy(base)
    merged.update({k: v for k, v in project.items() if k in merged})

    if isinstance(project.get("metadata"), dict):
        merged["metadata"].update(project["metadata"])

    for key in ("sources", "worksheets", "pages", "templates", "assets", "revisionLog", "revisionHistory"):
        if isinstance(project.get(key), list):
            merged[key] = project[key]
    # Preserve string identity fields set by the project store / rename flow.
    for key in (
        "projectDisplayName",
        "projectFolder",
        "projectRoot",
        "linkedProjectRoot",
        "projectFilesMode",
    ):
        if isinstance(project.get(key), str) and project[key]:
            merged[key] = project[key]
    if "paginationLocked" in project:
        merged["paginationLocked"] = bool(project["paginationLocked"])
    if "workbookSync" in project and isinstance(project["workbookSync"], dict):
        merged["workbookSync"] = project["workbookSync"]

    merged = sanitize_json(merged)
    merged["modified"] = utcnow_iso()
    recalc_page_numbers(merged)
    return merged
