# SA31 Export Fixes + Page Templates — Final Report

Implementation date: 2026-07-10

## Summary

Nine phases (A–I) shipped to fix SA31 workbook export table rendering, preserve manual layout pages on re-upload, add reusable page templates, and gate PDF export behind a hard QA check. All new and regression smoke tests pass; frontend production build succeeds.

---

## Phase A — EMS 2.0 Sheet Index was skipped

### Root cause

The `00_INDEX` worksheet rarely lists itself in the index grid. The importer used `include = not has_index` when no self-referencing row was found, so the Sheet Index tab was treated as excluded and never emitted as an output page.

### Fix

In `core/workbook_importer.py`, the index tab is now special-cased:

- Defaults `include=True` when there is no self-row in `00_INDEX`
- Emits an `importWarnings` entry explaining the assumption
- Falls back to title **"Sheet Index / TOC"** and sheet code **EMS {order}.0** (e.g. EMS 2.0 when Cover is EMS 1.0)

### Before / after

| | Before | After |
|---|--------|-------|
| `00_INDEX` without self-row | Page skipped entirely | EMS 2.0 Sheet Index / TOC exported, `include=True`, ordered after Cover |
| Export PDF tabs | Missing Sheet Index | `['Cover', '00_INDEX', 'Guidelines', …]` |
| QA gate | N/A | Index page excluded from reverse “missing from index rows” check |

**Smoke:** `scripts/smoke_sa31_export_sheet_index_included.py` — OK

---

## Phase B — Guidelines / Field Instructions tiny strips + TABLE OVERFLOW

### Root cause

Text-family pages inherited index-style split settings (`splitMode: none`), narrow `max_w=360` column caps, and `noGrow=True` on instruction tables. Tall narrative content was squeezed into a thin strip with overflow warnings.

### Fix

- Text-family pages use `splitMode: auto_rows` with continuation support
- `_preferred_col_widths` uses full `BODY_W` for text profiles
- Removed `noGrow=True` for instruction tables
- Narrative font floor (7.5pt-equivalent) applied to `front_matter_table` and `instruction_table`

### Before / after (EMS 3.0 Guidelines, EMS 17.0 Field Instructions)

| Page | Before (symptom) | After (smoke fixture) |
|------|------------------|------------------------|
| EMS 3.0 Guidelines | Single narrow strip, TABLE OVERFLOW | Up to 4 continuation pages, width ≥85% BODY_W, scale 0.856, no TABLE OVERFLOW |
| EMS 17.0 Field Instructions | Tiny overflow strip | 1 page, 1504×556, scale 1.0, no TABLE OVERFLOW |

**Smoke:** `scripts/smoke_instruction_pages_no_tiny_overflow.py` — OK

---

## Phase C — RDM/IDF network table columns

### Root cause

`_idf_columns` merged Controller ID / IP Address into Notes or combined columns when the two-up layout exceeded width budget.

### Fix

- Rewrote `_idf_columns` for 10 separate columns: Port, Label, Device / Drop, Controller ID, IP Address, Network, From, To, Cable, Notes
- `showTerminatedBy` gated (default hidden); optional via Properties panel checkbox on `network_48_port` pages
- Two-up column width priority retuned so Controller ID / IP / Network stay visible

### Before / after (EMS 13.0 RDM / IDF Network Table)

| | Before | After |
|---|--------|-------|
| Headers | Controller/IP folded into Notes | All 10 headers as separate columns |
| Row 3–4 | LCP1/601, LCP2/602 buried | Visible in Controller ID column |
| Terminated By | Always shown or merged | Hidden by default (`showTerminatedBy: false`) |
| Layout | Clipping risk | Two-up 1–24 / 25–48, no clipping |

**Smoke:** `scripts/smoke_network_table_preserves_controller_columns.py` — OK

---

## Phase D — LCP/I/O token wrapping (0-10VDC, etc.)

### Root cause

Dense I/O tables used 52px minimum columns with no nowrap; tokens like `0-10VDC` wrapped character-by-character.

### Fix

- `_TECH_TOKEN_RE` detector for technical tokens
- `nowrapColumns` on `ioSchedule`, `panelDetail`, `rackLayout` profiles
- Column min-width derived from longest token in column

### Before / after (EMS 16.0 LCP Panel Schedule)

| | Before | After |
|---|--------|-------|
| `0-10VDC` | Per-character wrap | Single-line nowrap |
| Column config | No nowrap | `nowrapColumns=[0, 2, 3]`, widths ≥300 for token columns |

**Smoke:** `scripts/smoke_io_tokens_no_character_wrap.py` — OK

---

## Phase E — Safe workbook re-upload

### Behavior

`core/workbook_reimport.py` provides `plan_reimport()` and `apply_reimport()`:

- Table/data pages refresh from the new workbook
- Manual layout pages (`canvasObjects`, blank canvas) are preserved byte-identical
- Removed sheets are archived, not deleted

