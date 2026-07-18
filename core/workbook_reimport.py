"""core/workbook_reimport.py — PHASE E: safe whole-workbook re-upload into an
existing project.

Today, uploading a workbook always builds a brand-new project
(``core.workbook_importer.import_workbook`` always starts from
``default_project()``) — there is no way to refresh table/source pages in an
*existing* project without risking the loss of hand-built manual layout
pages (Overall Layout, wiring schematics, device location plans, etc.).

This module adds a preview/apply pair that:
  1. Runs a normal ``import_workbook`` on the new file to get a *candidate*
     project (never mutates the existing one just to preview it).
  2. Matches candidate pages to existing pages by stable sheet code first,
     then normalized sheet title (never by raw physical order — order is
     not stable across a re-export of the same workbook).
  3. Classifies each matched existing page as "manual" (canvas/underlay/
     hybrid, or carrying canvas objects / image / connector blocks) or
     "source" (table/schedule content).
  4. Rebuilds "source" pages in place (same page id, canvas objects/notes
     carried forward) and leaves "manual" pages completely untouched unless
     the caller explicitly opts a page id into ``replace_page_ids``.
  5. Never deletes anything: unmatched existing pages are moved to
     ``project["archivedPages"]`` (``include: False``) instead of being
     dropped, and unmatched candidate pages are appended as new pages.

No network/API calls here — this module is directly unit-testable, exactly
like ``core/sheet_importer.py`` and ``core/workbook_importer.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.project_model import sanitize_json
from core.workbook_importer import import_workbook

# Page types that always mean "hand-built layout, never silently rebuild".
_MANUAL_PAGE_TYPES = {"canvas", "underlay", "hybrid"}

# Fields copied from the freshly-imported candidate page onto a "source"
# page being rebuilt in place. Deliberately excludes identity/position
# fields (id, order, pageGroupId, continuation*) and anything manual
# (canvasObjects, notes, revisionRows) so those always carry over from the
# existing page unless the page is an explicit manual "Replace Page".
_REBUILD_FIELDS = (
    "sheetTitle",
    "sheetTab",
    "sheetCode",
    "displaySheetCode",
    "pageType",
    "pageFamily",
    "blankPagePlaceholder",
    "layoutProfile",
    "twoUp",
    "renderMode",
    "renderProfile",
    "normalizedHeaderStyle",
    "sourceSheet",
    "sourceRange",
    "printArea",
    "splitMode",
    "repeatRows",
    "minScale",
    "allowContinuation",
    "scaleMode",
    "trimBlankRows",
    "trimBlankColumns",
    "linkedWorksheetId",
    "blocks",
    "layoutWarnings",
)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_manual_page(page: dict[str, Any]) -> bool:
    """True when a page carries hand-built layout work that must not be
    silently rebuilt from a workbook (Phase E rule 2/4).

    Manual layout page types: Image / Layout, reference/underlay, canvas,
    hybrid sheets with canvas objects, or any page with inserted
    components/images/connectors."""
    if page.get("pageType") in _MANUAL_PAGE_TYPES:
        return True
    if page.get("canvasObjects"):
        return True
    for b in page.get("blocks") or []:
        if b.get("type") in ("imagePlaceholder", "underlayPlaceholder", "canvas"):
            return True
    return False


def _match_key_code(page: dict[str, Any]) -> str:
    code = (page.get("displaySheetCode") or page.get("sheetCode") or "").strip().lower()
    return code if code and code not in ("new", "tbd") else ""


def _match_key_title(page: dict[str, Any]) -> str:
    return " ".join((page.get("sheetTitle") or "").strip().lower().split())


def _classify(page: dict[str, Any]) -> str:
    return "manual" if is_manual_page(page) else "source"


def plan_reimport(existing_project: dict[str, Any], new_workbook_path: str | Path) -> dict[str, Any]:
    """Build a reimport plan without mutating ``existing_project``.

    Returns ``{toUpdate, toPreserve, toAdd, toArchive, candidateWorksheetCount}``
    so a frontend preflight dialog can show, per page: sheet code/title,
    classification (manual vs source), and whether it has canvas objects —
    with "preserve" as the default outcome for every manual page.
    """
    candidate = import_workbook(new_workbook_path, project_id="__reimport_preview__")
    existing_pages = existing_project.get("pages", [])
    candidate_pages = candidate.get("pages", [])

    by_code: dict[str, dict[str, Any]] = {}
    by_title: dict[str, dict[str, Any]] = {}
    for p in existing_pages:
        code = _match_key_code(p)
        if code and code not in by_code:
            by_code[code] = p
        title = _match_key_title(p)
        if title and title not in by_title:
            by_title[title] = p

    matched_existing_ids: set[str] = set()
    to_update: list[dict[str, Any]] = []
    to_preserve: list[dict[str, Any]] = []
    to_add: list[dict[str, Any]] = []

    for cp in candidate_pages:
        code = _match_key_code(cp)
        title = _match_key_title(cp)
        existing = by_code.get(code) if code else None
        matched_by = "sheetCode" if existing is not None else None
        if existing is None and title:
            existing = by_title.get(title)
            matched_by = "sheetTitle" if existing is not None else None
        if existing is None or existing["id"] in matched_existing_ids:
            to_add.append(
                {
                    "candidatePageId": cp["id"],
                    "sheetCode": cp.get("displaySheetCode") or cp.get("sheetCode"),
                    "sheetTitle": cp.get("sheetTitle"),
                }
            )
            continue
        matched_existing_ids.add(existing["id"])
        entry = {
            "existingPageId": existing["id"],
            "candidatePageId": cp["id"],
            "sheetCode": existing.get("displaySheetCode") or existing.get("sheetCode"),
            "candidateSheetCode": cp.get("displaySheetCode") or cp.get("sheetCode"),
            "sheetTitle": existing.get("sheetTitle"),
            "matchedBy": matched_by,
            "classification": _classify(existing),
            "hasCanvasObjects": bool(existing.get("canvasObjects")),
        }
        if entry["classification"] == "manual":
            to_preserve.append(entry)
        else:
            to_update.append(entry)

    to_archive = [
        {
            "existingPageId": p["id"],
            "sheetCode": p.get("displaySheetCode") or p.get("sheetCode"),
            "sheetTitle": p.get("sheetTitle"),
            "classification": _classify(p),
        }
        for p in existing_pages
        if p["id"] not in matched_existing_ids
    ]

    return {
        "toUpdate": to_update,
        "toPreserve": to_preserve,
        "toAdd": to_add,
        "toArchive": to_archive,
        "candidateWorksheetCount": len(candidate.get("worksheets", [])),
    }


def apply_reimport(
    existing_project: dict[str, Any],
    new_workbook_path: str | Path,
    *,
    replace_page_ids: list[str] | None = None,
    source_filename: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply a Phase E safe reimport. Returns ``(updated_project, summary)``.

    ``replace_page_ids``: explicit opt-in list of existing page ids the user
    chose to fully replace even though they are classified "manual" — the
    default for every manual page is Preserve (rule 2/6).
    """
    replace_ids = set(replace_page_ids or [])
    plan = plan_reimport(existing_project, new_workbook_path)
    candidate = import_workbook(new_workbook_path, project_id="__reimport_apply__")
    candidate_pages_by_id = {p["id"]: p for p in candidate.get("pages", [])}

    pages = [dict(p) for p in existing_project.get("pages", [])]
    pages_by_id = {p["id"]: i for i, p in enumerate(pages)}

    updated_codes: list[str] = []
    preserved_codes: list[str] = []
    replaced_manual_codes: list[str] = []

    for entry in plan["toUpdate"] + plan["toPreserve"]:
        existing_id = entry["existingPageId"]
        cp = candidate_pages_by_id.get(entry["candidatePageId"])
        idx = pages_by_id.get(existing_id)
        if idx is None or cp is None:
            continue
        target = pages[idx]
        is_manual = entry["classification"] == "manual"

        if is_manual and existing_id not in replace_ids:
            # Preserve rule (default): leave the existing page completely
            # untouched — the user's manual layout work survives byte-for-byte.
            preserved_codes.append(entry["sheetCode"] or existing_id)
            continue

        # Rebuild table/source pages from the workbook (or an explicitly
        # replaced manual page) using the same in-place-merge style already
        # proven by sheet_importer.import_workbook_sheets(replace_page_id=...):
        # keep the existing page id/position, overwrite only the fields the
        # new import should own.
        merged = dict(target)
        for field in _REBUILD_FIELDS:
            if field in cp:
                merged[field] = cp[field]
        merged["importedFrom"] = {
            "sourceFile": source_filename or Path(new_workbook_path).name,
            "sheetName": cp.get("sheetTab", ""),
            "importedAt": _ts(),
            "reimport": True,
        }
        if is_manual and existing_id in replace_ids:
            # Explicit "Replace Page" opt-in — the new page's canvas content
            # (if any) replaces the old one too.
            merged["canvasObjects"] = cp.get("canvasObjects", [])
            replaced_manual_codes.append(entry["sheetCode"] or existing_id)
        else:
            updated_codes.append(entry["sheetCode"] or existing_id)
        pages[idx] = merged

    # Add unmatched candidate pages as new pages (never merged into an
    # existing one), appended after the existing pages.
    added_codes: list[str] = []
    for entry in plan["toAdd"]:
        cp = candidate_pages_by_id.get(entry["candidatePageId"])
        if cp is None:
            continue
        new_page = dict(cp)
        new_page["id"] = f"page_{uuid.uuid4().hex[:12]}"
        new_page["pageGroupId"] = new_page["id"]
        new_page["importedFrom"] = {
            "sourceFile": source_filename or Path(new_workbook_path).name,
            "sheetName": cp.get("sheetTab", ""),
            "importedAt": _ts(),
            "reimport": True,
        }
        pages.append(new_page)
        added_codes.append(entry["sheetCode"] or new_page["id"])

    # Archive unmatched existing pages instead of deleting them — never
    # destroy existing project work just because a sheet was renamed/removed
    # in the new workbook.
    archived_ids = {e["existingPageId"] for e in plan["toArchive"]}
    archived_codes: list[str] = []
    kept_pages: list[dict[str, Any]] = []
    archived_pages: list[dict[str, Any]] = [dict(p) for p in existing_project.get("archivedPages", [])]
    for p in pages:
        if p["id"] in archived_ids:
            archived_pages.append({**p, "include": False, "archivedAt": _ts()})
            archived_codes.append(p.get("displaySheetCode") or p.get("sheetCode") or p["id"])
        else:
            kept_pages.append(p)

    for i, p in enumerate(kept_pages):
        p["order"] = i + 1

    updated_project = dict(existing_project)
    updated_project["pages"] = kept_pages
    updated_project["archivedPages"] = archived_pages
    history_entry = {
        "sourceFile": source_filename or Path(new_workbook_path).name,
        "importedAt": _ts(),
        "mode": "reimport",
        "updated": updated_codes,
        "preserved": preserved_codes,
        "replacedManual": replaced_manual_codes,
        "added": added_codes,
        "archived": archived_codes,
    }
    updated_project["importHistory"] = list(existing_project.get("importHistory", [])) + [history_entry]

    summary = {
        "updated": updated_codes,
        "preserved": preserved_codes,
        "replacedManual": replaced_manual_codes,
        "added": added_codes,
        "archived": archived_codes,
    }
    return sanitize_json(updated_project), summary
