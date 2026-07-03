# Page Type Mapping

Reusable rules that map workbook sheet families to canonical page types. These
rules are keyword-based and **not** hardcoded to SA31 — they apply across the
Template, Carthage, and SA38 workbook families.

## Canonical page types

- `cover` — cover / project info / title sheet
- `index` — 00_INDEX / sheet index / drawing list
- `text` — guidelines, scope, responsibilities narrative, field instructions
- `table` — BOM, directory, schedules, lighting schedule, panel schedule
- `matrix` — responsibility matrix, X-mark grids
- `ioSchedule` — I/O points, rack/CCG/DLE I/O, BACnet points
- `idfTable` — IDF tables / network frame assignment
- `rackLayout` — RACKS, rack layout, condenser layout
- `panelDetail` — panel details, pharmacy panel, electrical panel details
- `wiringDiagram` — wiring, one-line, schematic, riser
- `canvas` — layout / location / diagram / drawing pages
- `hybrid` — mixed text/table + canvas/image
- `assetPlaceholder` — image/underlay reference pages with no attached asset

> Note: the runtime `PageModel.pageType` currently uses the base set
> (`cover|index|data-grid|canvas|hybrid|underlay`). The canonical families above
> drive **normalization and rendering** (which block renderer is chosen) and are
> recorded on the page as `pageFamily` for future expansion.

## Keyword rules (case-insensitive, first match wins)

| Family | Keywords |
| --- | --- |
| `cover` | cover, title sheet, project info |
| `index` | index, sheet index, drawing list, sheet list |
| `matrix` | responsibility, responsibilities, resp matrix, matrix |
| `idfTable` | idf, network frame |
| `ioSchedule` | i/o, io schedule, points list, bacnet, ccg, dle, rack i/o |
| `rackLayout` | rack, racks, condenser, ccg layout |
| `panelDetail` | panel, pharmacy panel, panel details, wi-tdb, wi-pr |
| `wiringDiagram` | one-line, oneline, one line, riser, wiring, schematic |
| `table` | bom, bill of materials, schedule, directory, contacts, lighting-tdb, datamanger, data manager |
| `text` | guideline, guidelines, scope, instruction, instructions, notes, workflow, hvac control, existing case control |
| `canvas` | layout, location, diagram, plan, map, overall |

Fallbacks:

- Sparse sheets (≤ 2 content columns) → `text`.
- Dense sheets with X-mark density ≥ 30% and ≥ 4 columns → `matrix`.
- Other dense sheets → `table`.
- Image-reference sheets (mostly filenames) → `assetPlaceholder` / `canvas`.

## Continuation / pagination

When a page's body content does not fit the printable body region, it is split
into generated continuation pages (see `core/page_composer.py`). Continuation
codes are deterministic:

- Simple integer `1` → `1.1`, `1.2`, `1.3`
- Decimal `6.0` → `6.0a`, `6.0b`, `6.0c`
- Engineering `EMS 3.10` → `EMS 3.10a`, `EMS 3.10b`
