from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.leak_sensor_standard import (
    HIGHLIGHT_COLLECTION,
    IDS,
    LSC_HIGHLIGHT_ID,
    LSC_PLAN_ID,
    PATHS,
    PLAN_COLLECTION,
    SENSORS,
    apply_leak_sensor_standard,
)
from core.library_v2 import LibraryV2
from core.symbol_mapper import SymbolMapperStore, _normalize_class, _normalize_template_symbol, fitz


class LeakSensorStandardTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        docs = root / ".docs"
        library = docs / "library"
        (library / Path(PATHS[("highlight", "LSc")]).parent).mkdir(parents=True)
        (library / Path(PATHS[("plan", "LSc")]).parent).mkdir(parents=True)
        (library / PATHS[("highlight", "LSc")]).write_text("old highlighted LS2", encoding="utf-8")
        (library / PATHS[("plan", "LSc")]).write_text("old plan LS2", encoding="utf-8")
        records = [
            {"id": LSC_HIGHLIGHT_ID, "sourceFile": PATHS[("highlight", "LSc")], "displayName": "LS₂ old", "retired": False},
            {"id": LSC_PLAN_ID, "sourceFile": PATHS[("plan", "LSc")], "displayName": "LS₂ old", "retired": False},
            {"id": IDS[("highlight", "LS")], "sourceFile": PATHS[("highlight", "LS")], "displayName": "LS old"},
            {"id": IDS[("plan", "LS")], "sourceFile": PATHS[("plan", "LS")], "displayName": "LS old"},
            {"id": "s360_rdm_lsc", "sourceFile": "components/symbols_markers/s360_rdm_lsc.svg", "retired": False},
            {"id": "s360_rdm_ls", "sourceFile": "components/symbols_markers/s360_rdm_ls.svg", "retired": False},
        ]
        (library / "manifest.json").write_text(json.dumps({"version": 2, "components": records}), encoding="utf-8")
        (library / "component_builder_export.json").write_text(json.dumps({"components": []}), encoding="utf-8")
        (library / "symbols.json").write_text("[]", encoding="utf-8")
        (library / "library.json").write_text(json.dumps({"components": [], "symbols": []}), encoding="utf-8")
        (library / "aliases.json").write_text(json.dumps({"version": 1, "aliases": {}}), encoding="utf-8")
        legends = library / "legend_templates"
        legends.mkdir()
        for name, payload in {
            "singh360-refrigeration-symbols-standard.json": {"rows": [{"code": "LS2"}, {"code": "LI2"}]},
            "singh360-plan-marker-legend.json": {"rows": [{"code": "LS"}, {"code": "LS2"}, {"code": "LI"}]},
            "rdm-wicp-safety-standard.json": {"rows": [{"id": "ls"}, {"id": "lsc"}, {"id": "li"}]},
            "wicp_refrigeration_symbol_legend.json": {"items": [{"symbolId": "sym_ls_hfc"}, {"symbolId": "sym_li"}]},
            "wicp_safety_alarm_legend.json": {"rows": [{"componentId": "wicp_ls_hfc"}, {"componentId": "wicp_lsc_co2"}, {"componentId": "wicp_li"}]},
            "legend_template_index.json": {"templates": [{"id": "wicp_safety_alarm_legend", "rows": [{"componentId": "wicp_ls_hfc"}, {"componentId": "wicp_li"}]}]},
            "manifest.json": {"version": 1, "templates": []},
        }.items():
            (legends / name).write_text(json.dumps(payload), encoding="utf-8")
        mapper = docs / "symbol_mapper" / "templates"
        mapper.mkdir(parents=True)
        (mapper / "standard.json").write_text(json.dumps({"symbols": [{"code": "LS2", "label": "old"}, {"code": "LI2", "label": "indicator"}]}), encoding="utf-8")
        return docs

    def test_migration_is_idempotent_and_preserves_audited_ids_and_paths(self) -> None:
        with TemporaryDirectory() as temp:
            docs = self._fixture(Path(temp))
            first = apply_leak_sensor_standard(docs)
            self.assertTrue(first["changed"])
            second = apply_leak_sensor_standard(docs)
            self.assertEqual([], second["changed"])
            manifest = json.loads((docs / "library" / "manifest.json").read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in manifest["components"]}
            self.assertEqual(PATHS[("highlight", "LSc")], by_id[LSC_HIGHLIGHT_ID]["sourceFile"])
            self.assertEqual(PATHS[("plan", "LSc")], by_id[LSC_PLAN_ID]["sourceFile"])
            self.assertTrue(by_id["s360_rdm_lsc"]["retired"])
            self.assertTrue(by_id["s360_rdm_ls"]["retired"])
            for kind, collection in (("highlight", HIGHLIGHT_COLLECTION), ("plan", PLAN_COLLECTION)):
                rows = [item for item in manifest["components"] if item.get("collection") == collection and not item.get("retired")]
                self.assertEqual(
                    [s["code"] for s in SENSORS],
                    [by_id[IDS[(kind, s["code"])]] ["defaultLabel"] for s in SENSORS],
                )
                self.assertEqual(4, len(rows))
            lsc_svg = (docs / "library" / PATHS[("highlight", "LSc")]).read_text(encoding="utf-8")
            self.assertIn('>c</text>', lsc_svg)
            self.assertNotIn("LS₂", lsc_svg)

    def test_library_search_metadata_and_legend_leak_rows(self) -> None:
        with TemporaryDirectory() as temp:
            docs = self._fixture(Path(temp))
            apply_leak_sensor_standard(docs)
            payload = LibraryV2(docs).load(include_legacy=False)
            active = payload["components"]
            for sensor in SENSORS:
                matches = [item for item in active if item.get("defaultLabel") == sensor["code"]]
                self.assertEqual(2, len(matches), sensor["code"])
                haystack = " ".join(str(value) for item in matches for value in (item.get("displayName"), item.get("partNumber"), item.get("manufacturer"), " ".join(item.get("aliases") or [])))
                for needle in (sensor["code"], sensor["description"], sensor["part"], sensor["supplier"]):
                    self.assertIn(needle.lower(), haystack.lower())
            visible = " ".join(item.get("displayName", "") for item in active)
            self.assertNotIn("LS₂", visible)
            for filename, field in (("singh360-refrigeration-symbols-standard.json", "rows"), ("singh360-plan-marker-legend.json", "rows"), ("wicp_refrigeration_symbol_legend.json", "items")):
                data = json.loads((docs / "library" / "legend_templates" / filename).read_text(encoding="utf-8"))
                codes = [str(row.get("code") or "") for row in data[field] if str(row.get("code") or "").lower().startswith("ls")]
                self.assertEqual(["LSc", "LSg", "LS", "LSb"], codes)

    @unittest.skipIf(fitz is None, "PyMuPDF unavailable")
    def test_symbol_mapper_keeps_hidden_ls2_aliases(self) -> None:
        raw = {"code": "LSc", "label": "CO2 Refrigerant Leak Detector", "aliases": ["LS2", "LS₂"], "shape": "circle"}
        normalized = _normalize_template_symbol(raw)
        self.assertEqual(["LS2", "LS₂"], normalized["aliases"])
        cls = _normalize_class(normalized, 0, fitz.Rect(0, 0, 100, 100))
        self.assertIn("LS2", cls["matchTexts"])
        self.assertIn("LS₂", cls["matchTexts"])

    @unittest.skipIf(fitz is None, "PyMuPDF unavailable")
    def test_symbol_mapper_detects_all_four_canonical_codes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = root / "leak-sensors.pdf"
            document = fitz.open()
            page = document.new_page(width=500, height=300)
            for index, sensor in enumerate(SENSORS):
                x = 70 + index * 110
                box = fitz.Rect(x - 22, 120, x + 22, 164)
                page.draw_circle((x, 142), 22, color=(0, 0, 0), width=1)
                page.insert_textbox(box, sensor["code"], fontsize=11, align=fitz.TEXT_ALIGN_CENTER)
            document.save(fixture)
            document.close()
            store = SymbolMapperStore(root / "sessions", default_template_path=Path(__file__).parents[1] / "defaults" / "symbol_mapper_standard.json")
            session = store.create_session(fixture.name, fixture.read_bytes())
            template = session["template"]
            leak_symbols = [item for item in template["symbols"] if item["code"] in {s["code"] for s in SENSORS}]
            classes = [{**item, "id": f"leak-{item['code']}", "markerSizePt": 24, "visualEnabled": False} for item in leak_symbols]
            detection = store.detect(session["id"], {"classes": classes})
            accepted = {item["code"] for item in detection["candidates"] if item["status"] == "accepted"}
            self.assertEqual({"LSc", "LSg", "LS", "LSb"}, accepted)


if __name__ == "__main__":
    unittest.main()
