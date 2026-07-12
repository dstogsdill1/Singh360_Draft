# AGENTS.md - Singh360 Draft Operating Instructions

## Mission

Maintain Singh360 Draft, the EMS drawing-package editor. The current product
imports workbooks, renders fixed 17 x 11 drawing sheets, edits canvas overlays
and components, preserves projects, and exports PDFs/packages.

Do not reintroduce the retired SmartDraw VSON / Visio VSDX / RDM XML generator.

## Sources of truth

- `server.py` - Flask routes and startup.
- `frontend/src/` - React editor.
- `core/` - current backend services.
- `engines/ems_sheet.py` - active sheet renderer.
- `.docs/` - local runtime data; never commit.
- `docs/` - public GitHub Pages only.
- `docs/component-library/` - published active catalog.

## Rules

1. Never invent project, controller, point, circuit, or equipment data.
2. Never wipe manual work without a backup.
3. Never commit `.docs/`, customer files, exports, credentials, or secrets.
4. Preserve 17 x 11 geometry and title-block/export fidelity.
5. Keep component changes recoverable.
6. Never merge `docs/` and `.docs/`.
7. Do not add historical buglists or retired architecture documentation.

## Required checks

```powershell
python -m compileall server.py core engines scripts
cd frontend
npm run build
cd ..
python scripts\smoke_routes.py
python scripts\smoke_component_library.py
```
