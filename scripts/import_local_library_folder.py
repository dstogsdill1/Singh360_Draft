"""scripts/import_local_library_folder.py — import/reset from a local library assets folder.

Usage:
    python scripts/import_local_library_folder.py "C:\\path\\to\\Singh360_Component_Library_Seed\\library\\assets" --dry-run
    python scripts/import_local_library_folder.py "C:\\path\\to\\Singh360_Component_Library_Seed\\library\\assets" --reset-clean
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
    ap = argparse.ArgumentParser(description="Import/reset Singh360 local component library from a folder")
    ap.add_argument("path", help="Path to local library assets folder")
    ap.add_argument("--dry-run", action="store_true", help="Preview only; do not copy/update files")
    ap.add_argument("--reset-clean", action="store_true", help="Archive old non-curated entries before import")
    ap.add_argument("--source-name", default="Local Library Folder", help="Source label written to metadata")
    args = ap.parse_args()

    store = LibraryStore(ROOT / ".docs", ROOT)
    res = store.import_local_folder(
        args.path,
        dry_run=args.dry_run,
        reset_clean=args.reset_clean,
        source_name=args.source_name,
    )
    if not res.get("ok"):
        print(f"ERROR: {res.get('error', 'import failed')}")
        return 1

    print("Local library import result")
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
