#!/usr/bin/env python3
"""export_approved_symbols.py -- export APPROVED components/symbols to the app library.

This is the ONLY script that may write into the production ``.docs/library`` tree,
and it will NOT do so unless ``--apply`` is passed. Without ``--apply`` it performs
a dry run and prints exactly what it would copy.

It reads the review manifest (``manifest_review.csv``) and, optionally, a decisions
CSV exported from the contact sheet (columns: id, decision, chosenVariant, notes).
Only rows that are APPROVED are exported.

For each approved item it:
    - copies the real source image to  .docs/library/components/<category>/
    - copies the chosen B/W candidate to .docs/library/symbols/<category>/
    - appends an entry to a manifest payload (component_builder_export.json)

Safety:
    - dry run by default; needs --apply to write.
    - never overwrites an existing destination file unless --replace is also given.
    - never exports unapproved candidates.

Usage:
    # dry run (safe, default)
    python tools/component_builder/export_approved_symbols.py \
        [--decisions .docs/component_builder/work/contact_sheets/review_decisions.csv]

    # actually write into the production library
    python tools/component_builder/export_approved_symbols.py --apply [--replace]
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
CANDIDATES_DIR = CB_ROOT / "work" / "symbol_candidates"
MANIFEST_DEFAULT = CB_ROOT / "approved" / "manifest_review.csv"

LIBRARY_ROOT = REPO_ROOT / ".docs" / "library"
LIB_COMPONENTS = LIBRARY_ROOT / "components"
LIB_SYMBOLS = LIBRARY_ROOT / "symbols"
EXPORT_MANIFEST = LIBRARY_ROOT / "component_builder_export.json"


def _resolve(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (REPO_ROOT / p)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_decisions(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    if not path.exists():
        print(f"[warn] decisions file not found: {_rel(path)} (ignoring)",
              file=sys.stderr)
        return {}
    out: dict[str, dict] = {}
    for row in load_rows(path):
        rid = row.get("id")
        if rid:
            out[rid] = row
    return out


def choose_candidate(row: dict, decision: dict) -> Path | None:
    mfr = row.get("manufacturer") or "generic"
    cat = row.get("category") or "custom"
    cid = row.get("id") or ""
    cdir = CANDIDATES_DIR / mfr / cat / cid
    if not cdir.exists():
        return None
    chosen = (decision.get("chosenVariant") or "").strip()
    if chosen:
        cand = cdir / f"{chosen}.png"
        if cand.exists():
            return cand
    # deterministic preference order when no explicit choice
    for name in ("outline", "silhouette", "edges", "threshold", "nobg", "grayscale"):
        cand = cdir / f"{name}.png"
        if cand.exists():
            return cand
    pngs = sorted(cdir.glob("*.png"))
    return pngs[0] if pngs else None


def is_approved(row: dict, decision: dict) -> bool:
    d = (decision.get("decision") or "").strip().lower()
    if d:
        return d in {"approve", "approved", "yes", "y"}
    # fall back to the manifest's own symbolStatus field
    return (row.get("symbolStatus") or "").strip().lower() == "approved"


def copy_plan(src: Path, dest_dir: Path, replace: bool) -> tuple[Path, str]:
    dest = dest_dir / src.name
    if dest.exists() and not replace:
        return dest, "skip-exists"
    if dest.exists():
        return dest, "overwrite"
    return dest, "new"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(MANIFEST_DEFAULT))
    ap.add_argument("--decisions", default=None,
                    help="CSV exported from the contact sheet (id,decision,chosenVariant,notes).")
    ap.add_argument("--apply", action="store_true",
                    help="Actually write into the production .docs/library tree.")
    ap.add_argument("--replace", action="store_true",
                    help="Allow overwriting existing destination files.")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = _resolve(args.manifest)
    if not manifest.exists():
        print(f"[error] manifest not found: {manifest}", file=sys.stderr)
        return 2

    decisions = load_decisions(_resolve(args.decisions) if args.decisions else None)
    rows = load_rows(manifest)

    approved = [(r, decisions.get(r.get("id", ""), {})) for r in rows]
    approved = [(r, d) for (r, d) in approved if is_approved(r, d)]

    if not approved:
        print("[note] nothing approved. Approve items via symbolStatus=approved "
              "in the manifest or a decisions CSV from the contact sheet.")
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] {len(approved)} approved item(s).")

    manifest_entries: list[dict] = []
    actions = 0
    skipped = 0

    for row, decision in approved:
        cat = row.get("category") or "custom"
        src = _resolve(row.get("sourcePath", ""))
        cand = choose_candidate(row, decision)

        comp_dir = LIB_COMPONENTS / cat
        sym_dir = LIB_SYMBOLS / cat

        plans: list[tuple[Path, Path, str]] = []
        if src.exists():
            dest, status = copy_plan(src, comp_dir, args.replace)
            plans.append((src, dest, status))
        else:
            print(f"[warn] {row.get('id')}: source missing {row.get('sourcePath')}")
        if cand and cand.exists():
            dest, status = copy_plan(cand, sym_dir, args.replace)
            plans.append((cand, dest, status))
        else:
            print(f"[warn] {row.get('id')}: no B/W candidate found (run make_line_art_candidates.py)")

        for source, dest, status in plans:
            if status == "skip-exists":
                print(f"  [skip] exists: {_rel(dest)} (use --replace)")
                skipped += 1
                continue
            print(f"  [{'copy' if args.apply else 'would-copy'}] "
                  f"{_rel(source)} -> {_rel(dest)}"
                  + ("  (OVERWRITE)" if status == "overwrite" else ""))
            if args.apply:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                actions += 1

        manifest_entries.append({
            "id": row.get("id"),
            "displayName": row.get("displayName"),
            "manufacturer": row.get("manufacturer"),
            "category": cat,
            "partNumber": row.get("partNumber"),
            "aliases": [a for a in (row.get("aliases", "").split(";")) if a],
            "sourceComponent": _rel(LIB_COMPONENTS / cat / src.name) if src.exists() else None,
            "symbol": _rel(LIB_SYMBOLS / cat / cand.name) if (cand and cand.exists()) else None,
            "sourceHash": row.get("sourceHash"),
            "notes": decision.get("notes") or row.get("notes"),
        })

    payload = {
        "schemaVersion": "0.1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "applied": bool(args.apply),
        "note": "Exported by tools/component_builder. Confirm against the live app "
                "library schema before production lock-in.",
        "components": manifest_entries,
    }

    if args.apply:
        EXPORT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        EXPORT_MANIFEST.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[ok] wrote export manifest {_rel(EXPORT_MANIFEST)}")
        print(f"[ok] applied {actions} file copy action(s); {skipped} skipped.")
    else:
        preview = CB_ROOT / "reports" / "export_preview.json"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[ok] dry-run preview written to {_rel(preview)}")
        print("[note] re-run with --apply to write into the production library.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
