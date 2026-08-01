"""Validated, atomic PDF optimization and export diagnostics."""
from __future__ import annotations

import hashlib
import os
import re
import statistics
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

import fitz
import pikepdf


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stream_size(document: fitz.Document, xref: int) -> int:
    if xref <= 0 or not document.xref_is_stream(xref):
        return 0
    return len(document.xref_stream_raw(xref) or b"")


def _page_resource_xrefs(page: fitz.Page) -> set[int]:
    xrefs = {int(xref) for xref in (page.get_contents() or []) if int(xref) > 0}
    xrefs.update(int(item[0]) for item in page.get_images(full=True) if int(item[0]) > 0)
    xrefs.update(int(item[0]) for item in page.get_xobjects() if int(item[0]) > 0)
    return xrefs


def analyze_pdf(
    pdf_path: str | Path,
    *,
    render_dpi: int = 96,
    managed_page_indices: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Return structural and interactive-render diagnostics for a real PDF."""
    path = Path(pdf_path)
    managed = {int(value) for value in (managed_page_indices or [])}
    started = time.perf_counter()
    document = fitz.open(path)
    open_ms = (time.perf_counter() - started) * 1000.0
    pages: list[dict[str, Any]] = []
    render_times: list[float] = []
    seen_font_xrefs: set[int] = set()
    subset_font_xrefs: set[int] = set()
    unsubset_embedded_font_xrefs: set[int] = set()
    stream_hashes: dict[str, set[int]] = {}
    image_hashes: dict[str, set[int]] = {}
    scale = max(72, int(render_dpi)) / 72.0

    try:
        for page_index, page in enumerate(document):
            render_started = time.perf_counter()
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                colorspace=fitz.csRGB,
                alpha=False,
            )
            render_ms = (time.perf_counter() - render_started) * 1000.0
            del pixmap
            render_times.append(render_ms)

            images: list[dict[str, Any]] = []
            for info in page.get_image_info(hashes=True, xrefs=True):
                xref = int(info.get("xref") or 0)
                bbox = fitz.Rect(info.get("bbox"))
                visible = bbox & page.rect
                visible_fraction = visible.get_area() / max(1.0, page.rect.get_area()) if not visible.is_empty else 0.0
                x_dpi = float(info.get("width") or 0) / (bbox.width / 72.0) if bbox.width else 0.0
                y_dpi = float(info.get("height") or 0) / (bbox.height / 72.0) if bbox.height else 0.0
                digest_value = info.get("digest") or b""
                digest = digest_value.hex() if isinstance(digest_value, (bytes, bytearray)) else str(digest_value)
                if digest and xref > 0:
                    image_hashes.setdefault(digest, set()).add(xref)
                images.append({
                    "xref": xref,
                    "width": int(info.get("width") or 0),
                    "height": int(info.get("height") or 0),
                    "bbox": [round(value, 2) for value in bbox],
                    "effectiveDpi": [round(x_dpi, 1), round(y_dpi, 1)],
                    "visiblePageFraction": round(visible_fraction, 4),
                    "streamBytes": _stream_size(document, xref),
                })

            content_streams = []
            for xref in page.get_contents() or []:
                raw = document.xref_stream_raw(xref) or b""
                decoded = document.xref_stream(xref) or b""
                content_streams.append({
                    "xref": int(xref),
                    "compressedBytes": len(raw),
                    "decodedBytes": len(decoded),
                })

            fonts = []
            for font in page.get_fonts(full=True):
                xref = int(font[0])
                seen_font_xrefs.add(xref)
                extension = str(font[1] or "")
                base_font = str(font[3] or "")
                subset = bool(re.match(r"^[A-Z]{6}\+", base_font))
                if subset:
                    subset_font_xrefs.add(xref)
                elif extension.casefold() not in {"", "n/a"}:
                    unsubset_embedded_font_xrefs.add(xref)
                fonts.append({
                    "xref": xref,
                    "extension": extension,
                    "type": font[2],
                    "baseFont": base_font,
                    "subset": subset,
                })

            resource_xrefs = _page_resource_xrefs(page)
            resource_bytes = sum(_stream_size(document, xref) for xref in resource_xrefs)
            high_dpi_full_page = [
                image for image in images
                if image["visiblePageFraction"] >= 0.30
                and min(image["effectiveDpi"]) >= 250.0
            ]
            pages.append({
                "page": page_index + 1,
                "managedPdfPage": page_index in managed,
                "widthPoints": round(page.rect.width, 3),
                "heightPoints": round(page.rect.height, 3),
                "renderMs": round(render_ms, 2),
                "resourceBytes": resource_bytes,
                "imageXObjectCount": len(images),
                "images": images,
                "fontCount": len(fonts),
                "fonts": fonts,
                "contentStreams": content_streams,
                "contentStreamBytes": sum(item["compressedBytes"] for item in content_streams),
                "decodedContentBytes": sum(item["decodedBytes"] for item in content_streams),
                "excludedPreviewDetected": bool(high_dpi_full_page) and page_index in managed,
                "highDpiFullPageImages": high_dpi_full_page,
            })

        for xref in range(1, document.xref_length()):
            if not document.xref_is_stream(xref):
                continue
            raw = document.xref_stream_raw(xref) or b""
            # Identical operator bytes are not necessarily duplicate resources:
            # Form XObjects commonly share ``/fullpage Do`` while carrying
            # different matrices, bounding boxes and resource dictionaries.
            descriptor = document.xref_object(xref, compressed=False).encode("utf-8", "replace")
            digest = hashlib.sha256(descriptor + b"\0" + raw).hexdigest()
            stream_hashes.setdefault(digest, set()).add(xref)

        duplicate_streams = [sorted(values) for values in stream_hashes.values() if len(values) > 1]
        duplicate_images = [sorted(values) for values in image_hashes.values() if len(values) > 1]
        navigation = render_times[1:] if len(render_times) > 1 else render_times
        largest = sorted(pages, key=lambda item: item["resourceBytes"], reverse=True)[:5]
        file_bytes = path.stat().st_size
        return {
            "path": str(path),
            "sha256": _sha256(path),
            "totalBytes": file_bytes,
            "pageCount": document.page_count,
            "averageBytesPerPage": round(file_bytes / max(1, document.page_count), 2),
            "linearized": b"/Linearized" in path.read_bytes()[:4096],
            "metadata": document.metadata,
            "xrefCount": document.xref_length(),
            "uniqueFontResources": len(seen_font_xrefs),
            "subsetFontResources": len(subset_font_xrefs),
            "unsubsetEmbeddedFontResources": len(unsubset_embedded_font_xrefs),
            "duplicateResourceGroups": len(duplicate_streams) + len(duplicate_images),
            "duplicateResourceCount": (
                sum(len(values) - 1 for values in duplicate_streams)
                + sum(len(values) - 1 for values in duplicate_images)
            ),
            "duplicateStreamXrefs": duplicate_streams,
            "duplicateImageXrefs": duplicate_images,
            "openMs": round(open_ms, 2),
            "firstPageOpenMs": round(open_ms + (render_times[0] if render_times else 0.0), 2),
            "renderDpi": int(render_dpi),
            "averagePageRenderMs": round(statistics.mean(render_times), 2) if render_times else 0.0,
            "pageNavigationAverageMs": round(statistics.mean(navigation), 2) if navigation else 0.0,
            "pageNavigationMaxMs": round(max(navigation), 2) if navigation else 0.0,
            "largestPages": [
                {"page": item["page"], "resourceBytes": item["resourceBytes"], "renderMs": item["renderMs"]}
                for item in largest
            ],
            "managedPreviewFailures": [
                item["page"] for item in pages if item["excludedPreviewDetected"]
            ],
            "pages": pages,
        }
    finally:
        document.close()


def optimize_pdf_atomic(
    source_path: str | Path,
    final_path: str | Path,
    *,
    expected_page_count: int,
    managed_page_indices: Iterable[int] | None = None,
    render_dpi: int = 96,
) -> dict[str, Any]:
    """Optimize, fully close, reopen, diagnose, then atomically publish a PDF."""
    source = Path(source_path)
    final = Path(final_path)
    final.parent.mkdir(parents=True, exist_ok=True)
    temporary = final.with_name(f".{final.stem}.{uuid.uuid4().hex}.optimizing.pdf")
    document: fitz.Document | None = None
    try:
        document = fitz.open(source)
        if document.page_count != expected_page_count:
            raise RuntimeError(
                f"Export page count mismatch before optimization: expected {expected_page_count}, got {document.page_count}."
            )
        if any(page.rect.width <= 0 or page.rect.height <= 0 for page in document):
            raise RuntimeError("Export contains an invalid media box before optimization.")
        document.close()
        document = None

        # ``apply_vector_pdf_underlays`` has already written a clean,
        # garbage-collected and deflated file. qpdf performs the final
        # metadata removal and linearization without expanding million-path
        # engineering content streams into memory.
        with pikepdf.Pdf.open(source) as optimized:
            for key in list(optimized.docinfo.keys()):
                del optimized.docinfo[key]
            if "/Metadata" in optimized.Root:
                del optimized.Root.Metadata
            optimized.save(
                temporary,
                linearize=True,
                compress_streams=True,
                recompress_flate=False,
                object_stream_mode=pikepdf.ObjectStreamMode.disable,
            )

        # Reopening is a release gate, not a best-effort check. Diagnostics also
        # render every page so corrupt resources cannot be published atomically.
        diagnostics = analyze_pdf(
            temporary,
            render_dpi=render_dpi,
            managed_page_indices=managed_page_indices,
        )
        if diagnostics["pageCount"] != expected_page_count:
            raise RuntimeError(
                f"Optimized export page count mismatch: expected {expected_page_count}, got {diagnostics['pageCount']}."
            )
        if not diagnostics["linearized"]:
            raise RuntimeError("Optimized PDF is not linearized for fast opening.")
        if diagnostics["managedPreviewFailures"]:
            raise RuntimeError(
                "Managed PDF page still contains an excluded high-resolution preview: page(s) "
                + ", ".join(str(value) for value in diagnostics["managedPreviewFailures"])
            )
        if diagnostics["unsubsetEmbeddedFontResources"]:
            raise RuntimeError(
                "Optimized PDF contains embedded fonts that are not subset: "
                f"{diagnostics['unsubsetEmbeddedFontResources']} resource(s)."
            )
        if diagnostics["firstPageOpenMs"] >= 3000:
            raise RuntimeError(
                "Optimized PDF failed the local first-page performance gate: "
                f"{diagnostics['firstPageOpenMs']} ms (maximum 3000 ms)."
            )
        if diagnostics["pageNavigationMaxMs"] >= 2000:
            raise RuntimeError(
                "Optimized PDF failed the local page-navigation performance gate: "
                f"{diagnostics['pageNavigationMaxMs']} ms (maximum 2000 ms)."
            )
        os.replace(temporary, final)
        diagnostics["path"] = str(final)
        diagnostics["publishedAtomically"] = True
        return diagnostics
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        if document is not None:
            document.close()
