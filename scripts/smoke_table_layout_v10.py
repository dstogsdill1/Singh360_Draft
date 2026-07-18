"""Regression smoke for Singh360 table layouts after the V11 readability upgrade."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.table_layout_profiles import (
    infer_named_layout_profile,
    preferred_named_col_widths,
    profile_body_font_px,
    profile_min_scale,
)
from core.workbook_importer import _layout_profile_for, _preferred_col_widths


def main() -> int:
    equipment = [
        ["Qty", "Item / Part No.", "Description", "Scope / Use", "Supplied By", "Installed By", "Destination / Location", "Notes"],
        ["1", "PR0650CD-TDB", "RDM programmable controller", "Primary RDM controller hardware", "Singh360", "EC-Elec", "LCP-1", "Verify controller ID"],
    ]
    cable = [
        ["Marker", "Circuit / Tag", "Cable Type", "From", "To", "Purpose / Device", "Cable Standard", "Installed By", "Notes"],
        ["1", "D1", "manufacturer approved equivalent", "LCP-1 Module 1", "Sales Floor", "Dimming Zone 1", "manufacturer approved equivalent", "DC", "VERIFY final zone name"],
    ]

    assert infer_named_layout_profile("table", "data-grid", "Equipment Supply Schedule") == "equipment_supply_schedule"
    assert infer_named_layout_profile("table", "data-grid", "Cable Pull / Termination Schedule") == "cable_termination_schedule"
    assert _layout_profile_for("matrix", "data-grid", "Responsibility Matrix") == "responsibility_matrix"

    equipment_widths = preferred_named_col_widths(equipment, "equipment_supply_schedule")
    cable_widths = preferred_named_col_widths(cable, "cable_termination_schedule")
    assert equipment_widths and len(equipment_widths) == 8
    assert cable_widths and len(cable_widths) == 9
    assert 1400 <= sum(equipment_widths) <= 1550
    assert 1400 <= sum(cable_widths) <= 1550
    assert equipment_widths[0] < equipment_widths[3]
    assert cable_widths[0] < cable_widths[5]

    imported = _preferred_col_widths(
        equipment,
        "table",
        "data-grid",
        "equipment_supply_schedule",
    )
    assert imported == equipment_widths
    assert profile_body_font_px("equipment_supply_schedule") == 12
    assert profile_min_scale("equipment_supply_schedule") == 0.80

    frontend = (ROOT / "frontend/src/model/excelRange.ts").read_text(encoding="utf-8")
    rebuild = (ROOT / "frontend/src/model/pageRebuild.ts").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/sheet.css").read_text(encoding="utf-8")
    assert "reflowExcelRangeBlock" in frontend
    assert "reflowExcelRangeBlock" in rebuild
    assert "S360 TABLE CENTERING V10" in css

    print("OK: named table profiles, readable V11 schedule fonts, rebuild parity, and centering are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
