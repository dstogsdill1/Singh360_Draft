from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.pdf_optimizer import analyze_pdf
from core.vector_pdf_export import build_selected_export_document, prepare_vector_export_clone


def _project_pdf_inventory(project_json: Path) -> dict[str, Any]:
    project = json.loads(project_json.read_text(encoding="utf-8"))
    selected = build_selected_export_document(project, [])
    source_dir = project_json.parent / "sources" / "pdf"
    export_clone, placements = prepare_vector_export_clone(selected, source_pdf_dir=source_dir)
    pages = sorted(
        [page for page in selected.get("pages", []) if isinstance(page, dict) and page.get("include", True)],
        key=lambda page: int(page.get("order") or 0),
    )
    imported = []
    for index, page in enumerate(pages):
        objects = page.get("canvasObjects") if isinstance(page.get("canvasObjects"), list) else []
        pdf_objects = [obj for obj in objects if isinstance(obj, dict) and str(obj.get("pdfSource") or "").strip()]
        if pdf_objects:
            imported.append({
                "page": index + 1,
                "projectPageId": page.get("id"),
                "sheetCode": page.get("sheetCode") or page.get("code"),
                "pageType": page.get("pageType"),
                "pdfObjects": [
                    {
                        "source": obj.get("pdfSource"),
                        "sourcePage": obj.get("pdfPage"),
                        "previewDpi": obj.get("pdfDpi"),
                        "previewDimensions": [obj.get("width"), obj.get("height")],
                        "previewUrl": obj.get("src"),
                        "rotation": obj.get("angle") or 0,
                        "managedBase": obj.get("pdfBase") is True,
                    }
                    for obj in pdf_objects
                ],
            })
    hidden = 0
    for page in export_clone.get("pages", []):
        for obj in page.get("canvasObjects", []) if isinstance(page, dict) else []:
            if isinstance(obj, dict) and obj.get("pdfPreviewExcluded") is True:
                hidden += 1
    return {
        "projectId": project.get("id"),
        "includedPages": len(pages),
        "importedPdfPages": imported,
        "pdfPreviewObjects": sum(len(item["pdfObjects"]) for item in imported),
        "excludedPreviewObjectsInExportClone": hidden,
        "vectorPlacements": len(placements),
        "managedPageIndices": sorted({placement.export_page_index for placement in placements}),
        "placements": [placement.to_dict() for placement in placements],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a real Singh360 PDF export for size and viewer performance.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--project-json", type=Path)
    parser.add_argument("--render-dpi", type=int, default=96)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    project = _project_pdf_inventory(args.project_json) if args.project_json else None
    diagnostics = analyze_pdf(
        args.pdf,
        render_dpi=args.render_dpi,
        managed_page_indices=(project or {}).get("managedPageIndices", []),
    )
    report = {"ok": True, "pdf": diagnostics, "project": project}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
