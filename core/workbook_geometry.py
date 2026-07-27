"""Canonical workbook, drawing, and PDF geometry conversions.

Excel stores column widths in default-font character units and row heights in
points. Univer and the Singh360 drawing renderers use CSS pixels. PDF uses
points. All workbook geometry must cross those boundaries through this module;
callers must not use ad-hoc ``* 7``, ``/ 7``, ``* .75``, or ``* 4 / 3`` math.
"""
from __future__ import annotations

import math
from typing import Any


CSS_PIXELS_PER_INCH = 96.0
PDF_POINTS_PER_INCH = 72.0
EXCEL_MAX_DIGIT_WIDTH_PX = 7
EXCEL_COLUMN_PADDING_PX = 5
DEFAULT_COLUMN_WIDTH_UNITS = 8.43
DEFAULT_ROW_HEIGHT_POINTS = 15.0
DEFAULT_COLUMN_WIDTH_PX = 64
DEFAULT_ROW_HEIGHT_PX = 20.0


def _positive_number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) and number > 0 else fallback


def excel_column_width_to_pixels(width: Any) -> int:
    """Convert OOXML column-width units to the pixel width Excel displays.

    This is the ECMA-376/Excel max-digit-width calculation for the default
    Calibri 11 metric (MDW 7), including Excel's five-pixel cell padding.
    """
    units = _positive_number(width, DEFAULT_COLUMN_WIDTH_UNITS)
    pixels = math.floor(
        (
            (
                256 * units
                + math.floor(128 / EXCEL_MAX_DIGIT_WIDTH_PX)
            )
            / 256
        )
        * EXCEL_MAX_DIGIT_WIDTH_PX
    ) + EXCEL_COLUMN_PADDING_PX
    return max(1, pixels)


def pixels_to_excel_column_width(pixels: Any) -> float:
    """Convert a displayed pixel width to stable OOXML column-width units."""
    width_px = _positive_number(pixels, DEFAULT_COLUMN_WIDTH_PX)
    if width_px <= EXCEL_COLUMN_PADDING_PX:
        return round(width_px / (EXCEL_MAX_DIGIT_WIDTH_PX + EXCEL_COLUMN_PADDING_PX), 2)
    return round(
        (width_px - EXCEL_COLUMN_PADDING_PX) / EXCEL_MAX_DIGIT_WIDTH_PX,
        2,
    )


def row_height_points_to_pixels(points: Any) -> float:
    """Convert Excel row-height points to CSS/Univer pixels."""
    value = _positive_number(points, DEFAULT_ROW_HEIGHT_POINTS)
    return round(value * CSS_PIXELS_PER_INCH / PDF_POINTS_PER_INCH, 4)


def pixels_to_row_height_points(pixels: Any) -> float:
    """Convert CSS/Univer pixels to Excel row-height points."""
    value = _positive_number(pixels, DEFAULT_ROW_HEIGHT_PX)
    return round(value * PDF_POINTS_PER_INCH / CSS_PIXELS_PER_INCH, 4)


def pixels_to_pdf_points(pixels: Any) -> float:
    """Convert drawing/CSS pixels to PDF points using physical units."""
    value = float(pixels)
    if not math.isfinite(value):
        raise ValueError("Pixel geometry must be finite.")
    return value * PDF_POINTS_PER_INCH / CSS_PIXELS_PER_INCH


def pdf_points_to_pixels(points: Any) -> float:
    """Convert PDF points to drawing/CSS pixels using physical units."""
    value = float(points)
    if not math.isfinite(value):
        raise ValueError("PDF geometry must be finite.")
    return value * CSS_PIXELS_PER_INCH / PDF_POINTS_PER_INCH


def unchanged_excel_width_or_converted(
    pixels: Any,
    previous_width: Any | None,
) -> float:
    """Preserve an exact stored Excel width if its displayed pixels are unchanged.

    Univer stores integer pixel widths. Several exact Excel widths can map to
    the same displayed pixel width, so an untouched value must retain its
    original OOXML unit rather than being needlessly quantized on save.
    """
    width_px = int(round(_positive_number(pixels, DEFAULT_COLUMN_WIDTH_PX)))
    if previous_width is not None:
        previous = _positive_number(previous_width, DEFAULT_COLUMN_WIDTH_UNITS)
        if excel_column_width_to_pixels(previous) == width_px:
            return previous
    return pixels_to_excel_column_width(width_px)


def unchanged_row_height_or_converted(
    pixels: Any,
    previous_points: Any | None,
    *,
    tolerance: float = 0.01,
) -> float:
    """Preserve exact row-height points unless Univer changed their pixel size."""
    height_px = _positive_number(pixels, DEFAULT_ROW_HEIGHT_PX)
    if previous_points is not None:
        previous = _positive_number(previous_points, DEFAULT_ROW_HEIGHT_POINTS)
        if abs(row_height_points_to_pixels(previous) - height_px) <= tolerance:
            return previous
    return pixels_to_row_height_points(height_px)
