"""Install published/draft labels and exact Sheet Index note synchronization.

This patch is intentionally source-only:
- Published Sheet Index notes use the same PageModel.notes value as the title block.
- NTS and every other nonblank page note are preserved.
- Sheet Tab remains in the Draft/source worksheet but is omitted from Published/PDF.
- User-facing view labels become Published and Draft.
- No workbook or project JSON is changed.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = (
    Path("frontend/src/model/packageIndex.ts"),
    Path("frontend/src/components/renderers/GeneratedIndexRenderer.tsx"),
    Path("frontend/src/components/ViewportToolbar.tsx"),
    Path("frontend/src/App.tsx"),
    Path("frontend/src/styles/sheet.css"),
)

CSS_MARKER_START = "/* SINGH360 PUBLISHED INDEX NOTES + DRAFT LABELS START */"
CSS_MARKER_END = "/* SINGH360 PUBLISHED INDEX NOTES + DRAFT LABELS END */"
CSS_BLOCK = r"""
/* SINGH360 PUBLISHED INDEX NOTES + DRAFT LABELS START */
/* Sheet Tab stays in Draft/source data but is intentionally omitted from the
   Published/PDF Sheet Index. Give that space to the actual title and notes. */
.np-index-table .ni-title { width: 370px; }
.np-index-table .ni-type { width: 145px; }
.np-index-table .ni-notes {
  width: auto;
  color: #303941;
}
.np-index-table td.ni-notes {
  white-space: normal;
  overflow-wrap: anywhere;
  text-overflow: clip;
}
/* SINGH360 PUBLISHED INDEX NOTES + DRAFT LABELS END */
""".strip()


class PatchError(RuntimeError):
    pass


def backup_files(repo: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = repo / ".docs" / "patch_backups" / f"published_draft_index_notes_{stamp}"
    for rel in FILES:
        src = repo / rel
        if not src.is_file():
            raise PatchError(f"Required source file is missing: {src}")
        dst = backup / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return backup


def restore_backup(repo: Path, backup: Path) -> None:
    for rel in FILES:
        src = backup / rel
        if src.is_file():
            dst = repo / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one marker, found {count}.")
    return text.replace(old, new, 1)


def patch_package_index(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    replacement = """export function cleanIndexNote(page: PageModel): string {
  const note = cleanText(page.notes);
  // Published index notes must match the title block. Only truly blank/dash
  // placeholders are suppressed; NTS and real page notes are preserved.
  if (!note || note === '—' || note === '-') return '';
  return note;
}"""
    pattern = re.compile(
        r"export function cleanIndexNote\(page: PageModel\): string \{.*?\n\}\n\nfunction stableOrder",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        if replacement in text:
            return
        raise PatchError("packageIndex.ts: cleanIndexNote function was not found.")
    text = text[:match.start()] + replacement + "\n\nfunction stableOrder" + text[match.end():]
    path.write_text(text, encoding="utf-8")


def patch_generated_index(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        " * Normalized/PDF output is built from the CURRENT included pages. The linked\n"
        " * workbook worksheet remains untouched and fully visible/editable in Source.\n",
        " * Published/PDF output is built from the CURRENT included pages. The linked\n"
        " * workbook worksheet remains untouched and fully visible/editable in Draft.\n",
    )
    text = text.replace('            <th className="ni-tab">Sheet Tab</th>\n', '')
    text = text.replace("              <td className=\"ni-tab\">{page.sheetTab || '—'}</td>\n", '')
    if 'className="ni-tab"' in text:
        raise PatchError("GeneratedIndexRenderer.tsx: Sheet Tab column was not fully removed.")
    if text.count("<th ") != 5:
        raise PatchError("GeneratedIndexRenderer.tsx: Published index must have exactly five columns.")
    path.write_text(text, encoding="utf-8")


def patch_viewport_toolbar(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        ">Normalized</button>",
        ">Published</button>",
        "ViewportToolbar Published label",
    )
    text = replace_once(
        text,
        ">Source</button>",
        ">Draft</button>",
        "ViewportToolbar Draft label",
    )
    text = replace_once(
        text,
        "title=\"Rebuild this page's normalized output from the linked source worksheet\"",
        "title=\"Rebuild this Published page from the linked Draft worksheet\"",
        "ViewportToolbar rebuild tooltip",
    )
    text = replace_once(
        text,
        "Rebuild This Page From Source",
        "Rebuild Published Page From Draft",
        "ViewportToolbar rebuild button",
    )
    path.write_text(text, encoding="utf-8")


def patch_app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("return 'Source edited';", "return 'Draft edited';")
    text = text.replace("return 'Normalized updated';", "return 'Published updated';")
    text = text.replace(
        "return 'Rebuild failed validation — current page kept';",
        "return 'Draft rebuild failed validation — current Published page kept';",
    )
    if "'Source edited'" in text or "'Normalized updated'" in text:
        raise PatchError("App.tsx: old user-facing Source/Normalized status labels remain.")
    path.write_text(text, encoding="utf-8")


def patch_css(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        re.escape(CSS_MARKER_START) + r".*?" + re.escape(CSS_MARKER_END),
        "",
        text,
        flags=re.DOTALL,
    ).rstrip()
    text += "\n\n" + CSS_BLOCK + "\n"
    path.write_text(text, encoding="utf-8")


def validate(repo: Path) -> None:
    package = (repo / FILES[0]).read_text(encoding="utf-8")
    index = (repo / FILES[1]).read_text(encoding="utf-8")
    toolbar = (repo / FILES[2]).read_text(encoding="utf-8")
    app = (repo / FILES[3]).read_text(encoding="utf-8")
    css = (repo / FILES[4]).read_text(encoding="utf-8")

    checks = {
        "NTS notes preserved": "note.toLowerCase() === 'nts'" not in package,
        "boilerplate notes not specially suppressed": "const boilerplate" not in package,
        "Sheet Tab omitted from Published index": 'className="ni-tab"' not in index,
        "Published view label": ">Published</button>" in toolbar,
        "Draft view label": ">Draft</button>" in toolbar,
        "Draft rebuild label": "Rebuild Published Page From Draft" in toolbar,
        "Draft status label": "'Draft edited'" in app,
        "Published status label": "'Published updated'" in app,
        "Published notes CSS": CSS_MARKER_START in css and CSS_MARKER_END in css,
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"[{'OK' if ok else 'FAIL'}] {name}")
    if failed:
        raise PatchError("Validation failed: " + ", ".join(failed))


def apply_patch(repo: Path) -> Path:
    repo = repo.resolve()
    backup = backup_files(repo)
    try:
        patch_package_index(repo / FILES[0])
        patch_generated_index(repo / FILES[1])
        patch_viewport_toolbar(repo / FILES[2])
        patch_app(repo / FILES[3])
        patch_css(repo / FILES[4])
        validate(repo)
    except Exception:
        restore_backup(repo, backup)
        raise
    print(f"[OK] Source backup: {backup}")
    return backup


def latest_backup(repo: Path) -> Path:
    root = repo / ".docs" / "patch_backups"
    backups = sorted(
        (p for p in root.glob("published_draft_index_notes_*") if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    if not backups:
        raise PatchError("No published/draft index-note backup was found.")
    return backups[0]


def restore_latest(repo: Path) -> None:
    backup = latest_backup(repo)
    restore_backup(repo, backup)
    print(f"[OK] Restored source files from: {backup}")


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        fixtures = {
            FILES[0]: """import type { PageModel } from './types';
