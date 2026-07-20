"""Apply the newest SA31 workbook with resilient panel-page recovery.

The SA31 workbook can contain the EMS 16.0 and EMS 16.1 worksheets while the
00_INDEX/import profile omits their candidate output pages. The prior complete
matrix refresh assumed a candidate EMS 16.0 page already existed and stopped
before saving the project. This entry point builds both panel pages directly
from their worksheets when necessary, then runs the controller-safe matrix
refresh and complete in-place workbook migration.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_sa31_updated_workbook import patch_renderer_sources
import scripts.apply_sa31_complete_matrix_refresh as matrix_refresh
import scripts.fix_lcp_panel_schedule_project as splitter
import scripts.sa31_refresh_core as refresh_core

DEFAULT_PROJECT_ID = refresh_core.DEFAULT_PROJECT_ID
PANEL_MIN_SCALE = 0.68
PANEL_BODY_FONT_PX = 12


class PanelRecoveryError(refresh_core.MigrationError):
    pass


def _fallback_page_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return harmless page metadata when the index omitted EMS 16.x pages."""
    for code in ("EMS 16.0", "EMS 16.1", "EMS 15.1", "EMS 17.0", "EMS 15.0"):
        page = refresh_core._candidate_page_by_code(candidate, code)
        if page is not None:
            return refresh_core._clone_page_metadata(page)

    pages = candidate.get("pages") or []
    if pages:
        return refresh_core._clone_page_metadata(pages[0])

    return {
        "templateId": "ansi-b-standard",
        "orientation": "landscape",
        "pageType": "data-grid",
        "renderMode": "excel_exact",
        "renderProfile": "singh360_standard_table",
    }


def _shared_panel_widths(block1: dict[str, Any], block2: dict[str, Any]) -> list[int]:
    widths1 = list(block1.get("colWidths") or [])
    widths2 = list(block2.get("colWidths") or [])
    width_count = max(len(widths1), len(widths2))
    if width_count == 0:
        return []

    raw: list[int] = []
    for col in range(width_count):
        raw.append(max(
            widths1[col] if col < len(widths1) else 0,
            widths2[col] if col < len(widths2) else 0,
            48,
        ))

    total = sum(raw) or 1
    scaled = [max(48, int(round(width * 1480 / total))) for width in raw]
    if scaled:
        scaled[-1] += 1480 - sum(scaled)
    return scaled


