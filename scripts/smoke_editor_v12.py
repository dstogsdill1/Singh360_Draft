from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.table_layout_profiles import preferred_named_col_widths, profile_nowrap_columns


def main() -> int:
    cable = [
        ["Marker", "Circuit / Tag", "Cable Type", "From", "To", "Purpose / Device", "Cable Standard", "Installed By", "Notes"],
        ["10", "IDF-MDF", "Fiber", "RDM IDF", "H-E-B MDF", "Network uplink", "By H-E-B EM direction", "H-E-B EM / EC-Comm", "Priority 1"],
    ]
    widths = preferred_named_col_widths(cable, "cable_termination_schedule")
    assert widths and widths[5] > widths[1]
    nowrap = profile_nowrap_columns(cable, "cable_termination_schedule")
    assert 7 not in nowrap, 'Installed By must wrap on EMS 13.0'
    assert 2 not in nowrap, 'Cable Type must wrap; generic Type handling must not override the cable profile'
    assert 8 not in nowrap, 'Notes must wrap; generic No handling must not treat Notes as a technical number column'

    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    raw = (ROOT / "frontend/src/components/renderers/RawGridRenderer.tsx").read_text(encoding="utf-8")
    excel = (ROOT / "frontend/src/model/excelRange.ts").read_text(encoding="utf-8")
    cleanup = (ROOT / "frontend/src/model/canvasCleanup.ts").read_text(encoding="utf-8")
    preview = (ROOT / "frontend/src/components/SourceLivePreview.tsx").read_text(encoding="utf-8")

    assert "Done - Apply & Preview" in raw
    assert "Page Preview" in raw
    assert "gx-tool-menu" in raw
    assert "geometryComesFromSource" in excel
    assert "maxDimension <= 42" in cleanup
    assert "Clean Hidden Artifacts" in app
    assert "same normalized/PDF layout engine" in preview
    print("OK: V12.1 editor and cover cleanup smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
