"""Regression tests for integer import display and project cleanup."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.source_number_cleanup import clean_integer_columns_in_grid
from core.workbook_importer import _display_cell_value


def main() -> int:
    assert _display_cell_value(1.0, "General") == "1"
    assert _display_cell_value(2.0, "0") == "2"
    assert _display_cell_value(1.0, "0.0") == "1.0"
    assert _display_cell_value(1.25, "General") == "1.25"
    assert _display_cell_value("EMS 1.0", "General") == "EMS 1.0"

    grid = [
        ["Port", "Device", "Voltage"],
        ["1.0", "DM00", "120.0"],
        ["2.0", "DM01", "208.0"],
    ]
    cleaned, count = clean_integer_columns_in_grid(grid)
    assert count == 2, (count, cleaned)
    assert cleaned[1][0] == "1"
    assert cleaned[2][0] == "2"
    assert cleaned[1][2] == "120.0"
    assert cleaned[2][2] == "208.0"

    quantity = [
        ["Qty", "Part No."],
        ["5.0", "100-4004"],
        ["1.0", "PR0663"],
    ]
    cleaned_qty, qty_count = clean_integer_columns_in_grid(quantity)
    assert qty_count == 2
    assert [row[0] for row in cleaned_qty[1:]] == ["5", "1"]

    print("[OK] Source-number import and integer-column cleanup regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
