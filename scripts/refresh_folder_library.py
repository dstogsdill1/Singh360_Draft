"""scripts/refresh_folder_library.py — refresh the folder-based master component library.

Usage:
    python scripts/refresh_folder_library.py "C:\\path\\to\\library\\assets" --dry-run
    python scripts/refresh_folder_library.py "C:\\path\\to\\library\\assets" --apply
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
    ap = argparse.ArgumentParser(description="Refresh folder-based master component library")
    ap.add_argument("path", help="Master library root (assets folder)")
    ap.add_argument("--dry-run", action="store_true", help="Preview only")
    ap.add_argument("--apply", action="store_true", help="Apply refresh")
    ap.add_argument("--reset-clean", action="store_true", help="Archive old non-curated entries before refresh")
    args = ap.parse_args()

    if args.dry_run and args.apply:
        print("Use either --dry-run or --apply, not both.")
        return 2

    store = LibraryStore(ROOT / ".docs", ROOT)
    set_res = store.set_master_root(args.path)
    if not set_res.get("ok"):
        print(f"ERROR: {set_res.get('error', 'Failed to set root')}")
        return 1

    dry = True if args.dry_run else (False if args.apply else True)
    res = store.refresh_from_master_root(dry_run=dry, reset_clean=args.reset_clean)
    if not res.get("ok"):
        print(f"ERROR: {res.get('error', 'Refresh failed')}")
        return 1

    print("Folder library refresh")
    print(f"  dryRun: {res.get('dryRun', False)}")
    print(f"  scanned: {res.get('scanned', 0)}")
    print(f"  added: {res.get('added', 0)}")
    print(f"  updated: {res.get('updated', 0)}")
    print(f"  skippedDuplicates: {res.get('skippedDuplicates', 0)}")
    print(f"  pdfConverted: {res.get('pdfConverted', 0)}")
    print(f"  needsReview: {res.get('needsReview', 0)}")
    print(f"  archivedOldEntries: {res.get('archivedOldEntries', 0)}")
    print("  categories:")
    for k, v in sorted((res.get("categories") or {}).items()):
        print(f"    - {k}: {v}")
    errs = res.get("errors") or []
    if errs:
        print(f"  errors: {len(errs)}")
        for e in errs[:20]:
            print(f"    - {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
