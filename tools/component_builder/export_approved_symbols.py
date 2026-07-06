#!/usr/bin/env python3
"""export_approved_symbols.py -- export APPROVED components with explicit paths.

Exports approved contact-sheet decisions into separate library folders:

  components/   original source images
  edges/        approved image-derived edge/lineart/outline candidates (NOT procedural)
  bw/           grayscale / high-contrast fallbacks when available
  symbols/      procedural/spec wireframes ONLY when explicitly chosen or no edge exists

Manifest (component_builder_export.json) records explicit fields per item:
  sourcePath, edgePath, bwPath, symbolPath, chosenVariant, hasSource, hasEdge, hasBw, hasProcedural

Modes:
  (default)          dry run -> .docs/component_builder/reports/export_preview.json
  --staging          .docs/component_builder/export_ready/
  --apply-production / --apply   .docs/library/

Variant resolution (shared with _catalog.resolve_export_representation):
  * chosenVariant=edges|lineart|outline|... -> that exact image-derived file
  * blank -> lineart, edges, outline, highcontrast, grayscale (never procedural first)
  * procedural/device only when explicitly chosen OR no image-derived candidate exists
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _catalog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
STAGING_ROOT = CB_ROOT / "export_ready"
LIBRARY_ROOT = REPO_ROOT / ".docs" / "library"

# Package manifest for rows sourced from the curated intake package.
PACKAGE_MANIFEST = REPO_ROOT / ".docs/library/singh360_component_master_package/Singh360_Component_Master_Catalog.csv"
PACKAGE_SOURCES = REPO_ROOT / ".docs/library/singh360_component_master_package/sources"


def _rel(path: Path | None) -> str | None:
    if not path:
        return None
    return _catalog.rel_to_repo(path)


def load_decisions(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        if path:
            print(f"[warn] decisions file not found: {_rel(path)} (ignoring)", file=sys.stderr)
        return {}
    import csv
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return {r["id"]: r for r in csv.DictReader(fh) if r.get("id")}


def is_approved(row: dict, decision: dict) -> bool:
    d = (decision.get("decision") or "").strip().lower()
    if d:
        return d in {"approve", "approved", "yes", "y"}
    return (row.get("symbolStatus") or "").strip().lower() == "approved"


def copy_plan(src: Path, dest: Path, replace: bool) -> str:
    if dest.exists() and not replace:
        return "skip-exists"
    if dest.exists():
        return "overwrite"
    return "new"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=None,
                    help="Catalog CSV (default: package manifest, then workbench master).")
    ap.add_argument("--source-root", default=None)
    ap.add_argument("--decisions", default=str(CB_ROOT / "work/contact_sheets/review_decisions.csv"),
                    help="Contact sheet decisions CSV.")
    ap.add_argument("--staging", action="store_true")
    ap.add_argument("--apply-production", dest="apply_production", action="store_true")
    ap.add_argument("--apply", action="store_true", help="Alias for --apply-production.")
    ap.add_argument("--replace", action="store_true")
    return ap.parse_args(argv)


def _resolve_manifest_and_root(args) -> tuple[Path, Path]:
    if args.manifest:
        manifest = _catalog.resolve_manifest(args.manifest)
        if not manifest:
            raise SystemExit(f"[error] manifest not found: {args.manifest}")
        source_root = _catalog.resolve_source_root(args.source_root, manifest.parent)
        return manifest, source_root
    # Prefer workbench master (may include extra approved rows like cd_controls), else package.
    master = _catalog.DEFAULT_MANIFEST
    if master.exists():
        return master, _catalog.resolve_source_root(args.source_root, master.parent)
    if PACKAGE_MANIFEST.exists():
        return PACKAGE_MANIFEST.resolve(), _catalog.resolve_source_root(
            args.source_root or str(PACKAGE_SOURCES), PACKAGE_MANIFEST.parent)
    raise SystemExit("[error] no catalog manifest found.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest, source_root = _resolve_manifest_and_root(args)
    rows, _ = _catalog.load_rows(manifest, source_root)

    production = args.apply_production or args.apply
    staging = args.staging and not production

    if production:
        root = LIBRARY_ROOT
        manifest_out = LIBRARY_ROOT / "component_builder_export.json"
        mode, do_write = "APPLY-PRODUCTION", True
    elif staging:
        root = STAGING_ROOT
        manifest_out = STAGING_ROOT / "manifest.json"
        mode, do_write = "STAGING", True
    else:
        root = STAGING_ROOT
        manifest_out = CB_ROOT / "reports" / "export_preview.json"
        mode, do_write = "DRY-RUN", False

    comp_root = root / "components"
    edge_root = root / "edges"
    bw_root = root / "bw"
    sym_root = root / "symbols"

    decisions_path = Path(args.decisions)
    if not decisions_path.is_absolute():
        decisions_path = (REPO_ROOT / decisions_path).resolve()
    decisions = load_decisions(decisions_path)

    approved = [(r, decisions.get(r["id"], {})) for r in rows]
    approved = [(r, d) for (r, d) in approved if is_approved(r, d)]

    if not approved:
        print("[note] nothing approved. Export a decisions CSV from the contact sheet.")
        return 0

    print(f"[{mode}] {len(approved)} approved item(s).")
    print(f"[info] manifest={_rel(manifest)} source-root={_rel(source_root)}")
    print(f"[info] decisions={_rel(decisions_path) if decisions_path.exists() else 'MISSING'}")

    entries: list[dict] = []
    actions = skipped = 0
    edge_count = proc_only = missing_edge = 0

    for row, decision in approved:
        cat = row["category"] or "custom"
        cid = row["id"]
        rep = _catalog.resolve_export_representation(row, decision)

        for w in rep["warnings"]:
            print(f"[warn] {cid}: {w}", file=sys.stderr)

        src = Path(row["sourcePath"]) if row.get("sourcePath") else None
        comp_dest = edge_dest = bw_dest = sym_dest = None
        plans: list[tuple[Path, Path, str]] = []

        if src and src.exists():
            comp_dest = comp_root / cat / f"{cid}{src.suffix.lower()}"
            plans.append((src, comp_dest, copy_plan(src, comp_dest, args.replace)))
        elif row.get("sourceExists"):
            print(f"[warn] {cid}: source path missing on disk: {row.get('sourcePath')}")

        if rep["edge"]:
            edge_dest = edge_root / cat / f"{cid}__{rep['edgeVariant']}.png"
            plans.append((rep["edge"], edge_dest, copy_plan(rep["edge"], edge_dest, args.replace)))
            edge_count += 1
        elif rep["procedural"]:
            missing_edge += 1
        else:
            missing_edge += 1
            print(f"[warn] {cid}: no edge or procedural candidate to export")

        if rep["bw"]:
            bw_dest = bw_root / cat / f"{cid}__{rep['bwVariant']}.png"
            plans.append((rep["bw"], bw_dest, copy_plan(rep["bw"], bw_dest, args.replace)))

        if rep["procedural"]:
            sym_dest = sym_root / cat / f"{cid}__{rep['proceduralVariant']}.png"
            plans.append((rep["procedural"], sym_dest,
                          copy_plan(rep["procedural"], sym_dest, args.replace)))
            if not rep["edge"]:
                proc_only += 1

        for source, dest, status in plans:
            if status == "skip-exists":
                print(f"  [skip] exists: {_rel(dest)} (use --replace)")
                skipped += 1
                continue
            verb = "copy" if do_write else "would-copy"
            tag = " (OVERWRITE)" if status == "overwrite" else ""
            print(f"  [{verb}] {_rel(source)} -> {_rel(dest)}{tag}")
            if do_write:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                actions += 1

        chosen = (decision.get("chosenVariant") or "").strip() or rep["edgeVariant"] or rep["proceduralVariant"]
        entry = {
            "id": cid,
            "displayName": row["displayName"],
            "manufacturer": row["manufacturer"],
            "category": cat,
            "partNumber": row["partNumber"],
            "defaultLabel": row.get("defaultLabel") or row["displayName"],
            "aliases": [a for a in (row["aliases"].split(";")) if a],
            "chosenVariant": chosen,
            "sourcePath": _rel(comp_dest),
            "edgePath": _rel(edge_dest),
            "bwPath": _rel(bw_dest),
            "symbolPath": _rel(sym_dest),
            "hasSource": bool(comp_dest and src and src.exists()),
            "hasEdge": bool(edge_dest),
            "hasBw": bool(bw_dest),
            "hasProcedural": bool(sym_dest),
            "notes": decision.get("notes") or row.get("notes") or "",
            # legacy aliases for older readers
            "sourceComponent": _rel(comp_dest),
            "symbol": _rel(edge_dest) or _rel(sym_dest),
        }
        entries.append(entry)

    payload = {
        "schemaVersion": "0.3",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "note": "edgePath = approved image-derived stencil. symbolPath = procedural wireframe only.",
        "components": entries,
    }

    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[ok] wrote manifest {_rel(manifest_out)}")
    if do_write:
        print(f"[ok] {mode}: {actions} file copy action(s); {skipped} skipped.")
        print(f"[ok] edgePath exports: {edge_count} | procedural-only: {proc_only} | missing edge: {missing_edge}")
    else:
        print(f"[ok] dry-run preview (no files copied unless --staging / --apply-production).")
        print(f"[ok] would export edgePath: {edge_count} | procedural-only: {proc_only} | missing edge: {missing_edge}")
        print("[note] re-run with --apply or --apply-production when paths look correct.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
