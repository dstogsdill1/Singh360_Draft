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
- For linked-root projects, render Project Files from the recursively
  enumerated physical project root. Do not inject synthetic folders or present
  `.docs/sources` as the visible file workspace.
- Do not expose or invoke **SAVE + WRITE EXCEL** from a new workflow unless the
  user explicitly requests workbook writes.
- Source sheets reserve locked gray generated bands above an editable A3 paste
  canvas; show `00_INDEX`-owned setup metadata outside normal cells.
- Dirty Data Workspace state must prompt Save / Discard / Cancel for app
  navigation and protect refresh/close. A local save is workbook-sync pending,
  not a workbook match.
- Treat only explicit `YES` as published and keep exclusion/lifecycle colors
  consistent across tabs, cards, sidebars, managers, and index views.
- Route Univer/Page Editor/PDF geometry through
  `frontend/src/model/workbookGeometry.ts`; keep it in parity with
  `core/workbook_geometry.py`. Preserve workbook proportions with uniform page
  scaling and never use `break-all` for normal cell text.
- Run the production frontend build for source changes and report its result.
