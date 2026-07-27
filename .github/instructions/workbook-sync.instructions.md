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
- Never invent missing engineering values or silently substitute workbook data.
- Never run or automate **SAVE + WRITE EXCEL** unless the user explicitly asks
  for that exact action.
- Tests must use generated sanitized workbooks or JSON fixtures outside
  `.docs/`.
