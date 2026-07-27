---
applyTo: "frontend/**/*.{ts,tsx,css,json}"
---

# Frontend instructions

Follow the root `AGENTS.md`.

- Inspect the current component, route, API client, styles, and diff first.
- Reuse existing Singh360 Draft components and interaction patterns. Do not
  redesign a working feature when a focused repair is sufficient.
- Preserve fixed 17 x 11 sheet geometry, project identity, components, sources,
  manual canvas objects, and export behavior.
- Keep Project Files and Data Workspace project-local; G Drive is a secondary
  mirror or backup, not the primary workspace.
- Do not expose or invoke **SAVE + WRITE EXCEL** from a new workflow unless the
  user explicitly requests workbook writes.
- Route Univer/Page Editor/PDF geometry through
  `frontend/src/model/workbookGeometry.ts`; keep it in parity with
  `core/workbook_geometry.py`. Preserve workbook proportions with uniform page
  scaling and never use `break-all` for normal cell text.
- Run the production frontend build for source changes and report its result.
