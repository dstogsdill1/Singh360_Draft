"""Repair an accidental all-Legends bulk edit when it reached disk."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.library_v2 import LibraryV2


def main() -> int:
    library = LibraryV2(ROOT / ".docs")
    result = library.repair_accidental_legend_bulk()
    if result.get("repaired"):
        print(
            f"[OK] Restored {result.get('restored', 0)} component categorization "
            f"override(s). Snapshot: {result.get('snapshot', '')}"
        )
    else:
        print(f"[OK] No saved all-Legends corruption found: {result.get('reason', 'not suspicious')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
