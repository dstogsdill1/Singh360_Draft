# Project Template Platform

Singh360 Draft schema-V2 projects are created from a registered, customer-neutral workbook template and a committed project profile. Legacy projects remain schema V1 and are not migrated automatically.

## Runtime paths

- Staging input: `.docs/template_staging/Singh360_BASE_Project_Workbook_Template_V1.xlsx`
- Runtime template: `.docs/library/workbook_templates/base/Singh360_BASE_Project_Workbook_Template_V1.xlsx`
- Runtime registry: `.docs/library/workbook_templates/manifest.json`
- Project package: `.docs/projects/<slug>__<project-id>/`
- App-owned workbook document: `data/workbook.json`
- Source manifest: `source_library.json`

The registered template is checksum verified before every new project. It is copied into `sources/workbook`; the registered copy is never edited during project work.

Use Project Home > New Project, choose a profile, enter user-supplied metadata, select an active template, and create. The new 16-character ID and package are created transactionally. Creation failures write `.docs/failure_logs/project_create_*.json` before removing only the incomplete new folder.

Use Sources to retain original inputs, Data to edit the app-owned workbook, Update Drawings to preview and compile generated layers, Drawings for manual canvas work, and SAVE + WRITE EXCEL for the explicit workbook mirror.

Every compile creates a project/workbook backup and page snapshots. Stable page IDs use profile recipe and entity identity. Existing canvas objects, assets, underlays, crops, images, legends, symbols, connectors, annotations, highlights, and page settings are retained; only generated blocks are replaced.

Project backups are stored under the project `backups` folder. Workbook mirror operations back up the prior workbook. A synchronized OneDrive or Google Drive folder may receive a package snapshot through the backup endpoint; that copy is not live editing authority.

V1 does not synthesize one-line diagrams, floor plans, technical conclusions, OCR truth, energy savings, dates, quantities, setpoints, or owners.
