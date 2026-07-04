"""core/workspace_reset.py — safe, archive-first local workspace cleanup.

Moves generated project data into a timestamped archive folder under
``.docs/_archive/YYYYMMDD-HHMMSS/`` instead of deleting it. The component
library, seed, and source code are preserved unless a caller explicitly opts
into a library reset (which is still an archive, never a hard delete by default).

This module is shared by:
  - scripts/reset_local_workspace.py (CLI)
  - server.py  (File ▸ Clean Workspace modal)
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# Folders that are ALWAYS preserved — never archived or deleted by this tool.
PROTECTED_NAMES = {"library", "_archive"}


@dataclass
class ResetPlan:
    """A description of what a reset run did (or would do in dry-run)."""

    dry_run: bool
    archive_dir: str = ""
    moved: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dryRun": self.dry_run,
            "archiveDir": self.archive_dir,
            "moved": self.moved,
            "kept": self.kept,
            "notes": self.notes,
            "movedCount": len(self.moved),
        }


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def run_reset(
    docs_dir: Path,
    *,
    archive_projects: bool = True,
    archive_exports: bool = True,
    archive_tmp: bool = True,
    archive_debug: bool = True,
    include_legacy_flat_json: bool = False,
    reset_library: bool = False,
    dry_run: bool = False,
) -> ResetPlan:
    """Archive selected generated data. Returns a ResetPlan.

    Nothing is ever hard-deleted here. Everything selected is MOVED into a fresh
    timestamped folder under ``.docs/_archive/``. The component library is only
    touched when ``reset_library`` is explicitly True (and even then it is
    archived, not deleted).
    """
    docs_dir = Path(docs_dir)
    plan = ResetPlan(dry_run=dry_run)
    if not docs_dir.exists():
        plan.notes.append(f"docs dir does not exist yet: {docs_dir}")
        return plan

    archive_root = docs_dir / "_archive" / _timestamp()
    plan.archive_dir = str(archive_root)

    def _move(src: Path, rel_label: str) -> None:
        if not src.exists():
            return
        if src.name in PROTECTED_NAMES and not (reset_library and src.name == "library"):
            plan.kept.append(rel_label)
            return
        plan.moved.append(rel_label)
        if dry_run:
            return
        dest = archive_root / rel_label
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))

    # Whole-directory targets.
    dir_targets: list[tuple[bool, str]] = [
        (archive_projects, "projects"),
        (archive_exports, "exports"),
        (archive_tmp, "tmp"),
        (archive_debug, "debug"),
        (True, "assets/legacy"),
    ]
    for enabled, rel in dir_targets:
        if enabled:
            _move(docs_dir / rel, rel)

    # Legacy flat project JSON files at the docs root (opt-in).
    if include_legacy_flat_json:
        for p in sorted(docs_dir.glob("*.json")):
            _move(p, p.name)

    # Library reset is explicit-only and still archived (never deleted).
    if reset_library:
        plan.notes.append("Library reset requested — library folder ARCHIVED (not deleted).")
        _move(docs_dir / "library", "library")
    else:
        lib = docs_dir / "library"
        if lib.exists():
            plan.kept.append("library")

    if not plan.moved:
        plan.notes.append("Nothing to archive — workspace already clean.")

    return plan
