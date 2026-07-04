"""core/pdf_renderer.py — render PDF pages to high-resolution PNG using PyMuPDF.

Provides a backend PDF-page renderer that converts individual PDF pages into
high-resolution PNG assets stored under a project's assets/images folder.
Falls back gracefully when PyMuPDF is unavailable.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False


def is_available() -> bool:
    return _HAS_FITZ


def get_page_count(pdf_path: Path) -> int:
    if not _HAS_FITZ:
        return 0
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        return len(doc)


def get_page_thumbnails(pdf_path: Path, max_size: int = 200) -> list[dict[str, Any]]:
    """Return base64 PNG thumbnails for all pages (for a picker UI)."""
    import base64

    if not _HAS_FITZ:
        return []
    result = []
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        for i, page in enumerate(doc):  # type: ignore[attr-defined]
            rect = page.rect
            scale = min(max_size / max(rect.width, 1), max_size / max(rect.height, 1))
            mat = fitz.Matrix(scale, scale)  # type: ignore[attr-defined]
            pix = page.get_pixmap(matrix=mat)
            data = base64.b64encode(pix.tobytes("png")).decode()
            result.append({
                "page": i,
                "width": int(rect.width),
                "height": int(rect.height),
                "thumbnailDataUrl": f"data:image/png;base64,{data}",
            })
    return result


def render_page_to_png(
    pdf_path: Path,
    page_index: int,
    output_path: Path,
    *,
    dpi: int = 200,
    crop: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Render a PDF page (with optional crop) to a PNG at the given DPI.

    Args:
        pdf_path:    Path to the source PDF.
        page_index:  0-based page number.
        output_path: Where to write the PNG.
        dpi:         Render resolution (default 200 ≈ "high"; use 300 for "print").
        crop:        Optional crop rectangle as fractions 0–1:
                     {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}

    Returns a metadata dict:
        {"ok", "pageIndex", "pageWidth", "pageHeight", "renderDpi",
         "outputWidth", "outputHeight", "outputPath", "originalPdfPage"}
    """
    if not _HAS_FITZ:
        return {"ok": False, "error": "PyMuPDF is not installed."}
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)  # type: ignore[attr-defined]
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        if page_index < 0 or page_index >= len(doc):
            return {"ok": False, "error": f"Page {page_index} out of range ({len(doc)} pages)."}
        page = doc[page_index]
        rect = page.rect
        page_w, page_h = rect.width, rect.height

        if crop:
            # Convert fractional crop to page coordinates.
            cx = float(crop.get("x", 0.0)) * page_w
            cy = float(crop.get("y", 0.0)) * page_h
            cw = float(crop.get("w", 1.0)) * page_w
            ch = float(crop.get("h", 1.0)) * page_h
            clip = fitz.Rect(cx, cy, cx + cw, cy + ch)  # type: ignore[attr-defined]
            pix = page.get_pixmap(matrix=mat, clip=clip)
        else:
            pix = page.get_pixmap(matrix=mat)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(output_path))

    return {
        "ok": True,
        "pageIndex": page_index,
        "pageWidth": int(page_w),
        "pageHeight": int(page_h),
        "renderDpi": dpi,
        "outputWidth": pix.width,
        "outputHeight": pix.height,
        "outputPath": str(output_path),
    }
