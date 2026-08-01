"""Standalone Singh360 drawing-set construction and migration helpers.

This module deliberately has no filesystem or workbook dependencies.  Every
public operation takes a project mapping, works on a deep copy, and returns the
updated project.  Runtime routes and migration tooling can therefore use the
same deterministic rules without creating a second persistence system.

The app-managed Cover and Sheet Index are project pages, but they are not
workbook rows.  Their identities are stable, their positions are normalized,
and Sheet Index continuation pages are derived solely from the current project
page manifest.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
import re
from typing import Any, Mapping
from uuid import uuid4

from core.project_model import PROJECT_SCHEMA_VERSION, default_template, recalc_page_numbers, sanitize_json


STANDALONE_PROJECT_MODE = "standalone_layout"
DEFAULT_INDEX_ROWS_PER_PAGE = 46
MIN_INDEX_ROWS_PER_PAGE = 2
MAX_INDEX_ROWS_PER_PAGE = 250

_ACTIVE_WORKBOOK_FIELDS = (
    "sourceWorkbookName",
    "sourceWorkbookPath",
    "workbookPath",
    "workbookHash",
    "baselineWorkbookHash",
    "sourceWorkbookHash",
    "lastWorkbookHash",
    "workbookImportedAt",
)
_ACTIVE_ROOT_FIELDS = (
    "projectRoot",
    "linkedProjectRoot",
    "EXACT_LINKED_PROJECT_ROOT",
)
_METADATA_WORKBOOK_FIELDS = (
    "sourceFile",
    "sourceWorkbookName",
    "sourceWorkbookPath",
    "workbookPath",
    "workbookHash",
    "baselineWorkbookHash",
    "sourceWorkbookHash",
    "lastWorkbookHash",
)


def _now(value: str | None = None) -> str:
    if value is not None:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("now must be a non-empty ISO-8601 timestamp when supplied")
        return cleaned
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug_token(value: Any) -> str:
    token = re.sub(r"[^A-Za-z0-9_-]+", "_", _text(value)).strip("_")
    return token or "project"


def _ordered_pages(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("project pages must be a list")
    if any(not isinstance(page, Mapping) for page in value):
        raise ValueError("every project page must be an object")
    pages = [deepcopy(dict(page)) for page in value]
    decorated = list(enumerate(pages))

    def key(item: tuple[int, dict[str, Any]]) -> tuple[float, int]:
        original_index, page = item
        raw = page.get("order")
        try:
            order = float(raw)
        except (TypeError, ValueError):
            order = float(original_index + 1)
        return order, original_index

    return [page for _, page in sorted(decorated, key=key)]


def _is_cover(page: Mapping[str, Any]) -> bool:
    return (
        _text(page.get("pageType")).casefold() == "cover"
        or _text(page.get("managedPage")).casefold() == "cover"
    )


def _is_index(page: Mapping[str, Any]) -> bool:
    page_type = re.sub(r"[^a-z0-9]+", "", _text(page.get("pageType")).casefold())
    return (
        page_type in {"index", "sheetindex"}
        or _text(page.get("managedPage")).casefold() == "index"
    )


def _is_generated_index_continuation(page: Mapping[str, Any]) -> bool:
    return bool(
        page.get("generatedIndexContinuation")
        or page.get("indexContinuation")
        or (
            page.get("generatedContinuation")
            and (page.get("continuationOf") or page.get("pageGroupId"))
            and _is_index(page)
        )
    )


def _managed_page_id(project_id: str, role: str) -> str:
    return f"{_slug_token(project_id)}__managed_{role}"


def _available_page_id(preferred: str, pages: list[Mapping[str, Any]]) -> str:
    used = {_text(page.get("id")) for page in pages if _text(page.get("id"))}
    if preferred not in used:
        return preferred
    discriminator = 2
    while f"{preferred}_{discriminator}" in used:
        discriminator += 1
    return f"{preferred}_{discriminator}"


def _validate_page_identities(
    active_pages: list[Mapping[str, Any]],
    archived_pages: list[Mapping[str, Any]],
) -> None:
    identities: list[str] = []
    for page in [*active_pages, *archived_pages]:
        identity = _text(page.get("id"))
        if not identity:
            raise ValueError("every existing project page must have a stable id")
        identities.append(identity)
    duplicates = sorted({identity for identity in identities if identities.count(identity) > 1})
    if duplicates:
        raise ValueError(f"project page ids are not unique: {duplicates}")


def _cover_page(project_id: str, created_at: str) -> dict[str, Any]:
    page_id = _managed_page_id(project_id, "cover")
    return {
        "id": page_id,
        "order": 1,
        "include": True,
        "sheetCode": "EMS 1.0",
        "displaySheetCode": "EMS 1.0",
        "sheetTitle": "Cover / Project Info",
        "sheetTab": "Cover",
        "pageType": "cover",
        "pageFamily": "cover",
        "renderMode": "generated_cover",
        "templateId": "ansi-b-standard",
        "blocks": [
            {
                "id": f"{page_id}__content",
                "type": "cover",
                "text": "",
                "rows": [],
            }
        ],
        "canvasObjects": [],
        "notes": "",
        "managedPage": "cover",
        "appManaged": True,
        "createdAt": created_at,
        "modifiedAt": created_at,
    }


def _index_page(project_id: str, created_at: str) -> dict[str, Any]:
    page_id = _managed_page_id(project_id, "sheet_index")
    return {
        "id": page_id,
        "order": 2,
        "include": True,
        "sheetCode": "EMS 2.0",
        "displaySheetCode": "EMS 2.0",
        "sheetTitle": "Sheet Index / TOC",
        "sheetTab": "Sheet Index",
        "pageType": "index",
        "pageFamily": "index",
        "renderMode": "generated_index",
        "normalizedHeaderStyle": "orange",
        "templateId": "ansi-b-standard",
        "blocks": [],
        "canvasObjects": [],
        "notes": "Generated automatically from the current included drawing set.",
        "managedPage": "index",
        "appManaged": True,
        "createdAt": created_at,
        "modifiedAt": created_at,
    }


def _blank_layout_page(project_id: str, created_at: str) -> dict[str, Any]:
    page_id = f"{_slug_token(project_id)}__layout_001"
    return {
        "id": page_id,
        "order": 3,
        "include": True,
        "sheetCode": "",
        "displaySheetCode": "",
        "sheetTitle": "Untitled Drawing",
        "sheetTab": "Untitled Drawing",
        "pageType": "canvas",
        "pageFamily": "drawing",
        "renderMode": "canvas",
        "templateId": "ansi-b-standard",
        "blocks": [],
        "canvasObjects": [],
        "notes": "",
        "createdAt": created_at,
        "modifiedAt": created_at,
    }


def _clean_metadata(metadata: Mapping[str, Any] | None, created_at: str) -> dict[str, Any]:
    supplied = dict(metadata or {})
    created_by = _text(supplied.get("createdBy") or supplied.get("preparedBy"))
    result: dict[str, Any] = {
        "projectName": "",
        "storeNumber": "",
        "client": "",
        "location": "",
        "address": "",
        "createdBy": created_by,
        "createdDate": _text(supplied.get("createdDate")),
        "sourceFile": "",
        "version": "",
        "templateVersion": "",
        "revision": "",
        "status": "Draft",
        "purpose": "",
        "projectType": "",
        "drawingSetTitle": "",
        "preparedBy": _text(supplied.get("preparedBy")),
        "checkedBy": "",
        "notes": "",
        "drawingPackageFileName": "",
        "customerLogoAsset": "",
    }
    result.update(deepcopy(supplied))
    return sanitize_json(result)


def _profile_pages(project_id: str, profile: str, created_at: str) -> list[dict[str, Any]]:
    normalized_profile = _text(profile).casefold()
    if normalized_profile not in {"minimal", "full"}:
        raise ValueError("profile must be 'minimal' or 'full'")
    pages = [_cover_page(project_id, created_at), _index_page(project_id, created_at)]
    if normalized_profile == "full":
        pages.append(_blank_layout_page(project_id, created_at))
    return pages


def create_standalone_project(
    project_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    *,
    profile: str = "full",
    now: str | None = None,
    rows_per_index_page: int = DEFAULT_INDEX_ROWS_PER_PAGE,
) -> dict[str, Any]:
    """Create a blank standalone drawing set.

    ``minimal`` contains only managed Cover and Sheet Index pages. ``full``
    additionally contains one empty drawing page. Supplying ``project_id`` and
    ``now`` makes the complete result deterministic, which is useful for
    templates, migrations, and sanitized tests.
    """

    created_at = _now(now)
    identity = _text(project_id) or uuid4().hex[:16]
    if not identity:
        raise ValueError("project_id must not be blank")
    rows = _validate_rows_per_page(rows_per_index_page)
    clean_metadata = _clean_metadata(metadata, created_at)
    display_name = _text(clean_metadata.get("projectName")) or identity
    project: dict[str, Any] = {
        "id": identity,
        "schemaVersion": PROJECT_SCHEMA_VERSION,
        "projectMode": STANDALONE_PROJECT_MODE,
        "managedPagePolicy": "automatic",
        "metadata": clean_metadata,
        "sources": [],
        "worksheets": [],
        "pages": _profile_pages(identity, profile, created_at),
        "templates": [default_template()],
        "assets": [],
        "revisionLog": [],
        "revisionHistory": [],
        "savedAssemblies": [],
        "projectDisplayName": display_name,
        "projectProfile": "ems",
        "projectFolder": "",
        "projectRoot": "",
        "linkedProjectRoot": "",
        "projectFilesMode": "project_package",
        "sourceWorkbookName": "",
        "created": created_at,
        "modified": created_at,
        "importWarnings": [],
        "archivedPages": [],
        "archived": False,
        "archivedAt": "",
        "archivedReason": "",
        "legacyWorkbookReference": {},
        "coverSettings": {"managed": True, "include": True},
        "indexSettings": {"managed": True, "rowsPerPage": rows},
        "workbookSync": {
            "mode": "disabled",
            "status": "disabled",
            "enabled": False,
            "warning": "",
            "pendingReason": "",
        },
        "dataWorkspace": {},
    }
    return normalize_standalone_project(project, now=created_at, rows_per_index_page=rows)


def _validate_rows_per_page(value: Any) -> int:
    try:
        rows = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("rows_per_index_page must be an integer") from exc
    if not MIN_INDEX_ROWS_PER_PAGE <= rows <= MAX_INDEX_ROWS_PER_PAGE:
        raise ValueError(
            f"rows_per_index_page must be between {MIN_INDEX_ROWS_PER_PAGE} and {MAX_INDEX_ROWS_PER_PAGE}"
        )
    return rows


def _next_index_code(base_code: str, ordinal: int, used: set[str]) -> str:
    """Return a deterministic, collision-free alphabetic continuation code."""

    def letters(number: int) -> str:
        result = ""
        while number > 0:
            number, remainder = divmod(number - 1, 26)
            result = chr(ord("a") + remainder) + result
        return result

    base = _text(base_code) or "EMS 2.0"
    candidate_ordinal = max(1, ordinal)
    while True:
        candidate = f"{base}{letters(candidate_ordinal)}"
        key = candidate.casefold()
        if key not in used:
            used.add(key)
            return candidate
        candidate_ordinal += 1


def _required_index_page_count(base_included_count: int, rows_per_page: int) -> int:
    count = 1
    for _ in range(100):
        physical_page_count = base_included_count + count - 1
        required = max(1, math.ceil(physical_page_count / rows_per_page))
        if required == count:
            return count
        count = required
    raise ValueError("Sheet Index page count did not converge")


def _normalize_managed_pages(
    project: dict[str, Any],
    *,
    timestamp: str,
    rows_per_page: int,
) -> None:
    project_id = _text(project.get("id"))
    pages = _ordered_pages(project.get("pages"))
    if not project_id:
        raise ValueError("project must have a non-empty id")
    archived_pages_raw = project.get("archivedPages") or []
    if not isinstance(archived_pages_raw, list) or any(
        not isinstance(page, Mapping) for page in archived_pages_raw
    ):
        raise ValueError("archivedPages must be a list of page objects")
    archived_pages = [deepcopy(dict(page)) for page in archived_pages_raw]
    _validate_page_identities(pages, archived_pages)

    covers = [page for page in pages if _is_cover(page) and not _is_generated_index_continuation(page)]
    indexes = [page for page in pages if _is_index(page) and not _is_generated_index_continuation(page)]
    if len(covers) > 1:
        raise ValueError("project has more than one Cover candidate; normalization would be ambiguous")
    if len(indexes) > 1:
        raise ValueError("project has more than one base Sheet Index candidate; normalization would be ambiguous")
    base_cover = covers[0] if covers else None
    base_index = indexes[0] if indexes else None
    if base_cover is None:
        base_cover = _cover_page(project_id, timestamp)
        available = _available_page_id(_text(base_cover["id"]), [*pages, *archived_pages])
        if available != base_cover["id"]:
            base_cover["id"] = available
            base_cover["blocks"][0]["id"] = f"{available}__content"
    if base_index is None:
        base_index = _index_page(project_id, timestamp)
        base_index["id"] = _available_page_id(
            _text(base_index["id"]), [*pages, base_cover, *archived_pages]
        )

    existing_continuations = [page for page in pages if _is_generated_index_continuation(page)]
    reserved_object_ids = {id(base_cover), id(base_index), *(id(page) for page in existing_continuations)}
    remaining = [page for page in pages if id(page) not in reserved_object_ids]

    # Preserve the selected existing page identities and content. Only fields
    # that make the two pages app-managed and workbook-independent are changed.
    if not _text(base_cover.get("id")):
        base_cover["id"] = _available_page_id(_managed_page_id(project_id, "cover"), pages)
    base_cover["pageType"] = "cover"
    base_cover["pageFamily"] = _text(base_cover.get("pageFamily")) or "cover"
    base_cover["managedPage"] = "cover"
    base_cover["appManaged"] = True
    base_cover["include"] = bool((project.get("coverSettings") or {}).get("include", True))
    base_cover["sheetCode"] = _text(base_cover.get("sheetCode") or base_cover.get("displaySheetCode")) or "EMS 1.0"
    base_cover["displaySheetCode"] = _text(base_cover.get("displaySheetCode") or base_cover.get("sheetCode"))
    base_cover["sheetTitle"] = _text(base_cover.get("sheetTitle")) or "Cover / Project Info"
    base_cover["sheetTab"] = _text(base_cover.get("sheetTab")) or "Cover"
    base_cover["templateId"] = _text(base_cover.get("templateId")) or "ansi-b-standard"
    blocks = base_cover.get("blocks")
    if not isinstance(blocks, list) or not any(
        isinstance(block, Mapping) and block.get("type") == "cover" for block in blocks
    ):
        preserved_blocks = deepcopy(blocks) if isinstance(blocks, list) else []
        preserved_blocks.insert(
            0,
            {
                "id": f"{base_cover['id']}__managed_cover_content",
                "type": "cover",
                "text": "",
                "rows": [],
            },
        )
        base_cover["blocks"] = preserved_blocks
    base_cover.setdefault("canvasObjects", [])
    base_cover.setdefault("notes", "")

    if not _text(base_index.get("id")):
        base_index["id"] = _available_page_id(
            _managed_page_id(project_id, "sheet_index"), [*pages, base_cover]
        )
    base_index["pageType"] = "index"
    base_index["pageFamily"] = "index"
    base_index["managedPage"] = "index"
    base_index["appManaged"] = True
    base_index["include"] = True
    base_index["renderMode"] = "generated_index"
    base_index["normalizedHeaderStyle"] = "orange"
    base_index["sheetCode"] = _text(base_index.get("sheetCode") or base_index.get("displaySheetCode")) or "EMS 2.0"
    base_index["displaySheetCode"] = _text(base_index.get("displaySheetCode") or base_index.get("sheetCode"))
    base_index["sheetTitle"] = re.sub(
        r"\s*[—-]\s*CONTINUED\s*$", "", _text(base_index.get("sheetTitle")), flags=re.IGNORECASE
    ) or "Sheet Index / TOC"
    base_index["sheetTab"] = _text(base_index.get("sheetTab")) or "Sheet Index"
    base_index["templateId"] = _text(base_index.get("templateId")) or "ansi-b-standard"
    base_index.setdefault("blocks", [])
    base_index.setdefault("canvasObjects", [])
    base_index.setdefault("notes", "Generated automatically from the current included drawing set.")
    # These source selectors may remain as read-only provenance, but generated
    # rendering and pagination never inspect them.
    base_index["standaloneIndex"] = True

    base_included_count = sum(
        1 for page in [base_cover, base_index, *remaining] if page.get("include", True)
    )
    required_count = _required_index_page_count(base_included_count, rows_per_page)
    used_codes = {
        _text(page.get("displaySheetCode") or page.get("sheetCode")).casefold()
        for page in [base_cover, base_index, *remaining]
        if _text(page.get("displaySheetCode") or page.get("sheetCode"))
    }
    used_ids = {
        _text(page.get("id"))
        for page in [base_cover, base_index, *remaining, *archived_pages]
        if _text(page.get("id"))
    }
    archived_continuations = {
        int(page.get("continuationIndex") or 0): page
        for page in archived_pages
        if _is_generated_index_continuation(page)
        and _text(page.get("continuationOf") or page.get("pageGroupId")) == _text(base_index.get("id"))
    }
    continuations: list[dict[str, Any]] = []
    base_index_id = _text(base_index.get("id"))
    base_code = _text(base_index.get("displaySheetCode") or base_index.get("sheetCode")) or "EMS 2.0"
    for ordinal in range(1, required_count):
        revived = False
        if ordinal <= len(existing_continuations):
            page = deepcopy(existing_continuations[ordinal - 1])
        elif ordinal in archived_continuations:
            archived_candidate = archived_continuations[ordinal]
            page = deepcopy(archived_candidate)
            archived_pages = [candidate for candidate in archived_pages if candidate is not archived_candidate]
            used_ids.discard(_text(page.get("id")))
            revived = True
        else:
            page = {}
        page_id = _text(page.get("id"))
        if not page_id or page_id in used_ids:
            page_id = f"{base_index_id}__index_cont_{ordinal}"
            discriminator = 2
            while page_id in used_ids:
                page_id = f"{base_index_id}__index_cont_{ordinal}_{discriminator}"
                discriminator += 1
        used_ids.add(page_id)
        existing_code = _text(page.get("displaySheetCode") or page.get("sheetCode"))
        code = existing_code if existing_code and existing_code.casefold() not in used_codes else _next_index_code(
            base_code, ordinal, used_codes
        )
        used_codes.add(code.casefold())
        page.update(
            {
                "id": page_id,
                "include": True,
                "sheetCode": code,
                "displaySheetCode": code,
                "sheetTitle": f"{base_index['sheetTitle']} — CONTINUED",
                "sheetTab": base_index["sheetTab"],
                "pageType": "index",
                "pageFamily": "index",
                "renderMode": "generated_index",
                "normalizedHeaderStyle": "orange",
                "templateId": base_index["templateId"],
                "managedPage": "index",
                "appManaged": True,
                "standaloneIndex": True,
                "pageGroupId": base_index_id,
                "continuationOf": base_index_id,
                "continuationIndex": ordinal,
                "generatedContinuation": True,
                "indexContinuation": True,
                "generatedIndexContinuation": True,
            }
        )
        page.setdefault("blocks", [])
        page.setdefault("canvasObjects", [])
        page.setdefault("notes", "Generated automatically from the current included drawing set.")
        page.setdefault("createdAt", timestamp)
        if revived:
            page["lastArchivedAt"] = page.pop("archivedAt", "")
            page["lastArchivedReason"] = page.pop("archivedReason", "")
            page["lastArchivedFromIndex"] = page.pop("archivedFromIndex", 0)
            page["restoredAt"] = timestamp
        continuations.append(page)

    # Generated continuations are derived data, but a prior page (and any
    # unexpected overlays on it) remains recoverable if the required count
    # shrinks. Never silently discard the old stable page identity.
    archived_ids = {_text(page.get("id")) for page in archived_pages}
    for surplus in existing_continuations[len(continuations) :]:
        surplus_id = _text(surplus.get("id"))
        if surplus_id in archived_ids:
            continue
        retired = deepcopy(surplus)
        retired["include"] = False
        retired["archivedAt"] = timestamp
        retired["archivedReason"] = "App-managed Sheet Index continuation no longer required."
        retired["archivedFromIndex"] = int(retired.get("order") or 0) - 1
        archived_pages.append(retired)
        archived_ids.add(surplus_id)

    arranged = [base_cover, base_index, *continuations, *remaining]
    total_included = sum(1 for page in arranged if page.get("include", True))
    for index, page in enumerate(arranged, start=1):
        page["order"] = index
        if _is_index(page) and (
            page is base_index or _is_generated_index_continuation(page)
        ):
            continuation_index = int(page.get("continuationIndex") or 0)
            start = continuation_index * rows_per_page
            page["indexRowsPerPage"] = rows_per_page
            page["indexRowsOnPage"] = max(0, min(rows_per_page, total_included - start))
            page["indexPageCount"] = required_count
    project["pages"] = arranged
    project["archivedPages"] = archived_pages
    recalc_page_numbers(project)


def normalize_standalone_project(
    project: Mapping[str, Any],
    *,
    now: str | None = None,
    rows_per_index_page: int | None = None,
) -> dict[str, Any]:
    """Return a normalized standalone project without mutating ``project``.

    Existing Cover and base Sheet Index IDs are preserved. Missing managed
    pages receive deterministic IDs derived from the stable project ID.
    Generated index pagination depends only on included project pages.
    """

    if not isinstance(project, Mapping):
        raise ValueError("project must be a mapping")
    original = sanitize_json(deepcopy(dict(project)))
    identity = _text(original.get("id"))
    if not identity:
        raise ValueError("project must have a non-empty id")
    updated = deepcopy(original)
    timestamp = _now(now)
    settings = deepcopy(updated.get("indexSettings")) if isinstance(updated.get("indexSettings"), Mapping) else {}
    selected_rows = rows_per_index_page if rows_per_index_page is not None else settings.get(
        "rowsPerPage", DEFAULT_INDEX_ROWS_PER_PAGE
    )
    rows = _validate_rows_per_page(selected_rows)

    updated["schemaVersion"] = max(int(updated.get("schemaVersion") or 0), PROJECT_SCHEMA_VERSION)
    updated["projectMode"] = STANDALONE_PROJECT_MODE
    updated["managedPagePolicy"] = "automatic"
    updated.setdefault("metadata", {})
    updated.setdefault("sources", [])
    updated.setdefault("worksheets", [])
    updated.setdefault("templates", [default_template()])
    if not updated.get("templates"):
        updated["templates"] = [default_template()]
    updated.setdefault("assets", [])
    updated.setdefault("savedAssemblies", [])
    updated.setdefault("revisionLog", [])
    updated.setdefault("revisionHistory", [])
    updated.setdefault("archivedPages", [])
    updated.setdefault("legacyWorkbookReference", {})
    cover_settings = deepcopy(updated.get("coverSettings")) if isinstance(updated.get("coverSettings"), Mapping) else {}
    cover_settings["managed"] = True
    cover_settings.setdefault("include", True)
    updated["coverSettings"] = cover_settings
    settings["managed"] = True
    settings["rowsPerPage"] = rows
    updated["indexSettings"] = settings
    _normalize_managed_pages(updated, timestamp=timestamp, rows_per_page=rows)

    clean = sanitize_json(updated)
    comparable_before = deepcopy(original)
    comparable_after = deepcopy(clean)
    comparable_before.pop("modified", None)
    comparable_after.pop("modified", None)
    if comparable_before != comparable_after:
        clean["modified"] = timestamp
    elif "modified" in original:
        clean["modified"] = original["modified"]
    return clean


def _legacy_workbook_reference(project: Mapping[str, Any], timestamp: str) -> dict[str, Any]:
    existing = deepcopy(project.get("legacyWorkbookReference")) if isinstance(
        project.get("legacyWorkbookReference"), Mapping
    ) else {}
    captured: dict[str, Any] = {}
    sync = project.get("workbookSync")
    if isinstance(sync, Mapping):
        sync_copy = deepcopy(dict(sync))
        is_disabled_only = _text(sync_copy.get("mode")).casefold() == "disabled" and not any(
            _text(value) for key, value in sync_copy.items() if key not in {"mode", "status", "warning", "pendingReason", "enabled"}
        )
        if sync_copy and not is_disabled_only and "workbookSync" not in existing:
            captured["workbookSync"] = sync_copy
    for key in (*_ACTIVE_ROOT_FIELDS, "projectFilesMode", *_ACTIVE_WORKBOOK_FIELDS):
        value = project.get(key)
        if key == "projectFilesMode" and _text(value).casefold() in {
            "project_package",
            "standalone",
            "standalone_layout",
        }:
            continue
        if value not in (None, "", {}, []):
            captured[key] = deepcopy(value)
    metadata = project.get("metadata")
    if isinstance(metadata, Mapping):
        metadata_values = {
            key: deepcopy(metadata.get(key))
            for key in (*_ACTIVE_ROOT_FIELDS, *_METADATA_WORKBOOK_FIELDS)
            if metadata.get(key) not in (None, "", {}, [])
        }
        if metadata_values:
            existing_metadata = deepcopy(existing.get("metadata")) if isinstance(existing.get("metadata"), Mapping) else {}
            for key, value in metadata_values.items():
                existing_metadata.setdefault(key, value)
            captured["metadata"] = existing_metadata
        if _text(metadata.get("sourceFile")):
            # Flat compatibility key retained for prior migration reports.
            captured["metadataSourceFile"] = deepcopy(metadata.get("sourceFile"))
    if captured:
        for key, value in captured.items():
            if key == "metadata":
                existing[key] = value
            else:
                existing.setdefault(key, value)
        existing.setdefault("migratedAt", timestamp)
        existing.setdefault("readOnly", True)
    return existing


def _detach_workbook_authority(project: dict[str, Any], timestamp: str) -> None:
    project["legacyWorkbookReference"] = _legacy_workbook_reference(project, timestamp)
    project["workbookSync"] = {
        "mode": "disabled",
        "status": "disabled",
        "enabled": False,
        "warning": "",
        "pendingReason": "",
    }
    for key in _ACTIVE_ROOT_FIELDS:
        if key in project or key in {"projectRoot", "linkedProjectRoot"}:
            project[key] = ""
    project["projectFilesMode"] = "project_package"
    for key in _ACTIVE_WORKBOOK_FIELDS:
        if key in project:
            project[key] = ""
    metadata = project.get("metadata")
    if isinstance(metadata, dict):
        for key in (*_ACTIVE_ROOT_FIELDS, *_METADATA_WORKBOOK_FIELDS):
            if key in metadata:
                metadata[key] = ""


def migrate_project_to_standalone(
    project: Mapping[str, Any],
    *,
    now: str | None = None,
    canonical_display_name: str | None = None,
    archived: bool | None = None,
    archive_reason: str = "",
    normalize_managed_pages: bool = True,
) -> dict[str, Any]:
    """Detach a legacy project from workbook authority.

    ``normalize_managed_pages=False`` is the protected-project escape hatch for
    migrations such as SA31 where no page redesign or normalization is allowed.
    In that mode, the page list remains byte-for-byte equal to the input.
    """

    if not isinstance(project, Mapping):
        raise ValueError("project must be a mapping")
    # A detach-only protected migration is metadata surgery. Preserve these
    # already-JSON-compatible payloads exactly, including literal source text
    # such as "NaN" that the general project sanitizer would otherwise clean.
    raw_pages = deepcopy(dict(project).get("pages"))
    raw_archived_pages = deepcopy(dict(project).get("archivedPages"))
    original = sanitize_json(deepcopy(dict(project)))
    if not _text(original.get("id")):
        raise ValueError("project must have a non-empty id")
    timestamp = _now(now)
    updated = deepcopy(original)
    updated["schemaVersion"] = max(int(updated.get("schemaVersion") or 0), PROJECT_SCHEMA_VERSION)
    updated["projectMode"] = STANDALONE_PROJECT_MODE
    updated["managedPagePolicy"] = "automatic" if normalize_managed_pages else "preserve_existing"
    updated.setdefault("metadata", {})
    _detach_workbook_authority(updated, timestamp)
    if canonical_display_name is not None:
        display = _text(canonical_display_name)
        if not display:
            raise ValueError("canonical_display_name must not be blank")
        updated["projectDisplayName"] = display
    if normalize_managed_pages:
        updated = normalize_standalone_project(updated, now=timestamp)
    if archived is True:
        updated = archive_project(updated, reason=archive_reason, now=timestamp)
    elif archived is False and updated.get("archived"):
        updated = restore_project(updated, now=timestamp)
    else:
        updated.setdefault("archived", False)
        updated.setdefault("archivedAt", "")
        updated.setdefault("archivedReason", "")

    clean = sanitize_json(updated)
    if not normalize_managed_pages:
        if raw_pages is not None:
            clean["pages"] = raw_pages
        if raw_archived_pages is not None:
            clean["archivedPages"] = raw_archived_pages
    comparable_before = deepcopy(dict(project)) if not normalize_managed_pages else deepcopy(original)
    comparable_after = deepcopy(clean)
    comparable_before.pop("modified", None)
    comparable_after.pop("modified", None)
    if comparable_before != comparable_after:
        clean["modified"] = timestamp
    elif "modified" in original:
        clean["modified"] = original["modified"]
    return clean


def _page_matches(page: Mapping[str, Any], page_id: str) -> bool:
    return _text(page.get("id")) == page_id


def archive_page(
    project: Mapping[str, Any],
    page_id: str,
    *,
    reason: str = "",
    now: str | None = None,
    allow_managed: bool = False,
) -> dict[str, Any]:
    """Recoverably archive a page and any continuations owned by that page.

    A source/base page and its active ``continuationOf`` pages form one archive
    group.  A continuation selected directly remains an independent archive
    operation, so restoring its source later cannot unexpectedly revive it.
    """

    identity = _text(page_id)
    if not identity:
        raise ValueError("page_id must not be blank")
    timestamp = _now(now)
    updated = deepcopy(dict(project))
    pages = _ordered_pages(updated.get("pages"))
    matches = [index for index, page in enumerate(pages) if _page_matches(page, identity)]
    if not matches:
        if any(_page_matches(page, identity) for page in updated.get("archivedPages") or [] if isinstance(page, Mapping)):
            return normalize_standalone_project(updated, now=timestamp)
        raise KeyError(identity)
    if len(matches) != 1:
        raise ValueError(f"page id {identity!r} is not unique")
    position = matches[0]
    target = pages[position]
    if not allow_managed and (_is_cover(target) or _is_index(target) or target.get("appManaged")):
        raise ValueError("app-managed Cover and Sheet Index pages require an explicit advanced action")

    # Selecting a continuation is deliberately a one-page operation.  Only a
    # source/base page owns the active pages that point to its stable ID.
    group_positions = [position]
    if not _text(target.get("continuationOf")):
        group_positions.extend(
            index
            for index, page in enumerate(pages)
            if index != position and _text(page.get("continuationOf")) == identity
        )
    group_positions = sorted(set(group_positions))
    group_ids = {_text(pages[index].get("id")) for index in group_positions}
    archive_reason = _text(reason) or "Archived by user"
    archived_group: list[dict[str, Any]] = []
    for group_position in group_positions:
        page = pages[group_position]
        page["archivedAt"] = timestamp
        page["archivedReason"] = archive_reason
        page["archivedFromIndex"] = group_position
        page["archivedPreviousPageId"] = (
            _text(pages[group_position - 1].get("id")) if group_position > 0 else ""
        )
        page["archivedNextPageId"] = (
            _text(pages[group_position + 1].get("id"))
            if group_position + 1 < len(pages)
            else ""
        )
        page["archivedInclude"] = bool(page.get("include", True))
        page["archivedGroupRootId"] = identity
        page["include"] = False
        archived_group.append(page)

    archived_pages = [
        deepcopy(candidate)
        for candidate in updated.get("archivedPages") or []
        if isinstance(candidate, Mapping) and _text(candidate.get("id")) not in group_ids
    ]
    archived_pages.extend(archived_group)
    updated["archivedPages"] = archived_pages
    updated["pages"] = [
        page for index, page in enumerate(pages) if index not in set(group_positions)
    ]
    return normalize_standalone_project(updated, now=timestamp)


def restore_page(
    project: Mapping[str, Any],
    page_id: str,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Restore an archived page (and its archived continuation group)."""

    identity = _text(page_id)
    if not identity:
        raise ValueError("page_id must not be blank")
    timestamp = _now(now)
    updated = deepcopy(dict(project))
    archived = [deepcopy(page) for page in updated.get("archivedPages") or [] if isinstance(page, Mapping)]
    matches = [index for index, page in enumerate(archived) if _page_matches(page, identity)]
    if not matches:
        if any(_page_matches(page, identity) for page in updated.get("pages") or [] if isinstance(page, Mapping)):
            return normalize_standalone_project(updated, now=timestamp)
        raise KeyError(identity)
    if len(matches) != 1:
        raise ValueError(f"archived page id {identity!r} is not unique")
    matched_index = matches[0]
    target = archived[matched_index]
    target_is_continuation = bool(_text(target.get("continuationOf")))
    group_root = _text(target.get("archivedGroupRootId"))
    selected_indexes = [matched_index]
    if not target_is_continuation and group_root == identity:
        selected_indexes.extend(
            index
            for index, page in enumerate(archived)
            if index != matched_index
            and _text(page.get("archivedGroupRootId")) == identity
            and _text(page.get("continuationOf")) == identity
        )

    def archived_position(index: int) -> tuple[int, int]:
        try:
            position = int(archived[index].get("archivedFromIndex"))
        except (TypeError, ValueError):
            position = index
        return position, index

    selected_indexes = sorted(set(selected_indexes), key=archived_position)
    selected_set = set(selected_indexes)
    restoring = [archived[index] for index in selected_indexes]
    archived = [page for index, page in enumerate(archived) if index not in selected_set]
    pages = _ordered_pages(updated.get("pages"))
    active_ids = {_text(page.get("id")) for page in pages}
    restoring_ids = [_text(page.get("id")) for page in restoring]
    duplicate_ids = sorted({page_id for page_id in restoring_ids if page_id in active_ids})
    if duplicate_ids:
        raise ValueError(f"active page ids already exist: {duplicate_ids}")

    # Restore in original order.  Each page keeps its own two-sided neighbor
    # anchors, so even non-contiguous continuation layouts return to their
    # former positions while later unrelated insertions remain undisturbed.
    for restored in restoring:
        next_id = _text(restored.get("archivedNextPageId"))
        previous_id = _text(restored.get("archivedPreviousPageId"))
        insertion: int | None = next(
            (index for index, page in enumerate(pages) if next_id and _page_matches(page, next_id)), None
        )
        if insertion is None:
            previous_position = next(
                (index for index, page in enumerate(pages) if previous_id and _page_matches(page, previous_id)), None
            )
            if previous_position is not None:
                insertion = previous_position + 1
        if insertion is None:
            try:
                insertion = int(restored.get("archivedFromIndex"))
            except (TypeError, ValueError):
                insertion = len(pages)
            insertion = max(0, min(insertion, len(pages)))

        restored["include"] = bool(restored.pop("archivedInclude", True))
        restored["lastArchivedAt"] = restored.pop("archivedAt", "")
        restored["lastArchivedReason"] = restored.pop("archivedReason", "")
        restored["lastArchivedFromIndex"] = restored.pop("archivedFromIndex", insertion)
        restored["lastArchivedGroupRootId"] = restored.pop("archivedGroupRootId", identity)
        restored.pop("archivedPreviousPageId", None)
        restored.pop("archivedNextPageId", None)
        restored["restoredAt"] = timestamp
        pages.insert(insertion, restored)

    # ``normalize_standalone_project`` begins by ordering on the persisted
    # numeric field.  Re-sequence that field from the neighbor-resolved list so
    # old archived order values cannot collide with pages compacted while the
    # group was absent and undo the positions established above.
    for order, page in enumerate(pages, start=1):
        page["order"] = order

    updated["pages"] = pages
    updated["archivedPages"] = archived
    return normalize_standalone_project(updated, now=timestamp)


