"""core/page_normalizer.py — worksheet → normalized output page blocks.

Analyzes a linked worksheet payload (grid + style hints) and produces a list of
normalized page "blocks" that the frontend renders as professional drawing
pages. Text is preserved verbatim — only presentation is normalized. Nothing is
invented; unknown/empty content simply yields fewer blocks.
"""
from __future__ import annotations

import re
from typing import Any

from openpyxl.utils.cell import get_column_letter

_IMAGE_EXT_RE = re.compile(r"\.(png|jpe?g|gif|bmp|webp|svg|pdf|vsdx?|dwg)\b", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*([-*•▪◦]|\d+[.)]|[a-z][.)])\s+", re.IGNORECASE)
_MARK_VALUES = {"x", "✓", "✔", "●", "•", "√", "yes", "y", "◼", "■"}


def _col_letter(c0: int) -> str:
    return get_column_letter(c0 + 1)


def _range(r0: int, c0: int, r1: int, c1: int) -> str:
    return f"{_col_letter(c0)}{r0 + 1}:{_col_letter(c1)}{r1 + 1}"


def _style_at(styles: dict[str, Any], r0: int, c0: int) -> dict[str, Any]:
    return styles.get(f"{_col_letter(c0)}{r0 + 1}", {}) or {}


def _row_is_bold(styles: dict[str, Any], r0: int, ncols: int) -> bool:
    return any(_style_at(styles, r0, c).get("bold") for c in range(ncols))


def _row_has_fill(styles: dict[str, Any], r0: int, ncols: int) -> bool:
    return any(_style_at(styles, r0, c).get("fill") for c in range(ncols))


def _trim_columns(grid: list[list[str]]) -> list[list[str]]:
    if not grid:
        return []
    width = max((len(r) for r in grid), default=0)
    # normalize width
    norm = [list(r) + [""] * (width - len(r)) for r in grid]
    # drop trailing empty columns
    last = -1
    for c in range(width):
        if any(norm[r][c].strip() for r in range(len(norm))):
            last = c
    if last < 0:
        return []
    return [r[: last + 1] for r in norm]


def _effective_columns(grid: list[list[str]]) -> int:
    if not grid:
        return 0
    width = len(grid[0])
    count = 0
    for c in range(width):
        if any((row[c] if c < len(row) else "").strip() for row in grid):
            count += 1
    return count


def _row_line(row: list[str]) -> str:
    """Join a row's non-empty cells into a single readable line."""
    parts = [c.strip() for c in row if c and c.strip()]
    return "  ".join(parts)


def _collect_image_refs(grid: list[list[str]]) -> list[str]:
    refs: list[str] = []
    for row in grid:
        for cell in row:
            if cell and _IMAGE_EXT_RE.search(cell):
                token = cell.strip()
                if token not in refs:
                    refs.append(token)
    return refs


def _looks_like_matrix(grid: list[list[str]], ncols: int) -> bool:
    if ncols < 4 or len(grid) < 3:
        return False
    body = grid[1:]
    marks = 0
    filled = 0
    for row in body:
        for cell in row:
            t = (cell or "").strip().lower()
            if not t:
                continue
            filled += 1
            if t in _MARK_VALUES or len(t) == 1:
                marks += 1
    return filled > 0 and (marks / filled) >= 0.3


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def next(self) -> str:
        self.n += 1
        return f"block_{self.n}"


