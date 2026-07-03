from __future__ import annotations

from typing import Any


def ansi_b_sheet_template(metadata: dict[str, Any], page: dict[str, Any], page_number: int | None, page_total: int) -> dict[str, Any]:
    return {
        "sheet": {"width": 1632, "height": 1056, "unit": "px"},
        "frames": {
            "outer": {"x": 8, "y": 8, "width": 1616, "height": 1040, "stroke": "#111", "strokeWidth": 2},
            "inner": {"x": 16, "y": 16, "width": 1600, "height": 1024, "stroke": "#222", "strokeWidth": 1},
            "body": {"x": 16, "y": 16, "width": 1600, "height": 880},
            "titleBlock": {"x": 16, "y": 896, "width": 1600, "height": 144},
        },
        "titleBlock": {
            "firm": "SINGH360 INC.",
            "project": metadata.get("projectName", ""),
            "creator": metadata.get("createdBy", ""),
            "file": metadata.get("sourceFile", ""),
            "created": metadata.get("createdDate", ""),
            "version": metadata.get("version", ""),
            "date": metadata.get("date", ""),
            "editedBy": metadata.get("editedBy", ""),
            "notes": page.get("notes", ""),
            "sheetCode": page.get("sheetCode", ""),
            "sheetTitle": page.get("sheetTitle", ""),
            "pageDisplay": f"Page {page_number} of {page_total}" if page_number else f"Page - of {page_total}",
        },
    }
