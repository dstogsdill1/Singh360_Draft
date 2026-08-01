"""Transactional, project-local PDF drawing-page import.

This module deliberately has no Flask dependency.  ``server.py`` can use
``preview_pdf`` for the selection UI and ``commit_pdf_import`` for the final
project mutation.  A commit validates and renders every requested page before
installing content-addressed source/preview assets and saving ``project.json``.

The original PDF is retained in the Singh360 project package because final PDF
export can restore born-digital vectors from it.  Replacing a revised PDF never
overwrites an earlier source revision and never adds or removes unmatched pages.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import fitz  # PyMuPDF

from core.pdf_renderer import render_page_to_png
from core.project_store import ProjectStore


SHEET_WIDTH_PX = 1632.0
SHEET_HEIGHT_PX = 1056.0
BODY_WIDTH_PX = 1598.0
BODY_HEIGHT_PX = 866.0
MIN_RENDER_DPI = 300
MAX_RENDER_DPI = 600

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_VALID_ACTIONS = {"add", "replace"}
_PLACEMENT_ALIASES = {
    "fit_body": "fit_body",
    "fit_inside_drawing_body": "fit_body",
    "fit inside drawing body": "fit_body",
    "full_sheet": "full_sheet",
    "full_sheet_already_formatted": "full_sheet",
    "full sheet already formatted": "full_sheet",
}

PdfImportProgressCallback = Callable[[Mapping[str, Any]], None]


def _report_progress(
    callback: PdfImportProgressCallback | None,
    *,
    phase: str,
    completed: int,
    total: int,
    message: str,
    page_index: int | None = None,
) -> None:
    """Publish best-effort progress without weakening the import transaction."""
    if callback is None:
        return
    payload: dict[str, Any] = {
        "phase": phase,
        "completed": int(completed),
        "total": int(total),
        "message": message,
    }
    if page_index is not None:
        payload["pageIndex"] = int(page_index)
        payload["pageNumber"] = int(page_index) + 1
    try:
        callback(payload)
    except Exception:
        # A disconnected progress observer must never abort or partially alter
        # an otherwise valid project-local import.
        return


class PdfPageImportError(RuntimeError):
    """Structured PDF import failure suitable for an exact API response."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        phase: str,
        page_index: int | None = None,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.page_index = page_index
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": str(self),
            "code": self.code,
            "phase": self.phase,
        }
        if self.page_index is not None:
            payload["pageIndex"] = self.page_index
        if self.detail:
            payload["detail"] = self.detail
        return payload


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PdfPageImportError(
            "The PDF source could not be read.",
            code="source_read_failed",
            phase="validate",
            detail=str(exc),
        ) from exc
    return digest.hexdigest()


def _clean_original_name(value: str | None, fallback: Path) -> str:
    name = Path(str(value or fallback.name)).name.strip() or "imported.pdf"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def _page_fingerprint(page: fitz.Page) -> str:
    """Stable visual fingerprint used to suggest revised-page matches."""
    rect = page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), colorspace=fitz.csGRAY, alpha=False)
    header = (
        f"{rect.width:.4f}|{rect.height:.4f}|{int(page.rotation or 0)}|"
        f"{pix.width}|{pix.height}|"
    ).encode("ascii")
    return hashlib.sha256(header + bytes(pix.samples)).hexdigest()


def _inspect_pdf(
    pdf_path: Path,
    *,
    original_name: str | None,
    include_thumbnails: bool,
    thumbnail_size: int,
) -> dict[str, Any]:
    source = Path(pdf_path)
    if not source.is_file():
        raise PdfPageImportError(
            "The PDF source was not found.",
            code="source_not_found",
            phase="validate",
            detail=str(source),
        )
    source_sha = _sha256(source)
    try:
        document = fitz.open(source)
    except Exception as exc:  # noqa: BLE001
        raise PdfPageImportError(
            "The selected file is not a readable PDF.",
            code="invalid_pdf",
            phase="validate",
            detail=str(exc),
        ) from exc

    try:
        if document.needs_pass:
            raise PdfPageImportError(
                "Password-protected PDFs are not supported for drawing-page import.",
                code="password_required",
                phase="validate",
            )
        if document.page_count < 1:
            raise PdfPageImportError(
                "The PDF contains no pages.",
                code="empty_pdf",
                phase="validate",
            )
        pages: list[dict[str, Any]] = []
        for index, page in enumerate(document):
            try:
                rect = page.rect
                item: dict[str, Any] = {
                    "index": index,
                    "pageNumber": index + 1,
                    "widthPt": round(float(rect.width), 3),
                    "heightPt": round(float(rect.height), 3),
                    "widthIn": round(float(rect.width) / 72.0, 4),
                    "heightIn": round(float(rect.height) / 72.0, 4),
                    "rotation": int(page.rotation or 0),
                    "fingerprint": _page_fingerprint(page),
                }
                if include_thumbnails:
                    maximum = max(float(rect.width), float(rect.height), 1.0)
                    scale = max(0.01, float(thumbnail_size) / maximum)
                    thumb = page.get_pixmap(
                        matrix=fitz.Matrix(scale, scale),
                        alpha=False,
                    )
                    encoded = base64.b64encode(thumb.tobytes("png")).decode("ascii")
                    item.update({
                        "thumbnailWidth": thumb.width,
                        "thumbnailHeight": thumb.height,
                        "thumbnailDataUrl": f"data:image/png;base64,{encoded}",
                    })
                pages.append(item)
            except PdfPageImportError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise PdfPageImportError(
                    f"PDF page {index + 1} could not be inspected.",
                    code="page_inspection_failed",
                    phase="preview",
                    page_index=index,
                    detail=str(exc),
                ) from exc
    finally:
        document.close()

    return {
        "ok": True,
        "originalFileName": _clean_original_name(original_name, source),
        "sha256": source_sha,
        "contentAddressedName": f"pdf_{source_sha}.pdf",
        "pageCount": len(pages),
        "pages": pages,
    }


