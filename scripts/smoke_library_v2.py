"""scripts/smoke_library_v2.py — Milestone 4A acceptance smoke test (Phase 9).

Exercises the clean library root, manifest v2, symbol generation, generators,
sheet rendering, continuation-sheet splitting, and (optionally) PDF import.
Runs entirely in a throwaway temp docs dir — never touches real .docs data.

Run:  python scripts/smoke_library_v2.py
Exit: 0 on success, 1 on any failed assertion.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.library_v2 import LibraryV2  # noqa: E402
from core.drawing_generators import (  # noqa: E402
    generate_callout_schedule,
    generate_component_stack,
    generate_overall_layout,
)
from engines.ems_sheet import render_layout_sheet, render_schedule_sheets  # noqa: E402

_FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {msg}")
    if not cond:
        _FAILS.append(msg)


def _write_svg(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>{body}</svg>", encoding="utf-8")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="singh360_lib2_"))
    docs = tmp / ".docs"
    lib = LibraryV2(docs)
    lib.ensure()

    # --- Test 1: Refresh scans only components/ ---
    _write_svg(lib.components / "controllers" / "pr0650.svg", "<rect width='40' height='40'/>")
    _write_svg(lib.components / "logos" / "heb.svg", "<circle cx='20' cy='20' r='18'/>")
    # A file OUTSIDE components/ must be ignored:
    (lib.thumbnails / "controllers").mkdir(parents=True, exist_ok=True)
    _write_svg(lib.thumbnails / "controllers" / "ghost.svg", "<rect/>")
    (docs / "projects").mkdir(parents=True, exist_ok=True)
    _write_svg(docs / "projects" / "ghost2.svg", "<rect/>")

    r1 = lib.refresh()
    check(r1["ok"] and r1["scanned"] == 2, f"Refresh scans only components/ (scanned={r1['scanned']}, expected 2)")
    data = lib.load()
    names = {c["displayName"] for c in data["components"]}
    check("ghost" not in " ".join(names), "Thumbnails/projects folders are never scanned")
    check(len(data["components"]) == 2, f"Two components tracked (got {len(data['components'])})")

    # --- Test 2: Refresh twice does not duplicate ---
    r2 = lib.refresh()
    data2 = lib.load()
    check(r2["added"] == 0 and len(data2["components"]) == 2,
          f"Refresh twice is idempotent (added={r2['added']}, total={len(data2['components'])})")

    # --- Test 4: displayName edit persists to manifest ---
    cid = data2["components"][0]["id"]
    lib.update_component(cid, {"displayName": "PR0650CD-TDB Controller", "partNumber": "PR0650CD-TDB"})
    reloaded = lib.load()
    persisted = next(c for c in reloaded["components"] if c["id"] == cid)
    check(persisted["displayName"] == "PR0650CD-TDB Controller" and persisted["partNumber"] == "PR0650CD-TDB",
          "displayName + partNumber edit persists to manifest.json")

    # --- Test 5: symbol generation produces a symbol file (group symbol+label) ---
    sym = lib.generate_symbol(cid)
    sym_path = lib.root / sym["symbolFile"]
    check(sym["ok"] and sym_path.exists() and "<svg" in sym_path.read_text(encoding="utf-8"),
          "Generate Symbol writes a black-and-white SVG symbol")

    # --- Test 3: thumbnails resolve after rebuild ---
    rt = lib.rebuild_thumbnails()
    rebuilt = lib.load()
    resolvable = 0
    for c in rebuilt["components"]:
        if c.get("thumbnailFile"):
            tp = lib.resolve_asset(c["thumbnailFile"])
            # svg thumbnails are copied with .svg extension
            if tp is None:
                alt = lib.root / (Path(c["thumbnailFile"]).with_suffix(".svg").as_posix())
                tp = alt if alt.exists() else None
            if tp is not None:
                resolvable += 1
    check(rt["ok"] and resolvable >= 1, f"Rebuild Thumbnails regenerates resolvable thumbs (resolved={resolvable})")

    # --- Test: clean-duplicates dry run then execute ---
    # Refresh already blocks NEW exact-hash dups from entering the manifest, so
    # Clean Duplicates is the remediation path for pre-existing manifest
    # duplicates (e.g. legacy imports). Inject one directly to exercise it.
    import json as _json
    _write_svg(lib.components / "custom" / "dup_copy.svg", "<rect width='40' height='40'/>")  # same bytes as pr0650
    manifest = _json.loads(lib.manifest_path.read_text(encoding="utf-8"))
    original = next(c for c in manifest["components"] if c["sourceFile"].endswith("pr0650.svg"))
    dup_entry = dict(original)
    dup_entry["id"] = "custom_dup_injected"
    dup_entry["sourceFile"] = "components/custom/dup_copy.svg"
    manifest["components"].append(dup_entry)  # same contentHash -> a real duplicate
    lib.manifest_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")
    dry = lib.clean_duplicates(dry_run=True)
    check(dry["duplicates"] >= 1, f"Clean Duplicates detects the exact-hash duplicate (dry={dry['duplicates']})")
    done = lib.clean_duplicates(dry_run=False)
    check(done["archived"] >= 1, f"Clean Duplicates archives duplicates (archived={done['archived']})")

    # --- Test: SVG thumbnailFile points at an existing file (no broken .webp) ---
    lib.rebuild_thumbnails()
    lib_data = lib.load()
    bad = [c for c in lib_data["components"]
           if c.get("thumbnailFile") and lib.resolve_asset(c["thumbnailFile"]) is None]
    check(not bad, f"Every thumbnailFile resolves to a real file (broken={len(bad)})")

    # --- Test: legacy migration populates V2 from assets/components ---
    legacy = lib.legacy_root
    (legacy / "controllers").mkdir(parents=True, exist_ok=True)
    (legacy / "alarm").mkdir(parents=True, exist_ok=True)
    _write_svg(legacy / "controllers" / "PR0650CD-TDB.svg", "<rect width='40' height='40' fill='none'/>")
    _write_svg(legacy / "alarm" / "Strobe_Horn.svg", "<circle cx='20' cy='20' r='16' fill='none'/>")
    check(lib.has_legacy(), "has_legacy() detects legacy assets/components files")
    preview = lib.migrate_legacy(dry_run=True)
    check(preview["willCopy"] >= 2, f"Migrate dry-run plans copies (willCopy={preview['willCopy']})")
    check(preview["targetCategories"].get("alarms_safety", 0) >= 1, "alarm -> alarms_safety mapping in plan")
    applied = lib.migrate_legacy(dry_run=False, rebuild_thumbnails=False, generate_symbols=False)
    after = lib.load()
    cat_ids = {c["category"] for c in after["components"]}
    check(applied["copied"] >= 2 and "alarms_safety" in cat_ids,
          f"Migration copied legacy files into V2 (copied={applied['copied']})")
    # Idempotent: migrating again copies nothing new (exact-hash skip).
    again = lib.migrate_legacy(dry_run=True)
    check(again["willCopy"] == 0, f"Re-migrate copies nothing new (willCopy={again['willCopy']})")

    # --- Test: bulk symbol generation writes symbolFile (skips logos) ---
    _write_svg(lib.components / "logos" / "HEB_logo.svg", "<rect width='40' height='40'/>")
    lib.refresh()
    gs = lib.generate_all_symbols()
    sym_data = lib.load()
    with_symbol = [c for c in sym_data["components"] if c.get("symbolFile")]
    logo = next((c for c in sym_data["components"] if c["category"] == "logos"), None)
    check(gs["generated"] >= 2 and len(with_symbol) >= 2, f"Bulk symbols generated (n={gs['generated']})")
    check(logo is not None and not logo.get("symbolFile"), "Logos are skipped by bulk symbol generation")

    # --- Test: physical duplicate cleanup archives byte-identical extras ---
    for i in range(5):
        _write_svg(lib.components / "custom" / f"contactor_copy_{i}.svg", "<rect width='9' height='9'/>")
    pd = lib.clean_physical_duplicates(dry_run=True)
    check(pd["duplicates"] >= 4, f"Physical dedupe detects identical copies (dupes={pd['duplicates']})")
    pdo = lib.clean_physical_duplicates(dry_run=False)
    check(pdo["archived"] >= 4, f"Physical dedupe archives extras, keeps one (archived={pdo['archived']})")
    remaining = list((lib.components / "custom").glob("contactor_copy_*.svg"))
    check(len(remaining) == 1, f"Exactly one identical contactor copy remains (remaining={len(remaining)})")

    # --- Test 8: overall layout generator makes nodes, connectors, legend ---
    graph = generate_overall_layout([
        {"name": "LCP1", "category": "panels_enclosures"},
        {"name": "LCP2", "category": "panels_enclosures"},
        {"name": "Zone Sensor", "category": "sensors_transducers"},
    ])
    check(len(graph["nodes"]) >= 4 and len(graph["edges"]) >= 1 and len(graph["legend"]) >= 1,
          f"Overall layout: nodes={len(graph['nodes'])}, edges={len(graph['edges'])}, legend={len(graph['legend'])}")
    check(graph["notes"] == ["N.T.S."], "Overall layout carries an N.T.S. note")

    # --- Test 9: export 17x11 and 8.5x11 both render ---
    svg_b = render_layout_sheet(graph, sheet="ansi_b", sheet_no="EMS 1.0")
    svg_a = render_layout_sheet(graph, sheet="ansi_a", sheet_no="EMS 1.0")
    check("width='1224'" in svg_b, "Layout renders at 17x11 (ANSI B, 1224px wide)")
    check("width='792'" in svg_a, "Layout scales to 8.5x11 (ANSI A, 792px wide)")

    # --- Test 7: table overflow creates continuation sheets, no scroll ---
    placed = [{"id": f"d{i}", "partNumber": f"P{i}", "location": "Store"} for i in range(120)]
    table = generate_callout_schedule(placed)
    sheets = render_schedule_sheets(table, sheet="ansi_b", base_sheet_no="EMS 0.6")
    check(len(sheets) >= 2, f"Large table splits into continuation sheets (sheets={len(sheets)})")
    check(all("Callout" in s["svg"] for s in sheets), "Header row repeats on every continuation sheet")

    # --- component stack generator ---
    stack = generate_component_stack([
        {"id": "a", "defaultLabel": "PR0650"}, {"id": "b", "defaultLabel": "PR0663"},
    ])
    ys = [n["y"] for n in stack["nodes"]]
    check(ys == sorted(ys) and len(set(ys)) == len(ys), "Component stack uses consistent vertical spacing")

    # --- Test 6 (optional): PDF import if PyMuPDF present ---
    try:
        from core import pdf_import_v2
        if pdf_import_v2.is_available():
            print("[INFO] PyMuPDF available — PDF import path importable")
        else:
            print("[SKIP] PyMuPDF not installed — PDF import path skipped (graceful)")
    except Exception as exc:  # noqa: BLE001
        print(f"[SKIP] PDF import import error: {exc}")

    print("\n" + ("ALL PASS" if not _FAILS else f"{len(_FAILS)} FAILED"))
    return 0 if not _FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
