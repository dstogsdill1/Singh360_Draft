# Singh360 Draft — Drawing Package Editor

Singh360 Draft is a **desktop drawing-package editor** for MEP/R engineering
sheets. You upload a Singh360 drawing **workbook (`.xlsx`)**, and the app turns
each sheet into a fixed **17 x 11 drawing page** you can edit directly —
PowerPoint/Visio-style object editing on top of Excel-style content, with a
Singh360 title block and deterministic PDF/package export.

> Deterministic first, no hallucinated values, code-only repo. Customer
> workbooks, PDFs, CSVs and generated exports are **never** committed.

The older deterministic diagram generator (SmartDraw VSON / Visio VSDX / RDM
XML) now lives in [docs/LEGACY_GENERATOR.md](docs/LEGACY_GENERATOR.md).

---

## Quick start

```powershell
# 1. Build the frontend
cd frontend
npm install
npm run build
cd ..

# 2. Start the app (default port 8766 for local dev)
$env:SINGH360_PORT = 8766
python server.py

# 3. Open the editor
#    http://127.0.0.1:8766/app
```

`GET /` redirects to `/app`. The legacy single-file editor remains available at
`/editor` as a fallback only.

## Using the editor

1. **Upload a workbook** — File > Upload Workbook (`.xlsx`). Each worksheet
   becomes an output page (Cover, Text / Instructions, Table / Schedule, Matrix,
   Image / Layout, Hybrid Sheet, Underlay / Reference).
2. **Rename a sheet** — double-click a top page tab (or the code/title in the
   left Output Pages list). The change syncs to the tab, sidebar, right panel,
   title block, and export.
3. **Paste a screenshot** — click any page and press **Ctrl+V**, or right-click
   the sheet for **Paste Image / Insert Text / Arrow / Line**. Pasted images are
   auto-named `Screenshot YYYY-MM-DD HH-mm-ss.png`, selected, and resizable.
4. **Draw and arrange** — Insert tab (Text/Rectangle/Circle/Line/Arrow), Arrange
   tab (z-order), Home tab (group/lock/duplicate). Objects are grabbable
   directly; toggle **Edit Overlay** for precise overlay work.
5. **Reorder and number** — drag page tabs to reorder; "Sheet X of Y" updates
   live. File > **Renumber Sheet Codes** opens a preview modal (keep / sequential
   / custom prefix).
6. **Export** — File > **Export PDF** (17 x 11 landscape via headless Chromium)
   and **Export Package** (ZIP: `project.json`, `manifest.json`, sources, assets,
   exports).

## Where things are saved

- Projects live under `.docs/projects/<slug>__<id>/` (gitignored):
  - `sources/` — the uploaded workbook / CSV / PDF
  - `assets/images/` — pasted screenshots and attached images
  - `assets/images/excel/` — images extracted from the workbook
  - `exports/` — generated PDFs and packages
- The right panel shows the resolved Project / Assets / Screenshots folder paths.

## Architecture

- `server.py` — Flask app. Serves `frontend/dist` at `/app`, JSON API under
  `/api/*`, per-project storage via `core/project_store.py`.
- `core/workbook_importer.py` — openpyxl import to normalized pages + embedded
  image extraction.
- `core/export_pdf.py` — Playwright headless Chromium PDF export; waits for the
  `data-print-ready` signal so async overlay images are painted first.
- `frontend/` — React 18 + TypeScript + Vite + Fabric.js v6. The editor shell,
  ribbon, page renderers, universal overlay canvas, title block, and modals.

## Scripts

```powershell
python -m compileall server.py core scripts
python scripts/smoke_import_workbook.py "<workbook.xlsx>"
python scripts/smoke_routes.py
python scripts/smoke_project_consistency.py
python scripts/smoke_editor_browser.py   # optional Playwright end-to-end
```

See [docs/VISUAL_QA.md](docs/VISUAL_QA.md) for the manual QA checklist and
[docs/BUGLIST_2F.md](docs/BUGLIST_2F.md) for the current known-issues log.

## Not committed

Customer workbooks, PDFs, VSDX, CSVs, `.docs/`, `frontend/dist/`,
`frontend/node_modules/`, generated exports/screenshots, and secrets are all
gitignored. This repository is **code only**.
