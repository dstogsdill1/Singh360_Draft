# Canonical Refrigeration Symbol Components

## Purpose

Singh360 Draft uses one canonical refrigeration symbol standard across three related workflows:

1. **Symbol Mapper** highlights existing symbols on workbook-backed drawing pages.
2. **Symbol Legend** builds and saves editable legend groups.
3. **Component Library** inserts one independent, movable map marker onto a canvas page.

The individual Component Library assets are exact highlighted map markers. They are not badge-style emblems. Each asset uses a square translucent highlight around the original source symbol.

## Canonical set

The standard contains 15 ordered entries:

1. TS — Temperature Sensor
2. DA — Door Alarm
3. LS — Refrigerant Leak Detection Sensor
4. LS₂ — CO₂ Refrigerant Leak Sensor
5. LI — Refrigerant Leak Indicator Audio/Visual Alarm
6. LI₂ — CO₂ Refrigerant Leak Indicator Audio/Visual Alarm
7. CC — RDM Case Controller
8. DTS — Dual Temperature Switch
9. HT — High Temperature Alarm Strobe (Amber)
10. ES — Walk-In Freezer Entrapment Switch
11. AS — Alarm Strobe (Red)
12. EA — Entrapment Alarm
13. S — Liquid Line Solenoid Valve 120V
14. DT — Defrost Termination Sensor
15. $ / S — Clean Switch

The source definitions remain in `defaults/symbol_mapper_standard.json`.

## Exact component renderer

Renderer version:

```text
singh360-map-marker-v39
```

The V39 SVG renderer creates:

- a transparent 96×96 SVG canvas;
- one rectangular colored highlight with a lightly tinted fill;
- a vertically split highlight for two-color symbols;
- one centered original source circle or square, when applicable;
- the approved black glyph;
- no oversized outer circle or badge construction.

Each generated SVG contains renderer metadata and role markers used by automated geometry tests.

## Runtime migration

Run from the repository root:

```powershell
python -m scripts.install_symbol_standard_v39
```

Verify without changing runtime data:

```powershell
python -m scripts.install_symbol_standard_v39 --check
```

Run the isolated migration, idempotence, metadata-preservation, alias, and SVG geometry tests:

```powershell
python -m scripts.smoke_symbol_standard_v39
```

The legacy V38 module names remain compatibility wrappers and route to V39.

## Runtime data affected

The controlled migration updates only canonical symbol-library runtime data:

- `.docs/symbol_mapper/templates/standard.json`
- `.docs/library/v2/components/symbols_markers/`
- `.docs/library/v2/symbols/symbols_markers/`
- `.docs/library/v2/thumbnails/symbols_markers/`
- `.docs/library/v2/manifest.json`
- `.docs/library/legend_templates/singh360-refrigeration-symbols-standard.json`

The migration does not read or write `project.json` or any linked workbook.

Before a live migration, create a complete timestamped backup under `.docs/patch_backups/` covering `.docs/library`, `.docs/symbol_mapper`, the canonical project package, the linked workbook, `frontend/dist`, repository status/diffs, and the verified server process.

## Identity and duplicate protection

Canonical Component Library entries use stable IDs derived from the full symbol key. V39 matches canonical entries only by:

- stable component ID;
- stable `singh360-symbol-key:` tag;
- canonical generated SVG filename; or
- exact `source.standardKey` metadata.

It does not retire components through fuzzy code or display-name matching. Unrelated user components remain untouched. Existing favorites, custom aliases, extra metadata, and notes are preserved.

## Adding a canonical symbol

1. Add the definition to `defaults/symbol_mapper_standard.json` in the required order.
2. Add the exact normalized key to `EXPECTED_KEYS` in `scripts/install_symbol_standard_v39.py` and its smoke test.
3. Use a unique full symbol key even when a short code is shared.
4. Add approved aliases without changing the display glyph.
5. Extend explicit geometry coverage for any new source shape or pattern.
6. Run the V39 smoke test and frontend production build.
7. Run the controlled live migration only after code tests pass and runtime backups exist.

Never add a second parallel refrigeration symbol collection to work around a canonical migration problem.
