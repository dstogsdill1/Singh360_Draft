# Component Builder Workbench

A **standalone, local** workbench for turning real RDM / CPC (Emerson) / Niagara /
H-E-B / Singh360 equipment images into reviewed **black-and-white drawing symbols**
for the Singh360 component library.

> **Boundary:** This workbench does not touch the production app. It never edits
> `server.py`, `frontend/`, or `core/` production modules. It only writes into
> `.docs/component_builder/`. The single exception is `export_approved_symbols.py`,
> which can write into `.docs/library/` **only when run with `--apply`** after human
> approval.

## Pipeline at a glance

```
input images/xlsx/pptx/pdf
        │  inspect_sources.py         (inventory + extract embedded images; read-only on sources)
        ▼
reports/source_inventory.json/.csv
        │  build_inventory.py         (classify by manufacturer/category/part number)
        ▼
approved/manifest_review.csv
        │  make_line_art_candidates.py (grayscale/threshold/edges/silhouette/outline → PNG)
        ▼
work/symbol_candidates/<mfr>/<category>/<id>/*.png
        │  make_contact_sheet.py       (HTML review page, editable decisions)
        ▼
work/contact_sheets/index.html  →  review_decisions.csv  (exported from browser)
        │  export_approved_symbols.py --apply   (ONLY approved items → app library)
        ▼
.docs/library/components/<category>/   +   .docs/library/symbols/<category>/
```

## Folder layout

```
tools/component_builder/            ← these scripts (code)
.docs/component_builder/
  input/                            ← drop your source files here
  work/
    extracted_images/               ← images pulled out of xlsx/pptx (+ rendered PDF pages)
    normalized_sources/             ← reserved for cleaned/normalized copies
    symbol_candidates/<mfr>/<cat>/<id>/*.png
    contact_sheets/index.html
  approved/
    symbols/
    manifest_review.csv             ← the classification manifest you review/edit
  reports/                          ← source_inventory.json/.csv, export_preview.json
```

## Requirements

Already present in this repo's environment:

- **Pillow** (PIL) — required for candidate generation.
- **numpy** — required for silhouette / background removal / high-quality variants.
- **openpyxl** / **python-pptx** — Office extraction (xlsx/pptx embedded media are
  also read directly from the OPC zip, so these are optional).
- **PyMuPDF** (`fitz`) — PDF page counting and optional page rendering.
- **OpenCV** (`opencv-python`) — *optional*; if present it produces cleaner edge /
  adaptive-threshold linework. If absent, a PIL + numpy fallback is used.

Install the optional extra for best line art:

```bash
pip install opencv-python
```

## Step-by-step

### 0. Place your source workbook / images

Copy `Drawimg_Assets.xlsx` (and any PNG/JPG/SVG/PDF/PPTX sources) into:

```
.docs/component_builder/input/
```

On Windows PowerShell, from the repo root:

```powershell
Copy-Item "C:\path\to\Drawimg_Assets.xlsx" ".docs\component_builder\input\"
```

Sources are treated as **read-only** — nothing here modifies or deletes them.

### 1. Inventory sources

```bash
python tools/component_builder/inspect_sources.py
```

- Walks `.docs/component_builder/input/` (or pass `--input <path>`, repeatable).
- Extracts embedded images from xlsx/pptx into `work/extracted_images/`.
- Records SHA256, dimensions, PDF page counts.
- Writes `reports/source_inventory.json` and `.csv`.
- PDF page **rendering** is opt-in: add `--render-pdf [--pdf-dpi 150]`.

### 2. Build the classified manifest

```bash
python tools/component_builder/build_inventory.py
```

- Reads the inventory, classifies each image by filename/path signals, the RDM
  part-number alias table (`rdm_aliases.json`), and taxonomy keywords
  (`component_taxonomy.json`).
- Writes `approved/manifest_review.csv` with:
  `id, displayName, manufacturer, category, partNumber, aliases, sourcePath,
  sourceHash, needsReview, symbolStatus, notes`.
- **Conservative by design:** anything without a confident part-number match is
  left with a provisional name and `needsReview=true`. It never asserts a wrong
  part number with high confidence.

Open `manifest_review.csv`, fix names/categories, and set `symbolStatus=approved`
for the items you want to export later (or approve them in the contact sheet).

### 3. Generate black/white candidate symbols

```bash
python tools/component_builder/make_line_art_candidates.py
```

- For each manifest row, generates variants into
  `work/symbol_candidates/<manufacturer>/<category>/<id>/`:
  `grayscale.png`, `nobg.png`, `threshold.png`, `edges.png`, `silhouette.png`,
  `outline.png`.
- Aspect ratio preserved; longest edge capped by `--max-size` (default 1024).
- Options: `--only <id>`, `--variants edges,outline`, `--replace`.
- Candidates are derived from the **real source pixels**, so they resemble the
  actual equipment — no generic placeholder rectangles.

### 4. Build the review contact sheet

```bash
python tools/component_builder/make_contact_sheet.py
```

- Writes `work/contact_sheets/index.html`. Open it in a browser.
- Each card shows the source image beside its candidates plus metadata, an
  Approve/Reject choice, a selectable "chosen variant", and a notes field.
- Decisions autosave in the browser; click **Export decisions CSV** to download
  `review_decisions.csv` for the export step.

### 5. Export approved symbols (guarded)

Dry run first (safe, default — writes nothing to the library):

```bash
python tools/component_builder/export_approved_symbols.py \
  --decisions .docs/component_builder/work/contact_sheets/review_decisions.csv
```

Then, after you're happy, actually write into the production library:

```bash
python tools/component_builder/export_approved_symbols.py \
  --decisions .docs/component_builder/work/contact_sheets/review_decisions.csv \
  --apply
```

- Copies approved **source** → `.docs/library/components/<category>/`.
- Copies chosen **B/W symbol** → `.docs/library/symbols/<category>/`.
- Writes an export manifest `.docs/library/component_builder_export.json`.
- Never overwrites existing files unless `--replace` is also given.
- Only exports items marked approved (via `symbolStatus=approved` in the manifest
  or `decision=approve` in the decisions CSV).

## Quality / safety rules honored

- Real source images stay as source images; B/W symbols are separate artifacts.
- Thumbnails are never used as final symbols (candidates come from full sources).
- No duplicate component files: destinations are name-based and gated by
  `--replace`.
- No writes into `.docs/library` unless `export_approved_symbols.py --apply`.
- Every destructive / overwrite action requires an explicit flag (`--apply`,
  `--replace`).

## Honest flags

- The RDM alias table encodes only the seed part numbers provided. Unknown parts
  are flagged for human review rather than guessed.
- The library export manifest schema (`component_builder_export.json`) is a
  workbench interchange format. Confirm it against the live app library schema
  before production lock-in.
- True SVG vector tracing is not produced by the PIL/numpy fallback; candidates
  are high-resolution PNG. Add a tracer (e.g. `potrace`) if vector output is
  required.
