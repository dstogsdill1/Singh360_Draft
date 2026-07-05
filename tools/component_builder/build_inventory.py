#!/usr/bin/env python3
"""build_inventory.py -- classify inspected sources into a review manifest.

Reads ``reports/source_inventory.json`` and applies conservative classification
using filename/path signals + the RDM part-number alias table + taxonomy
keywords. It NEVER guesses a specific part number with high confidence; anything
ambiguous is flagged ``needsReview=true``.

Output:
    .docs/component_builder/approved/manifest_review.csv

Columns:
    id, displayName, manufacturer, category, partNumber, aliases,
    sourcePath, sourceHash, needsReview, symbolStatus, notes

Usage:
    python tools/component_builder/build_inventory.py [--include-embedded]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _catalog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = Path(__file__).resolve().parent
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
REPORTS_DIR = CB_ROOT / "reports"
APPROVED_DIR = CB_ROOT / "approved"

TAXONOMY_PATH = TOOL_DIR / "component_taxonomy.json"
ALIASES_PATH = TOOL_DIR / "rdm_aliases.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    """Lowercase and collapse separators for tolerant matching."""
    return re.sub(r"[\s\-_./]+", " ", text.lower()).strip()


def _compact(text: str) -> str:
    """Strip all non-alphanumerics for tight part-number matching."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def match_part(haystack: str, parts: list[dict]) -> dict | None:
    """Return the RDM part dict if a known alias appears in the haystack."""
    norm = _normalize(haystack)
    compact = _compact(haystack)
    best = None
    best_len = 0
    for part in parts:
        for alias in part.get("aliases", []):
            a_norm = _normalize(alias)
            a_compact = _compact(alias)
            hit = (a_norm and a_norm in norm) or (
                len(a_compact) >= 5 and a_compact in compact
            )
            if hit and len(a_compact) > best_len:
                best = part
                best_len = len(a_compact)
    return best


def match_manufacturer(haystack: str, manufacturers: list[dict]) -> str | None:
    norm = _normalize(haystack)
    for mfr in manufacturers:
        if mfr["id"] == "generic":
            continue
        for alias in mfr.get("aliases", []):
            if _normalize(alias) in norm:
                return mfr["id"]
    return None


def match_category(haystack: str, categories: list[dict]) -> tuple[str | None, int]:
    """Return (category_id, hit_count) for the best keyword match."""
    norm = _normalize(haystack)
    best_id = None
    best_hits = 0
    for cat in categories:
        if cat["id"] == "custom":
            continue
        hits = sum(1 for kw in cat.get("keywords", []) if _normalize(kw) in norm)
        if hits > best_hits:
            best_hits = hits
            best_id = cat["id"]
    return best_id, best_hits


def classify(record: dict, taxonomy: dict, aliases: dict) -> dict:
    rel = record.get("relPath") or record.get("sourcePath") or ""
    name = record.get("fileName", "")
    parent = record.get("parentSource") or ""
    haystack = " ".join([rel, name, parent])

    notes: list[str] = []
    needs_review = False

    part = match_part(haystack, aliases.get("parts", []))
    manufacturer = match_manufacturer(haystack, taxonomy.get("manufacturers", []))
    category_id, cat_hits = match_category(haystack, taxonomy.get("categories", []))

    part_number = ""
    display_name = ""
    alias_list: list[str] = []

    if part:
        part_number = part["partNumber"]
        display_name = part["displayName"]
        alias_list = list(part.get("aliases", []))
        manufacturer = manufacturer or aliases.get("manufacturerId", "rdm")
        category_id = category_id or part.get("category")
        notes.append(f"matched RDM part {part_number}")
    else:
        # No confident part match -> derive a provisional display name from the
        # filename, but flag for review. Never assert a specific part number.
        stem = Path(name).stem.replace("_", " ").replace("-", " ").strip()
        display_name = stem.title() if stem else name
        needs_review = True
        notes.append("no confident part-number match; provisional name from filename")

    if not manufacturer:
        manufacturer = "generic"
        needs_review = True
        notes.append("manufacturer unknown")

    if not category_id:
        category_id = "custom"
        needs_review = True
        notes.append("category unknown")
    elif cat_hits < 1:
        needs_review = True

    if record.get("kind") == "embedded":
        notes.append(f"embedded from {parent}")

    return {
        "id": record.get("id", ""),
        "displayName": display_name,
        "manufacturer": manufacturer,
        "category": category_id,
        "partNumber": part_number,
        "aliases": ";".join(alias_list),
        "sourcePath": record.get("relPath", record.get("sourcePath", "")),
        "sourceHash": record.get("sha256", ""),
        "needsReview": "true" if needs_review else "false",
        "symbolStatus": "none",
        "notes": " | ".join(notes),
    }


