#!/usr/bin/env python3
"""Install the exact Singh360 refrigeration map-marker standard into runtime data.

V39 replaces the rejected emblem-style assets with the exact map-marker visual:
a square/translucent colored highlight around the original source symbol.

The migration is safe to rerun:
- canonical Component Library rows keep stable ids and user metadata;
- canonical SVG source/approved/thumbnail paths keep stable names;
- only exact stable-key duplicates are retired;
- unrelated user-created components are never matched by loose code/name guesses;
- the saved refrigeration legend template keeps its stable id and row order;
- project.json and linked workbooks are never read or written.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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
RENDERER_VERSION = "singh360-map-marker-v39"
DEFAULT_MARKER_SIZE = 34

# Canonical 96×96 vector geometry. This matches the existing Symbol Legend:
# a highlighted square with the original source symbol centered inside.
GEOMETRY = {
    "viewBox": 96,
    "highlight": {
        "x": 7,
        "y": 7,
        "size": 82,
        "radius": 1.5,
        "strokeWidth": 4,
        "fillOpacity": 0.24,
    },
    "source": {
        "circleRadius": 23,
        "squareX": 25,
        "squareSize": 46,
        "squareRadius": 3,
        "strokeWidth": 3,
        "fill": "#ffffff",
        "fillOpacity": 0.78,
    },
    "text": {
        "x": 48,
        "baselineY": 57,
        "fontFamily": "Segoe UI,Arial,sans-serif",
        "fontWeight": 800,
        "fill": "#111111",
    },
}


class InstallError(RuntimeError):
    """Raised when the canonical migration cannot be proven safe."""


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


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _ordered_union(existing: Iterable[str], required: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in [*existing, *required]:
        value = str(item).strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


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

    by_code: dict[str, list[str]] = {}
    for item in symbols:
        by_code.setdefault(str(item.get("code") or ""), []).append(str(item.get("label") or ""))
    duplicate_codes = {code: labels for code, labels in by_code.items() if len(labels) > 1}
    if duplicate_codes != {"S": ["LIQUID LINE SOLENOID VALVE 120V", "CLEAN SWITCH"]}:
        raise InstallError(f"Unexpected duplicate symbol codes: {duplicate_codes}")

    ls2 = next(item for item in symbols if item["key"] == EXPECTED_KEYS[3])
    li2 = next(item for item in symbols if item["key"] == EXPECTED_KEYS[5])
    if ls2.get("glyph") != "LS₂" or li2.get("glyph") != "LI₂":
        raise InstallError("CO₂ symbol glyphs are not the approved LS₂ / LI₂ values.")
    return data


def _gradient_stops(color1: str, color2: str, pattern: str, opacity: float | None) -> str:
    opacity_attr = "" if opacity is None else f' stop-opacity="{opacity:.2f}"'
    if pattern == "split-vertical":
        return (
            f'<stop offset="0%" stop-color="{color1}"{opacity_attr}/>'
            f'<stop offset="50%" stop-color="{color1}"{opacity_attr}/>'
            f'<stop offset="50%" stop-color="{color2}"{opacity_attr}/>'
            f'<stop offset="100%" stop-color="{color2}"{opacity_attr}/>'
        )
    if pattern == "split-horizontal":
        return (
            f'<stop offset="0%" stop-color="{color1}"{opacity_attr}/>'
            f'<stop offset="50%" stop-color="{color1}"{opacity_attr}/>'
            f'<stop offset="50%" stop-color="{color2}"{opacity_attr}/>'
            f'<stop offset="100%" stop-color="{color2}"{opacity_attr}/>'
        )
    return (
        f'<stop offset="0%" stop-color="{color1}"{opacity_attr}/>'
        f'<stop offset="100%" stop-color="{color1}"{opacity_attr}/>'
    )


def _gradient_axis(pattern: str) -> tuple[str, str, str, str]:
    if pattern == "split-horizontal":
        return "0", "0", "0", "1"
    return "0", "0", "1", "0"


def _font_size(glyph: str) -> int:
    if len(glyph) >= 4:
        return 20
    if len(glyph) == 3:
        return 22
    return 25


def svg_for(symbol: dict[str, Any]) -> str:
    """Return one exact highlighted map-marker SVG.

    The highlight is always a square/rectangular box. The original source
    symbol is the only circle/square inside it.
    """
    color1 = str(symbol.get("color") or "#ffd400")
    color2 = str(symbol.get("color2") or color1)
    pattern = str(symbol.get("pattern") or "solid")
    shape = str(symbol.get("shape") or "circle")
    raw_glyph = str(symbol.get("glyph") or symbol.get("code") or "?")
    glyph = html.escape(raw_glyph)

    h = GEOMETRY["highlight"]
    s = GEOMETRY["source"]
    t = GEOMETRY["text"]
    x1, y1, x2, y2 = _gradient_axis(pattern)
    fill_stops = _gradient_stops(color1, color2, pattern, float(h["fillOpacity"]))
    stroke_stops = _gradient_stops(color1, color2, pattern, None)

    if shape == "circle":
        source_outline = (
            f'<circle data-role="source-outline" cx="48" cy="48" r="{s["circleRadius"]}" '
            f'fill="{s["fill"]}" fill-opacity="{s["fillOpacity"]}" '
            f'stroke="#111111" stroke-width="{s["strokeWidth"]}"/>'
        )
    elif shape == "square":
        source_outline = (
            f'<rect data-role="source-outline" x="{s["squareX"]}" y="{s["squareX"]}" '
            f'width="{s["squareSize"]}" height="{s["squareSize"]}" rx="{s["squareRadius"]}" '
            f'fill="{s["fill"]}" fill-opacity="{s["fillOpacity"]}" '
            f'stroke="#111111" stroke-width="{s["strokeWidth"]}"/>'
        )
    elif shape == "none":
        source_outline = ""
    else:
        raise InstallError(f"Unsupported canonical symbol shape {shape!r} for {symbol.get('key')}")

    metadata = html.escape(
        json.dumps(
            {
                "renderer": RENDERER_VERSION,
                "standardKey": symbol["key"],
                "shape": shape,
                "pattern": pattern,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GEOMETRY["viewBox"]} {GEOMETRY["viewBox"]}" '
        'role="img" preserveAspectRatio="xMidYMid meet">\n'
        f"  <title>{html.escape(display_name(symbol))}</title>\n"
        f'  <metadata data-renderer="{RENDERER_VERSION}">{metadata}</metadata>\n'
        "  <defs>\n"
        f'    <linearGradient id="highlightFill" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{fill_stops}</linearGradient>\n'
        f'    <linearGradient id="highlightStroke" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{stroke_stops}</linearGradient>\n'
        "  </defs>\n"
        f'  <rect data-role="highlight" x="{h["x"]}" y="{h["y"]}" width="{h["size"]}" height="{h["size"]}" '
        f'rx="{h["radius"]}" fill="url(#highlightFill)" stroke="url(#highlightStroke)" '
        f'stroke-width="{h["strokeWidth"]}"/>\n'
        f"  {source_outline}\n"
        f'  <text data-role="glyph" x="{t["x"]}" y="{t["baselineY"]}" text-anchor="middle" '
        f'font-family="{t["fontFamily"]}" font-size="{_font_size(raw_glyph)}" '
        f'font-weight="{t["fontWeight"]}" fill="{t["fill"]}">{glyph}</text>\n'
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
        values.update(
            {
                "LS2",
                "LS₂",
                "LSC",
                "CO2 LEAK SENSOR",
                "CO₂ LEAK SENSOR",
                "CO2 REFRIGERANT LEAK SENSOR",
                "CO₂ REFRIGERANT LEAK SENSOR",
            }
        )
    if symbol["code"] == "LI2":
        values.update(
            {
                "LI2",
                "LI₂",
                "CO2 LEAK INDICATOR",
                "CO₂ LEAK INDICATOR",
                "CO2 REFRIGERANT LEAK INDICATOR",
                "CO₂ REFRIGERANT LEAK INDICATOR",
            }
        )
    return sorted(value for value in values if value)


def canonical_match(component: dict[str, Any], symbol: dict[str, Any]) -> bool:
    """Match only stable canonical identities; never fuzzy-match user content."""
    key = str(symbol["key"])
    tags = {str(tag) for tag in component.get("tags") or []}
    if f"{KEY_TAG_PREFIX}{key}" in tags:
        return True
    if str(component.get("id") or "") == stable_id(key):
        return True

    expected_name = stable_filename(symbol)
    for field in ("sourceFile", "symbolFile", "thumbnailFile"):
        value = str(component.get(field) or "").replace("\\", "/")
        if value.endswith("/" + expected_name) or value == expected_name:
            return True

    source = component.get("source")
    if isinstance(source, dict) and str(source.get("standardKey") or "") == key:
        return True
    return False


def _canonical_note(existing: str, key: str) -> str:
    line = f"Canonical Singh360 map-marker entry: {key}"
    lines = [item.rstrip() for item in existing.splitlines() if item.strip()]
    if not any(item.startswith("Canonical Singh360 ") for item in lines):
        lines.append(line)
    else:
        lines = [line if item.startswith("Canonical Singh360 ") else item for item in lines]
    return "\n".join(lines)


def _write_if_changed(path: Path, payload: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == payload:
        return False
    path.write_bytes(payload)
    return True


def _validate_svg_text(symbol: dict[str, Any], svg_text: str) -> None:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise InstallError(f"{symbol['key']}: generated SVG is invalid XML: {exc}") from exc

    ns = {"svg": "http://www.w3.org/2000/svg"}
    highlights = root.findall(".//svg:rect[@data-role='highlight']", ns)
    if len(highlights) != 1:
        raise InstallError(f"{symbol['key']}: expected one rectangular highlight; found {len(highlights)}")

    metadata = root.find(".//svg:metadata", ns)
    if metadata is None or metadata.attrib.get("data-renderer") != RENDERER_VERSION:
        raise InstallError(f"{symbol['key']}: renderer metadata is missing or incorrect")

    glyphs = root.findall(".//svg:text[@data-role='glyph']", ns)
    if len(glyphs) != 1 or "".join(glyphs[0].itertext()) != str(symbol.get("glyph") or symbol["code"]):
        raise InstallError(f"{symbol['key']}: glyph is missing or incorrect")

    circles = root.findall(".//svg:circle", ns)
    source_nodes = root.findall(".//*[@data-role='source-outline']", ns)
    shape = str(symbol.get("shape") or "circle")
    if shape == "circle":
        if len(source_nodes) != 1 or not source_nodes[0].tag.endswith("circle"):
            raise InstallError(f"{symbol['key']}: expected one inner source circle")
        if any(float(node.attrib.get("r", "0")) > float(GEOMETRY["source"]["circleRadius"]) for node in circles):
            raise InstallError(f"{symbol['key']}: rejected emblem-style outer circle is still present")
    elif shape == "square":
        if len(source_nodes) != 1 or not source_nodes[0].tag.endswith("rect"):
            raise InstallError(f"{symbol['key']}: expected one inner source square")
    elif shape == "none" and source_nodes:
        raise InstallError(f"{symbol['key']}: no-outline symbol unexpectedly has a source outline")

    colors = {str(symbol.get("color") or "").lower(), str(symbol.get("color2") or "").lower()}
    serialized = svg_text.lower()
    for color in colors:
        if color and color not in serialized:
            raise InstallError(f"{symbol['key']}: required color {color} is missing")


def _prepare_runtime_template(standard: dict[str, Any], runtime_template: Path) -> tuple[bool, Path | None]:
    runtime_history = runtime_template.parent / "history"
    runtime_history.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {**standard, "rendererVersion": RENDERER_VERSION},
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    encoded = payload.encode("utf-8")

    if runtime_template.is_file() and runtime_template.read_bytes() == encoded:
        return False, None

    backup: Path | None = None
    if runtime_template.is_file():
        backup = runtime_history / f"standard-before-v39-{stamp()}.json"
        shutil.copy2(runtime_template, backup)
    runtime_template.parent.mkdir(parents=True, exist_ok=True)
    runtime_template.write_bytes(encoded)
    return True, backup


def _save_legend_template(
    legend_store: LegendTemplateStore,
    existing: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write the stable legend while preserving user-edited layout metadata.

    The live branch's LegendTemplateStore has the original narrow save
    interface. Write through its established storage paths and manifest helpers
    without changing that public API.
    """
    legend_store.ensure()
    payload = dict(existing)
    payload.update(
        {
            "id": LEGEND_TEMPLATE_ID,
            "name": str(existing.get("name") or "Singh360 Refrigeration Symbols"),
            "category": str(existing.get("category") or "refrigeration"),
            "title": str(existing.get("title") or "SYMBOLS KEY:"),
            "rows": rows,
            "rendererVersion": RENDERER_VERSION,
            "updatedAt": now(),
        }
    )
    payload.setdefault(
        "layout",
        {
            "background": "#ffffff",
            "border": "#333333",
            "fontSize": 9,
            "rowHeight": 28,
            "iconWidth": 32,
        },
    )
    payload.setdefault("columns", 1)
    payload.setdefault("markerSize", DEFAULT_MARKER_SIZE)
    payload.setdefault("frame", False)
    payload["highlighted"] = True

    path = legend_store.root / f"{LEGEND_TEMPLATE_ID}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = legend_store._read_manifest()
    entries = [
        entry
        for entry in (manifest.get("templates") or [])
        if entry.get("id") != LEGEND_TEMPLATE_ID
    ]
    entry = {
        "id": LEGEND_TEMPLATE_ID,
        "name": payload["name"],
        "category": payload["category"],
        "rowCount": len(rows),
        "updatedAt": payload["updatedAt"],
    }
    entries.insert(0, entry)
    manifest["templates"] = entries
    legend_store._write_manifest(manifest)
    return entry


