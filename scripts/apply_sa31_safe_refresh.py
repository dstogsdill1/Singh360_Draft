"""Safe SA31 workbook refresh entry point with manual-page preservation.

Use this wrapper for future SA31 workbook refreshes. It installs the exact-code
manual-page guard before the controller-safe matrix and resilient panel refresh.
Manual canvas/image pages cannot be matched to another sheet code or archived
merely because a copied template retained an old title/source-tab string.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_sa31_updated_workbook import patch_renderer_sources
import scripts.apply_sa31_complete_matrix_refresh_v2 as resilient_refresh
from scripts.recover_sa31_manual_pages import install_manual_page_guard
import scripts.sa31_refresh_core as refresh_core

DEFAULT_PROJECT_ID = refresh_core.DEFAULT_PROJECT_ID


def install_safe_refresh() -> None:
    install_manual_page_guard(refresh_core)
    resilient_refresh.install_recovery()


def apply_safe_refresh(repo: Path, project_id: str, workbook: Path):
    install_safe_refresh()
    patch_result = patch_renderer_sources(repo)
    for changed in patch_result.get("changed") or []:
        print(f"[OK] Patched permanent renderer source: {changed}")
    if not patch_result.get("changed"):
        print("[OK] Permanent renderer source patch was already installed.")
    return refresh_core.apply_migration(repo, project_id, workbook)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--workbook", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    workbook = Path(args.workbook).expanduser().resolve()
    apply_safe_refresh(repo, args.project, workbook)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
