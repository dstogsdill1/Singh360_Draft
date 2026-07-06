"""scripts/smoke_pdf_import.py — high-res PDF crop import smoke.

Validates the Insert PDF Crop workflow end-to-end through the Flask API:
  - upload-preview (page dimensions in pt/in + preview image)
  - full page render at 300 DPI
  - crop render at 600 DPI using point coordinates
  - add rendered crop object to page canvas + save/reload
  - export package contains rendered crop asset and source PDF
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
    import server  # noqa: E402

    workbook = ROOT / "sample_data" / "S360_EMS_Simple_Workbook.xlsx"
    pdf_path = ROOT / "sample_data" / "Kyle_Specs.pdf"
    if not workbook.exists() or not pdf_path.exists():
        print("ERROR: missing sample workbook/PDF under sample_data/")
        return 2

    c = server.app.test_client()
    problems: list[str] = []

    # 1) Create project.
    with open(workbook, "rb") as fh:
        created = c.post(
            "/api/projects/new",
            data={"file": (io.BytesIO(fh.read()), "S360_EMS_Simple_Workbook.xlsx")},
            content_type="multipart/form-data",
        )
    if created.status_code != 200:
        print(f"FAIL create project: {created.status_code}")
        return 1
    pid = created.get_json()["id"]
    print(f"created project: {pid}")

    # 2) Upload PDF + preview pages.
    with open(pdf_path, "rb") as fh:
        up = c.post(
            f"/api/projects/{pid}/pdf/upload-preview",
            data={"file": (io.BytesIO(fh.read()), "Kyle_Specs.pdf")},
            content_type="multipart/form-data",
        )
    if up.status_code != 200:
        problems.append(f"upload-preview failed ({up.status_code})")
        print(up.get_data(as_text=True)[:400])
        c.delete(f"/api/projects/{pid}")
        return 1
    preview = up.get_json()
    pages = preview.get("pages", [])
    print(f"preview pages: {len(pages)}")
    if not pages:
        problems.append("upload-preview returned zero pages")
    else:
        p0 = pages[0]
        needed = ["widthPt", "heightPt", "widthIn", "heightIn", "previewDataUrl"]
        if any(k not in p0 for k in needed):
            problems.append("upload-preview missing page dimensions/preview fields")

    pdf_file = preview.get("pdfFile")

    # 3) Render full page at 300 DPI.
    rp = c.post(
        f"/api/projects/{pid}/pdf/render-page",
        json={"pdfFile": pdf_file, "page": 0, "dpi": 300},
    )
    if rp.status_code != 200:
        problems.append(f"render-page failed ({rp.status_code})")
        print(rp.get_data(as_text=True)[:400])
    else:
        page_meta = rp.get_json().get("meta", {})
        print(f"full page render: {page_meta.get('outputWidth')}x{page_meta.get('outputHeight')} @ {page_meta.get('dpi')} DPI")

    # 4) Render crop at 600 DPI using point coords.
    clip = {"x0": 72, "y0": 72, "x1": 72 * 8, "y1": 72 * 5}
    rc = c.post(
        f"/api/projects/{pid}/pdf/render-crop",
        json={"pdfFile": pdf_file, "page": 0, "dpi": 600, "clip": clip, "autocrop": False},
    )
    crop_asset_url = ""
    crop_asset_name = ""
    crop_meta = {}
    if rc.status_code != 200:
        problems.append(f"render-crop failed ({rc.status_code})")
        print(rc.get_data(as_text=True)[:400])
    else:
        rcj = rc.get_json()
        crop_asset_url = rcj["asset"]["url"]
        crop_asset_name = rcj["asset"]["name"]
        crop_meta = rcj.get("meta", {})
        print(f"crop render: {crop_meta.get('outputWidth')}x{crop_meta.get('outputHeight')} @ {crop_meta.get('dpi')} DPI")
        if crop_meta.get("dpi") != 600:
            problems.append("render-crop did not honor 600 DPI")

    # 5) Add crop image object to canvas + save/reload serialization proof.
    doc = c.get(f"/api/projects/{pid}").get_json()
    pages_doc = doc.get("pages", [])
    if not pages_doc:
        problems.append("project has no pages")
    else:
        crop_obj = {
            "type": "image",
            "src": crop_asset_url,
            "left": 120,
            "top": 140,
            "scaleX": 0.45,
            "scaleY": 0.45,
            "opacity": 1,
            "objName": "PDF Crop Leak Alarm Controller",
            "pdfSource": pdf_file,
            "pdfPage": 0,
            "pdfDpi": 600,
            "pdfCrop": "72,72,576,360",
        }
        pages_doc[0].setdefault("canvasObjects", []).append(crop_obj)
        sp = c.post(f"/api/projects/{pid}/pages", json={"pages": pages_doc})
        if sp.status_code != 200:
            problems.append(f"save pages with crop failed ({sp.status_code})")
        else:
            reloaded = c.get(f"/api/projects/{pid}").get_json()
            objs = reloaded.get("pages", [])[0].get("canvasObjects", []) if reloaded.get("pages") else []
            found = next((o for o in objs if o.get("objName") == "PDF Crop Leak Alarm Controller"), None)
            if not found:
                problems.append("inserted crop object missing after reload")
            else:
                if found.get("pdfDpi") != 600 or not found.get("pdfSource"):
                    problems.append("crop metadata not serialized on canvas object")

    # 6) Export package includes crop PNG and source PDF.
    pkg = c.post(f"/api/projects/{pid}/export/package")
    if pkg.status_code != 200:
        problems.append(f"export package failed ({pkg.status_code})")
    else:
        zf = zipfile.ZipFile(io.BytesIO(pkg.data))
        names = zf.namelist()
        if crop_asset_name and not any(crop_asset_name in n for n in names):
            problems.append("crop PNG missing from export package")
        if pdf_file and not any(n.endswith(f"/{pdf_file}") or n.endswith(pdf_file) for n in names):
            problems.append("source PDF missing from export package")
        print(f"package entries: {len(names)}")

    c.delete(f"/api/projects/{pid}")

    if problems:
        print("PDF IMPORT PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: pdf crop import smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
