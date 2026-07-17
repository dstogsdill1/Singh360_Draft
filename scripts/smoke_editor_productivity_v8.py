# Static UI contract smoke for Singh360 editor productivity patch V8.
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def need(path: str, *tokens: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8-sig")
    missing = [token for token in tokens if token not in text]
    if missing:
        raise SystemExit(f"{path}: missing expected patch tokens: {missing}")


def main() -> int:
    need(
        "frontend/src/styles/libraryV2.css",
        "S360 COMPONENT SIDEBAR FIT V8",
        ".libv2-preview img",
        "object-fit: contain",
    )
    need(
        "frontend/src/components/LibraryPanelV2.tsx",
        "function insertMetaFor(c: LibV2Component)",
        "insertMetaFor(c));",
        "...insertMetaFor(c)",
        "Image unavailable",
    )
    need(
        "frontend/src/components/DocumentView.tsx",
        "defaultHeight?: number; acronym?: string",
        "defaultHeight, acronym",
    )
    need(
        "frontend/src/App.tsx",
        "Package export failed",
        "defaultHeight?: number; acronym?: string",
    )
    need(
        "frontend/src/components/CanvasEditor.tsx",
        "const renderW = iw * scale",
        "Component image load failed",
        "CANVAS_W - renderW",
    )
    need(
        "frontend/src/components/Ribbon.tsx",
        "const historyEnabled = cx;",
        "const hasSelection = cx && !!selection;",
    )
    print("OK: V8 component-fit and editor command contracts are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
