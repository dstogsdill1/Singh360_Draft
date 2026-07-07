# BUGLIST — Milestone 4B: Workbook + Normalized Output Standardization

Date: 2026-07-07

Phase 0 audit. No code changes are described here as done — this file records
the current, verified behavior of the codebase and the concrete gaps versus the
4B requirements. Grounded in the actual source files listed.

## How uploaded workbook sheets become source tabs

- Entry: `server.py` `/api/projects/new` → `core/workbook_importer.import_workbook()`.
- `_worksheet_payload(ws)` builds, per sheet:
  - `name` (the ORIGINAL worksheet tab name — preserved verbatim),
  - `grid` (2D list of trimmed cell strings via `_norm`),
  - `formulas` (dict `A1 -> "=..."` — preserved),
  - `styles` (dict `A1 -> {bold, italic, underline, fontSize, hAlign, vAlign, fill, border}`;
    `fill` is a solid `#RRGGBB` via `_cell_fill_hex`),
  - `mergedCells`, `rowHeights`, `columnWidths`, `embeddedImages`.
- Each payload becomes a `project.worksheets[]` entry with the same fields and a
  stable id `ws_<n>`. Tab names are NOT renamed. SA31 `00_INDEX` stays `00_INDEX`.

## How normalized pages are generated

- For each worksheet, `import_workbook` calls `classify_page_type()` and
  `core/page_normalizer.normalize_page(ws, ws_id, page_type, title)`.
- `normalize_page` branches by page type:
  - `index` → one `table` block (styleRole `index`).
  - `canvas`/`hybrid`/`underlay` → a `canvas` block (+ image blocks).
  - `cover` → a `cover` block.
  - sparse (≤2 cols) → text blocks.
  - otherwise → `matrix` if `_looks_like_matrix` else `table`, via `_build_table_block`.
- `_build_table_block` returns `{ type, headers: string[], rows: string[][], ... }`.
- `core/page_composer.compose_pages()` then splits overflowing pages into
  continuation pages.

## Where table style is defined

- Frontend only, ad hoc, in `frontend/src/styles/sheet.css`:
  - `.np-table th` / `.np-matrix th` = dark bar (`#24282e`) column headers,
  - `.np-table td` = 1px gray borders, alternating even-row fill `#f4f6f8`,
  - `.np-index-table` for the generated TOC.
- There is NO single canonical style module shared by source preview and
  normalized output. There is NO gold/orange controller-section-header style,
  and NO dedicated gray column-header vs. dark titlebar distinction.

## Where source cell fill/highlight is lost (ROOT CAUSE)

- Fills ARE extracted at import (`styles[...]["fill"]` = `#RRGGBB`) and ARE
  passed into `normalize_page`.
- BUT `_build_table_block` only uses `styles` to FIND the header row
  (`_row_is_bold` / `_row_has_fill`). It then emits `headers`/`rows` as PLAIN
  STRINGS and DROPS every per-cell fill/font/align.
- The frontend `PageBlock` type (`frontend/src/model/types.ts`) has only
  `headers?: string[]` and `rows?: string[][]` — there is no per-cell fill map.
- Net effect: normalized output tables render with zero source highlights, and
  cannot match the gold/gray standardized look. This is the primary 4B mismatch.
- Source view (`RawGridRenderer`) DOES apply a generic `gc-fill` class from
  `worksheet.styles`, but only as a flat highlight flag, not the real color, and
  it is not carried to the normalized block.

## How row/column edits are stored

- Normalized: `TablePageRenderer` edits mutate `block.headers` / `block.rows`
  via `onChange` → `App.onBlockChange` → `project.pages[].blocks[]`.
- Source: `RawGridRenderer` edits call `onGridChange` → `App` updates
  `worksheets[].grid` AND (recent fix) re-syncs linked page table blocks from the
  grid via `syncBlocksFromGrid`.
- Neither path stores per-cell fill edits — only text.

## How long tables are split or scrolled