def preview_pdf(
    pdf_path: str | Path,
    *,
    original_name: str | None = None,
    thumbnail_size: int = 240,
) -> dict[str, Any]:
    """Return validated PDF metadata and base64 thumbnails for a picker UI."""
    size = max(96, min(600, int(thumbnail_size)))
    return _inspect_pdf(
        Path(pdf_path),
        original_name=original_name,
        include_thumbnails=True,
        thumbnail_size=size,
    )


def existing_pdf_import_groups(
    project: Mapping[str, Any],
    *,
    original_name: str | None = None,
) -> list[dict[str, Any]]:
    """Return every managed PDF import group in deterministic project order.

    The uploaded filename is only a ranking hint.  Renaming a revised PDF must
    not hide the existing import from the Replace Existing Pages workflow.
    Parallel page arrays deliberately retain the stable page ID, prior source
    index, and visual fingerprint needed for deterministic one-to-one mapping.
    """

    expected_name = _clean_original_name(original_name, Path("imported.pdf")).casefold()
    raw_pages = project.get("pages") if isinstance(project, Mapping) else []
    pages = raw_pages if isinstance(raw_pages, list) else []
    decorated = list(enumerate(page for page in pages if isinstance(page, Mapping)))

    def page_order(item: tuple[int, Mapping[str, Any]]) -> tuple[float, int]:
        position, page = item
        try:
            order = float(page.get("order") or position + 1)
        except (TypeError, ValueError):
            order = float(position + 1)
        return order, position

    groups: dict[str, dict[str, Any]] = {}
    for _, page in sorted(decorated, key=page_order):
        source = page.get("sourceImport") if isinstance(page.get("sourceImport"), Mapping) else {}
        if str(source.get("type") or "").strip().casefold() != "pdf":
            continue
        group_id = str(source.get("importGroupId") or source.get("groupId") or "").strip()
        page_id = str(page.get("id") or "").strip()
        if not group_id or not page_id:
            continue
        source_name = str(source.get("originalFileName") or source.get("originalName") or "").strip()
        group = groups.setdefault(
            group_id,
            {
                "groupId": group_id,
                "originalName": source_name or "Imported PDF",
                "pageIds": [],
                "pageIndices": [],
                "pageFingerprints": [],
                "revision": 0,
                "sameName": False,
            },
        )
        group["pageIds"].append(page_id)
        try:
            source_index = int(source.get("sourcePageIndex", source.get("pageIndex", 0)) or 0)
        except (TypeError, ValueError):
            source_index = 0
        group["pageIndices"].append(source_index)
        group["pageFingerprints"].append(str(source.get("pageFingerprint") or "").strip())
        try:
            revision = int(source.get("revision") or 1)
        except (TypeError, ValueError):
            revision = 1
        group["revision"] = max(int(group["revision"]), revision)
        if source_name and source_name.casefold() == expected_name:
            group["sameName"] = True

    return sorted(
        groups.values(),
        key=lambda group: (
            not bool(group["sameName"]),
            str(group["originalName"]).casefold(),
            str(group["groupId"]),
        ),
    )


def _normalize_placement(value: str | None, *, default: str = "fit_body") -> str:
    raw = str(value or default).strip().lower()
    placement = _PLACEMENT_ALIASES.get(raw)
    if placement is None:
        raise PdfPageImportError(
            "Choose Full Sheet Already Formatted or Fit Inside Drawing Body.",
            code="invalid_placement_mode",
            phase="validate",
            detail=str(value or ""),
        )
    return placement


def _normalize_selected(indices: Iterable[int] | None, page_count: int) -> list[int]:
    if indices is None:
        return list(range(page_count))
    selected: list[int] = []
    seen: set[int] = set()
    try:
        raw_values = list(indices)
    except TypeError as exc:
        raise PdfPageImportError(
            "Selected PDF pages must be a list of zero-based page indices.",
            code="invalid_page_selection",
            phase="validate",
            detail=str(exc),
        ) from exc
    if not raw_values:
        raise PdfPageImportError(
            "Select at least one PDF page to import.",
            code="empty_page_selection",
            phase="validate",
        )
    for raw in raw_values:
        if isinstance(raw, int) and not isinstance(raw, bool):
            index = raw
        elif isinstance(raw, str) and re.fullmatch(r"\d+", raw.strip()):
            index = int(raw.strip())
        else:
            index = -1
        if index < 0 or index >= page_count:
            raise PdfPageImportError(
                f"PDF page index {raw!r} is outside the 0-{page_count - 1} range.",
                code="page_out_of_range",
                phase="validate",
                page_index=index if index >= 0 else None,
            )
        if index not in seen:
            seen.add(index)
            selected.append(index)
    return selected


