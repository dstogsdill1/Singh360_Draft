# Singh360 Draft — Safe Workbook and Drawing Workflow V44

## One master at a time

The workbook and Singh360 Draft may both be used, but they must never be edited independently at the same time.

### Normal daily work

1. Start Singh360 Draft from the normal Desktop Control Center.
2. Open the saved project.
3. Work in Singh360 Draft.
4. Use **Save Now** during editing.
5. Close Excel and Google Sheets.
6. Use **SAVE + WRITE EXCEL** when you want a complete workbook mirror.
7. Wait for **PROJECT + EXCEL SAVED** before opening the workbook.

### When Excel was edited while Singh360 Draft was closed

1. Save and close Excel.
2. Start Singh360 Draft.
3. Open the project.
4. Choose the workbook as the authority when the app reports that the workbook changed.
5. Review the rebuilt drawing pages before editing.

## Workbook control sheets

- `00_PROJECT_META` stores project and synchronization metadata. It never publishes.
- `00_INDEX` controls base drawing pages only. Only explicit `YES` rows publish.
- `00_DRAWING_PAGES` lists every actual drawing page, including generated continuation pages and its matching physical Excel mirror tab.
- `00_HELP` and `00_AI_GUIDE` are control/instruction sheets and never publish.

## Source worksheets and drawing pages are not the same thing

One long source worksheet may produce several drawing pages:

`R-2.1 source worksheet` → `EMS 12.3` → `EMS 12.3a` → `EMS 12.3b`

The base worksheet remains the editable source. Generated continuation tabs are read-only mirrors of the individual drawing pages. They are rebuilt by **SAVE + WRITE EXCEL** and are ignored when the workbook is imported again.

## Page filters

- **All Pages** shows every drawing page.
- **Included Only** shows only pages currently included in the drawing set.
- **Not Included** shows only excluded/reference pages.
- The sidebar, bottom tabs, Previous/Next buttons, and page counter must all follow the same filter.

## Long-term architecture

The safest final design is one master Singh360 project:

`Excel import once` → `Singh360 spreadsheet + drawing editor` → `PDF / Excel exports`

The in-app spreadsheet should use a production spreadsheet engine rather than a custom HTML table so it can support Excel-like sizing, formatting, formulas, copy/paste, merges, and row/column operations. Until that engine is installed, use one-authority-at-a-time synchronization as described above.


## V44H exact base-tab synchronization

After physical drawing-page mirrors are built, Singh360 now rewrites every
base-page `00_INDEX` Sheet Tab from the stable Page ID to the exact physical
worksheet title. The same value is written back to the saved project page and
the project’s linked `00_INDEX` worksheet grid. This specifically prevents a
generated base page such as `EMS 2.0 Sheet Index / TOC` from leaving an obsolete
pre-mirror tab name in `00_INDEX`.

Verification resolves whitespace only to diagnose a candidate, then requires
the stored `00_INDEX` and `00_DRAWING_PAGES` values to equal the physical Excel
worksheet title exactly.
