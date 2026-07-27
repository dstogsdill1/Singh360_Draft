from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fitz

from core.symbol_count_package import build_symbol_mapper_package


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="s360_count_package_") as temp:
        root = Path(temp)
        final_pdf = root / "final.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=1224, height=792)
            page.draw_line((40, 100), (1180, 100), color=(0.25, 0.25, 0.25), width=0.8)
            page.insert_text((50, 80), "HIGHLIGHTED DRAWING", fontsize=18)
            doc.save(final_pdf)

        payload = {
            "title": "SYMBOL COUNTS — R-3.2",
            "drawingCode": "R-3.2",
            "sourceName": "R-3.2 REFG CNTL FLOOR PLAN.pdf",
            "rows": [
                {"code": "DA", "label": "DOOR ALARM", "included": 1, "color": "#00A651", "color2": "#00A651", "pattern": "solid", "shape": "circle"},
                {"code": "LI", "label": "REFRIGERANT LEAK INDICATOR AUDIO/VISUAL ALARM", "included": 1, "color": "#EF3340", "color2": "#FFD100", "pattern": "split-vertical", "shape": "circle"},
                {"code": "CC", "label": "RDM CASE CONTROLLER", "included": 30, "color": "#E83E8C", "color2": "#E83E8C", "pattern": "solid", "shape": "square"},
                {"code": "AS", "label": "ALARM STROBE", "included": 0, "color": "#EF3340", "color2": "#EF3340", "pattern": "solid", "shape": "circle"},
            ],
        }
        result = build_symbol_mapper_package(root, payload)
        package = root / "package.pdf"
        svg = (root / "count_legend.svg").read_text(encoding="utf-8")
        with fitz.open(package) as doc:
            assert doc.page_count == 2, doc.page_count
            assert "HIGHLIGHTED DRAWING" in (doc[0].get_text("text") or "")
            second_text = doc[1].get_text("text") or ""
            assert "DOOR ALARM" in second_text
            assert "RDM CASE CONTROLLER" in second_text
            assert "ALARM STROBE" not in second_text
        assert "#EF3340" in svg and "#FFD100" in svg
        assert "split-vertical" not in svg  # rendered into real gradient/paths, not a label
        assert ">30<" in svg
        assert (root / "count_legend.png").stat().st_size > 1000
        assert result["pageCount"] == 2
        assert result["listedRows"] == 3
        assert result["totalIncluded"] == 32
        print(json.dumps({"ok": True, **result, "splitColorsExact": True, "zeroCountOmitted": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
