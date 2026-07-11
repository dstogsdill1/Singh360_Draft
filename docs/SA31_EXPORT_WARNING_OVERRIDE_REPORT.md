# SA31 Export — Warning Override + Rendering Fix Report

Date: 2026-07-10

## Summary

Surgical fixes for SA31 PDF export: QA now **warns** instead of hard-blocking, narrative/IDF/I/O rendering improved, continuation pages accepted by QA, PDF page order fixed.

---

## Phase A — Warning override (not hard block)

**Before:** `POST /export/pdf` returned HTTP 409 and blocked export.

**After:**
- `GET /api/projects/<id>/export/warnings` — preview warnings
- `POST /export/pdf` — always generates PDF unless project missing, no included pages, or Playwright/write failure
- UI modal: **Export Warnings — Review Before PDF** with checkbox + **Export Anyway**

**Files:** `server.py`, `core/export_qa.py`, `frontend/src/api/client.ts`, `ExportWarningsModal.tsx`, `App.tsx`

---

## Phase B — EMS 2.0 Sheet Index in PDF

- Index tab defaults `include=True` when `00_INDEX` has no self-row (existing fix retained)
- **PrintView** now sorts included pages by `order` so PDF sequence matches index Order (Cover → Sheet Index → Guidelines)

**Files:** `PrintView.tsx`, `core/workbook_importer.py`

---

## Phase C — Guidelines / Field Instructions tiny strip fix

**Root cause:** Raw Excel geometry kept giant blank columns; narrow text column + inflated row height → TABLE OVERFLOW.

**Fix:**
- `_drop_fully_blank_columns` — removes interior/trailing blank columns
- `_drop_blank_spacer_rows` — removes blank spacer rows below header
- `_preferred_text_instruction_col_widths` — Topic/Step ~22%, Guideline/Instruction ~70%, clamped to ≥85% `BODY_W`
- `_compact_text_instruction_block` applied before geometry on `front_matter_table` / `instruction_table`
- TABLE OVERFLOW banner hidden in PDF export (`exporting` prop on renderers)

**Files:** `core/workbook_importer.py`, `ExcelRangeRenderer.tsx`, `NetworkTwoUpRenderer.tsx`, `NormalizedPage.tsx`

---

## Phase D — RDM/IDF Controller ID / IP / Network columns

**Fix:**
- `_idf_header_row` scans 12 rows, detects Controller ID / IP / Network headers
- `_normalize_header_cell` for merged/multi-line headers
- `_idf_columns` always keeps all `_IDF_REQUIRED_COLS` column shells (never drops Controller ID/IP/Network)
- Terminated By hidden by default

**Files:** `core/workbook_importer.py`

---

## Phase E — Technical token wrapping

Existing `nowrapColumns` + token min-width logic retained; renderers use `word-break: keep-all` for nowrap cells.

**Files:** `core/workbook_importer.py`, `ExcelRangeRenderer.tsx`

---

## Phase F — Continuation index sync

**Fix in `export_qa.py`:**
- `_is_generated_continuation()` — EMS 16.0a / 17.0a exempt from “missing from Sheet Index rows”
- `_index_codes_from_rendered_page()` — uses rendered Sheet Index grid (includes appended continuation rows)

**Files:** `core/export_qa.py`, `core/workbook_importer.py` (`_append_continuation_rows_to_index` existing)

---

## Phase G — Manual layout preservation

Existing `workbook_reimport.py` + `ReimportWorkbookModal` — preserves `canvasObjects` by default on re-upload.

**Storage:** merge plan via `/api/projects/<id>/reimport/preview` and `/reimport`

---

## Phase H — Page templates

Existing `.docs/library/page_templates/` + Save/Insert UI in Ribbon.

---

## Smoke results

| Script | Result |
|--------|--------|
| `npm run build` | OK |
| `smoke_routes.py` | OK (96 routes) |
| `smoke_export_warnings_override.py` | OK |
| `smoke_sa31_export_sheet_index_included.py` | OK |
| `smoke_instruction_pages_no_tiny_overflow.py` | OK (after width clamp) |
| `smoke_network_table_preserves_controller_columns.py` | OK |
| `smoke_io_tokens_no_character_wrap.py` | OK |
| `smoke_reupload_preserves_manual_layout_pages.py` | OK |
| `smoke_page_templates_save_insert.py` | OK |

---

## Manual verification checklist

- [ ] Export PDF → warnings modal → check box → Export Anyway → PDF downloads
- [ ] EMS 2.0 appears after Cover in real SA31 workbook
- [ ] EMS 3.0 / 17.0 full-width readable tables, no TABLE OVERFLOW banner in PDF
- [ ] EMS 13.0 shows Controller ID / IP / Network columns
- [ ] EMS 16.0 tokens (0-10VDC) readable
- [ ] EMS 16.0a / 17.0a no false index warnings
- [ ] Manual canvas on EMS 12.0 survives workbook re-upload

Restart `python server.py` after pulling these changes.
