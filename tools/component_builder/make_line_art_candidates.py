#!/usr/bin/env python3
"""make_line_art_candidates.py -- generate black/white symbol candidates.

Turns real source images into several black-and-white drawing-symbol *candidates*
so a human can pick the best one on a contact sheet. This is a CANDIDATE
generator, NOT final approval. Nothing here is exported to the app library.

Techniques (all derived from the actual source pixels, so output resembles the
real equipment -- never a generic placeholder rectangle):
    - grayscale
    - white-background removal (near-white -> transparent)
    - adaptive binary threshold (clean black/white)
    - edge detection (black linework on white/transparent)
    - filled silhouette (transparent background)
    - silhouette outline

Uses OpenCV if installed for higher-quality edges/threshold; otherwise falls back
to a pure PIL + numpy pipeline. Aspect ratio is always preserved.

Output:
    .docs/component_builder/work/symbol_candidates/<manufacturer>/<category>/<id>/<variant>.png

Usage:
    python tools/component_builder/make_line_art_candidates.py \
        [--manifest .docs/component_builder/approved/manifest_review.csv] \
        [--only <id>] [--variants grayscale,threshold,edges,silhouette,outline] \
        [--max-size 1024] [--replace]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
WORK_DIR = CB_ROOT / "work"
CANDIDATES_DIR = WORK_DIR / "symbol_candidates"
MANIFEST_DEFAULT = CB_ROOT / "approved" / "manifest_review.csv"

ALL_VARIANTS = ["grayscale", "nobg", "threshold", "edges", "silhouette", "outline"]

try:  # optional, higher quality
    import cv2  # type: ignore
    HAVE_CV2 = True
except Exception:  # pragma: no cover
    HAVE_CV2 = False

try:
    import numpy as np  # type: ignore
    HAVE_NUMPY = True
except Exception:  # pragma: no cover
    HAVE_NUMPY = False


def _resolve(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (REPO_ROOT / p)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_rows(manifest: Path) -> list[dict]:
    with manifest.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _fit(im, max_size: int):
    from PIL import Image  # type: ignore

    w, h = im.size
    if max(w, h) <= max_size:
        return im
    scale = max_size / float(max(w, h))
    return im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _foreground_mask(rgb, white_thresh: int = 245):
    """Boolean mask: True where pixel is foreground (not near-white)."""
    lum = rgb[..., :3].mean(axis=2)
    return lum < white_thresh


def generate_variants(src_path: Path, out_dir: Path, variants: list[str],
                      max_size: int, replace: bool) -> list[str]:
    from PIL import Image, ImageFilter, ImageOps  # type: ignore

    written: list[str] = []
    try:
        im = Image.open(src_path)
    except Exception as exc:
        print(f"[warn] cannot open {_rel(src_path)}: {exc}", file=sys.stderr)
        return written

    im = im.convert("RGBA")
    im = _fit(im, max_size)
    out_dir.mkdir(parents=True, exist_ok=True)

    rgba = np.array(im) if HAVE_NUMPY else None

    def _save(name: str, pil_img) -> None:
        target = out_dir / f"{name}.png"
        if target.exists() and not replace:
            print(f"[skip] exists (use --replace): {_rel(target)}")
            written.append(_rel(target))
            return
        pil_img.save(target)
        written.append(_rel(target))

    gray = ImageOps.grayscale(im.convert("RGB"))

    if "grayscale" in variants:
        _save("grayscale", gray)

    if HAVE_NUMPY:
        mask = _foreground_mask(rgba)  # True = keep

    if "nobg" in variants and HAVE_NUMPY:
        out = rgba.copy()
        out[..., 3] = np.where(mask, 255, 0).astype("uint8")
        _save("nobg", Image.fromarray(out, "RGBA"))

    if "threshold" in variants:
        if HAVE_CV2 and HAVE_NUMPY:
            g = np.array(gray)
            th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 21, 8)
            _save("threshold", Image.fromarray(th))
        else:
            th = gray.point(lambda p: 255 if p > 200 else 0, mode="1")
            _save("threshold", th.convert("L"))

    if "edges" in variants:
        if HAVE_CV2 and HAVE_NUMPY:
            g = np.array(gray)
            edges = cv2.Canny(g, 60, 160)
            inv = 255 - edges  # black lines on white
            _save("edges", Image.fromarray(inv))
        else:
            edges = gray.filter(ImageFilter.FIND_EDGES)
            inv = ImageOps.invert(edges)
            # push toward crisp black/white linework
            inv = inv.point(lambda p: 0 if p < 180 else 255)
            _save("edges", inv)

    if ("silhouette" in variants or "outline" in variants) and HAVE_NUMPY:
        sil = np.zeros(rgba.shape[:2] + (4,), dtype="uint8")
        sil[mask] = (0, 0, 0, 255)  # black shape, transparent bg
        if "silhouette" in variants:
            _save("silhouette", Image.fromarray(sil, "RGBA"))
        if "outline" in variants:
            sil_img = Image.fromarray(sil, "RGBA")
            alpha = sil_img.split()[3]
            edge = alpha.filter(ImageFilter.FIND_EDGES)
            outline = Image.new("RGBA", sil_img.size, (0, 0, 0, 0))
            outline.putalpha(edge)
            black = Image.new("RGBA", sil_img.size, (0, 0, 0, 255))
            black.putalpha(edge)
            _save("outline", black)
    elif ("silhouette" in variants or "outline" in variants) and not HAVE_NUMPY:
        print("[warn] numpy unavailable; silhouette/outline skipped", file=sys.stderr)

    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(MANIFEST_DEFAULT))
    ap.add_argument("--only", default=None, help="Process a single manifest id.")
    ap.add_argument("--variants", default=",".join(ALL_VARIANTS),
                    help=f"Comma list from: {','.join(ALL_VARIANTS)}")
    ap.add_argument("--max-size", type=int, default=1024,
                    help="Longest edge of candidate output (aspect preserved).")
    ap.add_argument("--replace", action="store_true",
                    help="Overwrite existing candidate PNGs.")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import PIL  # noqa: F401
    except Exception:
        print("[error] Pillow (PIL) is required. pip install Pillow", file=sys.stderr)
        return 3

    manifest = _resolve(args.manifest)
    if not manifest.exists():
        print(f"[error] manifest not found: {manifest}\n"
              "        run build_inventory.py first.", file=sys.stderr)
        return 2

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    bad = [v for v in variants if v not in ALL_VARIANTS]
    if bad:
        print(f"[error] unknown variant(s): {bad}. valid: {ALL_VARIANTS}", file=sys.stderr)
        return 2

    rows = load_rows(manifest)
    if args.only:
        rows = [r for r in rows if r.get("id") == args.only]
        if not rows:
            print(f"[error] id not found in manifest: {args.only}", file=sys.stderr)
            return 2

    processed = 0
    for row in rows:
        src = _resolve(row.get("sourcePath", ""))
        if not src.exists():
            print(f"[warn] source missing, skipping: {row.get('sourcePath')}",
                  file=sys.stderr)
            continue
        mfr = row.get("manufacturer") or "generic"
        cat = row.get("category") or "custom"
        cid = row.get("id") or src.stem
        out_dir = CANDIDATES_DIR / mfr / cat / cid
        written = generate_variants(src, out_dir, variants, args.max_size, args.replace)
        if written:
            processed += 1
            print(f"[ok] {cid}: {len(written)} candidate(s) -> {_rel(out_dir)}")

    print(f"[done] generated candidates for {processed} source(s).")
    if not HAVE_CV2:
        print("[note] OpenCV not installed; used PIL+numpy fallback "
              "(edges/threshold are lower fidelity). pip install opencv-python for better linework.")
    print("[note] SVG vector tracing is not produced by this fallback pipeline; "
          "PNG candidates are high-res. Install 'potrace' + vectorize separately if true SVG is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
