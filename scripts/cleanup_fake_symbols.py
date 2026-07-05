"""scripts/cleanup_fake_symbols.py

Archive generated fake `*.symbol.svg` files from `.docs/library/components/**`
into `.docs/archive/fake_symbols_<timestamp>/`, then clear manifest symbolFile
references and mark `symbolStatus=not_built`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.library_v2 import LibraryV2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=".docs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    lib = LibraryV2(Path(args.docs).resolve())
    lib.ensure()

    if args.dry_run and args.apply:
        print("Choose only one: --dry-run or --apply")
        return 1

    if args.apply:
        result = lib.archive_fake_symbols(dry_run=False)
    else:
        result = lib.archive_fake_symbols(dry_run=True)

    for k, v in result.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
