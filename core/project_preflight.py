"""Workbook contract preflight for project creation and exports."""
from __future__ import annotations

import re
from typing import Any

from core.ems_workbook_contract import (
    CANONICAL_REPOSITORY,
    is_recipe_grid,
    sample_row_numbers,
)
from core.workbook_geometry import DEFAULT_COLUMN_WIDTH_PX, DEFAULT_ROW_HEIGHT_PX


_A1_RANGE = re.compile(r"^\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?$", re.I)


def _column_index(value: str) -> int:
    result = 0
    for char in value.upper():
        result = result * 26 + ord(char) - 64
    return result - 1


def _range_bounds(value: Any) -> tuple[int, int, int, int] | None:
    match = _A1_RANGE.fullmatch(str(value or "").strip())
    if not match:
        return None
    start_col = _column_index(match.group(1))
    start_row = int(match.group(2)) - 1
    end_col = _column_index(match.group(3) or match.group(1))
    end_row = int(match.group(4) or match.group(2)) - 1
    return min(start_row, end_row), max(start_row, end_row), min(start_col, end_col), max(start_col, end_col)


def _overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    return left[0] <= right[1] and left[1] >= right[0] and left[2] <= right[3] and left[3] >= right[2]


def _contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    return outer[0] <= inner[0] and outer[1] >= inner[1] and outer[2] <= inner[2] and outer[3] >= inner[3]


