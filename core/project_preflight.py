"""Workbook contract preflight for project creation and exports."""
from __future__ import annotations

import re
from typing import Any

from core.ems_workbook_contract import (
    CANONICAL_REPOSITORY,
    is_recipe_grid,
    sample_row_numbers,
)


def _issue(
    code: str,
    message: str,
    fix: str,
    *,
    page: dict[str, Any] | None = None,
    worksheet: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "confirmationRequired": True,
        "pageCode": (
            str((page or {}).get("displaySheetCode") or (page or {}).get("sheetCode") or "")
        ),
        "pageTitle": str((page or {}).get("sheetTitle") or worksheet),
        "worksheet": worksheet,
        "issue": message,
        "suggestedFix": fix,
    }


def _metadata_values(project: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for worksheet in project.get("worksheets") or []:
        key = str(worksheet.get("name") or "").replace(" ", "").replace("_", "").casefold()
        if "projectmeta" not in key:
            continue
        for row in worksheet.get("grid") or []:
            if not row:
                continue
            label = " ".join(str(row[0] or "").split()).strip().casefold()
            if not label:
                continue
            value = " ".join(str(row[1] or "").split()).strip() if len(row) > 1 else ""
            values[label] = value
    return values


def compute_project_preflight(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explicit-confirmation issues without changing Include values."""
    issues: list[dict[str, Any]] = []
    worksheets = {
        str(item.get("name") or ""): item
        for item in project.get("worksheets") or []
    }
    included = [
        page
        for page in project.get("pages") or []
        if page.get("include", True) and not page.get("generatedContinuation")
    ]

    for page in included:
        missing = [str(name) for name in page.get("missingCanonicalSources") or [] if name]
        for sheet_name in missing:
            issues.append(
                _issue(
                    "missing_canonical_source",
                    f"Required canonical source table {sheet_name!r} is missing.",
                    f"Create or restore {sheet_name}, then regenerate this page; or explicitly confirm the exception.",
                    page=page,
                    worksheet=sheet_name,
                )
            )

        required = [str(name) for name in page.get("requiredCanonicalSources") or [] if name]
        if required and int(page.get("canonicalDataRowCount") or 0) <= 0:
            issues.append(
                _issue(
                    "included_page_no_mapped_data",
                    "Included page has no mapped canonical data rows.",
                    "Populate its canonical table, set Include to NO in 00_INDEX, or explicitly confirm the empty page.",
                    page=page,
                )
            )

        recipe_only = bool(page.get("recipeOnly"))
        if not recipe_only:
            source_ids = {
                str(block.get("sourceWorksheetId") or "")
                for block in page.get("blocks") or []
                if block.get("sourceWorksheetId")
            }
            source_grids = [
                worksheet.get("grid") or []
                for worksheet in worksheets.values()
                if str(worksheet.get("id") or "") in source_ids
            ]
            recipe_only = (
                page.get("pageType") == "data-grid"
                and bool(source_grids)
                and all(is_recipe_grid(grid) for grid in source_grids)
            )
        if recipe_only:
            issues.append(
                _issue(
                    "included_page_recipe_only",
                    "Included page is linked only to a Field / Value / Notes recipe worksheet.",
                    "Map the page to its canonical editable table; recipe rows must never publish.",
                    page=page,
                )
            )

    metadata_values = _metadata_values(project)
    linked_id = metadata_values.get("linked project id", "").strip()
    project_id = str(project.get("id") or "").strip()
    if linked_id and project_id and linked_id != project_id:
        issues.append(
            _issue(
                "stale_linked_project_id",
                f"Workbook Linked Project ID {linked_id!r} does not match project {project_id!r}.",
                "Relink the package-owned workbook to this project before publishing.",
            )
        )

    repository = metadata_values.get("repo", "") or metadata_values.get("repository", "")
    if repository and repository.casefold() != CANONICAL_REPOSITORY.casefold():
        issues.append(
            _issue(
                "stale_repository_name",
                f"Workbook repository {repository!r} is stale; expected {CANONICAL_REPOSITORY!r}.",
                "Update the repository metadata or explicitly confirm the legacy reference.",
            )
        )

    revision = str((project.get("metadata") or {}).get("revision") or "").strip()
    if revision and re.search(r"\b(template|template version|orange header locked)\b", revision, re.IGNORECASE):
        issues.append(
            _issue(
                "template_text_in_project_revision",
                f"Project Revision contains template-version text: {revision!r}.",
                "Set Project Revision to the issued drawing revision; keep Template Version separate.",
            )
        )

    required_names = {
        name
        for page in included
        for name in page.get("requiredCanonicalSources") or []
        if name
    }
    for worksheet in worksheets.values():
        name = str(worksheet.get("name") or "")
        if name not in required_names:
            continue
        rows = sample_row_numbers(worksheet.get("grid") or [])
        if rows:
            shown = ", ".join(str(row) for row in rows[:8])
            suffix = "…" if len(rows) > 8 else ""
            issues.append(
                _issue(
                    "sample_engineering_rows",
                    f"Canonical table contains sample/template engineering rows at {name}!{shown}{suffix}.",
                    "Remove sample rows or replace them with verified project data before publishing.",
                    worksheet=name,
                )
            )

    return issues
