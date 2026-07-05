#!/usr/bin/env python3
"""run_master_pipeline.py -- the one command for the master component workflow.

Most of the time this is all you run:

    python tools/component_builder/run_master_pipeline.py --open

It will (in order):
  1. ensure the workbench folders exist,
  2. sync the master Excel -> CSV when the workbook is newer (unless --skip-sync),
  3. build the review manifest from the master CSV,
  4. generate black/white symbol candidates,
  5. build the review contact sheet,
  6. open the contact sheet in your browser if --open,
  7. print clear next steps.

Everything stays inside .docs/component_builder/. The production .docs/library is
never touched here -- that only happens later via export_approved_symbols.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _catalog  # noqa: E402
import build_inventory  # noqa: E402
import make_contact_sheet  # noqa: E402
import make_line_art_candidates  # noqa: E402
import sync_master_excel  # noqa: E402

CB_ROOT = _catalog.CB_ROOT
WORKBOOK = _catalog.PACKAGE_DIR / "Singh360_Component_Master_Catalog.xlsx"

ENSURE_DIRS = [
    _catalog.PACKAGE_DIR,
    _catalog.PACKAGE_DIR / "sources",
    CB_ROOT / "work" / "symbol_candidates",
    CB_ROOT / "work" / "contact_sheets",
    CB_ROOT / "approved",
    CB_ROOT / "reports",
    CB_ROOT / "export_ready",
]


def _rel(p: Path) -> str:
    return _catalog.rel_to_repo(p)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--open", action="store_true", help="Open the contact sheet when done.")
    ap.add_argument("--sync-excel", action="store_true", help="Force Excel->CSV sync.")
    ap.add_argument("--skip-sync", action="store_true", help="Never sync Excel->CSV.")
    ap.add_argument("--replace-candidates", action="store_true",
                    help="Regenerate candidate PNGs even if they exist.")
    ap.add_argument("--manifest", default=None, help="Override master CSV path.")
    ap.add_argument("--source-root", default=None, help="Override sources root.")
    return ap.parse_args(argv)


def _needs_sync(workbook: Path, csv_path: Path) -> bool:
    if not workbook.exists():
        return False
    if not csv_path.exists():
        return True
    try:
        return workbook.stat().st_mtime > csv_path.stat().st_mtime
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    for d in ENSURE_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    manifest = Path(args.manifest).resolve() if args.manifest else _catalog.DEFAULT_MANIFEST
    source_root = Path(args.source_root).resolve() if args.source_root else _catalog.DEFAULT_SOURCE_ROOT

    print("=" * 64)
    print("Singh360 Component Builder -- master pipeline")
    print("=" * 64)
    print(f"master folder : {_rel(_catalog.PACKAGE_DIR)}")
    print(f"manifest CSV  : {_rel(manifest)}")
    print(f"sources root  : {_rel(source_root)}")

    # 2. sync excel -> csv
    do_sync = args.sync_excel or (not args.skip_sync and _needs_sync(WORKBOOK, manifest))
    if do_sync:
        print("\n[1/4] sync Excel -> CSV")
        rc = sync_master_excel.main(["--workbook", str(WORKBOOK), "--out-csv", str(manifest),
                                     "--source-root", str(source_root)])
        if rc != 0:
            print("[warn] Excel sync failed; continuing with existing CSV.", file=sys.stderr)
    else:
        why = "skipped (--skip-sync)" if args.skip_sync else "CSV already up to date"
        print(f"\n[1/4] sync Excel -> CSV: {why}")

    if not manifest.exists():
        print(f"[error] no manifest CSV at {_rel(manifest)}. Add the master workbook/CSV "
              f"under {_rel(_catalog.PACKAGE_DIR)}.", file=sys.stderr)
        return 2

    # 3. build inventory
    print("\n[2/4] build review manifest")
    build_inventory.main(["--manifest", str(manifest), "--source-root", str(source_root)])

    # 4. generate candidates
    print("\n[3/4] generate B/W candidates")
    cand_argv = ["--manifest", str(manifest), "--source-root", str(source_root)]
    if args.replace_candidates:
        cand_argv.append("--replace")
    make_line_art_candidates.main(cand_argv)

    # 5. contact sheet
    print("\n[4/4] build contact sheet")
    cs_argv = ["--manifest", str(manifest), "--source-root", str(source_root)]
    if args.open:
        cs_argv.append("--open")
    make_contact_sheet.main(cs_argv)

    sheet = CB_ROOT / "work" / "contact_sheets" / "index.html"
    print("\n" + "=" * 64)
    print("NEXT STEPS")
    print("=" * 64)
    print(f"1. Review the contact sheet:  {_rel(sheet)}")
    print("2. Approve/reject items, pick a variant, then click 'Export decisions CSV'.")
    print("3. Dry-run the export (writes nothing):")
    print("     python tools/component_builder/export_approved_symbols.py "
          "--decisions <downloaded>.csv")
    print("4. Stage approved items safely (does NOT touch the app library):")
    print("     python tools/component_builder/export_approved_symbols.py "
          "--decisions <downloaded>.csv --staging")
    print("   Do NOT export to production yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
