from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    modal = (root / "frontend" / "src" / "components" / "SymbolMapperModal.tsx").read_text(encoding="utf-8")
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    model = (root / "frontend" / "src" / "model" / "symbolCountSummary.ts").read_text(encoding="utf-8")
    client = (root / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    server = (root / "server.py").read_text(encoding="utf-8")
    core = (root / "core" / "symbol_count_package.py").read_text(encoding="utf-8")
    css = (root / "frontend" / "src" / "styles" / "symbolMapper.css").read_text(encoding="utf-8")

    checks = {
        "optionADefaultOn": "useState(true)" in modal and "Add a separate Symbol Count Summary page" in modal,
        "includedOnlyRows": ".filter(({ accepted }) => accepted > 0)" in modal,
        "twoPageDownloadButton": "Download highlighted + count PDF" in modal,
        "twoPagePackageApi": "createSymbolMapperCountPackage" in modal and "/package" in client,
        "legendPngAndSvgDownloads": (
            "Download count PNG" in modal
            and "Download count SVG" in modal
            and "downloadCountLegend('png')" in modal
            and "downloadCountLegend('svg')" in modal
            and "result.legendPngUrl" in modal
            and "result.legendSvgUrl" in modal
        ),
        "exactEmblemPreview": "symbolCountLegendDataUrl" in modal,
        "callbackCarriesCountPage": "countPage: SymbolMapperCountPageRequest" in modal,
        "appBuildsArtifacts": "buildSymbolCountSummaryArtifacts" in app,
        "summaryPageAfterDrawing": "pagesToAdd = countArtifacts ? [page, countArtifacts.page] : [page]" in app,
        "compactImageLegendPage": "type: 'imagePlaceholder'" in model and "symbol-count-legend.svg" in model,
        "noExtraWorksheetTab": "worksheets: latest.worksheets" in app and "linkedWorksheetId" not in model,
        "splitColorOutlines": "split-vertical" in model and "stroke=\"${c2}\"" in model,
        "zeroAndIgnoredOmitted": "zero-count, ignored, and unresolved symbols are omitted" in model,
        "packageRoute": "symbol_mapper_package" in server and "build_output_package" in server,
        "serverTwoPagePdf": "output.insert_pdf(highlighted)" in core and "output.new_page" in core,
        "exactColors": "row[\"color\"]" in core and "row[\"color2\"]" in core,
        "visibleActionDock": "sm-output-action-dock" in modal and "sm-output-actions-scroll" in modal,
        "countDownloadsDocked": "sm-count-download-row-docked" in modal and "Download count PNG" in modal and "Download count SVG" in modal,
        "addPageDocked": "sm-add-output-pages" in modal and "Add highlighted + count pages" in modal,
        "independentSaveScroll": "grid-template-rows: minmax(0, 1fr) auto" in css and "overflow-y: auto" in css,
        "fixedDockShadow": "box-shadow: 0 -8px 18px" in css,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
