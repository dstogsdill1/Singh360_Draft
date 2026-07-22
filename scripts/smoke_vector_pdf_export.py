from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import fitz

from core.vector_pdf_export import apply_vector_pdf_underlays, prepare_vector_export_clone


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="s360_vector_pdf_smoke_"))
    source_dir = root / "sources" / "pdf"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "vector-source.pdf"

    source = fitz.open()
    src_page = source.new_page(width=720, height=432)
    src_page.insert_text((72, 80), "VECTOR SOURCE TEST", fontsize=28)
    for index in range(18):
        y = 110 + index * 14
        src_page.draw_line((60, y), (660, y), color=(0, 0, 0), width=0.6)
    for index in range(16):
        x = 60 + index * 40
        src_page.draw_line((x, 100), (x, 370), color=(0.2, 0.2, 0.2), width=0.4)
    src_page.insert_text((72, 400), "Born-digital linework must remain vector.", fontsize=12)
    source.save(source_path)
    source.close()
    before_hash = sha(source_path)

    output_path = root / "playwright-output.pdf"
    base = fitz.open()
    out_page = base.new_page(width=1224, height=792)
    out_page.draw_rect(fitz.Rect(6, 6, 1218, 786), color=(0, 0, 0), width=1)
    out_page.insert_text((500, 760), "TITLE BLOCK TEST", fontsize=14)
    base.save(output_path)
    base.close()

    # 720x432 points at 400 DPI -> 4000x2400 pixels.  Place at the exact body
    # dimensions so the final vector underlay should cover the normal drawing area.
    project = {
        "pages": [
            {
                "id": "page_vector",
                "order": 1,
                "include": True,
                "sheetCode": "R-3.2",
                "sheetTitle": "Vector Test",
                "pageType": "canvas",
                "canvasObjects": [
                    {
                        "type": "image",
                        "objName": "vector-source.pdf page 1",
                        "pdfSource": "vector-source.pdf",
                        "pdfPage": 0,
                        "pdfDpi": 400,
                        "left": 0,
                        "top": 0,
                        "width": 4000,
                        "height": 2400,
                        "scaleX": 1598 / 4000,
                        "scaleY": 866 / 2400,
                        "originX": "left",
                        "originY": "top",
                        "opacity": 1,
                    }
                ],
            }
        ]
    }
    clone, placements = prepare_vector_export_clone(project, source_pdf_dir=source_dir)
    assert len(placements) == 1
    assert clone["pages"][0]["canvasObjects"][0]["visible"] is False

    audit = apply_vector_pdf_underlays(output_path, source_pdf_dir=source_dir, placements=placements)
    assert audit["inserted"] == 1
    assert audit["skipped"] == 0
    assert sha(source_path) == before_hash

    result = fitz.open(output_path)
    try:
        assert result.page_count == 1
        page = result[0]
        assert tuple(round(value, 3) for value in (page.rect.width, page.rect.height)) == (1224.0, 792.0)
        text = page.get_text()
        assert "VECTOR SOURCE TEST" in text
        assert "TITLE BLOCK TEST" in text
        # show_pdf_page inserts a Form XObject rather than a full-body raster.
        assert len(page.get_xobjects()) >= 1
        large_images = [image for image in page.get_images(full=True) if image[2] >= 1500 and image[3] >= 800]
        assert not large_images
    finally:
        result.close()

    print(json.dumps({
        "ok": True,
        "inserted": audit["inserted"],
        "sourceSha256Unchanged": True,
        "pageSize": [1224, 792],
        "vectorFormXObjects": True,
        "fullBodyRasterImages": 0,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
