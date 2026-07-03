"""scripts/smoke_project_consistency.py — validate a project's structural integrity.

Imports the SA31 workbook (path via arg or SINGH360_SA31_WORKBOOK) and asserts:
- unique page ids and orders
- pageNumber/pageTotal correct for included pages
- displaySheetCode present
- continuation pages linked to a base page
- no NaN/undefined scalars
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.validation import find_invalid_scalars
from core.workbook_importer import import_workbook


def main() -> int:
    wb = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SINGH360_SA31_WORKBOOK", "")
    if not wb:
        print("Usage: python scripts/smoke_project_consistency.py <workbook.xlsx>")
        print("   or set SINGH360_SA31_WORKBOOK")
        return 2
    if not Path(wb).exists():
        print(f"ERROR: workbook not found: {wb}")
        return 2

    p = import_workbook(wb, "consistency00001")
    pages = p.get("pages", [])
    problems: list[str] = []

    ids = [pg.get("id") for pg in pages]
    if len(ids) != len(set(ids)):
        problems.append("duplicate page ids")

    orders = [pg.get("order") for pg in pages]
    if len(orders) != len(set(orders)):
        problems.append("duplicate page orders")

    included = [pg for pg in pages if pg.get("include", True)]
    total = len(included)
    n = 0
    for pg in pages:
        if pg.get("include", True):
            n += 1
            if pg.get("pageNumber") != n:
                problems.append(f"pageNumber mismatch on {pg.get('id')}: {pg.get('pageNumber')} != {n}")
            if pg.get("pageTotal") != total:
                problems.append(f"pageTotal mismatch on {pg.get('id')}: {pg.get('pageTotal')} != {total}")
        if not pg.get("displaySheetCode"):
            problems.append(f"missing displaySheetCode on {pg.get('id')}")

    id_set = set(ids)
    for pg in pages:
        if pg.get("generatedContinuation"):
            base = pg.get("continuationOf")
            if base not in id_set and base not in {p2.get("pageGroupId") for p2 in pages}:
                problems.append(f"continuation {pg.get('id')} not linked to a base page")

    # Every page must carry a human title and a known internal page type.
    known_types = {"data-grid", "canvas", "underlay", "hybrid", "cover", "index"}
    for pg in pages:
        if not (pg.get("sheetTitle") or "").strip():
            problems.append(f"missing sheetTitle on {pg.get('id')}")
        if pg.get("pageType") not in known_types:
            problems.append(f"unknown pageType '{pg.get('pageType')}' on {pg.get('id')}")

    invalid = find_invalid_scalars(p)
    if invalid:
        problems.append(f"{len(invalid)} invalid scalar(s), first: {invalid[0]}")

    print(f"pages: {len(pages)} | included: {total} | continuation: {sum(1 for x in pages if x.get('generatedContinuation'))}")
    if problems:
        print("CONSISTENCY PROBLEMS:")
        for pr in problems[:40]:
            print(f"  - {pr}")
        return 1
    print("OK: project consistency checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
