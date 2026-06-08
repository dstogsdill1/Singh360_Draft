# Singh360_SmartDraw

Deterministic MEP/R **diagram generator**. It ingests the structured
engineering data produced upstream by **Singh360_Parser** (plus control and
network matrices and optional Azure Document Intelligence floor‑plan polygons)
and renders production diagrams for **SmartDraw** (VisualScript / VSON) and
**Microsoft Visio** (native `.vsdx`).

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
                            ▼                                               ▼
                    <name>.vson                                       <name>.vsdx
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
│   └── data_orchestrator.py  # pandas joins → DiagramGraph + deterministic layout
├── engines/
│   ├── smartdraw_vson.py     # VS.Document/Shape/Connector/Container compiler
│   └── visio_vsdx.py         # stdlib OPC/XML .vsdx writer (+ .vssx master hook)
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
    --name "HEB SA31 Demo" --out-dir output --targets vson,vsdx
```

Outputs land in `output/`:

- `HEB_SA31_Demo.vson` — import into SmartDraw (VisualScript). The extension
  **must** be `.vson` (SmartDraw also accepts `.sdon`/`.sdr`); it follows the
  official VSON Markup Language Reference (root `Shape` tree + `Returns`).
- `HEB_SA31_Demo.vsdx` — open in Microsoft Visio.

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
3. Toggle the **target outputs** (`.vson`, `.vsdx`).
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

---

## 5. Data contracts

- **assets.csv** — exact 11‑column Singh360 bulk‑upload header (see
  `config.APP_COLUMNS`).
- **control_matrix.csv** — `Relay, Contactor, Load, Panel, Voltage, Area`.
- **network.csv** — `Device, Switch, Port, IP, VLAN`.

`sample_data/` contains synthetic values only. Real customer plans/exports stay
out of the repo (`.gitignore`).
