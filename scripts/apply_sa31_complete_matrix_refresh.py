"""Apply the newest SA31 workbook with controller-safe output-matrix pagination.

This entry point fixes EMS 15.0 so every controller group is carried onto its
own readable page. It also supports future rack/condenser controller sections.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.page_composer import continuation_code
from scripts.apply_sa31_updated_workbook import patch_renderer_sources
import scripts.fix_lcp_panel_schedule_project as splitter
import scripts.sa31_refresh_core as refresh_core

DEFAULT_PROJECT_ID = refresh_core.DEFAULT_PROJECT_ID
MIN_READABLE_SCALE = 0.78
MAX_VISUAL_SCALE = 1.0
SOURCE_BODY_FONT_PX = 12
_CONTROLLER_RE = re.compile(r"\bcontroller\s*id\s*:\s*([A-Za-z0-9._-]+)", re.I)
_LCP_RE = re.compile(r"\bLCP[-\s]*(\d+)\b", re.I)


class MatrixRefreshError(refresh_core.MigrationError):
    pass


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _row_text(row: list[Any]) -> str:
    return " ".join(str(value or "").strip() for value in row if str(value or "").strip())


def _matrix_controller_header(ws: dict[str, Any], row: int) -> bool:
    grid = ws.get("grid") or []
    if not (0 <= row < len(grid)):
        return False
    text = _norm(_row_text(grid[row]))
    if "expansion" in text or "board id" in text or not _CONTROLLER_RE.search(text):
        return False
    return splitter._is_wide_merge_header(ws, row) or any(
        word in text
        for word in ("lcp", "panel", "rack", "condenser", "output", "schedule", "controller")
    )


def detect_all_controller_groups(ws: dict[str, Any]) -> tuple[list[int], list[dict[str, Any]]]:
    grid = ws.get("grid") or []
    if not grid:
        raise MatrixRefreshError("The EMS 15.0 output-matrix worksheet is empty.")
    end = splitter._trim_trailing_blank_rows(ws)
    controller_rows = [row for row in range(end) if _matrix_controller_header(ws, row)]
    if not controller_rows:
        raise MatrixRefreshError("No merged Controller ID headers were found in EMS 15.0.")

    preamble = list(range(controller_rows[0]))
    groups: list[dict[str, Any]] = []
    for index, start in enumerate(controller_rows):
        stop = controller_rows[index + 1] if index + 1 < len(controller_rows) else end
        rows = list(range(start, stop))
        header_text = _row_text(grid[start])
        controller_match = _CONTROLLER_RE.search(header_text)
        controller_id = controller_match.group(1) if controller_match else ""
        lcp_match = _LCP_RE.search(header_text)
        lcp_number = int(lcp_match.group(1)) if lcp_match else index + 1

        section_starts = [start]
        for row in rows[1:]:
            text = _norm(_row_text(grid[row]))
            if text and (
                "expansion" in text
                or "board id" in text
                or splitter._is_wide_merge_header(ws, row)
            ):
                section_starts.append(row)
        section_starts = sorted(set(section_starts))
        sections: list[list[int]] = []
        for section_index, section_start in enumerate(section_starts):
            section_stop = section_starts[section_index + 1] if section_index + 1 < len(section_starts) else stop
            section_rows = list(range(section_start, section_stop))
            if section_rows:
                sections.append(section_rows)

        groups.append({
            "start": start,
            "stop": stop,
            "rows": rows,
            "sections": sections or [rows],
            "headerText": header_text,
            "controllerId": controller_id,
            "lcpNumber": lcp_number,
            "hasExpansion": any(
                "expansion" in _norm(_row_text(grid[row])) or "board id" in _norm(_row_text(grid[row]))
                for row in rows
            ),
        })
    return preamble, groups


def _schedule_name(group: dict[str, Any]) -> str:
    header = _norm(group.get("headerText"))
    if "condenser" in header:
        return "Condenser Output Schedule"
    if "rack" in header:
        return "Rack Output Schedule"
    if any(word in header for word in ("lighting", "lcp", "contactor", "dimming")):
        return "Lighting Output Matrix"
    return "Controller Output Schedule"


def _controller_title(group: dict[str, Any], continued: bool) -> str:
    title = _schedule_name(group) + (" (Continued)" if continued else "")
    controller_id = str(group.get("controllerId") or "").strip()
    return f"{title} - Controller {controller_id}" if controller_id else title


def build_all_matrix_pages(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    ws = refresh_core._worksheet_by_name(candidate, "EMS 15.0 Lighting Output Matrix")
    base = refresh_core._candidate_page_by_code(candidate, "EMS 15.0")
    if base is None:
        raise MatrixRefreshError("Candidate EMS 15.0 page was not created.")

    preamble, groups = detect_all_controller_groups(ws)
    pages: list[dict[str, Any]] = []
    group_id = "page_sa31_15_0"
    for group_index, group in enumerate(groups):
        for group_part_index, group_rows in enumerate(splitter._pack_controller_group(ws, preamble, group)):
            page_index = len(pages)
            continued = page_index > 0
            rows = list(preamble) + list(group_rows)
            temp = splitter.slice_worksheet(
                ws,
                rows,
                new_id=f"{ws['id']}_matrix_{group_index}_{group_part_index}",
                new_name=ws.get("name") or "EMS 15.0 Lighting Output Matrix",
                title_text="LIGHTING OUTPUT MATRIX" if not continued else "LIGHTING OUTPUT MATRIX - CONTINUED",
            )
            block = splitter.build_excel_block(temp, f"{temp['id']}_xr")
            block.update({
                "sourceWorksheetId": ws["id"],
                "sourceSheet": ws.get("name", ""),
                "srcRows": rows,
                "splitMode": "none",
                "allowContinuation": False,
                "minScale": MIN_READABLE_SCALE,
                "maxScale": MAX_VISUAL_SCALE,
                "scaleMode": "fit_body",
                "pageFamily": "matrix",
                "layoutProfile": "io_table",
                "renderProfile": "singh360_standard_table",
                "bodyFontPx": SOURCE_BODY_FONT_PX,
                "noGrow": True,
            })
            code = "EMS 15.0" if page_index == 0 else continuation_code("EMS 15.0", page_index)
            page = refresh_core._clone_page_metadata(base)
            page.update({
                "id": group_id if page_index == 0 else f"{group_id}_c{page_index}",
                "order": 0,
                "include": True,
                "sheetCode": code,
                "displaySheetCode": code,
                "sheetTitle": _controller_title(group, continued),
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
                "minScale": MIN_READABLE_SCALE,
                "allowContinuation": False,
                "scaleMode": "fit_body",
                "linkedWorksheetId": ws["id"],
                "blocks": [block],
                "canvasObjects": [],
                "assets": [],
                "underlays": [],
                "notes": "" if not continued else f"Continued - Controller {group.get('controllerId') or group_index + 1}",
                "revisionRows": [],
                "pageGroupId": group_id,
                "continuationOf": None if page_index == 0 else group_id,
                "continuationIndex": page_index,
                "generatedContinuation": continued,
                "layoutWarnings": [],
                "matrixControllerId": group.get("controllerId"),
                "matrixControllerIndex": group_index,
                "matrixControllerPart": group_part_index,
            })
            pages.append(page)
    if not pages:
        raise MatrixRefreshError("EMS 15.0 pagination produced no output pages.")
    return pages


def matrix_pages(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        page for page in project.get("pages", [])
        if _norm(refresh_core._page_code(page)).startswith("ems 15.0") and page.get("include", True)
    ]


def verify_complete_matrix(project: dict[str, Any]) -> dict[str, Any]:
    ws = refresh_core._worksheet_by_name(project, "EMS 15.0 Lighting Output Matrix")
    preamble, groups = detect_all_controller_groups(ws)
    pages = matrix_pages(project)
    expected_parts = sum(len(splitter._pack_controller_group(ws, preamble, group)) for group in groups)
    if len(pages) != expected_parts:
        raise MatrixRefreshError(
            f"Lighting Output Matrix generated {len(pages)} page(s); {expected_parts} were expected."
        )
    all_text = " ".join(refresh_core._page_text(page) for page in pages).lower()
    missing = []
    for group in groups:
        controller_id = str(group.get("controllerId") or "").strip()
        token = f"controller id: {controller_id}".lower() if controller_id else _norm(group.get("headerText"))
        if token and token not in all_text:
            missing.append(controller_id or str(group.get("headerText") or "unknown"))
    if missing:
        raise MatrixRefreshError("Lighting Output Matrix lost controller group(s): " + ", ".join(missing))

    codes = [refresh_core._page_code(page) for page in pages]
    if len(codes) != len(set(codes)):
        raise MatrixRefreshError("Lighting Output Matrix continuation codes are not unique.")
    for index, page in enumerate(pages):
        block = (page.get("blocks") or [{}])[0]
        if float(block.get("minScale") or 0) < MIN_READABLE_SCALE:
            raise MatrixRefreshError(f"{refresh_core._page_code(page)} can shrink below the readable scale floor.")
        if int(block.get("bodyFontPx") or 0) < SOURCE_BODY_FONT_PX:
            raise MatrixRefreshError(f"{refresh_core._page_code(page)} uses body text smaller than 12px.")
        if index > 0:
            if "continued" not in _norm(page.get("sheetTitle")):
                raise MatrixRefreshError(f"{refresh_core._page_code(page)} is not labeled Continued.")
            grid = block.get("grid") or []
            first_cell = _norm(grid[0][0]) if grid and grid[0] else ""
            if "continued" not in first_cell:
                raise MatrixRefreshError(f"{refresh_core._page_code(page)} source heading is not labeled Continued.")
    return {
        "matrixPages": len(pages),
        "controllerGroups": len(groups),
        "controllerIds": [str(group.get("controllerId") or "") for group in groups],
        "codes": codes,
        "minScale": MIN_READABLE_SCALE,
        "bodyFontPx": SOURCE_BODY_FONT_PX,
    }


_ORIGINAL_VERIFY = refresh_core.verify_project


def verify_project_v2(project: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    result = _ORIGINAL_VERIFY(project, existing)
    result["completeOutputMatrix"] = verify_complete_matrix(project)
    return result


def install_generic_matrix_pagination() -> None:
    refresh_core._build_matrix_pages = build_all_matrix_pages
    refresh_core.verify_project = verify_project_v2


def apply_refresh(repo: Path, project_id: str, workbook: Path) -> dict[str, Any]:
    install_generic_matrix_pagination()
    patch_result = patch_renderer_sources(repo)
    for changed in patch_result.get("changed") or []:
        print(f"[OK] Patched permanent renderer source: {changed}")
    if not patch_result.get("changed"):
        print("[OK] Permanent renderer source patch was already installed.")
    result = refresh_core.apply_migration(repo, project_id, workbook)
    matrix = result["verification"]["completeOutputMatrix"]
    print(f"[OK] Output Matrix controller groups: {matrix['controllerGroups']}")
    print(f"[OK] Output Matrix pages: {matrix['matrixPages']}")
    print(f"[OK] Output Matrix codes: {', '.join(matrix['codes'])}")
    return result


def self_test() -> None:
    ncols = 12
    grid = [[""] * ncols for _ in range(38)]
    grid[0][0] = "LIGHTING OUTPUT MATRIX"
    headers = [
        (4, "LCP-1 LIGHTING PANEL - Controller ID: 601"),
        (12, "Expansion I/O Device - PR0663 - Board ID: 0"),
        (17, "LCP-2 CONTACTOR PANEL - Controller ID: 602"),
        (24, "REFRIGERATION RACK OUTPUT SCHEDULE - Controller ID: 701"),
        (31, "CONDENSER OUTPUT SCHEDULE - Controller ID: 801"),
    ]
    for row, text in headers:
        grid[row][0] = text
    for row in (5, 13, 18, 25, 32):
        grid[row][:4] = ["RO#", "Description", "Type", "DI#"]
    for row in range(6, 12):
        grid[row][:4] = [f"RO{row - 5}", f"Lighting output {row - 5}", "NO", str(row - 5)]
    for row in range(14, 17):
        grid[row][:4] = [str(row - 13), f"Expansion output {row - 13}", "", str(row - 13)]
    for row in range(19, 24):
        grid[row][:4] = [f"RO{row - 18}", f"Contactor output {row - 18}", "NO", str(row - 18)]
    for row in range(26, 31):
        grid[row][:4] = [f"RO{row - 25}", f"Rack output {row - 25}", "NO", str(row - 25)]
    for row in range(33, 38):
        grid[row][:4] = [f"RO{row - 32}", f"Condenser output {row - 32}", "NO", str(row - 32)]
    merged = [{"startRow": row, "endRow": row, "startCol": 0, "endCol": 11} for row, _ in headers]
    styles = {f"A{row + 1}": {"hAlign": "center", "fill": "#F4B400"} for row, _ in headers}
    ws = {
        "id": "ws_matrix",
        "name": "EMS 15.0 Lighting Output Matrix",
        "sourceRange": "A1:L38",
        "printArea": "A1:L38",
        "grid": grid,
        "formulas": [[""] * ncols for _ in grid],
        "styles": styles,
        "mergedCells": merged,
        "rowHeightsPx": [24] * len(grid),
        "manualPageBreaks": [],
    }
    candidate = {
        "worksheets": [ws],
        "pages": [{
            "id": "page_matrix",
            "order": 1,
            "include": True,
            "sheetCode": "EMS 15.0",
            "displaySheetCode": "EMS 15.0",
            "sheetTitle": "Lighting Output Matrix",
            "sheetTab": ws["name"],
            "pageType": "data-grid",
            "templateId": "ansi-b-standard",
            "blocks": [],
        }],
    }
    pages = build_all_matrix_pages(candidate)
    assert len(pages) == 4, len(pages)
    assert [page["displaySheetCode"] for page in pages] == ["EMS 15.0", "EMS 15.0a", "EMS 15.0b", "EMS 15.0c"]
    assert all("continued" in _norm(page["sheetTitle"]) for page in pages[1:])
    combined = " ".join(refresh_core._page_text(page) for page in pages).lower()
    for token in ("controller id: 601", "controller id: 602", "controller id: 701", "controller id: 801", "pr0663"):
        assert token in combined, token
    print("[OK] Generic four-controller matrix pagination self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--workbook", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        install_generic_matrix_pagination()
        self_test()
        return 0
    if not args.apply or not args.workbook:
        parser.error("--apply and --workbook are required unless --self-test is used.")
    apply_refresh(Path(args.repo).expanduser().resolve(), args.project, Path(args.workbook).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
