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
