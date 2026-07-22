from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sheet_index_pagination import ROWS_PER_INDEX_PAGE
from core.sheet_index_sync import sync_project_sheet_index


def require_source(path: Path, *needles: str) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{path}: missing {missing}")


def make_project() -> dict:
    header = ["PAGE", "SHEET CODE", "SHEET TAB", "PAGE TITLE", "INCLUDE", "FAMILY", "PAGE TYPE"]
    index_rows = [
        ["1", "EMS 1.0", "Cover", "Cover / Project Info", "YES", "Cover", "Cover"],
        ["2", "EMS 2.0", "Index", "Sheet Index / TOC", "YES", "Index", "Sheet Index"],
    ]
    pages = [
        {
            "id": "cover", "order": 1, "include": True,
            "sheetCode": "EMS 1.0", "displaySheetCode": "EMS 1.0",
            "sheetTitle": "Cover / Project Info", "sheetTab": "Cover",
            "pageType": "cover", "canvasObjects": [],
        },
        {
            "id": "index", "order": 2, "include": True,
            "sheetCode": "EMS 2.0", "displaySheetCode": "EMS 2.0",
            "sheetTitle": "Sheet Index / TOC", "sheetTab": "Index",
            "pageType": "index", "renderMode": "excel_exact",
            "linkedWorksheetId": "ws_index",
            "blocks": [{"id": "b_index", "type": "excelRange", "grid": [header], "rowHeights": [20]}],
            "canvasObjects": [],
        },
    ]
    for number in range(3, 89):
        code = f"EMS {number}.0"
        tab = f"S{number}"
        title = f"Drawing Page {number}"
        index_rows.append([str(number), code, tab, title, "YES", "Technical", "Table / Schedule"])
        pages.append(
            {
                "id": f"page_{number}", "order": number, "include": True,
                "sheetCode": code, "displaySheetCode": code,
                "sheetTitle": title, "sheetTab": tab,
                "pageType": "table", "pageFamily": "Technical", "canvasObjects": [],
            }
        )
    index_rows.append(["89", "X-1", "Scratch", "Excluded Scratch", "NO", "Internal", "Attachment"])
    pages.append(
        {
            "id": "scratch", "order": 89, "include": False,
            "sheetCode": "X-1", "displaySheetCode": "X-1",
            "sheetTitle": "Excluded Scratch", "sheetTab": "Scratch",
            "pageType": "canvas", "canvasObjects": [],
        }
    )
    return {
        "id": "0123456789abcdef",
        "metadata": {"projectName": "Index Pagination Smoke"},
        "worksheets": [{"id": "ws_index", "name": "00_INDEX", "grid": [header, *index_rows]}],
        "pages": pages,
    }


def main() -> int:
    project = make_project()
    synced = sync_project_sheet_index(project)
    index_pages = [
        page for page in synced["pages"]
        if page.get("pageType") == "index" and page.get("include", True)
    ]
    assert len(index_pages) == 2, len(index_pages)
    assert [page.get("displaySheetCode") for page in index_pages] == ["EMS 2.0", "EMS 2.0a"]
    assert [page.get("order") for page in index_pages] == [2, 3]
    assert index_pages[1].get("indexContinuation") is True

    listed_titles: list[str] = []
    listed_codes: list[str] = []
    row_counts: list[int] = []
    for page in index_pages:
        block = next(block for block in page.get("blocks", []) if block.get("type") == "excelRange")
        grid = block["grid"]
        header_index = next(
            index for index, row in enumerate(grid)
            if "PAGE" in {str(value).upper() for value in row}
            and "SHEET CODE" in {str(value).upper() for value in row}
        )
        body = grid[header_index + 1 :]
        row_counts.append(len(body))
        assert len(body) <= ROWS_PER_INDEX_PAGE
        listed_codes.extend(str(row[1]) for row in body)
        listed_titles.extend(str(row[3]) for row in body)

    included = [page for page in synced["pages"] if page.get("include", True)]
    assert len(listed_titles) == len(included), (len(listed_titles), len(included))
    assert "Excluded Scratch" not in listed_titles
    assert listed_codes[:3] == ["EMS 1.0", "EMS 2.0", "EMS 2.0a"], {
        "codes": listed_codes[:5], "titles": listed_titles[:5]
    }
    assert listed_titles[0] == "Cover / Project Info", listed_titles[:5]
    assert listed_titles[1] == "Sheet Index / TOC", listed_titles[:5]
    continuation_title = " ".join(str(listed_titles[2]).split()).casefold()
    assert continuation_title.startswith("sheet index / toc"), listed_titles[:5]
    assert continuation_title.endswith("continued"), listed_titles[:5]
    assert [page.get("pageNumber") for page in included] == list(range(1, len(included) + 1))

    synced_again = sync_project_sheet_index(synced)
    index_again = [page for page in synced_again["pages"] if page.get("pageType") == "index" and page.get("include", True)]
    assert [page.get("id") for page in index_again] == ["index", "index__index_cont_1"]

    require_source(ROOT / "server.py", "return jsonify(data)", "doc = sync_project_sheet_index(doc)")
    require_source(
        ROOT / "frontend" / "src" / "App.tsx",
        "savedFromServer = normalizeProjectAssetUrls(await saveProject(p))",
    )
    print(json.dumps({
        "ok": True,
        "rowsPerIndexPage": ROWS_PER_INDEX_PAGE,
        "indexPages": len(index_pages),
        "rowCounts": row_counts,
        "finalIncludedPages": len(included),
        "firstListedCodes": listed_codes[:3],
        "firstListedTitles": listed_titles[:3],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
