from __future__ import annotations

import argparse
import copy
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
        d = abs(number(obj.get("radius"))) * 2
        return d * sx, d * sy
    return abs(number(obj.get("width"))) * sx, abs(number(obj.get("height"))) * sy


def is_cover_micro_artifact(obj: dict[str, Any]) -> bool:
    kind = str(obj.get("type") or "").lower()
    if kind in {"text", "i-text", "textbox"} and str(obj.get("text") or obj.get("label") or "").strip():
        return False
    width, height = visible_size(obj)
    max_dimension = max(width, height)
    min_dimension = min(width, height)
    area = width * height
    if not math.isfinite(max_dimension) or not math.isfinite(area):
        return True
    if obj.get("visible") is False or number(obj.get("opacity"), 1.0) <= 0.001:
        return True
    if max_dimension <= 42 or area <= 1100:
        return True
    if min_dimension <= 2 and max_dimension <= 72:
        return True
    return False



def worksheet_semantic_snapshot(items: list[dict[str, Any]]) -> str:
    """Hash worksheet data/styles after shape normalization.

    layoutMode is intentionally excluded because this migration may reset the
    cable schedule from Manual to Auto. All worksheet values, styles, merges,
    dimensions, names, and source metadata remain protected.
    """
    normalized: list[dict[str, Any]] = []
    for item in items:
        clone = dict(item)
        clone.pop("layoutMode", None)
        normalized.append(clone)
    return stable(normalized)



def select_project(store: ProjectStore, requested: str | None) -> tuple[str, Path]:
    if requested:
        path = store.read_path(requested)
        if path:
            return requested, path
    candidates = sorted(store.projects_dir.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("No Singh360 projects found.")
    path = candidates[0]
    raw = json.loads(path.read_text(encoding="utf-8"))
    return str(raw.get("id") or path.parent.name.rsplit("__", 1)[-1]), path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--project-id")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    store = ProjectStore(repo / ".docs")
    project_id, path = select_project(store, args.project_id)
    project = store.load(project_id)
    if not project:
        raise RuntimeError(f"Could not load project {project_id}")
    project = ensure_project_shape(project)

    # Keep one immutable copy of the user's Source worksheets. Some legacy
    # workbook helper functions mutate their worksheet argument while preparing
    # output geometry. V12.3 builds from deep copies and restores this canonical
    # Source list before saving, so normalized reflow cannot alter Source data.
    source_worksheets = copy.deepcopy(project.get("worksheets", []))
    worksheet_baseline = worksheet_semantic_snapshot(source_worksheets)

    backup = repo / ".docs" / "archive" / f"wysiwyg_source_v12_3_{stamp()}"
    backup.mkdir(parents=True, exist_ok=True)
    before = backup / "project_before_v12.json"
    shutil.copy2(path, before)

    page_ids = [str(p.get("id")) for p in project.get("pages", [])]
    sheet_codes = [str(p.get("displaySheetCode") or p.get("sheetCode") or "") for p in project.get("pages", [])]
    non_cover_hash = stable([
        {"id": p.get("id"), "canvas": p.get("canvasObjects", []), "assets": p.get("assets", [])}
        for p in project.get("pages", []) if p.get("pageType") != "cover"
    ])

    # Reflow against disposable worksheet copies only.
    worksheets = {
        str(ws.get("id")): copy.deepcopy(ws)
        for ws in source_worksheets
    }
    removed = 0
    reflowed = 0
    cable_reset = 0

    try:
        for page in project.get("pages", []):
            code = str(page.get("displaySheetCode") or page.get("sheetCode") or "").lower()
            if page.get("pageType") == "cover" or code == "ems 1.0":
                objects = list(page.get("canvasObjects") or [])
                cleaned = [obj for obj in objects if not is_cover_micro_artifact(obj)]
                removed += len(objects) - len(cleaned)
                page["canvasObjects"] = cleaned
                page["sourceRevision"] = int(page.get("sourceRevision") or 0) + 1

            if page.get("renderMode") != "excel_exact":
                continue
            blocks = page.get("blocks") or []
            block_index = next((i for i, b in enumerate(blocks) if isinstance(b, dict) and b.get("type") == "excelRange"), None)
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

            if profile == "cable_termination_schedule" and ws.get("layoutMode") == "manual":
                ws["layoutMode"] = "auto"
                for saved_ws in source_worksheets:
                    if str(saved_ws.get("id")) == ws_id:
                        saved_ws["layoutMode"] = "auto"
                        break
                cable_reset += 1

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

            rows = [int(r) for r in (old.get("srcRows") or []) if isinstance(r, int) and 0 <= r < len(full.get("grid") or [])]
            part = _slice_excel_block(full, sorted(set(rows)), int(page.get("continuationIndex") or 0)) if rows and len(set(rows)) < len(full.get("grid") or []) else full
            part["id"] = old.get("id") or part.get("id")
            next_blocks = list(blocks)
            next_blocks[block_index] = part
            page["blocks"] = next_blocks
            page["layoutProfile"] = profile
            page["renderProfile"] = NARRATIVE_RENDER_PROFILE if profile in {
                "guideline_table", "instruction_table", "project_scope_table",
                "workflow_milestone_table", "contact_directory_table",
            } else RENDER_PROFILE
            page["sourceRevision"] = int(page.get("sourceRevision") or 0) + 1
            reflowed += 1

        if page_ids != [str(p.get("id")) for p in project.get("pages", [])]:
            raise RuntimeError("Page IDs changed.")
        if sheet_codes != [str(p.get("displaySheetCode") or p.get("sheetCode") or "") for p in project.get("pages", [])]:
            raise RuntimeError("Sheet codes changed.")
        if non_cover_hash != stable([
            {"id": p.get("id"), "canvas": p.get("canvasObjects", []), "assets": p.get("assets", [])}
            for p in project.get("pages", []) if p.get("pageType") != "cover"
        ]):
            raise RuntimeError("Non-cover overlays changed.")

        # Discard any accidental helper mutations and restore the protected
        # Source worksheets. The only permitted difference is layoutMode for
        # EMS 13.0, which worksheet_semantic_snapshot intentionally excludes.
        project["worksheets"] = source_worksheets

        if worksheet_baseline != worksheet_semantic_snapshot(project.get("worksheets", [])):
            raise RuntimeError("Worksheet values/styles changed.")

        store.save(project_id, project)
    except Exception:
        shutil.copy2(before, path)
        raise

    report = {
        "ok": True,
        "projectId": project_id,
        "coverArtifactsRemoved": removed,
        "pagesReflowed": reflowed,
        "cableScheduleAutoLayoutReset": cable_reset,
        "worksheetBaselineCapturedAfterShapeNormalization": True,
        "worksheetHelpersRanAgainstDeepCopies": True,
        "canonicalSourceWorksheetsRestoredBeforeSave": True,
        "worksheetValuesAndStylesPreserved": True,
        "backup": str(backup),
    }
    (backup / "v12_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
