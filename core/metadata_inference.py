"""Infer project metadata from labeled key/value cells in a worksheet grid.

Shared by workbook import and cover source rebuild paths. Mirrors the SA31-style
cover layout: label/value pairs across a row (e.g. Project / Store Name /
Address / Package / Revision / Prepared For / Prepared By).
"""
from __future__ import annotations

from typing import Any

METADATA_LABEL_MAP: dict[str, str] = {
    "project name": "projectName",
    "project": "projectName",
    "store name": "storeNumber",
    "drawing package file name": "drawingPackageFileName",
    "package": "drawingPackageFileName",
    "location": "location",
    "address": "location",
    "revision": "revision",
    "rev": "revision",
    "issue date": "issueDate",
    "drawn by": "drawnBy",
    "prepared by": "drawnBy",
    "checked by": "checkedBy",
    "prepared for": "client",
    "client": "client",
    "purpose": "purpose",
    "status": "status",
}


def infer_metadata_from_labeled_grid(ws: dict[str, Any] | None) -> dict[str, str]:
    """Infer title-block metadata from adjacent label/value cell pairs.

    Never invents a value: only a recognized label with a non-blank adjacent
    value is used. First occurrence wins per metadata field.
    """
    if not ws:
        return {}
    grid = ws.get("grid") or []
    out: dict[str, str] = {}
    for row in grid:
        for i in range(len(row) - 1):
            label = (row[i] or "").strip().lower().rstrip(":")
            field = METADATA_LABEL_MAP.get(label)
            if not field:
                continue
            value = (row[i + 1] or "").strip()
            if value and not out.get(field):
                out[field] = value
    return out
