"""Smoke: cover source rebuild updates metadata and normalized cover block rows."""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.metadata_inference import infer_metadata_from_labeled_grid
from core.page_normalizer import _row_line

NEW_PROJECT = "829 Mi Tienda EMS"
NEW_ADDRESS = "7140 Southwest Fwy, Houston, TX 77036"


def _cover_grid() -> list[list[str]]:
    return [
        ["LIGHT DIMMING & EMS INTEGRATION"],
        ["SINGH360 EMS CONTROLS WORKBOOK"],
        ["Project", "Old Project Name", "Store Name", "Old Store"],
        ["Address", "Old Address", "Package", "OLD_PKG"],
        ["Revision", "V0", "Prepared For", "Old Client"],
        ["Prepared By", "Old Author", "Purpose", "Integration"],
        ["Status", "Draft", "Issue Date", "2026-01-01"],
        ["Drawing Package File Name", "OLD_PKG", "Location", "Old City"],
    ]


def _edited_grid() -> list[list[str]]:
    g = _cover_grid()
    g[2][1] = NEW_PROJECT
    g[3][1] = NEW_ADDRESS
    g[3][3] = "SA829_EMS_V2"
    g[4][1] = "V2"
    return g


def _rebuild_cover_block(grid: list[list[str]]) -> list[list[str]]:
    lines = [_row_line(r) for r in grid if _row_line(r)]
    return [[ln] for ln in lines]


def main() -> int:
    problems: list[str] = []
    ws = {"grid": _edited_grid()}
    meta = infer_metadata_from_labeled_grid(ws)

    if meta.get("projectName") != NEW_PROJECT:
        problems.append(f"projectName={meta.get('projectName')!r}, expected {NEW_PROJECT!r}")
    if meta.get("location") != NEW_ADDRESS:
        problems.append(f"location={meta.get('location')!r}, expected {NEW_ADDRESS!r}")
    if meta.get("drawingPackageFileName") != "SA829_EMS_V2":
        problems.append(f"drawingPackageFileName={meta.get('drawingPackageFileName')!r}")
    if meta.get("revision") != "V2":
        problems.append(f"revision={meta.get('revision')!r}")

    rows = _rebuild_cover_block(ws["grid"])
    flat = "\n".join(r[0] for r in rows)
    if NEW_PROJECT not in flat:
        problems.append("rebuilt cover block missing updated project name")
    if NEW_ADDRESS not in flat:
        problems.append("rebuilt cover block missing updated address")

    # Cover metadata should overwrite stale project metadata (cover is truth).
    project = {
        "metadata": {
            "projectName": "Old Project Name",
            "location": "Old Address",
            "drawingPackageFileName": "OLD_PKG",
            "revision": "V0",
        }
    }
    project["metadata"].update({k: v for k, v in meta.items() if v})
    if project["metadata"]["projectName"] != NEW_PROJECT:
        problems.append("metadata merge did not overwrite projectName")

    if problems:
        print("FAIL — cover source rebuild")
        for p in problems:
            print(" -", p)
        return 1

    print("OK — cover source rebuild (metadata + normalized rows)")
    print(f"  projectName={NEW_PROJECT!r} location={NEW_ADDRESS!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
