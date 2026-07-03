from __future__ import annotations

import csv
from pathlib import Path


def import_csv_to_grid(path: str | Path) -> list[list[str]]:
    csv_path = Path(path)
    rows: list[list[str]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append([str(cell or "") for cell in row])
    while rows and not any(rows[-1]):
        rows.pop()
    return rows
