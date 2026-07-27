---
applyTo: ".docs/**,.local_backups/**,.tmp/**"
---

# Runtime-data instructions

Follow the root `AGENTS.md`.

- `.docs/` is protected production runtime data. Never delete, rename, move,
  overwrite, stage, or commit any file beneath it.
- Preserve SA31, project 829, workbooks, components, sources, PDFs, exports,
  and manual canvas objects exactly.
- `.local_backups/` is recovery data and must not be staged or committed.
- `.tmp/` is only for sanitized disposable fixtures. Remove task-created
  artifacts when verification finishes.
- If a requested change would require production-data mutation, stop and obtain
  explicit user authorization. **SAVE + WRITE EXCEL** always requires explicit
  authorization.
