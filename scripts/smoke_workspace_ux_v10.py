from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "frontend/src/components/ProjectShell.tsx": ["singh360-panel-left-pinned", "Hover for one second, or click to pin navigation open"],
    "frontend/src/components/PageNavigator.tsx": ["All Drawing Pages", "Show excluded/source-only"],
    "frontend/src/components/PageTabs.tsx": ["PageNavigator", "page-tabs-shell"],
    "frontend/src/components/WorkbookView.tsx": ["Workbook Drafts", "Publish"],
    "frontend/src/components/ViewportToolbar.tsx": ["Publish Worksheet", "Source-only worksheet"],
    "frontend/src/components/DocumentView.tsx": ["selectedWorksheetId", "sourceOnly"],
    "frontend/src/components/PageRenderer.tsx": ["worksheet?.id"],
    "frontend/src/components/LibraryPanelV2.tsx": ["Rebuild Previews", "libv2-health"],
    "frontend/src/App.tsx": ["openWorksheetDraft", "publishWorksheet", "Published Package", "Workbook Drafts", "page?.sheetTitle"],
    "frontend/src/styles/app.css": ["S360 WORKSPACE UX V10 START", "page-nav-popover", "source-tab-card"],
    "frontend/src/styles/libraryV2.css": ["libv2-preview-fallback-name"],
}

for rel, needles in checks.items():
    path = ROOT / rel
    assert path.is_file(), f"missing {rel}"
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        assert needle in text, f"{rel}: missing marker {needle!r}"
    assert not text.endswith("\n\n"), f"{rel}: blank line at EOF"
    for line_no, line in enumerate(text.splitlines(), 1):
        assert line == line.rstrip(), f"{rel}:{line_no}: trailing whitespace"

print("Workspace UX V10 source smoke: PASS")
