"""scripts/reset_local_workspace.py — safe, archive-first local workspace reset.

Archives generated project data (projects / exports / tmp / debug / legacy
assets) into a timestamped folder under ``.docs/_archive/`` so you can start
fresh WITHOUT hand-deleting folders. The component library and source code are
preserved.

Examples:
    python scripts/reset_local_workspace.py --dry-run
    python scripts/reset_local_workspace.py --archive-projects
    python scripts/reset_local_workspace.py --archive-projects --include-legacy-flat-json

Safety:
  - Archive, never delete (by default). No --delete is implemented here.
  - The component library is NEVER touched unless BOTH
    --reset-library and --confirm-reset-library are passed (and it is archived,
    not deleted).
  - Source code is never touched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.workspace_reset import run_reset  # noqa: E402

DOCS_DIR = ROOT / ".docs"


def main() -> int:
    ap = argparse.ArgumentParser(description="Safe archive-first workspace reset.")
    ap.add_argument("--archive-projects", action="store_true", help="Archive .docs/projects/")
    ap.add_argument("--archive-exports", action="store_true", help="Archive .docs/exports/")
    ap.add_argument("--archive-tmp", action="store_true", help="Archive .docs/tmp/ and .docs/debug/")
    ap.add_argument("--include-legacy-flat-json", action="store_true", help="Also archive legacy .docs/*.json project files")
    ap.add_argument("--reset-library", action="store_true", help="Archive the component library (requires --confirm-reset-library)")
    ap.add_argument("--confirm-reset-library", action="store_true", help="Confirm the library archive")
    ap.add_argument("--dry-run", action="store_true", help="Print what would move; change nothing")
    args = ap.parse_args()

    # If no specific target is chosen, default to a full project/export/tmp archive.
    any_target = args.archive_projects or args.archive_exports or args.archive_tmp
    archive_projects = args.archive_projects or not any_target
    archive_exports = args.archive_exports or not any_target
    archive_tmp = args.archive_tmp or not any_target

    reset_library = False
    if args.reset_library:
        if not args.confirm_reset_library:
            print("REFUSING: --reset-library requires --confirm-reset-library.")
            print("The component library will NOT be touched.")
            return 2
        print("WARNING: the component library will be ARCHIVED (not deleted).")
        reset_library = True

    plan = run_reset(
        DOCS_DIR,
        archive_projects=archive_projects,
        archive_exports=archive_exports,
        archive_tmp=archive_tmp,
        archive_debug=archive_tmp,
        include_legacy_flat_json=args.include_legacy_flat_json,
        reset_library=reset_library,
        dry_run=args.dry_run,
    )

    mode = "DRY RUN — nothing moved" if args.dry_run else "ARCHIVED"
    print(f"=== Workspace reset ({mode}) ===")
    print(f"archive dir: {plan.archive_dir}")
    if plan.moved:
        print("would move:" if args.dry_run else "moved:")
        for m in plan.moved:
            print(f"  - {m}")
    if plan.kept:
        print("kept (protected):")
        for k in plan.kept:
            print(f"  - {k}")
    for n in plan.notes:
        print(f"note: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
