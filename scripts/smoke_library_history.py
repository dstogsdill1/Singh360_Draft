"""Regression test for library batch history, restore, and all-Legends repair."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.library_v2 import LibraryV2


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        docs = Path(directory)
        library = LibraryV2(docs)
        library.ensure()

        builder = {
            "components": [
                {
                    "id": f"component_{index}",
                    "displayName": f"Component {index}",
                    "category": "controllers" if index % 2 == 0 else "network_data",
                    "sourcePath": "",
                    "edgePath": "",
                    "bwPath": "",
                }
                for index in range(30)
            ]
        }
        write_json(library.root / "component_builder_export.json", builder)

        updates = [
            {
                "id": f"component_{index}",
                "patch": {"category": "legends", "categories": ["legends"]},
            }
            for index in range(30)
        ]
        saved = library.batch_update_components(updates, reason="smoke bulk category")
        assert saved["ok"] is True
        assert saved["updated"] == 30
        assert saved.get("snapshot")

        history = library.list_history()
        assert history, history

        repaired = library.repair_accidental_legend_bulk()
        assert repaired["repaired"] is True, repaired
        assert repaired["restored"] == 30, repaired

        loaded = library.load(include_legacy=True)
        categories = {component["category"] for component in loaded["components"]}
        assert categories == {"controllers", "network_data"}, categories

        second = library.batch_update_components(
            [{"id": "component_0", "patch": {"displayName": "Changed"}}],
            reason="single smoke change",
        )
        snapshot = second["snapshot"]
        assert snapshot
        changed = next(c for c in library.load(include_legacy=True)["components"] if c["id"] == "component_0")
        assert changed["displayName"] == "Changed"

        restored = library.restore_history(snapshot)
        assert restored["ok"] is True
        original = next(c for c in library.load(include_legacy=True)["components"] if c["id"] == "component_0")
        assert original["displayName"] == "Component 0"

        print("[OK] Library history, batch save, restore, and category repair smoke test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
