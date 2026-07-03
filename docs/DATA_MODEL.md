# Singh360 SmartDraw — Data Model

## Top-level Project Schema

```json
{
  "id": "string",
  "schemaVersion": 1,
  "metadata": {
    "projectName": "",
    "storeNumber": "",
    "client": "",
    "location": "",
    "address": "",
    "createdBy": "",
    "createdDate": "",
    "sourceFile": "",
    "version": "",
    "status": "Draft"
  },
  "sources": [],
  "worksheets": [],
  "pages": [],
  "templates": [],
  "assets": [],
  "revisionLog": []
}
```

## Source Records

```json
{
  "id": "src_xxx",
  "type": "workbook|csv|pdf|image|vsdx",
  "name": "SA31 workbook.xlsx",
  "path": "relative/original/path",
  "importedAt": "2026-07-02T00:00:00Z",
  "checksum": "optional",
  "notes": ""
}
```

## Worksheet Model

```json
{
  "id": "ws_xxx",
  "name": "11_Bill of Materials",
  "sourceId": "src_xxx",
  "visible": true,
  "classHint": "data-grid|canvas|underlay|unknown",
  "grid": [["", ""]],
  "formulas": {"A1": "=SUM(B1:B5)"},
  "styles": {"A1": {"bold": true, "fontSize": 10}},
  "mergedCells": [{"startRow": 0, "startCol": 0, "endRow": 0, "endCol": 3}],
  "rowHeights": {"1": 24},
  "columnWidths": {"1": 120},
  "provenance": {"sheet": "11_Bill of Materials"}
}
```

## Page Model

```json
{
  "id": "page_xxx",
  "order": 1,
  "include": true,
  "sheetCode": "EMS 1.1",
  "sheetTitle": "BILL OF MATERIALS",
  "sheetTab": "11_Bill of Materials",
  "pageType": "data-grid",
  "templateId": "ansi-b-standard",
  "linkedWorksheetId": "ws_xxx",
  "blocks": [],
  "canvasObjects": [],
  "underlays": [],
  "notes": "",
  "revisionRows": []
}
```

## Canvas Object Model (Fabric-compatible serialized)

```json
{
  "id": "obj_xxx",
  "type": "rect|line|textbox|circle|image|arrow",
  "left": 100,
  "top": 100,
  "width": 200,
  "height": 80,
  "angle": 0,
  "scaleX": 1,
  "scaleY": 1,
  "stroke": "#111111",
  "strokeWidth": 1,
  "fill": "transparent",
  "text": "optional",
  "fontSize": 14,
  "locked": false,
  "layer": 10,
  "source": {"type": "manual", "worksheet": "", "cellRange": ""}
}
```

## Underlay Model

```json
{
  "id": "udl_xxx",
  "assetId": "asset_xxx",
  "kind": "pdf|image|vsdx",
  "page": 1,
  "x": 0,
  "y": 0,
  "width": 1632,
  "height": 946,
  "opacity": 0.35,
  "rotation": 0,
  "locked": true
}
```

## Numbering Rules

- `Page X of Y` uses only `include=true` pages.
- Recomputed after add/reorder/delete/include-toggle.
- `sheetCode` remains independent from ordinal page index.

## Normalization Rules

Before JSON serialization:

- Convert `None`, `NaN`, `NaT`, `<NA>`, `undefined` to empty string (`""`) where scalar text expected.
- Booleans are strict `true|false`.
- Lists and maps are present with empty defaults (no missing keys that break UI).

## Provenance Rules

- Page/worksheet records keep source references (`sourceId`, sheet name, optional cell refs).
- Imported/generated entities never lose origin metadata.
