from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import fitz

from core.vector_pdf_export import (
    apply_vector_pdf_underlays,
    export_page_id_marker,
    prepare_vector_export_clone,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pdf_object(source: str, source_page: int, *, name: str = "PDF") -> dict:
    return {
        "type": "image",
        "objName": name,
        "pdfSource": source,
        "pdfPage": source_page,
        "pdfDpi": 144,
        "left": 0,
        "top": 0,
        "width": 1440,
        "height": 864,
        "scaleX": 1598 / 1440,
        "scaleY": 866 / 864,
        "originX": "left",
        "originY": "top",
        "opacity": 0.85,
        "visible": True,
    }


def _raster_duplicate() -> dict:
    return {
        "type": "image",
        "objName": "Saved PDF screenshot",
        "src": "/api/assets/test/screenshot.png",
        "left": 0,
        "top": 0,
        "width": 1598,
        "height": 866,
        "scaleX": 1,
        "scaleY": 1,
        "originX": "left",
        "originY": "top",
        "opacity": 1,
        "visible": True,
    }


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="s360_page_identity_smoke_"))
    source_dir = root / "sources" / "pdf"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "two-page-source.pdf"

    source = fitz.open()
    a = source.new_page(width=720, height=432)
    a.insert_text((72, 80), "VECTOR PAGE A", fontsize=28)
    a.draw_rect(fitz.Rect(60, 100, 660, 360), color=(0, 0, 0), width=1)
    b = source.new_page(width=720, height=432)
    b.insert_text((72, 80), "VECTOR PAGE B", fontsize=28)
    b.draw_circle((360, 230), 120, color=(0, 0, 0), width=1)
    source.save(source_path)
    source.close()
    before_hash = _sha(source_path)

    project = {
        "pages": [
            {"id": "cover", "order": 1, "include": True, "pageType": "cover", "canvasObjects": []},
            {
                "id": "index",
                "order": 2,
                "include": True,
                "pageType": "index",
                # Simulate the exact failure: a stale PDF object must never be
                # vectorized onto the Sheet Index.
                "canvasObjects": [_pdf_object("two-page-source.pdf", 0, name="stale index PDF")],
            },
            {
                "id": "drawing_a",
                "order": 3,
                "include": True,
                "pageType": "canvas",
                # Simulate the user's PDF-on-top-of-screenshot comparison page.
                "canvasObjects": [_raster_duplicate(), _pdf_object("two-page-source.pdf", 0)],
            },
            {
                "id": "drawing_b",
                "order": 4,
                "include": True,
                "pageType": "canvas",
                "canvasObjects": [_pdf_object("two-page-source.pdf", 1)],
            },
        ]
    }

    clone, placements = prepare_vector_export_clone(project, source_pdf_dir=source_dir)
    assert len(placements) == 2, placements
    assert clone["pages"][1]["canvasObjects"][0]["visible"] is False
    assert clone["pages"][2]["canvasObjects"][0]["visible"] is False  # duplicate screenshot hidden
    assert clone["pages"][2]["canvasObjects"][1]["visible"] is False
    assert clone["pages"][3]["canvasObjects"][0]["visible"] is False

    # Create Playwright-like pages in a deliberately different physical order.
    # The page ID marker, not an ordinal guess, must control vector placement.
    output_path = root / "permuted-playwright-output.pdf"
    output = fitz.open()
    physical_ids = ["cover", "index", "drawing_b", "drawing_a"]
    for page_id in physical_ids:
        page = output.new_page(width=1224, height=792)
        page.insert_text((2, 8), export_page_id_marker(page_id), fontsize=1, color=(1, 1, 1))
        page.insert_text((40, 760), f"TITLE {page_id}", fontsize=12)
    output.save(output_path)
    output.close()

    audit = apply_vector_pdf_underlays(output_path, source_pdf_dir=source_dir, placements=placements)
    assert audit["inserted"] == 2, audit
    assert audit["skipped"] == 0, audit
    assert _sha(source_path) == before_hash

    result = fitz.open(output_path)
    try:
        texts = [page.get_text("text") for page in result]
        assert "VECTOR PAGE A" not in texts[0]
        assert "VECTOR PAGE B" not in texts[0]
        assert "VECTOR PAGE A" not in texts[1]  # Sheet Index stays clean
        assert "VECTOR PAGE B" not in texts[1]
        assert "VECTOR PAGE B" in texts[2]
        assert "VECTOR PAGE A" in texts[3]
    finally:
        result.close()

    print(json.dumps({
        "ok": True,
        "placements": len(placements),
        "sheetIndexProtected": True,
        "physicalPageIdentityMapping": True,
        "overlappingScreenshotHiddenInExportClone": True,
        "sourceSha256Unchanged": True,
        "physicalOrder": physical_ids,
        "pageIdMap": audit.get("pageIdMap"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
