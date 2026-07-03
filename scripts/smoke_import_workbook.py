from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.validation import validate_project
from core.workbook_importer import import_workbook


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: python scripts/smoke_import_workbook.py "C:\\path\\to\\workbook.xlsx"')
        return 2

    workbook = Path(sys.argv[1]).expanduser()
    print(f"workbook path: {workbook}")

    if not workbook.exists():
        print("ERROR: workbook not found")
        return 2

    project = import_workbook(workbook, project_id="smokeimport000001")
    errors = validate_project(project)

    pages = project.get("pages", [])
    worksheets = project.get("worksheets", [])

    print(f"pages count: {len(pages)}")
    print(f"worksheets count: {len(worksheets)}")
    print(f"validation errors: {len(errors)}")
    if errors:
        for e in errors[:50]:
            print(f"  - {e}")

    print("first 15 pages:")
    for p in pages[:15]:
        print(
            f"  sheetCode={p.get('sheetCode', '')} | "
            f"sheetTitle={p.get('sheetTitle', '')} | "
            f"pageType={p.get('pageType', '')} | "
            f"include={p.get('include', True)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
