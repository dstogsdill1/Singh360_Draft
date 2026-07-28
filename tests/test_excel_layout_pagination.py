from __future__ import annotations

import unittest

from core.excel_layout_export import PAGE_HEIGHT, page_count, paginate_layout, paginate_table
from tests.test_excel_layout_export import layout_page


class ExcelLayoutPaginationTests(unittest.TestCase):
    def test_boundary_move_adds_page(self) -> None:
        page = layout_page()
        page["excelLayout"]["tables"][1]["y"] = PAGE_HEIGHT + 30
        self.assertEqual(page_count(page), 2)

    def test_split_rows_and_repeat_options(self) -> None:
        table = layout_page()["excelLayout"]["tables"][0]
        table["y"] = 900
        table["keepTogether"] = False
        table["rows"] = [["H1", "H2", "H3"]] + [[f"R{i}", "neutral", str(i)] for i in range(30)]
        table["rowHeights"] = [28] * len(table["rows"])
        parts = paginate_table(table)
        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[0]["rowEnd"], parts[1]["rowStart"])
        self.assertTrue(all(part["id"] == f"a:{i}" for i, part in enumerate(parts)))
        self.assertEqual({part["tableId"] for part in paginate_layout({"excelLayout": {"tables": [table]}})}, {"a"})

    def test_keep_together_moves_valid_table(self) -> None:
        table = layout_page()["excelLayout"]["tables"][0]
        table["y"] = 940
        parts = paginate_table(table)
        self.assertEqual(parts[0]["page"], 1)
        self.assertEqual(parts[0]["rowStart"], 0)


if __name__ == "__main__":
    unittest.main()
