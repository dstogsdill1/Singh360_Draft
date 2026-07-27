from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.vector_pdf_export import build_selected_export_document


def main() -> int:
    header = [["PAGE", "SHEET CODE", "SHEET TAB", "PAGE TITLE", "INCLUDE", "FAMILY", "PAGE TYPE"]]
    project = {
        "pages": [
            {"id": "cover", "order": 1, "include": True, "sheetCode": "EMS 1.0", "displaySheetCode": "EMS 1.0", "sheetTitle": "Cover / Project Info", "sheetTab": "Cover", "pageType": "cover", "blocks": [], "canvasObjects": []},
            {"id": "index", "order": 2, "include": True, "sheetCode": "EMS 2.0", "displaySheetCode": "EMS 2.0", "sheetTitle": "Sheet Index / TOC", "sheetTab": "Index", "pageType": "index", "renderMode": "excel_exact", "blocks": [{"type": "excelRange", "grid": header, "rowHeights": [20]}], "canvasObjects": []},
            {"id": "page3", "order": 3, "include": True, "sheetCode": "EMS 3.0", "displaySheetCode": "EMS 3.0", "sheetTitle": "Page Three", "sheetTab": "P3", "pageType": "canvas", "blocks": [], "canvasObjects": []},
            {"id": "page4", "order": 4, "include": True, "sheetCode": "R-3.2", "displaySheetCode": "R-3.2", "sheetTitle": "REFG CNTL FLOOR PLAN", "sheetTab": "R3.2", "pageType": "canvas", "blocks": [], "canvasObjects": []},
            {"id": "page5", "order": 5, "include": True, "sheetCode": "EMS 5.0", "displaySheetCode": "EMS 5.0", "sheetTitle": "Page Five", "sheetTab": "P5", "pageType": "canvas", "blocks": [], "canvasObjects": []},
        ],
        "worksheets": [],
    }

    one = build_selected_export_document(project, ["page4"])
    one_included = [page for page in one["pages"] if page.get("include", True)]
    assert [page["id"] for page in one_included] == ["page4"]
    assert one_included[0]["pageNumber"] == 1 and one_included[0]["pageTotal"] == 1

    three = build_selected_export_document(project, ["cover", "index", "page4"])
    three_included = [page for page in three["pages"] if page.get("include", True)]
    assert [page["id"] for page in three_included] == ["cover", "index", "page4"]
    index = next(page for page in three_included if page["id"] == "index")
    grid = index["blocks"][0]["grid"]
    listed_codes = [row[1] for row in grid[1:]]
    assert listed_codes == ["EMS 1.0", "EMS 2.0", "R-3.2"]
    assert [page["pageNumber"] for page in three_included] == [1, 2, 3]

    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    modal = (ROOT / "frontend" / "src" / "components" / "ExportModal.tsx").read_text(encoding="utf-8")
    client = (ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    canvas = (ROOT / "frontend" / "src" / "components" / "CanvasEditor.tsx").read_text(encoding="utf-8")
    sheet_css = (ROOT / "frontend" / "src" / "styles" / "sheet.css").read_text(encoding="utf-8")
    pdf_modal = (ROOT / "frontend" / "src" / "components" / "PdfCropModal.tsx").read_text(encoding="utf-8")
    print_view = (ROOT / "frontend" / "src" / "components" / "PrintView.tsx").read_text(encoding="utf-8")

    checks = {
        "allSelectedByDefault": "new Set(includedPages.map((page) => page.id))" in modal,
        "selectAllAndNone": "Select All" in modal and ">None<" in modal,
        "pageIdsSent": "pageIds: pending.pageIds" in app and "pageIds?: string[]" in client,
        "warningsScoped": "fetchExportWarnings(proj.id, pageIds)" in app,
        "serverSelectedClone": "build_selected_export_document(doc, selected_ids)" in server,
        "vectorUnderlay": "apply_vector_pdf_underlays" in server,
        "pdfStartsNearFullBody": "const maxW = CANVAS_W * 0.98;" in canvas and "const maxH = CANVAS_H * 0.98;" in canvas,
        "transparentPrintCanvas": "S360 VECTOR PDF EXPORT START" in sheet_css,
        "cropUsesPdfPointMapping": "page.widthPt / page.previewWidth" in pdf_modal and "page.heightPt / page.previewHeight" in pdf_modal,
        "physicalPageIdentityMarker": "S360PID_${pageId}" in print_view,
        "livePdfPreviewOpaque": "S360 LIVE PDF OBJECT REPAIR V1" in canvas and "obj.opacity = 1" in canvas,
    }
    assert all(checks.values()), checks

    print(json.dumps({
        "ok": True,
        "singlePageSelection": [page["id"] for page in one_included],
        "threePageSelection": [page["id"] for page in three_included],
        "sheetIndexCodes": listed_codes,
        "sourceChecks": checks,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
