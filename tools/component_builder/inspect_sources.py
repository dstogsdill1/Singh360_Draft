#!/usr/bin/env python3
"""inspect_sources.py -- non-destructive source inventory for the component builder.

Walks one or more input folders/files, records every supported source asset, and
extracts embedded images from Office (xlsx/pptx) containers into the workbench
``extracted_images`` folder. PDF pages are catalogued (and optionally rendered).

This step NEVER alters source files. It only reads them and writes reports +
extracted copies under ``.docs/component_builder/``.

Outputs:
    .docs/component_builder/reports/source_inventory.json
    .docs/component_builder/reports/source_inventory.csv
    .docs/component_builder/work/extracted_images/<source_stem>/...   (embedded images)

Usage:
    python tools/component_builder/inspect_sources.py \
        --input .docs/component_builder/input \
        [--extract] [--render-pdf] [--pdf-dpi 150]

By default embedded-image extraction from Office files IS performed (it is
non-destructive to sources). PDF page *rendering* is opt-in via --render-pdf.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
INPUT_DIR = CB_ROOT / "input"
WORK_DIR = CB_ROOT / "work"
EXTRACTED_DIR = WORK_DIR / "extracted_images"
REPORTS_DIR = CB_ROOT / "reports"

RASTER_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VECTOR_EXTS = {".svg"}
DOC_EXTS = {".pdf", ".xlsx", ".pptx"}
SUPPORTED_EXTS = RASTER_EXTS | VECTOR_EXTS | DOC_EXTS

# Office embedded-image locations inside the OPC zip container.
OFFICE_MEDIA_PREFIXES = ("xl/media/", "ppt/media/", "word/media/")


@dataclass
class SourceRecord:
    id: str
    fileName: str
    sourcePath: str
    relPath: str
    ext: str
    kind: str  # raster | vector | document | embedded
    sizeBytes: int
    sha256: str
    width: int | None = None
    height: int | None = None
    pageCount: int | None = None
    parentSource: str | None = None  # for embedded images: the container file
    extractedTo: str | None = None
    notes: list[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _image_dims(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return None, None


def _image_dims_bytes(data: bytes) -> tuple[int | None, int | None]:
    try:
        import io

        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as im:
            return im.width, im.height
    except Exception:
        return None, None


def _short_id(sha: str, name: str) -> str:
    stem = Path(name).stem
    safe = "".join(c if c.isalnum() else "_" for c in stem).strip("_").lower()[:40]
    return f"{safe}_{sha[:10]}" if safe else sha[:16]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def iter_sources(inputs: Iterable[Path]) -> Iterable[Path]:
    for item in inputs:
        if item.is_dir():
            for p in sorted(item.rglob("*")):
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                    yield p
        elif item.is_file() and item.suffix.lower() in SUPPORTED_EXTS:
            yield item


def extract_office_media(path: Path, records: list[SourceRecord]) -> None:
    """Copy embedded media out of an xlsx/pptx OPC zip. Non-destructive."""
    out_root = EXTRACTED_DIR / _short_id(_sha256(path), path.name)
    try:
        with zipfile.ZipFile(path) as zf:
            names = [
                n
                for n in zf.namelist()
                if n.startswith(OFFICE_MEDIA_PREFIXES) and not n.endswith("/")
            ]
            if not names:
                return
            out_root.mkdir(parents=True, exist_ok=True)
            for name in names:
                data = zf.read(name)
                ext = Path(name).suffix.lower()
                if ext not in (RASTER_EXTS | VECTOR_EXTS):
                    continue
                sha = _sha256_bytes(data)
                target = out_root / Path(name).name
                # avoid clobbering distinct images that share a name
                if target.exists() and _sha256(target) != sha:
                    target = out_root / f"{target.stem}_{sha[:8]}{target.suffix}"
                target.write_bytes(data)
                w, h = _image_dims_bytes(data)
                records.append(
                    SourceRecord(
                        id=_short_id(sha, target.name),
                        fileName=target.name,
                        sourcePath=str(target),
                        relPath=_rel(target),
                        ext=ext,
                        kind="embedded",
                        sizeBytes=len(data),
                        sha256=sha,
                        width=w,
                        height=h,
                        parentSource=_rel(path),
                        extractedTo=_rel(target),
                        notes=[f"embedded media from {name}"],
                    )
                )
    except zipfile.BadZipFile:
        pass


def inspect_pdf(path: Path, rec: SourceRecord, render: bool, dpi: int,
                records: list[SourceRecord]) -> None:
    try:
        import fitz  # type: ignore  # PyMuPDF
    except Exception:
        rec.notes.append("PyMuPDF not available; page count/render skipped")
        return
    try:
        with fitz.open(path) as doc:
            rec.pageCount = doc.page_count
            if not render:
                return
            out_root = EXTRACTED_DIR / _short_id(rec.sha256, path.name)
            out_root.mkdir(parents=True, exist_ok=True)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=mat, alpha=False)
                target = out_root / f"page_{i + 1:03d}.png"
                pix.save(target)
                data = target.read_bytes()
                sha = _sha256_bytes(data)
                records.append(
                    SourceRecord(
                        id=_short_id(sha, target.name),
                        fileName=target.name,
                        sourcePath=str(target),
                        relPath=_rel(target),
                        ext=".png",
                        kind="embedded",
                        sizeBytes=len(data),
                        sha256=sha,
                        width=pix.width,
                        height=pix.height,
                        parentSource=_rel(path),
                        extractedTo=_rel(target),
                        notes=[f"rendered PDF page {i + 1} @ {dpi}dpi"],
                    )
                )
    except Exception as exc:  # pragma: no cover - defensive
        rec.notes.append(f"pdf inspect error: {exc}")


def build_record(path: Path) -> SourceRecord:
    ext = path.suffix.lower()
    sha = _sha256(path)
    if ext in RASTER_EXTS:
        kind = "raster"
    elif ext in VECTOR_EXTS:
        kind = "vector"
    else:
        kind = "document"
    w = h = None
    if kind == "raster":
        w, h = _image_dims(path)
    return SourceRecord(
        id=_short_id(sha, path.name),
        fileName=path.name,
        sourcePath=str(path),
        relPath=_rel(path),
        ext=ext,
        kind=kind,
        sizeBytes=path.stat().st_size,
        sha256=sha,
        width=w,
        height=h,
    )


def write_reports(records: list[SourceRecord], meta: dict) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / "source_inventory.json"
    csv_path = REPORTS_DIR / "source_inventory.csv"

    payload = {"meta": meta, "sources": [asdict(r) for r in records]}
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    fields = [
        "id", "fileName", "relPath", "ext", "kind", "sizeBytes", "sha256",
        "width", "height", "pageCount", "parentSource", "extractedTo", "notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            row = asdict(r)
            row["notes"] = " | ".join(row.get("notes") or [])
            writer.writerow(row)
    return json_path, csv_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--input", "-i", action="append", default=None,
        help="Input folder or file. Repeatable. Defaults to the workbench input/ dir.",
    )
    ap.add_argument(
        "--no-extract", dest="extract", action="store_false",
        help="Do NOT extract embedded images from xlsx/pptx (default: extract).",
    )
    ap.add_argument(
        "--render-pdf", action="store_true",
        help="Render PDF pages to PNG (opt-in; off by default).",
    )
    ap.add_argument("--pdf-dpi", type=int, default=150, help="DPI for --render-pdf.")
    ap.set_defaults(extract=True)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    inputs = [Path(p) for p in (args.input or [str(INPUT_DIR)])]
    inputs = [p if p.is_absolute() else (REPO_ROOT / p) for p in inputs]

    missing = [p for p in inputs if not p.exists()]
    for p in missing:
        print(f"[warn] input path does not exist: {p}", file=sys.stderr)
    inputs = [p for p in inputs if p.exists()]
    if not inputs:
        print("[error] no valid input paths. Place sources in "
              f"{_rel(INPUT_DIR)} or pass --input.", file=sys.stderr)
        return 2

    records: list[SourceRecord] = []
    for src in iter_sources(inputs):
        rec = build_record(src)
        if rec.ext == ".pdf":
            inspect_pdf(src, rec, args.render_pdf, args.pdf_dpi, records)
        records.append(rec)
        if args.extract and rec.ext in {".xlsx", ".pptx"}:
            extract_office_media(src, records)

    meta = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "tool": "inspect_sources.py",
        "inputs": [_rel(p) for p in inputs],
        "sourceCount": sum(1 for r in records if r.kind != "embedded"),
        "embeddedCount": sum(1 for r in records if r.kind == "embedded"),
        "totalRecords": len(records),
        "extractEmbedded": args.extract,
        "renderPdf": args.render_pdf,
    }
    json_path, csv_path = write_reports(records, meta)

    print(f"[ok] inspected {meta['sourceCount']} source file(s), "
          f"{meta['embeddedCount']} embedded image(s).")
    print(f"[ok] wrote {_rel(json_path)}")
    print(f"[ok] wrote {_rel(csv_path)}")
    if meta["sourceCount"] == 0:
        print(f"[note] no supported sources found. Drop files into {_rel(INPUT_DIR)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
