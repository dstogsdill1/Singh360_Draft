# Singh360 Component Library V40

## Purpose

V40 separates two symbol systems that serve different jobs:

1. **Symbol Mapper Highlight Legend** — the existing 15 square/translucent highlighted markers used when mapping symbols found on an existing drawing.
2. **Singh360 Plan Marker Legend** — simple colored-ring letter markers intended for direct placement on new plan/layout pages.

The two styles remain separate collections and separate saved editable legends. They are not alternate renderings of one card.

## V40 plan markers

The Plan Marker collection contains 24 ordered markers:

TS, DA, LS, LS₂, LI, LI₂, CC, DTS, HT, ES, AS, EA, S, DT, $, HS, DS, LT, OAT, PM, T, EEPR, EPR, and WICP.

Each asset is a transparent vector SVG with:

- one colored circular ring;
- a black centered glyph;
- a split ring where the approved meaning uses two colors;
- a green status dot on HS;
- no square Symbol Mapper highlight.

## Items retained

V40 explicitly retains:

- Callout Number 1 through Callout Number 20;
- Person Trapped Inside sign;
- When Lit Refrigerant Leak — Do Not Enter sign;
- HELP TRAPPED / PERSONA ATRAPADA sign;
- Safety Signage Legend;
- EEPR — Electronic Evaporator Pressure Regulator;
- EPR — Mechanical Evaporator Pressure Regulator;
- every unrelated real equipment component and user-added asset.

## Items retired

V40 retires only exact, known generated marker records and line-card records. It does not delete their files.

Examples include old duplicate RDM marker IDs, Electric Defrost marker, DIN Rail marker, Dimming Zone marker, individual CAT6/Fiber/BACnet line cards, old liquid-line open/closed cards, generic fan/coil/compressor/rack markers, and old IDF/MDF marker cards.

Retired records remain recoverable through the Component Library archive/history.

## Runtime data

The migration updates only:

- `.docs/library/manifest.json`
- `.docs/library/component_builder_export.json`
- `.docs/library/components/symbols_markers/plan_markers/`
- `.docs/library/symbols/symbols_markers/plan_markers/`
- `.docs/library/thumbnails/symbols_markers/plan_markers/`
- `.docs/library/legend_templates/`
- missing canonical callout/sign vector assets

It does not read or write project JSON, linked workbooks, canvas objects, or exported drawing packages.

## Commands

Install into the local runtime:

```powershell
python -m scripts.install_component_library_v40
```

Verify without changing runtime data:

```powershell
python -m scripts.install_component_library_v40 --check
```

Run isolated preservation/idempotence tests:

```powershell
python -m scripts.smoke_component_library_v40
```

## UI workflow

In the Component Library:

- choose **Mapper Highlights** for the 15 Symbol Mapper cards;
- choose **Plan Markers** for direct page-placement markers;
- use **Saved Symbol Legends** to open/insert either grouped legend;
- use **Safety Signage Legend** for the retained signs.

All physical removals are prohibited by this migration. Retired cards are hidden from the normal Active view but remain available in history/retired views.
