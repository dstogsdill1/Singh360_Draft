"""core/pdf_import_v2.py — Milestone 4A crisp PDF underlay import (Phase 6).

Builds on `core.pdf_renderer` (PyMuPDF) to import a single PDF page as a clean,
locked drawing underlay:

  * choose PDF + page number
  * auto-crop white margins (or apply a manual fractional crop)
  * vector-preserving SVG underlay when possible; otherwise 400–600 DPI PNG
  * returned descriptor is flagged `locked` + `placement: body` (never the
    title block) at a faint underlay opacity

Nothing here rasterizes at screenshot resolution — the default is 400 DPI, and
the SVG path preserves vectors outright. No content is invented.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except Exception:  # noqa: BLE001
    _HAS_FITZ = False

try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None

from core.drawing_style import UNDERLAY_GRAY_MAX
from core.pdf_renderer import get_page_count, render_page_to_png

# Crisp-import DPI presets. Underlays default to 400; 600 for fine schematics.
DPI_STANDARD = 400
DPI_FINE = 600
_WHITE_THRESHOLD = 245  # pixels lighter than this count as margin


def is_available() -> bool:
    return _HAS_FITZ


def get_pdf_info(pdf_path: Path) -> dict[str, Any]:
    """Return page count + per-page point sizes for a picker UI."""
    if not _HAS_FITZ:
        return {"ok": False, "error": "PyMuPDF is not installed."}
    pages = []
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        for i, page in enumerate(doc):  # type: ignore[attr-defined]
            r = page.rect
            pages.append({"page": i, "widthPt": round(r.width, 1), "heightPt": round(r.height, 1)})
    return {"ok": True, "pageCount": len(pages), "pages": pages}


def _autocrop_png(png_path: Path) -> dict[str, Any]:
    """Trim white margins from a PNG in place. Returns crop metadata."""
    if Image is None:
        return {"cropped": False}
    try:
        with Image.open(png_path) as im:
            rgb = im.convert("RGB")
            # Build a mask of non-white content and get its bounding box.
            gray = rgb.convert("L")
            bbox = gray.point(lambda p: 0 if p >= _WHITE_THRESHOLD else 255).getbbox()
            if not bbox:
                return {"cropped": False}
            left, top, right, bottom = bbox
            pad = 6
            left = max(0, left - pad)
            top = max(0, top - pad)
            right = min(rgb.width, right + pad)
            bottom = min(rgb.height, bottom + pad)
            if (left, top, right, bottom) == (0, 0, rgb.width, rgb.height):
                return {"cropped": False}
            rgb.crop((left, top, right, bottom)).save(png_path)
            return {"cropped": True, "cropBox": [left, top, right, bottom]}
    except Exception:  # noqa: BLE001
        return {"cropped": False}


def export_page_svg(pdf_path: Path, page_index: int, out_path: Path) -> dict[str, Any]:
    """Vector-preserving SVG export of a page (best fidelity underlay)."""
    if not _HAS_FITZ:
        return {"ok": False, "error": "PyMuPDF is not installed."}
    with fitz.open(str(pdf_path)) as doc:  # type: ignore[attr-defined]
        if page_index < 0 or page_index >= len(doc):
            return {"ok": False, "error": "Page out of range."}
        svg = doc[page_index].get_svg_image()  # type: ignore[attr-defined]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    return {"ok": True, "svgPath": str(out_path)}


def import_pdf_page(
    pdf_path: Path,
    page_index: int,
    out_dir: Path,
    *,
    dpi: int = DPI_STANDARD,
    autocrop: bool = True,
    crop: dict[str, float] | None = None,
    prefer_vector: bool = True,
) -> dict[str, Any]:
    """Import one PDF page as a locked underlay (SVG when possible, else PNG).

    Returns an underlay descriptor:
        {ok, pngPath, svgPath, dpi, cropped, locked, opacity, placement}
    """
    if not _HAS_FITZ:
        return {"ok": False, "error": "PyMuPDF is not installed."}
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{pdf_path.stem}_p{page_index + 1}"

    svg_path = out_dir / f"{stem}.svg"
    svg_meta: dict[str, Any] = {}
    if prefer_vector and not crop:
        svg_meta = export_page_svg(pdf_path, page_index, svg_path)

    png_path = out_dir / f"{stem}.png"
    png_meta = render_page_to_png(pdf_path, page_index, png_path, dpi=dpi, crop=crop)
    if not png_meta.get("ok"):
        return png_meta

    crop_meta = {"cropped": False}
    if autocrop and not crop:
        crop_meta = _autocrop_png(png_path)

    return {
        "ok": True,
        "pdf": pdf_path.name,
        "pageIndex": page_index,
        "pngPath": str(png_path),
        "svgPath": str(svg_path) if svg_meta.get("ok") else "",
        "dpi": dpi,
        "outputWidth": png_meta.get("outputWidth"),
        "outputHeight": png_meta.get("outputHeight"),
        "cropped": crop_meta.get("cropped", False),
        "cropBox": crop_meta.get("cropBox"),
        # Underlay policy (Phase 4/6): faint, locked, in the body — not the TB.
        "locked": True,
        "opacity": UNDERLAY_GRAY_MAX,
        "placement": "body",
        "vectorPreserved": bool(svg_meta.get("ok")),
    }
