# Reference Inputs (local-only, never committed)

These reference files are development targets and import test inputs. They contain
customer data and **must never be committed** (they are covered by `.gitignore`).
Place them anywhere locally and point the inspector / smoke scripts at them with
environment variables.

## Files and what they are used for

| Env var | File | Used for |
| --- | --- | --- |
| `SINGH360_REF_SA31_PDF` | `HEB_SA31(102)_EMS_Lighting_Drawing_version1.pdf` | Visual target: cover, location page, directory, scope/instructions, workflow, responsibility matrix, BOM, lighting matrix, one-line/layout/image pages, company info. |
| `SINGH360_REF_SA38_PDF` | `HEB 195 - San Antonio 38 - RDM Conversion - Version 1.pdf` | Visual target: issued EMS packages — cover/index, responsibility matrix, BOM, RDM one-line, device locations, IDF tables, rack/CCG/DLE I/O pages, data manager, lighting schedule. |
| `SINGH360_TEMPLATE_WORKBOOK` | `Template H-E-B CAD Worksheet - Master.xlsx` | Canonical worksheet/template families (page-type mapping source). |
| `SINGH360_CARTHAGE_WORKBOOK` | `458 Carthage CAD Worksheet - Master.xlsx` | Older/alternate workbook structure. |
| `SINGH360_KATY_CSV` | `HEB 797 Katy Park CSV File.csv` | Equipment inventory / CSV source-data import test. |
| `SINGH360_SA31_WORKBOOK` | `Copy of Singh360 Drawing Workbook_HEB_102_SA-31 (1).xlsx` | Current workbook-driven package test. |

## How to use locally (Windows PowerShell)

```powershell
$env:SINGH360_SA31_WORKBOOK = "C:\path\to\Copy of Singh360 Drawing Workbook_HEB_102_SA-31 (1).xlsx"
$env:SINGH360_KATY_CSV      = "C:\path\to\HEB 797 Katy Park CSV File.csv"
$env:SINGH360_TEMPLATE_WORKBOOK = "C:\path\to\Template H-E-B CAD Worksheet - Master.xlsx"

python scripts/inspect_reference_inputs.py
```

The inspector never fails on missing files — it warns and skips.

## Storage rules

- Do **not** copy these into the repo.
- Generated exports/screenshots go under `output/` or `.docs/` (both gitignored).
- Only code, config, and docs are committed.
