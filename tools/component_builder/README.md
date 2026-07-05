# Component Builder Workbench

Turn the curated **Singh360 Component Master** (an editable Excel workbook + a
`sources/` image folder) into black-and-white drawing-symbol candidates, review
them on a contact sheet, and later export the approved ones.

The master package is the source of truth and lives **inside the workbench**:

```
.docs/component_builder/master/
  Singh360_Component_Master_Catalog.xlsx   <- the editable master (edit this)
  Singh360_Component_Master_Catalog.csv    <- generated from the xlsx
  Singh360_Component_Master_Catalog.html   <- readable catalog
  sources/<category>/<image>               <- the real component images
  thumbs/<category>/<image>                <- thumbnails (reference only)
```

> The production app library at `.docs/library/` is **output only**. Nothing in
> the normal workflow reads from or writes to it. It is touched only when you
> explicitly run `export_approved_symbols.py --apply-production`.

---

## Do this (the one command)

```bash
python tools/component_builder/run_master_pipeline.py --open
```

That single command will:

1. make sure the workbench folders exist,
2. sync the Excel workbook to CSV if the workbook is newer,
3. build the review manifest from the master CSV,
4. generate B/W symbol candidates from `sources/`,
5. build the review contact sheet, and
6. open it in your browser (`--open`).

Then just review the contact sheet.

### Normal workflow

1. **Edit** `.docs/component_builder/master/Singh360_Component_Master_Catalog.xlsx`
   (add rows, fix display names / categories, drop images into `sources/<category>/`).
2. **Run** `python tools/component_builder/run_master_pipeline.py --open`.
3. **Review** the contact sheet that opens.
4. On the contact sheet, approve/reject each item, pick the best variant, then
   click **Export decisions CSV**.
5. **Dry-run** the export (writes nothing):
   ```bash
   python tools/component_builder/export_approved_symbols.py --decisions <downloaded>.csv
   ```
6. **Stage** approved items into the safe staging area (does NOT touch the app
   library) once you're happy:
   ```bash
   python tools/component_builder/export_approved_symbols.py --decisions <downloaded>.csv --staging
   ```

Production export happens later, only when explicitly approved (see below).

### Pipeline options

| Flag | Effect |
| --- | --- |
| `--open` | Open the contact sheet when done |
| `--sync-excel` | Force an Excel→CSV sync |
| `--skip-sync` | Never sync (use the CSV as-is) |
| `--replace-candidates` | Regenerate candidate PNGs even if they exist |
| `--manifest <path>` | Use a different master CSV |
| `--source-root <path>` | Use a different sources root |

---

## Excel is the master, CSV is derived

The Excel workbook is what you (and anyone you share it with) edit. The CSV is
regenerated from it:

```bash
python tools/component_builder/sync_master_excel.py [--replace]
```

- Reads the `Component_Master` sheet.
- Uses your `displayName`, `category`, `manufacturer`, `templateType` as typed.
- Blank category → a few keyword rules fill a best guess **and** set
  `needsReview=TRUE`.
- Pasted workbook images are extracted into `sources/<category>/` where present;
  existing curated files are preserved (never overwritten unless `--replace`).
- Part numbers are never invented.
- A row with no usable image is kept but flagged `needsReview=TRUE`, unless its
  `templateType` is specific enough to draw procedurally.

`run_master_pipeline.py` calls this automatically when the workbook is newer than
the CSV, so you normally don't run it by hand.

---

## Export: staging first, production later

`export_approved_symbols.py` has three safety levels:

| Mode | Command | Writes to |
| --- | --- | --- |
| Dry run (default) | `... --decisions d.csv` | nothing (preview JSON only) |
| **Staging (recommended)** | `... --decisions d.csv --staging` | `.docs/component_builder/export_ready/` |
| Production | `... --decisions d.csv --apply-production` | `.docs/library/` |

- Only rows marked **approve** (in the decisions CSV) or `symbolStatus=approved`
  are exported.
- Existing destination files are never overwritten unless `--replace` is added.
- `--apply` is a legacy alias for `--apply-production`.

Staging output:

```
.docs/component_builder/export_ready/
  components/<category>/<source image>
  symbols/<category>/<chosen B/W symbol>
  manifest.json
```

**Do not export to production until the components are approved.**

---

## Sharing with another person (no Git required)

1. Send them `Singh360_Component_Master_Catalog.xlsx` (and the `sources/` folder
   if they need to see or add images).
2. They edit display names / categories / images and paste new images into the
   workbook or drop files into `sources/<category>/`.
3. They send the workbook (and `sources/`) back.
4. Drop them into `.docs/component_builder/master/`.
5. Run `python tools/component_builder/sync_master_excel.py` to rebuild the CSV.
6. Run `python tools/component_builder/run_master_pipeline.py --open` to review.

---

## Contact sheet

`.docs/component_builder/work/contact_sheets/index.html` shows, per item:
source image, display name, category, manufacturer, part number (if provided),
the B/W candidate variants, an approve/reject choice, a chosen-variant picker,
and a notes field. A per-category count summary is shown at the top.

If a source looks like a full drawing sheet rather than a single component, the
card shows: **"Reference/full drawing detected — do not approve as component."**

Decisions autosave in the browser; **Export decisions CSV** downloads the file
the export step consumes.

---

## Advanced: `inspect_sources.py`

`inspect_sources.py` is **not** part of the normal master workflow. It only
exists for pulling images out of arbitrary files (folders, PDFs, xlsx/pptx) when
you need to build a source set from scratch. The master workflow already has
curated sources, so you should not need it.

---

## Requirements

- **Pillow**, **numpy** — candidate generation (required).
- **openpyxl** — reading the master Excel workbook (required for sync).
- **PyMuPDF** — only used by the advanced `inspect_sources.py`.
- **OpenCV** (`opencv-python`) — *optional*; sharpens `edges`/`lineart`. A
  PIL+numpy fallback is used when it is absent.

## Honest flags

- The staging `manifest.json` / production `component_builder_export.json` is a
  workbench interchange format — confirm it against the live app library schema
  before production lock-in.
- Candidates are high-resolution PNG; true SVG vector tracing is not produced by
  the fallback pipeline (add a tracer such as `potrace` if you need vectors).