def _spreadsheet_region_issues(project: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    worksheets = {str(item.get("id") or ""): item for item in project.get("worksheets") or []}
    seen: list[tuple[str, str, tuple[int, int, int, int], dict[str, Any]]] = []
    for page in project.get("pages") or []:
        regions = page.get("spreadsheetRegions") if isinstance(page.get("spreadsheetRegions"), list) else []
        page_has_content = False
        if page.get("renderMode") == "spreadsheet_layout" and not regions and page.get("include", True):
            issues.append(_issue("spreadsheet_blank_page", "Spreadsheet Page Layout has no selected ranges.", "Add an explicit range or exclude the page.", page=page))
        for region in regions:
            bounds = _range_bounds(region.get("range"))
            worksheet_id = str(region.get("sourceSheetId") or "")
            worksheet = worksheets.get(worksheet_id)
            if not bounds or not worksheet:
                issues.append(_issue("spreadsheet_source_missing", "Spreadsheet region has an invalid range or missing source sheet.", "Select the source range again in Data Workspace Page Layout.", page=page))
                continue
            for prior_page, prior_sheet, prior_bounds, prior_region in seen:
                if prior_sheet == worksheet_id and _overlap(bounds, prior_bounds):
                    issues.append(_issue("spreadsheet_duplicate_range", f"{region.get('range')} overlaps {prior_region.get('range')} on page {prior_page}; source rows would repeat.", "Select non-overlapping first and continuation ranges.", page=page, worksheet=str(worksheet.get("name") or "")))
            seen.append((str(page.get("id") or ""), worksheet_id, bounds, region))

            for merge in worksheet.get("mergedCells") or []:
                merge_bounds = (
                    int(merge.get("startRow") or 0), int(merge.get("endRow") or 0),
                    int(merge.get("startCol") or 0), int(merge.get("endCol") or 0),
                )
                if _overlap(bounds, merge_bounds) and not _contains(bounds, merge_bounds):
                    issues.append(_issue("spreadsheet_partial_merge", f"{region.get('range')} cuts through a merged cell.", "Move the range boundary outside the complete merge.", page=page, worksheet=str(worksheet.get("name") or "")))
                if any(merge_bounds[0] < int(row) <= merge_bounds[1] for row in region.get("explicitBreaks") or []):
                    issues.append(_issue("spreadsheet_merge_crosses_break", "An explicit page break crosses a merged range.", "Move the break before or after the merged rows.", page=page, worksheet=str(worksheet.get("name") or "")))

            hidden_rows = {int(item) for item in worksheet.get("hiddenRows") or []}
            hidden_columns = {int(item) for item in worksheet.get("hiddenColumns") or []}
            rows = [row for row in range(bounds[0], bounds[1] + 1) if row not in hidden_rows]
            columns = [column for column in range(bounds[2], bounds[3] + 1) if column not in hidden_columns]
            natural_width = sum(float((worksheet.get("colWidthsPx") or [])[column] if column < len(worksheet.get("colWidthsPx") or []) else DEFAULT_COLUMN_WIDTH_PX) for column in columns)
            natural_height = sum(float((worksheet.get("rowHeightsPx") or [])[row] if row < len(worksheet.get("rowHeightsPx") or []) else DEFAULT_ROW_HEIGHT_PX) for row in rows)
            width = float(region.get("width") or 0); height = float(region.get("height") or 0)
            fit_mode = str(region.get("fitMode") or "fit_width")
            scale = float(region.get("scale") or 1) if fit_mode == "exact_scale" else (width / max(1, natural_width))
            if fit_mode == "fit_box": scale = min(scale, height / max(1, natural_height))
            if natural_width * scale > width + .5 or natural_height * scale > height + .5:
                issues.append(_issue("spreadsheet_overflow", f"{region.get('range')} overflows its saved page box.", "Resize the box, use Fit Box, or select an explicit continuation range.", page=page, worksheet=str(worksheet.get("name") or "")))
            source_styles = worksheet.get("styles") or {}
            font_sizes = [float(style.get("fontSize") or 11) * scale for coordinate, style in source_styles.items() if isinstance(style, dict) and (_range_bounds(coordinate) and _contains(bounds, _range_bounds(coordinate)))]
            if font_sizes and min(font_sizes) < 6.5:
                issues.append(_issue("spreadsheet_font_too_small", f"{region.get('range')} renders below 6.5 pt.", "Increase the region size or select a smaller explicit range.", page=page, worksheet=str(worksheet.get("name") or "")))
            grid = worksheet.get("grid") or []
            clipped = False
            for row in rows:
                for column in columns:
                    text = str(grid[row][column] if row < len(grid) and column < len(grid[row]) else "")
                    if text.strip():
                        page_has_content = True
                    style_key = ""
                    current = column + 1
                    while current:
                        current, remainder = divmod(current - 1, 26)
                        style_key = chr(65 + remainder) + style_key
                    style = source_styles.get(f"{style_key}{row + 1}") or {}
                    column_width = float((worksheet.get("colWidthsPx") or [])[column] if column < len(worksheet.get("colWidthsPx") or []) else DEFAULT_COLUMN_WIDTH_PX)
                    if text and not style.get("wrap") and len(text) * float(style.get("fontSize") or 11) * 4 / 3 * .52 > column_width:
                        clipped = True
            if clipped:
                issues.append(_issue("spreadsheet_clipped_text", f"{region.get('range')} contains non-wrapped text wider than its source cell.", "Enable source wrapping, widen the source column, or choose a larger explicit region box.", page=page, worksheet=str(worksheet.get("name") or "")))
        if regions and not page_has_content and page.get("include", True):
            issues.append(_issue("spreadsheet_blank_page", "Spreadsheet Page Layout contains only blank selected cells.", "Select a nonblank range or exclude the page.", page=page))
    return issues


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
    issues: list[dict[str, Any]] = _spreadsheet_region_issues(project)
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
    source_revision = (
        metadata_values.get("project revision", "")
        or metadata_values.get("revision", "")
        or metadata_values.get("rev", "")
    ).strip()
    invalid_revision = source_revision or revision
    if invalid_revision and re.search(
        r"\b(template|template version|orange header locked)\b",
        invalid_revision,
        re.IGNORECASE,
    ):
        issues.append(
            _issue(
                "template_text_in_project_revision",
                f"Project Revision contains template-version text: {invalid_revision!r}.",
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
