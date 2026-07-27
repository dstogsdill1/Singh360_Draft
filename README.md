# Singh360 Draft

Singh360 Draft is the current Singh360 EMS drawing-package editor. It imports
project workbooks, builds fixed 17 x 11 drawing sheets, supports editable canvas
overlays and reusable components, and exports PDF drawing packages.

## Start locally

```powershell
cd "C:\Users\DarrinStogsdill\OneDrive - Homeland Development Services LLC\Desktop\Singh360 Draft"
.\.venv\Scripts\Activate.ps1
$env:SINGH360_PORT=8766
python server.py
```

Open:

- Drawing editor: `http://127.0.0.1:8766/app`
- Component administration: `http://127.0.0.1:8766/component-catalog`
- Public component catalog:
  `https://dstogsdill1.github.io/Singh360-Draft/component-library/`

## Folder roles

- `docs/` - public GitHub Pages content only; committed to Git.
- `.docs/` - local runtime data: projects, component library, exports, backups;
  never committed.

Do not merge or rename those folders.

## Active architecture

- `server.py` - Flask API and frontend host.
- `frontend/src/` - React/TypeScript/Fabric editor.
- `core/` - workbook import, project storage, page composition, library, PDF export.
- `engines/ems_sheet.py` - active SVG sheet renderer.
- `tools/component_catalog/` - editable local component catalog.
- `docs/component-library/` - published GitHub Pages catalog.
- `scripts/smoke_*.py` - active smoke tests.
- `tests/generated_fixtures.py` - sanitized test workbook/PDF generators.

## Launchers

The repository intentionally has exactly two Windows launchers:

- `START_SINGH360_DRAFT.bat` creates/checks the local environment, builds the
  frontend, starts port 8766, and opens the editor.
- `STOP_SINGH360_DRAFT.bat` stops the process listening on port 8766.

## Data safety

Never commit customer workbooks, project PDFs, screenshots, `.docs/`, exports,
tokens, or credentials.
