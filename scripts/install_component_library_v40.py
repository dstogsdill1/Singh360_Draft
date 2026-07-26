#!/usr/bin/env python3
"""Install the Singh360 V40 curated symbol library.

V40 separates the existing 15 highlighted Symbol Mapper markers from a new
simple colored-ring Plan Marker collection. It retires only exact, known
generated marker records; it never deletes component files, projects, workbooks,
manual canvas objects, or unrelated user assets.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.legend_template_store import LegendTemplateStore  # noqa: E402
from core.library_v2 import LibraryV2  # noqa: E402
from scripts.install_callout_number_components import (  # noqa: E402
    callout_svg,
    canonical_entry as canonical_callout_entry,
    override_entry as callout_override_entry,
)
from scripts.install_symbol_standard_v39 import (  # noqa: E402
    EXPECTED_KEYS as MAPPER_EXPECTED_KEYS,
    RENDERER_VERSION as MAPPER_RENDERER,
)

VERSION = "V40"
PLAN_RENDERER = "singh360-plan-ring-v40"
MAPPER_COLLECTION = "Refrigeration Controls Symbols"
PLAN_COLLECTION = "Singh360 Plan Markers"
MAPPER_LEGEND_ID = "singh360-refrigeration-symbols-standard"
PLAN_LEGEND_ID = "singh360-plan-marker-legend"
SAFETY_LEGEND_ID = "singh360-safety-signage-legend"
KEY_TAG_PREFIX = "singh360-symbol-key:"
PLAN_KEY_PREFIX = "PLAN|"

PLAN_MARKERS: list[dict[str, Any]] = [
    {"key": "TS|TEMPERATURE SENSOR", "code": "TS", "glyph": "TS", "label": "TEMPERATURE SENSOR", "color": "#1e73be", "color2": "#1e73be", "pattern": "solid", "aliases": ["TS", "temperature probe"]},
    {"key": "DA|DOOR ALARM", "code": "DA", "glyph": "DA", "label": "DOOR ALARM", "color": "#00a651", "color2": "#00a651", "pattern": "solid", "aliases": ["DA", "door open horn strobe"]},
    {"key": "LS|REFRIGERANT LEAK SENSOR", "code": "LS", "glyph": "LS", "label": "REFRIGERANT LEAK SENSOR", "color": "#c99a00", "color2": "#c99a00", "pattern": "solid", "aliases": ["LS", "HFC leak sensor", "refrigerant leak detection sensor"]},
    {"key": "LS2|CO2 REFRIGERANT LEAK SENSOR", "code": "LS2", "glyph": "LS₂", "label": "CO2 REFRIGERANT LEAK SENSOR", "color": "#ffd400", "color2": "#8e44ad", "pattern": "split-vertical", "aliases": ["LS2", "LS₂", "LSC", "LSc", "CO2 leak sensor", "CO₂ leak sensor"]},
    {"key": "LI|REFRIGERANT LEAK INDICATOR", "code": "LI", "glyph": "LI", "label": "REFRIGERANT LEAK INDICATOR", "color": "#e53935", "color2": "#ffd400", "pattern": "split-vertical", "aliases": ["LI", "leak indicator horn strobe"]},
    {"key": "LI2|CO2 REFRIGERANT LEAK INDICATOR", "code": "LI2", "glyph": "LI₂", "label": "CO2 REFRIGERANT LEAK INDICATOR", "color": "#e53935", "color2": "#8e44ad", "pattern": "split-vertical", "aliases": ["LI2", "LI₂", "CO2 leak indicator", "CO₂ leak indicator"]},
    {"key": "CC|RDM CASE CONTROLLER", "code": "CC", "glyph": "CC", "label": "RDM CASE CONTROLLER", "color": "#e84393", "color2": "#e84393", "pattern": "solid", "aliases": ["CC", "case controller"]},
    {"key": "DTS|DUAL TEMPERATURE SWITCH", "code": "DTS", "glyph": "DTS", "label": "DUAL TEMPERATURE SWITCH", "color": "#00a8cc", "color2": "#00a8cc", "pattern": "solid", "aliases": ["DTS", "dual temp switch"]},
    {"key": "HT|HIGH TEMPERATURE ALARM", "code": "HT", "glyph": "HT", "label": "HIGH TEMPERATURE ALARM", "color": "#e84393", "color2": "#e84393", "pattern": "solid", "aliases": ["HT", "high temperature alarm strobe", "amber alarm"]},
    {"key": "ES|ENTRAPMENT SWITCH", "code": "ES", "glyph": "ES", "label": "ENTRAPMENT SWITCH", "color": "#ffd400", "color2": "#1e73be", "pattern": "split-vertical", "aliases": ["ES", "walk-in freezer entrapment switch"]},
    {"key": "AS|ALARM STROBE", "code": "AS", "glyph": "AS", "label": "ALARM STROBE", "color": "#e53935", "color2": "#e53935", "pattern": "solid", "aliases": ["AS", "red alarm strobe"]},
    {"key": "EA|ENTRAPMENT ALARM", "code": "EA", "glyph": "EA", "label": "ENTRAPMENT ALARM", "color": "#e53935", "color2": "#00a651", "pattern": "split-vertical", "aliases": ["EA", "entrapment horn strobe"]},
    {"key": "S|LIQUID LINE SOLENOID VALVE", "code": "S", "glyph": "S", "label": "LIQUID LINE SOLENOID VALVE", "color": "#8e44ad", "color2": "#8e44ad", "pattern": "solid", "aliases": ["S", "LLS", "liquid line solenoid valve 120V"]},
    {"key": "DT|DEFROST TERMINATION SENSOR", "code": "DT", "glyph": "DT", "label": "DEFROST TERMINATION SENSOR", "color": "#ffd400", "color2": "#00a651", "pattern": "split-vertical", "aliases": ["DT", "defrost termination sensor"]},
    {"key": "S|CLEAN SWITCH", "code": "S", "glyph": "$", "label": "CLEAN SWITCH", "color": "#1e73be", "color2": "#00a651", "pattern": "split-vertical", "aliases": ["$", "clean switch"]},
    {"key": "HS|HORN SILENCER", "code": "HS", "glyph": "HS", "label": "HORN SILENCER", "color": "#5f6b72", "color2": "#5f6b72", "pattern": "solid", "accentDot": "#00a651", "aliases": ["HS", "horn silencer button", "leak silencer"]},
    {"key": "DS|DEFROST SENSOR", "code": "DS", "glyph": "DS", "label": "DEFROST SENSOR", "color": "#1e73be", "color2": "#1e73be", "pattern": "solid", "aliases": ["DS", "defrost sensor"]},
    {"key": "LT|LIGHT LEVEL SENSOR", "code": "LT", "glyph": "LT", "label": "LIGHT LEVEL SENSOR", "color": "#00a8cc", "color2": "#00a8cc", "pattern": "solid", "aliases": ["LT", "light sensor"]},
    {"key": "OAT|OUTDOOR AIR TEMPERATURE SENSOR", "code": "OAT", "glyph": "OAT", "label": "OUTDOOR AIR TEMPERATURE SENSOR", "color": "#00a8cc", "color2": "#00a8cc", "pattern": "solid", "aliases": ["OAT", "outside air temperature sensor"]},
    {"key": "PM|POWER MONITOR", "code": "PM", "glyph": "PM", "label": "POWER MONITOR", "color": "#00a8cc", "color2": "#00a8cc", "pattern": "solid", "aliases": ["PM", "power meter", "power monitor location"]},
    {"key": "T|TEMPERATURE SENSOR", "code": "T", "glyph": "T", "label": "TEMPERATURE SENSOR", "color": "#1e73be", "color2": "#1e73be", "pattern": "solid", "aliases": ["T", "temperature sensor location"]},
    {"key": "EEPR|ELECTRONIC EVAPORATOR PRESSURE REGULATOR", "code": "EEPR", "glyph": "EEPR", "label": "ELECTRONIC EVAPORATOR PRESSURE REGULATOR", "color": "#1e73be", "color2": "#8e44ad", "pattern": "split-vertical", "aliases": ["EEPR", "Electronic EEPR", "Electronic ERP"]},
    {"key": "EPR|MECHANICAL EVAPORATOR PRESSURE REGULATOR", "code": "EPR", "glyph": "EPR", "label": "MECHANICAL EVAPORATOR PRESSURE REGULATOR", "color": "#5f6b72", "color2": "#1e73be", "pattern": "split-vertical", "aliases": ["EPR", "Mechanical EPR", "Mechanical EEPR", "Mechanical ERP"]},
    {"key": "WICP|WALK-IN CONTROL PANEL", "code": "WICP", "glyph": "WICP", "label": "WALK-IN CONTROL PANEL", "color": "#d6d600", "color2": "#d6d600", "pattern": "solid", "aliases": ["WICP", "walk in control panel"]},
]

OBSOLETE_IDS = {
    "s360_rdm_li", "s360_rdm_da", "s360_rdm_ls", "s360_rdm_lsb", "s360_rdm_lsg", "s360_rdm_lsc",
    "s360_rdm_es", "s360_rdm_ea", "s360_rdm_hs", "s360_rdm_ts", "s360_rdm_ds", "s360_rdm_dts",
    "s360_rdm_electric_defrost", "s360_rdm_liquid_solenoid_plan", "s360_rdm_lls_open",
    "s360_rdm_lls_closed", "s360_rdm_eev", "s360_std_anti_sweat_trim", "s360_std_evaporator_fan",
    "s360_std_condenser_fan", "s360_std_evaporator_coil", "s360_std_compressor",
    "s360_std_refrigeration_rack", "s360_std_rdm_idf_marker", "s360_std_mdf_marker",
    "s360_rdm_strobe_li_blue", "s360_rdm_strobe_da_yellow", "s360_rdm_strobe_ea_red",
}
KEEP_SIGN_IDS = {"s360_rdm_sign_pti", "s360_rdm_sign_li", "s360_rdm_sign_help"}
KEEP_REGULATOR_IDS = {"s360_rdm_eepr_electronic", "s360_rdm_eepr_mechanical"}
LINE_CARD_RE = re.compile(
    r"^(?:line legend|cat ?6 drop|fiber link|bacnet link|canbus link|control wiring line|"
    r"existing reference line|line voltage line|power line)$",
    re.IGNORECASE,
)
EXACT_JUNK_NAMES = {
    "din rail", "dimming zone", "dimming zone marker", "electric defrost marker",
    "electric defrost plan marker", "liquid line solenoid marker", "liquid line solenoid plan marker",
    "liquid line solenoid open", "liquid line solenoid closed", "eev electronic expansion valve",
    "electronic expansion valve", "anti sweat trim heater", "anti-sweat / trim heater",
    "evaporator fan", "condenser fan", "evaporator coil", "compressor", "refrigeration rack",
    "rdm idf marker", "mdf server rack marker",
}
SAFETY_SIGNS = [
    {"id": "s360_rdm_sign_pti", "displayName": "Person Trapped Inside Sign", "shortName": "EA-PTI", "defaultLabel": "EA-PTI", "partNumber": "EA-PTI", "aliases": ["Person Trapped Inside", "Person Trapped", "PTI Sign"], "lines": ["PERSON", "TRAPPED", "INSIDE"], "background": "#d100b8", "foreground": "#fff200"},
    {"id": "s360_rdm_sign_li", "displayName": "When Lit Refrigerant Leak — Do Not Enter Sign", "shortName": "LI-A", "defaultLabel": "LI-A", "partNumber": "LI-A", "aliases": ["When Lit Refrigerant Leak", "Leak Do Not Enter", "Do Not Enter"], "lines": ["WHEN LIT", "REFRIGERANT LEAK", "DO NOT ENTER"], "background": "#fff200", "foreground": "#b00020"},
    {"id": "s360_rdm_sign_help", "displayName": "HELP TRAPPED / PERSONA ATRAPADA Sign", "shortName": "EA-MTS", "defaultLabel": "EA-MTS", "partNumber": "EA-MTS", "aliases": ["Help Trapped", "Persona Atrapada", "Man Trap Sign"], "lines": ["HELP TRAPPED", "PERSONA ATRAPADA"], "background": "#d100b8", "foreground": "#fff200"},
]


class InstallError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "marker"


def stable_plan_id(key: str) -> str:
    return f"s360-plan-marker-{hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]}"


def stable_plan_filename(marker: dict[str, Any]) -> str:
    return f"plan__{marker['code'].lower()}__{slug(marker['label'])}.svg"


def _gradient_stops(color1: str, color2: str, pattern: str) -> str:
    if pattern == "split-vertical":
        return (
            f'<stop offset="0%" stop-color="{color1}"/>'
            f'<stop offset="49.9%" stop-color="{color1}"/>'
            f'<stop offset="50%" stop-color="{color2}"/>'
            f'<stop offset="100%" stop-color="{color2}"/>'
        )
    return f'<stop offset="0%" stop-color="{color1}"/><stop offset="100%" stop-color="{color1}"/>'


def _font_size(glyph: str) -> int:
    if len(glyph) <= 1:
        return 34
    if len(glyph) == 2:
        return 29
    if len(glyph) == 3:
        return 23
    return 18


def plan_svg(marker: dict[str, Any]) -> str:
    color1 = str(marker["color"])
    color2 = str(marker.get("color2") or color1)
    pattern = str(marker.get("pattern") or "solid")
    glyph = str(marker.get("glyph") or marker["code"])
    metadata = html.escape(json.dumps({"renderer": PLAN_RENDERER, "standardKey": f"{PLAN_KEY_PREFIX}{marker['key']}", "pattern": pattern}, ensure_ascii=False, separators=(",", ":")))
    accent = ""
    if marker.get("accentDot"):
        accent = f'  <circle data-role="accent-dot" cx="76" cy="19" r="5.5" fill="{marker["accentDot"]}" stroke="#ffffff" stroke-width="2"/>\n'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" preserveAspectRatio="xMidYMid meet">\n'
        f'  <title>{html.escape(glyph)} — {html.escape(str(marker["label"]))}</title>\n'
        f'  <metadata data-renderer="{PLAN_RENDERER}">{metadata}</metadata>\n'
        '  <defs>\n'
        '    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="0">\n'
        f'      {_gradient_stops(color1, color2, pattern)}\n'
        '    </linearGradient>\n'
        '  </defs>\n'
        '  <circle data-role="ring" cx="48" cy="48" r="34" fill="#ffffff" stroke="url(#ring)" stroke-width="5"/>\n'
        f"{accent}"
        f'  <text data-role="glyph" x="48" y="58" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="{_font_size(glyph)}" font-weight="800" fill="#111111">{html.escape(glyph)}</text>\n'
        '</svg>\n'
    )


def sign_svg(sign: dict[str, Any]) -> str:
    lines = list(sign["lines"])
    ys, size = ([31, 51, 72], 14) if len(lines) == 3 else ([39, 64], 15)
    text = "\n".join(
        f'  <text x="80" y="{y}" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" font-weight="800" fill="{sign["foreground"]}">{html.escape(line)}</text>'
        for line, y in zip(lines, ys)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 96" role="img">\n'
        f'  <title>{html.escape(sign["displayName"])}</title>\n'
        f'  <rect x="3" y="3" width="154" height="90" rx="4" fill="{sign["background"]}" stroke="#111111" stroke-width="3"/>\n'
        f"{text}\n"
        '</svg>\n'
    )


def validate_plan_svg(marker: dict[str, Any], text: str) -> None:
    required = [f'data-renderer="{PLAN_RENDERER}"', 'data-role="ring"', 'data-role="glyph"', html.escape(str(marker.get("glyph") or marker["code"]))]
    missing = [token for token in required if token not in text]
    if missing:
        raise InstallError(f"{marker['key']}: invalid plan marker SVG; missing {missing}")
    if '<rect data-role="highlight"' in text:
        raise InstallError(f"{marker['key']}: highlighted Symbol Mapper geometry leaked into Plan Marker SVG")


def backup_runtime(repo: Path, docs: Path) -> Path:
    backup = docs / "patch_backups" / f"component_library_v40_{stamp()}"
    targets = [
        docs / "library" / "manifest.json",
        docs / "library" / "component_builder_export.json",
        docs / "library" / "legend_templates",
        docs / "library" / "components" / "symbols_markers" / "plan_markers",
        docs / "library" / "symbols" / "symbols_markers" / "plan_markers",
        docs / "library" / "thumbnails" / "symbols_markers" / "plan_markers",
        docs / "symbol_mapper" / "templates" / "standard.json",
    ]
    for source in targets:
        if not source.exists():
            continue
        try:
            rel = source.relative_to(repo)
        except ValueError:
            rel = Path(".docs") / source.relative_to(docs)
        target = backup / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    return backup


def is_retired(component: dict[str, Any]) -> bool:
    return bool(component.get("retired")) or str(component.get("status") or "").lower() in {"retired", "duplicate", "junk", "hidden"}


def should_retire(component: dict[str, Any]) -> bool:
    cid = str(component.get("id") or "").strip()
    if cid in OBSOLETE_IDS or cid.startswith("callout_number_"):
        return True
    name = norm(component.get("displayName") or component.get("name") or component.get("defaultLabel"))
    if LINE_CARD_RE.fullmatch(name):
        return True
    collection = str(component.get("collection") or "")
    category = str(component.get("category") or "").lower()
    if cid in KEEP_SIGN_IDS or cid in KEEP_REGULATOR_IDS:
        return False
    if cid.startswith("callout-number-"):
        return False
    if collection in {MAPPER_COLLECTION, PLAN_COLLECTION}:
        return False
    if name == "signage legend":
        return False
    generated = (
        cid.startswith("s360_")
        or str(component.get("assetKind") or "").startswith("singh360-")
        or collection.startswith("RDM Standard")
    )
    if generated and category == "symbols_markers":
        return True
    return generated and name in EXACT_JUNK_NAMES


def retirement_override(component: dict[str, Any]) -> dict[str, Any]:
    existing = dict(component)
    note = str(existing.get("notes") or "").strip()
    line = "Retired by Singh360 Component Library V40 curation; source file preserved."
    if line not in note:
        note = f"{note}\n{line}".strip()
    existing.update({"id": str(component.get("id") or "").strip(), "origin": existing.get("origin") or "override", "retired": True, "status": "retired", "approved": False, "needsReview": False, "retiredBy": "component-library-v40", "notes": note, "updatedAt": now()})
    return existing


def _asset_url(rel: str) -> str:
    clean = str(rel or "").replace("\\", "/").lstrip("/")
    return f"/api/lib/asset/{quote(clean, safe='/-_.~')}" if clean else ""


def _component_asset_rel(component: dict[str, Any]) -> str:
    for key in ("sourceFile", "sourcePath", "symbolFile", "symbolPath", "edgeFile", "edgePath", "bwFile", "bwPath"):
        value = str(component.get(key) or "").replace("\\", "/").lstrip("/")
        if value:
            return value
    return ""


def _find_by_id(entries: list[dict[str, Any]], component_id: str) -> dict[str, Any] | None:
    return next((entry for entry in entries if str(entry.get("id") or "") == component_id), None)


def ensure_callouts(library: LibraryV2, manifest_components: list[dict[str, Any]], builder_components: list[dict[str, Any]]) -> None:
    callout_dir = library.components / "symbols_markers" / "callout_numbers"
    callout_dir.mkdir(parents=True, exist_ok=True)
    for number in range(1, 21):
        cid = f"callout-number-{number:02d}"
        path = callout_dir / f"{cid}.svg"
        if not path.is_file():
            path.write_text(callout_svg(number), encoding="utf-8")
        rel = library._rel(path)
        existing_builder = _find_by_id(builder_components, cid)
        payload = canonical_callout_entry(number, rel)
        if existing_builder is None:
            builder_components.append(payload)
        else:
            aliases = list(dict.fromkeys([*(existing_builder.get("aliases") or []), *(payload.get("aliases") or [])]))
            existing_builder.update(payload)
            existing_builder["aliases"] = aliases
        existing_manifest = _find_by_id(manifest_components, cid)
        override = callout_override_entry(number)
        override.update({"sourceFile": rel, "symbolFile": rel, "edgeFile": rel, "bwFile": rel, "thumbnailFile": rel, "collection": "Callout Numbers"})
        if existing_manifest is None:
            manifest_components.append(override)
        else:
            existing_manifest.update(override)


def normalize_kept_components(manifest_components: list[dict[str, Any]], builder_components: list[dict[str, Any]]) -> None:
    by_id = {str(entry.get("id") or ""): entry for entry in [*builder_components, *manifest_components] if entry.get("id")}
    regulator_updates = {
        "s360_rdm_eepr_electronic": {"displayName": "EEPR — Electronic Evaporator Pressure Regulator", "shortName": "EEPR", "defaultLabel": "EEPR", "partNumber": "EEPR", "aliases": ["EEPR", "Electronic EEPR", "Electronic Evaporator Pressure Regulator", "Electronic ERP"]},
        "s360_rdm_eepr_mechanical": {"displayName": "EPR — Mechanical Evaporator Pressure Regulator", "shortName": "EPR", "defaultLabel": "EPR", "partNumber": "EPR", "aliases": ["EPR", "Mechanical EPR", "Mechanical EEPR", "Mechanical ERP", "Mechanical Evaporator Pressure Regulator"]},
    }
    for cid, patch in regulator_updates.items():
        base = dict(by_id.get(cid) or {"id": cid})
        base.update({**patch, "origin": "override", "category": "refrigeration", "categories": ["refrigeration", "symbols_markers"], "collection": "Refrigeration Control Devices", "approved": True, "needsReview": False, "retired": False, "status": "approved", "updatedAt": now()})
        existing = _find_by_id(manifest_components, cid)
        if existing is None:
            manifest_components.append(base)
        else:
            existing.update(base)
    sign_patches = {
        "s360_rdm_sign_pti": ("Person Trapped Inside Sign", "EA-PTI"),
        "s360_rdm_sign_li": ("When Lit Refrigerant Leak — Do Not Enter Sign", "LI-A"),
        "s360_rdm_sign_help": ("HELP TRAPPED / PERSONA ATRAPADA Sign", "EA-MTS"),
    }
    for cid, (name, label) in sign_patches.items():
        existing = _find_by_id(manifest_components, cid)
        base = dict(existing or by_id.get(cid) or {"id": cid})
        base.update({"id": cid, "origin": base.get("origin") or "override", "displayName": name, "shortName": label, "defaultLabel": label, "partNumber": label, "category": "symbols_markers", "categories": ["symbols_markers", "alarms_safety"], "collection": "Safety Signage", "approved": True, "needsReview": False, "retired": False, "status": "approved", "updatedAt": now()})
        if existing is None:
            manifest_components.append(base)
        else:
            existing.update(base)
    for component in manifest_components:
        cid = str(component.get("id") or "")
        if cid.startswith("callout-number-"):
            component.update({"collection": "Callout Numbers", "approved": True, "needsReview": False, "retired": False, "status": "approved", "updatedAt": now()})
        if norm(component.get("displayName") or "") == "signage legend":
            component.update({"retired": False, "status": "approved", "approved": True})


def ensure_safety_sign_assets(library: LibraryV2, manifest_components: list[dict[str, Any]], builder_components: list[dict[str, Any]]) -> None:
    for sign in SAFETY_SIGNS:
        cid = sign["id"]
        manifest_entry = _find_by_id(manifest_components, cid)
        builder_entry = _find_by_id(builder_components, cid)
        asset_rel = _component_asset_rel(manifest_entry or {}) or _component_asset_rel(builder_entry or {})
        asset_path = library.root / asset_rel if asset_rel else None
        if not asset_rel or asset_path is None or not asset_path.is_file():
            folder = library.components / "symbols_markers" / "safety_signage"
            folder.mkdir(parents=True, exist_ok=True)
            asset_path = folder / f"{cid}.svg"
            asset_path.write_text(sign_svg(sign), encoding="utf-8")
            asset_rel = library._rel(asset_path)
        override = dict(manifest_entry or {})
        override.update({"id": cid, "origin": override.get("origin") or "override", "displayName": sign["displayName"], "shortName": sign["shortName"], "defaultLabel": sign["defaultLabel"], "partNumber": sign["partNumber"], "aliases": sign["aliases"], "category": "symbols_markers", "categories": ["symbols_markers", "alarms_safety"], "collection": "Safety Signage", "sourceFile": asset_rel, "symbolFile": asset_rel, "edgeFile": asset_rel, "bwFile": asset_rel, "thumbnailFile": asset_rel, "defaultWidth": 66, "defaultHeight": 40, "labelPosition": "none", "approved": True, "needsReview": False, "retired": False, "status": "approved", "updatedAt": now()})
        if manifest_entry is None:
            manifest_components.append(override)
        else:
            manifest_entry.update(override)
        builder_payload = {"id": cid, "displayName": sign["displayName"], "category": "symbols_markers", "categories": ["symbols_markers", "alarms_safety"], "manufacturer": "Singh360", "partNumber": sign["partNumber"], "aliases": sign["aliases"], "sourcePath": asset_rel, "edgePath": asset_rel, "bwPath": asset_rel, "symbolPath": asset_rel, "defaultLabel": sign["defaultLabel"], "notes": "Canonical retained Singh360 safety signage.", "chosenVariant": "custom", "preferredEdgeVariant": "custom"}
        if builder_entry is None:
            builder_components.append(builder_payload)
        else:
            builder_entry.update(builder_payload)


def plan_manifest_entry(library: LibraryV2, marker: dict[str, Any], order: int, rel: str, svg_bytes: bytes) -> dict[str, Any]:
    stable_key = f"{PLAN_KEY_PREFIX}{marker['key']}"
    aliases = list(dict.fromkeys([marker["code"], marker["glyph"], marker["label"], *marker.get("aliases", [])]))
    return {"id": stable_plan_id(marker["key"]), "displayName": f"{marker['glyph']} — {marker['label']}", "category": "symbols_markers", "categories": ["symbols_markers"], "subcategory": "plan-markers", "manufacturer": "Singh360", "partNumber": marker["code"], "aliases": aliases, "sourceFile": rel, "thumbnailFile": rel, "symbolFile": rel, "edgeFile": rel, "bwFile": rel, "symbolStatus": "built", "type": "symbol", "assetKind": "singh360-plan-marker", "rendererVersion": PLAN_RENDERER, "sortOrder": order, "defaultLabel": marker["glyph"], "shortName": marker["glyph"], "defaultWidth": 34, "defaultHeight": 34, "labelPosition": "none", "ports": [], "approved": True, "needsReview": False, "favorite": True, "notes": f"Canonical Singh360 simple colored-ring plan marker: {stable_key}", "collection": PLAN_COLLECTION, "status": "approved", "retired": False, "tags": ["singh360-plan-marker", PLAN_RENDERER, f"{KEY_TAG_PREFIX}{stable_key}"], "contentHash": hashlib.sha256(svg_bytes).hexdigest(), "perceptualHash": None, "imageWidth": 96, "imageHeight": 96, "source": {"file": rel, "standardKey": stable_key, "rendererVersion": PLAN_RENDERER}, "updatedAt": now()}


def plan_builder_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {"id": entry["id"], "displayName": entry["displayName"], "category": entry["category"], "categories": entry["categories"], "manufacturer": entry["manufacturer"], "partNumber": entry["partNumber"], "aliases": entry["aliases"], "sourcePath": entry["sourceFile"], "edgePath": entry["edgeFile"], "bwPath": entry["bwFile"], "symbolPath": entry["symbolFile"], "defaultLabel": entry["defaultLabel"], "notes": entry["notes"], "chosenVariant": "custom", "preferredEdgeVariant": "custom"}


def upsert_legend_payload(store: LegendTemplateStore, payload: dict[str, Any]) -> dict[str, Any]:
    store.ensure()
    tid = str(payload["id"])
    full = dict(payload)
    full["updatedAt"] = now()
    full.setdefault("layout", {"background": "#ffffff", "border": "#333333", "fontSize": 9, "rowHeight": 28, "iconWidth": 32})
    write_json(store.root / f"{tid}.json", full)
    manifest = store._read_manifest()
    entries = [entry for entry in (manifest.get("templates") or []) if str(entry.get("id") or "") != tid]
    entry = {"id": tid, "name": full["name"], "category": full.get("category") or "custom", "rowCount": len(full.get("rows") or []), "updatedAt": full["updatedAt"]}
    entries.append(entry)
    preferred = [MAPPER_LEGEND_ID, PLAN_LEGEND_ID, SAFETY_LEGEND_ID]
    entries.sort(key=lambda item: preferred.index(item["id"]) if item.get("id") in preferred else len(preferred))
    manifest["version"] = max(1, int(manifest.get("version") or 1))
    manifest["templates"] = entries
    store._write_manifest(manifest)
    return entry


def update_legends(docs: Path, plan_entries: list[dict[str, Any]], manifest_components: list[dict[str, Any]]) -> dict[str, Any]:
    store = LegendTemplateStore(docs)
    mapper = store.get_template(MAPPER_LEGEND_ID) or {}
    mapper_rows = list(mapper.get("rows") or [])
    if len(mapper_rows) != len(MAPPER_EXPECTED_KEYS):
        raise InstallError(f"Existing Symbol Mapper legend has {len(mapper_rows)} rows; expected {len(MAPPER_EXPECTED_KEYS)}. Run the V39 installer first.")
    mapper.update({"id": MAPPER_LEGEND_ID, "name": "Symbol Mapper Highlight Legend", "category": "symbol-mapper", "title": "SYMBOL MAPPER HIGHLIGHT LEGEND", "rows": mapper_rows, "rendererVersion": MAPPER_RENDERER})
    mapper_entry = upsert_legend_payload(store, mapper)
    plan_by_id = {entry["id"]: entry for entry in plan_entries}
    plan_rows = []
    for marker in PLAN_MARKERS:
        entry = plan_by_id[stable_plan_id(marker["key"])]
        plan_rows.append({"key": entry["source"]["standardKey"], "code": marker["code"], "glyph": marker["glyph"], "label": marker["label"], "name": entry["source"]["standardKey"], "acronym": marker["code"], "shape": "circle", "color": marker["color"], "color2": marker.get("color2") or marker["color"], "pattern": marker.get("pattern") or "solid", "highlighted": True, "rendererVersion": PLAN_RENDERER, "symbolUrl": _asset_url(entry["sourceFile"])})
    plan_entry = upsert_legend_payload(store, {"id": PLAN_LEGEND_ID, "name": "Singh360 Plan Marker Legend", "category": "plan-markers", "title": "PLAN MARKER LEGEND", "rows": plan_rows, "columns": 2, "markerSize": 34, "frame": False, "highlighted": True, "rendererVersion": PLAN_RENDERER})
    sign_rows = []
    by_id = {str(entry.get("id") or ""): entry for entry in manifest_components}
    for sign in SAFETY_SIGNS:
        rel = _component_asset_rel(by_id.get(sign["id"]) or {})
        sign_rows.append({"key": f"SIGN|{sign['id']}", "code": sign["shortName"], "glyph": sign["shortName"], "label": sign["displayName"], "name": sign["id"], "acronym": sign["shortName"], "shape": "none", "highlighted": True, "rendererVersion": "singh360-safety-sign-v40", "symbolUrl": _asset_url(rel)})
    safety_entry = upsert_legend_payload(store, {"id": SAFETY_LEGEND_ID, "name": "Safety Signage Legend", "category": "safety-signage", "title": "SAFETY SIGNAGE LEGEND", "rows": sign_rows, "columns": 1, "markerSize": 42, "frame": False, "highlighted": True, "rendererVersion": "singh360-safety-sign-v40"})
    return {"mapper": mapper_entry, "plan": plan_entry, "safety": safety_entry}


def install(repo: Path, docs: Path) -> dict[str, Any]:
    repo, docs = repo.resolve(), docs.resolve()
    if not (repo / "server.py").is_file():
        raise InstallError(f"Singh360 repository was not found: {repo}")
    docs.mkdir(parents=True, exist_ok=True)
    backup = backup_runtime(repo, docs)
    library = LibraryV2(docs)
    library.ensure()
    library._snapshot_manifest("before-component-library-v40-curation")
    manifest = library._read_manifest()
    manifest_components = [dict(entry) for entry in (manifest.get("components") or []) if isinstance(entry, dict)]
    builder_path = library.root / "component_builder_export.json"
    builder_raw = read_json(builder_path, {"version": "0.3", "components": []})
    if isinstance(builder_raw, list):
        builder_data: dict[str, Any] = {"version": "0.3", "components": list(builder_raw)}
    elif isinstance(builder_raw, dict):
        builder_data = dict(builder_raw)
    else:
        builder_data = {"version": "0.3", "components": []}
    builder_components = [dict(entry) for entry in (builder_data.get("components") or []) if isinstance(entry, dict)]
    ensure_callouts(library, manifest_components, builder_components)
    combined_by_id: dict[str, dict[str, Any]] = {}
    for entry in [*builder_components, *manifest_components]:
        cid = str(entry.get("id") or "").strip()
        if cid:
            combined_by_id[cid] = {**combined_by_id.get(cid, {}), **entry}
    retired_ids: list[str] = []
    for cid, raw in combined_by_id.items():
        if not should_retire(raw):
            continue
        retired_ids.append(cid)
        override = retirement_override(raw)
        existing = _find_by_id(manifest_components, cid)
        if existing is None:
            manifest_components.append(override)
        else:
            existing.update(override)
    normalize_kept_components(manifest_components, builder_components)
    ensure_safety_sign_assets(library, manifest_components, builder_components)
    planned: list[tuple[dict[str, Any], bytes, Path, Path, Path]] = []
    for marker in PLAN_MARKERS:
        svg_text = plan_svg(marker)
        validate_plan_svg(marker, svg_text)
        payload = svg_text.encode("utf-8")
        filename = stable_plan_filename(marker)
        planned.append((marker, payload, library.components / "symbols_markers" / "plan_markers" / filename, library.symbols / "symbols_markers" / "plan_markers" / filename, library.thumbnails / "symbols_markers" / "plan_markers" / filename))
    plan_ids = {stable_plan_id(marker["key"]) for marker in PLAN_MARKERS}
    manifest_components = [entry for entry in manifest_components if str(entry.get("id") or "") not in plan_ids]
    builder_components = [entry for entry in builder_components if str(entry.get("id") or "") not in plan_ids]
    plan_entries: list[dict[str, Any]] = []
    asset_updates = 0
    for order, (marker, payload, source_path, symbol_path, thumb_path) in enumerate(planned, start=1):
        for target in (source_path, symbol_path, thumb_path):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != payload:
                target.write_bytes(payload)
                asset_updates += 1
        rel = library._rel(source_path)
        entry = plan_manifest_entry(library, marker, order, rel, payload)
        manifest_components.append(entry)
        builder_components.append(plan_builder_entry(entry))
        plan_entries.append(entry)
    manifest["version"] = max(2, int(manifest.get("version") or 2))
    manifest["components"] = manifest_components
    manifest["componentLibraryCuration"] = {"version": VERSION, "mapperCollection": MAPPER_COLLECTION, "planCollection": PLAN_COLLECTION, "planRenderer": PLAN_RENDERER, "planCount": len(PLAN_MARKERS), "retiredExactGeneratedCount": len(set(retired_ids)), "updatedAt": now()}
    library._write_manifest(manifest)
    builder_data["version"] = builder_data.get("version") or "0.3"
    builder_data["components"] = builder_components
    builder_data["updatedAt"] = now()
    write_json(builder_path, builder_data)
    legends = update_legends(docs, plan_entries, manifest_components)
    verified = verify(repo, docs)
    return {"ok": True, "version": VERSION, "backup": str(backup), "mapperCount": verified["mapperCount"], "planCount": verified["planCount"], "calloutCount": verified["calloutCount"], "safetySignCount": verified["safetySignCount"], "retiredExactGenerated": len(set(retired_ids)), "retiredIds": sorted(set(retired_ids)), "assetFilesUpdated": asset_updates, "legends": legends, "libraryManifest": str(library.manifest_path), "builderExport": str(builder_path)}


def canonical_key(component: dict[str, Any]) -> str:
    source = component.get("source")
    if isinstance(source, dict):
        value = str(source.get("standardKey") or "").strip()
        if value:
            return value
    for tag in component.get("tags") or []:
        value = str(tag or "")
        if value.startswith(KEY_TAG_PREFIX):
            return value.split(":", 1)[1].strip()
    return ""


def component_renderer(component: dict[str, Any]) -> str:
    value = str(component.get("rendererVersion") or "").strip()
    if value:
        return value
    source = component.get("source")
    return str(source.get("rendererVersion") or "").strip() if isinstance(source, dict) else ""


def verify(repo: Path, docs: Path) -> dict[str, Any]:
    library = LibraryV2(docs)
    library.ensure()
    payload = library.load(include_legacy=False, include_retired=True)
    components = list(payload.get("components") or [])
    active = [entry for entry in components if not is_retired(entry)]
    mapper = [entry for entry in active if str(entry.get("collection") or "") == MAPPER_COLLECTION and component_renderer(entry) == MAPPER_RENDERER]
    if len(mapper) != len(MAPPER_EXPECTED_KEYS):
        raise InstallError(f"Expected {len(MAPPER_EXPECTED_KEYS)} active Symbol Mapper cards; found {len(mapper)}")
    plan = [entry for entry in active if str(entry.get("collection") or "") == PLAN_COLLECTION and component_renderer(entry) == PLAN_RENDERER]
    plan.sort(key=lambda entry: int(entry.get("sortOrder") or 0))
    if len(plan) != len(PLAN_MARKERS):
        raise InstallError(f"Expected {len(PLAN_MARKERS)} active Plan Marker cards; found {len(plan)}")
    actual_keys = [canonical_key(entry) for entry in plan]
    expected_keys = [f"{PLAN_KEY_PREFIX}{marker['key']}" for marker in PLAN_MARKERS]
    if actual_keys != expected_keys:
        raise InstallError(f"Plan Marker order/identity mismatch: {actual_keys}")
    for entry in plan:
        for field in ("sourceFile", "symbolFile", "edgeFile", "bwFile", "thumbnailFile"):
            rel = str(entry.get(field) or "")
            path = library.root / rel
            if not rel or not path.is_file():
                raise InstallError(f"{entry.get('displayName')}: missing {field}: {path}")
        text = (library.root / str(entry["sourceFile"])).read_text(encoding="utf-8")
        if f'data-renderer="{PLAN_RENDERER}"' not in text:
            raise InstallError(f"{entry.get('displayName')}: wrong plan marker renderer")
    callouts = [entry for entry in active if re.fullmatch(r"callout-number-(?:0[1-9]|1[0-9]|20)", str(entry.get("id") or ""))]
    if len(callouts) != 20:
        raise InstallError(f"Expected 20 active Callout Number cards; found {len(callouts)}")
    sign_ids = {str(entry.get("id") or "") for entry in active if str(entry.get("id") or "") in KEEP_SIGN_IDS}
    if sign_ids != KEEP_SIGN_IDS:
        raise InstallError(f"Safety signage is incomplete; active ids={sorted(sign_ids)}")
    by_id = {str(entry.get("id") or ""): entry for entry in active}
    electronic = by_id.get("s360_rdm_eepr_electronic")
    mechanical = by_id.get("s360_rdm_eepr_mechanical")
    if electronic is not None and electronic.get("shortName") != "EEPR":
        raise InstallError("Existing electronic regulator is not normalized to EEPR")
    if mechanical is not None and mechanical.get("shortName") != "EPR":
        raise InstallError("Existing mechanical regulator is not normalized to EPR")
    active_obsolete = [entry for entry in active if str(entry.get("id") or "") in OBSOLETE_IDS or str(entry.get("id") or "").startswith("callout_number_")]
    if active_obsolete:
        raise InstallError(f"Known obsolete generated cards remain active: {[entry.get('id') for entry in active_obsolete]}")
    store = LegendTemplateStore(docs)
    mapper_legend = store.get_template(MAPPER_LEGEND_ID) or {}
    plan_legend = store.get_template(PLAN_LEGEND_ID) or {}
    safety_legend = store.get_template(SAFETY_LEGEND_ID) or {}
    if mapper_legend.get("name") != "Symbol Mapper Highlight Legend" or len(mapper_legend.get("rows") or []) != 15:
        raise InstallError("Symbol Mapper Highlight Legend is missing or incorrect")
    if len(plan_legend.get("rows") or []) != len(PLAN_MARKERS):
        raise InstallError("Plan Marker Legend is missing or incorrect")
    if any(not str(row.get("symbolUrl") or "") for row in plan_legend.get("rows") or []):
        raise InstallError("One or more Plan Marker Legend rows lack an exact symbolUrl")
    if len(safety_legend.get("rows") or []) != 3:
        raise InstallError("Safety Signage Legend is missing or incorrect")
    return {"ok": True, "version": VERSION, "mapperCount": len(mapper), "planCount": len(plan), "calloutCount": len(callouts), "safetySignCount": len(sign_ids), "mapperLegendRows": len(mapper_legend.get("rows") or []), "planLegendRows": len(plan_legend.get("rows") or []), "safetyLegendRows": len(safety_legend.get("rows") or []), "usingBuilderExport": bool(payload.get("usingBuilderExport"))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO)
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
        print(f"INSTALL ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
