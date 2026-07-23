from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    canvas = (root / "frontend/src/components/CanvasEditor.tsx").read_text(encoding="utf-8")
    ribbon = (root / "frontend/src/components/Ribbon.tsx").read_text(encoding="utf-8")
    types = (root / "frontend/src/model/types.ts").read_text(encoding="utf-8")
    main_tsx = (root / "frontend/src/main.tsx").read_text(encoding="utf-8")
    controls = (root / "frontend/src/components/TextBoxFormatControls.tsx").read_text(encoding="utf-8")
    css = (root / "frontend/src/styles/textBoxFormatting.css").read_text(encoding="utf-8")

    checks = {
        "canvasRenderer": "S360 POWERPOINT TEXT BOX FORMATTING V1" in canvas,
        "serializedProperties": all(token in canvas for token in (
            "'textBoxFill'", "'textBoxFillOpacity'", "'textBoxStroke'",
            "'textBoxStrokeWidth'", "'textBoxPadding'", "'textBoxRadius'",
        )),
        "newTextBoxDefaults": "textBoxFill: 'transparent'" in canvas and "textBoxPadding: 8" in canvas,
        "selectionSummary": "isTextBox" in canvas and "textBoxFillOpacity" in canvas,
        "updateSelectedMapsStyles": "S360 TEXT BOX PATCH APPLICATION" in canvas,
        "modelFields": all(token in types for token in (
            "textBoxFill?: string;", "textBoxFillOpacity?: number;",
            "textBoxStroke?: string;", "textBoxStrokeWidth?: number;",
            "textBoxPadding?: number;", "textBoxRadius?: number;",
        )),
        "ribbonControl": "TextBoxFormatControls" in ribbon,
        "typedRibbonCallback": "onChange={onUpdateSelection}" in ribbon,
        "noInvalidCanvasCallback": "canvas.updateSelected" not in ribbon,
        "whiteAndNoFill": "White" in controls and "No Fill" in controls,
        "outlineControls": "No Outline" in controls and "textBoxStrokeWidth" in controls,
        "opacityPaddingCorners": all(token in controls for token in ("Opacity", "Padding", "Corners")),
        "presets": all(token in controls for token in ("White Box", "Callout", "Clear Box")),
        "stylesheetImported": "textBoxFormatting.css" in main_tsx,
        "stylesheet": "S360 POWERPOINT TEXT BOX FORMATTING V1" in css,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
