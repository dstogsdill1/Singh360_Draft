"""Reflow existing excel_exact pages without changing source data or page count."""
from __future__ import annotations

import sys
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# S360_REPO_ROOT_BOOTSTRAP
# When a script is executed by absolute path, Python puts the scripts
# directory—not the repository root—at sys.path[0]. Add the repo root
# explicitly so `from core...` imports work reliably.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.page_composer import EXCEL_MIN_SCALE, _slice_excel_block
from core.project_model import ensure_project_shape
from core.project_store import ProjectStore
from core.table_style_profile import (
    NARRATIVE_RENDER_PROFILE,
    RENDER_PROFILE,
    apply_singh360_profile,
)
from core.workbook_importer import (
    _apply_table_geometry,
    _compact_text_instruction_block,
    _excel_range_block,
    _layout_profile_for,
    _split_settings_for_page,
)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def select_project(
    store: ProjectStore,
    project_id: str | None,
) -> tuple[str, Path, bool]:
    if project_id:
        path = store.read_path(project_id)
        if path:
            return project_id, path, False
    candidates = sorted(
        store.projects_dir.glob("*/project.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("No saved Singh360 projects were found.")
    path = candidates[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    chosen = str(data.get("id") or path.parent.name.rsplit("__", 1)[-1])
    return chosen, path, bool(project_id and chosen != project_id)


def reflow_project(project: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    project = ensure_project_shape(project)
    worksheets = {str(ws.get("id")): ws for ws in project.get("worksheets", [])}

    page_ids_before = [str(page.get("id")) for page in project.get("pages", [])]
    sheet_codes_before = [
        str(page.get("displaySheetCode") or page.get("sheetCode") or "")
        for page in project.get("pages", [])
    ]
    source_hash_before = stable_hash(project.get("worksheets", []))
    canvas_hash_before = stable_hash(
        [
            {
                "id": page.get("id"),
                "canvasObjects": page.get("canvasObjects", []),
                "assets": page.get("assets", []),
            }
            for page in project.get("pages", [])
        ]
    )

    changed = 0
    profiles: dict[str, int] = {}
    warnings: list[str] = []

    for page in project.get("pages", []):
        if page.get("renderMode") != "excel_exact":
            continue
        blocks = page.get("blocks") or []
        old_index = next(
            (
                index
                for index, block in enumerate(blocks)
                if isinstance(block, dict) and block.get("type") == "excelRange"
            ),
            None,
        )
        if old_index is None:
            continue
        old = blocks[old_index]
        ws_id = str(page.get("linkedWorksheetId") or old.get("sourceWorksheetId") or "")
        ws = worksheets.get(ws_id)
        if not ws:
            warnings.append(f"{page.get('sheetCode')}: linked worksheet {ws_id!r} is missing")
            continue

        family = str(page.get("pageFamily") or "table")
        page_type = str(page.get("pageType") or "data-grid")
        blob = f"{page.get('sheetTab', '')} {page.get('sheetTitle', '')} {family}".lower()
        profile = _layout_profile_for(family, page_type, blob)

        settings = _split_settings_for_page(family, page_type, True)
        settings.update(
            {
                "splitMode": page.get("splitMode", settings.get("splitMode", "auto_rows")),
                "allowContinuation": page.get(
                    "allowContinuation",
                    settings.get("allowContinuation", True),
                ),
                "minScale": page.get(
                    "minScale",
                    settings.get("minScale", EXCEL_MIN_SCALE),
                ),
                "scaleMode": "fit_body",
                "trimBlankRows": page.get("trimBlankRows", True),
                "trimBlankColumns": page.get("trimBlankColumns", True),
            }
        )

        full = _excel_range_block(
            ws,
            str(old.get("id") or f"{ws_id}_xr"),
            settings,
        )
        if family == "text" and profile in ("front_matter_table", "instruction_table"):
            _compact_text_instruction_block(full)
        _apply_table_geometry(full, family, page_type, profile)
        apply_singh360_profile(
            full,
            str(page.get("normalizedHeaderStyle") or "orange"),
        )
        full["layoutProfile"] = profile

        rows = [
            int(row)
            for row in (old.get("srcRows") or [])
            if isinstance(row, int) and 0 <= row < len(full.get("grid") or [])
        ]
        if rows and len(set(rows)) < len(full.get("grid") or []):
            part = _slice_excel_block(
                full,
                sorted(set(rows)),
                int(page.get("continuationIndex") or 0),
            )
        else:
            part = full
        part["id"] = old.get("id") or part.get("id")
        part["layoutProfile"] = profile

        next_blocks = list(blocks)
        next_blocks[old_index] = part
        page["blocks"] = next_blocks
        page["layoutProfile"] = profile
        page["renderProfile"] = (
            NARRATIVE_RENDER_PROFILE
            if profile == "front_matter_narrative_table"
            else RENDER_PROFILE
        )
        page["minScale"] = part.get("minScale", page.get("minScale", EXCEL_MIN_SCALE))
        page["scaleMode"] = "fit_body"
        page["repeatRows"] = part.get("repeatRows", page.get("repeatRows", []))
        page["sourceRevision"] = int(page.get("sourceRevision") or 0) + 1
        changed += 1
        profiles[profile] = profiles.get(profile, 0) + 1

    page_ids_after = [str(page.get("id")) for page in project.get("pages", [])]
    sheet_codes_after = [
        str(page.get("displaySheetCode") or page.get("sheetCode") or "")
        for page in project.get("pages", [])
    ]
    source_hash_after = stable_hash(project.get("worksheets", []))
    canvas_hash_after = stable_hash(
        [
            {
                "id": page.get("id"),
                "canvasObjects": page.get("canvasObjects", []),
                "assets": page.get("assets", []),
            }
            for page in project.get("pages", [])
        ]
    )

    if page_ids_before != page_ids_after:
        raise RuntimeError("Page IDs changed during table reflow.")
    if sheet_codes_before != sheet_codes_after:
        raise RuntimeError("Sheet codes changed during table reflow.")
    if source_hash_before != source_hash_after:
        raise RuntimeError("Source worksheets changed during table reflow.")
    if canvas_hash_before != canvas_hash_after:
        raise RuntimeError("Canvas overlays/assets changed during table reflow.")

    return project, {
        "pagesReflowed": changed,
        "profiles": profiles,
        "warnings": warnings,
        "pageCountPreserved": len(page_ids_before),
        "sourceWorksheetsPreserved": True,
        "canvasOverlaysPreserved": True,
        "sheetCodesPreserved": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--project-id")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    store = ProjectStore(repo / ".docs")
    project_id, path, used_fallback = select_project(store, args.project_id)
    project = store.load(project_id)
    if not project:
        raise RuntimeError(f"Could not load project {project_id}")

    backup_dir = repo / ".docs" / "archive" / f"table_layout_v10_{stamp()}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "project_before_reflow.json"
    shutil.copy2(path, backup_path)

    try:
        updated, report = reflow_project(project)
        if report["pagesReflowed"] == 0:
            raise RuntimeError("No excel_exact table pages were found to reflow.")
        saved = store.save(project_id, updated)
        reloaded = store.load(project_id)
        if not reloaded:
            raise RuntimeError("Saved project could not be reloaded.")
        report.update(
            {
                "projectId": project_id,
                "projectName": (
                    updated.get("projectDisplayName")
                    or updated.get("metadata", {}).get("projectName")
                ),
                "requestedProjectFallbackUsed": used_fallback,
                "savedPath": str(saved),
                "backup": str(backup_dir),
            }
        )
        (backup_dir / "reflow_report.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2))
    except Exception:
        shutil.copy2(backup_path, path)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
