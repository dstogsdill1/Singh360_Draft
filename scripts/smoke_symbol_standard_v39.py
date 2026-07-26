#!/usr/bin/env python3
"""Isolated validation for exact Singh360 refrigeration symbol components V39."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
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
RENDERER_VERSION = "singh360-map-marker-v39"
KEY_TAG_PREFIX = "singh360-symbol-key:"


def run(*args: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.install_symbol_standard_v39",
            "--repo",
            str(REPO),
            *args,
        ],
        check=True,
        cwd=REPO,
    )


def active_by_key(components: list[dict]) -> dict[str, list[dict]]:
    result = {key: [] for key in EXPECTED_KEYS}
    for component in components:
        if component.get("retired") or str(component.get("status") or "").lower() in {
            "retired",
            "duplicate",
            "junk",
        }:
            continue
        tags = set(component.get("tags") or [])
        for key in EXPECTED_KEYS:
            if f"{KEY_TAG_PREFIX}{key}" in tags:
                result[key].append(component)
    return result


def parse_svg(path: Path) -> ET.Element:
    root = ET.parse(path).getroot()
    ns = {"svg": "http://www.w3.org/2000/svg"}
    highlights = root.findall(".//svg:rect[@data-role='highlight']", ns)
    assert len(highlights) == 1, (path, len(highlights))
    metadata = root.find(".//svg:metadata", ns)
    assert metadata is not None
    assert metadata.attrib.get("data-renderer") == RENDERER_VERSION
    return root


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="s360_symbol_v39_") as temp:
        docs = Path(temp) / ".docs"
        first_report = Path(temp) / "first-report.json"
        run("--docs", str(docs), "--report", str(first_report))
        first = json.loads(first_report.read_text(encoding="utf-8"))
        assert first["symbols"] == 15, first
        assert first["rendererVersion"] == RENDERER_VERSION
        assert first["libraryAdded"] == 15, first

        manifest_path = Path(first["libraryManifest"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        components = manifest["components"]
        by_key = active_by_key(components)
        assert all(len(entries) == 1 for entries in by_key.values()), by_key

        da = by_key["DA|DOOR ALARM"][0]
        da["favorite"] = True
        da.setdefault("aliases", []).append("CUSTOM USER DA ALIAS")
        da["userCustomField"] = "must survive"

        unrelated = {
            "id": "user-created-preserve-me",
            "displayName": "User Created Component",
            "category": "custom",
            "status": "approved",
            "favorite": True,
            "notes": "Unrelated user component must survive canonical migration.",
        }
        components.append(unrelated)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        second_report = Path(temp) / "second-report.json"
        run("--docs", str(docs), "--report", str(second_report))
        second = json.loads(second_report.read_text(encoding="utf-8"))
        assert second["libraryAdded"] == 0, second
        assert second["retiredExactDuplicates"] == 0, second
        assert second["runtimeTemplateChanged"] is False, second
        run("--docs", str(docs), "--check")

        final_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        final_components = final_manifest["components"]
        final_by_key = active_by_key(final_components)
        assert all(len(entries) == 1 for entries in final_by_key.values()), final_by_key
        assert sum(len(entries) for entries in final_by_key.values()) == 15
        assert any(component.get("id") == unrelated["id"] for component in final_components)

        final_da = final_by_key["DA|DOOR ALARM"][0]
        assert final_da["favorite"] is True
        assert final_da["userCustomField"] == "must survive"
        assert "CUSTOM USER DA ALIAS" in final_da["aliases"]
        assert final_da["rendererVersion"] == RENDERER_VERSION
        assert final_da["defaultWidth"] == 34
        assert final_da["defaultHeight"] == 34

        ls2 = final_by_key["LS2|CO2 REFRIGERANT LEAK SENSOR"][0]
        assert {"LS2", "LS₂", "LSC", "CO2 LEAK SENSOR", "CO₂ LEAK SENSOR"} <= set(ls2["aliases"])
        li2 = final_by_key["LI2|CO2 REFRIGERANT LEAK INDICATOR AUDIO VISUAL ALARM"][0]
        assert {"LI2", "LI₂", "CO2 LEAK INDICATOR", "CO₂ LEAK INDICATOR"} <= set(li2["aliases"])

        explicit = [
            "DA|DOOR ALARM",
            "LS|REFRIGERANT LEAK DETECTION SENSOR",
            "LS2|CO2 REFRIGERANT LEAK SENSOR",
            "LI|REFRIGERANT LEAK INDICATOR AUDIO VISUAL ALARM",
            "LI2|CO2 REFRIGERANT LEAK INDICATOR AUDIO VISUAL ALARM",
            "CC|RDM CASE CONTROLLER",
            "S|CLEAN SWITCH",
        ]
        ns = {"svg": "http://www.w3.org/2000/svg"}
        for key in explicit:
            component = final_by_key[key][0]
            svg_path = manifest_path.parent / component["sourceFile"]
            root = parse_svg(svg_path)
            source_nodes = root.findall(".//*[@data-role='source-outline']", ns)
            circles = root.findall(".//svg:circle", ns)
            if key == "CC|RDM CASE CONTROLLER":
                assert len(source_nodes) == 1 and source_nodes[0].tag.endswith("rect")
            elif key == "S|CLEAN SWITCH":
                assert source_nodes == []
            else:
                assert len(source_nodes) == 1 and source_nodes[0].tag.endswith("circle")
                assert all(float(node.attrib.get("r", "0")) <= 23 for node in circles)

        template = json.loads(
            (docs / "symbol_mapper" / "templates" / "standard.json").read_text(encoding="utf-8")
        )
        keys = [row["key"] for row in template["symbols"]]
        assert keys == EXPECTED_KEYS
        assert template["rendererVersion"] == RENDERER_VERSION

        legend_manifest = docs / "library" / "legend_templates" / "manifest.json"
        legend_entries = json.loads(legend_manifest.read_text(encoding="utf-8"))["templates"]
        assert any(entry["id"] == "singh360-refrigeration-symbols-standard" for entry in legend_entries)
        legend_path = docs / "library" / "legend_templates" / "singh360-refrigeration-symbols-standard.json"
        legend = json.loads(legend_path.read_text(encoding="utf-8"))
        assert len(legend["rows"]) == 15
        assert all(row["rendererVersion"] == RENDERER_VERSION for row in legend["rows"])

        print("Exact Symbol Component Library V39 isolated validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
