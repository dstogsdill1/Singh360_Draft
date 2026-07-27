# AGENTS.md - Singh360 Draft Operating Instructions

## Mission

Maintain Singh360 Draft, the EMS drawing-package editor. The current product
imports workbooks, renders fixed 17 x 11 sheets, edits overlays/components,
preserves projects, and exports PDFs/packages.

Do not reintroduce the retired SmartDraw VSON / Visio VSDX / RDM XML generator.

## Sources of truth

- `server.py`
- `frontend/src/`
- `core/`
- `engines/ems_sheet.py`
- `.docs/` for local runtime data
- `docs/component-library/` for public Pages content

## Canonical identity

- Product name: `Singh360 Draft`
- Repository: `dstogsdill1/Singh360_Draft`
- Local folder: `Singh360_Draft`
- Local URL: `http://127.0.0.1:8766/app`
- Root launchers: `START_SINGH360_DRAFT.bat` and
  `STOP_SINGH360_DRAFT.bat`

## Rules

1. Never invent project or engineering data.
2. Never wipe manual work without a backup.
3. Never commit `.docs/`, customer files, exports, credentials, or secrets.
4. Preserve 17 x 11 geometry and export fidelity.
5. Keep component changes recoverable.
6. Never merge `docs/` and `.docs/`.
7. Do not add historical buglists or retired architecture documentation.
8. Keep `docs/` limited to required public component-catalog content.
9. Tests must generate sanitized fixtures; they must not require customer or
   sample files.
10. Do not weaken workbook authority, baseline hashes, project identity checks,
    or two-sided conflict detection.

## Required checks

```powershell
python -m compileall server.py core engines scripts tests
python -m unittest discover -s tests -v
cd frontend
npm run build
cd ..
python scripts\smoke_routes.py
python scripts\smoke_component_library.py
python scripts\smoke_sa31_829_regressions.py
python scripts\smoke_launchers.py
```
