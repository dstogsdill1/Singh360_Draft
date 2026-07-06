# Singh360_SmartDraw — Project Board (canonical)

Milestone **4A — Professional EMS Drawing Standard + Clean Component Library V2**.
Update statuses here as work progresses. `In Progress` = actively being built,
`Done` = implemented + smoke-tested, `Backlog` = not started.

## Milestone 4A

| Phase | Item | Status |
| ----- | ---- | ------ |
| 0 | Clean library root `.docs/library/components` + manifest/aliases/connector scaffolding | Done |
| 1 | Component manifest v2 schema (ports, symbolFile, labels) + immediate persistence | Done |
| 2 | Simplified library UI (search / category / All-Favorites-Needs Review / grid-list / add / refresh / rebuild / clean) | Done |
| 3 | Black-and-white SVG symbol generation per category | Done |
| 4 | Drawing style standard + line/connector presets (B&W readable) | Done |
| 5 | Professional page templates (overall layout, one-line, device plan, PDF underlay, schedule) | Done |
| 6 | Crisp PDF import (PyMuPDF, auto-crop, 400–600 DPI, locked underlay) | Done |
| 7 | Data-driven generators (overall layout, component rack/stack, callout schedule) | Done |
| 8 | EMS sheet numbering scheme (EMS 0.0 … 9.x) | Done |
| 9 | Tests + git hygiene | Done |

## Honest flags (carry forward)

- VSDX / Visio visual fidelity is proven only at package level — confirm in a Visio client.
- SmartDraw VSON wire field names remain an integration contract to confirm.
- PDF underlay visual crispness must be eyeballed at 100% + exported 17×11.
- RDM XML dialect must be confirmed against a native Layout Editor sample.

## Milestone 4B — Populate library from legacy + editor hardening

| Phase | Item | Status |
| ----- | ---- | ------ |
| 1 | Migrate legacy `assets/components` into V2 (SHA256-safe, no delete) | Done |
| 2 | Migration button + `scripts/migrate_legacy_library_v2.py` CLI | Done |
| 3 | Bulk B/W symbol generation + Source/Symbol/Both view + insert choices | Done |
| 4 | Thumbnail fixes (SVG path correct, PDF render, clean fallback tile) | Done |
| 5 | Physical duplicate cleanup (archive extras, keep one) | Done |
| 6 | Simplified panel (search incl. filename, migrate/symbols/dedupe buttons) | Done |
| 7 | Insert-with-label grouping (single object, ungroup, persist) | Deferred |
| 8 | Title block no longer shows raw Source File | Done |
| 9 | Created Date stays manual (no auto-update anywhere) | Done (verified) |
| 10 | Page template tooltips/descriptions | Deferred |
| 11 | Line/arrow connector geometry (pointsData sync) | Deferred |
| 12 | Polyline/elbow hardening (single dblclick handler) | Deferred |
| 13 | No baked-in workflow content (blank editable placeholder) | Deferred |
| 14 | Hard no-scroll normalized sheets | Deferred |
| 15 | Wire PDF underlay (`pdf_import_v2`) into the editor canvas | Deferred |
| 16 | Generators minimal UI wiring | Deferred |
| 17 | KANBAN update | Done |
| 18 | Tests | Done (see note) |

### 4B honest flags

- Migration/dedupe/symbols proven on live `.docs`: 60 components, 58 with B/W
  symbols (logos correctly excluded), 0 broken thumbnails, 77 stray physical
  duplicates archived.
- A few items from the earlier ad-hoc migration sit in `custom` (e.g. Alarm
  Strobe Horn); they are searchable and can be re-categorized in the editor
  (persists to `manifest.json`). No `Singh360` component exists in the legacy
  source (firm logo is served from `/static/LOGO-750px.png`).
- `scripts/smoke_component_library.py` (LEGACY `/api/library` store) reports 3
  missing thumbnails for vector-only legacy items (Fan, Valve Open, H-E-B Logo).
  This is the deprecated store and is independent of V2; the V2 smoke suite is
  fully green with no broken thumbnails.
