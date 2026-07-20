"""Install the generated Singh360 Sheet Index standard and repair one project.

The source workbook/worksheet remains intact and visible in Source view. The
Normalized/PDF Sheet Index is generated from the current included PageModel
list, so excluded/internal pages never appear and the index stays synchronized
with page order, sheet codes, titles, and include flags.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ID = "4acaef6006dd4620"

SOURCE_PATHS = (
    Path("frontend/src/App.tsx"),
    Path("frontend/src/components/renderers/GeneratedIndexRenderer.tsx"),
    Path("frontend/src/model/packageIndex.ts"),
    Path("frontend/src/styles/sheet.css"),
)

PACKAGE_INDEX_TS = r"""import type { PageModel } from './types';

function cleanText(value: unknown): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function pageHaystack(page: PageModel): string {
  return cleanText([
    page.sheetTitle,
    page.sheetTab,
    page.sourceSheet,
    page.displaySheetCode,
    page.sheetCode,
  ].filter(Boolean).join(' ')).toLowerCase();
}

export function isSheetIndexPage(page: PageModel): boolean {
  if (page.pageType === 'index') return true;
  const hay = pageHaystack(page);
  return hay.includes('sheet index')
    || hay.includes('table of contents')
    || /(^|\s)toc($|\s|\/)/i.test(hay);
}

export function isCoverPage(page: PageModel): boolean {
  if (page.pageType === 'cover') return true;
  const hay = pageHaystack(page);
  return hay.includes('cover / project info')
    || hay.includes('cover project info')
    || hay.includes('title sheet');
}

function currentCode(page: PageModel | undefined): string {
  return cleanText(page?.displaySheetCode || page?.sheetCode || '');
}

function inferIndexCode(cover: PageModel | undefined, index: PageModel): string {
  const existing = currentCode(index);
  const coverCode = currentCode(cover);
  if (existing && existing.toLowerCase() !== coverCode.toLowerCase()) return existing;

  const match = coverCode.match(/^(.+?)\s+\d+(?:\.\d+)?[a-z]?$/i);
  const prefix = cleanText(match?.[1] || 'EMS');
  return `${prefix || 'EMS'} 2.0`;
}

/** User-facing type text for the generated index; no internal render/profile data. */
export function indexPageTypeLabel(page: PageModel): string {
  const hay = pageHaystack(page);
  if (isCoverPage(page)) return 'Cover';
  if (isSheetIndexPage(page)) return 'Sheet Index';
  if (hay.includes('company info')) return 'Company Info';
  if (hay.includes('schematic') || hay.includes('wiring diagram')) return 'PDF / Layout';
  if (
    page.pageType === 'canvas'
    || page.pageType === 'underlay'
    || page.pageType === 'hybrid'
    || hay.includes('device location')
    || hay.includes('overall layout')
  ) return 'Image / Layout';

  const blockTypes = new Set((page.blocks ?? []).map((block) => block.type));
  if (blockTypes.has('idfNetworkTable')) return 'Network Table';
  if (blockTypes.has('matrix')) return 'Matrix';
  if (blockTypes.has('table') || blockTypes.has('excelRange')) return 'Table / Schedule';
  return 'Text / Instructions';
}

/** Remove importer/internal boilerplate while preserving real user-entered notes. */
export function cleanIndexNote(page: PageModel): string {
  const note = cleanText(page.notes);
  if (!note || note === '—' || note === '-' || note.toLowerCase() === 'nts') return '';
  const low = note.toLowerCase();
  const boilerplate = [
    'internal build tracker',
    'not exported unless intentionally included',
    'insert/crop pdf schematic',
    'manual plan/device location page',
    'manual floor-plan/underlay work in app',
    'manual layout page for singh360 draft',
  ];
  if (boilerplate.some((phrase) => low.includes(phrase))) return '';
  return note;
}

