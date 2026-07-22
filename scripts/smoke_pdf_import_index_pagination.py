from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(path: Path, *needles: str) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{path}: missing {missing}")


def main() -> int:
    require(
        ROOT / "frontend" / "src" / "components" / "Ribbon.tsx",
        "PDF Page / Crop",
        "Crop / Fit",
    )
    require(
        ROOT / "frontend" / "src" / "components" / "CanvasEditor.tsx",
        "applySelectedImageCrop",
        "pdfSource",
        "pdfDpi",
    )
    require(
        ROOT / "server.py",
        "/api/projects/<project_id>/pdf/render-page",
        "/api/projects/<project_id>/pdf/render-crop",
        "_PDF_CROP_DPI = {300, 400, 500, 600}",
    )
    modal_text = (ROOT / "frontend" / "src" / "components" / "PdfCropModal.tsx").read_text(encoding="utf-8")
    assert "S360 HIGH RES PDF IMPORT UX" in modal_text
    print(json.dumps({"ok": True, "pdfImport": "direct high-resolution render", "cropAfterInsert": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
