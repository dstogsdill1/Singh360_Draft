---
applyTo: "server.py,core/**/*workbook*.py,core/**/*project*.py,frontend/src/**/*.{ts,tsx}"
---

# Workbook synchronization instructions

Follow the root `AGENTS.md`.

- Treat the linked workbook, baseline hashes, project identity, and two-sided
  conflict detection as authoritative safeguards.
- Preserve SA31, project 829, workbook links, worksheet identities, widths,
  heights, merged ranges, formulas, styles, and manual canvas objects.
- Support legacy persisted shapes with narrow read compatibility instead of
  overwriting project data.
- The shared geometry contract preserves Excel column units, row-height points,
  default and explicit dimensions, hidden rows/columns, merges, wrapping, and
  alignment. Univer/drawing pixels and PDF points must use the canonical
  conversion helpers; unchanged Excel units must round-trip exactly.
- Never invent missing engineering values or silently substitute workbook data.
- Never run or automate **SAVE + WRITE EXCEL** unless the user explicitly asks
  for that exact action.
- Keep source-sheet setup metadata outside the editable grid. `00_INDEX`
  controls the generated locked title/instruction bands; A3 is the default
  editable source origin unless a page recipe explicitly says otherwise.
- Only explicit `YES` publishes. `NO`, `VERIFY`, and blank remain editable and
  visible but excluded, with the same status colors in the workbook, tabs,
  Page Editor, managers, and index views.
- An in-memory dirty Data Workspace must block navigation and override any
  apparent workbook-match status. Local project save means Excel sync pending
  until an intentional write-back succeeds.
- Tests must use generated sanitized workbooks or JSON fixtures outside
  `.docs/`; never exercise write-back against live customer workbooks.
