"""Back up and clean obvious integer identifier columns in active projects."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.source_number_cleanup import clean_project_integer_columns


def main() -> int:
    docs = ROOT / ".docs"
    projects = docs / "projects"
    if not projects.is_dir():
        print("[NOTE] No active project folders found.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = docs / "patch_backups" / f"source_integer_columns_{stamp}"
    touched_projects = 0
    touched_cells = 0

    for project_json in sorted(projects.glob("*__*/project.json")):
        try:
            project = json.loads(project_json.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[WARN] Skipped unreadable project: {project_json}: {exc}")
            continue

        changed = clean_project_integer_columns(project)
        if not changed:
            continue

        relative = project_json.relative_to(projects)
        backup = backup_root / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project_json, backup)

        project["lastSavedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        project_json.write_text(
            json.dumps(project, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        touched_projects += 1
        touched_cells += changed
        print(f"[OK] {project_json.parent.name}: cleaned {changed} cell(s)")

    if touched_projects:
        print(
            f"[OK] Cleaned {touched_cells} integer identifier cell(s) "
            f"in {touched_projects} project(s)."
        )
        print(f"[OK] Project backups: {backup_root}")
    else:
        print("[OK] No saved integer identifier cells required cleanup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
