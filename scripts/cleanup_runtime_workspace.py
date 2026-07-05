"""scripts/cleanup_runtime_workspace.py

Consolidate legacy runtime folders into `.docs/archive/legacy_runtime_<timestamp>/`.
Default is dry-run; apply with `--apply`.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

LEGACY_REL_PATHS = [
    "assets",
    "library/assets",
    "_archive",
    "library/_archive",
    "library_staging",
    "library/processed",
    "library/retired",
    "library/inbox",
]


def ensure_minimal(docs: Path) -> None:
    (docs / "projects").mkdir(parents=True, exist_ok=True)
    (docs / "exports").mkdir(parents=True, exist_ok=True)
    (docs / "archive").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "components").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "symbols").mkdir(parents=True, exist_ok=True)
    (docs / "library" / "thumbnails").mkdir(parents=True, exist_ok=True)
    manifest = docs / "library" / "manifest.json"
    aliases = docs / "library" / "aliases.json"
    connectors = docs / "library" / "connector_styles.json"
    if not manifest.exists():
        manifest.write_text('{\n  "version": 2,\n  "components": []\n}\n', encoding="utf-8")
    if not aliases.exists():
        aliases.write_text('{\n  "version": 1,\n  "aliases": {}\n}\n', encoding="utf-8")
    if not connectors.exists():
        connectors.write_text('{\n  "version": 1,\n  "presets": []\n}\n', encoding="utf-8")


def legacy_existing(docs: Path) -> list[Path]:
    found: list[Path] = []
    for rel in LEGACY_REL_PATHS:
        p = docs / rel
        if p.exists():
            found.append(p)
    return found


def run_cleanup(docs: Path, apply: bool) -> dict:
    docs = docs.resolve()
    ensure_minimal(docs)
    found = legacy_existing(docs)
    if not apply:
        return {
            "ok": True,
            "dryRun": True,
            "legacyFound": [str(p) for p in found],
            "willArchive": len(found),
            "willCreate": [
                str(docs / "projects"),
                str(docs / "exports"),
                str(docs / "archive"),
                str(docs / "library" / "components"),
                str(docs / "library" / "symbols"),
                str(docs / "library" / "thumbnails"),
                str(docs / "library" / "manifest.json"),
                str(docs / "library" / "aliases.json"),
                str(docs / "library" / "connector_styles.json"),
            ],
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_root = docs / "archive" / f"legacy_runtime_{stamp}"
    archive_root.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for src in found:
        rel = src.relative_to(docs)
        dst = archive_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dst))
            moved.append(str(rel))
        except Exception:
            pass

    ensure_minimal(docs)
    return {
        "ok": True,
        "dryRun": False,
        "archiveDir": str(archive_root),
        "moved": moved,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=".docs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    apply = bool(args.apply and not args.dry_run)
    result = run_cleanup(Path(args.docs), apply=apply)
    for k, v in result.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
