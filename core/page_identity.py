"""Shared predicates for workbook-controlled page identities."""
from __future__ import annotations

import re
from typing import Any, Mapping


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def is_sheet_index_page(page: Mapping[str, Any]) -> bool:
    """Return whether *page* is the published Sheet Index / TOC.

    Workbooks in the field use several spellings for Page Type, and some older
    controlled rows identify the index only through EMS 2.0 plus its tab/title.
    Keep this logic in one place so import, pagination, sync, render, and
    verification cannot disagree.
    """
    page_type = _key(page.get("pageType") or page.get("page_type"))
    if page_type in {"index", "sheetindex"}:
        return True

    code = _key(page.get("sheetCode") or page.get("displaySheetCode"))
    text = " ".join(
        str(page.get(name) or "").casefold()
        for name in ("sheetTab", "sheetTitle", "pageFamily", "title", "tab")
    )
    return code.startswith("ems20") and (
        "sheet index" in text
        or "toc" in text
        or _key(page.get("pageFamily")) in {"index", "sheetindex"}
    )
