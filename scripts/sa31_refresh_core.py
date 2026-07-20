"""Core project merge for the complete SA31 workbook refresh."""
from __future__ import annotations

import copy
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROJECT_ID = "4acaef6006dd4620"
MANUAL_PRESERVE_CODES = {"ems 4.0", "ems 13.0"}
REQUIRED_BASE_CODES = (
    "EMS 1.0", "EMS 2.0", "EMS 3.0", "EMS 4.0", "EMS 5.0", "EMS 6.0",
    "EMS 7.0", "EMS 8.0", "EMS 8.1", "EMS 9.0", "EMS 10.0", "EMS 11.0",
    "EMS 12.0", "EMS 13.0", "EMS 14.0", "EMS 15.0", "EMS 15.1",
    "EMS 16.0", "EMS 16.1", "EMS 17.0", "EMS 18.0", "EMS 19.0",
    "EMS 20.0", "EMS 21.0", "EMS 22.0", "EMS 23.0", "EMS 24.0",
    "EMS 25.0",
)
IDENTITY_FIELDS = (
    "sheetCode", "displaySheetCode", "sheetTitle", "sheetTab", "pageType",
    "pageFamily", "layoutProfile", "renderMode", "renderProfile",
    "normalizedHeaderStyle", "sourceSheet", "sourceRange", "printArea",
    "splitMode", "repeatRows", "minScale", "allowContinuation", "scaleMode",
    "trimBlankRows", "trimBlankColumns", "orientation", "templateId",
    "linkedWorksheetId", "blankPagePlaceholder", "twoUp", "showTerminatedBy",
)
MANUAL_FIELDS = ("canvasObjects", "assets", "underlays", "notes", "revisionRows")


class MigrationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _page_code(page: dict[str, Any]) -> str:
    return str(page.get("displaySheetCode") or page.get("sheetCode") or "").strip()


def _page_tab(page: dict[str, Any]) -> str:
    return _norm(page.get("sheetTab") or page.get("sourceSheet") or "")


def _page_title(page: dict[str, Any]) -> str:
    return _norm(page.get("sheetTitle") or "")


def _page_text(page: dict[str, Any]) -> str:
    values: list[str] = []
    for block in page.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        values.append(str(block.get("text") or ""))
        for row in block.get("grid") or []:
            if isinstance(row, list):
                values.extend(str(cell or "") for cell in row)
        for row in block.get("rows") or []:
            if isinstance(row, list):
                values.extend(str(cell or "") for cell in row)
    return " ".join(values)


def _has_manual_content(page: dict[str, Any]) -> bool:
    if page.get("pageType") in {"canvas", "hybrid", "underlay"}:
        return True
    if page.get("canvasObjects"):
        return True
    for block in page.get("blocks") or []:
        if isinstance(block, dict) and block.get("type") in {
            "imagePlaceholder", "underlayPlaceholder", "canvas"
        }:
            return True
    return False


def _count_manual(page: dict[str, Any]) -> tuple[int, int, int]:
    canvas = page.get("canvasObjects") if isinstance(page.get("canvasObjects"), list) else []
    assets = page.get("assets") if isinstance(page.get("assets"), list) else []
    image_blocks = [
        block for block in (page.get("blocks") or [])
        if isinstance(block, dict) and block.get("type") in {
            "imagePlaceholder", "underlayPlaceholder", "canvas"
        }
    ]
    return len(canvas), len(assets), len(image_blocks)


def _candidate_page_by_code(candidate: dict[str, Any], code: str) -> dict[str, Any] | None:
    low = _norm(code)
    return next(
        (page for page in candidate.get("pages", []) if _norm(_page_code(page)) == low),
        None,
    )


def _worksheet_by_name(project: dict[str, Any], name: str) -> dict[str, Any]:
    low = _norm(name)
    worksheet = next(
        (ws for ws in project.get("worksheets", []) if _norm(ws.get("name")) == low),
        None,
    )
    if worksheet is None:
        raise MigrationError(f"Workbook worksheet not found: {name}")
    return worksheet


def _clone_page_metadata(base: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in base.items()
        if key not in {"blocks", "canvasObjects", "assets", "underlays", "notes", "revisionRows"}
    }


