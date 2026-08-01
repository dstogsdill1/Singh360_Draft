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
import json
import math
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import fitz  # PyMuPDF

from core.page_identity import is_sheet_index_page

SHEET_W = 1632.0
SHEET_H = 1056.0
PAGE_ID_MARKER_PREFIX = "S360PID_"
# CSS geometry: 2px shell border + 8px .sheet-inner inset + 1px inner border
# + 8px .sheet-body inset = 19 logical pixels from the sheet origin.
BODY_ORIGIN_X = 19.0
BODY_ORIGIN_Y = 19.0
_SAFE_PDF_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}\.pdf$", re.IGNORECASE)
_TRANSPARENT_EXPORT_PREVIEW = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
)


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
    coordinate_space: str = "body"
    strict_base: bool = False
    rotation: int = 0

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


def _eligible_direct_pdf_object(obj: dict[str, Any]) -> bool:
    source = str(obj.get("pdfSource") or "").strip()
    if not source or not _SAFE_PDF_NAME.fullmatch(source):
        return False
    if str(obj.get("type") or "").lower() not in {"image", "fabricimage"}:
        return False
    try:
        angle = float(obj.get("angle") or 0)
    except (TypeError, ValueError):
        return False
    # Born-digital PDF bases must never fall back to their PNG editor preview.
    # Orthogonal rotation remains vector-preserving; arbitrary rotation and
    # mirroring fail preflight with a useful message instead of silently
    # embedding the preview.
    nearest_quarter_turn = round(angle / 90.0) * 90
    if abs(angle - nearest_quarter_turn) > 0.001 or bool(obj.get("flipX")) or bool(obj.get("flipY")):
        return False
    try:
        width = float(obj.get("width") or 0)
        height = float(obj.get("height") or 0)
        sx = float(obj.get("scaleX") if obj.get("scaleX") is not None else 1)
        sy = float(obj.get("scaleY") if obj.get("scaleY") is not None else 1)
    except (TypeError, ValueError):
        return False
    return width > 0 and height > 0 and sx > 0 and sy > 0


def _fabric_bounds(
    raw_left: float,
    raw_top: float,
    width: float,
    height: float,
    *,
    origin_x: str | None,
    origin_y: str | None,
    rotation: int,
) -> tuple[float, float, float, float]:
    """Return Fabric's axis-aligned bounds for an orthogonally rotated object."""
    ox = {"left": 0.0, "center": width / 2.0, "right": width}.get(str(origin_x or "left").lower(), 0.0)
    oy = {"top": 0.0, "center": height / 2.0, "bottom": height}.get(str(origin_y or "top").lower(), 0.0)
    radians = math.radians(rotation % 360)
    cosine, sine = math.cos(radians), math.sin(radians)
    points: list[tuple[float, float]] = []
    for x, y in ((0.0, 0.0), (width, 0.0), (0.0, height), (width, height)):
        local_x, local_y = x - ox, y - oy
        points.append((
            raw_left + local_x * cosine - local_y * sine,
            raw_top + local_x * sine + local_y * cosine,
        ))
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


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
    rotation = int(round(float(obj.get("angle") or 0))) % 360
    left, top, placed_width, placed_height = _fabric_bounds(
        raw_left,
        raw_top,
        rendered_width,
        rendered_height,
        origin_x=obj.get("originX"),
        origin_y=obj.get("originY"),
        rotation=rotation,
    )

    return VectorPlacement(
        export_page_index=export_page_index,
        project_page_id=project_page_id,
        source_pdf=source_pdf,
        source_page_index=source_page_index,
        clip=(x0, y0, x1, y1),
        left=left,
        top=top,
        width=placed_width,
        height=placed_height,
        object_name=str(obj.get("objName") or source_pdf),
        coordinate_space=str(obj.get("pdfCoordinateSpace") or ("sheet" if obj.get("pdfPlacementMode") == "full_sheet" else "body")),
        strict_base=bool(obj.get("pdfBase")),
        rotation=rotation,
    )



