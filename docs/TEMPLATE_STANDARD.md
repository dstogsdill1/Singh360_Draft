# Singh360 SmartDraw — Template Standard

## ANSI B Landscape Sheet

- Physical output: `17in x 11in` landscape.
- Working coordinate system (editor): `1632 x 1056` px.
- 1in = 96px mapping for deterministic browser rendering.

## Template Regions

1. Outer frame
2. Inner printable frame
3. Main drawing body
4. Optional top title rail
5. Bottom title block
6. Revision block
7. Firm/logo block
8. Project metadata block
9. Sheet metadata block
10. Page number block

## Default Geometry (px)

- Sheet: `1632 x 1056`
- Outer border inset: `8`
- Inner frame inset: `16`
- Title block height: `144`
- Body region: `x=16, y=16, w=1600, h=880`
- Title block region: `x=16, y=896, w=1600, h=144`

## Title Block Fields

Required fields:

- `SINGH360 INC.`
- `logo`
- `address`
- `website`
- `phone`
- `Project`
- `Creator`
- `File`
- `Created`
- `Version`
- `Date`
- `Edited by`
- `Notes`
- `Sheet Code`
- `Sheet Title`
- `Page X of Y`

## Visual Standard

- Strong black/gray technical linework.
- Square corners only.
- No rounded cards, no soft web panel style.
- Border hierarchy:
  - Primary frame: 2.0 px
  - Secondary grid lines: 1.0 px
  - Minor separators: 0.5 px
- Optional subtle Singh360 accent/watermark allowed if it does not reduce legibility.

## Determinism Requirements

- Template geometry generated from data constants, not copied ad-hoc HTML.
- Same template renderer for editor and export.
- Logo constrained to designated box with fit-contain behavior.

## Page Numbering Display

- Display uses included-page ordinal:
  - `Page 1 of 14`, `Page 2 of 14`, ...
- If page excluded, it is not counted in `Y` and not exported.
- `Sheet Code` remains user-defined (`EMS 3.10a`, etc.).
