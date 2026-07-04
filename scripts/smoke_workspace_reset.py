"""scripts/smoke_workspace_reset.py — verify safe archive-first workspace reset.

Self-contained (temp docs dir). Asserts:
  - dry-run moves nothing on disk but reports the plan
  - archive moves projects/exports/tmp into .docs/_archive/<ts>/
  - the component library is preserved (never archived by default)
  - reset_library requires explicit confirmation and only ARCHIVES (never deletes)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.workspace_reset import run_reset  # noqa: E402


def _seed(docs: Path) -> None:
    (docs / "projects" / "demo__abc").mkdir(parents=True, exist_ok=True)
    (docs / "projects" / "demo__abc" / "project.json").write_text("{}", encoding="utf-8")
    (docs / "exports").mkdir(parents=True, exist_ok=True)
    (docs / "exports" / "old.pdf").write_bytes(b"%PDF-1.4")
    (docs / "tmp").mkdir(parents=True, exist_ok=True)
    (docs / "tmp" / "scratch.txt").write_text("x", encoding="utf-8")
    (docs / "library" / "assets").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "library.json").write_text('{"components":[]}', encoding="utf-8")
    (docs / "keep-me.json").write_text("{}", encoding="utf-8")


def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp) / ".docs"

        # 1) Dry run — nothing on disk changes.
        _seed(docs)
        plan = run_reset(docs, dry_run=True)
        if not plan.dry_run:
            problems.append("dry-run flag lost")
        if not plan.moved:
            problems.append("dry-run should still report a plan of things to move")
        if not (docs / "projects" / "demo__abc").exists():
            problems.append("dry-run must NOT move anything on disk")

        # 2) Real archive — projects/exports/tmp move; library preserved.
        plan2 = run_reset(docs, include_legacy_flat_json=True)
        archive_root = Path(plan2.archive_dir)
        if (docs / "projects" / "demo__abc").exists():
            problems.append("projects should have been archived")
        if not (archive_root / "projects" / "demo__abc").exists():
            problems.append("archived project missing from archive dir")
        if not (archive_root / "exports" / "old.pdf").exists():
            problems.append("archived export missing")
        if not (docs / "library" / "library.json").exists():
            problems.append("component library must be preserved (Phase A requirement)")
        if "library" not in plan2.kept:
            problems.append("library should be reported as kept")
        if not (archive_root / "keep-me.json").exists():
            problems.append("legacy flat json should be archived when opted in")

        # 3) Library reset requires confirmation and only archives.
        _seed(docs)
        pl = run_reset(docs, reset_library=True)
        if not (Path(pl.archive_dir) / "library").exists():
            problems.append("reset_library should ARCHIVE the library folder")
        # The library was moved (archived), not deleted → archive copy exists.
        if not (Path(pl.archive_dir) / "library" / "library.json").exists():
            problems.append("library archive should preserve its contents (no delete)")

    if problems:
        print("WORKSPACE RESET PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: workspace reset checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
