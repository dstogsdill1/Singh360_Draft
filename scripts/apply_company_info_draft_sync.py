"""Make Company Info Published output read the current Draft worksheet rows.

The existing refresh path updates cover/table/matrix/excel-exact blocks but skips
companyInfo blocks. That produces a false "Published updated" status while the
Published page still renders stale cached rows. This patch adds companyInfo to
the source-first refresh path. It changes source code only; no workbook or
project JSON is modified.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path("frontend/src/model/excelRange.ts")

OLD = """    } else {
      const tableIdx = blocks.findIndex((b) => b.type === 'matrix' || b.type === 'table');
      if (tableIdx < 0) {
        nextBlocks = blocks;
      } else {
        const normalized = trimTrailingEmptyColumns(visibleWs.grid ?? []);
        const headers = (normalized[0] ?? []).map((x) => x ?? '');
        const rows = normalized.slice(1).map((r) => r.map((x) => x ?? ''));
        nextBlocks = blocks.map((b, i) => (i === tableIdx ? { ...b, headers, rows } : b));
      }
    }
"""

NEW = """    } else {
      const companyInfoIdx = blocks.findIndex((b) => b.type === 'companyInfo');
      if (companyInfoIdx >= 0) {
        // Company Info is a purpose-built Published renderer, but its values
        // still come directly from the current Draft worksheet. Keep every
        // nontrailing source column so Field / Value rows such as Drawing
        // Standard update immediately when switching back to Published.
        const rows = trimTrailingEmptyColumns(visibleWs.grid ?? []);
        nextBlocks = blocks.map((b, i) => (i === companyInfoIdx ? { ...b, rows } : b));
      } else {
        const tableIdx = blocks.findIndex((b) => b.type === 'matrix' || b.type === 'table');
        if (tableIdx < 0) {
          nextBlocks = blocks;
        } else {
          const normalized = trimTrailingEmptyColumns(visibleWs.grid ?? []);
          const headers = (normalized[0] ?? []).map((x) => x ?? '');
          const rows = normalized.slice(1).map((r) => r.map((x) => x ?? ''));
          nextBlocks = blocks.map((b, i) => (i === tableIdx ? { ...b, headers, rows } : b));
        }
      }
    }
"""


class PatchError(RuntimeError):
    pass


def patch_text(text: str) -> str:
    if NEW in text:
        return text
    count = text.count(OLD)
    if count != 1:
        raise PatchError(f"Expected one refreshPageFromSource table branch, found {count}.")
    return text.replace(OLD, NEW, 1)


def validate_text(text: str) -> None:
    required = [
        "const companyInfoIdx = blocks.findIndex((b) => b.type === 'companyInfo');",
        "const rows = trimTrailingEmptyColumns(visibleWs.grid ?? []);",
        "i === companyInfoIdx ? { ...b, rows } : b",
        "const tableIdx = blocks.findIndex((b) => b.type === 'matrix' || b.type === 'table');",
    ]
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise PatchError("Company Info Draft sync validation failed: " + ", ".join(missing))


def apply(repo: Path) -> Path:
    target = repo / TARGET
    if not target.is_file():
        raise PatchError(f"Required source file is missing: {target}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = repo / ".docs" / "patch_backups" / f"company_info_draft_sync_{stamp}" / TARGET
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)

    try:
        next_text = patch_text(target.read_text(encoding="utf-8"))
        validate_text(next_text)
        target.write_text(next_text, encoding="utf-8")
    except Exception:
        shutil.copy2(backup, target)
        raise

    print(f"[OK] Company Info Draft sync installed: {target}")
    print(f"[OK] Source backup: {backup.parent.parent.parent}")
    return backup


def latest_backup(repo: Path) -> Path:
    root = repo / ".docs" / "patch_backups"
    choices = sorted(
        (p for p in root.glob("company_info_draft_sync_*") if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    if not choices:
        raise PatchError("No Company Info Draft-sync backup was found.")
    return choices[0]


def restore_latest(repo: Path) -> None:
    backup_root = latest_backup(repo)
    source = backup_root / TARGET
    target = repo / TARGET
    if not source.is_file():
        raise PatchError(f"Backup source is missing: {source}")
    shutil.copy2(source, target)
    print(f"[OK] Restored {target} from {backup_root}")


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        target = root / TARGET
        target.parent.mkdir(parents=True, exist_ok=True)
        fixture = """function refreshPageFromSource() {
    } else {
      const tableIdx = blocks.findIndex((b) => b.type === 'matrix' || b.type === 'table');
      if (tableIdx < 0) {
        nextBlocks = blocks;
      } else {
        const normalized = trimTrailingEmptyColumns(visibleWs.grid ?? []);
        const headers = (normalized[0] ?? []).map((x) => x ?? '');
        const rows = normalized.slice(1).map((r) => r.map((x) => x ?? ''));
        nextBlocks = blocks.map((b, i) => (i === tableIdx ? { ...b, headers, rows } : b));
      }
    }
}
"""
        target.write_text(fixture, encoding="utf-8")
        (root / ".docs").mkdir(parents=True, exist_ok=True)
        apply(root)
        patched = target.read_text(encoding="utf-8")
        validate_text(patched)
        assert patched.count("companyInfoIdx") >= 3
        print("[OK] Synthetic Company Info Draft-sync self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--restore-latest", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / "server.py").is_file():
        raise PatchError(f"Singh360 repository not found: {repo}")

    if args.restore_latest:
        restore_latest(repo)
    else:
        apply(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
