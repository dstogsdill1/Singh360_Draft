# AGENTS.md - Singh360 Draft Operating Instructions

This file is the authoritative agent policy for the entire repository. More
specific instruction files may add constraints for their scope, but they may
not weaken or override this policy.

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

1. Before changing anything, inspect the live branch, `HEAD`, working-tree
   status, and relevant diffs. Do not assume a prior run's state.
2. Never invent project or engineering data.
3. Never delete, stage, commit, or overwrite `.docs/`.
4. Preserve SA31, project 829, linked workbooks, components, project sources,
   and manual canvas objects. Never wipe manual work without a verified backup.
5. Never run **SAVE + WRITE EXCEL** unless the user explicitly requests it.
6. Make the smallest related change. Reuse the working implementation,
   components, routes, and project schema already present.
7. Never commit customer files, workbooks, PDFs, exports, runtime data,
   credentials, or secrets.
8. Never claim success without direct evidence from the requested checks.
9. Preserve 17 x 11 geometry and export fidelity.
10. Keep component changes recoverable.
11. Never merge `docs/` and `.docs/`.
12. Do not add historical buglists or retired architecture documentation.
13. Keep `docs/` limited to required public component-catalog content.
14. Tests must generate sanitized fixtures; they must not require, copy, or
    mutate customer or sample files.
15. Do not weaken workbook authority, baseline hashes, project identity checks,
    or two-sided conflict detection.
16. For linked-root projects, Project Files is a direct validated view of the
    physical project root. Never replace it with a synthetic folder list or
    mirrored `.docs/sources` workspace.

## Shared workbook geometry contract

- `core/workbook_geometry.py` and
  `frontend/src/model/workbookGeometry.ts` are parity implementations of the
  one Singh360 workbook geometry contract.
- Excel column widths remain OOXML character units; row heights remain points.
  Univer, Page Editor, and drawing renderers use CSS pixels; PDF uses points.
- Do not add ad-hoc `* 7`, `/ 7`, `* .75`, or `* 4 / 3` conversions. Preserve an
  unchanged exact Excel dimension when its displayed pixel size is unchanged.
- Persist default and explicit dimensions, hidden rows/columns, merges,
  formulas, styles, wrapping, and alignment through import, Data Workspace,
  project-local save/reload, Update Drawings, Page Editor, PDF, and explicit
  Excel write-back.
- Drawing/PDF tables preserve relative column proportions and use one uniform
  page scale. Never stretch or crush individual columns, use `break-all`, or
  split ordinary words letter-by-letter. Wrapped content grows rows and may
  create continuation pages; continuation pages reuse the same width map.

## Required checks

Run only the checks relevant to the requested change. When a release request
specifies an exact validation set, do not add broader checks or browser
automation. Record the command and its direct result.

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
