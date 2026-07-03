# Component Library (local & private)

Singh360 Draft ships with a **local, private** component library used by the
Component Library panel in the editor. It is never committed to Git.

## Where it lives

- **Seed (input):** `Singh360_Component_Library_Seed/library/` — the unzipped
  seed you drop into the repo. Gitignored.
- **Active library:** `.docs/library/` — created on first use / seed import.
  Gitignored. Holds `library.json`, `connector_styles.json`, `symbols.json`, and
  `assets/{components,thumbnails,workbook_images,reference_pages}`.

Extracted/reference-derived images (H-E-B / customer media, blueprint crops) stay
local. **Do not commit them.**

## Item states / curation

- **Approved / Candidate** — normal draggable components.
- **Reference Pages** — page-sized blueprint crops (`category: reference-page`).
  Hidden from the default "All" view; still insertable by filtering to that
  category.
- **Retired** — hidden from search (toggle "Show retired" to see them). Kept so
  older projects still resolve. Restore any time.

## Using the panel

- **Import Seed Library** — one click when the library is empty; copies the seed
  into `.docs/library` (the seed folder is never modified/deleted).
- **Search + Category filter** combine; the count reflects the filtered set.
- **Insert / drag** a card onto the active sheet — the full-resolution asset is
  used (thumbnails are only for the card grid), and the object lands on the
  **active page only**.
- **✎ Edit** — rename (`displayName`) and recategorize inline; persists to
  `library.json` via `PATCH /api/library/components/<id>`.
- **Retire / Restore / Delete** — Retire is preferred for seed items. Delete
  requires confirmation, removes only the library entry (keeps the asset file on
  disk), and never touches objects already placed on pages.

## Routes

`GET /api/library`, `POST /api/library/import-seed`,
`GET /api/library/assets/<path>` (path-traversal safe),
`PATCH /api/library/components/<id>`,
`POST /api/library/components/<id>/retire|restore`,
`DELETE /api/library/components/<id>?confirm=1`.

## Keeping customer assets out of Git

`.gitignore` excludes `Singh360_Component_Library_Seed/`, `.reference_inputs/`,
`.docs/`, `*.zip`, `*.pptx`, `*.pdf`, `*.xlsx`. Verify with
`git ls-files Singh360_Component_Library_Seed .docs` (must be empty).

## Taxonomy & auto-categorize (3C)

Canonical categories (see `core/library_taxonomy.py`): Controllers, Expansion
Modules, Panels / Enclosures, Network / Data, Electrical / Power, Sensors /
Transducers, Alarms / Safety, Refrigeration, Lighting, Symbols / Markers,
Legends, Logos, Reference Pages, Unknown / Needs Review.

- **Auto-categorize** buckets components by part number / keyword and, when
  confident (part numbers, logos), sets a canonical name. It updates metadata
  only � it never deletes files. Items it cannot classify go to **Needs Review**.
- **Limitation:** auto-categorize matches on the item *name*. If the seed
  extraction gave a wrong name (e.g. an H-E-B logo saved as "ES Entrapment
  Switch", or a contactor named "PR0650"), it will be bucketed by that wrong
  name. Fix these with the card **? edit** � your edit sets a `curated` flag so
  auto-categorize will never overwrite it again.
- **Inserted labels** use defaultLabel ? shortName ? displayName; off by default
  for logos/symbols/legends/reference pages. Toggle "Insert with label".

## Line styles & selection properties (3C)

- Select a line/connector, then use the **Draw** ribbon tab: Line Color, Line
  Width, Line Style (solid/dashed/dotted/dash-dot), Arrowhead, and presets
  (CAT6 = green solid, Fiber = orange dashed, BACnet = blue dashed, Ref = gray
  dashed). Styles serialize/reload/export.
- Select text, then use the **Text** ribbon tab (Bold/Italic/Underline/size/
  align/color) � disabled with a tooltip when no text is selected.
- The **Selection Properties** panel adapts to the object type (line, text,
  image) and every field has a tooltip.