function cleanText(value: unknown): string { return String(value ?? '').trim(); }
/** Remove importer/internal boilerplate while preserving real user-entered notes. */
export function cleanIndexNote(page: PageModel): string {
  const note = cleanText(page.notes);
  if (!note || note === '—' || note === '-' || note.toLowerCase() === 'nts') return '';
  const low = note.toLowerCase();
  const boilerplate = [
    'internal build tracker',
    'manual floor-plan/underlay work in app',
  ];
  if (boilerplate.some((phrase) => low.includes(phrase))) return '';
  return note;
}

function stableOrder() { return []; }
""",
            FILES[1]: """export default function X() {
return (<table className="np-index-table"><thead><tr>
            <th className="ni-pg">Page</th>
            <th className="ni-code">Sheet Code</th>
            <th className="ni-tab">Sheet Tab</th>
            <th className="ni-title">Page Title</th>
            <th className="ni-type">Page Type</th>
            <th className="ni-notes">Notes</th>
</tr></thead><tbody><tr>
              <td className="ni-tab">{page.sheetTab || '—'}</td>
</tr></tbody></table>);
}
""",
            FILES[2]: """<button>Normalized</button>
<button>Source</button>
<button title="Rebuild this page's normalized output from the linked source worksheet">
Rebuild This Page From Source
</button>
""",
            FILES[3]: """if (x) return 'Source edited';
if (y) return 'Normalized updated';
if (z) return 'Rebuild failed validation — current page kept';
if (a) return 'Source edited';
""",
            FILES[4]: """.np-index-table .ni-tab { width: 190px; }
.np-index-table .ni-title { width: 280px; }
""",
        }
        for rel, content in fixtures.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (repo / ".docs").mkdir(parents=True, exist_ok=True)

        apply_patch(repo)
        validate(repo)
        package = (repo / FILES[0]).read_text(encoding="utf-8")
        assert "note.toLowerCase() === 'nts'" not in package
        assert "const boilerplate" not in package
        assert (repo / FILES[4]).read_text(encoding="utf-8").count(CSS_MARKER_START) == 1
        print("[OK] Synthetic published/draft + note-sync self-test")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--restore-latest", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / "server.py").is_file():
        raise PatchError(f"Singh360 repository not found: {repo}")

    if args.restore_latest:
        restore_latest(repo)
        return 0

    apply_patch(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
