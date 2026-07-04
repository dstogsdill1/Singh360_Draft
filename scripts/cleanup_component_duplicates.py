"""scripts/cleanup_component_duplicates.py

Cleanup duplicate component files under .docs/library/assets/components.

Examples:
  python scripts/cleanup_component_duplicates.py --dry-run
  python scripts/cleanup_component_duplicates.py --archive-current --archive-duplicates --dedupe-all
  python scripts/cleanup_component_duplicates.py --archive-duplicates --dedupe-category alarm
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.library_store import LibraryStore  # noqa: E402


def archive_current_state(store: LibraryStore) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = store.dir / "_archive" / f"exploded_library_{ts}"
    dst.mkdir(parents=True, exist_ok=True)

    copied_files = 0
    total_bytes = 0
    items = [
        store.dir / "assets" / "components",
        store.dir / "assets" / "thumbnails",
        store.dir / "assets" / "rendered",
        store.dir / "library.json",
    ]
    for src in items:
        if not src.exists():
            continue
        target = dst / src.name
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target)
            for p in target.rglob("*"):
                if p.is_file():
                    copied_files += 1
                    total_bytes += p.stat().st_size
        else:
            shutil.copy2(src, target)
            copied_files += 1
            total_bytes += target.stat().st_size
    return {
        "archivePath": str(dst),
        "files": copied_files,
        "bytes": total_bytes,
        "timestamp": ts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Cleanup component duplicate explosion")
    ap.add_argument("--dry-run", action="store_true", help="Detect duplicates without moving files")
    ap.add_argument("--archive-current", action="store_true", help="Archive current exploded state before cleanup")
    ap.add_argument("--archive-duplicates", action="store_true", help="Move duplicate files into archive")
    ap.add_argument("--dedupe-category", help="Limit cleanup to one category folder")
    ap.add_argument("--dedupe-all", action="store_true", help="Dedupe all categories")
    args = ap.parse_args()

    store = LibraryStore(ROOT / ".docs", ROOT)

    if args.archive_current:
        info = archive_current_state(store)
        print("Archived current library state:")
        print(json.dumps(info, indent=2))

    res = store.cleanup_duplicates(
        dry_run=args.dry_run,
        archive_duplicates=args.archive_duplicates,
        dedupe_category=args.dedupe_category,
        dedupe_all=args.dedupe_all,
    )
    if not res.get("ok"):
        print(f"ERROR: {res.get('error', 'cleanup failed')}")
        return 1

    print("Duplicate cleanup result:")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
