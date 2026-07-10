"""Smoke: page template save/list/insert round-trip (Phase F)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.page_template_store import PageTemplateStore


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = PageTemplateStore(tmp)
    problems: list[str] = []

    sample_page = {
        "id": "page_test",
        "order": 3,
        "include": True,
        "sheetCode": "EMS 12.0",
        "displaySheetCode": "EMS 12.0",
        "sheetTitle": "EMS Controls Overall Layout",
        "sheetTab": "Overall Layout",
        "pageType": "canvas",
        "layoutProfile": "",
        "templateId": "ansi-b-standard",
        "blocks": [{"id": "b1", "type": "paragraph", "text": "Layout notes"}],
        "canvasObjects": [{"type": "rect", "objName": "zone-a", "left": 50, "top": 60}],
        "notes": "",
    }

    entry = store.save_template(sample_page, "EMS Controls Overall Layout")
    tid = entry.get("id")
    if not tid:
        problems.append("save_template returned no id")

    listed = store.list_templates()
    if not any(t.get("id") == tid for t in listed):
        problems.append("template not in list")

    payload = store.get_template(tid)
    if payload is None:
        problems.append("get_template returned None")
    else:
        if payload.get("canvasObjects") != sample_page["canvasObjects"]:
            problems.append("canvasObjects round-trip mismatch")
        if payload.get("blocks") != sample_page["blocks"]:
            problems.append("blocks round-trip mismatch")
        if payload.get("sheetCode"):
            problems.append("sheetCode should be stripped from template payload")

    new_page = store.page_from_template(tid, order=5, sheet_code="NEW", sheet_title="From Template")
    if new_page is None:
        problems.append("page_from_template returned None")
    elif new_page.get("canvasObjects") != sample_page["canvasObjects"]:
        problems.append("inserted page canvasObjects mismatch")

    if not store.rename_template(tid, "Renamed Layout"):
        problems.append("rename failed")
    if not any(t.get("name") == "Renamed Layout" for t in store.list_templates()):
        problems.append("rename not reflected in list")

    if not store.delete_template(tid):
        problems.append("delete failed")
    if store.get_template(tid) is not None:
        problems.append("template still exists after delete")

    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — page template save/insert round-trip")


if __name__ == "__main__":
    main()
