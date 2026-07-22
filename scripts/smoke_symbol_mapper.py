from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import shutil
import sys
import tempfile

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.symbol_mapper import SymbolMapperStore, _draw_marker


def _make_fixture(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    # Legend area.
    page.insert_text((40, 40), "SYMBOLS KEY", fontsize=10)
    page.draw_circle((55, 70), 9, color=(0, 0, 0), width=0.8)
    page.insert_textbox(fitz.Rect(46, 61, 64, 79), "TS", fontsize=6.5, align=fitz.TEXT_ALIGN_CENTER)
    page.insert_text((80, 74), "TEMPERATURE SENSOR", fontsize=7)
    page.draw_circle((55, 100), 9, color=(0, 0, 0), width=0.8)
    page.insert_textbox(fitz.Rect(46, 91, 64, 109), "DA", fontsize=6.5, align=fitz.TEXT_ALIGN_CENTER)
    page.insert_text((80, 104), "DOOR ALARM", fontsize=7)
    page.draw_rect(fitz.Rect(46, 121, 64, 139), color=(0, 0, 0), width=0.8)
    page.insert_textbox(fitz.Rect(46, 121, 64, 139), "CC", fontsize=6.5, align=fitz.TEXT_ALIGN_CENTER)
    page.insert_text((80, 134), "CASE CONTROLLER", fontsize=7)
    page.draw_circle((55, 160), 9, color=(0, 0, 0), width=0.8)
    page.insert_textbox(fitz.Rect(46, 151, 64, 169), "S", fontsize=6.5, align=fitz.TEXT_ALIGN_CENTER)
    page.insert_text((80, 164), "LIQUID LINE SOLENOID VALVE 120V", fontsize=7)
    # CLEAN SWITCH is intentionally a plain-text source symbol with no enclosing
    # vector circle. It must be auto-counted from the saved Singh360 standard.
    page.insert_textbox(fitz.Rect(46, 181, 64, 199), "S", fontsize=6.5, align=fitz.TEXT_ALIGN_CENTER)
    page.insert_text((80, 194), "CLEAN SWITCH", fontsize=7)

    # Plan occurrences.
    for x, y, code, shape in [
        (250, 230, "TS", "circle"),
        (350, 290, "TS", "circle"),
        (500, 230, "DA", "circle"),
        (620, 330, "CC", "square"),
        (700, 250, "S", "circle"),
    ]:
        box = fitz.Rect(x - 9, y - 9, x + 9, y + 9)
        if shape == "circle":
            page.draw_circle((x, y), 9, color=(0, 0, 0), width=0.8)
        else:
            page.draw_rect(box, color=(0, 0, 0), width=0.8)
        page.insert_textbox(box, code, fontsize=6.5, align=fitz.TEXT_ALIGN_CENTER)
    # Two plain CLEAN SWITCH occurrences: one S and one $ glyph.
    page.insert_text((250, 455), "S", fontsize=8)
    page.insert_text((350, 455), "$", fontsize=8)
    # Deliberate TS text-only note should remain review, not accepted.
    page.insert_text((250, 400), "VERIFY TS SENSOR LOCATION", fontsize=10)
    doc.save(path)
    doc.close()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="s360_symbol_smoke_"))
    try:
        fixture = tmp / "fixture.pdf"
        _make_fixture(fixture)
        source_hash = sha256(fixture.read_bytes()).hexdigest()
        store = SymbolMapperStore(tmp / "sessions", default_template_path=ROOT / "defaults" / "symbol_mapper_standard.json")
        session = store.create_session(fixture.name, fixture.read_bytes())
        assert session["sourceSha256"] == source_hash
        assert session["pageCount"] == 1
        template = session.get("template") or {}
        assert len(template.get("symbols", [])) == 13, template
        assert len([item for item in template["symbols"] if item["code"] == "S"]) == 2, template

        saved = store.save_template({"symbols": [
            {
                "code": "TS",
                "label": "TEMPERATURE SENSOR",
                "enabled": True,
                "paletteId": "orange",
                "color": "#ff7a00",
                "color2": "#ff7a00",
                "pattern": "solid",
            },
            {
                "code": "ZZ",
                "label": "FUTURE TEST SYMBOL",
                "enabled": True,
                "paletteId": "blue",
                "color": "#1e73be",
                "color2": "#1e73be",
                "pattern": "solid",
            },
        ]})
        assert saved["added"] == 1 and saved["updated"] == 1, saved
        assert saved["total"] == 14, saved
        assert len([item for item in saved["template"]["symbols"] if item["code"] == "S"]) == 2, saved
        assert list((tmp / "sessions" / "templates" / "history").glob("standard-*.json")), saved

        # Split-color outlines must use both colors as actual PDF strokes, not one
        # color around the entire box with a merely split translucent fill.
        marker_doc = fitz.open()
        marker_page = marker_doc.new_page(width=100, height=100)
        _draw_marker(marker_page, fitz.Rect(20, 20, 60, 60), {
            "color": "#ffd400",
            "color2": "#1e73be",
            "pattern": "split-vertical",
        })
        strokes = [drawing.get("color") for drawing in marker_page.get_drawings() if drawing.get("color")]
        assert any(color and color[0] > 0.9 and color[1] > 0.7 and color[2] < 0.1 for color in strokes), strokes
        assert any(color and color[2] > 0.5 and color[0] < 0.3 for color in strokes), strokes
        marker_doc.close()

        legend = session.get("legend") or {}
        assert legend.get("found") is True, legend
        assert [row["code"] for row in legend.get("rows", [])] == ["TS", "DA", "CC", "S", "S"], legend
        assert legend.get("previewDataUrl", "").startswith("data:image/png;base64,"), legend

        choices = [
            ("#ffd400", "#ffd400", "solid"),
            ("#e53935", "#e53935", "solid"),
            ("#00a651", "#1e73be", "split-vertical"),
            ("#8e44ad", "#8e44ad", "solid"),
            ("#1e73be", "#00a651", "split-vertical"),
        ]
        classes = []
        for row, (color, color2, pattern) in zip(legend["rows"], choices):
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
        detection = store.detect(session["id"], {"classes": classes})
        accepted = [c for c in detection["candidates"] if c["status"] == "accepted"]
        review = [c for c in detection["candidates"] if c["status"] == "review"]
        # Field occurrences only: the five printed SYMBOL KEY samples are excluded.
        # TS=2, DA=1, CC=1, solenoid S=1, CLEAN SWITCH=2 (S + $).
        summary_by_label = {row["label"]: row for row in detection["summary"]}
        assert summary_by_label["TEMPERATURE SENSOR"]["accepted"] == 2, summary_by_label
        assert summary_by_label["DOOR ALARM"]["accepted"] == 1, summary_by_label
        assert summary_by_label["CASE CONTROLLER"]["accepted"] == 1, summary_by_label
        assert summary_by_label["LIQUID LINE SOLENOID VALVE 120V"]["accepted"] == 1, summary_by_label
        assert summary_by_label["CLEAN SWITCH"]["accepted"] == 2, summary_by_label
        assert not any(c["label"] == "CLEAN SWITCH" and c["status"] == "review" for c in detection["candidates"]), detection["candidates"]
        assert any(c["label"] == "CLEAN SWITCH" and c["method"] == "exact-text-plain-standard" for c in accepted), accepted
        # Note has a standalone TS word without an enclosing vector marker.
        assert any(c["code"] == "TS" and c["method"] == "text-only" for c in review), review

        # Reject the text-only note and render accepted candidates only.
        reviewed = []
        for item in detection["candidates"]:
            copy = dict(item)
            if copy["method"] == "text-only":
                copy["status"] = "rejected"
                copy["accepted"] = False
            reviewed.append(copy)
        result = store.render(session["id"], {"classes": classes, "candidates": reviewed})
        assert result["acceptedCount"] == 7, result
        assert result["rejectedCount"] >= 1, result
        assert sha256(fixture.read_bytes()).hexdigest() == source_hash

        source_path = store.asset_path(session["id"], "source.pdf")
        final_path = store.asset_path(session["id"], "final.pdf")
        with fitz.open(source_path) as src, fitz.open(final_path) as out:
            assert src.page_count == out.page_count == 1
            assert src[0].rect == out[0].rect
            assert out[0].get_text("text") == src[0].get_text("text")

        report = {
            "ok": True,
            "sessionId": session["id"],
            "accepted": result["acceptedCount"],
            "review": result["reviewCount"],
            "rejected": result["rejectedCount"],
            "outputSha256": result["outputSha256"],
            "legendRows": len(legend["rows"]),
            "templateSymbols": saved["total"],
            "splitOutline": True,
        }
        print(json.dumps(report, indent=2))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
