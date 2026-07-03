from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


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


# Canonical equipment columns (header substring → field).
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "category": ("category",),
    "unitType": ("unit/type", "unit type", "type"),
    "name": ("name",),
    "connected": ("connected", "area served", "refrigerant", "number of racks"),
    "fixtureType": ("fixture type", "rack type", "suction temp", "make"),
    "controlType": ("control type",),
    "designTemp": ("design temperature", "set point", "design temp"),
}

# Category → canonical inventory page title.
_CATEGORY_PAGES: list[tuple[str, tuple[str, ...]]] = [
    ("Refrigeration Inventory", ("refrig", "rack", "case", "condenser", "compressor")),
    ("HVAC Inventory", ("hvac", "rtu", "ahu", "air handler", "mechanical")),
    ("Electrical Inventory", ("electrical", "panel", "relay", "contactor", "breaker")),
    ("Lighting Inventory", ("lighting", "fixture", "lamp")),
    ("EMS / RDM Equipment", ("ems", "rdm", "controller", "data manager", "network")),
]


def _col_index(headers: list[str], aliases: tuple[str, ...]) -> int:
    low = [h.strip().lower() for h in headers]
    for i, h in enumerate(low):
        if any(a in h for a in aliases):
            return i
    return -1


def parse_csv_structured(path: str | Path) -> dict[str, Any]:
    """Parse a CSV into headers + rows + structured equipment records."""
    grid = import_csv_to_grid(path)
    if not grid:
        return {"headers": [], "rows": [], "records": [], "categories": {}}

    headers = grid[0]
    body = grid[1:]
    idx = {field: _col_index(headers, aliases) for field, aliases in _FIELD_ALIASES.items()}

    def cell(row: list[str], i: int) -> str:
        return row[i].strip() if 0 <= i < len(row) else ""

    records: list[dict[str, str]] = []
    categories: dict[str, int] = {}
    for row in body:
        if not any(c.strip() for c in row):
            continue
        rec = {field: cell(row, i) for field, i in idx.items()}
        records.append(rec)
        cat = rec.get("category") or "(uncategorized)"
        categories[cat] = categories.get(cat, 0) + 1

    return {"headers": headers, "rows": body, "records": records, "categories": categories}


def _table_block(block_id: str, ws_id: str, headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    return {
        "id": block_id,
        "type": "table",
        "sourceWorksheetId": ws_id,
        "sourceRange": "",
        "headers": headers,
        "rows": rows,
        "styleRole": "table-header",
        "editable": True,
    }


def build_csv_worksheet_and_pages(
    path: str | Path, ws_id: str, source_id: str, filename: str, start_index: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a raw worksheet + structured output pages (Equipment Summary +
    per-category inventory pages) from a CSV. Blank values stay blank.
    """
    parsed = parse_csv_structured(path)
    headers = parsed["headers"]
    rows = parsed["rows"]

    worksheet = {
        "id": ws_id,
        "name": filename,
        "sourceId": source_id,
        "visible": True,
        "classHint": "csv",
        "grid": [headers] + rows if headers else rows,
        "formulas": {},
        "styles": {},
        "mergedCells": [],
        "rowHeights": {},
        "columnWidths": {},
        "provenance": {"sheet": filename},
    }

    pages: list[dict[str, Any]] = []

    def make_page(offset: int, title: str, table_rows: list[list[str]]) -> dict[str, Any]:
        pid = f"csvpage_{ws_id}_{offset}"
        return {
            "id": pid,
            "order": start_index + offset,
            "include": True,
            "sheetCode": f"C{offset + 1}",
            "displaySheetCode": f"C{offset + 1}",
            "sheetTitle": title,
            "sheetTab": filename,
            "pageType": "data-grid",
            "pageFamily": "table",
            "templateId": "ansi-b-standard",
            "linkedWorksheetId": ws_id,
            "blocks": [_table_block(f"{pid}_b", ws_id, headers, table_rows)],
            "canvasObjects": [],
            "assets": [],
            "underlays": [],
            "notes": "",
            "revisionRows": [],
            "pageGroupId": pid,
            "continuationOf": None,
            "continuationIndex": 0,
            "generatedContinuation": False,
            "layoutWarnings": [],
        }

    # Equipment Summary (all rows)
    pages.append(make_page(0, "Equipment Summary", rows))

    # Per-category inventory pages (only when a category matches known families).
    cat_idx = _col_index(headers, _FIELD_ALIASES["category"])
    if cat_idx >= 0:
        offset = 1
        for page_title, keys in _CATEGORY_PAGES:
            matched = [
                r for r in rows
                if cat_idx < len(r) and any(k in r[cat_idx].strip().lower() for k in keys)
            ]
            if matched:
                pages.append(make_page(offset, page_title, matched))
                offset += 1

    return worksheet, pages