- Phases 7, 10–16 (deep editor: connectors, polylines, PDF underlay wiring,
  generator UI, workflow placeholder, no-scroll, insert grouping, template
  tooltips) are NOT done this pass — deferred, not faked.

## Milestone 4C — Phase Zero runtime cleanup

| Phase | Item | Status |
| ----- | ---- | ------ |
| A | Runtime inspect script (`inspect_runtime_workspace.py`) | Done |
| B | Minimal `.docs` self-heal on startup + cleanup script | Done |
| C | Fake generated symbol cleanup script + manifest clear | Done |
| D | Legacy runtime folder consolidator (dry-run + apply archive move) | Done |
| E | Active roots locked (`components`, `symbols`, `thumbnails`) | Done |
| F | Simplified normal library panel (no fake symbol generation) | Done |
| G | Runtime docs (`docs/COMPONENT_LIBRARY_RUNTIME.md`) | Done |
| H | KANBAN update | Done |
| I | Required tests | In Progress |

### 4C honest flags

- This pass intentionally **does not build real equipment symbols**. Symbol
  creation is deferred to a future Component Builder workflow.
- Existing fake `*.symbol.svg` files are archived and unlinked from manifest.
- Deep editor hardening (connectors/polyline/no-scroll/pdf underlay wiring)
  remains out of scope for this phase-zero cleanup pass.

## Milestone 4D — Component Library UX: Source / Edge / B&W only

| Phase | Item | Status |
| ----- | ---- | ------ |
| 1 | Representation contract (`sourceUrl`, `edgeUrl`, `bwUrl`, `thumbnailUrl`, flags, search terms) | Done |
| 2 | Approved export first + hide stale legacy by default | Done |
| 3 | Normal panel simplified (Search, Category, Source/Edge/B&W, Open Builder, Refresh, cards) | Done |
| 4 | Open Component Builder modal (Components + Advanced) | Done |
| 5 | Edge-first defaults + clean label priority | Done |
| 6 | Smoke coverage updates | Done |

## Milestone 3E — Save hardening + connector routing tools

| Phase | Item | Status |
| ----- | ---- | ------ |
| 0 | Audit + `docs/BUGLIST_CONNECTORS_SAVE.md` | Done |
| A | Trustworthy save (Unsaved/Saving/Saved/Failed) + flush + beforeunload | Done |
| A | Server backups before overwrite (keep 20) + list/restore API | Done |
| A | Local recovery snapshots (localStorage, keep 10) | Done |
| B | Connector model extended (stylePreset/wireNumber/labels/layer); pointsData authoritative | Done |
| C | Easier connectors: bigger hit band, Alt-drag duplicate, 12px offset | Done |
| D | Polyline + elbow tools (orthogonal), live preview, Esc/Enter/Backspace | Done |
| F | Bus / Harness (minimal parallel wires + labels + preset) | Done (minimal) |
| G | Connector style presets (B&W-safe) | Done (verified) |
| I | Shortcuts L/P/E/B + drawing hint in status bar | Done |
| K | Backups / recovery modal | Done |
| L | `smoke_connectors.py` + smoke updates | Done |
| M | `docs/VISUAL_QA.md` connector QA | Done |
| E | Component ports / terminal-row pin snapping | Deferred (honest) |
| F | Trunk + branch bus with fan-out | Deferred (honest) |
| H | Per-region double-click label editing | Deferred (honest) |

### 3E honest flags

- Save/backup/recovery + connector persistence are proven by `smoke_connectors.py`
  and `smoke_editor_browser.py` (Flask test client). Fabric-side UX (drag, snap,
  Alt-drag, bus placement) is not driven by CI — verify via `docs/VISUAL_QA.md`.
- Ports (E), trunk/branch bus (F "better"), and per-region label editing (H) are
  deferred, not faked.
