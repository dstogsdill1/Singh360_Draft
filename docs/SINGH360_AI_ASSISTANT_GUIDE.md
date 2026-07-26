# Singh360 Draft — AI-Ready Operating Guide

Help version: `2026.07.23-foolproof-workflow-1`

## Purpose

Singh360 Draft creates, edits, synchronizes, reviews, and exports engineering drawing packages. Each project has:

- a Singh360 project package containing `project.json`, assets, images, underlays, exports, backups, and app-only canvas objects;
- one linked Excel `.xlsx` or `.xlsm` workbook;
- a permanent page manifest controlled by `00_INDEX`.

The workbook and the app do not own the same data.

## Authority model

### Workbook owns

- verified worksheet cell data and formulas;
- workbook images, merges, row heights, column widths, and approved workbook formatting;
- `00_INDEX` page codes, titles, order, Include/Exclude, issue status, Page ID, and parent relationships when the workbook is chosen as the synchronization source.

### App owns

- manual drawings;
- pasted images and PDF crops;
- symbols, highlights, connectors, overlays, and canvas objects;
- app-created page assets and project recovery snapshots.

Workbook synchronization must never erase app canvas objects.

## Exact project workflow

1. Start the local app with `START_SINGH360_LOCAL.bat`.
2. Project Home opens.
3. Select the existing project, or create a new project from a new workbook.
4. In **Linked Workbook**, browse to the real `.xlsx` or `.xlsm`.
5. Review the path and click **Confirm Selected Workbook**.
6. The app verifies `00_PROJECT_META`, `00_INDEX`, project name, schema version, and Help version.
7. The **Workbook Inspector** audits the workbook.
8. Apply Safe Repair when structural problems exist. A backup is created first.
9. Resolve the initial synchronization:
   - **Import Workbook Structure into App** when Excel has the correct page manifest.
   - **Write App Structure into Workbook** when the app has the correct page manifest.
10. A matched workbook/project backup is created before either resolution.
11. Open **Page Manager** to review thumbnails and Include/Exclude.
12. Open the Page Editor.
13. Save normally. The local project saves first. Workbook problems become **Workbook Sync Pending** and do not block page navigation.
14. Export only included pages. The generated Sheet Index and Page X of Y are refreshed before export.

## Four issue stages

- **Draft** — initial creation.
- **Draft Confirmed** — engineer-reviewed draft.
- **Public** — approved for bid or external review.
- **Public Confirmed** — final approved publication before as-builts.

Issue status is separate from Include/Exclude.

## Sync resolution safety

### Import Workbook Structure into App

Updates page order, codes, titles, Include/Exclude, issue status, and supported manifest fields from `00_INDEX`.

Keeps app drawings, images, crops, symbols, components, highlights, and canvas objects.

### Write App Structure into Workbook

Updates `00_INDEX`, workbook tab order/colors, status fields, and required companion sheets.

Keeps existing worksheet cells, formulas, images, merges, and app canvas objects.

### Automatic backups

Before either direction, the app stores:

- `project_before.json`;
- `workbook_before.xlsx` or `.xlsm`;
- `resolution_manifest.json`.

Location: `.docs/backups/workbook_resolution/<project-id>/<timestamp>/`

## Workbook Inspector

### Safe Repair

- ensures `00_PROJECT_META`, `00_INDEX`, and `00_HELP`;
- restores the full index schema;
- registers new workbook sheets as excluded;
- restores sequential order, Page IDs, valid statuses, source modes, and sync directions;
- reorders physical tabs;
- restores tab colors and dropdowns;
- standardizes control/index formatting.

### Strict Formatting

Adds Arial 8 and standard borders to indexed table/schedule sheets while preserving images, merges, row heights, and column widths.

The tool reports formula errors. It never guesses formulas or technical data.

## Data-loss rules

- Never create a second project merely to relink the workbook.
- Never choose a workbook belonging to a different project.
- Never overwrite both sides silently.
- Never block local app saves because an external workbook is missing or locked.
- Never delete the external workbook when deleting a Singh360 project.
- Never commit customer workbooks or project packages to GitHub.
- Close Excel before writing app changes to the workbook.

## Common questions

### Why does Sync require a decision?

The first link has no trusted baseline. The app cannot know whether the workbook or app manifest is authoritative. The user must choose once.

### Why can the page counts differ?

One workbook sheet may create several continuation pages, and app-only drawing pages may not be ordinary Excel tables.

### Why is an excluded page still visible?

Exclude controls the published drawing set. It does not delete or hide the page from the editor.

### What happens when the workbook is moved?

The app reports Workbook Missing. Use Browse to relocate it. The local project remains safe.

### What happens when Excel is open?

Workbook writes are deferred. The project saves locally and shows Workbook Sync Pending.

## V44 Safe Workbook and Drawing-Page Synchronization

- Use only one authority at a time. Never edit Excel and Singh360 Draft simultaneously.
- `00_INDEX` controls base pages only.
- `00_DRAWING_PAGES` lists every actual drawing page and its physical Excel mirror tab.
- Generated continuation mirror tabs are read-only and are ignored on workbook import.
- All Pages, Included Only, and Not Included must filter the sidebar, bottom tabs, and Previous/Next navigation together.
- See `docs/SINGH360_SAFE_WORKFLOW_V44.md`.
