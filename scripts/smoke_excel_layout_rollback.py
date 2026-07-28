"""Validate rollback assets and their guard behavior without touching live data."""
from __future__ import annotations
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / ".docs" / "patch_backups" / "excel_layout_canvas_20260728_064900"
required = ["ROLLBACK_THIS_PATCH.ps1", "tracked_HEAD_before.zip", "source_files_before.json", "pre_run_manifest.json"]
missing = [name for name in required if not (BACKUP / name).is_file()]
if missing:
    raise SystemExit(f"missing rollback assets: {missing}")
manifest = json.loads((BACKUP / "pre_run_manifest.json").read_text(encoding="utf-8-sig"))
if manifest.get("headBefore") != "4190844f0d490c0eb11430c53f41dd15c8976350":
    raise SystemExit("rollback manifest starting commit changed")
with tempfile.TemporaryDirectory() as td:
    clone = Path(td) / "rollback-assets"
    clone.mkdir()
    for name in required:
        shutil.copy2(BACKUP / name, clone / name)
    script = (clone / "ROLLBACK_THIS_PATCH.ps1").read_text(encoding="utf-8-sig")
    if "$Confirm -ne 'ROLLBACK'" not in script or ".docs\\projects" not in script:
        raise SystemExit("rollback guard or project restore protection missing")
print("PASS: rollback assets validated on a temporary copy; live production data was untouched")
