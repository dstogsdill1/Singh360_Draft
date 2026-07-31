"""Canonical Singh360 refrigeration leak-sensor library migration.

The migration is deliberately scoped to the eight marker records that represent
the four approved leak-sensor codes.  Existing component IDs and the two LS2
asset paths are retained so saved drawings continue to resolve in place.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


STANDARD_UPDATED_AT = "2026-07-31T18:45:00Z"
HIGHLIGHT_COLLECTION = "Refrigeration Controls Symbols"
PLAN_COLLECTION = "Singh360 Plan Markers"
LSC_HIGHLIGHT_ID = "symbols_markers_s360_7a7d4d97334a"
LSC_PLAN_ID = "s360-plan-marker-7a7d4d97334a"

SENSORS: tuple[dict[str, str], ...] = (
    {"code": "LSc", "description": "CO2 Refrigerant Leak Detector", "part": "CT1O-A3D", "supplier": "Senva"},
    {"code": "LSg", "description": "Produce Prep Area HFC Sensor (Refrigerant Specific)", "part": "GG-R513A", "supplier": "CTI"},
    {"code": "LS", "description": "Leak Sensor for HFCs", "part": "REF-LK-832", "supplier": "EMC"},
    {"code": "LSb", "description": "Leak Sensor for HFCs, w/metal enclosure (produce/market coolers)", "part": "REF-LK-832-MTL", "supplier": "EMC"},
)

IDS = {
    ("highlight", "LSc"): LSC_HIGHLIGHT_ID,
    ("highlight", "LSg"): "s360_rdm_lsg",
    ("highlight", "LS"): "symbols_markers_s360_cfb272c0da74",
    ("highlight", "LSb"): "s360_rdm_lsb",
    ("plan", "LSc"): LSC_PLAN_ID,
    ("plan", "LSg"): "s360-plan-marker-lsg",
    ("plan", "LS"): "s360-plan-marker-548ddf294f9b",
    ("plan", "LSb"): "s360-plan-marker-lsb",
}

PATHS = {
    ("highlight", "LSc"): "components/symbols_markers/singh360__ls2__co2-refrigerant-leak-sensor.svg",
    ("highlight", "LSg"): "components/symbols_markers/s360_rdm_lsg.svg",
    ("highlight", "LS"): "components/symbols_markers/singh360__ls__refrigerant-leak-detection-sensor.svg",
    ("highlight", "LSb"): "components/symbols_markers/s360_rdm_lsb.svg",
    ("plan", "LSc"): "components/symbols_markers/plan_markers/plan__ls2__co2-refrigerant-leak-sensor.svg",
    ("plan", "LSg"): "components/symbols_markers/plan_markers/plan__lsg__produce-prep-hfc-sensor.svg",
    ("plan", "LS"): "components/symbols_markers/plan_markers/plan__ls__refrigerant-leak-sensor.svg",
    ("plan", "LSb"): "components/symbols_markers/plan_markers/plan__lsb__metal-enclosure-hfc-sensor.svg",
}


def _sensor(code: str) -> dict[str, str]:
    return next(item for item in SENSORS if item["code"] == code)


def _aliases(sensor: dict[str, str]) -> list[str]:
    aliases = [sensor["code"], sensor["description"], sensor["part"], sensor["supplier"]]
    if sensor["code"] == "LSc":
        aliases += ["LS2", "LS₂", "CO2 leak sensor", "CO₂ leak sensor", "CO2 Refrigerant Leak Sensor", "LSC"]
    elif sensor["code"] == "LSg":
        aliases += ["LSG", "LS-G", "CTI HFC leak sensor", "refrigerant specific sensor"]
    elif sensor["code"] == "LSb":
        aliases += ["LSB", "LS-B", "metal enclosure leak sensor", "produce cooler leak sensor", "market cooler leak sensor"]
    else:
        aliases += ["HFC leak sensor", "refrigerant leak sensor"]
    return list(dict.fromkeys(aliases))


def _standard_key(kind: str, sensor: dict[str, str]) -> str:
    prefix = "PLAN|" if kind == "plan" else ""
    return f"{prefix}{sensor['code']}|{sensor['description']}"


def _symbol_rel(kind: str, code: str) -> str:
    source = PATHS[(kind, code)]
    if kind == "plan":
        return source
    return source.replace("components/", "symbols/", 1)


def _thumb_rel(kind: str, code: str) -> str:
    return "thumbnails/symbols_markers/" + Path(PATHS[(kind, code)]).name


def _display(sensor: dict[str, str]) -> str:
    return f"{sensor['code']} — {sensor['description']} — {sensor['part']} — {sensor['supplier']}"


def _manifest_record(kind: str, sensor: dict[str, str], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    code = sensor["code"]
    source = PATHS[(kind, code)]
    symbol = _symbol_rel(kind, code)
    key = _standard_key(kind, sensor)
    renderer = "singh360-plan-ring-v40" if kind == "plan" else "singh360-map-marker-v39"
    record = deepcopy(previous or {})
    record.update({
        "id": IDS[(kind, code)],
        "displayName": _display(sensor),
        "category": "symbols_markers",
        "categories": ["symbols_markers", "refrigeration"] if kind == "highlight" else ["symbols_markers"],
        "subcategory": "refrigeration-controls" if kind == "highlight" else "plan-markers",
        "manufacturer": sensor["supplier"],
        "partNumber": sensor["part"],
        "aliases": _aliases(sensor),
        "sourceFile": source,
        "thumbnailFile": _thumb_rel(kind, code),
        "symbolFile": symbol,
        "edgeFile": symbol,
        "bwFile": symbol,
        "symbolStatus": "built",
        "type": "symbol",
        "assetKind": "singh360-plan-marker" if kind == "plan" else "singh360-map-marker",
        "rendererVersion": renderer,
        "sortOrder": {"LSc": 3, "LSg": 4, "LS": 5, "LSb": 6}[code],
        "defaultLabel": code,
        "shortName": code,
        "defaultWidth": 34,
        "defaultHeight": 34,
        "labelPosition": "none",
        "ports": [],
        "approved": True,
        "needsReview": False,
        "retired": False,
        "status": "approved",
        "notes": f"Canonical Singh360 leak-sensor marker: {key}",
        "collection": PLAN_COLLECTION if kind == "plan" else HIGHLIGHT_COLLECTION,
        "tags": [
            "singh360-standard", "symbol-mapper", "refrigeration-controls",
            f"singh360-symbol-key:{key}", "exact-map-marker", renderer,
        ],
        "imageWidth": 96,
        "imageHeight": 96,
        "source": {"file": source, "standardKey": key, "rendererVersion": renderer},
        "updatedAt": STANDARD_UPDATED_AT,
    })
    record.pop("retiredBy", None)
    return record


def _builder_record(kind: str, sensor: dict[str, str]) -> dict[str, Any]:
    code = sensor["code"]
    source = PATHS[(kind, code)]
    symbol = _symbol_rel(kind, code)
    return {
        "id": IDS[(kind, code)], "displayName": _display(sensor), "category": "symbols_markers",
        "categories": ["symbols_markers", "refrigeration"] if kind == "highlight" else ["symbols_markers"],
        "collection": PLAN_COLLECTION if kind == "plan" else HIGHLIGHT_COLLECTION,
        "manufacturer": sensor["supplier"], "partNumber": sensor["part"], "aliases": _aliases(sensor),
        "defaultLabel": code, "sourcePath": source, "edgePath": symbol, "bwPath": symbol,
        "symbolPath": symbol, "notes": f"Canonical Singh360 leak-sensor marker: {_standard_key(kind, sensor)}",
        "chosenVariant": "custom" if kind == "plan" else "device",
        "preferredEdgeVariant": "custom" if kind == "plan" else "device", "hasProcedural": False,
        "status": "approved",
    }


def _glyph_text(code: str) -> str:
    if code == "LS":
        return '<text data-role="glyph" x="48" y="57" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="25" font-weight="800" fill="#111111">LS</text>'
    return (
        '<text data-role="glyph-base" x="45" y="57" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="25" font-weight="800" fill="#111111">LS</text>\n'
        f'  <text data-role="glyph-suffix" x="63" y="62" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="15" font-weight="800" fill="#111111">{code[-1]}</text>'
    )


def render_svg(kind: str, sensor: dict[str, str]) -> str:
    code = sensor["code"]
    key = _standard_key(kind, sensor)
    title = _display(sensor)
    glyph = _glyph_text(code)
    if kind == "highlight":
        if code == "LSc":
            stops = '<stop offset="0%" stop-color="#ffd400"/><stop offset="49.9%" stop-color="#ffd400"/><stop offset="50%" stop-color="#8e44ad"/><stop offset="100%" stop-color="#8e44ad"/>'
            fill_stops = '<stop offset="0%" stop-color="#ffd400" stop-opacity="0.24"/><stop offset="49.9%" stop-color="#ffd400" stop-opacity="0.24"/><stop offset="50%" stop-color="#8e44ad" stop-opacity="0.24"/><stop offset="100%" stop-color="#8e44ad" stop-opacity="0.24"/>'
        else:
            stops = '<stop offset="0%" stop-color="#ffd400"/><stop offset="100%" stop-color="#ffd400"/>'
            fill_stops = '<stop offset="0%" stop-color="#ffd400" stop-opacity="0.24"/><stop offset="100%" stop-color="#ffd400" stop-opacity="0.24"/>'
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" preserveAspectRatio="xMidYMid meet">
  <title>{title}</title>
  <metadata data-renderer="singh360-map-marker-v39">{{&quot;renderer&quot;:&quot;singh360-map-marker-v39&quot;,&quot;standardKey&quot;:&quot;{key}&quot;,&quot;shape&quot;:&quot;circle&quot;}}</metadata>
  <defs><linearGradient id="highlightFill" x1="0" y1="0" x2="1" y2="0">{fill_stops}</linearGradient><linearGradient id="highlightStroke" x1="0" y1="0" x2="1" y2="0">{stops}</linearGradient></defs>
  <rect data-role="highlight" x="7" y="7" width="82" height="82" rx="1.5" fill="url(#highlightFill)" stroke="url(#highlightStroke)" stroke-width="4"/>
  <circle data-role="source-outline" cx="48" cy="48" r="23" fill="#ffffff" fill-opacity="0.78" stroke="#111111" stroke-width="3"/>
  {glyph}
</svg>
'''
    ring = "#ffd400|#8e44ad" if code == "LSc" else "#c99a00|#c99a00"
    first, second = ring.split("|")
    stops = f'<stop offset="0%" stop-color="{first}"/><stop offset="49.9%" stop-color="{first}"/><stop offset="50%" stop-color="{second}"/><stop offset="100%" stop-color="{second}"/>'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" preserveAspectRatio="xMidYMid meet">
  <title>{title}</title>
  <metadata data-renderer="singh360-plan-ring-v40">{{&quot;renderer&quot;:&quot;singh360-plan-ring-v40&quot;,&quot;standardKey&quot;:&quot;{key}&quot;}}</metadata>
  <defs><linearGradient id="ring" x1="0" y1="0" x2="1" y2="0">{stops}</linearGradient></defs>
  <circle data-role="ring" cx="48" cy="48" r="34" fill="#ffffff" stroke="url(#ring)" stroke-width="5"/>
  {glyph.replace('y="57"', 'y="58"', 1).replace('y="62"', 'y="63"', 1)}
</svg>
'''


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return deepcopy(fallback)


def _write_json(path: Path, payload: Any, changed: list[str]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8-sig") == rendered:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    changed.append(path.as_posix())


def _write_text(path: Path, rendered: str, changed: list[str]) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == rendered:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    changed.append(path.as_posix())


def _replace_rows(rows: list[dict[str, Any]], factory: Any) -> list[dict[str, Any]]:
    leak_codes = {"LS", "LS2", "LSC", "LSG", "LSB"}
    def is_leak(row: dict[str, Any]) -> bool:
        direct = str(row.get("code") or row.get("acronym") or row.get("id") or "").replace("₂", "2").upper()
        if direct in leak_codes:
            return True
        identity = " ".join(str(row.get(key) or "") for key in ("componentId", "symbolId", "label"))
        return bool(re.search(r"(?:^|[_\s—-])LS(?:2|C|G|B)?(?:[_\s—-]|$)", identity.replace("₂", "2"), re.IGNORECASE))
    indexes = [i for i, row in enumerate(rows) if is_leak(row)]
    insert_at = min(indexes) if indexes else len(rows)
    kept = [row for i, row in enumerate(rows) if i not in indexes]
    before_count = sum(1 for i in range(insert_at) if i not in indexes)
    return kept[:before_count] + [factory(sensor) for sensor in SENSORS] + kept[before_count:]


def _legend_row(sensor: dict[str, str], plan: bool = False) -> dict[str, Any]:
    code = sensor["code"]
    row = {
        "code": code, "glyph": code, "label": sensor["description"],
        "name": _standard_key("plan" if plan else "highlight", sensor), "acronym": code,
        "shape": "circle", "color": "#ffd400" if code == "LSc" else "#c99a00" if plan else "#ffd400",
        "color2": "#8e44ad" if code == "LSc" else "#c99a00" if plan else "#ffd400",
        "pattern": "split-vertical" if code == "LSc" else "solid", "highlighted": True,
        "rendererVersion": "singh360-plan-ring-v40" if plan else "singh360-map-marker-v39",
    }
    if plan:
        row["key"] = row["name"]
        row["symbolUrl"] = "/api/lib/asset/" + PATHS[("plan", code)]
    return row


def _saved_row(sensor: dict[str, str]) -> dict[str, Any]:
    code = sensor["code"]
    return {"id": code.lower(), "enabled": True, "label": f"{code} — {sensor['description']}", "acronym": code,
            "componentId": IDS[("highlight", code)], "searchTerms": _aliases(sensor), "preferredRep": "bw"}


def _update_legends(root: Path, changed: list[str]) -> None:
    legends = root / "legend_templates"
    for name, plan in (("singh360-refrigeration-symbols-standard.json", False), ("singh360-plan-marker-legend.json", True)):
        path = legends / name
        data = _read_json(path, {})
        data["rows"] = _replace_rows(list(data.get("rows") or []), lambda sensor, p=plan: _legend_row(sensor, p))
        data["updatedAt"] = STANDARD_UPDATED_AT
        _write_json(path, data, changed)
    for name in ("rdm-wicp-safety-standard.json",):
        path = legends / name
        data = _read_json(path, {})
        data["rows"] = _replace_rows(list(data.get("rows") or []), _saved_row)
        data["updatedAt"] = STANDARD_UPDATED_AT
        _write_json(path, data, changed)
    path = legends / "wicp_refrigeration_symbol_legend.json"
    data = _read_json(path, {})
    items = list(data.get("items") or [])
    positions = [i for i, item in enumerate(items) if str(item.get("symbolId") or "").startswith("sym_ls")]
    at = min(positions) if positions else len(items)
    kept = [item for i, item in enumerate(items) if i not in positions]
    before = sum(1 for i in range(at) if i not in positions)
    leak_items = [{"symbolId": f"sym_{s['code'].lower()}_refrigerant_leak_sensor", "code": s["code"], "label": s["description"]} for s in SENSORS]
    data["items"] = kept[:before] + leak_items + kept[before:]
    _write_json(path, data, changed)
    path = legends / "wicp_safety_alarm_legend.json"
    data = _read_json(path, {})
    data["rows"] = _replace_rows(list(data.get("rows") or []), _saved_row)
    _write_json(path, data, changed)
    index_path = legends / "legend_template_index.json"
    index = _read_json(index_path, {"templates": []})
    for template in index.get("templates") or []:
        if template.get("id") == "wicp_safety_alarm_legend":
            template["rows"] = _replace_rows(list(template.get("rows") or []), _saved_row)
    _write_json(index_path, index, changed)
    manifest_path = legends / "manifest.json"
    manifest = _read_json(manifest_path, {"version": 1, "templates": []})
    for entry in manifest.get("templates") or []:
        template = _read_json(legends / f"{entry.get('id')}.json", {})
        if template:
            entry["rowCount"] = len(template.get("rows") or template.get("items") or [])
        if entry.get("id") in {"singh360-refrigeration-symbols-standard", "singh360-plan-marker-legend", "rdm-wicp-safety-standard"}:
            entry["updatedAt"] = STANDARD_UPDATED_AT
    _write_json(manifest_path, manifest, changed)


def _update_symbol_keys(root: Path, changed: list[str]) -> None:
    symbols_path = root / "symbols.json"
    symbols = _read_json(symbols_path, [])
    if isinstance(symbols, list):
        leak_ids = {"sym_ls", "sym_lsc", "sym_lsg", "sym_lsb"}
        kept = [item for item in symbols if item.get("id") not in leak_ids]
        at = next((i for i, item in enumerate(symbols) if item.get("id") in leak_ids), len(kept))
        rows = [{"id": f"sym_{s['code'].lower()}", "displayName": _display(s), "shortName": s["code"], "category": "symbol", "shape": "circle", "stroke": "#d99a00", "fill": "#ffffff", "text": s["code"], "aliases": _aliases(s)} for s in SENSORS]
        symbols = kept[:at] + rows + kept[at:]
        _write_json(symbols_path, symbols, changed)
        legacy = root / "library.json"
        data = _read_json(legacy, {})
        if isinstance(data, dict) and isinstance(data.get("symbols"), list):
            data["symbols"] = deepcopy(symbols)
            _write_json(legacy, data, changed)
    aliases_path = root / "aliases.json"
    aliases = _read_json(aliases_path, {"version": 1, "aliases": {}})
    amap = aliases.setdefault("aliases", {})
    for old in ("LS2", "LS₂", "CO2 LEAK SENSOR", "CO₂ LEAK SENSOR", "CO2 REFRIGERANT LEAK SENSOR"):
        amap[old] = LSC_HIGHLIGHT_ID
    _write_json(aliases_path, aliases, changed)


def _update_mapper(docs_dir: Path, changed: list[str]) -> None:
    path = docs_dir / "symbol_mapper" / "templates" / "standard.json"
    data = _read_json(path, {"version": 1, "id": "singh360-standard", "name": "Singh360 Standard", "symbols": []})
    data["symbols"] = _replace_rows(list(data.get("symbols") or []), lambda sensor: {
        "key": f"{sensor['code'].upper()}|{sensor['description'].upper()}", "code": sensor["code"], "glyph": sensor["code"],
        "label": sensor["description"], "aliases": _aliases(sensor), "enabled": True,
        "paletteId": "yellow-purple" if sensor["code"] == "LSc" else "yellow", "color": "#ffd400",
        "color2": "#8e44ad" if sensor["code"] == "LSc" else "#ffd400",
        "pattern": "split-vertical" if sensor["code"] == "LSc" else "solid", "shape": "circle",
    })
    data["updatedAt"] = STANDARD_UPDATED_AT
    _write_json(path, data, changed)


def apply_leak_sensor_standard(docs_dir: Path) -> dict[str, Any]:
    docs_dir = Path(docs_dir).resolve()
    root = docs_dir / "library"
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path, {"version": 2, "components": []})
    existing = {str(item.get("id")): item for item in manifest.get("components") or []}
    if existing.get(LSC_HIGHLIGHT_ID, {}).get("sourceFile") != PATHS[("highlight", "LSc")]:
        raise RuntimeError("Audited highlighted LSc stable ID or source asset does not match the live library")
    if existing.get(LSC_PLAN_ID, {}).get("sourceFile") != PATHS[("plan", "LSc")]:
        raise RuntimeError("Audited plan-marker LSc stable ID or source asset does not match the live library")
    changed: list[str] = []
    for kind in ("highlight", "plan"):
        for sensor in SENSORS:
            code = sensor["code"]
            svg = render_svg(kind, sensor)
            source_path = root / PATHS[(kind, code)]
            symbol_path = root / _symbol_rel(kind, code)
            thumb_path = root / _thumb_rel(kind, code)
            for path in dict.fromkeys((source_path, symbol_path, thumb_path)):
                _write_text(path, svg, changed)
            record = _manifest_record(kind, sensor, existing.get(IDS[(kind, code)]))
            record["contentHash"] = sha256(svg.encode("utf-8")).hexdigest()
            existing[record["id"]] = record
    # Keep superseded RDM LS/LSc records recoverably retired so the approved
    # highlighted and plan-marker entries are the only visible systems.
    for legacy_id in ("s360_rdm_ls", "s360_rdm_lsc"):
        if legacy_id in existing:
            existing[legacy_id]["approved"] = False
            existing[legacy_id]["retired"] = True
            existing[legacy_id]["status"] = "retired"
    original_order = [str(item.get("id")) for item in manifest.get("components") or []]
    appended = [IDS[(kind, s["code"])] for kind in ("highlight", "plan") for s in SENSORS if IDS[(kind, s["code"])] not in original_order]
    manifest["components"] = [existing[item_id] for item_id in original_order if item_id in existing] + [existing[item_id] for item_id in appended]
    manifest["updatedAt"] = STANDARD_UPDATED_AT
    _write_json(manifest_path, manifest, changed)
    export_path = root / "component_builder_export.json"
    export = _read_json(export_path, {"components": []})
    entries = {str(item.get("id")): item for item in export.get("components") or []}
    for kind in ("highlight", "plan"):
        for sensor in SENSORS:
            entries[IDS[(kind, sensor["code"])]] = _builder_record(kind, sensor)
    order = [str(item.get("id")) for item in export.get("components") or []]
    additions = [item_id for item_id in entries if item_id not in order]
    export["components"] = [entries[item_id] for item_id in order] + [entries[item_id] for item_id in additions]
    export["updatedAt"] = STANDARD_UPDATED_AT
    _write_json(export_path, export, changed)
    _update_symbol_keys(root, changed)
    _update_legends(root, changed)
    _update_mapper(docs_dir, changed)
    return {
        "ok": True,
        "docsDir": str(docs_dir),
        "changed": changed,
        "componentIds": {f"{kind}:{code}": component_id for (kind, code), component_id in IDS.items()},
    }
