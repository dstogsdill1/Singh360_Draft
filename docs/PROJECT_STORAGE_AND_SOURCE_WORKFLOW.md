# Project Storage and Source Workflow

## Active storage

The local `.docs/projects` package is the active source of truth. Project
Settings may name an existing Google Drive, OneDrive, shared-drive, network, or
local folder as an external mirror destination. `Export / Backup Project Folder`
writes a verified, one-way package with a `project_manifest.json`, workbook,
Source Library manifest and files, drawing assets, exports, and a project ZIP.

The exporter stages and hashes the package before promotion. It preserves the
previous successful package when replacing an existing mirror. The external
copy is a backup and handoff artifact, not a second live workspace. Do not edit
the app project and mirrored workbook independently.

Moving the active storage root to cloud storage is deliberately deferred. That
change requires separate validation of multi-computer access, file locking,
concurrent edits, interrupted cloud synchronization, rollback, offline
operation, and conflict recovery.

## Fresh project workflow

Use this sequence for a new project, including the next Store 829 package:

1. Create a project with the appropriate profile, normally `EMS_FULL`.
2. Enter confirmed project metadata.
3. Upload the source folder or use Import ZIP.
4. Review paths, versions, hashes, and previews in Source Library.
5. Queue schedule conversions and select their canonical target sheets.
6. Edit the canonical Data Workspace sheets.
7. run Update Drawings preview.
8. Apply Update Drawings.
9. Review included, excluded, generated, and protected-manual pages.
10. Run SAVE + WRITE EXCEL.
11. Export the PDF and optional external mirror package.

Folder and ZIP imports preserve safe relative paths. Originals remain immutable;
replacement uploads create versions; archive is the normal removal action.
Conversion output must receive its own source/version record.

## V1 limitations

- External mirroring is explicit and one-way; there is no silent live sync.
- DOC/DOCX previews are metadata fallbacks, not full-fidelity renderings.
- No OCR runs automatically.
- The browser supplies folder-relative paths; unsupported or unsafe entries are
  rejected and recorded in the import report.