def build_panel_pages_resilient(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Build EMS 16.0/16.1 directly from worksheets, with one visual scale.

    This function intentionally does not require the workbook importer to have
    created an EMS 16.0 candidate page. The worksheets are the source of truth.
    """
    ws1 = refresh_core._worksheet_by_name(candidate, "EMS 16.0 LCP-1 Panel Schedule")
    ws2 = refresh_core._worksheet_by_name(candidate, "EMS 16.1 LCP-2 Panel Schedule")

    block1 = splitter.build_excel_block(ws1, f"{ws1['id']}_xr")
    block2 = splitter.build_excel_block(ws2, f"{ws2['id']}_xr")
    shared_widths = _shared_panel_widths(block1, block2)

    for block in (block1, block2):
        block.update({
            "colWidths": list(shared_widths),
            "splitMode": "none",
            "allowContinuation": False,
            "scaleMode": "fit_body",
            "pageFamily": "panelDetail",
            "layoutProfile": "io_table",
            "renderProfile": "singh360_standard_table",
            "bodyFontPx": PANEL_BODY_FONT_PX,
            "minScale": PANEL_MIN_SCALE,
            "noGrow": True,
        })

    natural_width = max(sum(shared_widths), 1)
    natural_height = max(
        sum(block1.get("rowHeights") or []),
        sum(block2.get("rowHeights") or []),
        1,
    )
    common_scale = min(1.0, 1578.0 / natural_width, 596.0 / natural_height)
    common_scale = max(0.42, min(1.0, common_scale))
    block1["maxScale"] = round(common_scale, 4)
    block2["maxScale"] = round(common_scale, 4)

    base = _fallback_page_metadata(candidate)
    pages: list[dict[str, Any]] = []
    definitions = (
        (
            ws1,
            block1,
            "EMS 16.0",
            "LCP-1 Dimming Panel & Expansion I/O",
            "page_sa31_16_0",
        ),
        (
            ws2,
            block2,
            "EMS 16.1",
            "LCP-2 Contactor Panel",
            "page_sa31_16_1",
        ),
    )

    for ws, block, code, title, page_id in definitions:
        page = copy.deepcopy(base)
        page.update({
            "id": page_id,
            "order": 0,
            "include": True,
            "sheetCode": code,
            "displaySheetCode": code,
            "sheetTitle": title,
            "sheetTab": ws.get("name", ""),
            "pageType": "data-grid",
            "pageFamily": "panelDetail",
            "layoutProfile": "io_table",
            "renderMode": "excel_exact",
            "renderProfile": "singh360_standard_table",
            "sourceSheet": ws.get("name", ""),
            "sourceRange": ws.get("sourceRange", ""),
            "printArea": ws.get("printArea"),
            "splitMode": "none",
            "repeatRows": block.get("repeatRows", []),
            "minScale": PANEL_MIN_SCALE,
            "allowContinuation": False,
            "scaleMode": "fit_body",
            "linkedWorksheetId": ws["id"],
            "blocks": [block],
            "canvasObjects": [],
            "assets": [],
            "underlays": [],
            "notes": "",
            "revisionRows": [],
            "pageGroupId": page_id,
            "continuationOf": None,
            "continuationIndex": 0,
            "generatedContinuation": False,
            "layoutWarnings": [],
        })
        pages.append(page)

    text1 = refresh_core._page_text(pages[0]).lower()
    text2 = refresh_core._page_text(pages[1]).lower()
    if "controller id: 601" not in text1 or "pr0663" not in text1:
        raise PanelRecoveryError("EMS 16.0 lost Controller 601 or its PR0663 expansion section.")
    if "controller id: 602" in text1:
        raise PanelRecoveryError("EMS 16.0 incorrectly contains Controller 602.")
    if "controller id: 602" not in text2 or "controller id: 601" in text2:
        raise PanelRecoveryError("EMS 16.1 controller-content validation failed.")
    if block1.get("maxScale") != block2.get("maxScale"):
        raise PanelRecoveryError("EMS 16.0 and EMS 16.1 do not share one scale ceiling.")
    return pages


def install_recovery() -> None:
    matrix_refresh.install_generic_matrix_pagination()
    refresh_core._build_panel_pages = build_panel_pages_resilient


def verify_saved_panels(project: dict[str, Any]) -> dict[str, Any]:
    pages = [page for page in project.get("pages", []) if page.get("include", True)]
    p16 = next((page for page in pages if refresh_core._norm(refresh_core._page_code(page)) == "ems 16.0"), None)
    p161 = next((page for page in pages if refresh_core._norm(refresh_core._page_code(page)) == "ems 16.1"), None)
    if p16 is None or p161 is None:
        raise PanelRecoveryError("The saved project is still missing EMS 16.0 or EMS 16.1.")

    text16 = refresh_core._page_text(p16).lower()
    text161 = refresh_core._page_text(p161).lower()
    if "controller id: 601" not in text16 or "pr0663" not in text16 or "controller id: 602" in text16:
        raise PanelRecoveryError("Saved EMS 16.0 verification failed.")
    if "controller id: 602" not in text161 or "controller id: 601" in text161:
        raise PanelRecoveryError("Saved EMS 16.1 verification failed.")

    block16 = (p16.get("blocks") or [{}])[0]
    block161 = (p161.get("blocks") or [{}])[0]
    scale16 = float(block16.get("maxScale") or 0)
    scale161 = float(block161.get("maxScale") or 0)
    if not scale16 or abs(scale16 - scale161) > 0.0001:
        raise PanelRecoveryError("Saved EMS 16.0/16.1 scale verification failed.")
    return {
        "EMS16": p16.get("sheetTitle"),
        "EMS16.1": p161.get("sheetTitle"),
        "commonScale": scale16,
    }


def apply_refresh(repo: Path, project_id: str, workbook: Path) -> dict[str, Any]:
    install_recovery()
    patch_result = patch_renderer_sources(repo)
    for changed in patch_result.get("changed") or []:
        print(f"[OK] Patched permanent renderer source: {changed}")
    if not patch_result.get("changed"):
        print("[OK] Permanent renderer source patch was already installed.")

    result = refresh_core.apply_migration(repo, project_id, workbook)

    from core.project_store import ProjectStore

    saved = ProjectStore(repo / ".docs").load(project_id)
    if saved is None:
        raise PanelRecoveryError("The repaired project could not be reloaded after saving.")
    panel_verification = verify_saved_panels(saved)
    matrix_verification = matrix_refresh.verify_complete_matrix(saved)
    print(f"[OK] Saved panel verification: {panel_verification}")
    print(f"[OK] Saved matrix verification: {matrix_verification}")
    result["panelVerification"] = panel_verification
    result["matrixVerification"] = matrix_verification
    return result


def self_test() -> None:
    def worksheet(worksheet_id: str, name: str, controller: str, *, expansion: bool) -> dict[str, Any]:
        grid = [[""] * 12 for _ in range(20 if expansion else 13)]
        grid[0][0] = name.upper()
        grid[4][0] = f"{name} - Controller ID: {controller}"
        grid[5][:6] = ["RO#", "Relay Output Description", "Type", "DI#", "Status Input", "Type"]
        for row in range(6, 12):
            grid[row][:4] = [f"RO{row - 5}", f"Output {row - 5}", "NO", str(row - 5)]
        if expansion:
            grid[13][0] = "Expansion I/O Device - PR0663 - Board ID: 0"
            grid[14][:6] = ["RO#", "Relay Output Description", "Type", "DI#", "Status Input", "Type"]
            for row in range(15, 20):
                grid[row][:4] = [str(row - 14), f"Expansion {row - 14}", "", str(row - 14)]
        merges = [
            {"startRow": 0, "endRow": 0, "startCol": 0, "endCol": 11},
            {"startRow": 4, "endRow": 4, "startCol": 0, "endCol": 11},
        ]
        if expansion:
            merges.append({"startRow": 13, "endRow": 13, "startCol": 0, "endCol": 11})
        return {
            "id": worksheet_id,
            "name": name,
            "sourceSheet": name,
            "grid": grid,
            "styles": {},
            "mergedCells": merges,
            "rowHeightsPx": [24] * len(grid),
            "sourceRange": f"A1:L{len(grid)}",
            "printArea": f"A1:L{len(grid)}",
        }

    candidate = {
        "pages": [
            {
                "id": "fallback_15_1",
                "sheetCode": "EMS 15.1",
                "displaySheetCode": "EMS 15.1",
                "sheetTitle": "Lighting Schedule",
                "sheetTab": "EMS 15.1 Lighting Schedule",
                "pageType": "data-grid",
                "templateId": "ansi-b-standard",
                "blocks": [],
            },
            {
                "id": "fallback_17",
                "sheetCode": "EMS 17.0",
                "displaySheetCode": "EMS 17.0",
                "sheetTitle": "Field Instructions",
                "sheetTab": "EMS 17.0 Field Instructions",
                "pageType": "data-grid",
                "templateId": "ansi-b-standard",
                "blocks": [],
            },
        ],
        "worksheets": [
            worksheet("ws16", "EMS 16.0 LCP-1 Panel Schedule", "601", expansion=True),
            worksheet("ws161", "EMS 16.1 LCP-2 Panel Schedule", "602", expansion=False),
        ],
    }

    pages = build_panel_pages_resilient(candidate)
    assert [page["displaySheetCode"] for page in pages] == ["EMS 16.0", "EMS 16.1"]
    assert "controller id: 601" in refresh_core._page_text(pages[0]).lower()
    assert "pr0663" in refresh_core._page_text(pages[0]).lower()
    assert "controller id: 602" in refresh_core._page_text(pages[1]).lower()
    assert (pages[0]["blocks"][0]["maxScale"] == pages[1]["blocks"][0]["maxScale"])
    print("[OK] Missing-candidate EMS 16.0/16.1 recovery self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--workbook", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.apply or not args.workbook:
        parser.error("Choose --apply and provide --workbook")

    apply_refresh(
        Path(args.repo).expanduser().resolve(),
        args.project,
        Path(args.workbook).expanduser().resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
