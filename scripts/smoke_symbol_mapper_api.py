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
    for x, y, code, square in [
        (90, 80, "TS", False),
        (240, 150, "TS", False),
        (390, 230, "CC", True),
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
        server.symbol_mapper_store = SymbolMapperStore(temp / "sessions")
        client = server.app.test_client()
        created = client.post(
            "/api/symbol-mapper/sessions",
            data={"file": (BytesIO(fixture_pdf()), "fixture.pdf")},
            content_type="multipart/form-data",
        )
        assert created.status_code == 201, created.get_data(as_text=True)
        session = created.get_json()
        sid = session["id"]

        classes = [
            {"id": "ts", "code": "TS", "label": "Temperature Sensor", "shape": "circle", "color": "#ffd400", "color2": "#12539b", "pattern": "solid", "markerSizePt": 22, "visualEnabled": False},
            {"id": "cc", "code": "CC", "label": "Case Controller", "shape": "square", "color": "#00a651", "color2": "#12539b", "pattern": "split-vertical", "markerSizePt": 22, "visualEnabled": False},
        ]
        detected = client.post(f"/api/symbol-mapper/sessions/{sid}/detect", json={"classes": classes})
        assert detected.status_code == 200, detected.get_data(as_text=True)
        detection = detected.get_json()
        assert len(detection["candidates"]) == 3, detection
        assert all(candidate["status"] == "accepted" for candidate in detection["candidates"]), detection

        rendered = client.post(
            f"/api/symbol-mapper/sessions/{sid}/render",
            json={"classes": classes, "candidates": detection["candidates"]},
        )
        assert rendered.status_code == 200, rendered.get_data(as_text=True)
        result = rendered.get_json()
        assert result["acceptedCount"] == 3, result

        asset = client.get(result["pdfUrl"])
        assert asset.status_code == 200
        with fitz.open(stream=asset.data, filetype="pdf") as doc:
            assert doc.page_count == 1
            assert doc[0].rect == fitz.Rect(0, 0, 612, 396)
        # Flask keeps a test response open until explicitly closed. On Windows
        # that can keep final.pdf locked if the route streamed the source path.
        asset.close()

        deleted = client.delete(f"/api/symbol-mapper/sessions/{sid}")
        assert deleted.status_code == 200
        print(json.dumps({"ok": True, "sessionId": sid, "accepted": result["acceptedCount"]}, indent=2))
        return 0
    finally:
        server.symbol_mapper_store = original_store
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
