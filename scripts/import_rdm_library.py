"""scripts/import_rdm_library.py — import official RDM Layout Editor image library.

Usage:
  python scripts/import_rdm_library.py "C:\\Program Files (x86)\\RDM Layout Editor 3\\Images"
  python scripts/import_rdm_library.py "C:\\Program Files (x86)\\RDM Layout Editor 3\\Images" --dry-run
  python scripts/import_rdm_library.py "..." --source-name "RDM Layout Editor 3" --no-auto-approve
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.library_store import LibraryStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Import official RDM image library into local .docs/library")
    ap.add_argument("path", help="Folder path (e.g. C:\\Program Files (x86)\\RDM Layout Editor 3\\Images)")
    ap.add_argument("--dry-run", action="store_true", help="Preview only, do not copy files")
    ap.add_argument("--source-name", default="RDM Layout Editor 3", help="Source display name")
    ap.add_argument("--reset-rdm-import", action="store_true", help="Reset existing RDM-imported records before import")
    ap.add_argument("--no-auto-approve", action="store_true", help="Disable auto-approval of high-confidence files")
    args = ap.parse_args()

    store = LibraryStore(ROOT / ".docs", ROOT)
    res = store.import_rdm_folder(
        args.path,
        dry_run=args.dry_run,
        source_name=args.source_name,
        reset_rdm_import=args.reset_rdm_import,
        auto_approve=not args.no_auto_approve,
    )
    if not res.get("ok"):
        print(f"ERROR: {res.get('error', 'RDM import failed')}")
        return 1

    print("RDM import result")
    print(f"  dryRun: {res.get('dryRun', False)}")
    print(f"  scanned: {res.get('scanned', 0)}")
    print(f"  added: {res.get('added', 0)}")
    print(f"  skippedDuplicates: {res.get('skippedDuplicates', 0)}")
    print(f"  updated: {res.get('updated', 0)}")
    print(f"  needsReview: {res.get('needsReview', 0)}")
    print("  categories:")
    for k, v in sorted((res.get("categories") or {}).items()):
        print(f"    - {k}: {v}")
    errs = res.get("errors") or []
    if errs:
        print(f"  errors: {len(errs)}")
        for e in errs[:20]:
            print(f"    - {e}")
    preview = res.get("preview") or []
    if preview:
        print("  preview (first 20):")
        for row in preview[:20]:
            print(f"    - {row.get('action')}: {row.get('displayName')} [{row.get('category')}] ({row.get('file')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
