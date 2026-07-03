# Singh360 SmartDraw — Product Specification

## Purpose

Build a production-grade local engineering drawing package editor that combines:

- workbook editing,
- WYSIWYG sheet editing,
- CAD-style title block templates,
- underlay imports,
- deterministic 17x11 PDF export.

## Core Principles

1. Deterministic first: no invented engineering values.
2. Unknown values remain blank and visually flagged.
3. Workbook provenance is preserved to sheet/cell level where available.
4. Editor rendering and exported PDF must use the same page renderer.
5. Every source workbook tab remains visible in the application.
6. `00_INDEX` controls output metadata/order, not source tab existence.
7. Blank `Include` in `00_INDEX` means included by default.
8. `TEMPLATE`/`UTILITY` are available in source browser, excluded from PDF by default.
9. No silent failures: visible error surfacing in UI and logs.
10. Technical drawing look/feel, not web-card styling.

## Target User Workflow

1. Create project.
2. Import workbook (`.xlsx`) and optional CSV/PDF/image/VSDX sources.
3. Review all source tabs in workbook view.
4. Manage output sheets from `00_INDEX` (include/order/title/code/type/template).
5. Edit per-sheet body in data-grid or canvas mode.
6. Adjust title block metadata and sheet properties.
7. Save (autosave + explicit Save Now).
8. Export deterministic 17x11 drawing package PDF.
9. Export project package (JSON + source references + outputs).

## Page Types

- `cover`
- `index`
- `data-grid`
- `canvas`
- `underlay`
- `hybrid`

## Import Flow

### Workbook (`.xlsx`)

- Read every worksheet and preserve worksheet names exactly.
- Parse `00_INDEX` by header names/aliases.
- Build output pages from `00_INDEX` rows where possible.
- Keep all workbook tabs as source worksheets regardless of include status.
- Preserve layout metadata if available: cell value/formula, merged cells, row heights, column widths, basic style hints.

### CSV

- Create worksheet from CSV table.
- Preserve source file reference and import timestamp.

### PDF/Image Underlay

- Register underlay asset.
- Create underlay-capable page or attach to selected page.
- Maintain transform settings (x/y/scale/rotation/opacity/lock).

### VSDX (milestone-2 import)

- Attach source file and parse page list where possible.
- Create underlay pages from page list.
- Full semantic conversion is future milestone.

## Save/Export Rules

- Project state persisted as JSON with schema version.
- No `NaN`, `NaT`, `<NA>`, `undefined` serialized into project JSON.
- Included pages only for PDF export and page `X of Y` numbering.
- PDF: 17in x 11in landscape, backgrounds on, zero margins.
- Export fails if fatal render/runtime errors are detected.

## Acceptance Criteria (Milestone 1)

1. App loads without console/runtime errors.
2. SA31 workbook upload creates project.
3. All workbook tabs visible in source/workbook views.
4. Output pages generated from `00_INDEX` metadata.
5. Included pages render on 17x11 sheet frame.
6. Title block appears on all sheets.
7. Page numbering updates after include/reorder/delete/add.
8. Data-grid pages are editable.
9. Canvas pages provide real object editing (not stub).
10. Autosave and Save Now visible and functional.
11. PDF export returns 17x11 package with included pages only.
12. Modular frontend/backend architecture in place.
13. Docs explain operating model and usage.
