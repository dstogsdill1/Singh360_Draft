"""scripts/migrate_legacy_library_v2.py — migrate legacy library into V2.

Copies `.docs/library/assets/components/<cat>` source files into the V2 root
`.docs/library/components/<cat>`, skipping exact-SHA256 duplicates, archiving
the current manifest first, then optionally rebuilding thumbnails + generating
black-and-white symbols. Never deletes legacy files.

Usage:
    python scripts/migrate_legacy_library_v2.py --dry-run
    python scripts/migrate_legacy_library_v2.py --apply --rebuild-thumbnails --generate-symbols
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.library_v2 import LibraryV2  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate legacy component library into V2.")
    ap.add_argument("--docs", default=str(ROOT / ".docs"), help="Path to the .docs directory.")
    ap.add_argument("--dry-run", action="store_true", help="Preview only; make no changes.")
    ap.add_argument("--apply", action="store_true", help="Actually perform the migration.")
    ap.add_argument("--rebuild-thumbnails", action="store_true", help="Rebuild thumbnails after copy.")
    ap.add_argument("--generate-symbols", action="store_true", help="Generate B/W symbols after copy.")
    args = ap.parse_args()

    if not args.dry_run and not args.apply:
        args.dry_run = True  # default to a safe preview

    lib = LibraryV2(Path(args.docs))
    lib.ensure()

    if not lib.has_legacy():
        print("No legacy assets found at:", lib.legacy_root)
        return 0

    if args.dry_run and not args.apply:
        preview = lib.migrate_legacy(dry_run=True)
        print(json.dumps(preview, indent=2))
        print("\nDry run only. Re-run with --apply to migrate.")
        return 0

    result = lib.migrate_legacy(
        dry_run=False,
        rebuild_thumbnails=args.rebuild_thumbnails,
        generate_symbols=args.generate_symbols,
    )
    print(json.dumps(result, indent=2))
    data = lib.load()
    print(f"\nManifest components now: {data['counts']['total']} "
          f"(withSymbol={data['counts']['withSymbol']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
