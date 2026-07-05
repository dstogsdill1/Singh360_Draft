#!/usr/bin/env python3
"""export_approved_symbols.py -- export APPROVED components/symbols.

Three modes, safest first:

  (no flag)          dry run -- prints exactly what would be copied, writes nothing
                     but a preview JSON in the workbench reports folder.
  --staging          copies into the SAFE workbench staging area
                     .docs/component_builder/export_ready/{components,symbols} +
                     manifest.json. This never touches the app library. USE THIS.
  --apply-production copies into the production .docs/library tree. Only use this
                     when you explicitly want the app library updated.
  --apply            legacy alias for --apply-production (kept for compatibility).

Only rows that are APPROVED are exported. Approval comes from a decisions CSV
exported by the contact sheet (id,decision,chosenVariant,notes) or from
symbolStatus=approved in the manifest.

Existing destination files are never overwritten unless --replace is given.

Usage:
    python tools/component_builder/export_approved_symbols.py --decisions <csv>            # dry run
    python tools/component_builder/export_approved_symbols.py --decisions <csv> --staging  # recommended
    python tools/component_builder/export_approved_symbols.py --decisions <csv> --apply-production
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _catalog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
CANDIDATES_DIR = CB_ROOT / "work" / "symbol_candidates"

STAGING_ROOT = CB_ROOT / "export_ready"
LIBRARY_ROOT = REPO_ROOT / ".docs" / "library"


def _rel(path: Path) -> str:
    return _catalog.rel_to_repo(path)


def load_decisions(path: Path | None) -> dict[str, dict]:
    if not path:
        return {}
    if not path.exists():
        print(f"[warn] decisions file not found: {_rel(path)} (ignoring)", file=sys.stderr)
        return {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {r["id"]: r for r in csv.DictReader(fh) if r.get("id")}


def choose_candidate(row: dict, decision: dict) -> Path | None:
    cdir = _catalog.candidate_dir(row)
    if not cdir.exists():
        return None
    chosen = (decision.get("chosenVariant") or "").strip()
    if chosen:
        cand = cdir / f"{chosen}.png"
        if cand.exists():
            return cand
    for name in ("device", "lineart", "outline", "silhouette", "edges",
                 "highcontrast", "nobg", "grayscale"):
        cand = cdir / f"{name}.png"
        if cand.exists():
            return cand
    pngs = sorted(cdir.glob("*.png"))
    return pngs[0] if pngs else None


def is_approved(row: dict, decision: dict) -> bool:
    d = (decision.get("decision") or "").strip().lower()
    if d:
        return d in {"approve", "approved", "yes", "y"}
    return (row.get("symbolStatus") or "").strip().lower() == "approved"


def copy_plan(src: Path, dest_dir: Path, dest_name: str, replace: bool) -> tuple[Path, str]:
    dest = dest_dir / dest_name
    if dest.exists() and not replace:
        return dest, "skip-exists"
    if dest.exists():
        return dest, "overwrite"
    return dest, "new"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(_catalog.DEFAULT_MANIFEST),
                    help="Master catalog CSV or manifest_review.csv.")
    ap.add_argument("--source-root", default=None)
    ap.add_argument("--decisions", default=None,
                    help="CSV from the contact sheet (id,decision,chosenVariant,notes).")
    ap.add_argument("--staging", action="store_true",
                    help="Export into the safe workbench staging area (recommended).")
    ap.add_argument("--apply-production", dest="apply_production", action="store_true",
                    help="Export into the production .docs/library tree.")
    ap.add_argument("--apply", action="store_true",
                    help="Legacy alias for --apply-production.")
    ap.add_argument("--replace", action="store_true",
                    help="Allow overwriting existing destination files.")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = _catalog.resolve_manifest(args.manifest)
    if not manifest:
        print(f"[error] manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    source_root = _catalog.resolve_source_root(args.source_root, manifest.parent)
    rows, _catalog_mode = _catalog.load_rows(manifest, source_root)

    production = args.apply_production or args.apply
    staging = args.staging and not production

    if production:
        comp_root, sym_root = LIBRARY_ROOT / "components", LIBRARY_ROOT / "symbols"
        manifest_out = LIBRARY_ROOT / "component_builder_export.json"
        mode, do_write = "APPLY-PRODUCTION", True
    elif staging:
        comp_root, sym_root = STAGING_ROOT / "components", STAGING_ROOT / "symbols"
        manifest_out = STAGING_ROOT / "manifest.json"
        mode, do_write = "STAGING", True
    else:
        comp_root, sym_root = STAGING_ROOT / "components", STAGING_ROOT / "symbols"
        manifest_out = CB_ROOT / "reports" / "export_preview.json"
        mode, do_write = "DRY-RUN", False

    decisions = load_decisions(Path(args.decisions).resolve() if args.decisions else None)
    approved = [(r, decisions.get(r["id"], {})) for r in rows]
    approved = [(r, d) for (r, d) in approved if is_approved(r, d)]

    if not approved:
        print("[note] nothing approved yet. Approve items in the contact sheet and "
              "export a decisions CSV, or set symbolStatus=approved in the manifest.")
        return 0

    print(f"[{mode}] {len(approved)} approved item(s).")
    entries: list[dict] = []
    actions = skipped = 0

    for row, decision in approved:
        cat = row["category"] or "custom"
        src = Path(row["sourcePath"]) if row["sourcePath"] else None
        cand = choose_candidate(row, decision)

        # Name destinations by component id so items never collide (the candidate
        # PNGs are named by variant, e.g. lineart.png, and would otherwise clobber
        # each other within a category).
        comp_src = None
        sym_src = None
        plans: list[tuple[Path, Path, str]] = []
        if src and src.exists():
            comp_name = f"{row['id']}{src.suffix.lower()}"
            dest, status = copy_plan(src, comp_root / cat, comp_name, args.replace)
            comp_src = dest
            plans.append((src, dest, status))
        else:
            print(f"[warn] {row['id']}: source image missing")
        if cand and cand.exists():
            variant = cand.stem
            sym_name = f"{row['id']}__{variant}.png"
            dest, status = copy_plan(cand, sym_root / cat, sym_name, args.replace)
            sym_src = dest
            plans.append((cand, dest, status))
        else:
            print(f"[warn] {row['id']}: no B/W candidate (run make_line_art_candidates.py)")

        for source, dest, status in plans:
            if status == "skip-exists":
                print(f"  [skip] exists: {_rel(dest)} (use --replace)")
                skipped += 1
                continue
            verb = "copy" if do_write else "would-copy"
            print(f"  [{verb}] {_rel(source)} -> {_rel(dest)}"
                  + ("  (OVERWRITE)" if status == "overwrite" else ""))
            if do_write:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                actions += 1

        entries.append({
            "id": row["id"],
            "displayName": row["displayName"],
            "manufacturer": row["manufacturer"],
            "category": cat,
            "partNumber": row["partNumber"],
            "aliases": [a for a in (row["aliases"].split(";")) if a],
            "chosenVariant": (decision.get("chosenVariant") or (cand.stem if cand else "")),
            "sourceComponent": _rel(comp_src) if comp_src else None,
            "symbol": _rel(sym_src) if sym_src else None,
            "notes": decision.get("notes") or row["notes"],
        })

    payload = {
        "schemaVersion": "0.2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "note": "Exported by tools/component_builder. Staging is safe; production "
                "writes into .docs/library. Confirm against the live app schema.",
        "components": entries,
    }

    if do_write:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[ok] wrote manifest {_rel(manifest_out)}")
        print(f"[ok] {mode}: {actions} file copy action(s); {skipped} skipped.")
        if staging:
            print(f"[note] staged under {_rel(STAGING_ROOT)} -- production library untouched.")
    else:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[ok] dry-run preview -> {_rel(manifest_out)}")
        print("[note] re-run with --staging to stage safely, or --apply-production "
              "to write the app library.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