function stableOrder(pages: PageModel[]): PageModel[] {
  return pages
    .map((page, index) => ({ page, index }))
    .sort((a, b) => {
      const ao = Number.isFinite(a.page.order) ? a.page.order : a.index + 1;
      const bo = Number.isFinite(b.page.order) ? b.page.order : b.index + 1;
      return ao - bo || a.index - b.index;
    })
    .map(({ page }) => ({ ...page }));
}

/**
 * Canonical package arrangement:
 *   1. Cover is the first included page.
 *   2. Sheet Index is the second included page and always included.
 *   3. Remaining included pages stay in their current relative order.
 *   4. Excluded/internal pages remain available, but move after package pages.
 *   5. Every included physical page (including continuations) gets a unique
 *      Page X of Y number. Therefore Order == Page for included pages.
 *
 * The linked worksheet is never changed, so Source view still shows every raw
 * index row and column.
 */
export function normalizePackagePages(input: PageModel[]): PageModel[] {
  const ordered = stableOrder(input ?? []);
  const cover = ordered.find(isCoverPage);
  const index = ordered.find(isSheetIndexPage);
  const reserved = new Set([cover?.id, index?.id].filter(Boolean) as string[]);
  const remaining = ordered.filter((page) => !reserved.has(page.id));
  const includedRest = remaining.filter((page) => page.include !== false);
  const excludedRest = remaining.filter((page) => page.include === false);

  let arranged: PageModel[] = [];
  if (cover) arranged.push({ ...cover, include: true });
  if (index) {
    const code = inferIndexCode(cover, index);
    arranged.push({
      ...index,
      include: true,
      pageType: 'index',
      renderMode: 'generated_index',
      normalizedHeaderStyle: 'orange',
      sheetCode: code,
      displaySheetCode: code,
      sheetTitle: cleanText(index.sheetTitle) || 'Sheet Index / TOC',
      sheetTab: cleanText(index.sheetTab) || 'Sheet Index',
    });
  }
  arranged.push(...includedRest, ...excludedRest);

  if (!cover && !index) arranged = [...includedRest, ...excludedRest];

  const total = arranged.filter((page) => page.include !== false).length;
  let pageNumber = 0;
  return arranged.map((page, indexPosition) => {
    if (page.include === false) {
      return { ...page, order: indexPosition + 1, pageNumber: null, pageTotal: total };
    }
    pageNumber += 1;
    return { ...page, order: indexPosition + 1, pageNumber, pageTotal: total };
  });
}
"""

GENERATED_INDEX_TSX = r"""import { useEffect, useMemo } from 'react';
import type { PageModel, ProjectModel } from '../../model/types';
import { cleanIndexNote, indexPageTypeLabel } from '../../model/packageIndex';

interface Props {
  project: ProjectModel;
  page: PageModel;
  onPatchPage: (pageId: string, patch: Partial<PageModel>) => void;
}

/**
 * Clean generated Sheet Index / TOC.
 *
 * Normalized/PDF output is built from the CURRENT included pages. The linked
 * workbook worksheet remains untouched and fully visible/editable in Source.
 * Internal/excluded pages and internal-only columns never appear here.
 */
