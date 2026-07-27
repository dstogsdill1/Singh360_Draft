---
applyTo: "server.py,core/**/*.py,engines/**/*.py,scripts/**/*.py,tests/**/*.py"
---

# Backend instructions

Follow the root `AGENTS.md`.

- Inspect the live route, service, model, test, and current diffs first.
- Keep project identity, workbook authority, baseline hashes, conflict checks,
  and atomic writes intact.
- Preserve existing project schemas and read legacy-compatible shapes when
  practical; do not rewrite runtime packages merely to migrate them.
- Resolve project paths through the existing store and reject path traversal.
- For linked-root projects, Project Files must enumerate and mutate only the
  validated physical root. Never substitute `STANDARD_FOLDERS` or a mirrored
  `.docs/sources` tree; retain that virtual mode only for unlinked projects.
- Use sanitized temporary directories and generated fixtures in tests.
- Never read from, write to, delete, stage, or commit `.docs/`.
- Route workbook/drawing/PDF unit conversion through
  `core/workbook_geometry.py`; preserve exact Excel units, defaults, explicit
  dimensions, visibility, merges, wrapping, and alignment.
- Prove changed behavior with the smallest relevant compile, unit, and direct
  API checks. Do not claim success from inspection alone.
