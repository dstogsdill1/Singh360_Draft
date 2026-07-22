from __future__ import annotations

"""Install and clean the canonical Singh360 RDM component library.

This is intentionally local-data only. It reads the tracked Singh360 catalog and
standard under the repository, creates a targeted backup of only the active files
it can change, installs the canonical RDM symbols/signs into the active local
library, retires only matching obsolete entries, and writes reusable editable
legend templates. Unrelated legacy assets are never traversed or deleted.

No project, project.json, workbook, PDF, or customer asset is modified.
"""

import argparse
import hashlib
import json
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

VERSION = "3.2.0"
CANONICAL_COMBINED_LEGEND_ID = "s360_rdm_signage_legend_3"
COMBINED_LEGEND_CANDIDATE_IDS = (
    "signage_legend_safety_trapped_leak_help",
    "signage_legend_strip",
    "legends_0e79dadc7d",
)
REQUIRED_STANDARD_IDS = {
    "s360_rdm_li",
    "s360_rdm_da",
    "s360_rdm_ls",
    "s360_rdm_es",
    "s360_rdm_ea",
    "s360_rdm_hs",
    "s360_rdm_sign_pti",
    "s360_rdm_sign_li",
    "s360_rdm_sign_help",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return deepcopy(default)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_copy(source: Path, destination: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".s360tmp")
    last_error: OSError | None = None
    for delay in (0.0, 0.08, 0.20, 0.45, 0.90):
        if delay:
            import time
            time.sleep(delay)
        try:
            shutil.copy2(source, temp)
            temp.replace(destination)
            return destination
        except OSError as exc:
            last_error = exc
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
    raise last_error or OSError(f"Could not copy {source} to {destination}")


def _safe_int(value: Any, fallback: int) -> int:
    """Accept integer, decimal, and semantic-ish numeric values such as '0.3'."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback


def _retry_unlink(path: Path) -> None:
    if not path.exists():
        return
    last_error: OSError | None = None
    for delay in (0.0, 0.08, 0.20, 0.45, 0.90):
        if delay:
            import time
            time.sleep(delay)
        try:
            path.unlink(missing_ok=True)
            return
        except OSError as exc:
            last_error = exc
    raise last_error or OSError(f"Could not remove {path}")


def _repo_ok(repo: Path) -> bool:
    return (
        repo.is_dir()
        and (repo / "server.py").is_file()
        and (repo / "frontend" / "package.json").is_file()
        and (repo / "docs" / "component-library" / "catalog.json").is_file()
        and (repo / "standards" / "rdm_symbols" / "standard.json").is_file()
    )


def _catalog_components(repo: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo / "docs" / "component-library" / "catalog.json", {"components": []})
    rows = payload.get("components") if isinstance(payload, dict) else payload
    return [row for row in (rows or []) if isinstance(row, dict)]


def _standard_components(repo: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo / "standards" / "rdm_symbols" / "standard.json", {"components": []})
    return [row for row in (payload.get("components") or []) if isinstance(row, dict)]


def _asset_path(repo: Path, catalog_record: dict[str, Any], *keys: str) -> Path | None:
    for key in keys:
        raw = str(catalog_record.get(key) or "").replace("\\", "/").lstrip("/")
        if not raw:
            continue
        candidate = (repo / "docs" / "component-library" / raw).resolve()
        root = (repo / "docs" / "component-library").resolve()
        if root in candidate.parents and candidate.is_file():
            return candidate
    return None


def _catalog_match(
    catalog: list[dict[str, Any]],
    standard: dict[str, Any],
) -> dict[str, Any] | None:
    component_id = str(standard.get("id") or "")
    direct = next((row for row in catalog if str(row.get("id") or "") == component_id), None)
    if direct:
        return direct
    needles = {
        _norm(standard.get("name")),
        _norm(standard.get("label")),
        *(_norm(value) for value in (standard.get("aliases") or [])),
    }
    needles.discard("")
    best: tuple[int, dict[str, Any]] | None = None
    for row in catalog:
        hay = {
            _norm(row.get("displayName")),
            _norm(row.get("defaultLabel")),
            _norm(row.get("partNumber")),
            *(_norm(value) for value in (row.get("aliases") or [])),
        }
        score = len(needles & hay)
        if score and (best is None or score > best[0]):
            best = (score, row)
    return best[1] if best else None


def _find_combined_legend(catalog: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_id = {str(row.get("id") or ""): row for row in catalog}
    for component_id in COMBINED_LEGEND_CANDIDATE_IDS:
        row = by_id.get(component_id)
        if row:
            return row
    matches = []
    for row in catalog:
        text = _norm(" ".join([
            str(row.get("id") or ""),
            str(row.get("displayName") or ""),
            " ".join(map(str, row.get("aliases") or [])),
        ]))
        if "signagelegend" in text and (
            "persontrapped" in text or "helptrapped" in text or "donotenter" in text
        ):
            matches.append(row)
    return matches[0] if matches else None


def _targeted_library_paths(
    install_plan: list[tuple[dict[str, Any], dict[str, Any], Path, Path]],
) -> list[str]:
    paths = {
        "component_builder_export.json",
        "manifest.json",
        "legend_templates/manifest.json",
    }
    for definition in _legend_definitions():
        paths.add(f"legend_templates/{definition['id']}.json")
    for component, _catalog_record, source, edge in install_plan:
        component_id = str(component["id"])
        category = str(component.get("cat") or "symbols_markers")
        paths.add(f"components/{category}/{component_id}{source.suffix.lower()}")
        paths.add(f"symbols/{category}/{component_id}{edge.suffix.lower()}")
        paths.add(f"thumbnails/{category}/{component_id}{edge.suffix.lower()}")
    return sorted(paths)


def _library_backup(repo: Path, target_paths: list[str]) -> Path:
    """Back up only files this cleanup can change.

    The legacy library tree can contain OneDrive-locked folders.  Copying or
    deleting the whole tree is both unnecessary and unsafe, so v3.1 records and
    copies the exact active files it will touch and leaves every other file alone.
    """
    library = repo / ".docs" / "library"
    archive = repo / ".docs" / "archive" / f"rdm_symbol_library_targeted_before_v31_{_stamp()}"
    files_root = archive / "files"
    files_root.mkdir(parents=True, exist_ok=False)
    entries: list[dict[str, Any]] = []
    for rel in target_paths:
        target = library / Path(rel)
        existed = target.is_file()
        if existed:
            _safe_copy(target, files_root / Path(rel))
        entries.append({"path": rel, "existed": existed})
    info = {
        "version": VERSION,
        "strategy": "targeted-files-v3.1",
        "createdAt": _now(),
        "source": str(library),
        "files": entries,
        "legacyAssetsTouched": False,
    }
    _write_json(archive / "BACKUP_INFO.json", info)
    return archive


def restore_library(repo: Path, backup: Path) -> dict[str, Any]:
    """Restore only files named in a v3.1 targeted backup.

    No directory tree is removed. This is safe even when OneDrive or the running
    app has a handle open under the unrelated legacy `assets/components` tree.
    """
    repo = repo.resolve()
    backup = backup.resolve()
    if not _repo_ok(repo):
        raise RuntimeError(f"Not a Singh360_SmartDraw repository: {repo}")
    info_path = backup / "BACKUP_INFO.json"
    info = _read_json(info_path, {})
    if not isinstance(info, dict) or info.get("strategy") != "targeted-files-v3.1":
        raise RuntimeError(
            "This backup predates the safe targeted restore format. It was left "
            "untouched; v3.1 will repair the active library without deleting it."
        )
    rows = info.get("files")
    if not isinstance(rows, list):
        raise RuntimeError(f"Targeted library backup is invalid: {backup}")
    library = repo / ".docs" / "library"
    files_root = backup / "files"
    restored = removed = 0
    errors: list[str] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        rel = str(raw.get("path") or "").replace("\\", "/").lstrip("/")
        if not rel or ".." in Path(rel).parts:
            continue
        target = library / Path(rel)
        try:
            if bool(raw.get("existed")):
                source = files_root / Path(rel)
                if not source.is_file():
                    raise FileNotFoundError(source)
                _safe_copy(source, target)
                restored += 1
            else:
                if target.exists():
                    _retry_unlink(target)
                    removed += 1
        except OSError as exc:
            errors.append(f"{rel}: {exc}")
    if errors:
        raise RuntimeError(
            "Targeted library restore could not finish for: " + "; ".join(errors[:8])
        )
    return {
        "ok": True,
        "strategy": "targeted-files-v3.1",
        "restoredFrom": str(backup),
        "restoredFiles": restored,
        "removedNewFiles": removed,
        "library": str(library),
        "legacyAssetsTouched": False,
    }


def _builder_export_shape(path: Path) -> tuple[dict[str, Any] | list[Any], list[dict[str, Any]]]:
    raw = _read_json(path, {"version": 3, "components": []})
    if isinstance(raw, list):
        return raw, [row for row in raw if isinstance(row, dict)]
    if not isinstance(raw, dict):
        raw = {"version": 3, "components": []}
    rows = raw.get("components")
    if not isinstance(rows, list):
        rows = []
        raw["components"] = rows
    return raw, [row for row in rows if isinstance(row, dict)]


def _record_text(record: dict[str, Any]) -> str:
    return _norm(" ".join([
        str(record.get("id") or ""),
        str(record.get("displayName") or record.get("name") or ""),
        str(record.get("defaultLabel") or record.get("label") or ""),
        str(record.get("partNumber") or ""),
        str(record.get("collection") or ""),
        " ".join(map(str, record.get("aliases") or [])),
    ]))


def _duplicate_family(record: dict[str, Any], canonical_ids: set[str]) -> str | None:
    component_id = str(record.get("id") or "")
    if component_id in canonical_ids or component_id == CANONICAL_COMBINED_LEGEND_ID:
        return None
    text = _record_text(record)
    if not text or "callout" in text or component_id.startswith("callout_"):
        return None

    signage_terms = (
        "persontrappedinside",
        "persontrapped",
        "eapti",
        "helptrapped",
        "personaatrapada",
        "eamts",
        "whenlitrefrigerantleak",
        "donotenter",
        "lia",
    )
    if "signagelegend" in text or ("legend" in text and any(term in text for term in signage_terms)):
        return "signage_legend"
    if any(term in text for term in signage_terms):
        return "safety_signage"

    category = str(record.get("category") or "").lower()
    try:
        width = float(record.get("defaultWidth") or record.get("w") or 0)
        height = float(record.get("defaultHeight") or record.get("h") or 0)
    except (TypeError, ValueError):
        width = height = 0
    marker_sized = category == "symbols_markers" or (
        max(width, height) <= 32 and max(width, height) > 0
    ) or "marker" in text or "plansymbol" in text
    if not marker_sized:
        return None

    if "leakindicator" in text or "lihornstrobe" in text:
        return "li_marker"
    if "dooralarm" in text or "dooropenhornstrobe" in text or "damarker" in text:
        return "da_marker"
    if "refrigerantleaksensor" in text or "hfcleaksensor" in text or "co2leaksensor" in text:
        return "ls_marker"
    if "entrapmentswitch" in text or "mantrapswitch" in text:
        return "es_marker"
    if "entrapmentalarm" in text or "entrapmenthornstrobe" in text:
        return "ea_marker"
    if "hornsilencer" in text or "silencebutton" in text:
        return "hs_marker"
    return None


def _canonical_export_record(
    component: dict[str, Any],
    source_rel: str,
    edge_rel: str,
    symbol_rel: str,
) -> dict[str, Any]:
    category = str(component.get("cat") or "symbols_markers")
    label = str(component.get("label") or component.get("name") or "")
    return {
        "id": str(component["id"]),
        "displayName": str(component.get("name") or component["id"]),
        "category": category,
        "categories": [category],
        "collection": str(component.get("coll") or ""),
        "manufacturer": "Singh360",
        "partNumber": label,
        "defaultLabel": label,
        "aliases": list(component.get("aliases") or []),
        "sourcePath": source_rel,
        "edgePath": edge_rel,
        "symbolPath": symbol_rel,
        "notes": "Canonical Singh360 RDM standard installed by v3.2 library cleanup.",
        "status": "approved",
    }


def _canonical_override(
    component: dict[str, Any],
    source_rel: str,
    edge_rel: str,
    symbol_rel: str,
    thumb_rel: str,
    content_hash: str,
) -> dict[str, Any]:
    category = str(component.get("cat") or "symbols_markers")
    label = str(component.get("label") or component.get("name") or "")
    return {
        "id": str(component["id"]),
        "origin": "override",
        "displayName": str(component.get("name") or component["id"]),
        "category": category,
        "categories": [category],
        "collection": str(component.get("coll") or ""),
        "manufacturer": "Singh360",
        "partNumber": label,
        "aliases": list(component.get("aliases") or []),
        "defaultLabel": label,
        "defaultWidth": _safe_int(component.get("w"), 18),
        "defaultHeight": _safe_int(component.get("h"), 18),
        "sourceFile": source_rel,
        "edgeFile": edge_rel,
        "symbolFile": symbol_rel,
        "thumbnailFile": thumb_rel,
        "approved": True,
        "needsReview": False,
        "retired": False,
        "status": "approved",
        "contentHash": content_hash,
        "notes": "Canonical Singh360 RDM standard. Replaces retired duplicate library entries without deleting their source assets.",
        "updatedAt": _now(),
    }


def _legend_row(row_id: str, label: str, terms: Iterable[str], acronym: str, component_id: str) -> dict[str, Any]:
    return {
        "id": row_id,
        "enabled": True,
        "label": label,
        "acronym": acronym,
        "componentId": component_id,
        "searchTerms": list(terms),
        "preferredRep": "edge",
    }


def _legend_definitions() -> list[dict[str, Any]]:
    return [
        {
            "id": "rdm-wicp-safety-standard",
            "name": "RDM WICP / Safety Standard",
            "category": "refrigeration",
            "title": "SYMBOL LEGEND",
            "rows": [
                _legend_row("li", "LI - Leak Indicator Horn/Strobe", ["LI Leak Indicator Horn/Strobe"], "LI", "s360_rdm_li"),
                _legend_row("da", "DA - Door Open Horn/Strobe", ["DA Door Open Horn/Strobe"], "DA", "s360_rdm_da"),
                _legend_row("ls", "LS - HFC Refrigerant Leak Sensor", ["LS HFC Refrigerant Leak Sensor"], "LS", "s360_rdm_ls"),
                _legend_row("lsc", "LSC - CO₂ Refrigerant Leak Sensor", ["LSC CO2 Refrigerant Leak Sensor", "LS CO2"], "LSC", "s360_rdm_lsc"),
                _legend_row("es", "ES - Entrapment Switch", ["ES Entrapment Switch"], "ES", "s360_rdm_es"),
                _legend_row("ea", "EA - Entrapment Horn/Strobe", ["EA Entrapment Horn/Strobe"], "EA", "s360_rdm_ea"),
                _legend_row("hs", "HS - Horn Silencer Button", ["HS Horn Silencer Button"], "HS", "s360_rdm_hs"),
            ],
        },
        {
            "id": "rdm-safety-signage-three-sign",
            "name": "RDM Safety Signage — Three Sign Legend",
            "category": "signage",
            "title": "SIGNAGE LEGEND",
            "rows": [
                _legend_row("person_trapped", "EA-PTI - Person Trapped Inside", ["Person Trapped Inside", "EA-PTI"], "EA-PTI", "s360_rdm_sign_pti"),
                _legend_row("leak_dne", "LI-A - When Lit: Refrigerant Leak / Do Not Enter", ["When Lit Refrigerant Leak Do Not Enter", "LI-A"], "LI-A", "s360_rdm_sign_li"),
                _legend_row("help_trapped", "EA-MTS - HELP TRAPPED / PERSONA ATRAPADA", ["HELP TRAPPED PERSONA ATRAPADA", "EA-MTS"], "EA-MTS", "s360_rdm_sign_help"),
            ],
        },
        {
            "id": "rdm-refrigeration-plan-standard",
            "name": "RDM Refrigeration Plan Standard",
            "category": "refrigeration",
            "title": "REFRIGERATION PLAN LEGEND",
            "rows": [
                _legend_row("ts", "TS - Temperature Sensor", ["TS Temperature Sensor"], "TS", "s360_rdm_ts"),
                _legend_row("ds", "DS - Defrost Sensor", ["DS Defrost Sensor"], "DS", "s360_rdm_ds"),
                _legend_row("dts", "DTS - Dual Temperature Switch", ["DTS Dual Temperature Switch"], "DTS", "s360_rdm_dts"),
                _legend_row("eepr", "EEPR - Electronic Evaporator Pressure Regulator", ["Electronic EEPR"], "EEPR", "s360_rdm_eepr_electronic"),
                _legend_row("epr", "EPR - Mechanical Evaporator Pressure Regulator", ["Mechanical EEPR"], "EPR", "s360_rdm_eepr_mechanical"),
                _legend_row("def", "DEF - Electric Defrost", ["Electric Defrost"], "DEF", "s360_rdm_electric_defrost"),
                _legend_row("lls", "LLS - Liquid Line Solenoid", ["Liquid Line Solenoid Plan Marker"], "LLS", "s360_rdm_liquid_solenoid_plan"),
            ],
        },
        {
            "id": "rdm-wicp-hardware-standard",
            "name": "RDM WICP Hardware Standard",
            "category": "wicp_hardware",
            "title": "WICP HARDWARE LEGEND",
            "rows": [
                _legend_row("li_blue", "Blue - Refrigerant Leak Horn/Strobe", ["Blue Refrigerant Leak Horn/Strobe"], "LI", "s360_rdm_strobe_li_blue"),
                _legend_row("da_yellow", "Yellow - Door Open Horn/Strobe", ["Yellow Door Open Horn/Strobe"], "DA", "s360_rdm_strobe_da_yellow"),
                _legend_row("ea_red", "Red - Entrapment Horn/Strobe", ["Red Entrapment Horn/Strobe"], "EA", "s360_rdm_strobe_ea_red"),
            ],
        },
        {
            "id": "rdm-refrigeration-line-standard",
            "name": "RDM Refrigeration Line Standard",
            "category": "refrigeration",
            "title": "REFRIGERATION SYMBOL LEGEND",
            "rows": [
                _legend_row("lls_open", "LLS - Liquid Line Solenoid Open", ["Liquid Line Solenoid Open"], "LLS", "s360_rdm_lls_open"),
                _legend_row("lls_closed", "LLS - Liquid Line Solenoid Closed", ["Liquid Line Solenoid Closed"], "LLS", "s360_rdm_lls_closed"),
                _legend_row("eev", "EEV - Electronic Expansion Valve", ["Electronic Expansion Valve"], "EEV", "s360_rdm_eev"),
            ],
        },
    ]


def _install_legend_templates(library: Path) -> list[dict[str, Any]]:
    root = library / "legend_templates"
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path, {"version": 1, "templates": []})
    entries = [row for row in (manifest.get("templates") or []) if isinstance(row, dict)]
    definitions = _legend_definitions()
    canonical_ids = {row["id"] for row in definitions}

    # Hide stale copies of the same Singh360 RDM standards. Unmatched/custom
    # templates remain exactly as they were.
    def stale(entry: dict[str, Any]) -> bool:
        if str(entry.get("id") or "") in canonical_ids:
            return True
        text = _norm(" ".join([str(entry.get("name") or ""), str(entry.get("category") or "")]))
        return text.startswith("rdm") and any(key in text for key in ("wicpsafety", "safetysignage", "refrigerationplan", "wicphardware", "refrigerationline"))

    entries = [entry for entry in entries if not stale(entry)]
    installed_entries: list[dict[str, Any]] = []
    for definition in definitions:
        payload = {
            **definition,
            "layout": {
                "background": "#ffffff",
                "border": "#333333",
                "fontSize": 9,
                "rowHeight": 28,
                "iconWidth": 32,
            },
            "updatedAt": _now(),
        }
        _write_json(root / f"{definition['id']}.json", payload)
        entry = {
            "id": definition["id"],
            "name": definition["name"],
            "category": definition["category"],
            "rowCount": len(definition["rows"]),
            "updatedAt": payload["updatedAt"],
        }
        installed_entries.append(entry)
    manifest["version"] = 1
    manifest["templates"] = installed_entries + entries
    _write_json(manifest_path, manifest)
    return installed_entries


def clean_library(repo: Path, *, dry_run: bool = False, create_backup: bool = True) -> dict[str, Any]:
    repo = repo.resolve()
    if not _repo_ok(repo):
        raise RuntimeError(f"Not a Singh360_SmartDraw repository with the tracked RDM standard: {repo}")

    standard = _standard_components(repo)
    catalog = _catalog_components(repo)
    catalog_by_id = {str(row.get("id") or ""): row for row in catalog}
    canonical_ids = {str(row.get("id") or "") for row in standard if row.get("id")}
    missing_required = sorted(REQUIRED_STANDARD_IDS - canonical_ids)
    if missing_required:
        raise RuntimeError(f"The tracked RDM standard is missing required IDs: {missing_required}")

    missing_catalog: list[str] = []
    install_plan: list[tuple[dict[str, Any], dict[str, Any], Path, Path]] = []
    for component in standard:
        match = _catalog_match(catalog, component)
        if not match:
            missing_catalog.append(str(component.get("id") or ""))
            continue
        source = _asset_path(repo, match, "real", "edge")
        edge = _asset_path(repo, match, "edge", "real")
        if source is None or edge is None:
            missing_catalog.append(str(component.get("id") or ""))
            continue
        install_plan.append((component, match, source, edge))

    planned_ids = {str(item[0].get("id") or "") for item in install_plan}
    missing_required_catalog = sorted(REQUIRED_STANDARD_IDS - planned_ids)
    if missing_required_catalog:
        raise RuntimeError(
            "The tracked component catalog is missing required canonical RDM assets: "
            f"{missing_required_catalog}"
        )

    combined_catalog = _find_combined_legend(catalog)
    if not combined_catalog:
        raise RuntimeError("The tracked three-sign signage legend asset was not found in docs/component-library/catalog.json.")
    combined_source = _asset_path(repo, combined_catalog, "real", "edge")
    combined_edge = _asset_path(repo, combined_catalog, "edge", "real")
    if combined_source is None or combined_edge is None:
        raise RuntimeError("The tracked three-sign signage legend is missing its source or edge asset.")
    combined_standard = {
        "id": CANONICAL_COMBINED_LEGEND_ID,
        "name": "RDM Safety Signage — Three Sign Legend",
        "cat": "symbols_markers",
        "coll": "RDM Standard — Safety Signage",
        "label": "Signage Legend",
        "aliases": [
            "Signage Legend - Safety / Trapped / Leak",
            "Three Sign Legend",
            "Person Trapped / Leak Do Not Enter / Help Trapped Legend",
        ],
        "w": _safe_int(combined_catalog.get("defaultWidth"), 220),
        "h": _safe_int(combined_catalog.get("defaultHeight"), 88),
    }
    install_plan.append((combined_standard, combined_catalog, combined_source, combined_edge))
    canonical_ids.add(CANONICAL_COMBINED_LEGEND_ID)

    # A missing optional catalog item is reported but does not erase or invent it.
    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "wouldInstall": [str(item[0]["id"]) for item in install_plan],
            "missingOptionalCatalog": missing_catalog,
            "combinedLegendSourceId": combined_catalog.get("id"),
        }

    target_paths = _targeted_library_paths(install_plan)
    backup = _library_backup(repo, target_paths) if create_backup else None
    rollback_pointer = repo / ".docs" / "patch_logs" / "rdm_symbol_library_cleanup" / "active-backup.txt"
    if backup:
        rollback_pointer.parent.mkdir(parents=True, exist_ok=True)
        rollback_pointer.write_text(str(backup), encoding="utf-8")
    library = repo / ".docs" / "library"
    components_root = library / "components"
    symbols_root = library / "symbols"
    thumbnails_root = library / "thumbnails"
    for root in (components_root, symbols_root, thumbnails_root):
        root.mkdir(parents=True, exist_ok=True)

    export_path = library / "component_builder_export.json"
    export_container, export_rows = _builder_export_shape(export_path)
    export_by_id = {str(row.get("id") or ""): row for row in export_rows}

    manifest_path = library / "manifest.json"
    manifest = _read_json(manifest_path, {"version": 2, "components": []})
    manifest_rows = [row for row in (manifest.get("components") or []) if isinstance(row, dict)]
    manifest_by_id = {str(row.get("id") or ""): row for row in manifest_rows}

    installed: list[str] = []
    for component, _catalog_record, source, edge in install_plan:
        component_id = str(component["id"])
        category = str(component.get("cat") or "symbols_markers")
        source_dest = _safe_copy(source, components_root / category / f"{component_id}{source.suffix.lower()}")
        edge_dest = _safe_copy(edge, symbols_root / category / f"{component_id}{edge.suffix.lower()}")
        thumb_dest = _safe_copy(edge, thumbnails_root / category / f"{component_id}{edge.suffix.lower()}")
        source_rel = source_dest.relative_to(library).as_posix()
        edge_rel = edge_dest.relative_to(library).as_posix()
        thumb_rel = thumb_dest.relative_to(library).as_posix()

        export_by_id[component_id] = _canonical_export_record(component, source_rel, edge_rel, edge_rel)
        manifest_by_id[component_id] = _canonical_override(
            component,
            source_rel,
            edge_rel,
            edge_rel,
            thumb_rel,
            _sha(source_dest),
        )
        installed.append(component_id)

    # Retire only known stale RDM marker/sign/signage entries. Hardware devices,
    # numbered callouts, controllers, and every unrelated component are preserved.
    retired: dict[str, str] = {}
    for row in [*export_rows, *manifest_rows]:
        component_id = str(row.get("id") or "")
        if not component_id or component_id in canonical_ids:
            continue
        family = _duplicate_family(row, canonical_ids)
        if not family:
            continue
        retired[component_id] = family
        existing = manifest_by_id.get(component_id, {"id": component_id, "origin": "override"})
        existing.update({
            "id": component_id,
            "origin": existing.get("origin") or "override",
            "retired": True,
            "status": "retired",
            "notes": (str(existing.get("notes") or "").strip() + f" [Retired by RDM v3 cleanup: replaced by canonical {family}.]").strip(),
            "updatedAt": _now(),
        })
        manifest_by_id[component_id] = existing

    # Retire every obsolete combined signage legend except the one canonical ID.
    for candidate_id in COMBINED_LEGEND_CANDIDATE_IDS:
        if candidate_id in export_by_id or candidate_id in manifest_by_id:
            retired[candidate_id] = "signage_legend"
            existing = manifest_by_id.get(candidate_id, {"id": candidate_id, "origin": "override"})
            existing.update({"retired": True, "status": "retired", "updatedAt": _now()})
            manifest_by_id[candidate_id] = existing

    canonical_export_ids = set(installed)
    preserved_export_order = [row for row in export_rows if str(row.get("id") or "") not in canonical_export_ids]
    canonical_export_rows = [export_by_id[component_id] for component_id in installed]
    updated_export_rows = canonical_export_rows + preserved_export_order
    if isinstance(export_container, list):
        export_container = updated_export_rows
    else:
        export_container["version"] = max(_safe_int(export_container.get("version"), 0), 3)
        export_container["updatedAt"] = _now()
        export_container["components"] = updated_export_rows
    _write_json(export_path, export_container)

    canonical_manifest_rows = [manifest_by_id[component_id] for component_id in installed]
    preserved_manifest_order = [
        row for row in manifest_rows
        if str(row.get("id") or "") not in set(installed) | set(retired)
    ]
    retired_rows = [manifest_by_id[component_id] for component_id in sorted(retired)]
    manifest["version"] = max(_safe_int(manifest.get("version"), 0), 2)
    manifest["updatedAt"] = _now()
    manifest["components"] = canonical_manifest_rows + preserved_manifest_order + retired_rows
    _write_json(manifest_path, manifest)

    templates = _install_legend_templates(library)

    report = {
        "ok": True,
        "version": VERSION,
        "backup": str(backup) if backup else "",
        "installed": installed,
        "installedCount": len(installed),
        "retired": retired,
        "retiredCount": len(retired),
        "missingOptionalCatalog": missing_catalog,
        "combinedLegend": CANONICAL_COMBINED_LEGEND_ID,
        "combinedLegendSourceId": combined_catalog.get("id"),
        "legendTemplates": [entry["id"] for entry in templates],
        "signageLegendRows": 3,
        "calloutsPreserved": True,
        "projectsModified": False,
        "sourceAssetsDeleted": False,
        "backupStrategy": "targeted-files-v3.1",
        "legacyAssetsTouched": False,
    }
    report_dir = repo / ".docs" / "patch_logs" / "rdm_symbol_library_cleanup"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"cleanup-{_stamp()}.json"
    _write_json(report_path, report)
    report["report"] = str(report_path)
    if rollback_pointer.exists():
        rollback_pointer.unlink()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and clean the local Singh360 RDM symbol/component library.")
    parser.add_argument("--repo", default=".", help="Singh360_SmartDraw repository root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", default="", help="Restore .docs/library from a backup created by this tool")
    args = parser.parse_args()
    repo = Path(args.repo).expanduser().resolve()
    try:
        if args.restore:
            result = restore_library(repo, Path(args.restore).expanduser())
        else:
            result = clean_library(repo, dry_run=args.dry_run, create_backup=not args.dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        failure: dict[str, Any] = {"ok": False, "error": str(exc)}
        pointer = repo / ".docs" / "patch_logs" / "rdm_symbol_library_cleanup" / "active-backup.txt"
        if not args.dry_run and not args.restore and pointer.is_file():
            try:
                backup = Path(pointer.read_text(encoding="utf-8").strip())
                failure["backup"] = str(backup)
                restored = restore_library(repo, backup)
                failure["autoRestored"] = True
                failure["restoredFrom"] = restored["restoredFrom"]
                failure["legacyAssetsTouched"] = False
                pointer.unlink(missing_ok=True)
            except Exception as restore_exc:
                failure["autoRestored"] = False
                failure["restoreError"] = str(restore_exc)
        print(json.dumps(failure, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
