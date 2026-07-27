from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook, load_workbook

from core.ems_workbook_contract import CANONICAL_REPOSITORY
from core.project_preflight import compute_project_preflight
from core.workbook_importer import import_workbook
from core.workbook_reimport import apply_reimport


def _recipe(workbook: Workbook, tab: str, code: str, title: str) -> None:
    ws = workbook.create_sheet(tab)
    ws.append([title])
    ws.append([code, "page recipe"])
    ws.append([])
    ws.append(["Field", "Value", "Notes"])
    ws.append(["Current Content", "Placeholder", "Recipe rows never publish."])


def _canonical(workbook: Workbook, name: str, headers: list[str], rows: list[list[object]]) -> None:
    ws = workbook.create_sheet(name)
    ws.append([name])
    ws.append(["Canonical editable table"])
    ws.append([])
    ws.append(headers)
    for row in rows:
        ws.append(row)


def write_contract_workbook(path: Path, *, stale: bool = False) -> Path:
    workbook = Workbook()
    meta = workbook.active
    meta.title = "00_PROJECT_META"
    meta.append(["SINGH360 EMS - PROJECT METADATA"])
    meta.append(["Metadata authority"])
    meta.append([])
    meta.append(["Field", "Value", "Authority", "Notes"])
    rows = [
        ["Project Name", "Sanitized 829 Contract Test", "Project", ""],
        ["Drawing Package File Name", "SANITIZED_829_PACKAGE", "Project", ""],
        ["Project Revision", "V3 TEMPLATE" if stale else "R1", "Project", ""],
        ["Template Version", "1.0.0", "Template", ""],
        ["Location", "100 Test Way", "Project", ""],
        ["Linked Project ID", "stale-project" if stale else "", "Application", ""],
        ["Repository", "dstogsdill1/Singh360_SmartDraw" if stale else CANONICAL_REPOSITORY, "Application", ""],
    ]
    for row in rows:
        meta.append(row)

    index = workbook.create_sheet("00_INDEX")
    index.append(["SINGH360 EMS - PAGE MANIFEST"])
    index.append(["Only YES publishes"])
    index.append([])
    index.append(["Include", "Order", "Sheet Code", "Sheet Tab", "Page Title", "Family", "Page Type", "Notes"])
    page_rows = [
        ["YES", 1, "EMS 1.0", "EMS 1.0 Cover", "Cover / Project Info", "cover", "cover", ""],
        ["YES", 2, "EMS 2.0", "EMS 2.0 Sheet Index", "Sheet Index / TOC", "Front Matter", "index", ""],
        ["YES", 3, "EMS 3.0", "EMS 3.0 Guidelines", "Guidelines", "Front Matter", "data-grid", ""],
        ["YES", 4, "EMS 12.0", "EMS 12.0 Overall Layout", "Overall Layout", "Layout", "canvas", ""],
        ["YES", 5, "EMS 13.1", "EMS 13.1 IDF 1", "IDF #1 Port / Network Table", "Network", "data-grid", ""],
        ["YES", 6, "EMS 13.2", "EMS 13.2 IDF 2", "IDF #2 Port / Network Table", "Network", "data-grid", ""],
        ["YES", 7, "EMS 13.3", "EMS 13.3 IDF 3", "IDF #3 Port / Network Table", "Network", "data-grid", ""],
        ["YES", 8, "EMS 24.0", "EMS 24.0 Lighting Matrix", "Lighting Output Matrix", "Lighting", "data-grid", ""],
    ]
    for row in page_rows:
        index.append(row)

    network_rows = [
        [1, 1, 1, "PORT-1", "Generic test device"],
        [1, 1, 2, "PORT-2", "Generic test device"],
        [2, 3, 1, "PORT-3", "Generic test device"],
    ]
    if stale:
        network_rows[0][-1] = "Spare network port - sample from template"
    _canonical(workbook, "21_NETWORK_PORTS", ["IDF", "Switch", "Port", "Label", "Device / Drop"], network_rows)
    _canonical(workbook, "26_LIGHTING_OUTPUTS", ["Output / Zone", "Panel", "Point", "Description"], [["Z-1", "LCP-1", "AO-1", "Generic dimming output"]])
    _canonical(workbook, "32_GUIDELINES", ["Guideline ID", "Topic", "Requirement"], [["G-1", "Testing", "Verify the generated package"]])

    for row in page_rows:
        _recipe(workbook, row[3], row[2], row[4])
    workbook.save(path)
    workbook.close()
    return path


