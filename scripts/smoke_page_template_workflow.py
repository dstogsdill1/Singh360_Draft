"""Smoke test for page-template upsert, dedupe, and thumbnails."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.page_template_store import PageTemplateStore


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl3lH0AAAAASUVORK5CYII="
)


def page(title: str, src: str) -> dict:
    return {
        "id": "source-page",
        "order": 19,
        "include": True,
        "sheetCode": "EMS 18.0",
        "sheetTitle": title,
        "sheetTab": "EMS 18.0 LCP1",
        "pageType": "canvas",
        "linkedWorksheetId": "ws_18",
        "renderMode": "excel_exact",
        "canvasObjects": [
            {
                "type": "Image",
                "src": src,
                "left": 20,
                "top": 30,
            }
        ],
        "blocks": [],
        "notes": "",
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        docs = Path(directory)
        store = PageTemplateStore(docs)

        first = store.save_template(
            page("LCP-1 Control Wiring Schematic", "data:image/png;base64,AAAA"),
            "LCP-1 Control Wiring Schematic",
            thumbnail_png=PNG_1X1,
        )
        second = store.save_template(
            page("LCP-1 Control Wiring Schematic", "data:image/png;base64,BBBB"),
            "  lcp-1   control wiring schematic  ",
            thumbnail_png=PNG_1X1,
        )

        assert first["id"] == second["id"], (first, second)
        templates = store.list_templates()
        assert len(templates) == 1, templates
        assert templates[0]["hasThumbnail"] is True, templates

        payload = store.get_template(first["id"])
        assert payload is not None
        assert payload["canvasObjects"][0]["src"].endswith("BBBB"), payload
        assert "linkedWorksheetId" not in payload, payload
        assert "renderMode" not in payload, payload
        assert "sheetTab" not in payload, payload

        manifest = json.loads(store.manifest_path.read_text("utf-8"))
        assert manifest["version"] == 2, manifest
        assert len(manifest["templates"]) == 1, manifest

        print("[OK] Page template upsert/dedupe/thumbnail smoke test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
