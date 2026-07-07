# BUGLIST — FINAL TABLE/LAYOUT POLISH (4G)

Audit of the current SA31 export, taken against the rebuilt SA31 EMS
workbook fixture (`SA31_EMS_Workbook_Rebuilt_V1.xlsx` — the original
`SA31_EMS_Workbook_V2.xlsx` used in the 4F session is no longer present on
disk; the rebuilt V1 fixture has the identical tab/sheet-code layout and is
used for this audit and for the new 4G smoke tests). Do not code against
this document — it is a record of what is wrong, not a design doc.

## 1. Tables still clip/crop at the bottom

- **Project Workflow / Milestones** (`EMS 0.5 Workflow`, output page 6):
  the last data row is cut off at the bottom of the sheet body.
- **LCP Panel Schedule** (`EMS 1.4 LCP Panel Sch`, output page 15): the
  table renders flush/tight against the title block with no breathing
  room — a one-line change to source content would push it into the title
  block.
- Root cause candidates identified in code:
  - `core/page_composer.py` fit math (`_excel_best_scale` /
    `_excel_needs_split`) compares against `BODY_BUDGET` with **no bottom
    safety margin** — a page can be judged "fits" while landing exactly at
    the printable edge.
  - The client `ExcelRangeRenderer.tsx` fit-to-body autoscale
    (`--xr-scale`) has no minimum bottom gap either; it only guarantees the
    *scaled* table height does not exceed the raw body height, not that it
    leaves a margin above the title block.
  - `text`-family pages (Workflow, Scope, Guidelines, Instructions) are
    configured with `splitMode: "none"` / `allowContinuation: False`
    (TABLE STYLE 4F), so if content genuinely cannot fit even at min scale
    there is currently no page split fallback — only a logged warning.

## 2. Trailing blank worksheet columns/rows in normalized output

- `core/workbook_importer.py::_worksheet_payload` trims trailing **blank
  rows** by value only (`while grid and not any(grid[-1]): grid.pop()`) —
  it does not consider meaningful fills/borders, and it does **not** trim
  trailing **blank columns** at all. `ws.max_column` (openpyxl) reflects the
  furthest column that ever carried a value/format in the sheet, which is
  frequently wider than the real content (e.g. Abbreviations, Directory,
  Project Scope, Sheet Index, instruction pages all show extra empty
  columns past their real content in the exported table).
