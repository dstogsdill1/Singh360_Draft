"""CLI and permanent renderer patch for the complete SA31 workbook refresh."""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from scripts.sa31_refresh_core import DEFAULT_PROJECT_ID, MigrationError, apply_migration, self_test

SOURCE_PATCH_MARKER = "SA31 EXACT RANGE CENTERING + STABLE REBUILD"


def _find_repo(argument: str | None) -> Path:
    candidates: list[Path] = []
    if argument:
        candidates.append(Path(argument))
    candidates.extend([
        Path.cwd(),
        Path.home() / "OneDrive - Homeland Development Services LLC" / "Desktop" / "Singh360_SmartDraw",
        Path.home() / "Desktop" / "Singh360_SmartDraw",
    ])
    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if (
            (candidate / "server.py").is_file()
            and (candidate / "core" / "workbook_importer.py").is_file()
            and (candidate / "frontend" / "src").is_dir()
        ):
            return candidate
    raise MigrationError("Singh360_SmartDraw repository was not found.")


def _backup_code_files(repo: Path, paths: Iterable[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = repo / ".docs" / "patch_backups" / f"sa31_full_refresh_code_{stamp}"
    for path in paths:
        if not path.is_file():
            raise MigrationError(f"Required source file is missing: {path}")
        dest = root / path.relative_to(repo)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    return root


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise MigrationError(f"Could not locate {label}.")
    return text.replace(old, new, 1)


def patch_renderer_sources(repo: Path) -> dict[str, Any]:
    """Install centering, common max-scale support, and stable continuation rebuild."""
    types_path = repo / "frontend" / "src" / "model" / "types.ts"
    renderer_path = repo / "frontend" / "src" / "components" / "renderers" / "ExcelRangeRenderer.tsx"
    rebuild_path = repo / "frontend" / "src" / "model" / "pageRebuild.ts"
    css_path = repo / "frontend" / "src" / "styles" / "sheet.css"
    targets = [types_path, renderer_path, rebuild_path, css_path]
    backup = _backup_code_files(repo, targets)
    changed: list[str] = []

    try:
        text = types_path.read_text(encoding="utf-8")
        if "maxScale?: number;" not in text:
            text = _replace_once(
                text,
                "  noGrow?: boolean;\n",
                "  noGrow?: boolean;\n"
                "  /** Optional per-block scale ceiling. Used to keep sibling schedule pages at one visual scale. */\n"
                "  maxScale?: number;\n",
                "PageBlock noGrow field",
            )
            types_path.write_text(text, encoding="utf-8")
            changed.append(str(types_path.relative_to(repo)))

        text = renderer_path.read_text(encoding="utf-8")
        if "configuredMaxScale" not in text:
            text = _replace_once(
                text,
                "      const growCap = block.noGrow ? 1 : GROW_CAP;\n",
                "      const configuredMaxScale = Number(block.maxScale ?? GROW_CAP);\n"
                "      const growCap = Math.min(\n"
                "        block.noGrow ? 1 : GROW_CAP,\n"
                "        Number.isFinite(configuredMaxScale) ? configuredMaxScale : GROW_CAP,\n"
                "      );\n",
                "ExcelRangeRenderer grow cap",
            )
            text = _replace_once(
                text,
                "  }, [naturalW, nRows, nCols, scaleMode, grid, reservedTop, block.noGrow]);\n",
                "  }, [naturalW, nRows, nCols, scaleMode, grid, reservedTop, block.noGrow, block.maxScale]);\n",
                "ExcelRangeRenderer effect dependencies",
            )
            renderer_path.write_text(text, encoding="utf-8")
            changed.append(str(renderer_path.relative_to(repo)))

        text = rebuild_path.read_text(encoding="utf-8")
        old = "    if (existing?.type === 'excelRange' && existing.srcRows && !page.generatedContinuation) {\n"
        new = "    if (existing?.type === 'excelRange' && existing.srcRows) {\n"
        if new not in text:
            text = _replace_once(text, old, new, "page rebuild sliced-range guard")
            rebuild_path.write_text(text, encoding="utf-8")
            changed.append(str(rebuild_path.relative_to(repo)))

        text = css_path.read_text(encoding="utf-8")
        if SOURCE_PATCH_MARKER not in text:
            text += f"""

/* {SOURCE_PATCH_MARKER}
   Excel-exact sheets use a scaled wrapper with a known layout width. Auto
   margins center that width without changing the table's fit math. */
.np-xr {{
  display: flex;
  flex-direction: column;
  align-items: center;
}}
.np-xr-warning {{
  align-self: stretch;
}}
.np-xr-fit {{
  margin-left: auto;
  margin-right: auto;
}}
"""
            css_path.write_text(text, encoding="utf-8")
            changed.append(str(css_path.relative_to(repo)))
    except Exception:
        for path in targets:
            saved = backup / path.relative_to(repo)
            if saved.is_file():
                shutil.copy2(saved, path)
        raise

    return {"backup": str(backup), "changed": changed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=None)
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--workbook", default=None)
    parser.add_argument("--patch-source", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    repo = _find_repo(args.repo)
    if args.patch_source:
        result = patch_renderer_sources(repo)
        print(f"[OK] Renderer source patch backup: {result['backup']}")
        for changed in result["changed"]:
            print(f"[OK] Patched: {changed}")
        if not result["changed"]:
            print("[OK] Renderer source patch was already installed.")

    if args.apply:
        if not args.workbook:
            raise MigrationError("--workbook is required with --apply")
        apply_migration(repo, args.project, Path(args.workbook))

    if not args.patch_source and not args.apply:
        parser.error("Choose --patch-source and/or --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
