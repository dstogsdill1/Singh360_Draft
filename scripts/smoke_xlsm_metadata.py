"""Verify colon-separated metadata and a real SA31 V2 XLSM when available."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.metadata_inference import infer_metadata_from_labeled_grid

EXPECTED = {
    "projectName": "SA31 - (102) Light-Dimming / EMS Integration",
    "drawingPackageFileName": "SA31_102 Light Dimming & EMS Integration",
    "location": "8503 NW Military Highway, San Antonio, TX 78231",
    "revision": "V1",
    "issueDate": "2026-07-18",
    "drawnBy": "DS",
}


def synthetic_test() -> None:
    worksheet = {
        "grid": [
            ["Project Name", ":", EXPECTED["projectName"]],
            ["Drawing Package File Name", ":", EXPECTED["drawingPackageFileName"]],
            ["Location", ":", EXPECTED["location"]],
            ["Revision", ":", EXPECTED["revision"]],
            ["Issue Date", ":", "2026-07-18 00:00:00"],
            ["Drawn By", ":", EXPECTED["drawnBy"]],
        ]
    }
    actual = infer_metadata_from_labeled_grid(worksheet)
    assert actual == EXPECTED, actual
    print("[OK] Synthetic colon-separated metadata")


def find_workbook() -> Path | None:
    roots = [
        ROOT,
        ROOT.parent,
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.home() / "OneDrive - Homeland Development Services LLC" / "Desktop",
    ]
    matches: list[Path] = []
    for folder in roots:
        if folder.is_dir():
            matches.extend(folder.glob("SA31_EMS_Lighting_Workbook_V2*.xlsm"))
    if not matches:
        return None
    return max({path.resolve() for path in matches}, key=lambda path: (path.stat().st_size, path.stat().st_mtime))


def real_workbook_test() -> None:
    workbook = find_workbook()
    if workbook is None:
        print("[NOTE] Real SA31 V2 XLSM not found in normal folders; synthetic test passed.")
        return

    from core.workbook_importer import import_workbook

    project = import_workbook(workbook, project_id="metadata_smoke")
    metadata = project.get("metadata") or {}
    for field, expected in EXPECTED.items():
        assert metadata.get(field) == expected, (field, metadata)
    assert all(value not in {":", ".", "-", "—"} for value in metadata.values())
    print(f"[OK] Real XLSM metadata: {workbook}")
    for field in EXPECTED:
        print(f"     {field}: {metadata.get(field)}")


if __name__ == "__main__":
    synthetic_test()
    real_workbook_test()
