"""LibraryV2 lifecycle checks using only generated temporary components.

Validates:
- refresh scans only components/ and never creates .symbol.svg
- legacy migration populates V2 when legacy files exist
- rebuild thumbnails writes only to thumbnails/
- fake symbols are archived + manifest refs cleared
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.library_v2 import LibraryV2  # noqa: E402

_FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {msg}")
    if not cond:
        _FAILS.append(msg)


def _write_svg(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>{body}</svg>", encoding="utf-8")


def _write_png(path: Path) -> None:
    # Tiny valid PNG bytes (1x1 pixel)
    data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="singh360_lib2_"))
    docs = tmp / ".docs"
    lib = LibraryV2(docs)
    lib.ensure()

    # Seed source components.
    _write_svg(lib.components / "controllers" / "Generic_Controller.svg", "<rect width='40' height='40' fill='none'/>")
    _write_png(lib.components / "logos" / "Sanitized_Client.png")

    # --- refresh scans only components and does not generate symbols ---
    r1 = lib.refresh()
    d1 = lib.load()
    check(r1["ok"] and r1["scanned"] == 2, f"Refresh scans only components/ (scanned={r1['scanned']})")
    check(len(d1["components"]) == 2, f"Manifest populated from components (count={len(d1['components'])})")
    fake_syms = list(lib.components.rglob("*.symbol.svg"))
    check(len(fake_syms) == 0, "Refresh does not generate .symbol.svg files")

    # --- refresh twice stable ---
    r2 = lib.refresh()
    d2 = lib.load()
    check(r2["added"] == 0 and len(d2["components"]) == 2, "Refresh twice does not increase count")

    # --- legacy migration (if legacy exists) populates v2 ---
    legacy = lib.legacy_root
    _write_svg(legacy / "alarm" / "Alarm_Strobe_Horn.svg", "<circle cx='20' cy='20' r='16' fill='none'/>")
    prev = lib.migrate_legacy(dry_run=True)
    check(prev.get("willCopy", 0) >= 1, f"Legacy migration dry-run plans copy (willCopy={prev.get('willCopy', 0)})")
    app = lib.migrate_legacy(dry_run=False, rebuild_thumbnails=False, generate_symbols=False)
    d3 = lib.load()
    check(app.get("copied", 0) >= 1 and d3["counts"]["total"] >= 3,
          f"Legacy migration applies (copied={app.get('copied', 0)}, total={d3['counts']['total']})")

    # --- rebuild thumbnails only affects thumbnails root ---
    before_comp_files = sorted(str(p.relative_to(lib.components)) for p in lib.components.rglob("*") if p.is_file())
    rt = lib.rebuild_thumbnails()
    after_comp_files = sorted(str(p.relative_to(lib.components)) for p in lib.components.rglob("*") if p.is_file())
    thumb_files = [p for p in lib.thumbnails.rglob("*") if p.is_file()]
    check(rt["ok"] and len(thumb_files) >= 1, f"Rebuild Thumbnails writes thumbnail outputs (n={len(thumb_files)})")
    check(before_comp_files == after_comp_files, "Rebuild Thumbnails does not create/delete component source files")

    # --- fake-symbol cleanup archives symbols + clears manifest refs ---
    fake = lib.components / "controllers" / "Generic_Controller.symbol.svg"
    _write_svg(fake, "<rect width='40' height='40'/>")
    # force a stale symbol ref
    man = lib._read_manifest()  # noqa: SLF001
    for c in man["components"]:
        if c.get("sourceFile", "").endswith("Generic_Controller.svg"):
            c["symbolFile"] = lib._rel(fake)  # noqa: SLF001
    lib._write_manifest(man)  # noqa: SLF001

    dry_fake = lib.archive_fake_symbols(dry_run=True)
    check(dry_fake["fakeSymbols"] >= 1, f"Fake-symbol cleanup dry-run detects symbols (n={dry_fake['fakeSymbols']})")
    done_fake = lib.archive_fake_symbols(dry_run=False)
    d4 = lib.load()
    refs = [c for c in d4["components"] if c.get("symbolFile")]
    fake_left = list(lib.components.rglob("*.symbol.svg"))
    check(done_fake["moved"] >= 1 and len(fake_left) == 0, "Fake symbols moved to archive; none remain under components")
    check(len(refs) == 0, "Manifest symbolFile references cleared after fake-symbol cleanup")
    status_ok = all(c.get("symbolStatus") == "not_built" for c in d4["components"])
    check(status_ok, "Manifest components marked symbolStatus=not_built")

    print("\n" + ("ALL PASS" if not _FAILS else f"{len(_FAILS)} FAILED"))
    return 0 if not _FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
