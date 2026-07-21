from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import shutil
import sys
import tempfile

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from core.symbol_mapper import SymbolMapperStore  # noqa: E402


def fixture_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=396)
    page.insert_text((20, 18), "SYMBOLS KEY", fontsize=9)
    for x, y, code, square, label in [
        (35, 45, "TS", False, "TEMPERATURE SENSOR"),
        (35, 72, "CC", True, "CASE CONTROLLER"),
    ]:
        rect = fitz.Rect(x - 9, y - 9, x + 9, y + 9)
        if square:
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
        else:
            page.draw_circle((x, y), 9, color=(0, 0, 0), width=0.8)
        page.insert_textbox(rect, code, fontsize=6.5, align=fitz.TEXT_ALIGN_CENTER)
        page.insert_text((58, y + 3), label, fontsize=7)

    for x, y, code, square in [
        (150, 150, "TS", False),
        (280, 220, "TS", False),
        (430, 285, "CC", True),
    ]:
        rect = fitz.Rect(x - 10, y - 10, x + 10, y + 10)
        if square:
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
        else:
            page.draw_circle((x, y), 10, color=(0, 0, 0), width=0.8)
        page.insert_textbox(rect, code, fontsize=7, align=fitz.TEXT_ALIGN_CENTER)
    data = doc.tobytes()
    doc.close()
    return data


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="s360_symbol_api_"))
    original_store = server.symbol_mapper_store
    try:
        server.symbol_mapper_store = SymbolMapperStore(temp / "sessions", default_template_path=ROOT / "defaults" / "symbol_mapper_standard.json")
        client = server.app.test_client()
        standard = client.get("/api/symbol-mapper/template")
        assert standard.status_code == 200, standard.get_data(as_text=True)
        assert len(standard.get_json()["template"]["symbols"]) == 13
        updated_standard = client.put("/api/symbol-mapper/template", json={"symbols": [{
            "code": "ZZ",
            "label": "FUTURE TEST SYMBOL",
            "enabled": True,
            "paletteId": "blue",
            "color": "#1e73be",
            "color2": "#1e73be",
            "pattern": "solid",
        }]})
        assert updated_standard.status_code == 200, updated_standard.get_data(as_text=True)
        assert updated_standard.get_json()["total"] == 14

        created = client.post(
            "/api/symbol-mapper/sessions",
            data={"file": (BytesIO(fixture_pdf()), "fixture.pdf")},
            content_type="multipart/form-data",
        )
        assert created.status_code == 201, created.get_data(as_text=True)
        session = created.get_json()
        sid = session["id"]
        assert len(session["template"]["symbols"]) == 14
        legend = session.get("legend") or {}
        assert legend.get("found") is True, legend
        assert [row["code"] for row in legend.get("rows", [])] == ["TS", "CC"], legend

        colors = [
            ("#ffd400", "#ffd400", "solid"),
            ("#e53935", "#1e73be", "split-vertical"),
        ]
        classes = []
        for row, (color, color2, pattern) in zip(legend["rows"], colors):
            classes.append({
                "id": row["id"],
                "code": row["code"],
                "label": row["label"],
                "shape": row["shape"],
                "color": color,
                "color2": color2,
                "pattern": pattern,
                "markerSizePt": row["markerSizePt"],
                "templateBox": row["templateBox"],
                "visualEnabled": False,
            })

        detected = client.post(f"/api/symbol-mapper/sessions/{sid}/detect", json={"classes": classes})
        assert detected.status_code == 200, detected.get_data(as_text=True)
        detection = detected.get_json()
        assert len(detection["candidates"]) == 5, detection
        assert all(candidate["status"] == "accepted" for candidate in detection["candidates"]), detection

        rendered = client.post(
            f"/api/symbol-mapper/sessions/{sid}/render",
            json={"classes": classes, "candidates": detection["candidates"]},
        )
        assert rendered.status_code == 200, rendered.get_data(as_text=True)
        result = rendered.get_json()
        assert result["acceptedCount"] == 5, result

        asset = client.get(result["pdfUrl"])
        assert asset.status_code == 200
        with fitz.open(stream=asset.data, filetype="pdf") as doc:
            assert doc.page_count == 1
            assert doc[0].rect == fitz.Rect(0, 0, 612, 396)
        asset.close()

        deleted = client.delete(f"/api/symbol-mapper/sessions/{sid}")
        assert deleted.status_code == 200
        print(json.dumps({
            "ok": True,
            "sessionId": sid,
            "accepted": result["acceptedCount"],
            "legendRows": len(legend["rows"]),
            "templateSymbols": len(session["template"]["symbols"]),
        }, indent=2))
        return 0
    finally:
        server.symbol_mapper_store = original_store
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