- Because this trim happens (or doesn't happen) once at import time and is
  shared by both the Source tab and the Normalized/export
  `excelRange` block, there is currently no way to trim only the
  Normalized/export copy while leaving Source untouched.

## 3. Wrong sheet numbers in the title block

- Root cause found: `core/workbook_importer.py` sets
  `sheetCode` / `displaySheetCode` from the index sheet's **`Order`**
  column (`idx["orderRaw"]`), not from the index sheet's **`Sheet Code`**
  column. The real SA31 index (`00_INDEX`) has a dedicated `Sheet Code`
  column (`EMS 0.0`, `EMS 0.2`, `EMS 0.3`, `EMS 1.4`, …) that is never read
  — `core/workbook_importer.py::_INDEX_ALIASES` has no `sheet_code` key at
  all, so `_header_map` never resolves that column.
- Compounding factor: `frontend/src/components/RenumberModal.tsx` /
  `frontend/src/model/emsNumbering.ts` expose a "Renumber Sheet Codes" tool
  whose **default selected scheme is `'ems'`** (family-classification) and
  also offers a **"Prefix + sequential"** scheme that stamps
  `EMS {outputOrder}.0` over whatever `sheetCode` is already set — this is
  almost certainly how the previously-exported deck ended up with
  `EMS 3.0` on the Abbreviations page (Abbreviations is output page 3;
  `3.0` matches the sequential scheme, not any real index code).
- `core/page_composer.py::continuation_code()` already produces the right
  continuation convention (`EMS 1.4` → `EMS 1.4a`) once the base code is
  correct — this only needs the import-time source of truth fixed.

## 4. Blank drawing/layout/pdf-vector pages missing the top dark header

- Pages affected: `EMS 1.0 Overall Layout`, `EMS 3.0 LCP1 Schematic`,
  `EMS 3.1 LCP2 Schematic`, `EMS 4.0 Interior Location`,
  `EMS 4.1 Exterior Location` (output pages ~11, 20, 21, 22, 23 in the
  previous export numbering).
- Root cause found: `frontend/src/components/renderers/NormalizedPage.tsx`
  computes `showBand = headerStyle === 'orange' && !isImageType &&
  !isCoverPage`. `isImageType` is true whenever `page.pageType ===
  'canvas'` — and `core/project_model.py::classify_page_type()` classifies
  any sheet whose tab/title contains `layout`, `location`, `diagram`,
  `schematic`, or `wiring` as `"canvas"`. So the *same* condition that
  correctly suppresses table styling on blank drawing pages **also**
  suppresses the top dark page-header band, which should show on every
  non-cover included page regardless of body content.

## 5. Source vs. Normalized/export parity

- Today the same worksheet `grid` (trailing-blank included) backs both the
  Source tab and the Normalized excel-exact block, so there is no
  structural distinction between "editable source, may show extra columns"
  and "trimmed, clean export" — this is really the same bug as (2), called
  out separately because Phase H asks for an explicit acceptance check.

## 6. RDM / IDF two-up layout (page 12)

- Currently acceptable (two-up, no rotation, floor-respecting font) per the
  TABLE STYLE 4F work. Flagged here only so it stays covered by the new
  no-clipping diagnostic and regression smoke test — no code change is
  expected unless the diagnostic finds an actual violation.

## 7. LCP continued page (page 16)

- Currently acceptable content-wise. Once (3) is fixed it must carry the
  correct continuation code (`EMS 1.4a`, not a sequential code derived from
  the wrong base).

---

Next: Phase A (sheet code mapping) → Phase B (blank-range trim) → Phase C
(hard no-clip guarantee) → Phase D (headers on layout pages) → Phase E/F
(two-up + LCP polish) → Phase G/H (style/parity verification) → Phase I/J
(diagnostics + smoke tests) → Phase K/L (visual QA + git hygiene).

## Resolution (this session)

- **(1) Clipping** — added `MIN_BOTTOM_GAP` (20px) on both the Python fit/split
  math (`SAFE_BODY_BUDGET = BODY_BUDGET - MIN_BOTTOM_GAP` in
  `core/page_composer.py`) and the client autoscale
  (`ExcelRangeRenderer.tsx`), so a page that "just fits" now always leaves a
  real margin instead of landing flush against the title block. Verified
  against the real SA31 fixture: every page's diagnostic `bottomGap` is now
  >= ~20px and `clipping=false`. A `"TABLE OVERFLOW — NOT EXPORTED CLIPPED"`
  warning is recorded when a no-continuation page genuinely can't reach the
  min readable scale even with the margin.
- **(2) Trailing blank ranges** — added `_trim_trailing_blank_ranges()` (and
  its JS mirror in `frontend/src/model/excelRange.ts`) which drops trailing
  blank rows/columns unless they carry a real fill/border or are inside an
  explicit print area; wired into `_excel_range_block` behind new
  `trimBlankRows` / `trimBlankColumns` page settings (default true). Also
  hardened the older value-only trailing-row pop in `_worksheet_payload` so
  it never discards a trailing row that still carries a meaningful
  fill/border.
- **(3) Sheet codes** — added a `sheet_code` index-column alias, a
  `_sheet_code_from_tab()` fallback, and precedence
  (index Sheet Code → tab-embedded code → Order → output order) in
  `core/workbook_importer.py`; changed `RenumberModal`'s default scheme from
  `'ems'` to `'keep'` so opening it can no longer silently overwrite correct
  imported codes. Verified against the real SA31 fixture: title blocks now
  read `EMS 0.0` / `EMS 0.2` / `EMS 0.3` / `EMS 1.4`, never `EMS 3.0`.
- **(4) Layout page headers** — removed the `!isImageType` exclusion from
  `showBand` in `NormalizedPage.tsx`; blank drawing/layout/schematic/location
  pages now render the dark header band with no table body underneath.
- **(5) Source vs. Normalized parity** — the Source tab still reads
  `ws["grid"]` directly (untouched); only the `excelRange` block built for
  Normalized/export runs the new trim step, and only when
  `trimBlankRows`/`trimBlankColumns` are true for that page.
- **(6)/(7) RDM/IDF + LCP continuation** — confirmed still correct; the RDM
  two-up now also has an unused hard-split fallback (`needsHardSplit`,
  `core/workbook_importer.py::_build_idf_network_block`) for the theoretical
  case where even a floor-font two-up can't fit, splitting into two balanced
  full-width pages instead of ever rendering below 6.5pt — not exercised by
  the real 48-port SA31 fixture, which stays a single two-up page.