### API

- `POST /api/projects/<id>/reimport/preview` — diff plan
- `POST /api/projects/<id>/reimport` — apply merge

### UI

`ReimportWorkbookModal.tsx` wired into the Import Workbook flow when a project is already open.

**Smoke:** `scripts/smoke_reupload_preserves_manual_layout_pages.py` — OK (preserved `EMS 12.0`, updated `EMS 2.0` + `EMS 13.0`)

---

## Phase F — Page templates

### Storage location

```
.docs/library/page_templates/
  manifest.json          # template index (id, name, tags, thumbnail path)
  <template-id>.json     # blocks + canvasObjects payload
  thumbnails/            # optional PNG previews
```

Managed by `core/page_template_store.py`.

### API routes (`server.py`)

- `GET/POST /api/page-templates`
- `GET/PUT/DELETE /api/page-templates/<id>`
- `POST /api/projects/<id>/pages/insert-template`

### UI

- **Ribbon → Templates:** Save Page Template, Page Template Library
- `SavePageTemplateModal.tsx`, `PageTemplateLibraryModal.tsx`
- Insert-as-new-page from library

**Smoke:** `scripts/smoke_page_templates_save_insert.py` — OK (save → list → get → insert → rename → delete round-trip)

---

## Phase G — Replace current page vs add-as-new

Verified existing `ImportWorksheetModal.tsx`:

- When an output page is active, default mode is **replace** (not add duplicate tab)
- Replace requires exactly one worksheet selected
- `scripts/smoke_import_replace_current_page.py` — OK (pre-existing regression)

---

## Phase H — PDF export QA gate (hard block)

`core/export_qa.py` — `compute_export_warnings()` checks:

- `layoutWarnings` containing `"TABLE OVERFLOW"`
- `clipping: True` from render diagnostics
- Effective font below contextual floor (7.5pt text/instruction, 6.5pt dense tables)
- Zero visible content on non-placeholder pages
- Index/output sync (included index rows ↔ exported pages; index pages exempt from reverse check)
- Title-block `displaySheetCode` vs index Sheet Code mismatch

**Wiring:** `POST /api/projects/<id>/export/pdf` returns HTTP **409** with warning list when issues exist; no PDF generated.

**UI:** `ExportWarningsModal.tsx` surfaces warnings with page jump links.

---

## Phase I — Smoke test results

### New smokes (all OK)

| Script | Result |
|--------|--------|
| `smoke_sa31_export_sheet_index_included.py` | OK |
| `smoke_instruction_pages_no_tiny_overflow.py` | OK |
| `smoke_network_table_preserves_controller_columns.py` | OK |
| `smoke_io_tokens_no_character_wrap.py` | OK |
| `smoke_reupload_preserves_manual_layout_pages.py` | OK |
| `smoke_page_templates_save_insert.py` | OK |

### Regression smokes (all OK)

| Script | Result |
|--------|--------|
| `smoke_routes.py` | OK |
| `smoke_included_only_index.py` | OK |
| `smoke_index_include_rules.py` | OK |
| `smoke_sa31_index_output_sync.py` | OK |
| `smoke_index_continuations.py` | OK |
| `smoke_instruction_pages.py` | OK |
| `smoke_no_table_clipping.py` | OK |
| `smoke_no_export_clipping.py` | OK |
| `smoke_idf_network_two_up.py` | OK |
| `smoke_sa31_idf_scaleup.py` | OK |
| `smoke_sa31_scope_table_fit.py` | OK |
| `smoke_import_replace_current_page.py` | OK (Phase G) |

### Build / compile

```
npm run build          → OK
python -m compileall   → OK
```

---

## Honest flags

1. **No real SA31 customer workbook in repo** — fixes proven on synthetic fixtures that reproduce reported symptoms. Re-run export against the actual SA31 workbook locally for visual QA.
2. **QA gate is a hard block** — legitimate edge cases cannot bypass without a follow-up override flag (not built in this pass).
3. **`showTerminatedBy` toggle** sets the page flag; IDF block may require reimport/rebuild to fully reflect live (no dedicated `rebuild_idf_network_page` endpoint).
4. **Template thumbnails** — storage supports PNG previews; Save modal does not yet capture canvas `toDataURL()` automatically (optional enhancement).

---

## Files touched (high level)

| Area | Key files |
|------|-----------|
| Import/render | `core/workbook_importer.py`, `core/project_model.py` |
| Reimport | `core/workbook_reimport.py` |
| Export QA | `core/export_qa.py` |
| Templates | `core/page_template_store.py` |
| Server | `server.py` |
| Frontend | `App.tsx`, `Ribbon.tsx`, `PropertiesPanel.tsx`, template/export modals, `api/client.ts` |
| Tests | 6 new `scripts/smoke_*.py` |
