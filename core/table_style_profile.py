"""core/table_style_profile.py — the Singh360 standard drawing-table profile.

One consistent look for every non-cover table/instruction/schedule page,
regardless of what fills the source workbook tab carried:

  1. Orange/gold title band (black centered title text).
  2. Optional light-gray project/subtitle row under the band.
  3. Gray column-header row.
  4. Excel-style grid borders.
  5. Alternating very-light-gray body rows.
  6. Gold controller / section bands preserved (they are the Singh360 accent).

This module is deterministic and hallucination-free: it only *recolors* cells
that already exist in the exact Excel range. It never invents rows, columns, or
values. The recolor is applied to ``excelRange`` blocks (styles keyed ``"r:c"``,
0-based) produced by ``core/workbook_importer``.
"""
from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Singh360 standard palette + typography (renderProfile = singh360_standard_table)
# --------------------------------------------------------------------------
RENDER_PROFILE = "singh360_standard_table"

TITLE_BAND_FILL = "#FFC000"   # orange/gold title band
TITLE_BAND_TEXT = "#000000"   # black centered title text
SUBTITLE_FILL = "#F2F2F2"     # optional light-gray project/subtitle row
COLUMN_HEADER_FILL = "#D9D9D9"  # gray column-header row
COLUMN_HEADER_TEXT = "#000000"
BODY_ALT_FILL = "#F4F6F8"     # alternating very-light-gray body rows
BODY_FILL = "#FFFFFF"
GRID_COLOR = "#A6A6A6"
SECTION_DIVIDER = "#000000"

FONT_FAMILY = "Calibri"
DENSE_FONT_SIZE = 7.5
NORMAL_FONT_SIZE = 8.0
TITLE_FONT_SIZE = 11.0

# A fill is considered a "controller / section accent" band (kept) when it is a
# saturated gold/amber. A fill is considered a "dark title band" (recolored to
# orange) when its relative luminance is below this threshold.
DARK_LUMINANCE_MAX = 0.34
# Gold band detection: high red+green, low-ish blue, reasonably bright.
GOLD_LUMINANCE_MIN = 0.45


def _parse_hex(color: str | None) -> tuple[int, int, int] | None:
    if not color or not isinstance(color, str):
        return None
    c = color.strip().lstrip("#")
    if len(c) == 8:  # ARGB
        c = c[2:]
    if len(c) != 6:
        return None
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return None


def _relative_luminance(color: str | None) -> float | None:
    rgb = _parse_hex(color)
    if rgb is None:
        return None
    r, g, b = (v / 255.0 for v in rgb)
    # Rec. 709 luma (perceptual enough for a light/dark decision).
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark_fill(color: str | None) -> bool:
    lum = _relative_luminance(color)
    return lum is not None and lum <= DARK_LUMINANCE_MAX


def is_gold_fill(color: str | None) -> bool:
    """True for the saturated gold/amber controller bands we want to preserve."""
    rgb = _parse_hex(color)
    if rgb is None:
        return False
    r, g, b = rgb
    lum = _relative_luminance(color) or 0.0
    # Amber/gold: strong red & green, weaker blue, mid-to-high brightness.
    return r >= 200 and g >= 140 and b <= 160 and (r + g) - 2 * b > 120 and lum >= 0.35


# --------------------------------------------------------------------------
# Profile application
# --------------------------------------------------------------------------
def _style_at(styles: dict[str, Any], r: int, c: int) -> dict[str, Any]:
    key = f"{r}:{c}"
    st = styles.get(key)
    if st is None:
        st = {}
        styles[key] = st
    return st


def _row_has_dark_band(styles: dict[str, Any], r: int, ncols: int) -> bool:
    for c in range(ncols):
        st = styles.get(f"{r}:{c}")
        if st and is_dark_fill(st.get("fill")):
            return True
    return False