export default function GeneratedIndexRenderer({ project, onPatchPage }: Props) {
  const included = useMemo(
    () => [...(project.pages ?? [])]
      .filter((page) => page.include !== false)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [project.pages],
  );

  const commitCode = (target: PageModel, value: string) => {
    const next = value.trim();
    onPatchPage(target.id, { sheetCode: next, displaySheetCode: next });
  };

  const commitTitle = (target: PageModel, value: string) => {
    onPatchPage(target.id, { sheetTitle: value.trim() || 'Untitled Sheet' });
  };

  const onKeyDown = (
    e: React.KeyboardEvent<HTMLElement>,
    target: PageModel,
    field: 'code' | 'title',
  ) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const value = e.currentTarget.textContent ?? '';
      if (field === 'code') commitCode(target, value);
      else commitTitle(target, value);
      e.currentTarget.blur();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.currentTarget.textContent = field === 'code'
        ? (target.displaySheetCode || target.sheetCode || '')
        : target.sheetTitle;
      e.currentTarget.blur();
    }
  };

  useEffect(() => {
    const capture = () => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || !el.isContentEditable || !el.closest('.np-index-table')) return;
      const pageId = el.dataset.pageId ?? '';
      const field = el.dataset.field as 'code' | 'title' | undefined;
      const target = included.find((page) => page.id === pageId);
      if (!target || !field) return;
      const value = el.textContent ?? '';
      if (field === 'code') commitCode(target, value);
      else commitTitle(target, value);
    };
    document.addEventListener('singh360:capture-active-editors', capture);
    return () => document.removeEventListener('singh360:capture-active-editors', capture);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [included, onPatchPage]);

  if (!included.length) {
    return <div className="np-index np-empty">No included sheets.</div>;
  }

  const compact = included.length > 28 ? ' ni-compact' : '';

  return (
    <div className="np-index">
      <table className={`np-index-table${compact}`}>
        <thead>
          <tr>
            <th className="ni-pg">Page</th>
            <th className="ni-code">Sheet Code</th>
            <th className="ni-tab">Sheet Tab</th>
            <th className="ni-title">Page Title</th>
            <th className="ni-type">Page Type</th>
            <th className="ni-notes">Notes</th>
          </tr>
        </thead>
        <tbody>
          {included.map((page) => (
            <tr key={page.id} className={page.generatedContinuation ? 'ni-cont' : ''}>
              <td className="ni-pg">{page.pageNumber ?? '—'}</td>
              <td
                className="ni-code"
                contentEditable
                suppressContentEditableWarning
                tabIndex={0}
                data-page-id={page.id}
                data-field="code"
                title="Edit the actual sheet code. Enter commits; Esc cancels."
                onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onBlur={(e) => commitCode(page, e.currentTarget.textContent ?? '')}
                onKeyDown={(e) => onKeyDown(e, page, 'code')}
              >
                {page.displaySheetCode || page.sheetCode || '—'}
              </td>
              <td className="ni-tab">{page.sheetTab || '—'}</td>
              <td
                className="ni-title"
                contentEditable
                suppressContentEditableWarning
                tabIndex={0}
                data-page-id={page.id}
                data-field="title"
                title="Edit the actual page title. Enter commits; Esc cancels."
                onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onBlur={(e) => commitTitle(page, e.currentTarget.textContent ?? '')}
                onKeyDown={(e) => onKeyDown(e, page, 'title')}
              >
                {page.sheetTitle}
                {page.generatedContinuation && <span className="ni-cont-mark"> — CONTINUED</span>}
              </td>
              <td className="ni-type">{indexPageTypeLabel(page)}</td>
              <td className="ni-notes">{cleanIndexNote(page)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
"""

CSS_BLOCK = r"""
/* SINGH360 GENERATED INDEX STANDARD START */
.np-index {
  padding: 22px 34px;
}
.np-index-table {
  width: 100%;
  table-layout: fixed;
  font-size: 11.5px;
}
.np-index-table th {
  padding: 5px 6px;
  font-size: 10px;
  white-space: nowrap;
}
.np-index-table td {
  padding: 4px 6px;
  line-height: 1.15;
  overflow: hidden;
  text-overflow: ellipsis;
}
.np-index-table .ni-pg {
  width: 50px;
  text-align: center;
  font-family: inherit;
  font-weight: 700;
}
.np-index-table .ni-code {
  width: 104px;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 10.5px;
  font-weight: 700;
}
.np-index-table .ni-tab { width: 190px; }
.np-index-table .ni-title { width: 280px; }
.np-index-table .ni-type { width: 140px; }
.np-index-table .ni-notes { width: auto; color: #4a525b; }
.np-index-table td[contenteditable="true"]:focus {
  outline: 2px solid #246fb4;
  outline-offset: -2px;
  background: #eef7ff;
}
.np-index-table.ni-compact {
  font-size: 9.5px;
}
.np-index-table.ni-compact th,
.np-index-table.ni-compact td {
  padding: 2px 4px;
  line-height: 1.05;
}
/* SINGH360 GENERATED INDEX STANDARD END */
"""

APP_IMPORT = "import { isSheetIndexPage, normalizePackagePages } from './model/packageIndex';"

APP_NUMBERING = """// Canonical package order + live Page X of Y. This also keeps the generated
// Sheet Index second, moves excluded/internal pages after package pages, and
// counts every included physical continuation page.
function withPageNumbers(pages: PageModel[]): PageModel[] {
  return normalizePackagePages(pages);
}"""

APP_SET_PROJECT = """  const setProjectSync = useCallback((updater: ProjectModel | null | ((prev: ProjectModel | null) => ProjectModel | null)) => {
    const rawNext = typeof updater === 'function'
      ? (updater as (prev: ProjectModel | null) => ProjectModel | null)(projectRef.current)
      : updater;
    const next = rawNext
      ? { ...rawNext, pages: normalizePackagePages(rawNext.pages ?? []) }
      : rawNext;
    projectRef.current = next;
    setProject(next);
    return next;
  }, []);"""

APP_DELETE_GUARD = """  const deletePage = (id: string) => {
    const target = projectRef.current?.pages.find((page) => page.id === id);
    if (target && isSheetIndexPage(target)) {
      window.alert('The Sheet Index / TOC is required and cannot be deleted. Excluded pages are removed from it automatically.');
      return;
    }
    if (!window.confirm('Delete this page? This cannot be undone. (Tip: use Exclude to keep it out of the package instead.)')) return;
    if (activePageId === id) {
      const remaining = project?.pages.filter((p) => p.id !== id) ?? [];
      setActivePageId(remaining[0]?.id ?? null);
    }
    mutatePages((pages) => pages.filter((p) => p.id !== id));
  };"""


class PatchError(RuntimeError):
    pass


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _page_hay(page: dict[str, Any]) -> str:
    return _norm(" ".join(str(page.get(key) or "") for key in (
        "sheetTitle", "sheetTab", "sourceSheet", "displaySheetCode", "sheetCode"
    )))


def _is_cover(page: dict[str, Any]) -> bool:
    if str(page.get("pageType") or "").lower() == "cover":
        return True
    hay = _page_hay(page)
    return (
        "cover / project info" in hay
        or "cover project info" in hay
        or "title sheet" in hay
    )


def _is_index(page: dict[str, Any]) -> bool:
    if str(page.get("pageType") or "").lower() == "index":
        return True
    hay = _page_hay(page)
    return (
        "sheet index" in hay
        or "table of contents" in hay
        or re.search(r"(^|\s)toc($|\s|/)", hay) is not None
    )


def _code(page: dict[str, Any] | None) -> str:
    if not page:
        return ""
    return str(page.get("displaySheetCode") or page.get("sheetCode") or "").strip()


def _infer_index_code(cover: dict[str, Any] | None, index: dict[str, Any]) -> str:
    existing = _code(index)
    cover_code = _code(cover)
    if existing and existing.lower() != cover_code.lower():
        return existing
    match = re.match(r"^(.+?)\s+\d+(?:\.\d+)?[a-z]?$", cover_code, re.I)
    prefix = (match.group(1).strip() if match else "EMS") or "EMS"
    return f"{prefix} 2.0"


def normalize_project_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [
        copy.deepcopy(page)
        for _, page in sorted(
            enumerate(pages),
            key=lambda item: (
                int(item[1].get("order") or item[0] + 1),
                item[0],
            ),
        )
        if isinstance(page, dict)
    ]
    cover = next((page for page in ordered if _is_cover(page)), None)
    index = next((page for page in ordered if _is_index(page)), None)
    reserved = {
        str(page.get("id") or "")
        for page in (cover, index)
        if page
    }
    remaining = [
        page for page in ordered
        if str(page.get("id") or "") not in reserved
    ]
    included_rest = [page for page in remaining if page.get("include") is not False]
    excluded_rest = [page for page in remaining if page.get("include") is False]

    arranged: list[dict[str, Any]] = []
    if cover:
        cover["include"] = True
        arranged.append(cover)
    if index:
        code = _infer_index_code(cover, index)
        index.update({
            "include": True,
            "pageType": "index",
            "renderMode": "generated_index",
            "normalizedHeaderStyle": "orange",
            "sheetCode": code,
            "displaySheetCode": code,
            "sheetTitle": str(index.get("sheetTitle") or "").strip() or "Sheet Index / TOC",
            "sheetTab": str(index.get("sheetTab") or "").strip() or "Sheet Index",
        })
        arranged.append(index)
    arranged.extend(included_rest)
    arranged.extend(excluded_rest)

    if not cover and not index:
        arranged = included_rest + excluded_rest

    total = sum(1 for page in arranged if page.get("include") is not False)
    number = 0
    for position, page in enumerate(arranged, start=1):
        page["order"] = position
        page["pageTotal"] = total
        if page.get("include") is False:
            page["pageNumber"] = None
        else:
            number += 1
            page["pageNumber"] = number
    return arranged


def _backup_sources(repo: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = repo / ".docs" / "patch_backups" / f"generated_sheet_index_source_{stamp}"
    for rel in SOURCE_PATHS:
        source = repo / rel
        if source.is_file():
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    return backup


def restore_latest_source_backup(repo: Path) -> Path:
    root = repo / ".docs" / "patch_backups"
    candidates = sorted(
        (path for path in root.glob("generated_sheet_index_source_*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise PatchError("No generated Sheet Index source backup was found.")
    backup = candidates[0]
    for rel in SOURCE_PATHS:
        source = backup / rel
        target = repo / rel
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.is_file() and rel == Path("frontend/src/model/packageIndex.ts"):
            target.unlink()
    print(f"[OK] Restored source files from {backup}")
    return backup


def _replace_app(app: str) -> str:
    if APP_IMPORT not in app:
        marker = "import { validatePageRebuild } from './model/pageRebuildValidation';"
        if marker not in app:
            raise PatchError("Could not locate App import marker.")
        app = app.replace(marker, marker + "\n" + APP_IMPORT, 1)

    number_pattern = re.compile(
        r"// Recompute live .*?\nfunction withPageNumbers\(pages: PageModel\[\]\): PageModel\[\] \{.*?\n\}\n\nexport default function App",
        re.S,
    )
    if "return normalizePackagePages(pages);" not in app:
        if not number_pattern.search(app):
            raise PatchError("Could not locate withPageNumbers in App.tsx.")
        app = number_pattern.sub(APP_NUMBERING + "\n\nexport default function App", app, count=1)

    if "const rawNext = typeof updater === 'function'" not in app:
        start = app.find("  const setProjectSync = useCallback(")
        if start < 0:
            raise PatchError("Could not locate setProjectSync in App.tsx.")
        end_marker = "\n  }, []);"
        end = app.find(end_marker, start)
        if end < 0:
            raise PatchError("Could not locate end of setProjectSync in App.tsx.")
        end += len(end_marker)
        app = app[:start] + APP_SET_PROJECT + app[end:]

    if "The Sheet Index / TOC is required and cannot be deleted." not in app:
        start = app.find("  const deletePage = (id: string) => {")
        if start < 0:
            raise PatchError("Could not locate deletePage in App.tsx.")
        end_marker = "\n  };"
        end = app.find(end_marker, start)
        if end < 0:
            raise PatchError("Could not locate end of deletePage in App.tsx.")
        end += len(end_marker)
        app = app[:start] + APP_DELETE_GUARD + app[end:]

    for required in (
        APP_IMPORT,
        "return normalizePackagePages(pages);",
        "pages: normalizePackagePages(rawNext.pages ?? [])",
        "The Sheet Index / TOC is required and cannot be deleted.",
    ):
        if required not in app:
            raise PatchError(f"App.tsx verification failed: {required}")
    return app


def patch_sources(repo: Path) -> dict[str, Any]:
    backup = _backup_sources(repo)
    changed: list[str] = []
    try:
        package_path = repo / "frontend/src/model/packageIndex.ts"
        package_path.parent.mkdir(parents=True, exist_ok=True)
        old = package_path.read_text("utf-8") if package_path.is_file() else ""
        if old != PACKAGE_INDEX_TS:
            package_path.write_text(PACKAGE_INDEX_TS, encoding="utf-8")
            changed.append(str(package_path.relative_to(repo)))

        renderer_path = repo / "frontend/src/components/renderers/GeneratedIndexRenderer.tsx"
        old = renderer_path.read_text("utf-8")
        if old != GENERATED_INDEX_TSX:
            renderer_path.write_text(GENERATED_INDEX_TSX, encoding="utf-8")
            changed.append(str(renderer_path.relative_to(repo)))

        css_path = repo / "frontend/src/styles/sheet.css"
        css = css_path.read_text("utf-8")
        marker_re = re.compile(
            r"\n?/\* SINGH360 GENERATED INDEX STANDARD START \*/.*?/\* SINGH360 GENERATED INDEX STANDARD END \*/\n?",
            re.S,
        )
        next_css = marker_re.sub("\n", css).rstrip() + "\n" + CSS_BLOCK.strip() + "\n"
        if next_css != css:
            css_path.write_text(next_css, encoding="utf-8")
            changed.append(str(css_path.relative_to(repo)))

        app_path = repo / "frontend/src/App.tsx"
        app = app_path.read_text("utf-8")
        next_app = _replace_app(app)
        if next_app != app:
            app_path.write_text(next_app, encoding="utf-8")
            changed.append(str(app_path.relative_to(repo)))

        print(f"[OK] Source backup: {backup}")
        for path in changed:
            print(f"[OK] Patched {path}")
        if not changed:
            print("[OK] Generated Sheet Index source was already installed.")
        return {"backup": str(backup), "changed": changed}
    except Exception:
        for rel in SOURCE_PATHS:
            source = backup / rel
            target = repo / rel
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif target.is_file() and rel == Path("frontend/src/model/packageIndex.ts"):
                target.unlink()
        raise


def apply_project(repo: Path, project_id: str) -> dict[str, Any]:
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from core.project_store import ProjectStore

    store = ProjectStore(repo / ".docs")
    project = store.load(project_id)
    if not project:
        raise PatchError(f"Project {project_id} was not found.")
    current_path = store.read_path(project_id)
    if not current_path:
        raise PatchError(f"Could not locate project.json for {project_id}.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = repo / ".docs" / "patch_backups" / f"generated_sheet_index_project_{project_id}_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_path, backup / "project.json")

    original_pages = project.get("pages")
    if not isinstance(original_pages, list):
        raise PatchError("Project pages are missing or invalid.")
    next_pages = normalize_project_pages(original_pages)

    cover = next((page for page in next_pages if _is_cover(page)), None)
    index = next((page for page in next_pages if _is_index(page)), None)
    if not cover or not index:
        raise PatchError("Could not prove both Cover and Sheet Index pages exist.")
    if next_pages[0].get("id") != cover.get("id") or next_pages[1].get("id") != index.get("id"):
        raise PatchError("Cover/Index ordering verification failed.")
    if index.get("include") is False or index.get("pageType") != "index":
        raise PatchError("Sheet Index inclusion/type verification failed.")
    if index.get("renderMode") == "excel_exact":
        raise PatchError("Sheet Index still uses raw Excel rendering.")
    included = [page for page in next_pages if page.get("include") is not False]
    expected = list(range(1, len(included) + 1))
    actual = [page.get("pageNumber") for page in included]
    if actual != expected:
        raise PatchError(f"Page numbering verification failed: {actual}")
    if any(int(page.get("order") or 0) != int(page.get("pageNumber") or 0) for page in included):
        raise PatchError("Included Order does not match Page number.")

    project["pages"] = next_pages
    project["lastSavedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    saved = store.save(project_id, project)

    print(f"[OK] Project safety backup: {backup}")
    print(f"[OK] Saved project: {saved}")
    print(f"[OK] Page 1: {_code(cover)} — {cover.get('sheetTitle')}")
    print(f"[OK] Page 2: {_code(index)} — {index.get('sheetTitle')}")
    print(f"[OK] Included package pages: {len(included)}")
    print(f"[OK] Excluded/internal pages omitted from generated index: {len(next_pages) - len(included)}")
    return {
        "backup": str(backup),
        "saved": str(saved),
        "included": len(included),
        "excluded": len(next_pages) - len(included),
        "coverCode": _code(cover),
        "indexCode": _code(index),
    }


def self_test() -> None:
    pages = [
        {
            "id": "internal", "order": 1, "include": False,
            "sheetCode": "EMS 0.3", "displaySheetCode": "EMS 0.3",
            "sheetTitle": "Drawing Build - Check", "sheetTab": "EMS 0.3",
            "pageType": "data-grid",
        },
        {
            "id": "index", "order": 2, "include": True,
            "sheetCode": "EMS 1.0", "displaySheetCode": "EMS 1.0",
            "sheetTitle": "Sheet Index / TOC", "sheetTab": "EMS 2.0 Sheet Index",
            "pageType": "data-grid", "renderMode": "excel_exact",
            "linkedWorksheetId": "ws_index",
        },
        {
            "id": "cover", "order": 3, "include": True,
            "sheetCode": "EMS 1.0", "displaySheetCode": "EMS 1.0",
            "sheetTitle": "Cover / Project Info", "sheetTab": "EMS 1.0 Cover",
            "pageType": "cover",
        },
        {
            "id": "a", "order": 4, "include": True,
            "sheetCode": "EMS 3.0", "displaySheetCode": "EMS 3.0",
            "sheetTitle": "Guidelines", "sheetTab": "EMS 3.0",
            "pageType": "data-grid",
        },
        {
            "id": "cont", "order": 5, "include": True,
            "sheetCode": "EMS 3.0a", "displaySheetCode": "EMS 3.0a",
            "sheetTitle": "Guidelines Continued", "sheetTab": "EMS 3.0a",
            "pageType": "data-grid", "continuationOf": "a",
        },
    ]
    result = normalize_project_pages(pages)
    assert [page["id"] for page in result] == ["cover", "index", "a", "cont", "internal"]
    assert result[1]["pageType"] == "index"
    assert result[1]["renderMode"] == "generated_index"
    assert result[1]["displaySheetCode"] == "EMS 2.0"
    assert [page["pageNumber"] for page in result[:4]] == [1, 2, 3, 4]
    assert result[4]["pageNumber"] is None
    assert result[1]["linkedWorksheetId"] == "ws_index"
    print("[OK] Generated index order, exclusion, source-link, and continuation numbering self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--patch-source", action="store_true")
    parser.add_argument("--apply-project", action="store_true")
    parser.add_argument("--restore-latest", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if args.self_test:
        self_test()
        return 0
    if not (repo / "server.py").is_file():
        raise PatchError(f"Singh360 repository not found: {repo}")
    if args.restore_latest:
        restore_latest_source_backup(repo)
        return 0

    if not args.patch_source and not args.apply_project:
        args.patch_source = True
        args.apply_project = True

    if args.patch_source:
        patch_sources(repo)
    if args.apply_project:
        apply_project(repo, args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
