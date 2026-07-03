# Singh360 SmartDraw — Implementation Plan

## Milestones

### Milestone 1 (current)

Deliver a stable workbook-to-WYSIWYG flow with modular architecture:

- backend project model + importer + save/export APIs,
- React frontend shell with sheet manager/workbook view/document view,
- real Fabric canvas editor for canvas pages,
- deterministic 17x11 PDF export route,
- acceptance smoke checks.

### Milestone 2

- underlay management UI (PDF/image transforms + lock/layer controls),
- CSV import UI and worksheet creation flow,
- VSDX page-list extraction underlay flow,
- richer worksheet formatting support.

### Milestone 3

- VSDX semantic extraction to editable canvas objects,
- advanced revision and issue workflows,
- visual diff checks and regression baselines.

## Proposed Target Structure

```text
frontend/
  package.json
  vite.config.ts
  src/
    App.tsx
    api/
    model/
    components/
    styles/

core/
  project_model.py
  workbook_importer.py
  csv_importer.py
  pdf_importer.py
  vsdx_importer.py
  template_engine.py
  export_pdf.py
  validation.py
```

## API Contract (Milestone 1)

- `GET  /api/health`
- `GET  /api/projects`
- `POST /api/projects/new`
- `GET  /api/projects/<id>`
- `POST /api/projects/<id>`
- `POST /api/projects/<id>/pages`
- `POST /api/projects/<id>/export/pdf`
- `POST /api/import/workbook`

Planned soon:

- `POST /api/projects/<id>/sources`
- `POST /api/import/csv`
- `POST /api/import/pdf`
- `POST /api/import/vsdx`

## Workbook Import Rules (Milestone 1)

1. Parse all worksheets.
2. Parse `00_INDEX` by header text aliases.
3. Build page ordering/metadata from `00_INDEX`.
4. Keep all source tabs discoverable in workbook panel.
5. Normalize null-like values to empty strings.
6. Page type classification from index metadata + title heuristics.
7. Default include behavior:
   - blank include => included,
   - TEMPLATE/UTILITY => excluded by default.

## Acceptance Tests

### Backend smoke tests

- Workbook import returns no `NaN`/`NaT`/`<NA>` values.
- `00_INDEX` output page creation works.
- Blank include defaults to included.
- TEMPLATE/UTILITY rows default excluded.
- Project save/reload round-trip is lossless for core fields.

### Frontend smoke tests

- App loads without JS runtime errors.
- Workbook upload returns project id and renders pages.
- Sheet manager page selection updates document view.
- Title block visible and updates with metadata.
- Page numbering updates after include toggles.
- Save Now and autosave status updates are visible.
- Canvas editor supports add/select/move/delete and persists state.

### Export smoke tests

- Included pages only in output.
- PDF dimensions are 17x11 landscape with zero margins.
- Export fails loudly if renderer has fatal page errors.

## Delivery Notes

- Keep existing Flask startup behavior and `/editor` compatibility during transition.
- Keep old `web/index.html` as fallback while new frontend is introduced.
- Avoid introducing data hallucination or destructive migration behavior.