def export_page_id_marker(page_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(page_id or "")).strip("_")[:96]
    return f"{PAGE_ID_MARKER_PREFIX}{safe}"


def _object_bounds(obj: dict[str, Any]) -> fitz.Rect | None:
    try:
        width = float(obj.get("width") or 0) * float(obj.get("scaleX") if obj.get("scaleX") is not None else 1)
        height = float(obj.get("height") or 0) * float(obj.get("scaleY") if obj.get("scaleY") is not None else 1)
        rotation = int(round(float(obj.get("angle") or 0))) % 360
        left, top, width, height = _fabric_bounds(
            float(obj.get("left") or 0),
            float(obj.get("top") or 0),
            width,
            height,
            origin_x=str(obj.get("originX") or "left"),
            origin_y=str(obj.get("originY") or "top"),
            rotation=rotation,
        )
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return fitz.Rect(left, top, left + width, top + height)


def _overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    smaller = min(a.get_area(), b.get_area())
    return inter.get_area() / smaller if smaller > 0 else 0.0


def _drawing_page(page: dict[str, Any]) -> bool:
    page_type = str(page.get("pageType") or "").strip().lower()
    if page_type in {"cover", "index", "sheet index", "toc", "data-grid", "table", "matrix"}:
        return False
    if page_type in {"canvas", "hybrid", "image", "layout", "image / layout", "underlay", "pdf"}:
        return True
    family = str(page.get("pageFamily") or page.get("family") or "").lower()
    if any(token in family for token in ("image", "layout", "floor plan", "device location")):
        return True
    blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    return any(
        isinstance(block, dict)
        and str(block.get("type") or "").lower() in {"canvas", "imageplaceholder", "underlayplaceholder"}
        for block in blocks
    )


def _hide_export_object(obj: dict[str, Any], *, remove_pdf_preview: bool = False) -> None:
    obj["visible"] = False
    obj["excludeFromExport"] = True
    if remove_pdf_preview:
        # The clone is disposable. Removing the project-local PNG URL makes it
        # impossible for a renderer regression to paint the editor preview.
        obj["src"] = _TRANSPARENT_EXPORT_PREVIEW
        obj["pdfPreviewExcluded"] = True


