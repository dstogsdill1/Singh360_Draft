# Singh360_SmartDraw

Deterministic MEP/R **diagram generator**. It ingests the structured
engineering data produced upstream by **Singh360_Parser** (plus control and
network matrices and optional Azure Document Intelligence floor‑plan polygons)
and renders production diagrams for **SmartDraw** (VisualScript / VSON),
**Microsoft Visio** (native `.vsdx`), and a neutral **RDM Layout XML** package
(`.rdm.xml`).

> Operating standard (shared with Singh360_Parser): deterministic first, no
> hallucinated values, full traceability, code‑only repo. Unknowns are left
> blank and **flagged** — never invented.

---

## 1. What it does

```text
 Singh360_Parser (upstream)            Singh360_SmartDraw (this tool)
 ───────────────────────────          ──────────────────────────────────────────
 Azure DI prebuilt-layout  ─┐
   *_DI_tables.csv          │  spatial  ┌─ core/ingestion.py ──────────────┐
 (8-pt bounding polygons) ──┼─ overlay ─┤  polygon → (cx,cy,w,h) normalize │
                            │           └──────────────────────────────────┘
 assets.csv (11-col app) ───┤  joins    ┌─ core/data_orchestrator.py ──────┐
 control_matrix.csv  ───────┼──────────►│  pandas → DiagramGraph           │
 network.csv  ──────────────┘           │  nodes + hierarchy/control/net   │
                                        └──────────────┬───────────────────┘
                                                       │
                            ┌──────────────────────────┴───────────────────┐
                            ▼                                               ▼
                 engines/smartdraw_vson.py                      engines/visio_vsdx.py
                 VS.Document / Shape / Connector                OPC ZIP + XML ShapeSheet
                 auto-layout, TextGrow, data[]                  PinX/PinY, glued Connects
                            │                                               │
                            └───────────────────────┬───────────────────────┘
                                        ▼
                                  engines/rdm_layout_xml.py
                                  neutral XML package + provenance
                                        │
                           ┌──────────────────────────┴──────────────────────────┐
                           ▼                                                     ▼
                    <name>.vson                                       <name>.vsdx
                           +
                         <name>.rdm.xml
```

### The relational model (grounded, not guessed)

Every diagram node comes from a real upstream row, and **edges come from the
data itself**:

| Source | Becomes | Edge kind |
| --- | --- | --- |
| `assets.csv` row (`Name`) | a shape node | — |
| `Connected/Area Served/...` column | edge **child → parent** when it names another `Name` (Circuit→Loop, Compressor→Loop, Condenser→Rack, Fixture→Panel) | `hierarchy` (solid) |
| `control_matrix.csv` | `Relay → Contactor → Load`; the `Load` stitches into the asset graph when it matches an asset `Name` | `control` (dashed) |
| `network.csv` | `Device → Switch` (`Port`/`IP`/`VLAN` carried as data); `Device` inherits asset location on name match | `network` (dotted) |

A value in the `Connected/...` column that is **not** another node (e.g. a
refrigerant code `R404A`, an area string, or a rack count) is kept as a shape
attribute and counted — it is **never** turned into a phantom node.

---

## 2. Module map

```text
Singh360_SmartDraw/
├── __init__.py
├── config.py                 # env, units, category→style map, app schema
├── core/
│   ├── ingestion.py          # Azure DI layout + polygon normalization + grid rebuild
│   ├── idf_builder.py        # deterministic IDF rules: rack drops, case naming, WICP groups
│   └── data_orchestrator.py  # pandas joins → DiagramGraph + deterministic layout
├── engines/
│   ├── smartdraw_vson.py     # VS.Document/Shape/Connector/Container compiler
│   ├── visio_vsdx.py         # stdlib OPC/XML .vsdx writer (+ .vssx master hook)
│   ├── rdm_layout_xml.py     # deterministic neutral RDM-style XML package writer
│   └── drawing_package.py    # copy-paste-ready HTML component package (build by hand)
├── main_generator.py         # CLI entry point + traceability report
├── server.py                 # Flask bridge: web GUI <-> main_generator.py
├── web/
│   └── index.html            # live browser GUI (upload -> generate -> download)
└── sample_data/              # synthetic demo inputs (NOT customer data)
    ├── assets.csv
    ├── control_matrix.csv
    └── network.csv
```

---

## 3. Quick start

