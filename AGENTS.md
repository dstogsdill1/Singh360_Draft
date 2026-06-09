# AGENTS.md — Singh360_SmartDraw Operating Instructions

This file defines how any coding agent should operate in this repository.

## Mission

Render Singh360 MEP/R assets into production diagrams for **SmartDraw**
(VisualScript / VSON), **Microsoft Visio** (native `.vsdx`), and a neutral
**RDM Layout XML** package (`.rdm.xml`) — deterministically, traceably, with
zero hallucinated values.

## Non-negotiables

1. **No hallucination**: if a value is unclear, leave it blank and flag it. Never
   invent nodes, edges, coordinates, or vendor field names.
2. **Deterministic first**: CSV / vector parsing before any OCR. The Azure DI path
   is optional and lazily imported.
3. **Traceability**: every node/edge carries a `source` provenance (`file:row`).
4. **Code-only repo**: never commit customer drawings, exports, or secrets.

## Architecture (keep these boundaries)

- `config.py` — env, units, `CATEGORY_STYLES`, the 11-column app schema.
- `core/ingestion.py` — Azure DI layout + 8-pt polygon normalization + grid rebuild
  (reuses the upstream parser `grid=[['']*(maxc+1) ...]` reconstruction).
- `core/schedule_adapter.py` — converts a raw MEP schedule workbook (SA#31-style
  `.xlsx`: SCHEDULE STORE + CONTACTORS sheets) into canonical `assets.csv` +
  `control_matrix.csv` by HEADER TEXT (not fixed columns). Empty Excel cells map to
  blank, never the literal `nan`. Used by `main_generator --schedule-xlsx`.
- `core/data_orchestrator.py` — pandas joins → `DiagramGraph` (Node/Edge) +
  `compute_layout`. The `Connected/Area Served/...` column is a parent edge ONLY
  when it names another node; otherwise it stays an attribute (never a phantom node).
- `engines/smartdraw_vson.py` — `VS.Document/Shape/Connector/Container`, `TextGrow`,
  embedded `data[]`, `meta.traceability`.
- `engines/visio_vsdx.py` — stdlib `zipfile` + `ElementTree` OPC writer; real
  ShapeSheet cells (`PinX/PinY`), glued `<Connect>` rows, `RGB()` color formulas.
- `engines/rdm_layout_xml.py` — deterministic neutral RDM-oriented XML package
  writer from `DiagramGraph` + `compute_layout`; includes source traceability and
  structural validator.
- `main_generator.py` — the CLI control surface + traceability report. This is the
  **public contract** the web bridge depends on; do not break its flags/exit codes.
- `server.py` — Flask bridge for `web/index.html`. Runs `main_generator.py` via
  `subprocess` (never re-implements the pipeline). Serves the GUI + JSON API.
- `web/index.html` — single-file browser GUI (upload → generate → download).

## Web bridge rules

- The bridge must reuse the **exact** `main_generator.py` CLI contract via
  subprocess. Do not duplicate generation logic in `server.py`.
- Per-request work goes in `.jobs/<uuid>/` (gitignored). Save uploads with fixed
  names so CLI arguments stay deterministic.
- Keep downloads path-traversal safe (validate job id = 32-hex; resolved file must
  stay inside the job `output/`).
- Server binds `127.0.0.1` only. Do not expose it on `0.0.0.0` without a reason.
- ZIP packaging stays on the standard library (`zipfile`) — no new dependency.

## Validation expectations

- `python main_generator.py --assets sample_data/assets.csv --control
  sample_data/control_matrix.csv --network sample_data/network.csv --name "Demo"`
  must exit 0 and write valid `.vson` + `.vsdx` + `.rdm.xml` when requested.
- `smartdraw_vson.validate()`, `visio_vsdx.validate_vsdx()`, and
  `rdm_layout_xml.validate()` must pass for their respective targets.
- If you touch the bridge, smoke-test `python server.py` + a `POST /api/generate`
  with the sample data and confirm a ZIP downloads (including `.rdm.xml` when
  selected).

## Honest flags (carry these forward)

- SmartDraw's public VisualScript JSON spec page was unreachable at build time —
  VSON wire field names are an **integration contract to confirm** against the live
  SmartDraw import endpoint, not a vendor-published guarantee.
- VSDX fidelity is proven at the OPC/package level only (no Visio runtime in CI).
  Open once in a Visio client to confirm visual rendering.
- RDM target currently emits a neutral XML contract for deterministic interchange.
  Exact vendor import dialect must be confirmed against official docs or a native
  Layout Editor project sample before production lock-in.

## Commit policy

- Stage only code/config/docs: `*.py`, `web/`, `sample_data/`, `requirements.txt`,
  `.gitignore`, `README.md`, `AGENTS.md`.
- Never stage `output/`, `.jobs/`, `.env`, customer PDFs/stencils, or generated
  `*.vsdx` / `*.vson` / `*.rdm.xml`.