def _physical_page_map(output: fitz.Document) -> dict[str, int]:
    mapping: dict[str, int] = {}
    pattern = re.compile(rf"{re.escape(PAGE_ID_MARKER_PREFIX)}([A-Za-z0-9_-]{{1,96}})")
    for index, page in enumerate(output):
        text = page.get_text("text") or ""
        for match in pattern.finditer(text):
            mapping.setdefault(match.group(1), index)
    return mapping


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
    def _recalc_page_numbers_local(doc: dict[str, Any]) -> None:
        pages_local = doc.get("pages") if isinstance(doc.get("pages"), list) else []
        included_local = [page for page in pages_local if isinstance(page, dict) and page.get("include", True)]
        total = len(included_local)
        number = 0
        for page in pages_local:
            if not isinstance(page, dict):
                continue
            if page.get("include", True):
                number += 1
                page["pageNumber"] = number
                page["pageTotal"] = total
            else:
                page["pageNumber"] = None
                page["pageTotal"] = total

    def _normalize_automatic_standalone(doc: dict[str, Any]) -> dict[str, Any]:
        """Refresh managed pages without consulting legacy workbook data."""
        from core.standalone_project import normalize_standalone_project

        stable_timestamp = str(
            doc.get("modified")
            or doc.get("created")
            or "1970-01-01T00:00:00Z"
        )
        return normalize_standalone_project(doc, now=stable_timestamp)

    clone = copy.deepcopy(project)
    standalone = clone.get("projectMode") == "standalone_layout"
    automatic_standalone = standalone and clone.get("managedPagePolicy") != "preserve_existing"
    if automatic_standalone:
        clone = _normalize_automatic_standalone(clone)
    selected = selected_page_ids_from_request(selected_page_ids)
    pages = clone.get("pages") if isinstance(clone.get("pages"), list) else []
    originally_included = {
        str(page.get("id"))
        for page in pages
        if isinstance(page, dict) and page.get("include", True)
    }
    if not selected:
        # A standalone project JSON is authoritative.  In particular, never
        # let a retained legacy ``worksheets`` / ``00_INDEX`` snapshot rewrite
        # the saved sheet codes during export.  Automatic sets were refreshed
        # above solely from their current page manifest; detach-only sets such
        # as SA31 must remain byte-structure preserving in the export clone.
        if not standalone:
            from core.sheet_index_sync import sync_project_sheet_index

            clone = sync_project_sheet_index(clone)
        _recalc_page_numbers_local(clone)
        return clone

    # Explicit selection means exactly those published pages.  Do not silently
    # add Cover or Sheet Index.  If the base Sheet Index itself is selected, it
    # is rebuilt from the selected set and any required TOC continuation pages
    # are retained automatically.
    allowed = set(selected) & originally_included
    selected_base_index = any(
        str(page.get("id")) in allowed
        and is_sheet_index_page(page)
        and not page.get("generatedContinuation")
        for page in pages if isinstance(page, dict)
    )
    for page in pages:
        if isinstance(page, dict):
            page["include"] = str(page.get("id")) in allowed

    if selected_base_index and automatic_standalone:
        # Normalization normally keeps the Cover included according to project
        # settings.  For an exact selected export, reflect the explicit Cover
        # selection while deriving the required index continuation count.
        cover_selected = any(
            str(page.get("id")) in allowed
            and str(page.get("pageType") or "").strip().casefold() == "cover"
            for page in pages
            if isinstance(page, dict)
        )
        clone["coverSettings"] = {
            **dict(clone.get("coverSettings") or {}),
            "include": cover_selected,
        }
        clone = _normalize_automatic_standalone(clone)
        pages = clone.get("pages") if isinstance(clone.get("pages"), list) else []
        generated_index_ids = {
            str(page.get("id"))
            for page in pages
            if isinstance(page, dict)
            and is_sheet_index_page(page)
            and page.get("generatedContinuation")
            and page.get("include", True)
        }
        allowed |= generated_index_ids
    elif selected_base_index and not standalone:
        from core.sheet_index_sync import sync_project_sheet_index

        clone = sync_project_sheet_index(clone)
        pages = clone.get("pages") if isinstance(clone.get("pages"), list) else []
        generated_index_ids = {
            str(page.get("id"))
            for page in pages
            if isinstance(page, dict)
            and is_sheet_index_page(page)
            and page.get("generatedContinuation")
            and page.get("include", True)
        }
        allowed |= generated_index_ids

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("id"))
        page["include"] = page_id in allowed
    _recalc_page_numbers_local(clone)
    return clone


