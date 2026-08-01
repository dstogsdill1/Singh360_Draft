"""Create a deterministic PDF layout audit and contact sheet for a saved project."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


def visible_pages(project: dict) -> list[dict]:
    return sorted((page for page in project.get("pages", []) if page.get("include", True)), key=lambda page: int(page.get("order") or 0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--contact-sheet", required=True, type=Path)
    args = parser.parse_args()
    project = json.loads(args.project.read_text(encoding="utf-8-sig"))
    pages = visible_pages(project)
    pdf = fitz.open(args.pdf)
    if len(pdf) != len(pages):
        raise RuntimeError(f"PDF/project page mismatch: {len(pdf)} != {len(pages)}")
    args.images.mkdir(parents=True, exist_ok=True)
    records = []
    thumbnails = []
    matrix = fitz.Matrix(2, 2)
    for index, (pdf_page, page) in enumerate(zip(pdf, pages), start=1):
        pixmap = pdf_page.get_pixmap(matrix=matrix, alpha=False)
        image_path = args.images / f"page-{index:02d}.png"
        pixmap.save(image_path)
        image = Image.open(image_path).convert("RGB")
        # Ignore the frame/header and title-block areas. The audited printable
        # body is a stable inner rectangle on every ANSI-B export.
        x0, x1 = int(image.width * .035), int(image.width * .965)
        y0, y1 = int(image.height * .09), int(image.height * .82)
        body = image.crop((x0, y0, x1, y1)).convert("L")
        ink = body.point(lambda value: 255 if value < 242 else 0)
        bbox = ink.getbbox()
        body_w, body_h = body.size
        if bbox:
            left, top, right, bottom = bbox
            bounding_utilization = ((right - left) * (bottom - top)) / (body_w * body_h)
            ink_utilization = sum(1 for value in ink.getdata() if value) / (body_w * body_h)
            whitespace = {
                "left": round(left / body_w * 100, 2), "right": round((body_w - right) / body_w * 100, 2),
                "top": round(top / body_h * 100, 2), "bottom": round((body_h - bottom) / body_h * 100, 2),
            }
        else:
            bounding_utilization = ink_utilization = 0.0
            whitespace = {"left": 100.0, "right": 100.0, "top": 100.0, "bottom": 100.0}
        spans = [
            span for block in pdf_page.get_text("dict").get("blocks", [])
            for line in block.get("lines", []) for span in line.get("spans", [])
            if str(span.get("text") or "").strip()
            and float(span.get("bbox", [0, 0, 0, 0])[1]) >= pdf_page.rect.height * .09
            and float(span.get("bbox", [0, 0, 0, 0])[3]) <= pdf_page.rect.height * .82
        ]
        warnings = list(page.get("layoutWarnings") or [])
        lower_warnings = " ".join(map(str, warnings)).casefold()
        diagnostics = dict(page.get("layoutDiagnostics") or {})
        records.append({
            "pdfPage": index, "pageId": page.get("id"), "sheetCode": page.get("displaySheetCode") or page.get("sheetCode"),
            "sheetTitle": page.get("sheetTitle"), "renderMode": page.get("renderMode"), "layoutProfile": page.get("layoutProfile"),
            "layoutOverride": page.get("layoutOverride"), "selectedArrangement": diagnostics.get("selectedArrangement") or page.get("tableLayout"),
            "blockCount": diagnostics.get("blockCount", len(page.get("blocks") or [])),
            "continuationOf": page.get("continuationOf"), "continuationIndex": page.get("continuationIndex", 0),
            "rawUsedRange": diagnostics.get("rawUsedRange"), "effectiveUsedRange": diagnostics.get("effectiveUsedRange"),
            "printableBodyBoundingUtilizationPct": round(bounding_utilization * 100, 2),
            "printableBodyInkUtilizationPct": round(ink_utilization * 100, 2), "whitespacePct": whitespace,
            "minimumPdfTextPt": round(min((float(span["size"]) for span in spans), default=0.0), 2),
            "overflowCount": diagnostics.get("overflowCount", int("overflow" in lower_warnings)),
            "clippedCellCount": diagnostics.get("clippedCellCount", int("crop" in lower_warnings or "clip" in lower_warnings)),
            "titleBlockOverlapCount": diagnostics.get("titleBlockOverlapCount", 0), "layoutWarnings": warnings,
            "image": str(image_path),
        })
        thumb = image.copy(); thumb.thumbnail((360, 235)); thumbnails.append((thumb.copy(), f"{index}: {records[-1]['sheetCode']} — {records[-1]['sheetTitle']}"))
    pdf.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "projectId": project.get("id"), "projectName": (project.get("metadata") or {}).get("projectName"),
        "pdf": str(args.pdf), "pdfPageCount": len(records), "pages": records,
        "summary": {
            "overflowPages": sum(record["overflowCount"] > 0 for record in records),
            "clippedPages": sum(record["clippedCellCount"] > 0 for record in records),
            "titleBlockOverlapPages": sum(record["titleBlockOverlapCount"] > 0 for record in records),
            "spreadsheetPages": sum(record["renderMode"] == "excel_exact" for record in records),
        },
    }
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cell_w, cell_h, columns = 390, 275, 3
    rows = (len(thumbnails) + columns - 1) // columns
    contact = Image.new("RGB", (columns * cell_w, rows * cell_h), "white"); draw = ImageDraw.Draw(contact)
    for idx, (thumb, label) in enumerate(thumbnails):
        x, y = (idx % columns) * cell_w, (idx // columns) * cell_h
        contact.paste(thumb, (x + 15, y + 28)); draw.text((x + 12, y + 8), label[:58], fill="black")
    contact.save(args.contact_sheet)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