def _build_matrix_pages(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Split EMS 15.0 by controller while keeping its PR0663 section with LCP-1."""
    from core.page_composer import continuation_code
    from scripts.fix_lcp_panel_schedule_project import (
        build_excel_block,
        detect_controller_groups,
        slice_worksheet,
    )

    ws = _worksheet_by_name(candidate, "EMS 15.0 Lighting Output Matrix")
    base = _candidate_page_by_code(candidate, "EMS 15.0")
    if base is None:
        raise MigrationError("Candidate EMS 15.0 page was not created.")

    preamble, groups = detect_controller_groups(ws)
    if len(groups) < 2:
        raise MigrationError("EMS 15.0 must contain Controller 601 and Controller 602 sections.")

    pages: list[dict[str, Any]] = []
    group_id = "page_sa31_15_0"
    for index, group in enumerate(groups[:2]):
        rows = list(preamble) + list(group["rows"])
        temp = slice_worksheet(
            ws,
            rows,
            new_id=f"{ws['id']}_matrix_{index}",
            new_name=ws.get("name") or "EMS 15.0 Lighting Output Matrix",
            title_text="LIGHTING OUTPUT MATRIX",
        )
        block = build_excel_block(temp, f"{temp['id']}_xr")
        block["sourceWorksheetId"] = ws["id"]
        block["sourceSheet"] = ws.get("name", "")
        block["srcRows"] = rows
        block["splitMode"] = "none"
        block["allowContinuation"] = False
        block["minScale"] = 0.68
        block["scaleMode"] = "fit_body"
        block["pageFamily"] = "matrix"
        block["layoutProfile"] = "io_table"
        block["renderProfile"] = "singh360_standard_table"

        page = _clone_page_metadata(base)
        page.update({
            "id": group_id if index == 0 else f"{group_id}_c{index}",
            "order": 0,
            "include": True,
            "sheetCode": "EMS 15.0" if index == 0 else continuation_code("EMS 15.0", index),
            "displaySheetCode": "EMS 15.0" if index == 0 else continuation_code("EMS 15.0", index),
            "sheetTitle": (
                "Lighting Output Matrix - LCP-1 / Expansion"
                if index == 0
                else "Lighting Output Matrix - LCP-2"
            ),
            "sheetTab": ws.get("name", ""),
            "pageType": base.get("pageType", "data-grid"),
            "pageFamily": "matrix",
            "layoutProfile": "io_table",
            "renderMode": "excel_exact",
            "renderProfile": "singh360_standard_table",
            "sourceSheet": ws.get("name", ""),
            "sourceRange": temp.get("sourceRange", ""),
            "printArea": temp.get("printArea"),
            "splitMode": "none",
            "repeatRows": block.get("repeatRows", []),
            "minScale": 0.68,
            "allowContinuation": False,
            "scaleMode": "fit_body",
            "linkedWorksheetId": ws["id"],
            "blocks": [block],
            "canvasObjects": [],
            "assets": [],
            "underlays": [],
            "notes": "",
            "revisionRows": [],
            "pageGroupId": group_id,
            "continuationOf": None if index == 0 else group_id,
            "continuationIndex": index,
            "generatedContinuation": index > 0,
            "layoutWarnings": [],
        })
        pages.append(page)

    combined = " ".join(_page_text(page) for page in pages).lower()
    for token in ("controller id: 601", "pr0663", "controller id: 602"):
        if token not in combined:
            raise MigrationError(f"EMS 15.0 split lost required content: {token}")
    return pages


def _build_panel_pages(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Build EMS 16.0/16.1 with equal columns and one common visual scale."""
    from scripts.fix_lcp_panel_schedule_project import build_excel_block

    ws1 = _worksheet_by_name(candidate, "EMS 16.0 LCP-1 Panel Schedule")
    ws2 = _worksheet_by_name(candidate, "EMS 16.1 LCP-2 Panel Schedule")
    base = _candidate_page_by_code(candidate, "EMS 16.0")
    if base is None:
        raise MigrationError("Candidate EMS 16.0 page was not created.")

    block1 = build_excel_block(ws1, f"{ws1['id']}_xr")
    block2 = build_excel_block(ws2, f"{ws2['id']}_xr")

    width_count = max(len(block1.get("colWidths") or []), len(block2.get("colWidths") or []))
    shared_widths: list[int] = []
    for col in range(width_count):
        shared_widths.append(max(
            (block1.get("colWidths") or [0] * width_count)[col] if col < len(block1.get("colWidths") or []) else 0,
            (block2.get("colWidths") or [0] * width_count)[col] if col < len(block2.get("colWidths") or []) else 0,
            48,
        ))
    total = sum(shared_widths) or 1
    shared_widths = [max(48, int(round(width * 1480 / total))) for width in shared_widths]
    if shared_widths:
        shared_widths[-1] += 1480 - sum(shared_widths)

    for block in (block1, block2):
        block["colWidths"] = list(shared_widths)
        block["splitMode"] = "none"
        block["allowContinuation"] = False
        block["scaleMode"] = "fit_body"
        block["pageFamily"] = "panelDetail"
        block["layoutProfile"] = "io_table"

    natural_width = max(sum(block1.get("colWidths") or []), sum(block2.get("colWidths") or []), 1)
    natural_height = max(sum(block1.get("rowHeights") or []), sum(block2.get("rowHeights") or []), 1)
    common_scale = min(1.0, 1578.0 / natural_width, 596.0 / natural_height)
    common_scale = max(0.42, min(1.0, common_scale))
    block1["maxScale"] = round(common_scale, 4)
    block2["maxScale"] = round(common_scale, 4)

    pages: list[dict[str, Any]] = []
    for index, (ws, block, code, title) in enumerate((
        (ws1, block1, "EMS 16.0", "LCP-1 Panel Schedule"),
        (ws2, block2, "EMS 16.1", "LCP-2 Panel Schedule"),
    )):
        page = _clone_page_metadata(base)
        page.update({
            "id": f"page_sa31_16_{index}",
            "order": 0,
            "include": True,
            "sheetCode": code,
            "displaySheetCode": code,
            "sheetTitle": title,
            "sheetTab": ws.get("name", ""),
            "pageType": base.get("pageType", "data-grid"),
            "pageFamily": "panelDetail",
            "layoutProfile": "io_table",
            "renderMode": "excel_exact",
            "renderProfile": "singh360_standard_table",
            "sourceSheet": ws.get("name", ""),
            "sourceRange": ws.get("sourceRange", ""),
            "printArea": ws.get("printArea"),
            "splitMode": "none",
            "repeatRows": block.get("repeatRows", []),
            "minScale": 0.68,
            "allowContinuation": False,
            "scaleMode": "fit_body",
            "linkedWorksheetId": ws["id"],
            "blocks": [block],
            "canvasObjects": [],
            "assets": [],
            "underlays": [],
            "notes": "",
            "revisionRows": [],
            "pageGroupId": f"page_sa31_16_{index}",
            "continuationOf": None,
            "continuationIndex": 0,
            "generatedContinuation": False,
            "layoutWarnings": [],
        })
        pages.append(page)

    text1 = _page_text(pages[0]).lower()
    text2 = _page_text(pages[1]).lower()
    if "controller id: 601" not in text1 or "pr0663" not in text1 or "controller id: 602" in text1:
        raise MigrationError("EMS 16.0 content validation failed.")
    if "controller id: 602" not in text2 or "controller id: 601" in text2:
        raise MigrationError("EMS 16.1 content validation failed.")
    return pages


def _candidate_pages(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    matrix_pages = _build_matrix_pages(candidate)
    panel_pages = _build_panel_pages(candidate)

    result: list[dict[str, Any]] = []
    inserted_matrix = False
    inserted_panels = False
    for page in sorted(candidate.get("pages", []), key=lambda item: int(item.get("order") or 0)):
        code = _norm(_page_code(page))
        if code.startswith("ems 15.0"):
            if not inserted_matrix:
                result.extend(matrix_pages)
                inserted_matrix = True
            continue
        if code.startswith("ems 16.0") or code == "ems 16.1":
            if not inserted_panels:
                result.extend(panel_pages)
                inserted_panels = True
            continue
        result.append(copy.deepcopy(page))

    if not inserted_matrix:
        at = next((i for i, page in enumerate(result) if _norm(_page_code(page)) == "ems 15.1"), len(result))
        result[at:at] = matrix_pages
    if not inserted_panels:
        at = next((i for i, page in enumerate(result) if _norm(_page_code(page)) == "ems 17.0"), len(result))
        result[at:at] = panel_pages

    for order, page in enumerate(result, start=1):
        page["order"] = order
    return result


def _match_existing(candidate_page: dict[str, Any], existing_pages: list[dict[str, Any]], used: set[str]) -> dict[str, Any] | None:
    tab = _page_tab(candidate_page)
    title = _page_title(candidate_page)
    code = _norm(_page_code(candidate_page))

    def available(page: dict[str, Any]) -> bool:
        return str(page.get("id") or "") not in used

    if tab:
        match = next((page for page in existing_pages if available(page) and _page_tab(page) == tab), None)
        if match:
            return match
    if title:
        match = next((page for page in existing_pages if available(page) and _page_title(page) == title), None)
        if match:
            return match
    if code:
        match = next((page for page in existing_pages if available(page) and _norm(_page_code(page)) == code), None)
        if match:
            return match
    return None


def merge_projects(existing: dict[str, Any], candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_pages = _candidate_pages(candidate)
    existing_pages = [copy.deepcopy(page) for page in existing.get("pages", [])]
    used: set[str] = set()
    final_pages: list[dict[str, Any]] = []
    preserved_manual: list[str] = []
    refreshed: list[str] = []
    added: list[str] = []
    manual_counts_before: dict[str, tuple[int, int, int]] = {}

    for candidate_page in candidate_pages:
        existing_page = _match_existing(candidate_page, existing_pages, used)
        code = _page_code(candidate_page)
        preserve_exact = _norm(code) in MANUAL_PRESERVE_CODES
        if existing_page:
            used.add(str(existing_page.get("id") or ""))
            manual_counts_before[str(existing_page.get("id"))] = _count_manual(existing_page)

        if existing_page and (_has_manual_content(existing_page) or preserve_exact):
            merged = copy.deepcopy(existing_page)
            for field in IDENTITY_FIELDS:
                if field in candidate_page:
                    merged[field] = copy.deepcopy(candidate_page[field])
            merged["include"] = True
            merged["order"] = len(final_pages) + 1
            merged["pageGroupId"] = merged.get("id")
            merged["continuationOf"] = None
            merged["continuationIndex"] = 0
            merged["generatedContinuation"] = False
            if preserve_exact:
                linked = candidate_page.get("linkedWorksheetId")
                for block in merged.get("blocks") or []:
                    if isinstance(block, dict) and block.get("sourceWorksheetId"):
                        block["sourceWorksheetId"] = linked
                        block["sourceSheet"] = candidate_page.get("sourceSheet", block.get("sourceSheet", ""))
                        block["sourceRange"] = candidate_page.get("sourceRange", block.get("sourceRange", ""))
            preserved_manual.append(code)
        else:
            merged = copy.deepcopy(candidate_page)
            if existing_page:
                merged["id"] = existing_page["id"]
                for field in MANUAL_FIELDS:
                    if existing_page.get(field):
                        merged[field] = copy.deepcopy(existing_page[field])
                refreshed.append(code)
            else:
                added.append(code)
            merged["order"] = len(final_pages) + 1
            if not _norm(code).startswith("ems 15.0"):
                merged["pageGroupId"] = merged.get("id")
                merged["continuationOf"] = None
                merged["continuationIndex"] = 0
                merged["generatedContinuation"] = False

        final_pages.append(merged)

    stale = [page for page in existing_pages if str(page.get("id") or "") not in used]
    archived = [copy.deepcopy(page) for page in existing.get("archivedPages", [])]
    for page in stale:
        archived.append({
            **page,
            "include": False,
            "archivedAt": _now(),
            "archiveReason": "Superseded by latest SA31 workbook refresh",
        })

    matrix_base = next((p for p in final_pages if _norm(_page_code(p)) == "ems 15.0"), None)
    if matrix_base:
        group_id = matrix_base["id"]
        matrix_base["pageGroupId"] = group_id
        matrix_base["continuationOf"] = None
        matrix_base["continuationIndex"] = 0
        matrix_base["generatedContinuation"] = False
        continuation_index = 0
        for page in final_pages:
            code = _norm(_page_code(page))
            if code.startswith("ems 15.0") and page is not matrix_base:
                continuation_index += 1
                page["pageGroupId"] = group_id
                page["continuationOf"] = group_id
                page["continuationIndex"] = continuation_index
                page["generatedContinuation"] = True

    result = copy.deepcopy(existing)
    result["worksheets"] = copy.deepcopy(candidate.get("worksheets", []))
    result["sources"] = copy.deepcopy(candidate.get("sources", []))
    result["pages"] = final_pages
    result["archivedPages"] = archived
    result["sourceWorkbookName"] = candidate.get("sourceWorkbookName") or candidate.get("metadata", {}).get("sourceFile")
    result["paginationLocked"] = True

    metadata = copy.deepcopy(existing.get("metadata", {}))
    for key, value in (candidate.get("metadata") or {}).items():
        if value not in (None, ""):
            metadata[key] = value
    result["metadata"] = metadata

    result.setdefault("importHistory", []).append({
        "sourceFile": result.get("sourceWorkbookName") or metadata.get("sourceFile"),
        "importedAt": _now(),
        "mode": "SA31 exact workbook refresh",
        "preservedManual": preserved_manual,
        "refreshed": refreshed,
        "added": added,
        "archived": [_page_code(page) for page in stale],
    })

    for order, page in enumerate(final_pages, start=1):
        page["order"] = order

    summary = {
        "preservedManual": preserved_manual,
        "refreshed": refreshed,
        "added": added,
        "archived": [_page_code(page) for page in stale],
        "manualCountsBefore": manual_counts_before,
    }
    return result, summary


def verify_project(project: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    pages = [page for page in project.get("pages", []) if page.get("include", True)]
    codes = [_page_code(page) for page in pages]
    code_set = {_norm(code) for code in codes}

    missing = [code for code in REQUIRED_BASE_CODES if _norm(code) not in code_set]
    if missing:
        raise MigrationError("Required output pages are missing: " + ", ".join(missing))

    if sum(1 for code in codes if _norm(code) == "ems 16.0") != 1:
        raise MigrationError("EMS 16.0 must occur exactly once.")
    if sum(1 for code in codes if _norm(code) == "ems 16.1") != 1:
        raise MigrationError("EMS 16.1 must occur exactly once.")

    group15 = [page for page in pages if _norm(_page_code(page)).startswith("ems 15.0")]
    combined15 = " ".join(_page_text(page) for page in group15).lower()
    for token in ("controller id: 601", "pr0663", "controller id: 602"):
        if token not in combined15:
            raise MigrationError(f"Lighting Output Matrix is missing {token}.")
    schedule = next(page for page in pages if _norm(_page_code(page)) == "ems 15.1")
    if "controller id: 601" not in _page_text(schedule).lower():
        raise MigrationError("EMS 15.1 lost its Controller 601 header.")

    p16 = next(page for page in pages if _norm(_page_code(page)) == "ems 16.0")
    p161 = next(page for page in pages if _norm(_page_code(page)) == "ems 16.1")
    text16 = _page_text(p16).lower()
    text161 = _page_text(p161).lower()
    if "controller id: 601" not in text16 or "pr0663" not in text16 or "controller id: 602" in text16:
        raise MigrationError("EMS 16.0 verification failed.")
    if "controller id: 602" not in text161 or "controller id: 601" in text161:
        raise MigrationError("EMS 16.1 verification failed.")

    scale16 = (p16.get("blocks") or [{}])[0].get("maxScale")
    scale161 = (p161.get("blocks") or [{}])[0].get("maxScale")
    if not scale16 or abs(float(scale16) - float(scale161)) > 0.0001:
        raise MigrationError("EMS 16.0 and EMS 16.1 do not share one scale ceiling.")

    if existing:
        for code in ("EMS 12.0", "EMS 18.0", "EMS 19.0", "EMS 20.0"):
            old = next((page for page in existing.get("pages", []) if _norm(_page_title(page)) == _norm(
                next((p.get("sheetTitle") for p in pages if _norm(_page_code(p)) == _norm(code)), "")
            )), None)
            new = next((page for page in pages if _norm(_page_code(page)) == _norm(code)), None)
            if old and new and _has_manual_content(old):
                before = _count_manual(old)
                after = _count_manual(new)
                if any(a < b for a, b in zip(after, before)):
                    raise MigrationError(f"Manual content count dropped on {code}: {before} -> {after}")

    return {
        "pageCount": len(pages),
        "codes": codes,
        "lightingMatrixPages": len(group15),
        "panelCommonScale": scale16,
    }


def apply_migration(repo: Path, project_id: str, workbook_path: Path) -> dict[str, Any]:
    repo = repo.resolve()
    workbook_path = workbook_path.resolve()
    if not workbook_path.is_file():
        raise MigrationError(f"Updated workbook was not found: {workbook_path}")

    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from core.project_model import recalc_page_numbers, sanitize_json
    from core.project_store import ProjectStore
    from core.sheet_index_sync import sync_project_sheet_index
    from core.workbook_importer import import_workbook

    docs = repo / ".docs"
    store = ProjectStore(docs)
    existing = store.load(project_id)
    if existing is None:
        raise MigrationError(f"Project {project_id} was not found.")

    project_dir = store.dir_for(project_id, existing)
    source_dir = store.sources_dir(project_id, "workbook", existing)
    source_copy = source_dir / workbook_path.name
    if source_copy.resolve() != workbook_path:
        shutil.copy2(workbook_path, source_copy)

    candidate = import_workbook(source_copy, project_id=project_id)
    candidate["sourceWorkbookName"] = workbook_path.name
    candidate.setdefault("metadata", {})["sourceFile"] = workbook_path.name
    for source in candidate.get("sources", []):
        if isinstance(source, dict) and source.get("type") == "workbook":
            source["name"] = workbook_path.name
            source["path"] = str(source_copy)

    merged, summary = merge_projects(existing, candidate)
    sync_project_sheet_index(merged)
    recalc_page_numbers(merged)
    merged = sanitize_json(merged)
    verification = verify_project(merged, existing)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = docs / "patch_backups" / f"sa31_full_workbook_refresh_{project_id}_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    current_path = store.read_path(project_id)
    if current_path and current_path.is_file():
        shutil.copy2(current_path, backup_dir / "project.json")
    shutil.copy2(source_copy, backup_dir / workbook_path.name)

    saved_path = store.save(project_id, merged)
    print(f"[OK] Saved repaired project: {saved_path}")
    print(f"[OK] Project backup: {backup_dir}")
    print(f"[OK] Output pages: {verification['pageCount']}")
    print(f"[OK] Lighting Matrix pages: {verification['lightingMatrixPages']}")
    print(f"[OK] EMS 16 common scale: {verification['panelCommonScale']}")
    return {
        "savedPath": str(saved_path),
        "backup": str(backup_dir),
        "summary": summary,
        "verification": verification,
    }


def self_test() -> None:
    def page(code: str, tab: str, title: str, text: str, *, manual: bool = False) -> dict[str, Any]:
        return {
            "id": f"old_{code.replace(' ', '_').replace('.', '_')}",
            "order": 1,
            "include": True,
            "sheetCode": code,
            "displaySheetCode": code,
            "sheetTitle": title,
            "sheetTab": tab,
            "pageType": "canvas" if manual else "data-grid",
            "linkedWorksheetId": f"ws_{code}",
            "blocks": [{"id": "b", "type": "canvas" if manual else "excelRange", "grid": [[text]]}],
            "canvasObjects": [{"type": "rect"}] if manual else [],
            "assets": [],
            "underlays": [],
            "notes": "",
            "revisionRows": [],
            "templateId": "ansi-b-standard",
        }

    existing = {
        "id": DEFAULT_PROJECT_ID,
        "metadata": {"projectName": "Existing"},
        "pages": [
            page("EMS 12.0", "EMS 12.0 Overall Layout", "EMS Controls Overall Layout", "manual", manual=True),
            page("EMS 15.0", "EMS 15.0 Lighting Output Matrix", "Lighting Output Matrix", "old 601"),
        ],
        "worksheets": [],
        "sources": [],
        "archivedPages": [],
    }
    candidate = copy.deepcopy(existing)
    candidate["metadata"] = {"projectName": "Updated"}
    candidate["worksheets"] = [{"id": "ws_new", "name": "Updated"}]
    candidate["sources"] = [{"id": "src", "type": "workbook", "name": "new.xlsm"}]
    candidate["pages"] = [
        page("EMS 12.0", "EMS 12.0 Overall Layout", "EMS Controls Overall Layout", "candidate"),
        page("EMS 15.1", "EMS 15.1 Lighting Schedule", "Lighting Schedule", "Controller ID: 601"),
    ]

    used: set[str] = set()
    matched = _match_existing(candidate["pages"][0], existing["pages"], used)
    assert matched is existing["pages"][0]
    merged = copy.deepcopy(matched)
    for field in IDENTITY_FIELDS:
        if field in candidate["pages"][0]:
            merged[field] = candidate["pages"][0][field]
    assert merged["canvasObjects"] == [{"type": "rect"}]
    assert merged["sheetCode"] == "EMS 12.0"
    print("[OK] Pure manual-page preservation self-test")
