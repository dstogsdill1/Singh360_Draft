"""Vector-preserving PDF-page export helpers for Singh360 Draft.

The editor uses a raster preview inside the Fabric canvas so users can move and
crop a source PDF page interactively.  During final PDF export, this module hides
eligible raster previews in an export-only project clone and places the original
born-digital PDF content back into the exported sheet with PyMuPDF.  This keeps
linework and text sharp at any zoom without altering the live project or source
PDF.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import fitz  # PyMuPDF

SHEET_W = 1632.0
SHEET_H = 1056.0
# CSS geometry: 2px shell border + 8px .sheet-inner inset + 1px inner border
# + 8px .sheet-body inset = 19 logical pixels from the sheet origin.
BODY_ORIGIN_X = 19.0
BODY_ORIGIN_Y = 19.0
_SAFE_PDF_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}\.pdf$", re.IGNORECASE)


@dataclass(frozen=True)
class VectorPlacement:
    export_page_index: int
    project_page_id: str
    source_pdf: str
    source_page_index: int
    clip: tuple[float, float, float, float]
    left: float
    top: float
    width: float
    height: float
    object_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_crop(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, str):
        try:
            values = [float(part.strip()) for part in value.split(",")]
        except ValueError:
            return None
        if len(values) == 4:
            x0, y0, x1, y1 = values
            if x1 > x0 and y1 > y0:
                return x0, y0, x1, y1
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            x0, y0, x1, y1 = (float(item) for item in value)
        except (TypeError, ValueError):
            return None
        if x1 > x0 and y1 > y0:
            return x0, y0, x1, y1
    return None


def _origin_adjust(value: float, size: float, origin: str | None) -> float:
    key = str(origin or "left").lower()
    if key == "center":
        return value - size / 2.0
    if key in {"right", "bottom"}:
        return value - size
    return value


def _eligible_direct_pdf_object(obj: dict[str, Any]) -> bool:
    source = str(obj.get("pdfSource") or "").strip()
    if not source or not _SAFE_PDF_NAME.fullmatch(source):
        return False
    if str(obj.get("type") or "").lower() not in {"image", "fabricimage"}:
        return False
    try:
        angle = float(obj.get("angle") or 0)
        opacity = float(obj.get("opacity") if obj.get("opacity") is not None else 1)
    except (TypeError, ValueError):
        return False
    # Rotated/flipped/semi-transparent previews stay raster so the export cannot
    # silently change a user's intended appearance.
    if abs(angle) > 0.001 or bool(obj.get("flipX")) or bool(obj.get("flipY")):
        return False
    if opacity < 0.999:
        return False
    try:
        width = float(obj.get("width") or 0)
        height = float(obj.get("height") or 0)
        sx = float(obj.get("scaleX") if obj.get("scaleX") is not None else 1)
        sy = float(obj.get("scaleY") if obj.get("scaleY") is not None else 1)
    except (TypeError, ValueError):
        return False
    return width > 0 and height > 0 and sx > 0 and sy > 0


def _placement_from_object(
    obj: dict[str, Any],
    *,
    export_page_index: int,
    project_page_id: str,
) -> VectorPlacement | None:
    if not _eligible_direct_pdf_object(obj):
        return None
    source_pdf = str(obj.get("pdfSource") or "").strip()
    try:
        source_page_index = max(0, int(obj.get("pdfPage") or 0))
        dpi = max(72.0, float(obj.get("pdfDpi") or 400))
        width_px = float(obj.get("width") or 0)
        height_px = float(obj.get("height") or 0)
        crop_x_px = max(0.0, float(obj.get("cropX") or 0))
        crop_y_px = max(0.0, float(obj.get("cropY") or 0))
        scale_x = float(obj.get("scaleX") if obj.get("scaleX") is not None else 1)
        scale_y = float(obj.get("scaleY") if obj.get("scaleY") is not None else 1)
        raw_left = float(obj.get("left") or 0)
        raw_top = float(obj.get("top") or 0)
    except (TypeError, ValueError):
        return None

    base_crop = _parse_crop(obj.get("pdfCrop"))
    # Full-page imports omit pdfCrop.  The final page rectangle is resolved from
    # the source PDF at insertion time; use a sentinel rectangle here.
    if base_crop is None:
        base_crop = (math.nan, math.nan, math.nan, math.nan)

    points_per_pixel = 72.0 / dpi
    if not math.isnan(base_crop[0]):
        x0 = base_crop[0] + crop_x_px * points_per_pixel
        y0 = base_crop[1] + crop_y_px * points_per_pixel
    else:
        x0 = crop_x_px * points_per_pixel
        y0 = crop_y_px * points_per_pixel
    x1 = x0 + width_px * points_per_pixel
    y1 = y0 + height_px * points_per_pixel

    rendered_width = width_px * scale_x
    rendered_height = height_px * scale_y
    left = _origin_adjust(raw_left, rendered_width, obj.get("originX"))
    top = _origin_adjust(raw_top, rendered_height, obj.get("originY"))

    return VectorPlacement(
        export_page_index=export_page_index,
        project_page_id=project_page_id,
        source_pdf=source_pdf,
        source_page_index=source_page_index,
        clip=(x0, y0, x1, y1),
        left=left,
        top=top,
        width=rendered_width,
        height=rendered_height,
        object_name=str(obj.get("objName") or source_pdf),
    )


def selected_page_ids_from_request(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        for item in str(raw or "").split(","):
            page_id = item.strip()
            if page_id and page_id not in seen:
                seen.add(page_id)
                out.append(page_id)
    return out


def build_selected_export_document(
    project: dict[str, Any],
    selected_page_ids: Iterable[str] | None,
) -> dict[str, Any]:
    """Return an export-only clone with exactly the selected published pages.

    An empty/omitted selection means all currently included pages.  The Sheet
    Index is rebuilt only when its base page is selected, and Page X of Y is
    recalculated for the selected export set.
    """
    from core.project_model import recalc_page_numbers
    from core.sheet_index_sync import sync_project_sheet_index

    clone = copy.deepcopy(project)
    selected = selected_page_ids_from_request(selected_page_ids)
    pages = clone.get("pages") if isinstance(clone.get("pages"), list) else []
    originally_included = {
        str(page.get("id"))
        for page in pages
        if isinstance(page, dict) and page.get("include", True)
    }
    allowed = set(selected) if selected else originally_included
    for page in pages:
        if not isinstance(page, dict):
            continue
        page["include"] = str(page.get("id")) in allowed and str(page.get("id")) in originally_included

    clone = sync_project_sheet_index(clone)
    recalc_page_numbers(clone)
    return clone


def prepare_vector_export_clone(
    project: dict[str, Any],
    *,
    source_pdf_dir: Path | None = None,
) -> tuple[dict[str, Any], list[VectorPlacement]]:
    """Hide eligible direct PDF preview images and return vector placements.

    When a source directory is supplied, a preview is hidden only after the
    original PDF and referenced page have been verified.  A missing/bad source
    therefore stays raster rather than becoming a blank export.
    """
    clone = copy.deepcopy(project)
    pages = sorted(
        [page for page in clone.get("pages", []) if isinstance(page, dict) and page.get("include", True)],
        key=lambda page: int(page.get("order") or 0),
    )
    placements: list[VectorPlacement] = []
    verified_sources: dict[Path, int] = {}
    for export_index, page in enumerate(pages):
        objects = page.get("canvasObjects") if isinstance(page.get("canvasObjects"), list) else []
        for obj in objects:
            # Grouped objects require transform composition and deliberately stay
            # raster.  Direct images cover the normal PDF-page import workflow.
            if not isinstance(obj, dict):
                continue
            placement = _placement_from_object(
                obj,
                export_page_index=export_index,
                project_page_id=str(page.get("id") or ""),
            )
            if placement is None:
                continue
            if source_pdf_dir is not None:
                source_path = _resolve_source_pdf(Path(source_pdf_dir), placement.source_pdf)
                if source_path is None:
                    continue
                page_count = verified_sources.get(source_path)
                if page_count is None:
                    try:
                        source_doc = fitz.open(source_path)
                        page_count = source_doc.page_count
                        source_doc.close()
                    except Exception:
                        continue
                    verified_sources[source_path] = page_count
                if placement.source_page_index < 0 or placement.source_page_index >= page_count:
                    continue
            placements.append(placement)
            obj["visible"] = False
            obj["excludeFromExport"] = True
    return clone, placements


def _resolve_source_pdf(source_pdf_dir: Path, name: str) -> Path | None:
    if not _SAFE_PDF_NAME.fullmatch(name):
        return None
    root = source_pdf_dir.resolve()
    candidate = (root / name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def _destination_rect(page: fitz.Page, placement: VectorPlacement) -> fitz.Rect:
    sheet_scale = min(page.rect.width / SHEET_W, page.rect.height / SHEET_H)
    rendered_sheet_w = SHEET_W * sheet_scale
    rendered_sheet_h = SHEET_H * sheet_scale
    offset_x = (page.rect.width - rendered_sheet_w) / 2.0
    offset_y = (page.rect.height - rendered_sheet_h) / 2.0
    x0 = offset_x + (BODY_ORIGIN_X + placement.left) * sheet_scale
    y0 = offset_y + (BODY_ORIGIN_Y + placement.top) * sheet_scale
    return fitz.Rect(
        x0,
        y0,
        x0 + placement.width * sheet_scale,
        y0 + placement.height * sheet_scale,
    )


def apply_vector_pdf_underlays(
    pdf_path: Path,
    *,
    source_pdf_dir: Path,
    placements: Iterable[VectorPlacement],
) -> dict[str, Any]:
    """Insert original PDF content behind the transparent export canvas.

    Saves through a temporary file and atomically replaces the Playwright output.
    Returns an audit dictionary suitable for logs/tests.
    """
    pdf_path = Path(pdf_path)
    source_pdf_dir = Path(source_pdf_dir)
    placement_list = list(placements)
    if not placement_list:
        return {"ok": True, "inserted": 0, "skipped": 0, "placements": []}

    output = fitz.open(pdf_path)
    source_docs: dict[Path, fitz.Document] = {}
    inserted = 0
    skipped: list[dict[str, Any]] = []
    try:
        for placement in placement_list:
            if placement.export_page_index < 0 or placement.export_page_index >= output.page_count:
                skipped.append({**placement.to_dict(), "reason": "export page is missing"})
                continue
            source_path = _resolve_source_pdf(source_pdf_dir, placement.source_pdf)
            if source_path is None:
                skipped.append({**placement.to_dict(), "reason": "source PDF is missing or unsafe"})
                continue
            source = source_docs.get(source_path)
            if source is None:
                source = fitz.open(source_path)
                source_docs[source_path] = source
            if placement.source_page_index >= source.page_count:
                skipped.append({**placement.to_dict(), "reason": "source page is outside the PDF"})
                continue

            source_page = source[placement.source_page_index]
            clip_values = placement.clip
            if any(math.isnan(value) for value in clip_values):
                clip = fitz.Rect(source_page.rect)
            else:
                clip = fitz.Rect(*clip_values) & source_page.rect
            if clip.is_empty or clip.width <= 0 or clip.height <= 0:
                skipped.append({**placement.to_dict(), "reason": "source crop is empty"})
                continue

            destination = _destination_rect(output[placement.export_page_index], placement)
            if destination.is_empty or destination.width <= 0 or destination.height <= 0:
                skipped.append({**placement.to_dict(), "reason": "destination is empty"})
                continue
            output[placement.export_page_index].show_pdf_page(
                destination,
                source,
                placement.source_page_index,
                clip=clip,
                keep_proportion=False,
                overlay=False,
            )
            inserted += 1

        temp_path = pdf_path.with_name(f"{pdf_path.stem}.vectorized.tmp.pdf")
        output.save(temp_path, garbage=4, deflate=True, clean=True)
    finally:
        output.close()
        for source in source_docs.values():
            source.close()

    temp_doc = fitz.open(temp_path)
    try:
        page_count = temp_doc.page_count
        page_sizes = [(round(page.rect.width, 4), round(page.rect.height, 4)) for page in temp_doc]
    finally:
        temp_doc.close()
    temp_path.replace(pdf_path)
    return {
        "ok": True,
        "inserted": inserted,
        "skipped": len(skipped),
        "skippedDetails": skipped,
        "pageCount": page_count,
        "pageSizes": page_sizes,
        "placements": [placement.to_dict() for placement in placement_list],
    }