class EmsWorkbookContractTests(unittest.TestCase):
    def test_recipe_pages_render_canonical_tables_and_filter_idf(self) -> None:
        with TemporaryDirectory(prefix="s360_contract_") as raw:
            workbook = write_contract_workbook(Path(raw) / "contract.xlsx")
            project = import_workbook(workbook, project_id="contract-project")

        pages = {page["sheetCode"]: page for page in project["pages"] if not page.get("generatedContinuation")}
        self.assertEqual("Sanitized 829 Contract Test", project["metadata"]["projectName"])
        self.assertEqual("SANITIZED_829_PACKAGE", project["metadata"]["drawingPackageFileName"])
        self.assertEqual("R1", project["metadata"]["revision"])
        self.assertEqual("1.0.0", project["metadata"]["templateVersion"])

        all_blocks = str([page.get("blocks") for page in pages.values()])
        self.assertNotIn("Current Content", all_blocks)
        self.assertNotIn("Placeholder", all_blocks)

        idf1 = pages["EMS 13.1"]
        idf2 = pages["EMS 13.2"]
        self.assertEqual("21_NETWORK_PORTS", idf1["sourceSheet"])
        self.assertEqual(2, idf1["canonicalDataRowCount"])
        self.assertEqual(1, idf2["canonicalDataRowCount"])
        self.assertEqual(
            {"1"},
            {
                str(row[0])
                for row in idf1["blocks"][0]["grid"][4:]
                if row and str(row[0]).strip()
            },
        )
        self.assertEqual(
            {"2"},
            {
                str(row[0])
                for row in idf2["blocks"][0]["grid"][4:]
                if row and str(row[0]).strip()
            },
        )
        self.assertEqual("32_GUIDELINES", pages["EMS 3.0"]["sourceSheet"])
        self.assertEqual("26_LIGHTING_OUTPUTS", pages["EMS 24.0"]["sourceSheet"])

        cover_text = str(pages["EMS 1.0"]["blocks"])
        self.assertIn("SANITIZED_829_PACKAGE", cover_text)
        self.assertIn("Project Revision: R1", cover_text)
        self.assertNotIn("Template Version", cover_text)

    def test_preflight_reports_empty_mapping_and_stale_template_data(self) -> None:
        with TemporaryDirectory(prefix="s360_preflight_") as raw:
            workbook = write_contract_workbook(Path(raw) / "stale.xlsx", stale=True)
            project = import_workbook(workbook, project_id="contract-project")

        codes = {issue["code"] for issue in compute_project_preflight(project)}
        self.assertIn("included_page_no_mapped_data", codes)
        self.assertIn("stale_linked_project_id", codes)
        self.assertIn("stale_repository_name", codes)
        self.assertIn("template_text_in_project_revision", codes)
        self.assertIn("sample_engineering_rows", codes)
        self.assertNotIn("included_page_recipe_only", codes)

    def test_manual_canvas_objects_survive_canonical_reimport(self) -> None:
        with TemporaryDirectory(prefix="s360_contract_reimport_") as raw:
            workbook = write_contract_workbook(Path(raw) / "contract.xlsx")
            project = import_workbook(workbook, project_id="contract-project")
            layout = next(page for page in project["pages"] if page["sheetCode"] == "EMS 12.0")
            layout["canvasObjects"] = [{"type": "textbox", "text": "manual survives"}]
            updated, summary = apply_reimport(
                project,
                workbook,
                project_id="contract-project",
                source_filename=workbook.name,
            )

        updated_layout = next(page for page in updated["pages"] if page["sheetCode"] == "EMS 12.0")
        self.assertEqual("manual survives", updated_layout["canvasObjects"][0]["text"])
        self.assertIn("EMS 12.0", summary["preserved"])

    def test_tracked_runtime_template_is_clean_and_styled(self) -> None:
        template = (
            Path(__file__).resolve().parents[1]
            / "defaults"
            / "runtime_templates"
            / "Singh360_BASE_Project_Workbook_Template_V1.xlsx"
        )
        workbook = load_workbook(template)
        try:
            for required in (
                "00_PROJECT_META", "00_INDEX", "21_NETWORK_PORTS",
                "31_OPEN_ITEMS", "32_GUIDELINES", "37_RESPONSIBILITY_MATRIX",
            ):
                self.assertIn(required, workbook.sheetnames)
            for name in ("21_NETWORK_PORTS", "32_GUIDELINES"):
                ws = workbook[name]
                self.assertEqual("00D97706", ws["A1"].fill.fgColor.rgb)
                self.assertEqual("001F4E78", ws["A2"].fill.fgColor.rgb)
                self.assertIsNone(ws["A3"].value)
                self.assertEqual("00A6A6A6", ws["A4"].fill.fgColor.rgb)
                self.assertTrue(all(ws.cell(row, 1).value in (None, "") for row in range(5, 20)))
            metadata = {
                str(row[0].value): str(row[1].value or "")
                for row in workbook["00_PROJECT_META"].iter_rows(min_row=5)
                if row[0].value
            }
            self.assertEqual("", metadata["Linked Project ID"])
            self.assertEqual(CANONICAL_REPOSITORY, metadata["Repository"])
            self.assertEqual("TBD", metadata["Project Revision"])
            self.assertEqual("1.0.0", metadata["Template Version"])
            blob = " ".join(str(cell.value or "") for ws in workbook for row in ws for cell in row)
            self.assertNotIn("SmartDraw", blob)
        finally:
            workbook.close()


if __name__ == "__main__":
    unittest.main()
