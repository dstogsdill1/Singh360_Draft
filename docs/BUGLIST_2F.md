# BUGLIST_2F — reproduction notes

Method: this pass was reproduced by **code inspection** of the current build plus
the existing smoke scripts (routes, import, project-consistency). A full
interactive browser session against the SA31 workbook is still recommended and
is captured by the new `scripts/smoke_editor_browser.py` + `docs/VISUAL_QA.md`
checklist. Items below drove the 2F fixes.

Reference workbook:
`Copy of Singh360 Drawing Workbook_HEB_102_SA-31 (1).xlsx`

## Confirmed issues (from code)

1. **Objects hard to move / text boxes not grabbable.**
   The overlay canvas used a binary pointer-events model: it was `none` unless
   "Edit Overlay" was toggled on or a draw tool was active. So a pasted image or
   text box could not be clicked/moved without first toggling overlay mode →
   feels broken. FIX (Phase A/C): smart hover pass-through — the overlay becomes
   interactive automatically when the cursor is over an overlay object, and lets
   clicks fall through to base content (editable tables/text) otherwise.

2. **Right-click shows the browser menu, not an app paste workflow.**
   No custom context menu existed. FIX (Phase B): app context menu on the sheet
   with Paste Image / Insert Text / Arrow / Line / Duplicate / Delete / Bring to
   Front / Send to Back / Lock, plus a clear "Press Ctrl+V to paste screenshot"
   fallback when the browser blocks clipboard image reads.

3. **Double "— CONTINUED".**
   Import writes the continuation title as `... — CONTINUED`, and the title block
   ALSO appended a `— CONTINUED` badge → doubled. FIX (Phase E): normalize the
   title (strip a trailing `— CONTINUED`) and rely on a single badge.

4. **PDF export defects / possible missing overlay images.**
   `core/export_pdf.py` waited a fixed 1200ms after `networkidle` and hard-failed
   on ANY console error. Async Fabric image loads (pasted screenshots / embedded
   workbook images) could be unpainted at capture, and noisy console warnings
   could abort a valid export. There was no `@page` size rule. FIX (Phase F):
   wait for `body[data-print-ready="1"]` (PrintView sets it after overlay images
   settle), only fail on real page errors, and add `@page { size: 17in 11in }`.

5. **No snapping when moving objects.**
   Only a coarse grid snap on move existed; no center/edge guides. FIX (Phase C):
   grid + canvas-center snap with visible guide lines while dragging. NOTE: full
   arrow-endpoint-to-object snapping with live connector re-routing remains
   partial (see "Still not implemented").

6. **Stale README.**
   `README.md` still described the old SmartDraw/VSON/Visio generator. FIX
   (Phase K): rewritten for the current Singh360 Draft editor; legacy generator
   notes moved to `docs/LEGACY_GENERATOR.md`.

## Verified working before 2F (regression guard)

- Workbook import (31 pages, 24 included, 2 continuation) — `smoke_import_workbook.py`.
- Routes register (27 routes) — `smoke_routes.py`.
- Project consistency — `smoke_project_consistency.py`.
- Embedded image extraction (6 sheets incl. LCP1/LCP2).

## Still not implemented after 2F (honest)

- Rich text / table formatting ribbon (Phase D) — browser contenteditable only.
- Recompose / shrink-to-fit / merge-continuation layout engine (Phase E) —
  "Make independent" exists; automatic re-fit does not.
- Auto-insert of extracted LCP/layout images into the page body (Phase G) —
  images render as inline blocks when present; automatic placement/scaling into
  the editable overlay is manual (paste/drop).
- Full Asset Manager list with thumbnails / replace / delete (Phase J) — folder
  paths are shown; list UI is not built.
- Arrow endpoint object-snap with live connector re-routing (Phase C) — grid /
  center snap works; connector glue does not.
