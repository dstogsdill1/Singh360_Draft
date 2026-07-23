from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


PROJECT_SCHEMA_VERSION = 1
_WORKBOOK_TEMP_NAME_RE = re.compile(
    r"^(?:temp|preview)_[a-f0-9]{16}\.(?:xlsx|xlsm)$", re.IGNORECASE
)
_WORKBOOK_SUFFIXES = {".xlsx", ".xlsm"}


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
        "projectFolder": "",
        "projectSlug": "",
        "sourceWorkbookName": "",
        "lastSavedAt": "",
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


def _is_real_workbook_name(value: Any) -> bool:
    name = Path(str(value or "").strip()).name
    return bool(
        name
        and Path(name).suffix.lower() in _WORKBOOK_SUFFIXES
        and not _WORKBOOK_TEMP_NAME_RE.fullmatch(name)
    )


def _newest_source_workbook(project: dict[str, Any]) -> Path | None:
    """Find the newest real workbook already stored inside this project package."""
    folder = str(project.get("projectFolder") or "").strip()
    if not folder:
        return None
    source_dir = Path(folder) / "sources" / "workbook"
    try:
        candidates = [
            path
            for path in source_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in _WORKBOOK_SUFFIXES
            and not _WORKBOOK_TEMP_NAME_RE.fullmatch(path.name)
        ]
    except OSError:
        return None
    if not candidates:
        return None

    def modified_key(path: Path) -> tuple[float, str]:
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        return modified, path.name.lower()

    return max(candidates, key=modified_key)


def _workbook_identity(project: dict[str, Any]) -> tuple[str, str]:
    """Return the best supported workbook filename and project-local path."""
    top_name = str(project.get("sourceWorkbookName") or "").strip()
    if _is_real_workbook_name(top_name):
        folder = str(project.get("projectFolder") or "").strip()
        if folder:
            matching = Path(folder) / "sources" / "workbook" / Path(top_name).name
            if matching.is_file():
                return matching.name, str(matching)
        return Path(top_name).name, ""

    sources = project.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict) or str(source.get("type") or "").lower() != "workbook":
                continue
            source_name = str(source.get("name") or "").strip()
            if _is_real_workbook_name(source_name):
                return Path(source_name).name, str(source.get("path") or "").strip()

    stored_copy = _newest_source_workbook(project)
    if stored_copy is not None:
        return stored_copy.name, str(stored_copy)

    metadata = project.get("metadata")
    if isinstance(metadata, dict):
        source_file = str(metadata.get("sourceFile") or "").strip()
        if _is_real_workbook_name(source_file):
            return Path(source_file).name, ""

    return "", ""


def _restore_original_workbook_identity(project: dict[str, Any]) -> None:
    """Repair parser temp names without rebuilding pages or touching manual work.

    Fresh ingest records the user-selected filename before project shaping. Older
    broken projects may have lost that field, but their untouched workbook copy
    remains under ``<projectFolder>/sources/workbook``. The newest real workbook
    in that folder is used only to repair identity/path metadata.
    """
    original_name, source_path = _workbook_identity(project)
    if not original_name:
        return

    project["sourceWorkbookName"] = original_name
    metadata = project.get("metadata")
    if isinstance(metadata, dict):
        source_file = str(metadata.get("sourceFile") or "").strip()
        if not _is_real_workbook_name(source_file):
            metadata["sourceFile"] = original_name

    sources = project.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict) or str(source.get("type") or "").lower() != "workbook":
                continue
            source_name = str(source.get("name") or "").strip()
            if not _is_real_workbook_name(source_name):
                source["name"] = original_name
            if source_path:
                recorded_path = str(source.get("path") or "").strip()
                if not recorded_path or _WORKBOOK_TEMP_NAME_RE.fullmatch(Path(recorded_path).name):
                    source["path"] = source_path


def ensure_project_shape(project: dict[str, Any]) -> dict[str, Any]:
    base = default_project(project.get("id"))
    merged = deepcopy(base)
    merged.update({k: v for k, v in project.items() if k in merged})

    if isinstance(project.get("metadata"), dict):
        merged["metadata"].update(project["metadata"])

    for key in ("sources", "worksheets", "pages", "templates", "assets", "revisionLog", "revisionHistory"):
        if isinstance(project.get(key), list):
            merged[key] = project[key]
    # Preserve identity fields set by ingest, the project store, and rename flow.
    for key in (
        "projectDisplayName",
        "projectFolder",
        "projectSlug",
        "sourceWorkbookName",
        "lastSavedAt",
    ):
        if isinstance(project.get(key), str) and project[key]:
            merged[key] = project[key]
    if "paginationLocked" in project:
        merged["paginationLocked"] = bool(project["paginationLocked"])
    if "workbookSync" in project and isinstance(project["workbookSync"], dict):
        merged["workbookSync"] = project["workbookSync"]

    _restore_original_workbook_identity(merged)
    merged = sanitize_json(merged)
    merged["modified"] = utcnow_iso()
    recalc_page_numbers(merged)
    return merged
