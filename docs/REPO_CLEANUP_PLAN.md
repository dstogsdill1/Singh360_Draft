# Repo Cleanup Plan

Audit of folders/files with a disposition. **No risky deletions in this pass** —
this is a plan. Removals only happen after confirming import/build still work.

## Keep (active, required)

- `server.py` — Flask backend (active).
- `core/` — active engine: `project_model`, `workbook_importer`, `page_normalizer`,
  `page_composer`, `csv_importer`, `pdf_importer`, `vsdx_importer`, `export_pdf`,
  `validation`, `project_store`.
- `frontend/` (src only) — active React editor. `frontend/dist` and
  `frontend/node_modules` are build/deps, gitignored.
- `scripts/` — smoke + inspector scripts.
- `docs/` — product docs.
- `sample_data/` — synthetic demo inputs (safe).
- `config.py`, `requirements.txt`, `README.md`, `AGENTS.md`, `.gitignore`.

## Legacy fallback (keep, clearly labeled)

- `web/index.html` — legacy `/editor` page. Superseded by `/app`. Kept only as a
  fallback and clearly labeled in the UI ("legacy fallback only"). Do **not**
  wire new features here.

## Legacy / pre-Draft engine (review later — do NOT delete now)

These predate the Drawing Package Editor and may still be referenced by the
older diagram-generation pipeline or docs. Confirm no imports before removing.

- `engines/` — old SmartDraw/VSDX/RDM diagram writers (`smartdraw_vson`,
  `visio_vsdx`, `rdm_layout_xml`, `drawing_package`, `svg_diagram`, `spatial_layout`,
  `title_block`, `doc_templates/`). Not imported by `server.py`/`core` editor path.
- `ems/` — old EMS component/widget library HTML. Gitignored in part; not used by
  the editor.
- `output/` — generated artifacts (gitignored). Safe to clear locally.
- `readme` (lowercase, if present) — possible duplicate of `README.md`.

## Generated / local-only (never commit)

- `.docs/` — projects, assets, exports (gitignored).
- `frontend/dist/`, `frontend/node_modules/` (gitignored).
- `output/`, `*.pdf`, `*.xlsx`, `*.csv`, `*.vsdx` (gitignored).

## Removal criteria (future pass)

1. `grep` the codebase for imports/references.
2. Confirm `python -m compileall server.py core` and `npm run build` still pass.
3. Confirm smoke scripts pass.
4. Only then remove, in a dedicated commit, one folder at a time.
