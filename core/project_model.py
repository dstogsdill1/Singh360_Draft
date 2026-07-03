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
        return "" if txt.lower() in {"nan", "nat", "<na>", "none", "undefined"} else value
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
            "status": "Draft",
        },
        "sources": [],
        "worksheets": [],
        "pages": [],
        "templates": [default_template()],
        "assets": [],
        "revisionLog": [],
        "revisionHistory": [],
        "projectDisplayName": "",
        "projectFolder": "",
        "modified": created,
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
    for key in ("projectDisplayName", "projectFolder"):
        if isinstance(project.get(key), str) and project[key]:
            merged[key] = project[key]

    merged = sanitize_json(merged)
    merged["modified"] = utcnow_iso()
    recalc_page_numbers(merged)
    return merged
