# Symbol Mapper — Singh360 Standard

Symbol Mapper reads a printed `SYMBOLS KEY` or `SYMBOL LEGEND`, lets the user
choose which rows to include, and applies ready-made solid or split colors before
running detection.

## Saved standard

The writable standard is stored under:

```text
.docs/symbol_mapper/templates/standard.json
```

The repository provides the initial company standard at:

```text
defaults/symbol_mapper_standard.json
```

The default is copied only when no local standard exists. Future edits are saved
through the Symbol Mapper interface and are not committed to GitHub.

Matching uses **code plus description**, not code alone. This keeps duplicate
codes such as `S — LIQUID LINE SOLENOID VALVE 120V` and `S — CLEAN SWITCH`
independent.

When a later drawing contains the same row, its include setting and color load
automatically. New rows are marked **New**. Assign a color and click **Update
standard**; the server merges the rows into the existing standard instead of
deleting symbols that are absent from the current page.

Every standard update creates a timestamped backup under:

```text
.docs/symbol_mapper/templates/history/
```

## Split-color markers

For a vertical split marker, the left fill and left half of the outer border use
color one. The right fill and right half of the outer border use color two. The
same visual rule is used in palette buttons, row swatches, legend preview, result
counts, review PDF, and final PDF.

## Accuracy and export

- Exact symbol-code text with enclosing vector evidence may be accepted.
- Uncertain matches remain review items.
- Only accepted matches are included in the final PDF.
- The uploaded source PDF is never modified in place.
- Source hash and page geometry are checked before final output is returned.

Runtime sessions and saved standards remain beneath `.docs/` and are never part
of customer-facing Git history.


## Add-page confirmation and package ordering

When **Add page to Singh360** is used, the editor now waits for the reviewed PNG
to finish loading on the Fabric canvas and confirms the exact latest project JSON
on the server before reporting success.

The output form prefills a sheet code and page title from the source PDF filename
when that filename contains an explicit drawing code, such as `R-3.2`. Both fields
remain editable.

Published Package rows and Renumber Sheet Codes rows support drag-and-drop.
Continuation pages move with their base page. Cover and Sheet Index remain in the
required first and second published positions. Excluding a page records its prior
package slot, and including it restores that slot.


## PDF page import and Sheet Index continuation (v2.7)

- Prefer **Insert > PDF Page / Crop** over screenshots for floor plans and engineering sheets.
- The server renders the source PDF directly at 300, 400, 500, or 600 DPI.
- Once inserted, PDF pages use the same Crop / Fit, Fit Page, Fill Page, and Reset Crop commands as other images.
- The published Sheet Index is rebuilt on every save/export and automatically continues as EMS 2.0a, EMS 2.0b, etc. when needed.

## Vector-preserving PDF-page export (v2.9)

`Insert > PDF Page / Crop` keeps a raster preview for interactive positioning, but
that preview is not the final engineering output. During PDF export Singh360:

1. creates an export-only project clone;
2. hides eligible direct PDF preview images in that clone;
3. renders the remaining title blocks and manual overlays on a transparent page;
4. restores the original source PDF page/crop with PyMuPDF at the saved position;
5. verifies output page geometry and writes a vector-export audit JSON beside the PDF.

The live `project.json`, customer source PDF, and editor preview asset are not
modified. Rotated, flipped, grouped, semi-transparent, missing-source, or invalid
PDF objects deliberately stay raster rather than disappearing.

## Selected-page PDF export (v2.9)

The Export PDF dialog starts with all published pages checked. Use **Select All**,
**None**, or check individual pages. Export QA warnings, `Page X of Y`, and the
published Sheet Index are calculated from that selected export set. Sheet Index
continuation pages remain automatic whenever the base Sheet Index is selected.

## Version 2.9 crystal-clear PDF export and selective package export

- PDF crop coordinates are measured against the displayed PDF page image, not the letterboxed modal wrapper.
- The canvas keeps a high-resolution preview for editing. Final export hides eligible previews in an export-only clone and restores the original source PDF crop as vector content.
- Export PDF starts with all included pages selected and supports Select All, None, and individual page selection.
- Export warnings, Sheet Index rows, and Page X of Y are scoped to the selected export set.
- The live project, source PDF, and manual overlays remain unchanged.

## v3.1 — canonical RDM library and automatic counts

The clickable v3.1 updater also runs `scripts.cleanup_rdm_symbol_library` against
local `.docs/library` after creating a full rollback backup under `.docs/archive`.
It installs the tracked Singh360 RDM standard, retires only matching obsolete
marker/sign records, keeps numbered callouts and unrelated equipment, and creates
one combined three-sign signage legend plus five editable legend templates.

The Symbol Mapper results panel reports live **Found / Included / Check / Ignored**
counts for every selected class. Counts update immediately after a review decision.
Exact plain CLEAN SWITCH symbols are accepted automatically using the narrow saved
aliases `S`, `$`, `CS`, and `CCS`; ambiguous unrelated text remains review-only.

Repository smoke tests must be run as modules from the repository root, for example:

```powershell
python -m scripts.smoke_vector_pdf_export
```

Running `python scripts\smoke_vector_pdf_export.py` directly is not supported because
Python otherwise puts `scripts\` rather than the repository root on `sys.path`.


## v3.2 — field-only API regression correction

The detector intentionally excludes the printed samples inside the drawing's SYMBOLS KEY.
The API regression fixture therefore expects three field occurrences (TS=2 and CC=1),
not five occurrences that incorrectly include the two legend examples.
