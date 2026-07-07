# BUGLIST - Table Output 4E (SA31 regression)

Audit of the latest SA31 export issues reported for Emergency 4E. This file is
created before code changes, per Phase 0.

## Observed Failures

| Page | Failure | Expected behavior |
| --- | --- | --- |
| Page 2 Sheet Index | Output index still includes NO / optional rows and does not fit cleanly. | Normalized/output index lists included output pages only, fits one page unless included rows truly exceed body. |
| Page 14 Lighting Output Matrix | Relay / contactor schedule is clipped or cut off. | Full table geometry visible; split by Controller I/O and Relay / Contactor sections if needed. |
| Page 15 LCP Panel Schedule | Closest current page, but body style has confusing fills and split can orphan RO rows. | White body cells, visible gridlines, gray headers, orange section bands; split by LCP logical sections. |
| Page 16 EC Field Instructions | Table clipped; only part of the instruction rows show. | All current instruction rows fit on one page with wrapping and auto-height rows. |
| Page 17 DC Field Instructions | Table clipped; only part of the instruction rows show. | All current instruction rows fit on one page with wrapping and auto-height rows. |
| Page 18 EMS Remote Instructions | Table clipped; only part of the instruction rows show. | All current instruction rows fit on one page with wrapping and auto-height rows. |
| Page 23 Company Info | Rendered as a tiny generic table. | Centered Singh360 company/logo reference page using workbook values as data. |
| Other table pages | Some tables look like cropped screenshots with inconsistent body fills. | Clean gridline drawing tables, no zebra fill by default, no silent clipping. |

## Likely Root Causes

- Sheet Index was converted to an exact workbook range, preserving optional rows
  from the source tab rather than deriving the output index from included pages.
- Exact range renderer used fixed Excel row heights with `overflow: hidden`, so
  wrapped text could clip instead of expanding rows.
- Fit logic allowed very tall tables to shrink or visually clip instead of
  failing/splitting at row or section boundaries.
- The table style path still preserved alternating body fills from workbook
  templates, which read as zebra striping in normalized output.
- Continuation logic splits rows greedily instead of honoring known logical
  sections for LCP, Lighting, and IDF/network tables.
- Company Info is classified as a normal tabular page instead of a special
  centered reference/company page.

## 4E Acceptance Checklist

- [x] Page 2 Sheet Index lists included pages only.
- [x] Page 2 fits one page unless included rows truly exceed body.
- [x] Tables use gridlines and white body cells by default.
- [x] Source highlights and blocked/unused fills are preserved when intentional.
- [x] No table silently clips rows/text at export; layout warnings render visibly.
- [x] Lighting Output Matrix no longer crops relay schedule; splits by section when needed.
- [x] LCP splits by logical section, not RO orphan tail rows.
- [x] EC/DC/EMS instruction rows all fit and wrap.
- [x] Company Info renders as centered logo/company info page.
- [x] Smoke tests cover included-only index, no clipping, gridline style,
      logical splits, and company info.

## Validation Added

- `scripts/smoke_included_only_index.py`
- `scripts/smoke_no_table_clipping.py`
- `scripts/smoke_gridline_table_style.py`
- `scripts/smoke_logical_section_splits.py`
- `scripts/smoke_company_info_page.py`