- `compose_pages` / `_paginate_blocks` / `_split_table_block` split large
  table/matrix blocks by an estimated body height budget (`BODY_BUDGET`), now
  content-aware for wrapped rows (3G). Header row is repeated because each chunk
  deep-copies the block (headers stay); rows are chunked.
- Continuation pages get `— CONTINUED` in the sheet title and a continuation
  sheet code.
- Final output CSS enforces `overflow: hidden` (no internal scrollbars) on
  `.np`, `.np-base-layer`, `.np-index`. Frontend also has a runtime auto-fit
  scale fallback for oversized tables.
- Gap: splitting has no concept of a MERGED controller/section header that must
  repeat on every continuation, and no fill carry-through (because fills are not
  in the model).

## How page-template selection maps to renderers

- Backend `pageType` ∈ `{data-grid, canvas, underlay, hybrid, cover, index}`.
- Friendly template names in `frontend/src/model/pageTemplates.ts`.
- `NormalizedPage` routing:
  - `index` → `GeneratedIndexRenderer`,
  - `canvas`/canvas-block → image/canvas base,
  - blocks → `TablePageRenderer` (table), `MatrixPageRenderer` (matrix),
    text renderers, cover, image.
- Gap: there is ONE generic table renderer. There are no type-specific
  renderers for Controller I/O, IDF 48-port, Rack I/O, DLE/WI-TDB, Lighting-TDB,
  Pharmacy Panel, Power Meter/BACnet, Data Manager. All render as a generic
  table.

## How source/normalized editing syncs

- Source → Normalized: `syncBlocksFromGrid` maps the edited grid's first row to
  headers and the rest to rows for the linked page's table/matrix block.
- Normalized → Source: NOT synced back to the worksheet grid today.
- Neither direction carries per-cell fill.

## Current gaps vs. the provided workbooks

- SA31 `00_INDEX`: read by `_find_index_sheet` (matches any sheet containing
  "INDEX") and `_parse_index`. Works. `Include` YES/NO honored by `_included`.
- SA38 `00_APP_INDEX`: also matched by `_find_index_sheet` (contains "INDEX"),
  but there is no dedicated APP-index mapping schema (Sheet Code/Page Title/type
  columns) — it is parsed with the same generic index aliases, so richer SA38
  mapping columns are not fully used.
- Full EMS master template optional tabs: `Include` YES/NO is honored, but there
  is no explicit "optional tab remains available but not forced" concept beyond
  include/exclude.
- Source highlights: LOST in normalized output (root cause above).
- Controller/IO gold-gray styling: not implemented.
- Type-specific renderers: not implemented.

## What 4B must fix (scope map)

- Phase A: one canonical style map (colors + roles) shared by source preview and
  normalized output. Required colors: controller gold `#FFC000`, dark header
  `#20252B`, column gray `#D9D9D9`, alt row light gray, verify yellow, stop
  red/pink, done green.
- Phase B: deterministic page/table-type detection (index, BOM, matrix, IDF, I/O
  variants, panel, metering, data manager, BACnet, narrative, image).
- Phase C: editable table model that PRESERVES per-cell fill/formula/merge and
  persists/reloads/exports it. Minimum viable: add a per-cell fill map to the
  table block, populate it at import from source fills, render it, edit it,
  persist it.
- Phase D: multi-cell selection + highlight apply/clear + undo/redo.
- Phase E: continuation splitting that repeats merged controller/column headers
  and carries fills.
- Phase F: SA31 / SA38 (00_APP_INDEX) / master-template conventions.
- Phase G: type-specific renderers.
- Phase H: export parity (no rasterization of editable tables; highlights + no
  clipping).

## Incremental delivery note

Because the SA31/SA38/master reference workbooks and PDFs are customer files and
are intentionally NOT in the repo (code-only policy), Phase F/G/J acceptance must
be validated locally by the user against those files. Automated smokes in this
repo use synthetic fixtures so CI stays deterministic and no customer data is
committed.
