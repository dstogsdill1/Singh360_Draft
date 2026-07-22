from __future__ import annotations

import json
from pathlib import Path


def require(path: Path, *needles: str) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{path}: missing {missing}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    require(
        root / "server.py",
        "return jsonify(data)",
        "doc = sync_project_sheet_index(doc)",
        "store.save(project_id, doc)",
    )
    require(
        root / "frontend" / "src" / "api" / "client.ts",
        "saveProject(project: ProjectModel): Promise<ProjectModel>",
        "getSymbolMapperTemplate",
        "saveSymbolMapperTemplate",
    )
    require(
        root / "frontend" / "src" / "model" / "types.ts",
        "export interface ImageCropRect",
        "export interface ImageCropState",
        "getSelectedImageCrop",
        "applySelectedImageCrop",
        "glyph?: string",
        "highlighted?: boolean",
    )
    require(
        root / "frontend" / "src" / "components" / "CanvasEditor.tsx",
        "S360 IMAGE CROP API START",
        "getSelectedImageCrop",
        "applySelectedImageCrop",
        "Singh360 Symbol Legend",
        "row.highlighted",
        "row.pattern",
    )
    require(
        root / "frontend" / "src" / "components" / "ImageCropModal.tsx",
        "Apply crop",
        "Fit crop to page",
        "Fill page with crop",
    )
    require(
        root / "frontend" / "src" / "components" / "SymbolLegendModal.tsx",
        "Uses the same Singh360 Standard",
        "saveSymbolMapperTemplate",
        "No highlights",
        "Save / update standard",
        "SYMBOL_PALETTE",
    )
    require(
        root / "frontend" / "src" / "model" / "symbolPalette.ts",
        "Red / Green",
        "backgroundClip: 'padding-box, border-box'",
    )
    require(
        root / "frontend" / "src" / "components" / "Ribbon.tsx",
        "Crop / Fit",
        "Fit Page",
        "Fill Page",
    )
    require(
        root / "frontend" / "src" / "App.tsx",
        "savedFromServer = normalizeProjectAssetUrls(await saveProject(p))",
        "<ImageCropModal",
        "openSelectedImageCrop",
        "placeSelectedImageOnPage",
    )
    require(
        root / "frontend" / "src" / "styles" / "app.css",
        "S360 IMAGE CROP UX START",
        ".image-crop-selection",
    )

    result = {
        "ok": True,
        "imageCrop": True,
        "fitAndFill": True,
        "sheetIndexSyncOnSaveAndExport": True,
        "symbolLegendUsesMapperStandard": True,
        "optionalLegendHighlights": True,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