def _safe_group_id(value: str | None) -> str:
    group_id = str(value or f"pdfimp_{uuid.uuid4().hex[:16]}").strip()
    if not _SAFE_ID.fullmatch(group_id):
        raise PdfPageImportError(
            "The PDF import group ID is invalid.",
            code="invalid_import_group",
            phase="validate",
            detail=group_id,
        )
    return group_id


def _copy_without_overwrite(source: Path, destination: Path, expected_sha: str) -> bool:
    """Install ``source`` exclusively; return True only when newly created."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256(destination) != expected_sha:
            raise PdfPageImportError(
                "A content-addressed import asset has unexpected contents.",
                code="content_address_collision",
                phase="install",
                detail=str(destination),
            )
        return False
    created = False
    try:
        with source.open("rb") as incoming, destination.open("xb") as outgoing:
            created = True
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if _sha256(destination) != expected_sha:
            raise PdfPageImportError(
                "A copied PDF import asset failed SHA-256 validation.",
                code="installed_hash_mismatch",
                phase="install",
                detail=str(destination),
            )
    except FileExistsError:
        if _sha256(destination) != expected_sha:
            raise PdfPageImportError(
                "A content-addressed import asset has unexpected contents.",
                code="content_address_collision",
                phase="install",
                detail=str(destination),
            )
        return False
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return True


def _asset_geometry(
    output_width: int,
    output_height: int,
    placement_mode: str,
) -> dict[str, float | str | bool]:
    if placement_mode == "full_sheet":
        # Fabric still uses drawing-body coordinates while SheetFrame displays
        # that canvas across the complete physical sheet.  Compensate for the
        # different X/Y display scales so the final on-screen and raster-export
        # geometry is a centered contain operation, never a stretch or crop.
        sheet_scale = min(
            SHEET_WIDTH_PX / max(1, output_width),
            SHEET_HEIGHT_PX / max(1, output_height),
        )
        displayed_width = output_width * sheet_scale
        displayed_height = output_height * sheet_scale
        display_scale_x = SHEET_WIDTH_PX / BODY_WIDTH_PX
        display_scale_y = SHEET_HEIGHT_PX / BODY_HEIGHT_PX
        return {
            "left": ((SHEET_WIDTH_PX - displayed_width) / 2.0) / display_scale_x,
            "top": ((SHEET_HEIGHT_PX - displayed_height) / 2.0) / display_scale_y,
            "scaleX": (displayed_width / display_scale_x) / max(1, output_width),
            "scaleY": (displayed_height / display_scale_y) / max(1, output_height),
            "pdfCoordinateSpace": "sheet",
            "suppressTitleBlock": True,
        }
    else:
        target_w, target_h = BODY_WIDTH_PX, BODY_HEIGHT_PX
        coordinate_space = "body"
    scale = min(target_w / max(1, output_width), target_h / max(1, output_height))
    rendered_w = output_width * scale
    rendered_h = output_height * scale
    return {
        "left": (target_w - rendered_w) / 2.0,
        "top": (target_h - rendered_h) / 2.0,
        "scaleX": scale,
        "scaleY": scale,
        "pdfCoordinateSpace": coordinate_space,
        "suppressTitleBlock": placement_mode == "full_sheet",
    }


def _base_object(
    *,
    project_id: str,
    source_name: str,
    source_id: str,
    source_page_index: int,
    output_name: str,
    output_width: int,
    output_height: int,
    dpi: int,
    group_id: str,
    placement_mode: str,
    page_fingerprint: str,
    object_id: str | None = None,
) -> dict[str, Any]:
    geometry = _asset_geometry(output_width, output_height, placement_mode)
    return {
        "type": "image",
        "objectId": object_id or f"obj_{uuid.uuid4().hex[:16]}",
        "objName": f"PDF page {source_page_index + 1}",
        "src": f"/api/assets/{project_id}/{output_name}",
        "left": geometry["left"],
        "top": geometry["top"],
        "width": output_width,
        "height": output_height,
        "scaleX": geometry["scaleX"],
        "scaleY": geometry["scaleY"],
        "originX": "left",
        "originY": "top",
        "opacity": 1,
        "visible": True,
        "selectable": True,
        "evented": True,
        "lockMovementX": True,
        "lockMovementY": True,
        "lockScalingX": True,
        "lockScalingY": True,
        "lockRotation": True,
        "pdfBase": True,
        "pdfImportGroupId": group_id,
        "pdfSourceId": source_id,
        "pdfSource": source_name,
        "pdfPage": source_page_index,
        "pdfDpi": dpi,
        "pdfPlacementMode": placement_mode,
        "pdfCoordinateSpace": geometry["pdfCoordinateSpace"],
        "pdfPageFingerprint": page_fingerprint,
    }


def _source_import(
    *,
    source_record: Mapping[str, Any],
    page_meta: Mapping[str, Any],
    source_page_index: int,
    asset_name: str,
    dpi: int,
    placement_mode: str,
    imported_at: str,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = {
        "type": "pdf",
        "importGroupId": source_record["importGroupId"],
        "sourceId": source_record["id"],
        "originalFileName": source_record["originalFileName"],
        "projectLocalPath": source_record["projectLocalPath"],
        "sha256": source_record["sha256"],
        "sourcePageIndex": source_page_index,
        "sourcePageNumber": source_page_index + 1,
        "pageFingerprint": page_meta["fingerprint"],
        "placementMode": placement_mode,
        "renderDpi": dpi,
        "renderAssetPath": f"assets/images/{asset_name}",
        "renderAssetUrl": f"/api/assets/{source_record['projectId']}/{asset_name}",
        "importedAt": imported_at,
        "revision": source_record["revision"],
    }
    if previous:
        value["previousSourceId"] = previous.get("sourceId", "")
        value["previousSha256"] = previous.get("sha256", "")
        value["previousPageIndex"] = previous.get("sourcePageIndex")
    return value


def _metadata_for_page(
    page_metadata: Mapping[int | str, Mapping[str, Any]] | None,
    index: int,
) -> Mapping[str, Any]:
    if not page_metadata:
        return {}
    value = page_metadata.get(index) or page_metadata.get(str(index))
    return value if isinstance(value, Mapping) else {}


def _new_page(
    *,
    project_id: str,
    original_stem: str,
    source_record: Mapping[str, Any],
    page_meta: Mapping[str, Any],
    source_page_index: int,
    asset: Mapping[str, Any],
    dpi: int,
    placement_mode: str,
    order: float,
    supplied_metadata: Mapping[str, Any],
    imported_at: str,
) -> dict[str, Any]:
    page_id = f"page_{uuid.uuid4().hex[:16]}"
    code = str(supplied_metadata.get("sheetCode") or f"PDF {source_page_index + 1}").strip()
    title = str(
        supplied_metadata.get("sheetTitle")
        or supplied_metadata.get("title")
        or f"{original_stem} — Page {source_page_index + 1}"
    ).strip()
    base = _base_object(
        project_id=project_id,
        source_name=str(source_record["storedFileName"]),
        source_id=str(source_record["id"]),
        source_page_index=source_page_index,
        output_name=str(asset["name"]),
        output_width=int(asset["outputWidth"]),
        output_height=int(asset["outputHeight"]),
        dpi=dpi,
        group_id=str(source_record["importGroupId"]),
        placement_mode=placement_mode,
        page_fingerprint=str(page_meta.get("fingerprint") or ""),
    )
    return {
        "id": page_id,
        "order": order,
        "include": bool(supplied_metadata.get("include", True)),
        "publishStatus": "YES" if bool(supplied_metadata.get("include", True)) else "NO",
        "sheetCode": code,
        "displaySheetCode": code,
        "sheetTitle": title,
        "sheetTab": str(supplied_metadata.get("sheetTab") or title)[:31],
        "pageType": "pdf",
        "pageFamily": "pdf",
        "sourceMode": "imported",
        "syncDirection": "none",
        "template": "ansi-b-standard",
        "templateId": "ansi-b-standard",
        "renderMode": "pdf_page",
        "renderProfile": "pdf_full_sheet" if placement_mode == "full_sheet" else "pdf_fit_body",
        "normalizedHeaderStyle": "none",
        "pdfPlacementMode": placement_mode,
        "suppressTitleBlock": placement_mode == "full_sheet",
        "blocks": [{"id": f"block_{uuid.uuid4().hex[:16]}", "type": "canvas"}],
        "canvasObjects": [base],
        "assets": [{"id": asset["id"], "url": asset["url"], "type": "pdf-preview"}],
        "notes": str(supplied_metadata.get("notes") or ""),
        "createdAt": imported_at,
        "modifiedAt": imported_at,
        "sourceImport": _source_import(
            source_record=source_record,
            page_meta=page_meta,
            source_page_index=source_page_index,
            asset_name=str(asset["name"]),
            dpi=dpi,
            placement_mode=placement_mode,
            imported_at=imported_at,
        ),
    }


def _insertion_orders(
    pages: list[dict[str, Any]],
    count: int,
    insert_after_page_id: str | None,
) -> tuple[int, list[float]]:
    if not pages:
        return 0, [float(index + 1) for index in range(count)]
    if insert_after_page_id:
        position = next(
            (index for index, page in enumerate(pages) if str(page.get("id")) == insert_after_page_id),
            -1,
        )
        if position < 0:
            raise PdfPageImportError(
                "The requested insertion page was not found.",
                code="insert_after_page_not_found",
                phase="validate",
                detail=insert_after_page_id,
            )
        previous_order = float(pages[position].get("order") or position + 1)
        if position + 1 < len(pages):
            next_order = float(pages[position + 1].get("order") or previous_order + 1)
            if next_order <= previous_order:
                next_order = previous_order + 1.0
            step = (next_order - previous_order) / (count + 1)
            return position + 1, [previous_order + step * (index + 1) for index in range(count)]
        return len(pages), [previous_order + index + 1 for index in range(count)]
    maximum = max(float(page.get("order") or 0) for page in pages)
    return len(pages), [maximum + index + 1 for index in range(count)]


def _find_pdf_base(page: Mapping[str, Any], group_id: str) -> tuple[int, dict[str, Any]]:
    objects = page.get("canvasObjects") if isinstance(page.get("canvasObjects"), list) else []
    matches = [
        (index, obj)
        for index, obj in enumerate(objects)
        if isinstance(obj, dict)
        and obj.get("pdfBase") is True
        and str(obj.get("pdfImportGroupId") or "") == group_id
    ]
    if len(matches) != 1:
        raise PdfPageImportError(
            "The existing PDF drawing page does not have one unambiguous base object.",
            code="pdf_base_not_unique",
            phase="replace",
            detail=str(page.get("id") or ""),
        )
    if not str(matches[0][1].get("objectId") or "").strip():
        raise PdfPageImportError(
            "The existing PDF base object is missing its stable object ID.",
            code="pdf_base_id_missing",
            phase="replace",
            detail=str(page.get("id") or ""),
        )
    return matches[0]


def _asset_sha_record(path: Path, *, asset_id: str, project_id: str) -> dict[str, Any]:
    return {
        "id": asset_id,
        "type": "pdf-preview",
        "name": path.name,
        "path": f"assets/images/{path.name}",
        "url": f"/api/assets/{project_id}/{path.name}",
        "sha256": _sha256(path),
    }


def commit_pdf_import(
    store: ProjectStore,
    project_id: str,
    pdf_path: str | Path,
    *,
    original_name: str | None = None,
    selected_page_indices: Iterable[int] | None = None,
    placement_mode: str | None = None,
    action: str = "add",
    replace_mapping: Mapping[str, int] | None = None,
    import_group_id: str | None = None,
    page_metadata: Mapping[int | str, Mapping[str, Any]] | None = None,
    insert_after_page_id: str | None = None,
    dpi: int = MIN_RENDER_DPI,
    project_transform: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
    progress_callback: PdfImportProgressCallback | None = None,
) -> dict[str, Any]:
    """Atomically add or explicitly replace project-local PDF drawing pages.

    ``selected_page_indices=None`` means all pages for ``action="add"``.  A
    replacement requires an explicit ``existing page ID -> revised PDF index``
    mapping and never adds, deletes, or changes unmatched pages.
    """
    action = str(action or "").strip().lower()
    if action not in _VALID_ACTIONS:
        raise PdfPageImportError(
            "PDF import action must be Add as New Pages or Replace Existing Pages.",
            code="invalid_import_action",
            phase="validate",
            detail=action,
        )
    try:
        dpi = int(dpi)
    except (TypeError, ValueError) as exc:
        raise PdfPageImportError(
            "PDF render DPI must be a number.",
            code="invalid_render_dpi",
            phase="validate",
            detail=str(dpi),
        ) from exc
    if dpi < MIN_RENDER_DPI or dpi > MAX_RENDER_DPI:
        raise PdfPageImportError(
            f"PDF render DPI must be between {MIN_RENDER_DPI} and {MAX_RENDER_DPI}.",
            code="invalid_render_dpi",
            phase="validate",
            detail=str(dpi),
        )

    source_path = Path(pdf_path)
    inspection = _inspect_pdf(
        source_path,
        original_name=original_name,
        include_thumbnails=False,
        thumbnail_size=240,
    )
    page_count = int(inspection["pageCount"])
    try:
        mapping = {str(key): int(value) for key, value in (replace_mapping or {}).items()}
    except (TypeError, ValueError) as exc:
        raise PdfPageImportError(
            "Replacement mappings must use existing page IDs and zero-based PDF page indices.",
            code="invalid_replace_mapping",
            phase="validate",
            detail=str(exc),
        ) from exc
    if action == "replace":
        if not mapping:
            raise PdfPageImportError(
                "Choose exactly which existing PDF pages the revised pages replace.",
                code="replace_mapping_required",
                phase="validate",
            )
        mapped_indices = list(mapping.values())
        if len(set(mapped_indices)) != len(mapped_indices):
            raise PdfPageImportError(
                "One revised PDF page cannot replace more than one existing page.",
                code="duplicate_replace_source_page",
                phase="validate",
            )
        selected = _normalize_selected(
            mapped_indices if selected_page_indices is None else selected_page_indices,
            page_count,
        )
        if set(selected) != set(mapped_indices):
            raise PdfPageImportError(
                "The selected revised pages and explicit replacement mapping do not match.",
                code="replace_selection_mismatch",
                phase="validate",
            )
    else:
        if mapping:
            raise PdfPageImportError(
                "Replacement mappings are not accepted when adding pages.",
                code="unexpected_replace_mapping",
                phase="validate",
            )
        selected = _normalize_selected(selected_page_indices, page_count)

    total_pages = len(selected)
    _report_progress(
        progress_callback,
        phase="validate",
        completed=0,
        total=total_pages,
        message="Validating the selected PDF pages",
    )

    loaded = store.load(project_id)
    if loaded is None:
        raise PdfPageImportError(
            "The Singh360 project was not found.",
            code="project_not_found",
            phase="validate",
            detail=project_id,
        )
    project_dir = store.find_dir(project_id)
    if project_dir is None:
        raise PdfPageImportError(
            "The Singh360 project package folder was not found.",
            code="project_package_not_found",
            phase="validate",
            detail=project_id,
        )
    original_project = copy.deepcopy(loaded)
    project = copy.deepcopy(loaded)
    pages = project.get("pages") if isinstance(project.get("pages"), list) else []
    pages = [copy.deepcopy(page) for page in pages if isinstance(page, dict)]

    group_id = _safe_group_id(import_group_id)
    existing_by_id = {str(page.get("id") or ""): page for page in pages}
    if action == "replace":
        mapped_pages: list[dict[str, Any]] = []
        discovered_groups: set[str] = set()
        for page_id in mapping:
            page = existing_by_id.get(page_id)
            if page is None:
                raise PdfPageImportError(
                    "A mapped existing PDF page was not found.",
                    code="replace_page_not_found",
                    phase="validate",
                    detail=page_id,
                )
            source_import = page.get("sourceImport") if isinstance(page.get("sourceImport"), dict) else {}
            existing_group = str(source_import.get("importGroupId") or "")
            if not existing_group:
                raise PdfPageImportError(
                    "A mapped page is not a managed PDF import page.",
                    code="replace_page_not_managed",
                    phase="validate",
                    detail=page_id,
                )
            discovered_groups.add(existing_group)
            mapped_pages.append(page)
        if len(discovered_groups) != 1:
            raise PdfPageImportError(
                "One replacement operation cannot span multiple PDF import groups.",
                code="replace_group_mismatch",
                phase="validate",
                detail=", ".join(sorted(discovered_groups)),
            )
        discovered_group = next(iter(discovered_groups))
        if import_group_id is not None and group_id != discovered_group:
            raise PdfPageImportError(
                "The replacement mapping does not belong to the requested PDF import group.",
                code="replace_group_mismatch",
                phase="validate",
                detail=f"{group_id} != {discovered_group}",
            )
        group_id = discovered_group

    group_revisions = [
        int((page.get("sourceImport") or {}).get("revision") or 0)
        for page in pages
        if isinstance(page.get("sourceImport"), dict)
        and str(page["sourceImport"].get("importGroupId") or "") == group_id
    ]
    revision = (max(group_revisions) + 1) if group_revisions else 1
    imported_at = _utcnow()
    source_id = f"pdfsrc_{uuid.uuid4().hex[:16]}"
    source_name = str(inspection["contentAddressedName"])
    source_record: dict[str, Any] = {
        "id": source_id,
        "type": "pdf",
        "projectId": project_id,
        "importGroupId": group_id,
        "revision": revision,
        "originalFileName": inspection["originalFileName"],
        "storedFileName": source_name,
        "projectLocalPath": f"sources/pdf/{source_name}",
        "sha256": inspection["sha256"],
        "pageCount": page_count,
        "selectedPageIndices": list(selected),
        "importedAt": imported_at,
        "status": "project-local",
    }

    stage_dir = Path(tempfile.mkdtemp(prefix=".pdf-import-", dir=project_dir))
    staged_assets: dict[int, dict[str, Any]] = {}
    created_files: list[Path] = []
    project_save_completed = False
    try:
        page_meta_by_index = {int(item["index"]): item for item in inspection["pages"]}
        _report_progress(
            progress_callback,
            phase="render",
            completed=0,
            total=total_pages,
            message="Rendering full-quality project-local PDF pages",
        )
        for completed, index in enumerate(selected, start=1):
            suffix = re.sub(r"[^A-Za-z0-9]+", "", group_id)[-16:] or uuid.uuid4().hex[:8]
            asset_name = (
                f"pdf_{suffix}_{str(inspection['sha256'])[:16]}_"
                f"p{index + 1:04d}_r{revision}_{dpi}dpi.png"
            )
            staged_path = stage_dir / asset_name
            try:
                result = render_page_to_png(source_path, index, staged_path, dpi=dpi)
            except Exception as exc:  # noqa: BLE001
                raise PdfPageImportError(
                    f"PDF page {index + 1} could not be rendered.",
                    code="page_render_failed",
                    phase="render",
                    page_index=index,
                    detail=str(exc),
                ) from exc
            if not result.get("ok"):
                raise PdfPageImportError(
                    f"PDF page {index + 1} could not be rendered.",
                    code="page_render_failed",
                    phase="render",
                    page_index=index,
                    detail=str(result.get("error") or "unknown render error"),
                )
            meta = page_meta_by_index[index]
            effective_x = int(result["outputWidth"]) / max(float(meta["widthIn"]), 0.001)
            effective_y = int(result["outputHeight"]) / max(float(meta["heightIn"]), 0.001)
            if min(effective_x, effective_y) < MIN_RENDER_DPI - 1:
                raise PdfPageImportError(
                    f"PDF page {index + 1} rendered below {MIN_RENDER_DPI} DPI.",
                    code="render_quality_too_low",
                    phase="render",
                    page_index=index,
                    detail=f"{effective_x:.1f}x{effective_y:.1f} DPI",
                )
            asset_id = f"pdfasset_{uuid.uuid4().hex[:16]}"
            staged_assets[index] = {
                "id": asset_id,
                "name": asset_name,
                "path": staged_path,
                "sha256": _sha256(staged_path),
                "url": f"/api/assets/{project_id}/{asset_name}",
                "outputWidth": int(result["outputWidth"]),
                "outputHeight": int(result["outputHeight"]),
                "effectiveDpiX": effective_x,
                "effectiveDpiY": effective_y,
            }

            _report_progress(
                progress_callback,
                phase="render",
                completed=completed,
                total=total_pages,
                message="Rendering full-quality project-local PDF pages",
                page_index=index,
            )

        source_destination = project_dir / "sources" / "pdf" / source_name
        _report_progress(
            progress_callback,
            phase="install",
            completed=0,
            total=total_pages,
            message="Installing the PDF and rendered pages inside the project",
        )
        if _copy_without_overwrite(source_path, source_destination, str(inspection["sha256"])):
            created_files.append(source_destination)
        for completed, index in enumerate(selected, start=1):
            asset = staged_assets[index]
            destination = project_dir / "assets" / "images" / str(asset["name"])
            if _copy_without_overwrite(Path(asset["path"]), destination, str(asset["sha256"])):
                created_files.append(destination)
            _report_progress(
                progress_callback,
                phase="install",
                completed=completed,
                total=total_pages,
                message="Installing the PDF and rendered pages inside the project",
                page_index=index,
            )

        results: list[dict[str, Any]] = []
        _report_progress(
            progress_callback,
            phase="compose",
            completed=0,
            total=total_pages,
            message="Creating stable Singh360 drawing pages",
        )
        if action == "add":
            insertion_index, orders = _insertion_orders(pages, len(selected), insert_after_page_id)
            new_pages: list[dict[str, Any]] = []
            stem = Path(str(inspection["originalFileName"])).stem or "Imported PDF"
            for offset, index in enumerate(selected):
                page = _new_page(
                    project_id=project_id,
                    original_stem=stem,
                    source_record=source_record,
                    page_meta=page_meta_by_index[index],
                    source_page_index=index,
                    asset=staged_assets[index],
                    dpi=dpi,
                    placement_mode=_normalize_placement(placement_mode),
                    order=orders[offset],
                    supplied_metadata=_metadata_for_page(page_metadata, index),
                    imported_at=imported_at,
                )
                new_pages.append(page)
                results.append({
                    "action": "added",
                    "pageId": page["id"],
                    "sourcePageIndex": index,
                    "sourcePageNumber": index + 1,
                })
                _report_progress(
                    progress_callback,
                    phase="compose",
                    completed=offset + 1,
                    total=total_pages,
                    message="Creating stable Singh360 drawing pages",
                    page_index=index,
                )
            pages[insertion_index:insertion_index] = new_pages
        else:
            for completed, (page_id, index) in enumerate(mapping.items(), start=1):
                page = existing_by_id[page_id]
                source_import = page.get("sourceImport") if isinstance(page.get("sourceImport"), dict) else {}
                page_mode = _normalize_placement(
                    placement_mode,
                    default=str(source_import.get("placementMode") or "fit_body"),
                )
                base_index, old_base = _find_pdf_base(page, group_id)
                new_base = _base_object(
                    project_id=project_id,
                    source_name=source_name,
                    source_id=source_id,
                    source_page_index=index,
                    output_name=str(staged_assets[index]["name"]),
                    output_width=int(staged_assets[index]["outputWidth"]),
                    output_height=int(staged_assets[index]["outputHeight"]),
                    dpi=dpi,
                    group_id=group_id,
                    placement_mode=page_mode,
                    page_fingerprint=str(page_meta_by_index[index].get("fingerprint") or ""),
                    object_id=str(old_base.get("objectId") or f"obj_{uuid.uuid4().hex[:16]}"),
                )
                objects = copy.deepcopy(page.get("canvasObjects") or [])
                objects[base_index] = new_base
                page["canvasObjects"] = objects
                existing_page_assets = page.get("assets") if isinstance(page.get("assets"), list) else []
                page["assets"] = [
                    copy.deepcopy(asset)
                    for asset in existing_page_assets
                    if not isinstance(asset, dict) or asset.get("type") != "pdf-preview"
                ]
                page["assets"].append({
                    "id": staged_assets[index]["id"],
                    "url": staged_assets[index]["url"],
                    "type": "pdf-preview",
                })
                page["sourceImport"] = _source_import(
                    source_record=source_record,
                    page_meta=page_meta_by_index[index],
                    source_page_index=index,
                    asset_name=str(staged_assets[index]["name"]),
                    dpi=dpi,
                    placement_mode=page_mode,
                    imported_at=imported_at,
                    previous=source_import,
                )
                page["pdfPlacementMode"] = page_mode
                page["renderProfile"] = "pdf_full_sheet" if page_mode == "full_sheet" else "pdf_fit_body"
                page["suppressTitleBlock"] = page_mode == "full_sheet"
                page["modifiedAt"] = imported_at
                results.append({
                    "action": "replaced",
                    "pageId": page_id,
                    "sourcePageIndex": index,
                    "sourcePageNumber": index + 1,
                })
                _report_progress(
                    progress_callback,
                    phase="compose",
                    completed=completed,
                    total=total_pages,
                    message="Replacing matched PDF pages in place",
                    page_index=index,
                )

        project["pages"] = pages
        sources = project.get("sources") if isinstance(project.get("sources"), list) else []
        project["sources"] = [*sources, {key: value for key, value in source_record.items() if key != "projectId"}]
        assets = project.get("assets") if isinstance(project.get("assets"), list) else []
        installed_asset_records = []
        for index in selected:
            destination = project_dir / "assets" / "images" / str(staged_assets[index]["name"])
            installed_asset_records.append(
                _asset_sha_record(
                    destination,
                    asset_id=str(staged_assets[index]["id"]),
                    project_id=project_id,
                )
            )
        project["assets"] = [*assets, *installed_asset_records]
        project["modified"] = imported_at
        _report_progress(
            progress_callback,
            phase="save",
            completed=0,
            total=total_pages,
            message="Saving and verifying the updated Singh360 project",
        )
        if project_transform is not None:
            try:
                transformed = project_transform(copy.deepcopy(project))
            except Exception as exc:  # noqa: BLE001
                raise PdfPageImportError(
                    "The PDF pages were prepared, but the project could not be normalized for saving.",
                    code="project_transform_failed",
                    phase="save",
                    detail=str(exc),
                ) from exc
            if not isinstance(transformed, Mapping):
                raise PdfPageImportError(
                    "The PDF project normalizer returned an invalid project.",
                    code="project_transform_invalid",
                    phase="save",
                    detail=type(transformed).__name__,
                )
            project = copy.deepcopy(dict(transformed))
        try:
            store.save(project_id, project)
            project_save_completed = True
        except Exception as exc:  # noqa: BLE001
            raise PdfPageImportError(
                "The PDF pages were rendered, but the project could not be saved.",
                code="project_save_failed",
                phase="save",
                detail=str(exc),
            ) from exc
        persisted = store.load(project_id)
        if persisted is None:
            raise PdfPageImportError(
                "The saved project could not be read back.",
                code="project_readback_failed",
                phase="save",
            )
        _report_progress(
            progress_callback,
            phase="save",
            completed=total_pages,
            total=total_pages,
            message="Saving and verifying the updated Singh360 project",
        )

        group_page_ids = [
            str(page.get("id"))
            for page in persisted.get("pages", [])
            if isinstance(page, dict)
            and isinstance(page.get("sourceImport"), dict)
            and str(page["sourceImport"].get("importGroupId") or "") == group_id
        ]
        mapped_page_ids = set(mapping)
        unmatched_existing = [page_id for page_id in group_page_ids if page_id not in mapped_page_ids] if action == "replace" else []
        mapped_source_indices = set(mapping.values())
        unmatched_source = [index for index in range(page_count) if index not in mapped_source_indices] if action == "replace" else []
        response = {
            "ok": True,
            "action": action,
            "project": persisted,
            "importGroupId": group_id,
            "revision": revision,
            "source": {key: value for key, value in source_record.items() if key != "projectId"},
            "pageResults": results,
            "unmatchedExistingPageIds": unmatched_existing,
            "unmatchedSourcePageIndices": unmatched_source,
            "projectUnchangedOnFailure": True,
        }
        _report_progress(
            progress_callback,
            phase="complete",
            completed=total_pages,
            total=total_pages,
            message="PDF import complete",
        )
        return response
    except PdfPageImportError:
        if not project_save_completed:
            for path in reversed(created_files):
                path.unlink(missing_ok=True)
        # ProjectStore.save is atomic; keep this check explicit for custom stores.
        current = store.load(project_id)
        if current is None and original_project:
            # Do not attempt a blind rewrite here.  The caller receives an exact
            # failure and can use ProjectStore's history/rollback facilities.
            pass
        raise
    except Exception as exc:  # noqa: BLE001
        if not project_save_completed:
            for path in reversed(created_files):
                path.unlink(missing_ok=True)
        raise PdfPageImportError(
            "PDF page import failed before the project could be changed.",
            code="pdf_import_failed",
            phase="commit",
            detail=str(exc),
        ) from exc
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
