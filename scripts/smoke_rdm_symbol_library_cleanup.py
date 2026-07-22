from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cleanup_rdm_symbol_library import (
    CANONICAL_COMBINED_LEGEND_ID,
    clean_library,
    restore_library,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def svg(label: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><circle cx="32" cy="32" r="28" fill="white" stroke="black"/><text x="32" y="37" text-anchor="middle" font-family="Arial" font-size="12">{label}</text></svg>'''


def fixture(repo: Path) -> None:
    (repo / "server.py").write_text("# fixture\n", encoding="utf-8")
    write_json(repo / "frontend" / "package.json", {"name": "fixture"})

    standard_rows = [
        ("s360_rdm_li", "LI Leak Indicator Horn/Strobe", "LI"),
        ("s360_rdm_da", "DA Door Open Horn/Strobe", "DA"),
        ("s360_rdm_ls", "LS HFC Refrigerant Leak Sensor", "LS"),
        ("s360_rdm_es", "ES Entrapment Switch", "ES"),
        ("s360_rdm_ea", "EA Entrapment Horn/Strobe", "EA"),
        ("s360_rdm_hs", "HS Leak / Horn Silencer Button", "HS"),
        ("s360_rdm_sign_pti", "Person Trapped Inside Sign Symbol", "EA-PTI"),
        ("s360_rdm_sign_li", "When Lit Refrigerant Leak — Do Not Enter Sign Symbol", "LI-A"),
        ("s360_rdm_sign_help", "HELP TRAPPED / PERSONA ATRAPADA Sign Symbol", "EA-MTS"),
    ]
    standard = []
    catalog = []
    for component_id, name, label in standard_rows:
        category = "symbols_markers"
        rel = f"assets/{category}/{component_id}"
        real = repo / "docs" / "component-library" / rel / "real.svg"
        edge = repo / "docs" / "component-library" / rel / "edge.svg"
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text(svg(label), encoding="utf-8")
        edge.write_text(svg(label), encoding="utf-8")
        standard.append({
            "id": component_id,
            "name": name,
            "cat": category,
            "coll": "RDM Standard — Safety Signage" if "sign_" in component_id else "RDM Standard — WICP Plan",
            "label": label,
            "aliases": [label, name],
            "w": 22 if "sign_" in component_id else 18,
            "h": 22 if "sign_" in component_id else 18,
        })
        catalog.append({
            "id": component_id,
            "displayName": name,
            "category": category,
            "aliases": [label, name],
            "defaultWidth": 22 if "sign_" in component_id else 18,
            "defaultHeight": 22 if "sign_" in component_id else 18,
            "real": f"{rel}/real.svg",
            "edge": f"{rel}/edge.svg",
        })

    legend_id = "signage_legend_safety_trapped_leak_help"
    legend_rel = f"assets/symbols_markers/{legend_id}"
    legend_real = repo / "docs" / "component-library" / legend_rel / "real.svg"
    legend_real.parent.mkdir(parents=True, exist_ok=True)
    legend_real.write_text(svg("3 SIGNS"), encoding="utf-8")
    (legend_real.parent / "edge.svg").write_text(svg("3 SIGNS"), encoding="utf-8")
    catalog.append({
        "id": legend_id,
        "displayName": "Signage Legend - Safety / Trapped / Leak / Help",
        "category": "symbols_markers",
        "aliases": ["Person Trapped", "Help Trapped", "Do Not Enter"],
        "defaultWidth": 220,
        "defaultHeight": 88,
        "real": f"{legend_rel}/real.svg",
        "edge": f"{legend_rel}/edge.svg",
    })

    write_json(repo / "standards" / "rdm_symbols" / "standard.json", {"version": 1, "components": standard})
    write_json(repo / "docs" / "component-library" / "catalog.json", {"version": 1, "components": catalog})

    library = repo / ".docs" / "library"
    write_json(library / "component_builder_export.json", {
        "version": "0.3",
        "components": [
            {
                "id": "callout_number_01",
                "displayName": "Callout Number 1",
                "category": "symbols_markers",
                "aliases": ["Callout 1"],
                "sourcePath": "components/symbols_markers/callout_1.svg",
            },
            {
                "id": "old_li_marker",
                "displayName": "LI Leak Indicator Marker",
                "category": "symbols_markers",
                "defaultWidth": 18,
                "defaultHeight": 18,
            },
            {
                "id": "old_door_alarm_marker",
                "displayName": "Door Alarm Marker",
                "category": "symbols_markers",
                "defaultWidth": 18,
                "defaultHeight": 18,
            },
            {
                "id": "old_person_trapped_sign",
                "displayName": "Person Trapped Inside Symbol",
                "category": "custom",
            },
            {
                "id": "old_help_trapped_sign",
                "displayName": "HELP TRAPPED Symbol",
                "category": "custom",
            },
            {
                "id": "old_signage_legend",
                "displayName": "Signage Legend Safety Trapped Leak Help",
                "category": "custom",
            },
            {
                "id": "hardware_door_strobe",
                "displayName": "Door Open Horn/Strobe DA",
                "category": "alarms_safety",
                "defaultWidth": 44,
                "defaultHeight": 44,
            },
        ],
    })
    callout = library / "components" / "symbols_markers" / "callout_1.svg"
    callout.parent.mkdir(parents=True, exist_ok=True)
    callout.write_text(svg("1"), encoding="utf-8")
    write_json(library / "manifest.json", {"version": "0.3", "components": []})
    locked_legacy = library / "assets" / "components" / "rdm_layout_editor" / "Light"
    locked_legacy.mkdir(parents=True, exist_ok=True)
    (locked_legacy / "DO_NOT_TOUCH.txt").write_text("legacy sentinel\n", encoding="utf-8")
    write_json(library / "legend_templates" / "manifest.json", {
        "version": 1,
        "templates": [
            {"id": "old-rdm-signage", "name": "RDM Safety Signage Standard", "category": "signage", "rowCount": 1},
            {"id": "custom-field-legend", "name": "Custom Field Legend", "category": "custom", "rowCount": 2},
        ],
    })


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="s360_rdm_library_smoke_"))
    try:
        repo = tmp / "repo"
        repo.mkdir()
        fixture(repo)
        result = clean_library(repo)
        assert result["ok"] is True, result
        assert result["signageLegendRows"] == 3, result
        assert result["combinedLegend"] == CANONICAL_COMBINED_LEGEND_ID, result
        assert result["calloutsPreserved"] is True, result
        assert result["sourceAssetsDeleted"] is False, result
        assert result["backupStrategy"] == "targeted-files-v3.1", result
        assert result["legacyAssetsTouched"] is False, result
        assert Path(result["backup"]).is_dir(), result

        library = repo / ".docs" / "library"
        legacy_sentinel = library / "assets" / "components" / "rdm_layout_editor" / "Light" / "DO_NOT_TOUCH.txt"
        assert legacy_sentinel.read_text(encoding="utf-8") == "legacy sentinel\n"
        export = json.loads((library / "component_builder_export.json").read_text(encoding="utf-8"))
        export_rows = export["components"]
        ids = [row["id"] for row in export_rows]
        assert "callout_number_01" in ids, ids
        assert "hardware_door_strobe" in ids, ids
        assert CANONICAL_COMBINED_LEGEND_ID in ids, ids
        for required in ("s360_rdm_li", "s360_rdm_da", "s360_rdm_sign_pti", "s360_rdm_sign_li", "s360_rdm_sign_help"):
            assert required in ids, required

        manifest = json.loads((library / "manifest.json").read_text(encoding="utf-8"))
        by_id = {row["id"]: row for row in manifest["components"]}
        for obsolete in ("old_li_marker", "old_door_alarm_marker", "old_person_trapped_sign", "old_help_trapped_sign", "old_signage_legend"):
            assert by_id[obsolete]["retired"] is True, (obsolete, by_id.get(obsolete))
        assert "hardware_door_strobe" not in by_id or not by_id["hardware_door_strobe"].get("retired"), by_id.get("hardware_door_strobe")
        assert "callout_number_01" not in by_id or not by_id["callout_number_01"].get("retired"), by_id.get("callout_number_01")

        template_manifest = json.loads((library / "legend_templates" / "manifest.json").read_text(encoding="utf-8"))
        template_ids = [row["id"] for row in template_manifest["templates"]]
        assert "rdm-safety-signage-three-sign" in template_ids, template_ids
        assert "custom-field-legend" in template_ids, template_ids
        signage = json.loads((library / "legend_templates" / "rdm-safety-signage-three-sign.json").read_text(encoding="utf-8"))
        assert len(signage["rows"]) == 3, signage
        assert [row["componentId"] for row in signage["rows"]] == [
            "s360_rdm_sign_pti",
            "s360_rdm_sign_li",
            "s360_rdm_sign_help",
        ], signage

        # The targeted backup ignores the legacy assets tree and can restore without
        # deleting the whole library. This directly covers the Windows OneDrive lock
        # that stopped v3.0.
        backup_path = Path(result["backup"])
        restored = restore_library(repo, backup_path)
        assert restored["ok"] is True, restored
        assert restored["legacyAssetsTouched"] is False, restored
        restored_export = json.loads((library / "component_builder_export.json").read_text(encoding="utf-8"))
        assert restored_export["version"] == "0.3", restored_export
        assert legacy_sentinel.read_text(encoding="utf-8") == "legacy sentinel\n"
        assert not (library / "components" / "symbols_markers" / "s360_rdm_li.svg").exists()

        # Idempotent second pass from the restored pre-cleanup state. Decimal string
        # versions are accepted and normalized instead of crashing.
        second = clean_library(repo)
        export2 = json.loads((library / "component_builder_export.json").read_text(encoding="utf-8"))
        ids2 = [row["id"] for row in export2["components"]]
        assert len(ids2) == len(set(ids2)), ids2
        assert ids2.count(CANONICAL_COMBINED_LEGEND_ID) == 1, ids2
        assert second["installedCount"] == result["installedCount"], (result, second)

        print(json.dumps({
            "ok": True,
            "installed": result["installedCount"],
            "retired": result["retiredCount"],
            "combinedLegend": result["combinedLegend"],
            "signageLegendRows": result["signageLegendRows"],
            "calloutsPreserved": True,
            "hardwarePreserved": True,
            "idempotent": True,
            "decimalVersionAccepted": True,
            "targetedRestore": True,
            "lockedLegacyTreeIgnored": True,
        }, indent=2))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
