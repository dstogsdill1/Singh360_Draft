# Symbol Legend Builder + Library Label Cleanup — Report

Date: 2026-07-11

## Summary

Added editable **Symbol Legend** insert (grouped Fabric objects with icons + editable labels), legend template storage, and a library label cleanup script. Connector Legend unchanged.

---

## Phase A — Component library label cleanup

**Script:** `scripts/clean_component_library_labels.py`

**Primary targets cleaned:**
| File | Labels cleaned | Duplicates removed | Remaining |
|------|----------------|-------------------|-----------|
| `component_builder_export.json` | 35 | 17 | 187 |
| `manifest.json` | 345 | 112 | 252 |

**Backup:** `.docs/library/_backup_before_label_cleanup_<timestamp>/`

**Rules applied:**
- Strip `sym_` / `sym ` / `symbol_` prefixes from display names
- Title Case with acronym preservation (LI, DA, LS, LSc, IDF, WICP, LCP, BACnet, CAT6, CO2, etc.)
- Remove duplicate entries (prefer SVG/builder_export over PNG duplicates)
- Specific label fixes (LI Leak Indicator, DA Door Open, LS/LSc sensors, LLV solenoids, PowerScout, Orbit TouchXL, RDM Data Manager, …)

**Bold duplicates removed:** 0 (no `_bold` asset files found; duplicates were PNG/SVG pairs)

**After run:** Restart server or click **Refresh Library** in the component panel.

---

## Phase B — Insert Symbol Legend UI

**Entry points:**
- Right-click canvas → **Insert Symbol Legend**
- Insert tab → Legend → **Symbol Legend**
- Draw tab → Legend → **Symbol Legend** (Connector Legend renamed for clarity)

**Dialog:** `SymbolLegendModal.tsx`
- Template dropdown (5 built-ins + saved templates)
- Search component library + add rows
- Per-row checkbox, editable label, move up/down
- Add Row / Remove Selected / Save As Template / Delete Template
- Insert Legend

**Built-in templates:**
1. Refrigeration / WICP Symbols (LI, DA, LS, LSc, ES, EA, T, LLV, EEV)
2. Interior Device Location Symbols
3. Exterior Device Location Symbols
4. Lighting Symbols
5. Power Metering Symbols
6. Custom (empty)

---

## Phase C — Editable grouped objects

**Implementation:** `CanvasEditor.addSymbolLegend()`
- Fabric `Group` with white background, black border, editable title
- Each row: symbol image (edge/bw from library) + editable `Textbox` label
- `objName`: `Symbol Legend` on group; per-row labels named `Legend Label: …`
- User can move/resize group, **Ungroup** to edit/delete individual rows
- Persists in `page.canvasObjects` → saves with project → exports to PDF

Connector Legend (`addLegend`) unchanged.

---

## Phase D — Legend template storage

**Location:** `.docs/library/legend_templates/`
- `manifest.json` — template index
- `<template_id>.json` — rows, title, category, layout styling

**API:**
- `GET/POST /api/lib/legend-templates`
- `GET/DELETE /api/lib/legend-templates/<id>`
- `POST /api/lib/legend-templates/<id>/rename`

**Backend:** `core/legend_template_store.py`

---

## Files changed

| Area | Files |
|------|-------|
| Cleanup | `scripts/clean_component_library_labels.py` |
| Backend | `core/legend_template_store.py`, `server.py` |
| Canvas | `frontend/src/components/CanvasEditor.tsx` |
| UI | `SymbolLegendModal.tsx`, `App.tsx`, `Ribbon.tsx` |
| Data | `frontend/src/model/symbolLegendPresets.ts`, `types.ts`, `api/client.ts` |
| Styles | `frontend/src/styles/app.css` |
| Tests | `scripts/smoke_legend_templates.py` |

---

## How to use

1. Run `python scripts/clean_component_library_labels.py` (once; backup created automatically)
2. Restart `python server.py` or Refresh Library
3. Open a layout/canvas page
4. Right-click → **Insert Symbol Legend** (or Insert → Symbol Legend)
5. Pick **Refrigeration / WICP Symbols**, uncheck unwanted rows, edit labels
6. Click **Insert Legend**
7. Move/resize; Ungroup to edit text or delete rows
8. Save project — legend persists and exports to PDF

---

## Build / test results

| Check | Result |
|-------|--------|
| `npm run build` | OK |
| `python -m compileall server.py core scripts` | OK |
| `scripts/smoke_routes.py` | OK |
| `scripts/smoke_legend_templates.py` | OK |

---

## Honest flags

- Library cleanup modifies gitignored `.docs/library/` files locally — run the script on each machine that needs clean labels.
- Symbol icons load from library edge/bw URLs; rows without a matched component show a gray placeholder box.
- Connector Legend not migrated to the new row editor (intentionally unchanged this pass).