```powershell
# from the Singh360_SmartDraw folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # pandas is the only hard requirement

python main_generator.py `
    --assets sample_data/assets.csv `
    --control sample_data/control_matrix.csv `
    --network sample_data/network.csv `
  --name "HEB SA31 Demo" --out-dir output --targets vson,vsdx,rdmxml,package
```

Outputs land in `output/`:

- `HEB_SA31_Demo.vson` — import into SmartDraw (VisualScript). The extension
  **must** be `.vson` (SmartDraw also accepts `.sdon`/`.sdr`); it follows the
  official VSON Markup Language Reference (root `Shape` tree + `Returns`).
- `HEB_SA31_Demo.vsdx` — open in Microsoft Visio.
- `HEB_SA31_Demo.rdm.xml` — neutral RDM-oriented XML package with deterministic
  node/edge ordering, coordinates, provenance, and symbol-library hints.
- `HEB_SA31_Demo_package.html` — copy-paste-ready **drawing package** (see §4):
  every component in clean tables to assemble the drawing yourself.

The CLI prints a graph summary, a coordinate→shape flow legend, per‑target
**validation** results, and any flags.

### Raw schedule workbook (SA#31-style `.xlsx`)

Skip hand-building CSVs — point the CLI at a raw MEP light-fixture/contactor
workbook and `core/schedule_adapter.py` maps it to the canonical schema by
**header text** (so layout shifts don't break it):

```powershell
python main_generator.py `
    --schedule-xlsx "LIGHT FIXTURE SCHEDULE - SA #31.xlsx" `
    --name "HEB SA31 Lighting" --out-dir output/SA31 --targets vson,vsdx
```

- `SCHEDULE STORE` sheet → Lighting fixture nodes (TYPE → Name; QTY/VOLTAGE/
  WATTAGE/MANUFACTURER/DESCRIPTION carried as node data; Interior/Exterior
  inferred from the description).
- `CONTACTORS` sheet → `Relay → Contactor → Load` control chain
  (`CONTROLLED CIRCUIT(S)` → Panel reference).
- Empty Excel cells become **blank**, never the literal `nan`. Canonical CSVs
  are written to `<out-dir>/_canonical/` (gitignored — they hold customer data).

### Spatial overlay (optional)

```powershell
# Deterministic, offline — reuse a parser-produced DI tables CSV:
python main_generator.py --assets sample_data/assets.csv `
    --di-tables ..\Singh360_Parser\output_data\Waldorf904\R2-1_..._DI_tables.csv

# Live — call Azure DI on a floor plan (needs .env creds + azure/PyMuPDF):
python main_generator.py --assets sample_data/assets.csv --pdf plan.pdf --pages 3-4
```

#### Lighting plan → true X/Y (vector PDFs)

`core/extractors/lighting_plan.py` reads a vector **lighting / EMS controls
plan** PDF (e.g. `109 E-1.0 ELEC LIGHTING EMS CONTROLS PLAN.pdf`, drawn 1:1 to
Arch D), pulls every **LCP** zone marker (`LCP-1…LCP-n`) and fixture-type tag
(`B1`, `T10`, `UL924`…) with its coordinate, and fits that true bounding box onto
the 42×30 canvas (Y-flipped to a bottom-left origin). It emits one PANEL per LCP
at the centroid of its markers, one LIGHTING zone per marker at its real X/Y, and
one LIGHTING node per fixture type — each stamped with `attrs["x"]/["y"]` so
`floorplan_layout` → `spatial_layout` place them at **absolute PinX/PinY** on the
sheet (the SA-31 spatial overlay). The `pipeline_cli.py` floorplan sheet picks
these anchors up automatically:

```powershell
python pipeline_cli.py "<raw HEB project folder>" --name "HEB 109 Bunker Hills" `
    --out output/bh109 --sheets io_schedule,floorplan_layout --canvas archd
```

### IDF setup rules (`core/idf_builder.py`)

Step one of IDF (network frame) setup — gather + normalize the equipment
schedule, circuit schedule, and refrigeration controls notes into structured,
correctly-named records before assigning them to an IDF. The rules come
verbatim from the draftsman email in
`sample_data/Singh360 Inc Mail - Visual studios IDF information.pdf` and are
verified by a self-test (`python core/idf_builder.py`):

- **Racks (equipment schedule).** Each rack gets **2 drops** — one for the
  SuperPAC and one for the **loop** or **cascade** controller. CO2 cascade
  racks → cascade controller; everything else → loop controller
  (`rack_drops(...)`).
- **Cases (circuit schedule).** The IDF case name strips the 2-letter product
  designator from the full circuit name: `RADA01 → RA01`, `RABK02a → RA02`,
  sorted alphanumerically by rack + circuit (`parse_circuit_name`,
  `circuit_sort_key`). Multiple cases on one lineup get `a/b/c`
  (`RA01a/RA01b/RA01c`); `Q3-SP` / `Q3-MV` cases carry two coils named with two
  trailing letters (`RA01aa`, `RA01ab`) — all from `build_lineup_cases(...)`.
- **Case description** = full circuit name + case type + temperature + product,
  e.g. `RADA01a MD Fresh Dairy` (`MD`=Multideck, `WI`=Wide-Island,
  `RI`=Reach-in; `Service`/`2-deck`/`3-deck` stay as written; temp = Fresh or
  Frozen; product expands the designator — `DA`=Dairy, `BK`=Bakery).
- **WICP (controls general notes).** Walk-In Control Panels are grouped one
  group per panel (`group_wicps_by_panel(...)`).

Unknown product designators expand to blank and are flagged for confirmation —
never guessed (no-hallucination rule). The module is the deterministic data
layer only; wiring a live equipment/circuit workbook through it needs the real
schedule column map (a follow-up once the source `.xlsx` is supplied).

---

## 3b. Web GUI (App Central bridge)

A browser front end ([web/index.html](web/index.html)) drives the same pipeline
without the command line, and is the destination of the **SmartDraw** card in the
Singh360 Dashboard "App Central" hub.

```powershell
# from the Singh360_SmartDraw folder (after pip install -r requirements.txt)
python server.py
# -> Singh360 SmartDraw bridge -> http://localhost:8765
```

Open `http://localhost:8765`, then:

1. Enter a **Project Name**.
2. Drop or browse `assets.csv` (required) plus optional `control_matrix.csv`,
   `network.csv`, and a blueprint **PDF** (with a page range for Azure DI).
3. Toggle the **target outputs** (`.vson`, `.vsdx`, `.rdm.xml`).
4. Click **Generate Diagrams** — a spinner runs while the Flask bridge executes
   `main_generator.py`, then the results panel lists each file with individual
   downloads, a **Download all (.zip)**, the pipeline report, and any flags.

### How the bridge works

```text
web/index.html  --FormData(POST /api/generate)-->  server.py (Flask)
     ^                                                  |
     |  JSON {files[], zipHref, report, flags}          | subprocess (exact CLI)
     |                                                  v
  download <--- /api/download/<job>/<file>  <---  main_generator.py -> .jobs/<id>/output
```

- Each request gets an isolated sandbox under `.jobs/<uuid>/` (gitignored).
  Uploads are saved with fixed names (`assets.csv`, `control_matrix.csv`,
  `network.csv`, `blueprint.pdf`) so the CLI arguments are deterministic.
- The bridge reuses the **exact** `main_generator.py` CLI contract via
  `subprocess`, so a generation crash can never take the server down, and the
  captured report/flags are surfaced verbatim in the UI.
- Downloads are path‑traversal safe: the job id must be a 32‑char hex and the
  resolved file must stay inside that job's `output/` directory.
- ZIP packaging uses the standard library (`zipfile`) — no extra dependency.

> **Endpoints:** `GET /` (GUI) · `GET /health` · `POST /api/generate` ·
> `GET /api/download/<job>/<file>` · `GET /api/download/<job>.zip`. The server
> binds `127.0.0.1:8765` (local only).

---

## 4. Output formats

### Drawing package — copy-paste HTML (`engines/drawing_package.py`)

The **build-it-yourself** target. Rather than emit a finished diagram, it
consolidates *every* component of a project into one self-contained HTML
**drawing package** you open in a browser and copy from — straight into
**SmartDraw** or **Microsoft Visio** — then lay out the drawing by hand with all
the data already gathered, named, and grouped.

```powershell
python main_generator.py --assets sample_data/assets.csv `
    --control sample_data/control_matrix.csv --network sample_data/network.csv `
    --name "HEB SA31 Demo" --out-dir output --targets package
```

Tabs in the package:

- **Overview** — component counts by category/group + connection counts.
- **Components** — one table per group (Refrigeration, EMS Control, Lighting,
  Network…) listing every node with its attributes (fixture/make, control,
  panel/circuit, voltage, set point, area, IP/switch/port…) and source row.
- **Connections** — the full relationship list (hierarchy / control / network).
- **Build List** — a flat, printable bill of materials with tick boxes.
- **Flags & Sources** — validation flags + source-file provenance.

Every table is a real `<table>` (drag-select straight into Visio/Excel) **and**
wired to **Copy (TSV)** (clipboard, tab-separated for instant paste) and
**Download CSV** (for Visio *Data → Link Data to Shapes* / SmartDraw import).
Deterministic and no-hallucination: it renders only what the schedules provide;
blank cells mean a value was not supplied. `drawing_package.validate()` confirms
the HTML structure. Accepts `--targets package` (aliases `html`, `drawingpkg`).

### SmartDraw VSON (`engines/smartdraw_vson.py`)

Emits the **official VSON document** from SmartDraw's
[VisualScript Markup Language Reference](https://www.smartdraw.com/developers/visualscript-markup-language-reference.htm):
a single root object `{ "Version", "Template", "Title", "Shape", "Returns" }`.
The diagram is a **tree** — one root `Shape` whose children hang off
`ShapeConnector` arrays, recursively — so SmartDraw's intelligent‑formatting
engine lays everything out with **no coordinates**. Fields follow the published
reference exactly (`Label`, `ShapeType`, `FillColor`, `LineColor`,
`LinePattern`, `TextGrow:"Proportional"`). Relationships that don't fit the
spanning tree become `Returns` (lines by `StartID`/`EndID`); per‑node specs go
in `Note`. The file is written with the **`.vson`** extension that SmartDraw's
importer requires.

> **Confirmed against the spec (June 2026):** the structure follows the
> official VSON reference. `smartdraw_vson.validate()` proves the `Shape` tree
> has unique positive IDs and that every `Return` resolves. Final visual
> rendering should still be confirmed by importing once into your SmartDraw
> account (Import → SmartDraw → choose the `.vson`).

### Visio VSDX (`engines/visio_vsdx.py`)

A real Open Packaging Conventions container built with the standard library
only, following the Microsoft `.vsdx` schema: `[Content_Types].xml`,
`_rels/.rels`, `docProps/*`, `visio/document.xml`, `visio/pages/pages.xml`,
`visio/pages/page1.xml` and their `.rels`. Nodes carry real ShapeSheet cells
(`PinX`/`PinY`/`Width`/`Height` + rectangle `Geometry`); connectors are 1‑D
line shapes **glued** with `<Connect>` rows (`FromPart` 9=begin / 12=end →
`ToPart` 3=whole shape). Exact colors are written as `RGB()` formulas so they
survive independent of the document color table.

`visio_vsdx.validate_vsdx()` is a deterministic structural proof: it re‑opens
the zip, confirms every required part exists, parses **every** XML part, and
resolves **every** relationship target inside the package.

> **Flag:** Fidelity is proven at the package/OPC level here. Final visual
> fidelity should be confirmed by opening once in a Visio client (this
> environment has no Visio runtime). `.vssx` corporate stencils can be
> enumerated via `MasterLibrary`; with none supplied the writer uses inline
> rectangle geometry (flagged in the run report).

### RDM Layout XML (`engines/rdm_layout_xml.py`)

Emits a deterministic, neutral XML package from `DiagramGraph` suitable for
Layout-Editor-oriented interchange when an official vendor schema is not
available in the installed binaries. The file contains:

- `Metadata` (document name, UTC generation time, page size, coordinate units)
- `LibraryHints` (paths discovered from the local RDM image libraries)
- `Nodes` (id/label/category/unit/group/source + `x/y/w/h` in inches)
- `Attributes` (all node data key/value pairs)
- `Edges` (source/target/kind/label/source_ref)
- `Flags` (run-time notes carried forward)

`rdm_layout_xml.validate()` checks parseability, root tag, node ID uniqueness,
and edge endpoint integrity.

> **Flag:** This is a neutral deterministic contract, not a vendor-certified
> final import dialect. Lock exact tag/attribute names against official RDM
> docs or a native Layout Editor project sample before production rollout.

---

## 5. Data contracts

- **assets.csv** — exact 11‑column Singh360 bulk‑upload header (see
  `config.APP_COLUMNS`).
- **control_matrix.csv** — `Relay, Contactor, Load, Panel, Voltage, Area`.
- **network.csv** — `Device, Switch, Port, IP, VLAN`.

`sample_data/` contains synthetic values only. Real customer plans/exports stay
out of the repo (`.gitignore`).