def prepare_vector_export_clone(
    project: dict[str, Any],
    *,
    source_pdf_dir: Path | None = None,
) -> tuple[dict[str, Any], list[VectorPlacement]]:
    """Hide verified PDF previews in an export clone and collect vector placements.

    The operation is deliberately page-aware:
    * PDF objects on Cover / Sheet Index / table pages are hidden and never
      vectorized, preventing a stale overlay from bleeding through a protected page.
    * A raster image underneath the same PDF at the same bounds is treated as a
      comparison/preview duplicate and is hidden in the export clone only.
    * duplicate PDF previews with identical geometry are inserted once.
    """
    clone = copy.deepcopy(project)
    pages = sorted(
        [page for page in clone.get("pages", []) if isinstance(page, dict) and page.get("include", True)],
        key=lambda page: int(page.get("order") or 0),
    )
    placements: list[VectorPlacement] = []
    placement_keys: set[tuple[Any, ...]] = set()
    verified_sources: dict[Path, int] = {}

    for export_index, page in enumerate(pages):
        objects = page.get("canvasObjects") if isinstance(page.get("canvasObjects"), list) else []
        drawing_page = _drawing_page(page)
        strict_pdf_page = str(page.get("pageType") or "").strip().lower() == "pdf"
        strict_base_count = 0

        # Protected pages never receive source-PDF vector content.  Hide any stale
        # direct PDF object in the export clone so it cannot show through the
        # transparent print background used by the vector workflow.
        if not drawing_page:
            for obj in objects:
                if isinstance(obj, dict) and str(obj.get("pdfSource") or "").strip():
                    _hide_export_object(obj, remove_pdf_preview=True)
            continue

        for obj in objects:
            if not isinstance(obj, dict):
                continue
            pdf_source = str(obj.get("pdfSource") or "").strip()
            placement = _placement_from_object(
                obj,
                export_page_index=export_index,
                project_page_id=str(page.get("id") or ""),
            )
            if placement is None:
                if pdf_source:
                    _hide_export_object(obj, remove_pdf_preview=True)
                    raise RuntimeError(
                        "Born-digital PDF base cannot be exported as vector content on "
                        f"project page {page.get('id') or ''}: {pdf_source}. "
                        "Only unmirrored 0, 90, 180, or 270 degree placement is supported."
                    )
                if strict_pdf_page and obj.get("pdfBase") is True:
                    raise RuntimeError(f"Managed PDF base is invalid on project page {page.get('id') or ''}.")
                continue
            if placement.strict_base:
                strict_base_count += 1
            if source_pdf_dir is not None:
                source_path = _resolve_source_pdf(Path(source_pdf_dir), placement.source_pdf)
                if source_path is None:
                    raise RuntimeError(
                        f"Born-digital PDF source is missing for project page {placement.project_page_id}: {placement.source_pdf}"
                    )
                page_count = verified_sources.get(source_path)
                if page_count is None:
                    try:
                        with fitz.open(source_path) as source_doc:
                            page_count = source_doc.page_count
                    except Exception:
                        raise RuntimeError(
                            f"Born-digital PDF source is unreadable for project page {placement.project_page_id}: {placement.source_pdf}"
                        )
                    verified_sources[source_path] = page_count
                if placement.source_page_index < 0 or placement.source_page_index >= page_count:
                    raise RuntimeError(
                        f"Born-digital PDF source page is out of range for project page {placement.project_page_id}."
                    )

            key = (
                placement.project_page_id,
                placement.source_pdf.lower(),
                placement.source_page_index,
                *(round(value, 3) for value in placement.clip),
                round(placement.left, 2),
                round(placement.top, 2),
                round(placement.width, 2),
                round(placement.height, 2),
                placement.rotation,
            )
            if key not in placement_keys:
                placement_keys.add(key)
                placements.append(placement)
            _hide_export_object(obj, remove_pdf_preview=True)

            # If the user stacked the PDF over a screenshot/image of the same
            # drawing for comparison, the opaque raster would otherwise cover the
            # vector content inserted behind the canvas.  Hide only near-identical
            # full-bound image duplicates in the export clone; live project data is
            # untouched.
            pdf_bounds = _object_bounds(obj)
            if pdf_bounds is None:
                continue
            for other in objects:
                if other is obj or not isinstance(other, dict):
                    continue
                if str(other.get("pdfSource") or "").strip():
                    continue
                if str(other.get("type") or "").lower() not in {"image", "fabricimage"}:
                    continue
                other_bounds = _object_bounds(other)
                if other_bounds is None:
                    continue
                body_fraction = min(pdf_bounds.get_area(), other_bounds.get_area()) / max(1.0, SHEET_W * SHEET_H)
                if body_fraction >= 0.30 and _overlap_ratio(pdf_bounds, other_bounds) >= 0.90:
                    _hide_export_object(other)

        if strict_pdf_page and strict_base_count != 1:
            raise RuntimeError(
                f"Managed PDF project page {page.get('id') or ''} requires exactly one vector base; found {strict_base_count}."
            )

    return clone, placements


