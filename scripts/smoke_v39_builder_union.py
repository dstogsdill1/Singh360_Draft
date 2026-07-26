#!/usr/bin/env python3
"""Regression: stale builder metadata must not hide the two canonical S symbols."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.library_v2 import LibraryV2
from scripts.install_symbol_standard_v39 import (
    COLLECTION,
    EXPECTED_KEYS,
    RENDERER_VERSION,
    install,
)

ROOT = Path(__file__).resolve().parents[1]


def canonical_key(component: dict) -> str:
    source = component.get("source")
    if isinstance(source, dict):
        key = str(source.get("standardKey") or "").strip()
        if key:
            return key
    for tag in component.get("tags") or []:
        value = str(tag or "")
        if value.startswith("singh360-symbol-key:"):
            return value.split(":", 1)[1].strip()
    return ""


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="s360_v39_builder_union_") as temp:
        docs = Path(temp) / ".docs"
        install(ROOT, docs)

        library = LibraryV2(docs)
        manifest = library._read_manifest()
        manifest_by_key = {
            canonical_key(component): component
            for component in manifest.get("components") or []
            if canonical_key(component)
        }
        assert list(manifest_by_key) == EXPECTED_KEYS

        da = manifest_by_key["DA|DOOR ALARM"]
        solenoid = manifest_by_key["S|LIQUID LINE SOLENOID VALVE 120V"]
        export = {
            "components": [
                {
                    "id": da["id"],
                    "displayName": "STALE BUILDER DA",
                    "category": "symbols_markers",
                    "partNumber": "DA",
                    "sourcePath": da["sourceFile"],
                },
                {
                    "id": "stale-builder-generic-s",
                    "displayName": "STALE GENERIC S SYMBOL",
                    "category": "symbols_markers",
                    "partNumber": "S",
                    "sourcePath": solenoid["sourceFile"],
                },
            ]
        }
        (docs / "library" / "component_builder_export.json").write_text(
            json.dumps(export, indent=2),
            encoding="utf-8",
        )

        payload = library.load(include_legacy=False)
        canonical = [
            component
            for component in payload.get("components") or []
            if canonical_key(component) in EXPECTED_KEYS and not component.get("retired")
        ]
        canonical.sort(key=lambda component: int(component.get("sortOrder") or 0))

        actual_keys = [canonical_key(component) for component in canonical]
        assert actual_keys == EXPECTED_KEYS, actual_keys
        assert len([
            component
            for component in payload.get("components") or []
            if component.get("collection") == COLLECTION and not component.get("retired")
        ]) == 15

        loaded_da = next(component for component in canonical if canonical_key(component) == "DA|DOOR ALARM")
        assert loaded_da["displayName"] == da["displayName"]
        assert loaded_da["rendererVersion"] == RENDERER_VERSION
        assert loaded_da["source"]["standardKey"] == "DA|DOOR ALARM"

        s_keys = [key for key in actual_keys if key.startswith("S|")]
        assert s_keys == ["S|LIQUID LINE SOLENOID VALVE 120V", "S|CLEAN SWITCH"]

        print("PASS: builder export union preserves all 15 canonical V39 symbols")


if __name__ == "__main__":
    main()
