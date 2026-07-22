from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    app = (root / 'frontend' / 'src' / 'App.tsx').read_text(encoding='utf-8')
    modal = (root / 'frontend' / 'src' / 'components' / 'SymbolMapperModal.tsx').read_text(encoding='utf-8')
    model = (root / 'frontend' / 'src' / 'model' / 'symbolCountSummary.ts').read_text(encoding='utf-8')
    checks = {
        'optionADefaultOn': 'const [addCountPage, setAddCountPage] = useState(true)' in modal,
        'includedOnlyRows': '.filter(({ accepted }) => accepted > 0)' in modal,
        'separateSummaryChoice': 'Add a separate Symbol Count Summary page' in modal,
        'callbackCarriesCountPage': 'countPage: SymbolMapperCountPageRequest' in modal,
        'twoPageButton': 'Add highlighted + count pages' in modal,
        'appBuildsArtifacts': 'buildSymbolCountSummaryArtifacts' in app,
        'summaryPageAfterDrawing': 'pagesToAdd' in app and 'countArtifacts.page' in app,
        'separateWorksheet': 'countArtifacts.worksheet' in app,
        'noContinuation': "allowContinuation: false" in model and "splitMode: 'none'" in model,
        'includedCountColumn': "'COUNT'" in model and 'String(row.included)' in model,
        'zeroAndIgnoredOmitted': 'zero-count and ignored symbols are omitted' in model,
        'standardTitleBlockPage': "pageType: 'data-grid'" in model and "renderMode: 'excel_exact'" in model,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({'ok': True, **checks}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
