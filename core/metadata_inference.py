"""Infer Singh360 project metadata from labeled worksheet rows.

The standard workbook uses:
    Project Name | : | actual value
The punctuation cell is a display separator and must never become metadata.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

METADATA_LABEL_MAP: dict[str, str] = {
    "project name": "projectName",
    "project": "projectName",
    "store name": "storeNumber",
    "store number": "storeNumber",
    "drawing package file name": "drawingPackageFileName",
    "package": "drawingPackageFileName",
    "location": "location",
    "address": "location",
    "revision": "revision",
    "rev": "revision",
    "issue date": "issueDate",
    "drawn by": "drawnBy",
    "checked by": "checkedBy",
    "prepared for": "client",
    "client": "client",
    "purpose": "purpose",
    "status": "status",
}

_ONLY_PUNCTUATION = re.compile(r"^[\s:;,.|/\\\-–—_•·]+$")
_ISO_MIDNIGHT = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T]00:00:00(?:\.0+)?$")
_US_MIDNIGHT = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})[ T]00:00:00(?:\.0+)?$")


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    text = " ".join(str(value).replace("\u00a0", " ").split()).strip()
    if text.lower() in {"", "none", "nan", "nat", "<na>"}:
        return ""
    return text


def _label(value: Any) -> str:
    return re.sub(r"[:\s]+$", "", _as_text(value).lower())


def _value(value: Any) -> str:
    text = _as_text(value)
    if not text or _ONLY_PUNCTUATION.fullmatch(text):
        return ""
    return text if re.search(r"[A-Za-z0-9]", text) else ""


def _normalize_issue_date(value: str) -> str:
    value = value.strip()
    match = _ISO_MIDNIGHT.fullmatch(value)
    if match:
        return match.group(1)
    match = _US_MIDNIGHT.fullmatch(value)
    if match:
        return match.group(1)
    try:
        serial = float(value)
        if 20000 <= serial <= 80000:
            return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    return value


def infer_metadata_from_labeled_grid(ws: dict[str, Any] | None) -> dict[str, str]:
    """Find the first real value after a recognized label.

    Blank cells and punctuation-only separators such as ":" are skipped.
    """
    if not ws:
        return {}

    out: dict[str, str] = {}
    for row in ws.get("grid") or []:
        cells = list(row or [])
        for index, raw in enumerate(cells):
            field = METADATA_LABEL_MAP.get(_label(raw))
            if not field or out.get(field):
                continue

            for cursor in range(index + 1, min(len(cells), index + 13)):
                if METADATA_LABEL_MAP.get(_label(cells[cursor])):
                    break
                candidate = _value(cells[cursor])
                if not candidate:
                    continue
                if field == "issueDate":
                    candidate = _normalize_issue_date(candidate)
                out[field] = candidate
                break

    return out
