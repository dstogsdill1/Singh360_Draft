from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    excel = (ROOT / "frontend/src/components/renderers/ExcelRangeRenderer.tsx").read_text(encoding="utf-8")
    normalized = (ROOT / "frontend/src/components/renderers/NormalizedPage.tsx").read_text(encoding="utf-8")
    document = (ROOT / "frontend/src/components/DocumentView.tsx").read_text(encoding="utf-8")
    toolbar = (ROOT / "frontend/src/components/ViewportToolbar.tsx").read_text(encoding="utf-8")
    types = (ROOT / "frontend/src/model/types.ts").read_text(encoding="utf-8")
    reflow = (ROOT / "frontend/src/model/tableLayoutProfiles.ts").read_text(encoding="utf-8")
    refresh = (ROOT / "frontend/src/model/excelRange.ts").read_text(encoding="utf-8")
    rebuild = (ROOT / "frontend/src/model/pageRebuild.ts").read_text(encoding="utf-8")
    css = (ROOT / "frontend/src/styles/sheet.css").read_text(encoding="utf-8")
    page_renderer = (ROOT / "frontend/src/components/PageRenderer.tsx").read_text(encoding="utf-8")

    assert "xr-layout-col-handle" in excel
    assert "xr-layout-row-handle" in excel
    assert "Auto Row Heights" in excel
    assert "pageLayoutManual: true" in excel
    assert "layoutEditing={layoutEditing && !previewOnly}" in normalized
    assert "Edit Page Layout" in toolbar
    assert "Reset Standard Layout" in toolbar
    assert "resetPageLayout" in document
    assert "pageLayoutManual?: boolean;" in types
    assert "const pageManual = !!block.pageLayoutManual;" in reflow
    assert "const refreshExcelRangeWithPageLayout" in refresh
    assert "const outputPart = previousLayout?.pageLayoutManual" in rebuild
    assert "SINGH360 DIRECT PAGE LAYOUT EDITOR V13" in css
    assert "useState(false)" in page_renderer

    print("OK: V13 direct printable-page layout editor is installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
