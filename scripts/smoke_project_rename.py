"""scripts/smoke_project_rename.py — rename must not duplicate project folders.

Self-contained (no workbook needed). Uses a temp docs dir and asserts:
- rename moves the folder to the new slug (single canonical folder for the ID)
- renaming when the target slug folder already exists reuses it (no duplicate)
- planted duplicate folders are detected and archived (never deleted)
- list_projects reports one row per project ID with the new fields
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project_store import ProjectStore, slugify  # noqa: E402


def _count_id_dirs(store: ProjectStore, pid: str) -> int:
    return len(list(store.projects_dir.glob(f"*__{pid}")))


def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        store = ProjectStore(Path(tmp))
        pid = "a1b2c3d4e5f60718"
        store.save(pid, {"metadata": {"projectName": "Original Name"}, "pages": []})

        if _count_id_dirs(store, pid) != 1:
            problems.append("expected exactly 1 folder after initial save")

        # 1) Basic rename → single folder at the new slug.
        store.rename(pid, "Second Name")
        if _count_id_dirs(store, pid) != 1:
            problems.append(f"rename produced {_count_id_dirs(store, pid)} folders (expected 1)")
        canonical = store.find_dir(pid)
        if canonical is None or not canonical.name.startswith(slugify("Second Name")):
            problems.append(f"canonical folder not at new slug: {canonical}")

        # 2) Plant a stale duplicate folder for the SAME id, then rename back.
        stale = store.projects_dir / f"{slugify('Original Name')}__{pid}"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "project.json").write_text("{}", encoding="utf-8")
        if _count_id_dirs(store, pid) != 2:
            problems.append("failed to plant duplicate folder for test")

        dups = store.detect_duplicate_folders(pid)
        if len(dups) != 1:
            problems.append(f"detect_duplicate_folders returned {len(dups)} (expected 1)")

        # 3) Rename onto the existing (planted) slug — must reuse, not triplicate.
        store.rename(pid, "Original Name")
        if _count_id_dirs(store, pid) != 1:
            problems.append(f"rename-onto-existing produced {_count_id_dirs(store, pid)} folders (expected 1)")

        # Archived folder must still exist on disk (never deleted).
        archived = list((store.projects_dir / "_archive").glob("*"))
        if not archived:
            problems.append("archived duplicate folder missing (should be preserved, not deleted)")

        # 4) Plant another dup, then explicit archive action.
        stale2 = store.projects_dir / f"third-name__{pid}"
        stale2.mkdir(parents=True, exist_ok=True)
        (stale2 / "project.json").write_text("{}", encoding="utf-8")
        moved = store.archive_duplicate_folders(pid)
        if len(moved) != 1:
            problems.append(f"archive_duplicate_folders moved {len(moved)} (expected 1)")
        if _count_id_dirs(store, pid) != 1:
            problems.append("archive left more than 1 canonical folder")

        # 5) list_projects: one row per ID, with the new fields.
        rows = [r for r in store.list_projects() if r["id"] == pid]
        if len(rows) != 1:
            problems.append(f"list_projects returned {len(rows)} rows for id (expected 1)")
        elif not {"packageFile", "sourceWorkbook", "duplicateFolders", "lastSavedAt"} <= set(rows[0]):
            problems.append("list_projects row missing new fields")

    if problems:
        print("RENAME/DEDUP PROBLEMS:")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("OK: project rename / duplicate-folder checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
