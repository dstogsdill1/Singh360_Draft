from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.project_model import ensure_project_shape, recalc_page_numbers, sanitize_json
from core.project_store import ProjectStore
from core.workbook_reimport import apply_reimport, is_manual_page


EXPECTED_COLUMNS = {
    "EMS 3.0 Guidelines": 2,
    "EMS 4.0 Abbrev": 4,
    "EMS 5.0 Directory": 6,
    "EMS 6.0 Project Scope": 4,
    "EMS 7.0 Workflow": 6,
    "EMS 8.0 Resp Matrix": 10,
    "EMS 8.1 HEB Responsibilities": 4,
    "EMS 9.0 Equip Supply": 8,
    "EMS 10.0 BOM": 6,
    "EMS 13.0 RDM IDF Network": 11,
    "EMS 14.0 Cable Pulls": 9,
    "EMS 15.0 Lighting Output Matrix": 12,
    "EMS 16.0 LCP Panel Schedule": 12,
    "EMS 17.0 Field Instructions": 2,
}


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def stable(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def manual_fingerprint(page: dict[str, Any]) -> str:
    return stable(
        {
            "id": page.get("id"),
            "sheetCode": page.get("sheetCode"),
            "displaySheetCode": page.get("displaySheetCode"),
            "sheetTitle": page.get("sheetTitle"),
            "pageType": page.get("pageType"),
            "canvasObjects": page.get("canvasObjects", []),
            "assets": page.get("assets", []),
            "notes": page.get("notes"),
            "blocks": page.get("blocks", []),
        }
    )


def sheet_name(ws: dict[str, Any]) -> str:
    return str(ws.get("name") or ws.get("sourceSheet") or "").strip()


def grid_col_count(ws: dict[str, Any]) -> int:
    grid = ws.get("grid") or []
    return max((len(row or []) for row in grid), default=0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--workbook", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    workbook = Path(args.workbook).resolve()
    if not workbook.is_file():
        raise RuntimeError(f"Workbook not found: {workbook}")

    store = ProjectStore(repo / ".docs")
    project_path = store.read_path(args.project_id)
    existing = store.load(args.project_id)
    if not project_path or not existing:
        raise RuntimeError(f"Project not found: {args.project_id}")
    existing = ensure_project_shape(sanitize_json(existing))

    archive = repo / ".docs" / "archive" / f"sa31_appready_reimport_v14_{stamp()}"
    archive.mkdir(parents=True, exist_ok=True)
    before_path = archive / "project_before_v14.json"
    shutil.copy2(project_path, before_path)

    manual_before = {
        str(page.get("id")): manual_fingerprint(page)
        for page in existing.get("pages", [])
        if is_manual_page(page)
    }

    source_dir = store.sources_dir(args.project_id, "workbook")
    stored_workbook = source_dir / "SA31_102_EMS_Lighting_AppReady.xlsx"
    shutil.copy2(workbook, stored_workbook)

    try:
        updated, summary = apply_reimport(
            existing,
            stored_workbook,
            replace_page_ids=[],
            source_filename=stored_workbook.name,
        )
        updated = ensure_project_shape(updated)
        recalc_page_numbers(updated)

        if updated.get("id") != existing.get("id"):
            raise RuntimeError("Project ID changed during safe workbook refresh.")

        manual_after = {
            str(page.get("id")): manual_fingerprint(page)
            for page in updated.get("pages", [])
            if str(page.get("id")) in manual_before
        }
        for page_id, fingerprint in manual_before.items():
            if page_id not in manual_after:
                raise RuntimeError(
                    f"Manual drawing page was removed or archived during workbook refresh: {page_id}"
                )
            if manual_after[page_id] != fingerprint:
                raise RuntimeError(
                    f"Manual drawing page content changed during workbook refresh: {page_id}"
                )

        worksheets = {
            sheet_name(ws): ws
            for ws in updated.get("worksheets", [])
            if sheet_name(ws)
        }
        missing = [name for name in EXPECTED_COLUMNS if name not in worksheets]
        if missing:
            raise RuntimeError(
                "Required app-ready worksheets are missing: " + ", ".join(missing)
            )

        wrong_columns: list[str] = []
        for name, expected in EXPECTED_COLUMNS.items():
            actual = grid_col_count(worksheets[name])
            if actual != expected:
                wrong_columns.append(f"{name}: expected {expected}, got {actual}")
        if wrong_columns:
            raise RuntimeError(
                "App-ready worksheet column validation failed: "
                + "; ".join(wrong_columns)
            )

        # The exact pages that must remain standard.
        standard_tabs = {
            "EMS 13.0 RDM IDF Network",
            "EMS 14.0 Cable Pulls",
            "EMS 15.0 Lighting Output Matrix",
            "EMS 16.0 LCP Panel Schedule",
            "EMS 17.0 Field Instructions",
        }
        page_tabs = {str(page.get("sheetTab") or "") for page in updated.get("pages", [])}
        absent_standard = sorted(standard_tabs - page_tabs)
        if absent_standard:
            raise RuntimeError(
                "Standard output pages were not rebuilt: "
                + ", ".join(absent_standard)
            )

        metadata = dict(updated.get("metadata") or {})
        metadata["sourceFile"] = stored_workbook.name
        updated["metadata"] = metadata

        store.save(args.project_id, updated)
        if not store.load(args.project_id):
            raise RuntimeError("Refreshed project could not be reloaded.")
    except Exception:
        shutil.copy2(before_path, project_path)
        raise

    report = {
        "ok": True,
        "projectId": args.project_id,
        "workbook": str(stored_workbook),
        "summary": summary,
        "manualDrawingPagesPreserved": len(manual_before),
        "validatedWorksheetColumnCounts": EXPECTED_COLUMNS,
        "backup": str(archive),
    }
    (archive / "reimport_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
