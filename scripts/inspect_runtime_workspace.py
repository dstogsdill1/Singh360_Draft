"""scripts/inspect_runtime_workspace.py

Inspect local `.docs` runtime workspace and print current state + cleanup dry-run
summary (no mutations).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cleanup_runtime_workspace import LEGACY_REL_PATHS, run_cleanup


def count_files(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.rglob(pattern))


def project_count(docs: Path) -> int:
    p = docs / "projects"
    if not p.exists():
        return 0
    # Count projects by project.json files or top-level folders.
    by_json = sum(1 for _ in p.rglob("project.json"))
    return by_json if by_json else sum(1 for d in p.iterdir() if d.is_dir())


def main() -> int:
    docs = Path(".docs").resolve()
    lib = docs / "library"
    comps = lib / "components"
    thumbs = lib / "thumbnails"
    manifest = lib / "manifest.json"

    print("=== Runtime Workspace Inspection ===")
    print(f"docs_root: {docs}")
    print("existing_docs_folders:")
    if docs.exists():
        for p in sorted([x for x in docs.rglob("*") if x.is_dir()]):
            print(f"  - {p.relative_to(docs)}")
    else:
        print("  - (none)")

    print(f"active_project_count: {project_count(docs)}")

    by_cat = {}
    if comps.exists():
        for cat in sorted([d for d in comps.iterdir() if d.is_dir()]):
            by_cat[cat.name] = sum(1 for f in cat.rglob("*") if f.is_file() and not f.name.lower().endswith('.symbol.svg'))
    print("library_component_counts:")
    print(json.dumps(by_cat, indent=2))

    fake_symbols = sum(1 for _ in comps.rglob("*.symbol.svg")) if comps.exists() else 0
    thumb_count = count_files(thumbs) if thumbs.exists() else 0
    print(f"generated_fake_symbol_count: {fake_symbols}")
    print(f"thumbnail_count: {thumb_count}")

    dup_archives = []
    for rel in ("_archive", "library/_archive", "archive"):
        p = docs / rel
        if p.exists():
            dup_archives.append(str(p.relative_to(docs)))
    print(f"duplicate_archive_folders_found: {dup_archives}")

    legacy_found = []
    for rel in LEGACY_REL_PATHS:
        p = docs / rel
        if p.exists():
            legacy_found.append(str(p.relative_to(docs)))
    print(f"legacy_folders_found: {legacy_found}")

    dry = run_cleanup(docs, apply=False)
    print("cleanup_dry_run:")
    print(json.dumps(dry, indent=2))

    # Manifest quick view
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            print(f"manifest_components: {len(data.get('components', []))}")
        except Exception:
            print("manifest_components: unreadable")
    else:
        print("manifest_components: manifest_missing")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