def _build_text_blocks(
    grid: list[list[str]], styles: dict[str, Any], ncols: int, ws_id: str, ids: _Ids, page_title: str
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    # Page title block (from first prominent line or page title)
    title_used = False
    lines: list[tuple[int, str, bool, bool]] = []  # (row, text, bold, isHeading)
    for r0, row in enumerate(grid):
        text = _row_line(row)
        if not text:
            continue
        bold = _row_is_bold(styles, r0, ncols)
        upper = text.isupper() and len(text) > 2
        heading = bold or upper or text.rstrip().endswith(":")
        lines.append((r0, text, bold, heading))

    if not lines:
        return blocks

    # Title: first bold/upper line, else page_title
    first_r, first_text, first_bold, _ = lines[0]
    if first_bold or first_text.isupper():
        blocks.append(
            {
                "id": ids.next(),
                "type": "title",
                "sourceWorksheetId": ws_id,
                "sourceRange": _range(first_r, 0, first_r, ncols - 1),
                "text": first_text,
                "styleRole": "page-title",
                "editable": True,
            }
        )
        title_used = True
        lines = lines[1:]
    elif page_title:
        blocks.append(
            {
                "id": ids.next(),
                "type": "title",
                "sourceWorksheetId": ws_id,
                "sourceRange": "",
                "text": page_title,
                "styleRole": "page-title",
                "editable": True,
            }
        )

    # Body: group bullets, headings, paragraphs
    bullet_buf: list[str] = []

    def flush_bullets() -> None:
        if bullet_buf:
            blocks.append(
                {
                    "id": ids.next(),
                    "type": "bulletList",
                    "sourceWorksheetId": ws_id,
                    "sourceRange": "",
                    "items": list(bullet_buf),
                    "styleRole": "body",
                    "editable": True,
                }
            )
            bullet_buf.clear()

    for r0, text, bold, heading in lines:
        if _BULLET_RE.match(text):
            bullet_buf.append(_BULLET_RE.sub("", text).strip() or text)
            continue
        flush_bullets()
        if heading and len(text) <= 90:
            blocks.append(
                {
                    "id": ids.next(),
                    "type": "sectionHeading",
                    "sourceWorksheetId": ws_id,
                    "sourceRange": _range(r0, 0, r0, ncols - 1),
                    "text": text,
                    "styleRole": "section-title",
                    "editable": True,
                }
            )
        else:
            blocks.append(
                {
                    "id": ids.next(),
                    "type": "paragraph",
                    "sourceWorksheetId": ws_id,
                    "sourceRange": _range(r0, 0, r0, ncols - 1),
                    "text": text,
                    "styleRole": "body",
                    "editable": True,
                }
            )
    flush_bullets()
    _ = title_used
    return blocks


def _build_table_block(
    grid: list[list[str]], styles: dict[str, Any], ncols: int, ws_id: str, ids: _Ids, kind: str
) -> dict[str, Any]:
    # Find header row: first row that is bold/fill, else first non-empty row.
    header_idx = 0
    for r0, row in enumerate(grid):
        if not any((c or "").strip() for c in row):
            continue
        if _row_is_bold(styles, r0, ncols) or _row_has_fill(styles, r0, ncols):
            header_idx = r0
            break
        header_idx = r0
        break

    headers = [(grid[header_idx][c] if c < len(grid[header_idx]) else "").strip() for c in range(ncols)]
    body_rows: list[list[str]] = []
    cell_fills: dict[str, str] = {}
    # Header-row fills (r = -1).
    for c in range(ncols):
        fill = _style_at(styles, header_idx, c).get("fill")
        if fill:
            cell_fills[f"-1:{c}"] = fill
    out_r = 0
    for src_r in range(header_idx + 1, len(grid)):
        row = grid[src_r]
        if not any((c or "").strip() for c in row):
            continue
        body_rows.append([(row[c] if c < len(row) else "").strip() for c in range(ncols)])
        for c in range(ncols):
            fill = _style_at(styles, src_r, c).get("fill")
            if fill:
                cell_fills[f"{out_r}:{c}"] = fill
        out_r += 1

    block: dict[str, Any] = {
        "id": ids.next(),
        "type": "matrix" if kind == "matrix" else "table",
        "sourceWorksheetId": ws_id,
        "sourceRange": _range(header_idx, 0, len(grid) - 1, ncols - 1),
        "headers": headers,
        "rows": body_rows,
        "styleRole": "table-header",
        "editable": True,
    }
    if cell_fills:
        block["cellFills"] = cell_fills
    return block


def _image_blocks(refs: list[str], ws_id: str, ids: _Ids) -> list[dict[str, Any]]:
    return [
        {
            "id": ids.next(),
            "type": "imagePlaceholder",
            "sourceWorksheetId": ws_id,
            "sourceRange": "",
            "filename": ref,
            "text": ref,
            "styleRole": "note",
            "editable": False,
        }
        for ref in refs
    ]


def normalize_page(
    ws_payload: dict[str, Any], ws_id: str, page_type: str, page_title: str = ""
) -> list[dict[str, Any]]:
    """Analyze a worksheet payload and return normalized page blocks.

    Never raises: on any failure it falls back to a single raw table block so the
    page still renders and no source content is lost.
    """
    ids = _Ids()
    try:
        grid = _trim_columns([list(r) for r in ws_payload.get("grid", [])])
        styles = ws_payload.get("styles", {}) or {}
        if not grid:
            return []

        ncols = _effective_columns(grid)
        image_refs = _collect_image_refs(grid)

        # Sheet Index — clean index table, never image placeholders.
        if page_type == "index":
            block = _build_table_block(grid, styles, max(ncols, 1), ws_id, ids, "table")
            block["styleRole"] = "index"
            return [block]

        # Canvas / diagram / layout pages
        if page_type in ("canvas", "hybrid", "underlay"):
            blocks: list[dict[str, Any]] = [
                {
                    "id": ids.next(),
                    "type": "canvas",
                    "sourceWorksheetId": ws_id,
                    "sourceRange": "",
                    "text": page_title,
                    "styleRole": "body",
                    "editable": True,
                }
            ]
            blocks.extend(_image_blocks(image_refs, ws_id, ids))
            return blocks

        # Cover page
        if page_type == "cover":
            lines = [_row_line(r) for r in grid if _row_line(r)]
            block = {
                "id": ids.next(),
                "type": "cover",
                "sourceWorksheetId": ws_id,
                "sourceRange": _range(0, 0, len(grid) - 1, ncols - 1),
                "text": page_title,
                "rows": [[ln] for ln in lines],
                "styleRole": "page-title",
                "editable": True,
            }
            out = [block]
            out.extend(_image_blocks(image_refs, ws_id, ids))
            return out

        # Image-dominant data pages
        if image_refs and ncols <= 2:
            out = [
                {
                    "id": ids.next(),
                    "type": "canvas",
                    "sourceWorksheetId": ws_id,
                    "sourceRange": "",
                    "text": page_title,
                    "styleRole": "body",
                    "editable": True,
                }
            ]
            out.extend(_image_blocks(image_refs, ws_id, ids))
            return out

        # Text-heavy page (sparse columns)
        if ncols <= 2:
            blocks = _build_text_blocks(grid, styles, ncols, ws_id, ids, page_title)
            blocks.extend(_image_blocks(image_refs, ws_id, ids))
            return blocks or [_build_table_block(grid, styles, max(ncols, 1), ws_id, ids, "table")]

        # Matrix vs table
        kind = "matrix" if _looks_like_matrix(grid, ncols) else "table"
        blocks = [_build_table_block(grid, styles, ncols, ws_id, ids, kind)]
        blocks.extend(_image_blocks(image_refs, ws_id, ids))
        return blocks

    except Exception:
        # Deterministic fallback: never lose the page.
        grid = ws_payload.get("grid", []) or []
        return [
            {
                "id": ids.next(),
                "type": "table",
                "sourceWorksheetId": ws_id,
                "sourceRange": "",
                "headers": (grid[0] if grid else []),
                "rows": grid[1:] if len(grid) > 1 else [],
                "styleRole": "table-header",
                "editable": True,
            }
        ]