def _row_is_header_like(styles: dict[str, Any], r: int, ncols: int) -> bool:
    """A header-ish row: mostly bold and/or filled, non-empty."""
    styled = 0
    for c in range(ncols):
        st = styles.get(f"{r}:{c}")
        if st and (st.get("bold") or st.get("fill")):
            styled += 1
    return styled >= max(1, ncols // 3)


def apply_singh360_profile(block: dict[str, Any], style: str = "orange") -> dict[str, Any]:
    """Recolor an ``excelRange`` block into the Singh360 standard.

    ``style``:
      - ``"orange"`` (default): dark title bands → orange w/ black centered title;
        column-header rows → gray; gold controller bands preserved; alt-row shade.
      - ``"source"``: leave the source colors untouched (legacy look).
      - ``"none"``: strip dark bands to white (plain), no orange accent.

    Mutates and returns ``block``. Non-``excelRange`` blocks are returned as-is.
    """
    block["renderProfile"] = RENDER_PROFILE
    block["normalizedHeaderStyle"] = style
    if style == "source" or block.get("type") != "excelRange":
        return block

    grid = block.get("grid") or []
    n_rows = len(grid)
    if n_rows == 0:
        return block
    n_cols = max((len(r) for r in grid), default=0)
    styles: dict[str, Any] = dict(block.get("styles") or {})
    repeat = set(block.get("repeatRows") or [])
    header_count = int(block.get("headerRowCount") or (max(repeat) + 1 if repeat else 1))

    # Header band: the leading rows (repeatRows / headerRowCount). The first dark
    # band row becomes the orange title; the remaining header rows become gray
    # column headers. Gold controller/section bands are preserved everywhere.
    title_assigned = False
    for r in range(min(n_rows, max(header_count, 1))):
        row_dark = _row_has_dark_band(styles, r, n_cols)
        for c in range(n_cols):
            st = _style_at(styles, r, c)
            fill = st.get("fill")
            if is_gold_fill(fill):
                continue  # keep the Singh360 gold accent
            if style == "none":
                if is_dark_fill(fill):
                    st["fill"] = BODY_FILL
                    st["fontColor"] = "#000000"
                continue
            # style == "orange"
            if not title_assigned and row_dark:
                st["fill"] = TITLE_BAND_FILL
                st["fontColor"] = TITLE_BAND_TEXT
                st["bold"] = True
                st.setdefault("hAlign", "center")
            else:
                # Column-header row → gray.
                st["fill"] = COLUMN_HEADER_FILL
                st["fontColor"] = COLUMN_HEADER_TEXT
                st["bold"] = True
        if row_dark and not title_assigned and style == "orange":
            title_assigned = True

    # Body: recolor any *remaining* dark bands (section titles inside the body).
    # Dark → orange section band (orange), gold preserved; also apply alt-row.
    data_start = max(header_count, 1)
    alt = False
    for r in range(data_start, n_rows):
        row_dark = _row_has_dark_band(styles, r, n_cols)
        if row_dark:
            for c in range(n_cols):
                st = _style_at(styles, r, c)
                if is_gold_fill(st.get("fill")):
                    continue
                if is_dark_fill(st.get("fill")):
                    if style == "none":
                        st["fill"] = BODY_FILL
                        st["fontColor"] = "#000000"
                    else:
                        st["fill"] = TITLE_BAND_FILL
                        st["fontColor"] = TITLE_BAND_TEXT
                        st["bold"] = True
            alt = False
            continue
        # Alternating body shading on rows that carry no explicit source fill.
        if style == "orange" and alt:
            for c in range(n_cols):
                st = _style_at(styles, r, c)
                if not st.get("fill"):
                    st["fill"] = BODY_ALT_FILL
        alt = not alt

    block["styles"] = styles
    return block


def profile_summary(block: dict[str, Any]) -> dict[str, Any]:
    """Small diagnostic summary of what the profile did (for render logs)."""
    styles = block.get("styles") or {}
    fills = [st.get("fill") for st in styles.values() if isinstance(st, dict) and st.get("fill")]
    return {
        "renderProfile": block.get("renderProfile"),
        "normalizedHeaderStyle": block.get("normalizedHeaderStyle"),
        "orangeBands": sum(1 for f in fills if f == TITLE_BAND_FILL),
        "grayHeaders": sum(1 for f in fills if f == COLUMN_HEADER_FILL),
        "goldBands": sum(1 for f in fills if is_gold_fill(f)),
    }
