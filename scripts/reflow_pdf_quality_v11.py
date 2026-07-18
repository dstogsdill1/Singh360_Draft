"""Reflow the active SA31 project and remove hidden cover micro-artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.page_composer import EXCEL_MIN_SCALE, _slice_excel_block
from core.project_model import ensure_project_shape
from core.project_store import ProjectStore
from core.table_style_profile import NARRATIVE_RENDER_PROFILE, RENDER_PROFILE, apply_singh360_profile
from core.workbook_importer import _apply_table_geometry, _excel_range_block, _layout_profile_for, _split_settings_for_page


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def stable(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def number(value: Any, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else fallback
    except (TypeError, ValueError):
        return fallback


def visible_size(obj: dict[str, Any]) -> tuple[float, float]:
    kind = str(obj.get("type") or "").lower()
    sx = abs(number(obj.get("scaleX"), 1.0))
    sy = abs(number(obj.get("scaleY"), 1.0))
    if kind == "line":
        return abs(number(obj.get("x2")) - number(obj.get("x1"))) * sx, abs(number(obj.get("y2")) - number(obj.get("y1"))) * sy
    if kind == "circle":
        diameter = abs(number(obj.get("radius"))) * 2
        return diameter * sx, diameter * sy
    return abs(number(obj.get("width"))) * sx, abs(number(obj.get("height"))) * sy


def is_micro_artifact(obj: dict[str, Any]) -> bool:
    kind = str(obj.get("type") or "").lower()
    if kind in {"text", "i-text", "textbox", "image", "group"}:
        return False
    if any(str(obj.get(key) or "").strip() for key in ("text", "label", "componentId", "s360ComponentId", "pdfSource", "assetId")):
        return False
    width, height = visible_size(obj)
    return max(width, height) <= 10 and width * height <= 70


def select_project(store: ProjectStore, requested: str | None) -> tuple[str, Path, bool]:
    if requested:
        path = store.read_path(requested)
        if path:
            return requested, path, False
    candidates = sorted(store.projects_dir.glob("*/project.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("No Singh360 projects were found.")
    path = candidates[0]
    raw = json.loads(path.read_text(encoding="utf-8"))
    return str(raw.get("id") or path.parent.name.rsplit("__", 1)[-1]), path, bool(requested)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--project-id")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    store = ProjectStore(repo / ".docs")
    project_id, path, fallback = select_project(store, args.project_id)
    project = store.load(project_id)
    if not project:
        raise RuntimeError(f"Could not load project {project_id}")
    project = ensure_project_shape(project)

    backup = repo / ".docs" / "archive" / f"pdf_quality_v11_{stamp()}"
    backup.mkdir(parents=True, exist_ok=True)
    before_path = backup / "project_before_v11.json"
    shutil.copy2(path, before_path)

    page_ids = [str(page.get("id")) for page in project.get("pages", [])]
    sheet_codes = [str(page.get("displaySheetCode") or page.get("sheetCode") or "") for page in project.get("pages", [])]
    worksheets_hash = stable(project.get("worksheets", []))
    non_cover_canvas_hash = stable([
        {"id": page.get("id"), "canvas": page.get("canvasObjects", []), "assets": page.get("assets", [])}
        for page in project.get("pages", [])
        if page.get("pageType") != "cover"
    ])

    worksheets = {str(ws.get("id")): ws for ws in project.get("worksheets", [])}
    reflowed = 0
    profiles: dict[str, int] = {}
    removed_artifacts = 0

    try:
        for page in project.get("pages", []):
            code = str(page.get("displaySheetCode") or page.get("sheetCode") or "").lower()
            if page.get("pageType") == "cover" or code == "ems 1.0":
                objects = list(page.get("canvasObjects") or [])
                cleaned = [obj for obj in objects if not is_micro_artifact(obj)]
                removed_artifacts += len(objects) - len(cleaned)
                page["canvasObjects"] = cleaned

            if page.get("renderMode") != "excel_exact":
                continue
            blocks = page.get("blocks") or []
            block_index = next((i for i, block in enumerate(blocks) if isinstance(block, dict) and block.get("type") == "excelRange"), None)
            if block_index is None:
                continue
            old = blocks[block_index]
            ws_id = str(page.get("linkedWorksheetId") or old.get("sourceWorksheetId") or "")
            ws = worksheets.get(ws_id)
            if not ws:
                continue

            family = str(page.get("pageFamily") or "table")
            page_type = str(page.get("pageType") or "data-grid")
            blob = f"{page.get('sheetTab', '')} {page.get('sheetTitle', '')} {family}".lower()
            profile = _layout_profile_for(family, page_type, blob)
            settings = _split_settings_for_page(family, page_type, True)
            settings.update({
                "splitMode": page.get("splitMode", settings.get("splitMode", "auto_rows")),
                "allowContinuation": page.get("allowContinuation", settings.get("allowContinuation", True)),
                "minScale": page.get("minScale", settings.get("minScale", EXCEL_MIN_SCALE)),
                "scaleMode": "fit_body",
                "trimBlankRows": page.get("trimBlankRows", True),
                "trimBlankColumns": page.get("trimBlankColumns", True),
            })

            full = _excel_range_block(ws, str(old.get("id") or f"{ws_id}_xr"), settings)
            _apply_table_geometry(full, family, page_type, profile)
            apply_singh360_profile(full, str(page.get("normalizedHeaderStyle") or "orange"))
            full["layoutProfile"] = profile

            wanted_source_rows = {
                int(row)
                for row in (old.get("srcRows") or [])
                if isinstance(row, int)
            }
            full_source_rows = list(full.get("srcRows") or range(len(full.get("grid") or [])))
            slice_indices = [
                index
                for index, source_row in enumerate(full_source_rows)
                if int(source_row) in wanted_source_rows
            ]
            part = (
                _slice_excel_block(
                    full,
                    slice_indices,
                    int(page.get("continuationIndex") or 0),
                )
                if slice_indices and len(slice_indices) < len(full.get("grid") or [])
                else full
            )
            part["id"] = old.get("id") or part.get("id")
            part["layoutProfile"] = profile

            next_blocks = list(blocks)
            next_blocks[block_index] = part
            page["blocks"] = next_blocks
            page["layoutProfile"] = profile
            page["renderProfile"] = NARRATIVE_RENDER_PROFILE if profile in {"guideline_table", "instruction_table", "project_scope_table", "workflow_milestone_table", "contact_directory_table"} else RENDER_PROFILE
            page["minScale"] = part.get("minScale", page.get("minScale", EXCEL_MIN_SCALE))
            page["scaleMode"] = "fit_body"
            page["repeatRows"] = part.get("repeatRows", page.get("repeatRows", []))
            page["sourceRevision"] = int(page.get("sourceRevision") or 0) + 1
            reflowed += 1
            profiles[profile] = profiles.get(profile, 0) + 1

        if page_ids != [str(page.get("id")) for page in project.get("pages", [])]:
            raise RuntimeError("Page IDs changed.")
        if sheet_codes != [str(page.get("displaySheetCode") or page.get("sheetCode") or "") for page in project.get("pages", [])]:
            raise RuntimeError("Sheet codes changed.")
        if worksheets_hash != stable(project.get("worksheets", [])):
            raise RuntimeError("Source worksheets changed.")
        if non_cover_canvas_hash != stable([
            {"id": page.get("id"), "canvas": page.get("canvasObjects", []), "assets": page.get("assets", [])}
            for page in project.get("pages", [])
            if page.get("pageType") != "cover"
        ]):
            raise RuntimeError("Non-cover overlays or assets changed.")

        store.save(project_id, project)
        if not store.load(project_id):
            raise RuntimeError("Saved project could not be reloaded.")
    except Exception:
        shutil.copy2(before_path, path)
        raise

    report = {
        "ok": True,
        "projectId": project_id,
        "requestedProjectFallbackUsed": fallback,
        "pagesReflowed": reflowed,
        "profiles": profiles,
        "coverMicroArtifactsRemoved": removed_artifacts,
        "pageCountPreserved": len(page_ids),
        "sourceWorksheetsPreserved": True,
        "sheetCodesPreserved": True,
        "nonCoverOverlaysPreserved": True,
        "backup": str(backup),
    }
    (backup / "v11_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