def audit_export_preview_exclusion(
    export_project: dict[str, Any],
    placements: Iterable[VectorPlacement],
) -> dict[str, Any]:
    """Fail if a born-digital PDF preview can still reach print output."""
    pdf_objects: list[tuple[str, dict[str, Any]]] = []
    for page in export_project.get("pages", []):
        if not isinstance(page, dict) or not page.get("include", True) or not _drawing_page(page):
            continue
        for obj in page.get("canvasObjects", []):
            if isinstance(obj, dict) and str(obj.get("pdfSource") or "").strip():
                pdf_objects.append((str(page.get("id") or ""), obj))
    exposed = [
        page_id
        for page_id, obj in pdf_objects
        if obj.get("visible") is not False
        or obj.get("excludeFromExport") is not True
        or obj.get("pdfPreviewExcluded") is not True
        or obj.get("src") != _TRANSPARENT_EXPORT_PREVIEW
    ]
    if exposed:
        raise RuntimeError(
            "Managed PDF preview exclusion failed for project page(s): "
            + ", ".join(sorted(set(exposed)))
        )
    placement_list = list(placements)
    if len(placement_list) > len(pdf_objects):
        raise RuntimeError("Vector placement count exceeds the number of imported PDF bases.")
    return {
        "pdfPreviewObjects": len(pdf_objects),
        "excludedPreviewObjects": len(pdf_objects),
        "vectorPlacements": len(placement_list),
        "deduplicatedPreviewObjects": len(pdf_objects) - len(placement_list),
        "previewRasterAllowed": False,
    }

