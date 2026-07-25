#!/usr/bin/env python3
"""Apply the Singh360 Rapid Page Review V35 feature to the exact V32.2 source."""
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "S360 RAPID PAGE REVIEW V35"


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_file(path: Path, transform) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = transform(original)
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def patch_ribbon(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(text, "export interface ViewControls {\n", "export type PageReviewFilter = 'all' | 'included' | 'excluded';\n\nexport interface ViewControls {\n", "Ribbon filter type")
    text = replace_once(text, "  onSetLineStyle: (style: LineStyle) => void;\n}", "  onSetLineStyle: (style: LineStyle) => void;\n  pageFilter: PageReviewFilter;\n  onSetPageFilter: (filter: PageReviewFilter) => void;\n}", "Ribbon filter props")
    text = replace_once(text, "  onUpdateSelection,\n  onSetLineStyle,\n}: Props) {", "  onUpdateSelection,\n  onSetLineStyle,\n  pageFilter,\n  onSetPageFilter,\n}: Props) {", "Ribbon prop destructure")
    text = replace_once(
        text,
        "            <Group title=\"Grid\">\n              <button className={`ribbon-btn ${view.showGrid ? 'active' : ''}`} disabled={!hasProject} onClick={view.toggleGrid}>Show Grid</button>\n              <button className={`ribbon-btn ${view.snap ? 'active' : ''}`} disabled={!hasProject} onClick={view.toggleSnap}>Snap</button>\n            </Group>\n",
        "            {/* S360 RAPID PAGE REVIEW V35 */}\n            <Group title=\"Page Filter\">\n              <button className={`ribbon-btn ${pageFilter === 'all' ? 'active' : ''}`} disabled={!hasProject} onClick={() => onSetPageFilter('all')}>All Pages</button>\n              <button className={`ribbon-btn ${pageFilter === 'included' ? 'active' : ''}`} disabled={!hasProject} onClick={() => onSetPageFilter('included')}>Included Only</button>\n              <button className={`ribbon-btn ${pageFilter === 'excluded' ? 'active' : ''}`} disabled={!hasProject} onClick={() => onSetPageFilter('excluded')}>Not Included</button>\n            </Group>\n            <Group title=\"Grid\">\n              <button className={`ribbon-btn ${view.showGrid ? 'active' : ''}`} disabled={!hasProject} onClick={view.toggleGrid}>Show Grid</button>\n              <button className={`ribbon-btn ${view.snap ? 'active' : ''}`} disabled={!hasProject} onClick={view.toggleSnap}>Snap</button>\n            </Group>\n",
        "Ribbon View filter group",
    )
    return text


def patch_app(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(text, "import Ribbon, { type ViewControls } from './components/Ribbon';", "import Ribbon, { type PageReviewFilter, type ViewControls } from './components/Ribbon';", "App Ribbon type import")
    text = replace_once(
        text,
        "  const [showGrid, setShowGrid] = useState(false);\n  const [snap, setSnap] = useState(true);\n",
        "  const [showGrid, setShowGrid] = useState(false);\n  const [snap, setSnap] = useState(true);\n  // S360 RAPID PAGE REVIEW V35\n  const [pageFilter, setPageFilter] = useState<PageReviewFilter>(() => {\n    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem('singh360-page-filter') : null;\n    return saved === 'included' || saved === 'excluded' ? saved : 'all';\n  });\n  const [rapidReviewBusy, setRapidReviewBusy] = useState(false);\n  useEffect(() => {\n    try { localStorage.setItem('singh360-page-filter', pageFilter); } catch { /* ignore */ }\n  }, [pageFilter]);\n",
        "App rapid-review state",
    )
    text = replace_once(
        text,
        "  const activePage = useMemo(() => {\n    if (!project || !activePageId) return null;\n    return project.pages.find((p) => p.id === activePageId) ?? null;\n  }, [project, activePageId]);\n",
        "  const activePage = useMemo(() => {\n    if (!project || !activePageId) return null;\n    return project.pages.find((p) => p.id === activePageId) ?? null;\n  }, [project, activePageId]);\n\n  // S360 RAPID PAGE REVIEW V35\n  const reviewPages = useMemo(() => {\n    const ordered = [...(project?.pages ?? [])].sort((a, b) => a.order - b.order);\n    if (pageFilter === 'included') return ordered.filter((page) => page.include);\n    if (pageFilter === 'excluded') return ordered.filter((page) => !page.include);\n    return ordered;\n  }, [project?.pages, pageFilter]);\n\n  const navigateReviewPage = useCallback(async (direction: -1 | 1) => {\n    if (!reviewPages.length) return;\n    const currentIndex = reviewPages.findIndex((page) => page.id === activePageRef.current?.id);\n    const targetIndex = currentIndex < 0\n      ? (direction > 0 ? 0 : reviewPages.length - 1)\n      : currentIndex + direction;\n    if (targetIndex < 0 || targetIndex >= reviewPages.length) return;\n    await switchPageSafely(reviewPages[targetIndex].id);\n  }, [reviewPages, switchPageSafely]);\n",
        "App review-page derivation",
    )
    text = replace_once(
        text,
        "  const toggleInclude = (id: string) =>\n    mutatePages((pages) => {\n      const target = pages.find((page) => page.id === id);\n      return target ? setPageIncludedAtStoredPosition(pages, id, !target.include) : pages;\n    });\n",
        "  const toggleInclude = (id: string) =>\n    mutatePages((pages) => {\n      const target = pages.find((page) => page.id === id);\n      return target ? setPageIncludedAtStoredPosition(pages, id, !target.include) : pages;\n    });\n\n  // S360 RAPID PAGE REVIEW V35\n  const toggleIncludeAndAdvance = async () => {\n    if (rapidReviewBusy) return;\n    const currentPage = activePageRef.current;\n    const currentProject = projectRef.current;\n    if (!currentPage || !currentProject) return;\n    const includeLocked = currentPage.pageType === 'cover' || isSheetIndexPage(currentPage);\n    if (includeLocked) return;\n\n    const ordered = [...currentProject.pages].sort((a, b) => a.order - b.order);\n    const filteredBefore = pageFilter === 'included'\n      ? ordered.filter((page) => page.include)\n      : pageFilter === 'excluded'\n        ? ordered.filter((page) => !page.include)\n        : ordered;\n    const currentIndex = filteredBefore.findIndex((page) => page.id === currentPage.id);\n    const nextPageId = currentIndex >= 0\n      ? (filteredBefore[currentIndex + 1]?.id ?? filteredBefore[currentIndex - 1]?.id ?? null)\n      : (filteredBefore[0]?.id ?? null);\n\n    const pages = withPageNumbers(setPageIncludedAtStoredPosition(currentProject.pages, currentPage.id, !currentPage.include));\n    const nextProject = { ...currentProject, pages };\n    setRapidReviewBusy(true);\n    setProjectSync(nextProject);\n    setSaveStatus('saving');\n    setSaveNotice('Saving page review…');\n    await new Promise<void>((resolve) => window.setTimeout(resolve, 700));\n    const saved = await confirmLatestProjectSaved(15000);\n    if (!saved) {\n      setSaveStatus('failed');\n      setSaveNotice('PAGE REVIEW SAVE FAILED · STAYING ON CURRENT PAGE');\n      setRapidReviewBusy(false);\n      return;\n    }\n    if (nextPageId && nextPageId !== currentPage.id) {\n      const target = projectRef.current?.pages.find((page) => page.id === nextPageId);\n      setActivePageId(nextPageId);\n      if (target?.linkedWorksheetId) setSelectedWorksheetId(target.linkedWorksheetId);\n      setSelection(null);\n    }\n    setSaveNotice('PAGE REVIEW SAVED');\n    window.setTimeout(() => setSaveNotice((notice) => notice === 'PAGE REVIEW SAVED' ? '' : notice), 2500);\n    setRapidReviewBusy(false);\n  };\n",
        "App include-save-advance flow",
    )
    text = replace_once(text, "      onSetLineStyle={(style) => setLineStyle(style)}\n    />", "      onSetLineStyle={(style) => setLineStyle(style)}\n      pageFilter={pageFilter}\n      onSetPageFilter={setPageFilter}\n    />", "App Ribbon filter wiring")
    text = replace_once(
        text,
        "          onOpenHelp={() => window.open('/app?help=1', '_blank', 'noopener,noreferrer')}\n          activeTool={activeTool}\n",
        "          onOpenHelp={() => window.open('/app?help=1', '_blank', 'noopener,noreferrer')}\n          reviewPages={reviewPages}\n          pageFilter={pageFilter}\n          rapidReviewBusy={rapidReviewBusy}\n          onNavigateReview={(direction) => { void navigateReviewPage(direction); }}\n          onToggleIncludeAndAdvance={() => { void toggleIncludeAndAdvance(); }}\n          activeTool={activeTool}\n",
        "App DocumentView rapid-review wiring",
    )
    return text


def patch_document_view(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(text, "import type { ViewControls } from './Ribbon';", "import type { PageReviewFilter, ViewControls } from './Ribbon';", "DocumentView filter type import")
    text = replace_once(text, "  onOpenHelp?: () => void;\n}", "  onOpenHelp?: () => void;\n  reviewPages: PageModel[];\n  pageFilter: PageReviewFilter;\n  rapidReviewBusy: boolean;\n  onNavigateReview: (direction: -1 | 1) => void;\n  onToggleIncludeAndAdvance: () => void;\n}", "DocumentView rapid-review props")
    text = replace_once(text, "  onExportPageSource,\n  onOpenHelp,\n}: Props) {", "  onExportPageSource,\n  onOpenHelp,\n  reviewPages,\n  pageFilter,\n  rapidReviewBusy,\n  onNavigateReview,\n  onToggleIncludeAndAdvance,\n}: Props) {", "DocumentView rapid-review destructure")
    text = replace_once(text, "        onPatchPage={(patch) => onPatchPage(activePage.id, patch)}\n        onOpenHelp={onOpenHelp}\n", "        onPatchPage={(patch) => onPatchPage(activePage.id, patch)}\n        onOpenHelp={onOpenHelp}\n        reviewPages={reviewPages}\n        pageFilter={pageFilter}\n        rapidReviewBusy={rapidReviewBusy}\n        onNavigateReview={onNavigateReview}\n        onToggleIncludeAndAdvance={onToggleIncludeAndAdvance}\n", "DocumentView toolbar wiring")
    return text


def patch_viewport_toolbar(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(text, "import type { ViewControls } from './Ribbon';", "import type { PageReviewFilter, ViewControls } from './Ribbon';\nimport { isCoverPage, isSheetIndexPage } from '../model/packageIndex';\nimport '../styles/rapidPageReview.css';", "ViewportToolbar imports")
    text = replace_once(text, "  onOpenHelp?: () => void;\n}", "  onOpenHelp?: () => void;\n  reviewPages: PageModel[];\n  pageFilter: PageReviewFilter;\n  rapidReviewBusy: boolean;\n  onNavigateReview: (direction: -1 | 1) => void;\n  onToggleIncludeAndAdvance: () => void;\n}", "ViewportToolbar rapid-review props")
    text = replace_once(text, "  onPatchPage,\n  onOpenHelp,\n}: Props) {", "  onPatchPage,\n  onOpenHelp,\n  reviewPages,\n  pageFilter,\n  rapidReviewBusy,\n  onNavigateReview,\n  onToggleIncludeAndAdvance,\n}: Props) {", "ViewportToolbar rapid-review destructure")
    text = replace_once(text, "  const displayTitle = viewMode === 'source' && sourceWorksheetName ? sourceWorksheetName : activePage.sheetTitle;\n", "  const displayTitle = viewMode === 'source' && sourceWorksheetName ? sourceWorksheetName : activePage.sheetTitle;\n  // S360 RAPID PAGE REVIEW V35\n  const reviewIndex = reviewPages.findIndex((page) => page.id === activePage.id);\n  const filterLabel = pageFilter === 'included' ? 'Included only' : pageFilter === 'excluded' ? 'Not included' : 'All pages';\n  const filterPosition = reviewIndex >= 0 ? reviewIndex + 1 : 0;\n  const includeLocked = isCoverPage(activePage) || isSheetIndexPage(activePage);\n  const canPrevious = reviewPages.length > 0 && (reviewIndex < 0 || reviewIndex > 0);\n  const canNext = reviewPages.length > 0 && (reviewIndex < 0 || reviewIndex < reviewPages.length - 1);\n", "ViewportToolbar rapid-review derivation")
    text = replace_once(
        text,
        "      <span className=\"vt-spacer\" />\n      <span className=\"sb-item\">{pageLabel}</span>\n      <button className={`fit-btn ${view.fitMode === 'width' ? 'active' : ''}`} onClick={() => view.setFitMode('width')}>Fit Width</button>\n      <button className={`fit-btn ${view.fitMode === 'page' ? 'active' : ''}`} onClick={() => view.setFitMode('page')}>Fit Page</button>\n",
        "      <span className=\"vt-spacer\" />\n      <span className={`vt-page-filter-widget filter-${pageFilter}`}>{filterLabel} · {filterPosition} of {reviewPages.length}</span>\n      <button type=\"button\" className=\"fit-btn vt-review-nav\" disabled={!canPrevious || rapidReviewBusy} onClick={() => onNavigateReview(-1)}>← Previous</button>\n      <button\n        type=\"button\"\n        className={`fit-btn vt-rapid-include ${activePage.include ? 'included' : 'excluded'}`}\n        disabled={includeLocked || rapidReviewBusy}\n        onClick={onToggleIncludeAndAdvance}\n        title={includeLocked ? 'Cover and Sheet Index are required pages' : 'Toggle Include, save automatically, then advance'}\n      >\n        {rapidReviewBusy ? 'Saving…' : `Include in Drawing: ${activePage.include ? 'YES' : 'NO'} →`}\n      </button>\n      <button type=\"button\" className=\"fit-btn vt-review-nav\" disabled={!canNext || rapidReviewBusy} onClick={() => onNavigateReview(1)}>Next →</button>\n      <span className=\"sb-item\">{pageLabel}</span>\n      <button className={`fit-btn ${view.fitMode === 'width' ? 'active' : ''}`} onClick={() => view.setFitMode('width')}>Fit Width</button>\n      <button className={`fit-btn ${view.fitMode === 'page' ? 'active' : ''}`} onClick={() => view.setFitMode('page')}>Fit Page</button>\n",
        "ViewportToolbar rapid-review controls",
    )
    return text


CSS = """/* S360 RAPID PAGE REVIEW V35 */
.viewport-toolbar { flex-wrap: wrap; height: auto; min-height: 36px; gap: 4px; overflow: visible; }
.vt-page-filter-widget { display: inline-flex; align-items: center; min-height: 26px; padding: 0 10px; border-radius: 999px; border: 1px solid #64748b; background: #e2e8f0; color: #0f172a; font-weight: 800; font-size: 11px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.vt-page-filter-widget.filter-included { background: #dcfce7; border-color: #16a34a; color: #14532d; }
.vt-page-filter-widget.filter-excluded { background: #fee2e2; border-color: #dc2626; color: #7f1d1d; }
.vt-review-nav { font-weight: 800; }
.vt-rapid-include { min-width: 172px; font-weight: 900; border-width: 2px; }
.vt-rapid-include.included { background: #15803d; border-color: #166534; color: #fff; }
.vt-rapid-include.excluded { background: #b91c1c; border-color: #7f1d1d; color: #fff; }
.vt-rapid-include:disabled { opacity: .58; cursor: not-allowed; }
@media (max-width: 1500px) { .viewport-toolbar .vt-label { flex-basis: min(100%, 520px); } .viewport-toolbar .vt-spacer { display: none; } }
"""


def apply(repo: Path) -> list[str]:
    changed: list[str] = []
    for relative, transform in [
        ("frontend/src/App.tsx", patch_app),
        ("frontend/src/components/Ribbon.tsx", patch_ribbon),
        ("frontend/src/components/DocumentView.tsx", patch_document_view),
        ("frontend/src/components/ViewportToolbar.tsx", patch_viewport_toolbar),
    ]:
        path = repo / relative
        if not path.is_file():
            raise PatchError(f"Missing target: {relative}")
        if patch_file(path, transform):
            changed.append(relative)
    css_path = repo / "frontend/src/styles/rapidPageReview.css"
    if not css_path.exists() or css_path.read_text(encoding="utf-8") != CSS:
        css_path.write_text(CSS, encoding="utf-8", newline="\n")
        changed.append("frontend/src/styles/rapidPageReview.css")
    return changed


def verify(repo: Path) -> None:
    checks = {
        "frontend/src/App.tsx": [MARKER, "toggleIncludeAndAdvance", "reviewPages={reviewPages}"],
        "frontend/src/components/Ribbon.tsx": [MARKER, "Included Only", "Not Included"],
        "frontend/src/components/DocumentView.tsx": ["reviewPages: PageModel[]", "onToggleIncludeAndAdvance"],
        "frontend/src/components/ViewportToolbar.tsx": [MARKER, "Include in Drawing:", "vt-page-filter-widget"],
        "frontend/src/styles/rapidPageReview.css": [MARKER, ".vt-rapid-include"],
    }
    for relative, tokens in checks.items():
        text = (repo / relative).read_text(encoding="utf-8")
        missing = [token for token in tokens if token not in text]
        if missing:
            raise PatchError(f"{relative}: missing verification tokens {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    if args.check:
        verify(repo)
        print("Rapid Page Review V35 verification passed")
        return 0
    changed = apply(repo)
    verify(repo)
    print(f"Rapid Page Review V35 applied; changed {len(changed)} file(s)")
    for item in changed:
        print(item)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"PATCH ERROR: {exc}")
        raise SystemExit(2)
