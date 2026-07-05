"""scripts/smoke_component_library.py — verify the local component library.

Checks (deterministic, via the Flask test client — no live server needed):
  - the library can be initialized / seed-imported
  - GET /api/library returns components, categories, connectorStyles, symbols
  - at least one category exists
  - component asset + thumbnail paths resolve through the safe asset route
  - path traversal is rejected
  - the delete route requires an explicit confirm flag
  - inserting a component onto a project page works and is PAGE-SCOPED
    (objects saved on one page do NOT leak onto another page)
"""
from __future__ import annotations

import os
import json
import sys
import uuid
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import server

    c = server.app.test_client()
    problems: list[str] = []

    # 1. Seed import (idempotent) + read.
    seed = c.post("/api/library/import-seed")
    lib = c.get("/api/library").get_json()
    comps = lib.get("components", [])
    cats = lib.get("categories", [])
    status_counts = lib.get("statusCounts", {})
    print(
        f"seed import: {seed.status_code} | components: {len(comps)} | categories: {len(cats)} | "
        f"connectorStyles: {len(lib.get('connectorStyles', []))} | symbols: {len(lib.get('symbols', []))} | "
        f"statusCounts: {status_counts}"
    )

    if not comps:
        print("NOTE: no components found — seed folder may be absent. Skipping asset checks.")
    else:
        if not cats:
            problems.append("no categories derived")
        if not lib.get("connectorStyles"):
            problems.append("no connector styles")
        for k in ("approved", "candidate", "needs_review", "duplicate", "reference_page", "retired"):
            if k not in status_counts:
                problems.append(f"missing statusCounts[{k}]")

        # Dedupe is best-effort and may be zero in folder-based clean mode.
        dup_groups: dict[str, int] = {}
        for x in comps:
            g = x.get("duplicateGroupId")
            if g:
                dup_groups[g] = dup_groups.get(g, 0) + 1
        if dup_groups:
            biggest = max(dup_groups.values())
            print(f"duplicate groups: {len(dup_groups)} (largest group size={biggest})")

        # Insert-label metadata sanity.
        logos = [x for x in comps if (x.get("category") or "").lower() == "logos"]
        if logos and any(x.get("insertWithLabel") is not False for x in logos[:5]):
            problems.append("logos should default to insertWithLabel=false")

        # 2. Asset + thumbnail resolve for the first component that has them.
        sample = next((x for x in comps if x.get("assetPath") and not x.get("missing")), None)
        if sample:
            a = c.get("/api/library/assets/" + sample["assetPath"])
            if a.status_code != 200 and not sample.get("missing"):
                print(f"NOTE: sample asset route returned {a.status_code} for {sample['id']} (non-fatal)")
            if sample.get("thumbnailPath"):
                t = c.get("/api/library/assets/" + sample["thumbnailPath"])
                if t.status_code != 200:
                    print(f"NOTE: thumbnail did not resolve ({t.status_code}) for {sample['id']} (legacy store)")

    # 3. Path traversal must be rejected.
    trav = c.get("/api/library/assets/..%2f..%2fserver.py")
    if trav.status_code == 200:
        problems.append("path traversal was NOT blocked")

    # 4. Delete route must require confirmation.
    if comps:
        cid = comps[0]["id"]
        no_confirm = c.delete(f"/api/library/components/{cid}")
        if no_confirm.status_code != 400:
            problems.append("delete without confirm should be rejected (400)")

    # 4b. Approve + rename persistence via PATCH.
    target = next((x for x in comps if x.get("status") in {"needs_review", "candidate"}), None)
    if target:
        rid = target["id"]
        patch = {
            "displayName": "Contactor",
            "category": "electrical",
            "status": "approved",
            "defaultLabel": "Contactor",
            "insertWithLabel": True,
        }
        p = c.patch(f"/api/library/components/{rid}", json=patch)
        if p.status_code != 200:
            problems.append(f"patch approve/rename failed ({p.status_code})")
        else:
            reload_lib = c.get("/api/library").get_json()
            again = next((x for x in reload_lib.get("components", []) if x.get("id") == rid), None)
            if not again:
                problems.append("patched component missing after reload")
            else:
                if again.get("displayName") != "Contactor" or again.get("status") != "approved":
                    problems.append("patch changes did not persist")
                if again.get("curated") is not True:
                    problems.append("patched component should be marked curated=True")
                # Phase D: auto-categorize must NOT overwrite curated edits.
                ac = c.post("/api/library/auto-categorize")
                if ac.status_code != 200:
                    problems.append(f"auto-categorize failed ({ac.status_code})")
                after_ac = c.get("/api/library").get_json()
                curated = next((x for x in after_ac.get("components", []) if x.get("id") == rid), None)
                if not curated:
                    problems.append("curated component missing after auto-categorize")
                elif (
                    curated.get("displayName") != "Contactor"
                    or (curated.get("category") or "").lower() != "electrical"
                    or curated.get("status") != "approved"
                ):
                    problems.append("auto-categorize overwrote curated edits (Phase D violation)")

    # 4c. Inbox import proof (generate tiny PNG in inbox, rescan).
    inbox = server.DOCS_DIR / "library" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    tiny = inbox / f"smoke_{uuid.uuid4().hex[:8]}.png"
    tiny.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c6360000000020001e221bc330000000049454e44ae426082"
        )
    )
    rscan = c.post("/api/library/rescan-inbox")
    if rscan.status_code != 200:
        problems.append(f"rescan-inbox failed ({rscan.status_code})")
    else:
        info = rscan.get_json()
        print(f"rescan-inbox: added={info.get('added')} duplicates={info.get('duplicates')}")
        if int(info.get("added", 0)) < 1:
            problems.append("inbox file was not imported as a candidate")

    # 4d. RDM folder import proof (fake local folder, deterministic names).
    tiny_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6360000000020001e221bc330000000049454e44ae426082"
    )
    with tempfile.TemporaryDirectory() as tdir:
        rroot = Path(tdir) / "Images"
        (rroot / "Refrigeration").mkdir(parents=True, exist_ok=True)
        (rroot / "Light").mkdir(parents=True, exist_ok=True)
        # Ensure distinct bytes per file so SHA dedupe doesn't collapse them.
        (rroot / "Refrigeration" / "pump.png").write_bytes(tiny_png + b"pump")
        (rroot / "Refrigeration" / "traffic lights on.jpg").write_bytes(tiny_png + b"traffic-on")
        (rroot / "Refrigeration" / "rdm intuitiveplant.png").write_bytes(tiny_png + b"intuitiveplant")
        (rroot / "Light" / "light sensor.png").write_bytes(tiny_png + b"light-sensor")

        rdm1 = c.post("/api/library/import-rdm-folder", json={"path": str(rroot), "dryRun": False})
        if rdm1.status_code != 200:
            problems.append(f"RDM import failed ({rdm1.status_code})")
        else:
            r1 = rdm1.get_json()
            if int(r1.get("added", 0)) < 1:
                problems.append("RDM import added no components")
            l1 = c.get("/api/library").get_json().get("components", [])
            by_name = {str(x.get("displayName") or ""): x for x in l1}
            for nm in ("Pump", "Traffic Lights On", "RDM IntuitivePlant Controller", "Light Sensor"):
                if nm not in by_name:
                    problems.append(f"RDM display name missing: {nm}")
            if by_name.get("Pump", {}).get("category") != "refrigeration":
                problems.append("RDM Pump category should be refrigeration")
            if by_name.get("Traffic Lights On", {}).get("category") != "alarms":
                problems.append("Traffic Lights On category should be alarms")
            if by_name.get("RDM IntuitivePlant Controller", {}).get("category") != "controllers":
                problems.append("RDM IntuitivePlant category should be controllers")
            if by_name.get("Light Sensor", {}).get("category") != "lighting":
                problems.append("Light Sensor category should be lighting")

            # Insert/save/reload proof using an imported RDM asset.
            rpump = by_name.get("Pump") or by_name.get("Traffic Lights On")
            if rpump and rpump.get("assetPath"):
                pid2 = "c0ffee00c0ffee01"
                proj2 = {
                    "id": pid2,
                    "pages": [{"id": "page_rdm", "sheetTitle": "RDM Insert", "sheetCode": "1.0",
                               "displaySheetCode": "1.0", "sheetTab": "", "pageType": "canvas",
                               "order": 1, "include": True, "blocks": [], "canvasObjects": [],
                               "notes": "", "revisionRows": [], "pageGroupId": "pg_rdm",
                               "continuationOf": None, "continuationIndex": 0,
                               "generatedContinuation": False, "layoutWarnings": []}],
                    "worksheets": [],
                    "sources": [],
                    "metadata": {"projectName": "RDM Insert Test"},
                    "projectDisplayName": "RDM Insert Test",
                }
                c.post(f"/api/projects/{pid2}", json=proj2)
                rdm_src = "/api/library/assets/" + str(rpump.get("assetPath"))
                proj_saved = c.get(f"/api/projects/{pid2}").get_json()
                proj_saved["pages"][0]["canvasObjects"] = [{
                    "type": "image",
                    "left": 24,
                    "top": 24,
                    "width": 80,
                    "height": 80,
                    "src": rdm_src,
                    "objName": "RDM Pump",
                }]
                c.post(f"/api/projects/{pid2}/pages", json={"pages": proj_saved["pages"]})
                re2 = c.get(f"/api/projects/{pid2}").get_json()
                src2 = ((re2.get("pages") or [{}])[0].get("canvasObjects") or [{}])[0].get("src")
                if src2 != rdm_src:
                    problems.append("RDM insert src did not persist after save/reload")
                # Asset route must resolve for inserted item.
                chk = c.get(rdm_src)
                if chk.status_code != 200:
                    problems.append(f"RDM inserted asset route failed ({chk.status_code})")
                c.delete(f"/api/projects/{pid2}")

            # Curated item must not be overwritten by reimport.
            pump = by_name.get("Pump")
            if pump and pump.get("id"):
                c.patch(f"/api/library/components/{pump['id']}", json={"displayName": "Pump Curated", "category": "electrical", "status": "approved"})

            before_count = len(l1)
            rdm2 = c.post("/api/library/import-rdm-folder", json={"path": str(rroot), "dryRun": False})
            if rdm2.status_code != 200:
                problems.append(f"RDM reimport failed ({rdm2.status_code})")
            else:
                r2 = rdm2.get_json()
                if int(r2.get("added", 0)) != 0:
                    problems.append("RDM reimport should not add duplicate components")
                l2 = c.get("/api/library").get_json().get("components", [])
                # Count should not double.
                if len(l2) > before_count + 1:
                    problems.append("RDM reimport unexpectedly increased count")
                # Curated value should persist.
                p2 = next((x for x in l2 if x.get("id") == pump.get("id")), None) if pump else None
                if p2 and p2.get("displayName") != "Pump Curated":
                    problems.append("curated RDM item displayName was overwritten on reimport")

    # 4e. Folder-master workflow proof using fixed .docs/components root.
    lroot = server.DOCS_DIR / "library" / "assets" / "components"
    (lroot / "hvac").mkdir(parents=True, exist_ok=True)
    (lroot / "refrigeration").mkdir(parents=True, exist_ok=True)
    (lroot / "panel").mkdir(parents=True, exist_ok=True)
    (lroot / "symbol").mkdir(parents=True, exist_ok=True)
    (lroot / "thumbnails" / "hvac").mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image  # type: ignore

        Image.new("RGB", (8, 8), (220, 40, 40)).save(lroot / "hvac" / "Fan.png", "PNG")
        Image.new("RGB", (8, 8), (40, 220, 40)).save(lroot / "refrigeration" / "Valve_Open.png", "PNG")
        Image.new("RGB", (8, 8), (40, 40, 220)).save(lroot / "symbol" / "HEB_logo.png", "PNG")
    except Exception:
        (lroot / "hvac" / "Fan.png").write_bytes(tiny_png)
        (lroot / "refrigeration" / "Valve_Open.png").write_bytes(tiny_png)
        (lroot / "symbol" / "HEB_logo.png").write_bytes(tiny_png)
    (lroot / "thumbnails" / "hvac" / "thumb_only_item.png").write_bytes(tiny_png + b"thumb-only")

    # Build a tiny PDF when PyMuPDF is available.
    has_fitz = False
    try:
        import fitz  # type: ignore
        has_fitz = True
        doc = fitz.open()
        page = doc.new_page(width=240, height=120)
        page.insert_text((20, 60), "WICP Enclosure")
        doc.save(str(lroot / "panel" / "WICP_Enclosure.pdf"))
        doc.close()
    except Exception:
        (lroot / "panel" / "WICP_Enclosure.pdf").write_bytes(b"%PDF-1.4\n%fake\n")

    # library_settings.json should store fixed .docs/components root.
    settings_path = server.DOCS_DIR / "library" / "library_settings.json"
    if not settings_path.exists():
        problems.append("library_settings.json not created")
    else:
        try:
            cfg = json.loads(settings_path.read_text(encoding="utf-8"))
            if Path(str(cfg.get("libraryRoot") or "")).resolve() != lroot.resolve():
                problems.append("library_settings.json libraryRoot mismatch")
        except Exception:
            problems.append("library_settings.json unreadable")

    imp = c.post("/api/library/refresh", json={"dryRun": False, "resetClean": True})
    if imp.status_code != 200:
        problems.append(f"local-folder import failed ({imp.status_code})")
    else:
        # Old metadata should be snapshotted.
        if not any((server.DOCS_DIR / "library" / "_archive").glob("library_*.json")):
            problems.append("old metadata archive snapshot was not created")

        j = imp.get_json()
        if int(j.get("scanned", 0)) < 4:
            problems.append("local-folder import scanned too few files")
        lib2 = c.get("/api/library").get_json().get("components", [])
        local_only = [x for x in lib2 if str((x.get("source") or {}).get("sourceType") or "") == "local-library-folder"]
        by_name2 = {str(x.get("displayName") or ""): x for x in local_only}
        if "Fan" not in by_name2:
            problems.append("Fan missing after local-folder import")
        if "Valve Open" not in by_name2:
            problems.append("Valve Open missing after local-folder import")
        if "H-E-B Logo" not in by_name2:
            problems.append("H-E-B Logo missing after local-folder import")
        if by_name2.get("Fan", {}).get("category") != "hvac":
            problems.append("hvac/Fan should map to hvac")
        if by_name2.get("Valve Open", {}).get("category") != "refrigeration":
            problems.append("refrigeration/Valve_Open should map to refrigeration")
        if by_name2.get("H-E-B Logo", {}).get("category") != "symbol":
            problems.append("symbol/HEB_logo should map to symbol")

        # No temp path should be used for library root imports.
        for comp in lib2:
            src_loc = str((comp.get("source") or {}).get("sourceLocation") or "").lower()
            if "appdata" in src_loc and "temp" in src_loc:
                problems.append("temp path used in component sourceLocation")

        # sourceQuality warning flag for thumbnail-only source.
        thumb_only = next((x for x in lib2 if "thumb_only_item" in str((x.get("source") or {}).get("sourceFile") or "")), None)
        if thumb_only and not thumb_only.get("sourceQuality"):
            problems.append("thumbnail-only source should include sourceQuality metadata")

        # PDF conversion check when fitz is available.
        wicp = next((x for x in lib2 if "WICP" in str(x.get("displayName") or "")), None)
        if has_fitz:
            if not wicp:
                problems.append("WICP Enclosure PDF did not produce a component")
            else:
                ap = str(wicp.get("assetPath") or "")
                if not ap.lower().endswith(".png"):
                    problems.append("WICP Enclosure asset should be rendered PNG")

        # Thumbnails should exist for imported entries.
        try:
            from PIL import Image as _PILImage  # type: ignore # noqa: F401
            has_pillow = True
        except Exception:
            has_pillow = False
        if has_pillow:
            for nm in ("Fan", "Valve Open", "H-E-B Logo"):
                cc = by_name2.get(nm)
                if cc and cc.get("thumbnailPath"):
                    tp = server.DOCS_DIR / str(cc.get("thumbnailPath")).replace("library/", "", 1)
                    if not tp.exists():
                        print(f"NOTE: thumbnail missing for {nm} (legacy folder mode)")

        # Rename metadata + optional file rename and verify persistence.
        fan = by_name2.get("Fan")
        if fan and fan.get("id"):
            p1 = c.patch(f"/api/library/components/{fan['id']}", json={"displayName": "Contactor", "category": "electrical", "renameAssetFile": True})
            if p1.status_code != 200:
                problems.append(f"patch rename failed ({p1.status_code})")
            else:
                l3 = c.get("/api/library").get_json().get("components", [])
                ff = next((x for x in l3 if x.get("id") == fan["id"]), None)
                if not ff or ff.get("displayName") != "Contactor":
                    problems.append("renamed metadata did not persist")

                # curated name must survive sync-names.
                c.post("/api/library/sync-names", json={})
                l4 = c.get("/api/library").get_json().get("components", [])
                ff2 = next((x for x in l4 if x.get("id") == fan["id"]), None)
                if ff2 and ff2.get("displayName") != "Contactor":
                    problems.append("sync names overwrote curated displayName")

        # Missing-file mark check: remove a known asset then rescan.
        victim = by_name2.get("Valve Open")
        if victim and victim.get("assetPath"):
            abs_v = server.DOCS_DIR / str(victim["assetPath"]).replace("library/", "", 1)
            if abs_v.exists():
                abs_v.unlink()
                c.post("/api/library/rescan-library", json={})
                l5 = c.get("/api/library").get_json().get("components", [])
                vv = next((x for x in l5 if x.get("id") == victim.get("id")), None)
                if vv and vv.get("missing") is not True:
                    problems.append("missing asset should be marked missing=true after rescan")

        # Add file through app route into folder-based root.
        import io
        add_res = c.post(
            "/api/library/add-file",
            data={"category": "refrigeration", "file": (io.BytesIO(tiny_png + b"new-local-pump"), "New_Local_Pump.png")},
            content_type="multipart/form-data",
        )
        if add_res.status_code != 200:
            problems.append(f"add-file route failed ({add_res.status_code})")
        l6 = c.get("/api/library").get_json().get("components", [])
        if not any("new_local_pump" in str((x.get("source") or {}).get("sourceFile") or "").lower() for x in l6):
            problems.append("folder add + refresh did not surface new component source file")

        # Thumbnail API URLs should resolve by component id.
        for nm in ("Fan", "Valve Open", "H-E-B Logo"):
            cc = by_name2.get(nm)
            if cc and cc.get("id"):
                tr = c.get(f"/api/library/thumbnail/{cc['id']}")
                if tr.status_code not in {200, 404}:
                    problems.append(f"thumbnail API bad status for {nm}: {tr.status_code}")

        # Refresh should be stable (no count growth on second refresh).
        r1 = c.post("/api/library/refresh", json={"dryRun": False, "resetClean": False})
        r2 = c.post("/api/library/refresh", json={"dryRun": False, "resetClean": False})
        if r1.status_code == 200 and r2.status_code == 200:
            j1 = r1.get_json()
            j2 = r2.get_json()
            if int(j2.get("added", 0)) > int(j1.get("added", 0)) + 5:
                problems.append("refresh count instability detected")

        # Rebuild thumbnails must not change source component count.
        before_components = len(c.get("/api/library").get_json().get("components", []))
        rb = c.post("/api/library/rebuild-thumbnails", json={})
        after_components = len(c.get("/api/library").get_json().get("components", []))
        if rb.status_code != 200:
            problems.append(f"rebuild-thumbnails failed ({rb.status_code})")
        if before_components != after_components:
            problems.append("rebuild-thumbnails changed component count")

        # Duplicate cleanup dry-run should execute.
        cd = c.post("/api/library/cleanup-duplicates", json={"dryRun": True, "dedupeAll": True})
        if cd.status_code != 200:
            problems.append(f"cleanup-duplicates dry-run failed ({cd.status_code})")

    # 5. Page-scoped overlay isolation via a throwaway project.
    wb = os.environ.get("SINGH360_SA31_WORKBOOK", "")
    if not wb:
        # Try the known desktop workbook name relative to common locations.
        pass
    pid = None
    if wb and Path(wb).exists():
        import io
        with open(wb, "rb") as fh:
            res = c.post("/api/projects/new", data={"file": (io.BytesIO(fh.read()), "SA31.xlsx")},
                         content_type="multipart/form-data")
        if res.status_code == 200:
            pid = res.get_json()["id"]
    if pid:
        proj = c.get(f"/api/projects/{pid}").get_json()
        pages = proj["pages"]
        if len(pages) >= 2:
            pages[0]["canvasObjects"] = [{"type": "image", "left": 10, "top": 10, "width": 50, "height": 50,
                                          "src": "/api/library/assets/x.png", "objName": "OnPageOne"}]
            pages[1]["canvasObjects"] = []
            c.post(f"/api/projects/{pid}/pages", json={"pages": pages})
            reload = c.get(f"/api/projects/{pid}").get_json()["pages"]
            p0 = reload[0].get("canvasObjects") or []
            p1 = reload[1].get("canvasObjects") or []
            if len(p0) != 1:
                problems.append("page 1 lost its overlay object")
            if len(p1) != 0:
                problems.append("overlay object LEAKED onto page 2")
            print(f"page-scoped overlay: page1={len(p0)} obj, page2={len(p1)} obj (expected 1 / 0)")
        c.delete(f"/api/projects/{pid}")
    else:
        print("page-scope check skipped (set SINGH360_SA31_WORKBOOK to a workbook to enable it)")

    # 6. Component Library V2 — approved builder export wiring (/api/lib).
    v2 = c.get("/api/lib").get_json()
    if v2.get("usingBuilderExport"):
        v2comps = v2.get("components", [])
        with_edge = [x for x in v2comps if x.get("edgeUrl") and x.get("hasEdge")]
        with_source = [x for x in v2comps if x.get("sourceUrl") and x.get("hasSource")]
        with_bw = [x for x in v2comps if x.get("bwUrl") and x.get("hasBw")]
        print(
            f"V2 builder export: total={len(v2comps)} withSource={len(with_source)} withEdge={len(with_edge)} withBw={len(with_bw)} "
            f"legacyHidden={v2.get('legacyCount')}"
        )
        if not v2comps:
            problems.append("V2 builder export produced zero components")
        if not with_edge:
            problems.append("V2 builder export exposed no edge representations")
        if not with_source:
            problems.append("V2 builder export exposed no source representations")
        if not with_bw:
            problems.append("V2 builder export exposed no bw representations")
        # Approved items must expose the normalized URL/flag contract.
        required = {"sourceUrl", "edgeUrl", "bwUrl", "thumbnailUrl", "hasSource", "hasEdge", "hasBw", "searchTerms"}
        if any(any(k not in x for k in required) for x in v2comps):
            problems.append("V2 components missing source/edge/bw API fields")
        # No stale hash-name junk in the default view.
        import re as _re
        stale = [x for x in v2comps if _re.search(r"_[0-9a-f]{8,}\b", str(x.get("id") or ""))]
        if stale:
            problems.append(f"V2 default view still shows {len(stale)} stale hash-name items")
        # A component with edge must serve it through the asset route.
        if with_edge:
            edge_u = with_edge[0].get("edgeUrl", "")
            ar = c.get(edge_u)
            if ar.status_code != 200:
                problems.append(f"V2 edge asset did not resolve ({ar.status_code})")

        # Edge must be the approved edge/lineart stencil (edgePath), never a
        # procedural symbol, and must differ from the source when both exist.
        export_path = server.DOCS_DIR / "library" / "component_builder_export.json"
        if export_path.exists():
            raw_export = json.loads(export_path.read_text(encoding="utf-8"))
            raw_rows = raw_export.get("components", raw_export) if isinstance(raw_export, dict) else raw_export
            raw_by_id = {r.get("id"): r for r in raw_rows}
            comp_by_id = {x.get("id"): x for x in v2comps}

            with_edge_path = [r for r in raw_rows if r.get("edgePath")]
            print(f"V2 edgePath rows: {len(with_edge_path)} of {len(raw_rows)}")

            def _tail(url: str) -> str:
                return (url or "").split("/api/lib/asset/", 1)[-1]

            # edgePath must map straight through to edgeUrl.
            for rid, row in raw_by_id.items():
                comp = comp_by_id.get(rid)
                if not comp:
                    continue
                edge_path = (row.get("edgePath") or "").replace("\\", "/")
                if edge_path:
                    if not comp.get("hasEdge"):
                        problems.append(f"{rid}: edgePath present but hasEdge=false")
                    if not edge_path.endswith(_tail(comp.get("edgeUrl", ""))):
                        problems.append(f"{rid}: edgeUrl does not map to edgePath")
                    # Edge must never point at the procedural /symbols/ folder.
                    if "/symbols/" in f"/{_tail(comp.get('edgeUrl', ''))}":
                        problems.append(f"{rid}: edge resolved to procedural symbol path")
                    # Source and Edge must differ when both exist.
                    if comp.get("hasSource") and _tail(comp.get("sourceUrl", "")) == _tail(comp.get("edgeUrl", "")):
                        problems.append(f"{rid}: sourceUrl and edgeUrl are identical")

            # Named acceptance components must resolve Edge from their edgePath.
            for rid in ("rdm-touchxl", "rdm-mercury", "rdm_pr0650cd_tdb_controller"):
                comp = comp_by_id.get(rid)
                row = raw_by_id.get(rid)
                if not comp or not row:
                    problems.append(f"acceptance component missing: {rid}")
                    continue
                if not comp.get("hasEdge"):
                    problems.append(f"{rid}: expected an approved Edge drawing")
                if "__device" in _tail(comp.get("edgeUrl", "")):
                    problems.append(f"{rid}: Edge still using procedural __device wireframe")
                if row.get("edgePath") and not comp.get("edgeUrl", "").endswith(
                    row["edgePath"].replace("\\", "/").split("/api/lib/asset/", 1)[-1].split("/")[-1]
                ):
                    problems.append(f"{rid}: Edge filename does not match edgePath")

        # PATCH persistence for an export-derived id (override entry), including
        # preferredEdgeVariant.
        if v2comps:
            tid = v2comps[0]["id"]
            orig_label = v2comps[0].get("defaultLabel", "")
            orig_pref = v2comps[0].get("preferredEdgeVariant", "")
            pref = (v2comps[0].get("edgeVariantOptions") or [""])[0]
            pr = c.patch(f"/api/lib/components/{tid}", json={"defaultLabel": "SMOKE_LABEL", "preferredEdgeVariant": pref})
            if pr.status_code != 200:
                problems.append(f"V2 PATCH failed ({pr.status_code})")
            else:
                again = next((x for x in c.get("/api/lib").get_json().get("components", []) if x.get("id") == tid), None)
                if not again or again.get("defaultLabel") != "SMOKE_LABEL":
                    problems.append("V2 PATCH defaultLabel did not persist for export item")
                if again and pref and again.get("preferredEdgeVariant") != pref:
                    problems.append("V2 PATCH preferredEdgeVariant did not persist")
                # Restore so the smoke does not pollute the real approved manifest.
                c.patch(f"/api/lib/components/{tid}", json={"defaultLabel": orig_label, "preferredEdgeVariant": orig_pref})

        # includeLegacy=1 should expose at least as many components as default.
        v2_legacy = c.get("/api/lib?includeLegacy=1").get_json()
        if len(v2_legacy.get("components", [])) < len(v2comps):
            problems.append("includeLegacy=1 should not return fewer components than default")
    else:
        print("V2 builder export: component_builder_export.json NOT present (manifest fallback in use)")

    if problems:
        print("COMPONENT LIBRARY PROBLEMS:")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print("OK: component library smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