def _resolve_source_pdf(source_pdf_dir: Path, name: str) -> Path | None:
    if not _SAFE_PDF_NAME.fullmatch(name):
        return None
    root = source_pdf_dir.resolve()
    candidate = (root / name).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def _prune_source_in_worker(
    source_path: Path,
    source_page_index: int,
    clip: fitz.Rect,
    output_path: Path,
) -> dict[str, Any]:
    """Prune one huge engineering page in an isolated process.

    MuPDF's display-list store retains memory after redaction. A separate worker
    guarantees that a series of million-path crops cannot accumulate enough
    retained memory to terminate the live server.
    """
    worker = Path(__file__).with_name("pdf_prune_worker.py")
    process = subprocess.run(
        [
            sys.executable,
            str(worker),
            "--source", str(source_path),
            "--page", str(source_page_index),
            "--clip", ",".join(f"{value:.8f}" for value in clip),
            "--output", str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if process.returncode != 0 or not output_path.is_file():
        detail = (process.stderr or process.stdout or "PDF crop worker failed")[-3000:]
        raise RuntimeError(f"Could not prune source PDF crop (worker exit {process.returncode}): {detail}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"PDF crop worker returned invalid diagnostics: {process.stdout[-1000:]}") from exc


def _contained_rect(container: fitz.Rect, source: fitz.Rect) -> fitz.Rect:
    if source.width <= 0 or source.height <= 0:
        return fitz.Rect()
    scale = min(container.width / source.width, container.height / source.height)
    width = source.width * scale
    height = source.height * scale
    left = container.x0 + (container.width - width) / 2.0
    top = container.y0 + (container.height - height) / 2.0
    return fitz.Rect(left, top, left + width, top + height)


def _destination_rect(
    page: fitz.Page,
    placement: VectorPlacement,
    *,
    source_clip: fitz.Rect | None = None,
) -> fitz.Rect:
    if placement.coordinate_space == "sheet" and placement.strict_base:
        clip = source_clip or fitz.Rect(*placement.clip)
        return _contained_rect(fitz.Rect(page.rect), clip)
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
    pruned_paths: dict[tuple[Any, ...], Path | None] = {}
    pruned_docs: dict[tuple[Any, ...], fitz.Document] = {}
    pruning_audit: dict[tuple[Any, ...], dict[str, Any]] = {}
    inserted = 0
    skipped: list[dict[str, Any]] = []
    physical_page_map = _physical_page_map(output)
    try:
        with tempfile.TemporaryDirectory(prefix="s360_pdf_vector_crop_", dir=pdf_path.parent) as raw_pruned:
            pruned_root = Path(raw_pruned)
            for placement in placement_list:
                mapped_index = physical_page_map.get(placement.project_page_id)
                if mapped_index is None:
                    # Marker-aware exports must never guess.  The ordinal fallback is
                    # retained only for older one-off tests/PDFs that contain no page
                    # identity markers at all.
                    if physical_page_map:
                        skipped.append({**placement.to_dict(), "reason": "project page marker is missing from export"})
                        continue
                    mapped_index = placement.export_page_index
                if mapped_index < 0 or mapped_index >= output.page_count:
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

                destination = _destination_rect(
                    output[mapped_index],
                    placement,
                    source_clip=clip,
                )
                if destination.is_empty or destination.width <= 0 or destination.height <= 0:
                    skipped.append({**placement.to_dict(), "reason": "destination is empty"})
                    continue
                prune_key = (
                    source_path,
                    placement.source_page_index,
                    *(round(value, 4) for value in clip),
                )
                if prune_key not in pruned_paths:
                    pruned_path = pruned_root / f"crop-{len(pruned_paths) + 1:03d}.pdf"
                    try:
                        detail = _prune_source_in_worker(
                            source_path,
                            placement.source_page_index,
                            clip,
                            pruned_path,
                        )
                        detail["mode"] = "pruned-vector"
                        pruning_audit[prune_key] = detail
                        pruned_paths[prune_key] = pruned_path
                        pruned_docs[prune_key] = fitz.open(pruned_path)
                    except RuntimeError as exc:
                        pruned_path.unlink(missing_ok=True)
                        pruning_audit[prune_key] = {
                            "mode": "full-source-vector-fallback",
                            "reason": str(exc),
                            "cropFraction": round(clip.get_area() / max(1.0, source_page.rect.get_area()), 6),
                        }
                        pruned_paths[prune_key] = None
                pruned_path = pruned_paths[prune_key]
                if pruned_path is None:
                    output[mapped_index].show_pdf_page(
                        destination,
                        source,
                        placement.source_page_index,
                        clip=clip,
                        keep_proportion=placement.coordinate_space == "sheet" and placement.strict_base,
                        overlay=False,
                        rotate=placement.rotation,
                    )
                else:
                    pruned_source = pruned_docs[prune_key]
                    output[mapped_index].show_pdf_page(
                        destination,
                        pruned_source,
                        0,
                        keep_proportion=placement.coordinate_space == "sheet" and placement.strict_base,
                        overlay=False,
                        rotate=placement.rotation,
                    )
                inserted += 1

            temp_path = pdf_path.with_name(f"{pdf_path.stem}.vectorized.tmp.pdf")
            output.save(temp_path, garbage=4, deflate=True, clean=True)
            output.close()
            output = None
            for source in pruned_docs.values():
                source.close()
            pruned_docs.clear()
    finally:
        if output is not None:
            output.close()
        for source in pruned_docs.values():
            source.close()
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
        "pageIdMap": physical_page_map,
        "placements": [placement.to_dict() for placement in placement_list],
        "prunedSourceVariants": sum(path is not None for path in pruned_paths.values()),
        "fullSourceVectorFallbacks": sum(path is None for path in pruned_paths.values()),
        "pruning": list(pruning_audit.values()),
        "allVectorBasesInsertedExactlyOnce": inserted == len(placement_list) and not skipped,
    }
