from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.vector_pdf_export import build_selected_export_document


def page(pid: str, order: int, kind: str = "canvas") -> dict:
    return {"id": pid, "order": order, "include": True, "pageType": kind, "sheetCode": f"EMS {order}.0", "displaySheetCode": f"EMS {order}.0", "sheetTitle": pid, "blocks": [], "canvasObjects": []}


def main() -> int:
    project = {"id": "selection", "pages": [page("cover", 1, "cover"), page("index", 2, "index"), page("drawing_a", 3), page("drawing_b", 4)], "worksheets": [], "sources": []}
    selected = build_selected_export_document(project, ["drawing_a", "drawing_b"])
    included = [p["id"] for p in selected["pages"] if p.get("include", True)]
    assert included == ["drawing_a", "drawing_b"], included
    assert [p.get("pageNumber") for p in selected["pages"] if p.get("include", True)] == [1, 2]
    assert all(p.get("pageTotal") == 2 for p in selected["pages"] if p.get("include", True))
    print(json.dumps({"ok": True, "included": included, "pageCount": len(included)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
