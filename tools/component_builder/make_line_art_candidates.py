#!/usr/bin/env python3
"""make_line_art_candidates.py -- generate black/white symbol candidates.

Two sources of candidates, both driven by the master catalog (or the legacy
manifest_review.csv):

  * rows WITH a curated source image -> image-derived variants (grayscale,
    highcontrast, nobg, edges, silhouette, outline, cleaned lineart). For
    controllers / expansion modules / electrical items that also carry terminal
    geometry, an extra ``device`` procedural outline is drawn so terminal rows
    and screens are preserved.
  * rows WITHOUT a source image but with a SPECIFIC templateType -> a single
    procedural ``device`` symbol drawn from catalog geometry. Rows whose
    templateType is not specific enough are skipped (they stay needsReview).

Nothing generic-rectangle-as-final: every output is derived from a real image
or from a concrete equipment template + geometry.

Output:
    .docs/component_builder/work/symbol_candidates/<manufacturer>/<category>/<id>/<variant>.png

Usage:
    python tools/component_builder/make_line_art_candidates.py \
        --manifest Singh360_Component_Master_Catalog.csv --source-root sources --replace
    python tools/component_builder/make_line_art_candidates.py --only <componentId>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _catalog  # noqa: E402
import _render  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
CANDIDATES_DIR = CB_ROOT / "work" / "symbol_candidates"
MANIFEST_DEFAULT = _catalog.DEFAULT_MANIFEST

# categories/templates where a procedural device outline meaningfully preserves
# terminals/screens/ports and is worth generating alongside an image.
PROCEDURAL_ALSO = {"controllers", "expansion_modules", "electrical_power",
                   "panels_enclosures"}


def _rel(path: Path) -> str:
    return _catalog.rel_to_repo(path)


def out_dir_for(row: dict) -> Path:
    return _catalog.candidate_dir(row)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(MANIFEST_DEFAULT),
                    help="Master catalog CSV or manifest_review.csv.")
    ap.add_argument("--source-root", default=None,
                    help="Root folder for catalog sourceImageFile paths (e.g. 'sources').")
    ap.add_argument("--only", default=None, help="Process a single row id / componentId.")
    ap.add_argument("--variants", default=",".join(_render.ALL_IMAGE_VARIANTS),
                    help=f"Comma list from: {','.join(_render.ALL_IMAGE_VARIANTS)}")
    ap.add_argument("--no-procedural", dest="procedural", action="store_false",
                    help="Do not draw procedural device symbols.")
    ap.add_argument("--max-size", type=int, default=1024,
                    help="Longest edge of image-derived output (aspect preserved).")
    ap.add_argument("--replace", action="store_true", help="Overwrite existing candidate PNGs.")
    ap.set_defaults(procedural=True)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        import PIL  # noqa: F401
    except Exception:
        print("[error] Pillow (PIL) is required. pip install Pillow", file=sys.stderr)
        return 3

    args = parse_args(argv)
    manifest = _catalog.resolve_manifest(args.manifest)
    if not manifest:
        print(f"[error] manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    source_root = _catalog.resolve_source_root(args.source_root, manifest.parent)
    rows, _catalog_mode = _catalog.load_rows(manifest, source_root)

    requested = [v.strip() for v in args.variants.split(",") if v.strip()]
    bad = [v for v in requested if v not in _render.ALL_IMAGE_VARIANTS]
    if bad:
        print(f"[error] unknown variant(s): {bad}", file=sys.stderr)
        return 2

    if args.only:
        rows = [r for r in rows if r["id"] == args.only]
        if not rows:
            print(f"[error] id not found: {args.only}", file=sys.stderr)
            return 2

    total_candidates = 0
    image_rows = 0
    procedural_rows = 0
    skipped_rows: list[str] = []

    for row in rows:
        out_dir = out_dir_for(row)
        row_written = 0

        if row["sourceExists"]:
            src = Path(row["sourcePath"])
            variants = [v for v in requested if v in _render.variants_for_category(row["category"])]
            written = _render.generate_image_variants(src, out_dir, variants,
                                                       args.max_size, args.replace)
            row_written += len(written)
            if written:
                image_rows += 1
            # add a device outline for geometry-bearing hardware
            if (args.procedural and row["category"] in PROCEDURAL_ALSO
                    and row["templateSpecific"]):
                dev = out_dir / "device.png"
                if args.replace or not dev.exists():
                    if _render.procedural_symbol(row, dev):
                        row_written += 1

        elif args.procedural and row["templateSpecific"]:
            dev = out_dir / "device.png"
            if args.replace or not dev.exists():
                if _render.procedural_symbol(row, dev):
                    row_written += 1
                    procedural_rows += 1
        else:
            skipped_rows.append(f"{row['id']} ({row['category']}/{row['templateType'] or 'no-template'})")
            continue

        if row_written:
            total_candidates += row_written
            print(f"[ok] {row['id']}: {row_written} candidate(s) -> {_rel(out_dir)}")

    print(f"\n[done] rows with image variants: {image_rows} | "
          f"procedural-only rows: {procedural_rows} | "
          f"total candidate files: {total_candidates}")
    if skipped_rows:
        print(f"[skip] {len(skipped_rows)} row(s) had no source image and no specific "
              "template (left as needsReview):")
        for s in skipped_rows:
            print(f"  - {s}")
    if not _render.HAVE_CV2:
        print("[note] OpenCV absent; used PIL+numpy fallback for edges/lineart. "
              "pip install opencv-python for sharper linework.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