MANIFEST_FIELDS = [
    "id", "displayName", "manufacturer", "category", "partNumber", "aliases",
    "sourcePath", "sourceHash", "needsReview", "symbolStatus", "notes",
]


def write_manifest(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_catalog_mode(args: argparse.Namespace) -> int:
    manifest = _catalog.resolve_manifest(args.manifest)
    if not manifest:
        print(f"[error] manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    source_root = _catalog.resolve_source_root(args.source_root, manifest.parent)
    rows, catalog = _catalog.load_rows(manifest, source_root)
    if not catalog:
        print(f"[note] {manifest.name} is not a master catalog; falling back to "
              "inventory classification is not applicable here.", file=sys.stderr)

    out_rows = []
    for r in rows:
        out_rows.append({
            "id": r["id"],
            "displayName": r["displayName"],
            "manufacturer": r["manufacturer"],
            "category": r["category"],
            "partNumber": r["partNumber"],
            "aliases": r["aliases"],
            "sourcePath": r["sourceRel"] or r["sourceImageFile"],
            "sourceHash": "",
            "needsReview": "true" if r["needsReview"] else "false",
            "symbolStatus": r["symbolStatus"],
            "notes": r["notes"],
        })

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    write_manifest(out_rows, out_path)

    missing = [r for r in rows if not r["sourceExists"]]
    missing_specific = [r for r in missing if r["templateSpecific"]]
    missing_review = [r for r in missing if not r["templateSpecific"]]

    print(f"[ok] read {len(rows)} catalog row(s) from {_catalog.rel_to_repo(manifest)}")
    print(f"[ok] source-root: {_catalog.rel_to_repo(source_root)}")
    print(f"[ok] with source image: {sum(1 for r in rows if r['sourceExists'])} | "
          f"missing image: {len(missing)} "
          f"(procedural-eligible: {len(missing_specific)}, needsReview: {len(missing_review)})")
    print(f"[ok] wrote {_catalog.rel_to_repo(out_path)}")

    print("\n[category summary]")
    print(f"  {'category':22} {'total':>5} {'src':>5} {'proc':>5} {'review':>7}")
    for c in _catalog.category_summary(rows):
        print(f"  {c['category']:22} {c['total']:>5} {c['withSource']:>5} "
              f"{c['proceduralOnly']:>5} {c['needsReview']:>7}")

    if missing_review:
        print("\n[rows missing source image AND not procedural-drawable -> needsReview]")
        for r in missing_review:
            print(f"  - {r['id']} ({r['category']}/{r['templateType'] or 'no-template'})")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=None,
                    help="Master catalog CSV (e.g. Singh360_Component_Master_Catalog.csv). "
                         "If given, classify directly from it instead of source_inventory.json.")
    ap.add_argument("--source-root", default=None,
                    help="Root folder for catalog sourceImageFile paths (e.g. 'sources').")
    ap.add_argument("--inventory", default=str(REPORTS_DIR / "source_inventory.json"),
                    help="Path to source_inventory.json (legacy inventory mode).")
    ap.add_argument("--out", default=str(APPROVED_DIR / "manifest_review.csv"),
                    help="Output manifest CSV path.")
    ap.add_argument("--include-embedded", action="store_true",
                    help="Also classify embedded/rendered images (default: skip container docs, keep raster+embedded).")
    ap.add_argument("--no-embedded", dest="embedded", action="store_false",
                    help="Skip embedded images; classify original raster/vector only.")
    ap.set_defaults(embedded=True)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.manifest:
        return run_catalog_mode(args)

    inv_path = Path(args.inventory)
    if not inv_path.is_absolute():
        inv_path = REPO_ROOT / inv_path
    if not inv_path.exists():
        print(f"[error] inventory not found: {inv_path}\n"
              "        run inspect_sources.py first.", file=sys.stderr)
        return 2

    taxonomy = _load_json(TAXONOMY_PATH)
    aliases = _load_json(ALIASES_PATH)
    inventory = _load_json(inv_path)

    rows: list[dict] = []
    for rec in inventory.get("sources", []):
        kind = rec.get("kind")
        # documents (pdf/xlsx/pptx) are containers, not drawable symbols
        if kind == "document":
            continue
        if kind == "embedded" and not args.embedded:
            continue
        rows.append(classify(rec, taxonomy, aliases))

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "id", "displayName", "manufacturer", "category", "partNumber", "aliases",
        "sourcePath", "sourceHash", "needsReview", "symbolStatus", "notes",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    flagged = sum(1 for r in rows if r["needsReview"] == "true")
    rel_out = out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path
    print(f"[ok] classified {len(rows)} item(s); {flagged} flagged needsReview=true.")
    print(f"[ok] wrote {rel_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
