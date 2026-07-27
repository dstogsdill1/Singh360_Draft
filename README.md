# Singh360 Draft

Singh360 Draft is the Singh360 EMS drawing-package editor. It imports project
workbooks, renders fixed 17 x 11 sheets, preserves app-owned overlays and
components, and exports PDF drawing sets and portable project packages.

## Canonical identity

- Product, UI, browser, and window name: **Singh360 Draft**
- GitHub repository: `dstogsdill1/Singh360_Draft`
- Local folder:
  `C:\Users\DarrinStogsdill\OneDrive - Homeland Development Services LLC\Desktop\Singh360_Draft`
- Project Home: `http://127.0.0.1:8766/app`
- Component administration: `http://127.0.0.1:8766/component-catalog`
- Public component catalog:
  `https://dstogsdill1.github.io/Singh360_Draft/component-library/`

## Start and stop

The repository intentionally has exactly two root launchers:

- `START_SINGH360_DRAFT.bat` creates or checks the Python environment, installs
  required packages when needed, builds the frontend, starts port 8766, and
  opens the generic Project Home at `/app`.
- `STOP_SINGH360_DRAFT.bat` stops the process listening on port 8766.

From PowerShell:

```powershell
cd "C:\Users\DarrinStogsdill\OneDrive - Homeland Development Services LLC\Desktop\Singh360_Draft"
.\START_SINGH360_DRAFT.bat
```

## Project workflow

1. Start Singh360 Draft and select an existing project, or create a project by
   uploading its workbook.
2. Use **Linked Workbook** to select the matching `.xlsx` or `.xlsm` file.
3. Confirm the selected workbook. Singh360 Draft verifies the workbook control
   sheets and project identity before synchronization.
4. Review the Workbook Inspector and apply only explicit, backup-first repairs.
5. Open Page Manager to review order, sheet codes, and Include/Exclude.
6. Edit pages. Local project saves protect app-owned work before workbook writes.
7. Export only reviewed, included pages. The Sheet Index and Page X of Y are
   refreshed before export.

Do not create a replacement project merely to relink a workbook. If a workbook
moves, relocate the link from Project Home; the local project remains intact.

## Authority and conflict safety

The workbook remains authoritative for verified worksheet cells, formulas,
formatting, the `00_INDEX` page manifest, and workbook-controlled page metadata.
Singh360 Draft remains authoritative for manual drawings, images, PDF crops,
symbols, highlights, connectors, overlays, and other canvas objects.

The app compares workbook and project hashes against the last synchronized
baseline:

- A workbook-only change is pulled into the app.
- An app-only workbook-backed change requires an explicit workbook write.
- If both sides changed, the app reports a conflict and blocks automatic
  overwrite.
- App-owned canvas work is merged back after workbook refresh and must never be
  erased by synchronization.

Before either synchronization direction or a repair, Singh360 Draft creates
recoverable project and workbook snapshots. Close Excel before a workbook write.

## Page status and publication

Issue status and Include/Exclude are separate:

- **Draft** — active creation.
- **Draft Confirmed** — engineer-reviewed draft.
- **Public** — approved for bid or external review.
- **Public Confirmed** — final approved publication before as-builts.

An excluded page stays visible and editable, but is omitted from the generated
Sheet Index and exports.

## Active architecture

- `server.py` — Flask API and frontend host.
- `frontend/src/` — React, TypeScript, and Fabric editor.
- `core/` — workbook authority, project storage, page composition, component
  library, and PDF/package export.
- `engines/ems_sheet.py` — active fixed-sheet SVG renderer.
- `tests/generated_fixtures.py` — generated sanitized workbook and PDF fixtures.
- `scripts/smoke_*.py` — active deterministic smoke and regression checks.
- `tools/component_catalog/` — local component-catalog UI templates.
- `docs/component-library/` — published catalog and downloadable component
  packages.

The retired VSON, VSDX, and RDM XML generator is not part of Singh360 Draft.

## Runtime and public files

- `.docs/` contains production projects, sources, component libraries, templates,
  exports, and backups. It is local runtime data and is never committed.
- `docs/` contains only the GitHub Pages component catalog. It is committed.

Never merge, rename, or substitute these folders. Never commit customer
workbooks, drawings, screenshots, project packages, exports, credentials, or
secrets.

## Verification

Minimum checks:

```powershell
python -m compileall server.py core engines scripts tests
python -m unittest discover -s tests -v
cd frontend
npm run build
cd ..
python scripts\smoke_routes.py
python scripts\smoke_component_library.py
```

The release regression pass also covers workbook authority/conflicts, sanitized
SA31- and 829-shaped workbooks, PDF crop/import/export, worksheet import,
connector persistence and rollback, no-scroll sheet rendering, launchers,
health, live browser Project Home, PDF export, and package export.
