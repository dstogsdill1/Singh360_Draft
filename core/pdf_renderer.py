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


def get_page_previews(pdf_path: Path, *, preview_dpi: int = 110) -> list[dict[str, Any]]:
    """Return crop-selection previews for every page.

    Each entry carries the page size in BOTH points and inches plus a base64 PNG
    rendered at ``preview_dpi`` (larger than a thumbnail so the user can draw an
    accurate crop rectangle). The preview pixel-to-point scale is exactly
    ``preview_dpi / 72`` so the frontend can map a screen rectangle back to PDF
    point coordinates.
    """
    import base64

    if not _HAS_FITZ:
        return []
    scale = preview_dpi / 72.0
    mat = fitz.Matrix(scale, scale)  # type: ignore[attr-defined]
    out: list[dict[str, Any]] = []
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        for i, page in enumerate(doc):  # type: ignore[attr-defined]
            rect = page.rect
            pix = page.get_pixmap(matrix=mat)
            data = base64.b64encode(pix.tobytes("png")).decode()
            out.append({
                "page": i,
                "widthPt": round(rect.width, 2),
                "heightPt": round(rect.height, 2),
                "widthIn": round(rect.width / 72.0, 3),
                "heightIn": round(rect.height / 72.0, 3),
                "rotation": int(getattr(page, "rotation", 0) or 0),
                "previewDpi": preview_dpi,
                "previewWidth": pix.width,
                "previewHeight": pix.height,
                "previewDataUrl": f"data:image/png;base64,{data}",
            })
    return out



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
        return {"ok": False, "error": "PDF rendering requires PyMuPDF. Run: python -m pip install pymupdf"}
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


def render_crop_points(
    pdf_path: Path,
    page_index: int,
    output_path: Path,
    *,
    dpi: int = 400,
    clip_points: dict[str, float],
) -> dict[str, Any]:
    """Render a crop given a rectangle in PDF POINT coordinates at ``dpi``.

    ``clip_points`` = {"x0","y0","x1","y1"} in PDF points (1/72 inch), the same
    coordinate space as ``page.rect`` — so rotation is handled by PyMuPDF and the
    crop matches the preview the user drew on. The rectangle is clamped to the
    page bounds; a degenerate rectangle falls back to the full page.
    """
    if not _HAS_FITZ:
        return {"ok": False, "error": "PDF rendering requires PyMuPDF. Run: python -m pip install pymupdf"}
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)  # type: ignore[attr-defined]
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        if page_index < 0 or page_index >= len(doc):
            return {"ok": False, "error": f"Page {page_index} out of range ({len(doc)} pages)."}
        page = doc[page_index]
        rect = page.rect
        x0 = max(rect.x0, min(float(clip_points.get("x0", rect.x0)), rect.x1))
        y0 = max(rect.y0, min(float(clip_points.get("y0", rect.y0)), rect.y1))
        x1 = max(rect.x0, min(float(clip_points.get("x1", rect.x1)), rect.x1))
        y1 = max(rect.y0, min(float(clip_points.get("y1", rect.y1)), rect.y1))
        if x1 - x0 < 2 or y1 - y0 < 2:
            clip = rect  # degenerate selection → full page
        else:
            clip = fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))  # type: ignore[attr-defined]
        pix = page.get_pixmap(matrix=mat, clip=clip)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(output_path))

    return {
        "ok": True,
        "pageIndex": page_index,
        "renderDpi": dpi,
        "cropPoints": {"x0": clip.x0, "y0": clip.y0, "x1": clip.x1, "y1": clip.y1},
        "cropWidthIn": round((clip.x1 - clip.x0) / 72.0, 3),
        "cropHeightIn": round((clip.y1 - clip.y0) / 72.0, 3),
        "outputWidth": pix.width,
        "outputHeight": pix.height,
        "outputPath": str(output_path),
    }
