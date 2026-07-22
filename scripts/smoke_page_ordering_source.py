from __future__ import annotations

from pathlib import Path


def require(path: Path, *needles: str) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{path}: missing {missing}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    require(
        root / "frontend" / "src" / "App.tsx",
        "confirmLatestProjectSaved",
        "await imageReady",
        "setPageIncludedAtStoredPosition",
        "onToggleInclude={toggleInclude}",
        "savedFromServer = normalizeProjectAssetUrls(await saveProject(p))",
        "Crop / Fit Selected Image",
        "<ImageCropModal",
    )
    require(
        root / "frontend" / "src" / "model" / "types.ts",
        "restorePackageIndex?: number;",
        "Promise<void> | void",
        "export interface ImageCropState",
        "getSelectedImageCrop",
        "columns?: 1 | 2",
    )
    require(root / "frontend" / "src" / "components" / "SheetManager.tsx", "sheet-drag-handle", "reorderByDrop", "isCoverPage(target)")
    require(root / "frontend" / "src" / "components" / "PageTabs.tsx", "pt-drag", "dragOverId", "movingIds", "isCoverPage(target)")
    require(
        root / "frontend" / "src" / "components" / "RenumberModal.tsx",
        "renumber-drag-table",
        "orderedPages",
        "Apply order &amp; codes",
        "isCoverPage(target)",
    )
    require(
        root / "frontend" / "src" / "components" / "CanvasEditor.tsx",
        "S360 IMAGE CROP API START",
        "applySelectedImageCrop",
        "Singh360 Symbol Legend",
        "split-vertical",
    )
    require(
        root / "frontend" / "src" / "components" / "ImageCropModal.tsx",
        "Crop / Fit Image",
        "Fit crop to page",
        "Fill page with crop",
    )
    require(
        root / "frontend" / "src" / "components" / "SymbolLegendModal.tsx",
        "Uses the same Singh360 Standard",
        "Save / update standard",
        "Highlight all",
        "No highlights",
        "Columns",
        "Marker size",
    )
    require(
        root / "frontend" / "src" / "components" / "SymbolMapperModal.tsx",
        "Sheet code",
        "inferOutputFields",
        "Adding and saving",
    )
    print("page ordering, confirmed-save, image-crop, and standard-legend source checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
