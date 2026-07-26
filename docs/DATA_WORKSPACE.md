# Data Workspace

The full-screen Data Workspace uses the open-source Univer Sheets core preset. The Python backend remains authoritative for XLSX import and writeback; no Univer Pro XLSX package is used.

The app-owned live document is `.docs/projects/<slug>__<id>/data/workbook.json`. Saves use an expected revision and return HTTP 409 for stale writes. Writes are atomic, and the previous document is retained in bounded workbook history.

Univer provides worksheet tabs, formula bar, cell editing, selection, keyboard navigation, row and column operations, merge, formatting, number formats, undo/redo, find, freeze controls, and zoom. The browser clipboard handles HTML and plain-text table data; Excel and Google Sheets preservation depends on what those applications expose to the browser. Values, formulas, spans, common font/fill/border/alignment/wrap attributes, and represented number formats are accepted. TSV is the fallback.

Charts, macros, conditional formatting, embedded workbook images, and proprietary Excel features are preserved through workbook import/writeback where supported, not ordinary clipboard paste. V1 does not claim complete Excel parity.

Update Drawings displays compile operations and warnings before applying generated layers. SAVE + WRITE EXCEL first saves the Data Workspace, backs up the project workbook, writes values/formulas/layout, updates metadata/index tabs, and records the new checksum.
