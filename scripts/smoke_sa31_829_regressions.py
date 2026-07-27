"""Sanitized SA31- and 829-shaped workbook regression checks.

The identifiers describe historical regression shapes only. Every workbook and
all engineering-like values are generated in a temporary directory.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.heb_idf_switch_matrix import HEB_HEADERS, TABLE_PROFILE
from core.workbook_importer import import_workbook
from tests.generated_fixtures import (
    write_829_regression_workbook,
    write_sa31_regression_workbook,
)


def _page_code(page: dict) -> str:
    return str(page.get("displaySheetCode") or page.get("sheetCode") or "")


def _check_sa31(path: Path, problems: list[str]) -> None:
    project = import_workbook(path, project_id="sanitized-sa31")
    pages = project.get("pages") or []
    expected = {
        "Cover": "EMS 0.0",
        "00_INDEX": "EMS 0.1",
        "Scope": "EMS 0.4",
        "IDF Network": "EMS 1.1",
        "LCP Panel Schedule": "EMS 1.4",
    }
    for tab, code in expected.items():
        page = next(
            (item for item in pages if item.get("sheetTab") == tab and not item.get("generatedContinuation")),
            None,
        )
        if page is None:
            problems.append(f"SA31 shape: missing base page for {tab}")
        elif _page_code(page) != code:
            problems.append(f"SA31 shape: {tab} code {_page_code(page)!r}, expected {code!r}")

    panel_pages = [page for page in pages if page.get("sheetTab") == "LCP Panel Schedule"]
    continuations = [page for page in panel_pages if page.get("generatedContinuation")]
    if not continuations:
        problems.append("SA31 shape: oversized panel schedule did not continue")
    elif _page_code(continuations[0]) != "EMS 1.4a":
        problems.append(
            f"SA31 shape: first panel continuation code {_page_code(continuations[0])!r}, "
            "expected 'EMS 1.4a'"
        )

    included = [page for page in pages if page.get("include", True)]
    totals = {page.get("pageTotal") for page in included}
    if totals != {len(included)}:
        problems.append(f"SA31 shape: page totals {totals!r} do not match {len(included)}")


def _check_829(path: Path, problems: list[str]) -> None:
    project = import_workbook(path, project_id="sanitized-829")
    pages = [
        page for page in project.get("pages") or []
        if page.get("sheetTab") == "EMS 13.2 IDF #2"
    ]
    base = next((page for page in pages if not page.get("generatedContinuation")), None)
    continuation = next((page for page in pages if page.get("generatedContinuation")), None)
    if base is None:
        problems.append("829 shape: base switch-matrix page is missing")
        return

    block = (base.get("blocks") or [{}])[0]
    if block.get("tableProfile") != TABLE_PROFILE:
        problems.append(f"829 shape: wrong table profile {block.get('tableProfile')!r}")
    if block.get("headers") != HEB_HEADERS:
        problems.append(f"829 shape: seven authoritative columns changed: {block.get('headers')!r}")
    if len(block.get("leftRows") or []) != 48 or len(block.get("rightRows") or []) != 48:
        problems.append("829 shape: switches 3 and 4 were not preserved as 48-row tables")
    if block.get("layoutWarnings"):
        problems.append(f"829 shape: unexpected source conflict warnings {block.get('layoutWarnings')!r}")

    if continuation is None:
        problems.append("829 shape: switch 5 continuation is missing")
    else:
        if _page_code(continuation) != "EMS 13.2b":
            problems.append(
                f"829 shape: reserved EMS 13.2a was not skipped; got {_page_code(continuation)!r}"
            )
        continuation_block = (continuation.get("blocks") or [{}])[0]
        if continuation_block.get("layoutMode") != "single":
            problems.append("829 shape: final switch was not rendered as a single table")
        if len(continuation_block.get("rows") or []) != 48:
            problems.append("829 shape: final switch does not contain 48 rows")


def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="singh360_sanitized_regressions_") as raw:
        root = Path(raw)
        _check_sa31(write_sa31_regression_workbook(root / "sa31-shape.xlsx"), problems)
        _check_829(write_829_regression_workbook(root / "829-shape.xlsx"), problems)

    if problems:
        print("SANITIZED SA31/829 REGRESSION PROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK: sanitized SA31 and 829 workbook regressions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
