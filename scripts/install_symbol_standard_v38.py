#!/usr/bin/env python3
"""Install the canonical Singh360 refrigeration symbol standard into runtime data.

This script is safe to rerun:
- the runtime Symbol Mapper standard is replaced only after a history backup;
- Component Library entries are updated by stable symbol key, not duplicated;
- exact duplicate canonical entries are retired, never deleted;
- SVG source, approved symbol, and thumbnail files use stable names;
- the saved refrigeration legend template uses a stable template id.

The script never reads or writes project.json or any linked workbook.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.legend_template_store import LegendTemplateStore
from core.library_v2 import LibraryV2


EXPECTED_KEYS = [
    "TS|TEMPERATURE SENSOR",
    "DA|DOOR ALARM",
    "LS|REFRIGERANT LEAK DETECTION SENSOR",
    "LS2|CO2 REFRIGERANT LEAK SENSOR",
    "LI|REFRIGERANT LEAK INDICATOR AUDIO VISUAL ALARM",
    "LI2|CO2 REFRIGERANT LEAK INDICATOR AUDIO VISUAL ALARM",
    "CC|RDM CASE CONTROLLER",
    "DTS|DUAL TEMPERATURE SWITCH",
    "HT|HIGH TEMPERATURE ALARM STROBE AMBER",
    "ES|WALK IN FREEZER ENTRAPMENT SWITCH",
    "AS|ALARM STROBE RED",
    "EA|ENTRAPMENT ALARM",
    "S|LIQUID LINE SOLENOID VALVE 120V",
    "DT|DEFROST TERMINATION SENSOR",
    "S|CLEAN SWITCH",
]
STANDARD_TAG = "singh360-standard"
KEY_TAG_PREFIX = "singh360-symbol-key:"
LEGEND_TEMPLATE_ID = "singh360-refrigeration-symbols-standard"
COLLECTION = "Refrigeration Controls Symbols"


class InstallError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:72] or "symbol"


def stable_id(key: str) -> str:
    return f"symbols_markers_s360_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def stable_filename(symbol: dict[str, Any]) -> str:
    return f"singh360__{symbol['code'].lower()}__{slug(symbol['label'])}.svg"


def display_name(symbol: dict[str, Any]) -> str:
    glyph = str(symbol.get("glyph") or symbol["code"])
    return f"{glyph} — {symbol['label']}"


def load_standard(repo: Path) -> dict[str, Any]:
    path = repo / "defaults" / "symbol_mapper_standard.json"
    if not path.is_file():
        raise InstallError(f"Default symbol standard was not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"Default symbol standard is unreadable: {exc}") from exc
    symbols = data.get("symbols")
    if not isinstance(symbols, list):
        raise InstallError("Default symbol standard has no symbols list.")
    keys = [str(item.get("key") or "") for item in symbols if isinstance(item, dict)]
    if keys != EXPECTED_KEYS:
        raise InstallError(f"Unexpected canonical symbol order/keys: {keys}")
    if len(keys) != len(set(keys)):
        raise InstallError("Canonical symbol keys are duplicated.")
    by_code = {}
    for item in symbols:
        by_code.setdefault(str(item.get("code") or ""), []).append(str(item.get("label") or ""))
    duplicate_codes = {code: labels for code, labels in by_code.items() if len(labels) > 1}
    if duplicate_codes != {
        "S": ["LIQUID LINE SOLENOID VALVE 120V", "CLEAN SWITCH"],
    }:
        raise InstallError(f"Unexpected duplicate symbol codes: {duplicate_codes}")
    ls2 = next(item for item in symbols if item["key"] == EXPECTED_KEYS[3])
    li2 = next(item for item in symbols if item["key"] == EXPECTED_KEYS[5])
    if ls2.get("glyph") != "LS₂" or li2.get("glyph") != "LI₂":
        raise InstallError("CO₂ symbol glyphs are not the approved LS₂ / LI₂ values.")
    return data


def svg_for(symbol: dict[str, Any]) -> str:
    color1 = str(symbol.get("color") or "#ffd400")
    color2 = str(symbol.get("color2") or color1)
    pattern = str(symbol.get("pattern") or "solid")
    shape = str(symbol.get("shape") or "circle")
    glyph = html.escape(str(symbol.get("glyph") or symbol.get("code") or "?"))
    clip_shape = (
        '<circle cx="48" cy="48" r="42"/>'
        if shape == "circle"
        else '<rect x="7" y="7" width="82" height="82" rx="5"/>'
    )
    outer = (
        '<circle cx="48" cy="48" r="42" fill="url(#fill)" stroke="#111" stroke-width="3"/>'
        if shape == "circle"
        else '<rect x="7" y="7" width="82" height="82" rx="5" fill="url(#fill)" stroke="#111" stroke-width="3"/>'
    )
    if pattern == "split-vertical":
        fill = (
            f'<linearGradient id="fill" x1="0" x2="1" y1="0" y2="0">'
            f'<stop offset="0%" stop-color="{color1}"/><stop offset="50%" stop-color="{color1}"/>'
            f'<stop offset="50%" stop-color="{color2}"/><stop offset="100%" stop-color="{color2}"/>'
            f"</linearGradient>"
        )
    elif pattern == "split-horizontal":
        fill = (
            f'<linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">'
            f'<stop offset="0%" stop-color="{color1}"/><stop offset="50%" stop-color="{color1}"/>'
            f'<stop offset="50%" stop-color="{color2}"/><stop offset="100%" stop-color="{color2}"/>'
            f"</linearGradient>"
        )
    else:
        fill = (
            f'<linearGradient id="fill" x1="0" x2="1" y1="0" y2="0">'
            f'<stop offset="0%" stop-color="{color1}"/><stop offset="100%" stop-color="{color1}"/>'
            f"</linearGradient>"
        )

    if shape == "none":
        outer = '<rect x="7" y="7" width="82" height="82" rx="7" fill="url(#fill)" stroke="none"/>'
        inner = ""
    elif shape == "square":
        inner = '<rect x="25" y="25" width="46" height="46" rx="3" fill="rgba(255,255,255,.62)" stroke="#111" stroke-width="3"/>'
    else:
        inner = '<circle cx="48" cy="48" r="23" fill="rgba(255,255,255,.62)" stroke="#111" stroke-width="3"/>'

    font_size = 25
    if len(str(symbol.get("glyph") or "")) >= 4:
        font_size = 20
    elif len(str(symbol.get("glyph") or "")) == 3:
        font_size = 22
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img">\n'
        f"  <title>{html.escape(display_name(symbol))}</title>\n"
        "  <defs>\n"
        f"    {fill}\n"
        f'    <clipPath id="markerClip">{clip_shape}</clipPath>\n'
        "  </defs>\n"
        f"  {outer}\n"
        f"  {inner}\n"
        f'  <text x="48" y="57" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" '
        f'font-size="{font_size}" font-weight="800" fill="#111">{glyph}</text>\n'
        "</svg>\n"
    )


def aliases_for(symbol: dict[str, Any]) -> list[str]:
    values = {
        str(symbol["code"]),
        str(symbol.get("glyph") or ""),
        str(symbol["label"]),
        display_name(symbol),
    }
    if symbol["code"] == "LS2":
        values.update({"LS2", "LS₂", "CO2 LEAK SENSOR", "CO₂ LEAK SENSOR"})
    if symbol["code"] == "LI2":
        values.update({"LI2", "LI₂", "CO2 LEAK INDICATOR", "CO₂ LEAK INDICATOR"})
    return sorted(value for value in values if value)


def canonical_match(component: dict[str, Any], symbol: dict[str, Any]) -> bool:
    key = str(symbol["key"])
    tags = {str(tag) for tag in component.get("tags") or []}
    if f"{KEY_TAG_PREFIX}{key}" in tags:
        return True
    if str(component.get("id") or "") == stable_id(key):
        return True
    if str(component.get("sourceFile") or "").endswith("/" + stable_filename(symbol)):
        return True
    code = norm(component.get("partNumber") or component.get("shortName") or component.get("defaultLabel"))
    label_blob = norm(
        " ".join(
            [
                str(component.get("displayName") or ""),
                str(component.get("notes") or ""),
                " ".join(str(x) for x in component.get("aliases") or []),
            ]
        )
    )
    return code == norm(symbol["code"]) and norm(symbol["label"]) in label_blob


def install(repo: Path, docs: Path) -> dict[str, Any]:
    standard = load_standard(repo)
    symbols = standard["symbols"]
    docs.mkdir(parents=True, exist_ok=True)

    runtime_template = docs / "symbol_mapper" / "templates" / "standard.json"
    runtime_history = runtime_template.parent / "history"
    runtime_history.mkdir(parents=True, exist_ok=True)
    if runtime_template.is_file():
        backup = runtime_history / f"standard-before-v38-{stamp()}.json"
        shutil.copy2(runtime_template, backup)
    runtime_template.parent.mkdir(parents=True, exist_ok=True)
    runtime_template.write_text(
        json.dumps({**standard, "updatedAt": now()}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    library = LibraryV2(docs)
    library.ensure()
    library._snapshot_manifest("before-symbol-standard-v38")
    manifest = library._read_manifest()
    components = list(manifest.get("components") or [])

    source_dir = library.components / "symbols_markers"
    approved_dir = library.symbols / "symbols_markers"
    thumb_dir = library.thumbnails / "symbols_markers"
    for folder in (source_dir, approved_dir, thumb_dir):
        folder.mkdir(parents=True, exist_ok=True)

    added = updated = retired_duplicates = 0
    canonical_ids: list[str] = []
    for symbol in symbols:
        key = str(symbol["key"])
        filename = stable_filename(symbol)
        svg_text = svg_for(symbol)
        svg_bytes = svg_text.encode("utf-8")
        source_path = source_dir / filename
        approved_path = approved_dir / filename
        thumb_path = thumb_dir / filename
        for target in (source_path, approved_path, thumb_path):
            target.write_bytes(svg_bytes)

        matches = [component for component in components if canonical_match(component, symbol)]
        canonical = next(
            (component for component in matches if component.get("id") == stable_id(key)),
            matches[0] if matches else None,
        )
        if canonical is None:
            canonical = {"id": stable_id(key), "createdAt": now()}
            components.append(canonical)
            added += 1
        else:
            updated += 1

        canonical.update(
            {
                "displayName": display_name(symbol),
                "category": "symbols_markers",
                "categories": ["symbols_markers", "refrigeration"],
                "subcategory": "refrigeration-controls",
                "manufacturer": "Singh360",
                "partNumber": symbol["code"],
                "aliases": aliases_for(symbol),
                "sourceFile": library._rel(source_path),
                "thumbnailFile": library._rel(thumb_path),
                "symbolFile": library._rel(approved_path),
                "symbolStatus": "built",
                "type": "symbol",
                "defaultLabel": str(symbol.get("glyph") or symbol["code"]),
                "shortName": str(symbol.get("glyph") or symbol["code"]),
                "defaultWidth": 48,
                "defaultHeight": 48,
                "labelPosition": "none",
                "ports": [],
                "approved": True,
                "needsReview": False,
                "favorite": bool(canonical.get("favorite", False)),
                "notes": f"Canonical Singh360 Symbol Mapper entry: {key}",
                "collection": COLLECTION,
                "status": "approved",
                "retired": False,
                "tags": [
                    STANDARD_TAG,
                    "symbol-mapper",
                    "refrigeration-controls",
                    f"{KEY_TAG_PREFIX}{key}",
                ],
                "contentHash": hashlib.sha256(svg_bytes).hexdigest(),
                "perceptualHash": None,
                "imageWidth": 96,
                "imageHeight": 96,
                "source": {
                    "file": library._rel(source_path),
                    "standardKey": key,
                },
                "updatedAt": now(),
            }
        )
        canonical_ids.append(str(canonical["id"]))

        for duplicate in matches:
            if duplicate is canonical:
                continue
            duplicate["retired"] = True
            duplicate["status"] = "duplicate"
            duplicate["notes"] = (
                str(duplicate.get("notes") or "").strip()
                + f"\nRetired by V38 as an exact duplicate of {canonical['id']}."
            ).strip()
            retired_duplicates += 1

    manifest["version"] = 2
    manifest["components"] = components
    library._write_manifest(manifest)

    legend_rows = [
        {
            "code": symbol["code"],
            "glyph": symbol.get("glyph") or symbol["code"],
            "label": symbol["label"],
            "name": symbol["key"],
            "acronym": symbol["code"],
            "shape": symbol["shape"],
            "color": symbol["color"],
            "color2": symbol["color2"],
            "pattern": symbol["pattern"],
            "highlighted": True,
        }
        for symbol in symbols
    ]
    legend_store = LegendTemplateStore(docs)
    legend_entry = legend_store.save_template(
        name="Singh360 Refrigeration Symbols",
        category="refrigeration",
        title="SYMBOLS KEY:",
        rows=legend_rows,
        template_id=LEGEND_TEMPLATE_ID,
    )

    result = {
        "ok": True,
        "symbols": len(symbols),
        "libraryAdded": added,
        "libraryUpdated": updated,
        "retiredExactDuplicates": retired_duplicates,
        "canonicalIds": canonical_ids,
        "legendTemplate": legend_entry,
        "runtimeTemplate": str(runtime_template),
        "libraryManifest": str(library.manifest_path),
    }
    verify(repo, docs)
    return result


def verify(repo: Path, docs: Path) -> dict[str, Any]:
    standard = load_standard(repo)

    runtime_template = docs / "symbol_mapper" / "templates" / "standard.json"
    if not runtime_template.is_file():
        raise InstallError(f"Runtime standard is missing: {runtime_template}")
    runtime = json.loads(runtime_template.read_text(encoding="utf-8-sig"))
    runtime_keys = [str(item.get("key") or "") for item in runtime.get("symbols") or []]
    if runtime_keys != EXPECTED_KEYS:
        raise InstallError(f"Runtime standard keys are incorrect: {runtime_keys}")

    library = LibraryV2(docs)
    library.ensure()
    manifest = library._read_manifest()
    components = list(manifest.get("components") or [])
    active_by_key: dict[str, list[dict[str, Any]]] = {key: [] for key in EXPECTED_KEYS}
    for component in components:
        if component.get("retired") or str(component.get("status") or "").lower() in {"retired", "duplicate", "junk"}:
            continue
        tags = {str(tag) for tag in component.get("tags") or []}
        for key in EXPECTED_KEYS:
            if f"{KEY_TAG_PREFIX}{key}" in tags:
                active_by_key[key].append(component)

    for key, entries in active_by_key.items():
        if len(entries) != 1:
            raise InstallError(f"Expected one active library entry for {key}; found {len(entries)}")
        component = entries[0]
        for field in ("sourceFile", "symbolFile", "thumbnailFile"):
            rel = str(component.get(field) or "")
            path = library.root / rel
            if not rel or not path.is_file():
                raise InstallError(f"{key}: missing {field}: {path}")

    legend_store = LegendTemplateStore(docs)
    legend = legend_store.get_template(LEGEND_TEMPLATE_ID)
    if not legend:
        raise InstallError("Saved refrigeration legend template is missing.")
    rows = legend.get("rows") or []
    if len(rows) != len(EXPECTED_KEYS):
        raise InstallError(f"Legend template row count is {len(rows)}, expected {len(EXPECTED_KEYS)}")
    row_keys = [f"{norm(row.get('code'))}|{norm(row.get('label'))}" for row in rows]
    if row_keys != EXPECTED_KEYS:
        raise InstallError(f"Legend template rows are out of order or incorrect: {row_keys}")

    return {
        "ok": True,
        "symbols": len(EXPECTED_KEYS),
        "activeLibraryEntries": sum(len(items) for items in active_by_key.values()),
        "legendRows": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--docs", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    docs = (args.docs or (repo / ".docs")).resolve()
    result = verify(repo, docs) if args.check else install(repo, docs)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallError as exc:
        print(f"INSTALL ERROR: {exc}")
        raise SystemExit(2)