def install(repo: Path, docs: Path) -> dict[str, Any]:
    standard = load_standard(repo)
    symbols = standard["symbols"]
    docs.mkdir(parents=True, exist_ok=True)

    runtime_template = docs / "symbol_mapper" / "templates" / "standard.json"

    library = LibraryV2(docs)
    library.ensure()
    manifest = library._read_manifest()
    components = list(manifest.get("components") or [])

    source_dir = library.components / "symbols_markers"
    approved_dir = library.symbols / "symbols_markers"
    thumb_dir = library.thumbnails / "symbols_markers"
    for folder in (source_dir, approved_dir, thumb_dir):
        folder.mkdir(parents=True, exist_ok=True)

    added = updated = retired_duplicates = asset_updates = 0
    canonical_ids: list[str] = []
    planned: list[tuple[dict[str, Any], bytes, Path, Path, Path, list[dict[str, Any]]]] = []

    # Build and verify every asset before writing any library/runtime assets.
    for symbol in symbols:
        svg_text = svg_for(symbol)
        _validate_svg_text(symbol, svg_text)
        svg_bytes = svg_text.encode("utf-8")
        filename = stable_filename(symbol)
        matches = [component for component in components if canonical_match(component, symbol)]
        canonical = next(
            (component for component in matches if component.get("id") == stable_id(str(symbol["key"]))),
            None,
        )
        if canonical is None:
            canonical = {"id": stable_id(str(symbol["key"])), "createdAt": now()}
            components.append(canonical)
            added += 1
        else:
            updated += 1
        planned.append(
            (
                symbol,
                svg_bytes,
                source_dir / filename,
                approved_dir / filename,
                thumb_dir / filename,
                matches,
            )
        )

    # Do not touch runtime data until every canonical SVG has been generated
    # and structurally validated.
    runtime_changed, runtime_backup = _prepare_runtime_template(standard, runtime_template)
    library._snapshot_manifest("before-exact-symbol-component-library-v39")

    for index, (symbol, svg_bytes, source_path, approved_path, thumb_path, matches) in enumerate(planned, start=1):
        key = str(symbol["key"])
        canonical = next(
            (component for component in components if component.get("id") == stable_id(key)),
            None,
        )
        if canonical is None:
            raise InstallError(f"{key}: canonical component disappeared during migration planning")

        for target in (source_path, approved_path, thumb_path):
            if _write_if_changed(target, svg_bytes):
                asset_updates += 1

        aliases = _ordered_union(_string_list(canonical.get("aliases")), aliases_for(symbol))
        categories = _ordered_union(_string_list(canonical.get("categories")), ["symbols_markers", "refrigeration"])
        tags = _ordered_union(
            _string_list(canonical.get("tags")),
            [
                STANDARD_TAG,
                "symbol-mapper",
                "refrigeration-controls",
                "exact-map-marker",
                RENDERER_VERSION,
                f"{KEY_TAG_PREFIX}{key}",
            ],
        )
        source_meta = dict(canonical.get("source") or {}) if isinstance(canonical.get("source"), dict) else {}
        source_meta.update(
            {
                "file": library._rel(source_path),
                "standardKey": key,
                "rendererVersion": RENDERER_VERSION,
            }
        )

        canonical.update(
            {
                "displayName": display_name(symbol),
                "category": "symbols_markers",
                "categories": categories,
                "subcategory": "refrigeration-controls",
                "manufacturer": "Singh360",
                "partNumber": symbol["code"],
                "aliases": aliases,
                "sourceFile": library._rel(source_path),
                "thumbnailFile": library._rel(thumb_path),
                "symbolFile": library._rel(approved_path),
                "symbolStatus": "built",
                "type": "symbol",
                "assetKind": "singh360-map-marker",
                "rendererVersion": RENDERER_VERSION,
                "sortOrder": index,
                "defaultLabel": str(symbol.get("glyph") or symbol["code"]),
                "shortName": str(symbol.get("glyph") or symbol["code"]),
                "defaultWidth": DEFAULT_MARKER_SIZE,
                "defaultHeight": DEFAULT_MARKER_SIZE,
                "labelPosition": "none",
                "ports": list(canonical.get("ports") or []),
                "approved": True,
                "needsReview": False,
                "favorite": bool(canonical.get("favorite", False)),
                "notes": _canonical_note(str(canonical.get("notes") or ""), key),
                "collection": COLLECTION,
                "status": "approved",
                "retired": False,
                "tags": tags,
                "contentHash": hashlib.sha256(svg_bytes).hexdigest(),
                "perceptualHash": None,
                "imageWidth": GEOMETRY["viewBox"],
                "imageHeight": GEOMETRY["viewBox"],
                "source": source_meta,
                "updatedAt": now(),
            }
        )
        canonical_ids.append(str(canonical["id"]))

        for duplicate in matches:
            if duplicate is canonical:
                continue
            duplicate["retired"] = True
            duplicate["status"] = "duplicate"
            duplicate["duplicateOf"] = canonical["id"]
            duplicate["notes"] = (
                str(duplicate.get("notes") or "").strip()
                + f"\nRetired by V39 as an exact stable-key duplicate of {canonical['id']}."
            ).strip()
            retired_duplicates += 1

    manifest["version"] = max(2, int(manifest.get("version") or 0))
    manifest["components"] = components
    manifest["symbolComponentStandard"] = {
        "rendererVersion": RENDERER_VERSION,
        "collection": COLLECTION,
        "count": len(EXPECTED_KEYS),
        "updatedAt": now(),
    }
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
            "rendererVersion": RENDERER_VERSION,
        }
        for symbol in symbols
    ]
    legend_store = LegendTemplateStore(docs)
    existing_legend = legend_store.get_template(LEGEND_TEMPLATE_ID) or {}
    legend_entry = _save_legend_template(legend_store, existing_legend, legend_rows)

    result = {
        "ok": True,
        "rendererVersion": RENDERER_VERSION,
        "symbols": len(symbols),
        "libraryAdded": added,
        "libraryUpdated": updated,
        "retiredExactDuplicates": retired_duplicates,
        "assetFilesUpdated": asset_updates,
        "runtimeTemplateChanged": runtime_changed,
        "runtimeTemplateBackup": str(runtime_backup) if runtime_backup else None,
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
    if runtime.get("rendererVersion") != RENDERER_VERSION:
        raise InstallError("Runtime standard renderer version is missing or incorrect")

    library = LibraryV2(docs)
    library.ensure()
    manifest = library._read_manifest()
    components = list(manifest.get("components") or [])
    active_by_key: dict[str, list[dict[str, Any]]] = {key: [] for key in EXPECTED_KEYS}
    for component in components:
        if component.get("retired") or str(component.get("status") or "").lower() in {
            "retired",
            "duplicate",
            "junk",
        }:
            continue
        tags = {str(tag) for tag in component.get("tags") or []}
        for key in EXPECTED_KEYS:
            if f"{KEY_TAG_PREFIX}{key}" in tags:
                active_by_key[key].append(component)

    expected_symbols = {str(item["key"]): item for item in standard["symbols"]}
    for order, (key, entries) in enumerate(active_by_key.items(), start=1):
        if len(entries) != 1:
            raise InstallError(f"Expected one active library entry for {key}; found {len(entries)}")
        component = entries[0]
        if component.get("rendererVersion") != RENDERER_VERSION:
            raise InstallError(f"{key}: component renderer version is incorrect")
        if int(component.get("sortOrder") or 0) != order:
            raise InstallError(f"{key}: component sort order is incorrect")
        if int(component.get("defaultWidth") or 0) != DEFAULT_MARKER_SIZE:
            raise InstallError(f"{key}: default marker width is incorrect")
        if component.get("collection") != COLLECTION:
            raise InstallError(f"{key}: component collection is incorrect")

        for field in ("sourceFile", "symbolFile", "thumbnailFile"):
            rel = str(component.get(field) or "")
            path = library.root / rel
            if not rel or not path.is_file():
                raise InstallError(f"{key}: missing {field}: {path}")
            svg_text = path.read_text(encoding="utf-8")
            _validate_svg_text(expected_symbols[key], svg_text)
            if hashlib.sha256(svg_text.encode("utf-8")).hexdigest() != component.get("contentHash"):
                raise InstallError(f"{key}: {field} content hash does not match manifest")

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
    if any(row.get("rendererVersion") != RENDERER_VERSION for row in rows):
        raise InstallError("Legend template renderer version is missing from one or more rows")

    return {
        "ok": True,
        "rendererVersion": RENDERER_VERSION,
        "symbols": len(EXPECTED_KEYS),
        "activeLibraryEntries": sum(len(items) for items in active_by_key.values()),
        "legendRows": len(rows),
        "collection": COLLECTION,
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
