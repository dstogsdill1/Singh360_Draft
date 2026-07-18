from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    normalized = (ROOT / "frontend/src/components/renderers/NormalizedPage.tsx").read_text(encoding="utf-8")
    document = (ROOT / "frontend/src/components/DocumentView.tsx").read_text(encoding="utf-8")
    toolbar = (ROOT / "frontend/src/components/ViewportToolbar.tsx").read_text(encoding="utf-8")
    raw = (ROOT / "frontend/src/components/renderers/RawGridRenderer.tsx").read_text(encoding="utf-8")
    reimport = (ROOT / "core/workbook_reimport.py").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/sheet.css").read_text(encoding="utf-8")

    assert "layoutEditing={layoutEditing && !previewOnly}" in normalized
    assert "onChange={patch}" in normalized
    assert "layoutUndoRef" in document
    assert "onSourceUndo" in document
    compact_toolbar = re.sub(r"\s+", "", toolbar)
    assert ">Page</button>" in compact_toolbar
    assert ">Data</button>" in compact_toolbar
    assert ">Undo</button>" in compact_toolbar
    assert ">Redo</button>" in compact_toolbar
    assert "Apply Data & Return" in raw
    assert 'updated_project["worksheets"] = candidate.get("worksheets", [])' in reimport
    assert '"toPreserveUnmatched": to_preserve_unmatched' in reimport
    assert 'plan.get("toPreserveUnmatched", [])' in reimport
    assert "SINGH360 SIMPLIFIED PAGE DATA EDITOR V14" in css

    print("OK: V14 page/data workflow, layout editing, undo/redo, and safe workbook refresh are installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
