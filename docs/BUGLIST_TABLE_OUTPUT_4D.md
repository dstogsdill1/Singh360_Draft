# BUGLIST — Table Output 4D (Singh360 Standard Table Renderer)

Phase 0 audit of the latest SA31 export. Grounded in the real render pipeline
(`core/workbook_importer.py`, `core/page_composer.py`,
`frontend/src/components/renderers/ExcelRangeRenderer.tsx`, `styles/sheet.css`).

Direction change from 4C: stop preserving every Excel visual style verbatim.
Apply **one** Singh360 drawing-table standard — orange (`#FFC000`) title band with
black centered title, gray (`#D9D9D9`) column headers, Excel-style grid borders,
alternating light-gray body rows, auto-fit to the full printable body width, and
balanced continuation with no orphan tails.

---

## Observed failures (latest SA31 export)

| Page | Symptom | Root cause (code-level) |
|------|---------|-------------------------|
| 15 Lighting Output Matrix | Clipped / cut off; second relay/contact table runs under the title block | `ExcelRangeRenderer` fit is `min(1, sw, sh)` on `BODY_H` only. The source tab stacks two tables taller than one body; `_excel_needs_split` uses `minScale=0.48` but the block is one range so it scales past readability and clips instead of splitting into two intentional sections. |
| 16 LCP Panel Schedule | Closest to correct (gold controller bands, gray-ish headers) but the top band is dark, not orange | Source dark title fill is preserved verbatim by excel_exact. No profile recolor. |
| 17 LCP `15.1` | Useless continuation holding only RO9–RO12 (4 rows) | `_excel_data_chunks` greedy-packs page 1 then drops a tiny tail. `MIN_ORPHAN_DATA_ROWS=4` treats a 4-row tail as "legal", so the orphan survives. No section-aware split and no even balancing. |
| 12–13 RDM / IDF Network Table | Bad short-tail split: page 12 holds most rows, 12.1 holds a short tail | Same greedy `_excel_data_chunks`: fills the first page to the height budget, leaving an unbalanced remainder (e.g. 37/11) instead of an even 24/24. |
| 3–10 Front matter (Abbreviations, Directory, Scope, Workflow, Responsibility, Equipment, BOM, Revision) | Small Excel tables float top-left under a dark/black band; huge empty right side | (a) Dark source title fill preserved (black band). (b) Fit caps at `scale ≤ 1`, so a narrow source range never grows to the printable width → tiny floating table. |
| Any optional `include=NO` sheet | Occasionally still visible | Guarded by `_included` (blank = NO) + page-creation skip; keep enforced, add to smoke. |
| Every table page | No consistent Singh360 identity | There is no render profile. Each page inherits whatever fills the source tab carried; there is no orange title band, no gray-header normalization, no full-width auto-fit. |

---

## Root-cause summary

1. **No render profile.** Nothing applies one consistent Singh360 standard; the
   excel_exact path is a faithful *photocopy* of the source (including black
   bands, tiny widths).
2. **Auto-fit only shrinks.** `ExcelRangeRenderer` clamps `scale ≤ 1`, so small
   ranges never fill the body width (the "floating table" look). It also fits to
   the whole `BODY_H` without reserving room for a title band, so tall stacked
   ranges clip.
3. **Greedy, unbalanced continuation.** `_excel_data_chunks` packs page 1 to the
   budget and dumps a short tail. Orphan avoidance only nudges a `<4`-row tail; a
   4-row tail (RO9–RO12) is allowed, and a 37/11 split is considered "fine".
4. **Dark bands preserved.** Source dark title fills survive into output because
   nothing recolors them for normalized output.

---

## Fix plan (this milestone)

- **Phase A** — `core/table_style_profile.py`: Singh360 standard constants +
  `apply_singh360_profile(block, style)` that recolors dark title fills → orange
  (`#FFC000`, black centered bold text) and header rows → gray (`#D9D9D9`),
  preserving gold controller/section bands and applying alt-row light gray.
- **Phase B** — Auto-fit: allow the exact range to grow to the printable body
  width (grow cap) and reserve the orange title-band height so tall ranges never
  clip.
- **Phase C** — Balanced continuation: when a split is unavoidable, distribute
  rows evenly across pages (24/24 not 37/11) and split panel/lighting ranges on
  section boundaries so LCP never orphans RO9–RO12.
- **Phase D** — Page fields `renderProfile="singh360_standard_table"` and
  `normalizedHeaderStyle="orange"` (default) on every non-cover page; a rendered
  orange title band on every table/text/instruction page; gray column headers in
  CSS for the normalized/index renderers.
- **Phase G** — Per-page render diagnostics (family, profile, scale, font, rows,
  continuation count + reason).
- **Phase H** — Smokes: `smoke_singh360_standard_table_style.py`,
  `smoke_table_autofit.py`, `smoke_balanced_continuation.py`,
  `smoke_orange_headers.py`.

---

## Acceptance (tracked)

- [ ] No `15.1` LCP continuation holding only RO9–RO12.
- [ ] RDM/IDF is one page or a balanced split (no short tail).
- [ ] Lighting Output Matrix never clips (fits or splits into 2 sections).
- [ ] All non-cover pages carry an orange title band + gray headers.
- [ ] No dark/black title bands except the cover or explicit legacy setting.
- [ ] Front-matter tables use the full printable body width.
- [ ] Optional `include=NO` sheets never output.

> Customer SA31/SA38 workbooks are NOT in the repo (code-only policy). Automated
> smokes use synthetic fixtures; final visual QA is done locally by the user
> against the real SA31 export.
