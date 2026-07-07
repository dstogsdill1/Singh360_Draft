# BUGLIST — Table Output 4C (SA31_EMS_Workbook_V2 regression)

Audit of failed output from latest SA31_EMS_Workbook_V2 PDF import/export cycle.
Reference: user-reported failures vs SA38/Kyle/EMC visual standard.

## Root causes (code-level)

| Failure | Root cause |
|---------|------------|
| TOC pages 2 / 2.1 / 2.2 | Index `pageType=index` used `normalize_page` → generic table block → `compose_pages` split it. Frontend rendered `GeneratedIndexRenderer` on **every** index/continuation page (full duplicate TOC). Index was excluded from `excel_exact`. |
| Page 5.1 (Project Scope) | `page_family=text` → normalized blocks → dumb `_paginate_blocks` split despite tiny row count. Not using `excel_exact` + `splitMode=none`. |
| Page 6.1 (Workflow/Milestones) | Same as Scope — text family normalized + paginated. |
| Disabled sheets in output | `_included()` defaulted blank index cells to **True**; pages created for all worksheets with `include=false` still exported if toggled wrong; optional tabs auto-included. |
| Page 14 Lighting Output clipped | Generic table renderer + aggressive split/scale; not `excel_exact` fit-to-body. |
| Page 15 LCP (closest) | `excel_exact` path works; needs tighter fit-to-body scale (minScale tuning). |
| Responsibility Matrix wrong | Should be `excel_exact`; if re-imported with old code, generic matrix renderer used. |
| Inconsistent headers/numbering | Mixed normalized vs excel_exact pages; continuation titles duplicated. |

---

## Failed pages (observed)

### Pages 2 / 2.1 / 2.2 — duplicate Sheet Index / TOC

- **Expected:** One page showing the Excel INDEX range (or one live TOC).
- **Actual:** Three output pages (2, 2.1, 2.2), each showing a full generated TOC.
- **Fix:** Index → `excel_exact`, `splitMode=none`, no `compose_pages` split; render Excel range not GeneratedIndexRenderer for excel_exact index.

### Page 5.1 — unnecessary Project Scope continuation

- **Expected:** One page (few rows).
- **Actual:** Continuation 5.1 for a single Closeout row.
- **Fix:** Text/scope pages → `excel_exact` when tabular, `splitMode=none`, orphan rule min 4 rows.

### Page 6.1 — unnecessary Workflow / Milestones continuation

- **Expected:** One page (two rows).
- **Actual:** Continuation 6.1.
- **Fix:** Same as Scope.

### Disabled / not-included sheets rendered

- **Expected:** Source tabs only; no output page, no PDF, no TOC entry.
- **Actual:** Optional full-EMS tabs appeared in output.
- **Fix:** Strict `_included()`: blank/unknown index cell = NO; skip page creation when not included.

### Page 7 — Responsibility Matrix wrong style

- **Expected:** SA38/Kyle matrix (gold/gray headers, X marks, trade columns, grid).
- **Actual:** Generic dark-header app table.
- **Fix:** `excel_exact` matrix block; no `TablePageRenderer`.

### Page 14 — Lighting Output Matrix clipped

- **Expected:** Full matrix visible in body, scaled to fit.
- **Actual:** Content cut off / runs under title block.
- **Fix:** `excel_exact` + fit-to-body scaling; split only if truly exceeds minScale.

### Page 15 — LCP Panel Schedule (closest to correct)

- **Expected:** Gold controller bands, gray column headers, exact Excel layout.
- **Actual:** Closest match; minor fit issues.
- **Fix:** Tune minScale for panelDetail family; verify fit-to-body.

### Title block / sheet numbering inconsistencies

- **Expected:** Index sheet codes on all pages; single “— CONTINUED” suffix.
- **Actual:** Mixed numbering; “CONTINUED — CONTINUED” on some continuations.
- **Fix:** Continuation title guard; preserve index `orderRaw` sheet codes.

---

## Acceptance checklist (4C)

- [x] TOC = 1 page (excel_exact + splitMode none; no GeneratedIndexRenderer duplicate)
- [x] Project Scope = 1 page (text family excel_exact + no paginate)
- [x] Workflow/Milestones = 1 page (same)
- [x] Optional/disabled sheets excluded from output + PDF + TOC (strict `_included`, skip page creation)
- [x] Responsibility Matrix = excel_exact block path (not generic matrix renderer on re-import)
- [x] Lighting Output Matrix fits (fit_body + scale before split; smoke_table_fit)
- [x] LCP keeps gold/gray headers (excel_exact styles preserved)
- [x] No blank/orphan continuations (<4 data rows merged)
- [x] No duplicate full-table continuations (index uses excel range, not paginated generic table)
- [ ] Full SA31_EMS_Workbook_V2 regression PDF (requires re-upload + manual QA)
