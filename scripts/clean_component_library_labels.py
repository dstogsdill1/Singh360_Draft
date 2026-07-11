"""Clean component library display names and remove duplicate entries.

Targets:
  .docs/library/component_builder_export.json
  .docs/library/manifest.json
  any *.json under .docs/library with a top-level "components" list

Usage:
  python scripts/clean_component_library_labels.py
  python scripts/clean_component_library_labels.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / ".docs" / "library"

ACRONYMS = {
    "LI", "DA", "LS", "LSc", "LSC", "ES", "EA", "IDF", "MDF", "WICP", "LCP", "PCP",
    "RDM", "EMS", "BACnet", "CAT6", "CANbus", "OAT", "CT", "EEV", "LLV", "CO2",
    "LT", "OAU", "PACU", "MDP", "DP1", "PS48", "PS24", "PS12", "PS3", "DM", "NC",
    "NO", "DI", "AIO", "TI", "HFC", "BBQ", "XL", "TouchXL",
}

SPECIFIC_FIXES: dict[str, str] = {
    "sym li leak indicator horn": "LI Leak Indicator Horn/Strobe",
    "sym li leak indicator horn strobe": "LI Leak Indicator Horn/Strobe",
    "leak indicator horn strobe li": "LI Leak Indicator Horn/Strobe",
    "sym da door open horn": "DA Door Open Horn/Strobe",
    "sym da door open horn strobe": "DA Door Open Horn/Strobe",
    "door open horn strobe da": "DA Door Open Horn/Strobe",
    "sym ls hfc refrigerant leak": "LS HFC Refrigerant Leak Sensor",
    "sym ls hfc refrigerant leak sensor": "LS HFC Refrigerant Leak Sensor",
    "sym lsc co2 refrigerant leak": "LSc CO2 Refrigerant Leak Sensor",
    "sym lsc co2 refrigerant leak sensor": "LSc CO2 Refrigerant Leak Sensor",
    "co2 refrigerant leak sensor lsc": "LSc CO2 Refrigerant Leak Sensor",
    "sym es entrapment horn strobe": "ES Entrapment Horn/Strobe",
    "sym ea entrapment alarm": "EA Entrapment Alarm",
    "liquid solenoid": "LLV Liquid Line Solenoid",
    "co2 liquid solenoid": "CO2 Liquid Line Solenoid",
    "light level sensor": "LT Light Level Sensor",
    "outside air temp": "OAT Outside Air Temp Sensor",
    "outside air temperature": "OAT Outside Air Temp Sensor",
    "powerscout ps48": "PowerScout PS48",
    "dent powerscout ps48": "PowerScout PS48",
    "orbit touch xl": "Orbit TouchXL",
    "orbit touchxl": "Orbit TouchXL",
    "rdm data manager": "RDM Data Manager",
    "sym dm data manager marker": "RDM Data Manager",
    "sym idf network marker": "RDM IDF",
    "sym lcp panel marker": "LCP",
    "sym wicp marker": "WICP",
}


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _strip_prefixes(text: str) -> str:
    s = (text or "").strip()
    for pat in (
        r"^sym[_\s]+",
        r"^symbol[_\s]+",
        r"^sym$",
    ):
        s = re.sub(pat, "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"\bbold\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _title_word(word: str) -> str:
    if not word:
        return word
    bare = re.sub(r"[^A-Za-z0-9/+-]", "", word)
    upper = bare.upper()
    if upper in ACRONYMS:
        return upper
    if bare.isupper() and len(bare) <= 6:
        return bare
    if "/" in word:
        return "/".join(_title_word(p) for p in word.split("/"))
    if word.isupper() and len(word) <= 4:
        return word
    return word[:1].upper() + word[1:].lower() if len(word) > 1 else word.upper()


def clean_display_name(raw: str, comp_id: str = "") -> str:
    key = _norm_key(raw)
    if key in SPECIFIC_FIXES:
        return SPECIFIC_FIXES[key]
    # Also try after prefix strip.
    stripped_key = _norm_key(_strip_prefixes(raw))
    if stripped_key in SPECIFIC_FIXES:
        return SPECIFIC_FIXES[stripped_key]

    text = _strip_prefixes(raw)
    if not text:
        text = _strip_prefixes(comp_id.replace("_", " "))
    words = re.split(r"(\s+|/)", text)
    out: list[str] = []
    for w in words:
        if not w or w.isspace() or w == "/":
            out.append(w)
            continue
        out.append(_title_word(w))
    cleaned = "".join(out)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Component"


def _base_id(cid: str) -> str:
    s = (cid or "").strip()
    s = re.sub(r"(__?bold)$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"_bold$", "", s, flags=re.IGNORECASE)
    return s


def _is_bold_entry(comp: dict[str, Any]) -> bool:
    cid = str(comp.get("id") or "").lower()
    if "bold" in cid:
        return True
    for field in ("sourceFile", "sourcePath", "sourceComponent", "edgePath", "edgeFile", "bwPath", "bwFile", "symbolPath", "symbolFile"):
        val = str(comp.get(field) or "").lower()
        if "bold" in val or "__bold" in val:
            return True
    return False


def _source_rel(comp: dict[str, Any]) -> str:
    return str(comp.get("sourceFile") or comp.get("sourcePath") or comp.get("sourceComponent") or "")


def _score_entry(comp: dict[str, Any]) -> tuple[int, int, int]:
    """Higher is better."""
    rel = _source_rel(comp).lower()
    origin = 2 if comp.get("origin") == "builder_export" else 0
    svg = 1 if rel.endswith(".svg") else 0
    has_rep = 1 if any(comp.get(k) for k in ("edgeFile", "edgePath", "bwFile", "bwPath", "symbolFile", "symbolPath")) else 0
    return (origin, svg + has_rep, -len(rel))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _component_list(doc: Any) -> list[dict[str, Any]] | None:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("components"), list):
        return doc["components"]
    return None


def _dedupe_components(components: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    """Remove bold duplicates and png/svg name duplicates."""
    removed_bold = 0
    by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for comp in components:
        by_base[_base_id(str(comp.get("id") or ""))].append(comp)

    survivors: list[dict[str, Any]] = []
    for _base, group in by_base.items():
        non_bold = [c for c in group if not _is_bold_entry(c)]
        bold_only = [c for c in group if _is_bold_entry(c)]
        if non_bold and bold_only:
            removed_bold += len(bold_only)
            survivors.extend(non_bold)
        elif bold_only and not non_bold:
            survivors.append(max(bold_only, key=_score_entry))
            removed_bold += len(bold_only) - 1
        else:
            survivors.extend(group)

    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for comp in survivors:
        name = _norm_key(str(comp.get("displayName") or ""))
        by_name[name].append(comp)

    final: list[dict[str, Any]] = []
    removed_dup = 0
    for _name, group in by_name.items():
        if len(group) == 1:
            final.append(group[0])
            continue
        keep = max(group, key=_score_entry)
        final.append(keep)
        removed_dup += len(group) - 1

    return final, removed_bold, removed_dup


def _clean_id(comp: dict[str, Any]) -> None:
    cid = str(comp.get("id") or "")
    new_id = _base_id(cid)
    if new_id and new_id != cid:
        comp["id"] = new_id


def process_file(path: Path, *, dry_run: bool) -> dict[str, int]:
    doc = _load_json(path)
    components = _component_list(doc)
    if components is None:
        return {"files": 0, "labels": 0, "bold": 0, "dupes": 0}

    labels_changed = 0
    for comp in components:
        old = str(comp.get("displayName") or "")
        new = clean_display_name(old, str(comp.get("id") or ""))
        if new != old:
            comp["displayName"] = new
            labels_changed += 1
        _clean_id(comp)

    deduped, removed_bold, removed_dup = _dedupe_components(components)
    if isinstance(doc, list):
        new_doc: Any = deduped
    else:
        doc["components"] = deduped
        new_doc = doc

    if not dry_run:
        _save_json(path, new_doc)

    return {
        "files": 1,
        "labels": labels_changed,
        "bold": removed_bold,
        "dupes": removed_dup,
        "remaining": len(deduped),
    }


def _discover_targets() -> list[Path]:
    targets: list[Path] = []
    for rel in ("component_builder_export.json", "manifest.json"):
        p = LIB / rel
        if p.exists():
            targets.append(p)
    if LIB.exists():
        for p in sorted(LIB.rglob("*.json")):
            if p.name in ("manifest.json", "component_builder_export.json"):
                continue
            if re.match(r"^library_\d", p.name):
                continue
            if p.parent.name in ("legend_templates", "page_templates", "_backup_before_label_cleanup"):
                continue
            try:
                doc = _load_json(p)
            except Exception:
                continue
            if _component_list(doc) is not None:
                targets.append(p)
    # De-dupe paths.
    seen: set[Path] = set()
    out: list[Path] = []
    for p in targets:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def _backup_library() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = LIB / f"_backup_before_label_cleanup_{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("component_builder_export.json", "manifest.json", "aliases.json"):
        src = LIB / name
        if src.exists():
            shutil.copy2(src, dest / name)
    return dest


def _try_refresh() -> None:
    try:
        import urllib.request

        req = urllib.request.Request(
            "http://127.0.0.1:8765/api/lib/refresh",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                print("Triggered /api/lib/refresh on running server.")
                return
    except Exception:
        pass
    print("Open Singh360 Draft and click Refresh Library.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean component library labels")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not LIB.exists():
        print(f"Library folder not found: {LIB}")
        return 1

    targets = _discover_targets()
    if not targets:
        print("No component manifest files found under .docs/library")
        return 1

    backup = None
    if not args.dry_run:
        backup = _backup_library()
        print(f"Backup: {backup}")

    totals = {"files": 0, "labels": 0, "bold": 0, "dupes": 0, "remaining": 0}
    for path in targets:
        stats = process_file(path, dry_run=args.dry_run)
        for k in totals:
            totals[k] += stats.get(k, 0)
        print(
            f"{'[dry-run] ' if args.dry_run else ''}{path.name}: "
            f"labels={stats['labels']} bold_removed={stats['bold']} "
            f"dupes_removed={stats['dupes']} remaining={stats['remaining']}"
        )

    print(
        f"\nSummary: files={totals['files']} labels_cleaned={totals['labels']} "
        f"bold_removed={totals['bold']} duplicates_removed={totals['dupes']}"
    )
    if not args.dry_run:
        _try_refresh()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
