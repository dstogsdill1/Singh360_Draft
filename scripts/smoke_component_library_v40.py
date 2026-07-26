#!/usr/bin/env python3
"""Isolated regression tests for Singh360 Component Library V40."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.library_v2 import LibraryV2
from scripts.install_component_library_v40 import (
    MAPPER_COLLECTION,
    PLAN_COLLECTION,
    PLAN_MARKERS,
    PLAN_RENDERER,
    SAFETY_LEGEND_ID,
    install,
    is_retired,
    stable_plan_id,
    verify,
)
from scripts.install_symbol_standard_v39 import install as install_v39

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="s360_component_v40_") as temp:
        docs = Path(temp) / ".docs"
        install_v39(ROOT, docs)

        library = LibraryV2(docs)
        manifest = library._read_manifest()
        manifest["components"].extend(
            [
                {
                    "id": "user-component-preserve-me",
                    "displayName": "User Manual Component",
                    "category": "custom",
                    "categories": ["custom"],
                    "favorite": True,
                    "status": "approved",
                    "notes": "Manual user asset must survive V40.",
                    "userCustomField": "preserve",
                },
                {
                    "id": "s360_rdm_electric_defrost",
                    "displayName": "Electric Defrost Plan Marker",
                    "category": "symbols_markers",
                    "collection": "RDM Standard — Refrigeration Plan",
                    "status": "approved",
                    "retired": False,
                },
                {
                    "id": "legacy-line-card",
                    "displayName": "CAT6 Drop",
                    "category": "symbols_markers",
                    "status": "approved",
                    "retired": False,
                },
                {
                    "id": "s360_rdm_eepr_electronic",
                    "displayName": "Electronic EEPR Plan Marker",
                    "category": "symbols_markers",
                    "status": "approved",
                    "retired": False,
                },
                {
                    "id": "s360_rdm_eepr_mechanical",
                    "displayName": "Mechanical EEPR Plan Marker",
                    "category": "symbols_markers",
                    "status": "approved",
                    "retired": False,
                },
            ]
        )
        library._write_manifest(manifest)

        builder_path = docs / "library" / "component_builder_export.json"
        builder = json.loads(builder_path.read_text(encoding="utf-8"))
        builder.setdefault("components", []).extend(
            [
                {"id": "legacy-line-card", "displayName": "CAT6 Drop", "category": "symbols_markers", "sourcePath": ""},
                {"id": "s360_rdm_electric_defrost", "displayName": "Electric Defrost Plan Marker", "category": "symbols_markers", "sourcePath": ""},
            ]
        )
        builder_path.write_text(json.dumps(builder, indent=2), encoding="utf-8")

        first = install(ROOT, docs)
        assert first["mapperCount"] == 15, first
        assert first["planCount"] == len(PLAN_MARKERS), first
        assert first["calloutCount"] == 20, first
        assert first["safetySignCount"] == 3, first
        assert first["assetFilesUpdated"] == len(PLAN_MARKERS) * 3, first

        checked = verify(ROOT, docs)
        assert checked["mapperCount"] == 15
        assert checked["planCount"] == len(PLAN_MARKERS)
        assert checked["calloutCount"] == 20
        assert checked["safetyLegendRows"] == 3

        loaded = library.load(include_legacy=False, include_retired=True)
        components = loaded["components"]
        by_id = {str(component.get("id") or ""): component for component in components}

        manual = by_id["user-component-preserve-me"]
        assert manual["favorite"] is True
        assert manual["userCustomField"] == "preserve"
        assert manual["notes"] == "Manual user asset must survive V40."

        assert is_retired(by_id["s360_rdm_electric_defrost"])
        assert is_retired(by_id["legacy-line-card"])
        assert by_id["s360_rdm_eepr_electronic"]["displayName"].startswith("EEPR")
        assert by_id["s360_rdm_eepr_electronic"]["shortName"] == "EEPR"
        assert by_id["s360_rdm_eepr_mechanical"]["displayName"].startswith("EPR")
        assert by_id["s360_rdm_eepr_mechanical"]["shortName"] == "EPR"

        active = [component for component in components if not is_retired(component)]
        mapper = [component for component in active if component.get("collection") == MAPPER_COLLECTION]
        plan = [component for component in active if component.get("collection") == PLAN_COLLECTION]
        assert len(mapper) == 15
        assert len(plan) == len(PLAN_MARKERS)
        assert all(component.get("rendererVersion") == PLAN_RENDERER for component in plan)
        assert {component["id"] for component in plan} == {stable_plan_id(marker["key"]) for marker in PLAN_MARKERS}

        plan_legend = json.loads((docs / "library" / "legend_templates" / "singh360-plan-marker-legend.json").read_text(encoding="utf-8"))
        assert len(plan_legend["rows"]) == len(PLAN_MARKERS)
        assert all(row.get("symbolUrl") for row in plan_legend["rows"])
        safety_legend = json.loads((docs / "library" / "legend_templates" / f"{SAFETY_LEGEND_ID}.json").read_text(encoding="utf-8"))
        assert len(safety_legend["rows"]) == 3

        second = install(ROOT, docs)
        assert second["planCount"] == len(PLAN_MARKERS), second
        assert second["assetFilesUpdated"] == 0, second
        verify(ROOT, docs)

        final_manifest = library._read_manifest()
        manifest_plan_ids = [
            component.get("id")
            for component in final_manifest.get("components") or []
            if component.get("collection") == PLAN_COLLECTION and not is_retired(component)
        ]
        assert len(manifest_plan_ids) == len(set(manifest_plan_ids)) == len(PLAN_MARKERS)

        print(
            "PASS: V40 preserves user assets, keeps 15 mapper highlights, "
            f"creates {len(PLAN_MARKERS)} plan markers, 20 callouts, and 3 safety signs."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
