#!/usr/bin/env python3
"""Static integration gate for exact V39 symbol parity in Component Library legends."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.install_symbol_standard_v39 import EXPECTED_KEYS

ROOT = Path(__file__).resolve().parents[1]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> None:
    modal = (ROOT / "frontend/src/components/SymbolLegendModal.tsx").read_text(encoding="utf-8")
    canvas = (ROOT / "frontend/src/components/CanvasEditor.tsx").read_text(encoding="utf-8")
    client = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    panel = (ROOT / "frontend/src/components/LibraryPanelV2.tsx").read_text(encoding="utf-8")
    standard_payload = json.loads((ROOT / "defaults/symbol_mapper_standard.json").read_text(encoding="utf-8-sig"))

    require(modal, "CANONICAL_RENDERER = 'singh360-map-marker-v39'", "canonical renderer gate")
    require(modal, "canonicalAssetMap", "canonical library asset resolver")
    require(modal, "component.sourceUrl", "exact source SVG URL")
    require(modal, '<img src={row.symbolUrl}', "exact builder preview image")
    require(modal, "symbolUrl: row.highlighted ? row.symbolUrl : undefined", "exact insert payload")
    require(modal, "getLegendTemplate", "saved legend loader")
    require(modal, "rendererVersion === CANONICAL_RENDERER", "saved legend renderer gate")
    require(modal, "Switch to Live Singh360 Standard before saving standard changes.", "saved legend isolation guard")
    require(modal, "STANDARD_TEMPLATE_ID;", "live standard default")

    require(canvas, "addSymbolLegend: async", "async exact legend insertion")
    require(canvas, "FabricImage.fromURL(assetUrl", "Fabric exact SVG loading")
    require(canvas, "const canonicalMarker = loadedMarkers[index]", "canonical row insertion")
    require(canvas, "addFallbackMarker", "custom-row fallback")
    require(canvas, "rec.sourceUrl = assetUrl", "serialized source identity")

    require(client, "export async function getLegendTemplate", "saved legend API client")
    require(panel, "Saved Symbol Legends", "saved legend cards")
    require(panel, "singh360-symbol-legend-template-id", "saved legend handoff")

    actual_keys = [str(item.get("key") or "") for item in standard_payload.get("symbols") or []]
    if actual_keys != EXPECTED_KEYS:
        raise AssertionError(f"canonical standard order mismatch: {actual_keys}")

    print("PASS: exact V39 Component Library SVGs drive builder previews and inserted saved legends")


if __name__ == "__main__":
    main()