def archive_project(
    project: Mapping[str, Any],
    *,
    reason: str = "",
    now: str | None = None,
) -> dict[str, Any]:
    """Mark a project archived without moving or deleting its package."""

    timestamp = _now(now)
    updated = deepcopy(dict(project))
    if updated.get("archived"):
        return updated
    updated["archived"] = True
    updated["archivedAt"] = timestamp
    updated["archivedReason"] = _text(reason) or "Archived by user"
    updated["modified"] = timestamp
    return updated


def restore_project(
    project: Mapping[str, Any],
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Restore a metadata-archived project without moving its package."""

    timestamp = _now(now)
    updated = deepcopy(dict(project))
    if not updated.get("archived"):
        return updated
    updated["lastArchivedAt"] = _text(updated.get("archivedAt"))
    updated["lastArchivedReason"] = _text(updated.get("archivedReason"))
    updated["archived"] = False
    updated["archivedAt"] = ""
    updated["archivedReason"] = ""
    updated["restoredAt"] = timestamp
    updated["modified"] = timestamp
    return updated


__all__ = [
    "DEFAULT_INDEX_ROWS_PER_PAGE",
    "STANDALONE_PROJECT_MODE",
    "archive_page",
    "archive_project",
    "create_standalone_project",
    "migrate_project_to_standalone",
    "normalize_standalone_project",
    "restore_page",
    "restore_project",
]
