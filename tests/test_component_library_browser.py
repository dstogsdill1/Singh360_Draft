from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.component_interop import archive_component, restore_component
from core.library_store import LibraryStore
from core.library_v2 import LibraryV2


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30"/></svg>'


class CountingLibraryV2(LibraryV2):
    def __init__(self, docs_dir: Path) -> None:
        super().__init__(docs_dir)
        self.variant_index_builds = 0

    def _build_variant_index(self):  # type: ignore[override]
        self.variant_index_builds += 1
        return super()._build_variant_index()


class ComponentLibraryBrowserTests(unittest.TestCase):
    def write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def test_load_indexes_symbols_once_and_keeps_retired_legacy_ids_reviewable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / ".docs"
            library = CountingLibraryV2(docs)
            library.ensure()

            source = library.components / "logos" / "heb.svg"
            source.write_bytes(SVG)
            symbol = library.symbols / "logos" / "heb__lineart.svg"
            symbol.write_bytes(SVG)
            legacy_asset = library.root / "assets" / "components" / "symbol" / "heb-legacy.svg"
            legacy_asset.parent.mkdir(parents=True, exist_ok=True)
            legacy_asset.write_bytes(SVG)

            self.write_json(library.root / "component_builder_export.json", {
                "components": [{
                    "id": "heb-current",
                    "displayName": "H-E-B Logo",
                    "category": "logos",
                    "sourcePath": str(source),
                    "edgePath": str(symbol),
                }],
            })
            self.write_json(library.root / "library.json", {
                "components": [{
                    "id": "cmp_6ce7166e39c3",
                    "displayName": "H-E-B Logo",
                    "category": "symbol",
                    "assetPath": "library/assets/components/symbol/heb-legacy.svg",
                    "status": "approved",
                }],
            })

            active = library.load(include_legacy=True, include_retired=False)
            self.assertEqual(1, library.variant_index_builds)
            self.assertEqual(["heb-current"], [component["id"] for component in active["components"]])
            self.assertTrue(active["components"][0]["edgeUrl"])

            legacy_payload = json.loads((library.root / "library.json").read_text(encoding="utf-8"))
            legacy_payload["components"][0]["status"] = "retired"
            self.write_json(library.root / "library.json", legacy_payload)
            library.variant_index_builds = 0

            review = library.load(include_legacy=True, include_retired=True)
            self.assertEqual(1, library.variant_index_builds)
            retired = next(component for component in review["components"] if component["id"] == "cmp_6ce7166e39c3")
            self.assertTrue(retired["retired"])
            self.assertEqual("symbols_markers", retired["category"])
            self.assertEqual("assets/components/symbol/heb-legacy.svg", retired["sourceFile"])

    def test_create_edit_duplicate_retire_restore_and_history_are_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory) / ".docs"
            library = LibraryV2(docs)
            library.ensure()

            created = library.create_component("demo.svg", SVG, {
                "displayName": "Disposable Demo",
                "category": "controllers",
                "collection": "Disposable Tests",
                "tags": ["generated", "safe"],
                "defaultWidth": 120,
                "defaultHeight": 80,
                "favorite": True,
            })
            self.assertTrue(created["ok"])
            component_id = created["component"]["id"]
            self.assertTrue(component_id.startswith("cmp_"))
            self.assertTrue((library.root / created["component"]["sourceFile"]).is_file())

            updated = library.update_component(component_id, {
                "displayName": "Disposable Demo Renamed",
                "collection": "Builder Tests",
            })
            self.assertTrue(updated["snapshot"])
            loaded = next(component for component in library.load()["components"] if component["id"] == component_id)
            self.assertEqual("Disposable Demo Renamed", loaded["displayName"])
            self.assertEqual("Builder Tests", loaded["collection"])
            self.assertEqual(120, loaded["defaultWidth"])
            self.assertTrue(loaded["favorite"])

            duplicate = library.duplicate_component(component_id)
            self.assertTrue(duplicate["ok"])
            self.assertNotEqual(component_id, duplicate["component"]["id"])
            self.assertEqual(loaded["sourceFile"], duplicate["component"]["sourceFile"])
            self.assertTrue(duplicate["snapshot"])

            archived = archive_component(library, component_id)
            self.assertTrue(archived["ok"])
            self.assertFalse(any(component["id"] == component_id for component in library.load()["components"]))
            retired = next(
                component
                for component in library.load(include_retired=True)["components"]
                if component["id"] == component_id
            )
            self.assertTrue(retired["retired"])

            restored = restore_component(library, component_id)
            self.assertTrue(restored["ok"])
            active = next(component for component in library.load()["components"] if component["id"] == component_id)
            self.assertFalse(active["retired"])
            self.assertGreaterEqual(len(library.list_history()), 4)

    def test_legacy_retire_changes_only_target_record_and_creates_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / ".docs"
            store = LibraryStore(docs, root)
            original = {
                "schemaVersion": "0.2",
                "components": [
                    {"id": "keep", "displayName": "Keep", "status": "approved", "tags": ["unchanged"]},
                    {"id": "cmp_6ce7166e39c3", "displayName": "H-E-B Logo", "status": "approved"},
                ],
                "customTopLevel": {"preserve": True},
            }
            self.write_json(store.index_path, original)

            self.assertTrue(store.retire_component("cmp_6ce7166e39c3"))
            retired = json.loads(store.index_path.read_text(encoding="utf-8"))
            expected = json.loads(json.dumps(original))
            expected["components"][1]["status"] = "retired"
            self.assertEqual(expected, retired)

            snapshots = list((store.dir / "history").glob("legacy_library_*__before-retire-cmp_6ce7166e39c3.json"))
            self.assertEqual(1, len(snapshots))
            self.assertEqual(original, json.loads(snapshots[0].read_text(encoding="utf-8")))

            self.assertTrue(store.restore_component("cmp_6ce7166e39c3"))
            restored = json.loads(store.index_path.read_text(encoding="utf-8"))
            self.assertEqual(original, restored)


if __name__ == "__main__":
    unittest.main()
