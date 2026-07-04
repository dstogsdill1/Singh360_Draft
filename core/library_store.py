"""core/library_store.py — local component-library storage.

The component library is a LOCAL/private store under .docs/library (gitignored).
It is seeded (imported) from the unzipped Singh360_Component_Library_Seed folder
and read by the editor's Component Library panel. Extracted/reference-derived
images stay local and are never committed.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None

try:
    import fitz  # PyMuPDF
except Exception:  # noqa: BLE001
    fitz = None


STATUSES = {
    "approved",
    "candidate",
    "needs_review",
    "duplicate",
    "reference_page",
    "retired",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}

RDM_TAGS = ["rdm", "rdm-layout-editor", "official-rdm-library"]


class LibraryStore:
    def __init__(self, docs_dir: Path, repo_root: Path) -> None:
        self.dir = docs_dir / "library"
        self.assets = self.dir / "assets"
        self.seed = repo_root / "Singh360_Component_Library_Seed" / "library"
        self.index_path = self.dir / "library.json"
        self.config_path = self.dir / "config.json"
        self.default_master_root = repo_root / "Singh360_Component_Library_Seed" / "library" / "assets"

    # ---- filesystem helpers -------------------------------------------------
    def ensure(self) -> None:
        for sub in (
            "assets/components",
            "assets/components/controllers",
            "assets/components/expansion_modules",
            "assets/components/electrical_power",
            "assets/components/network_data",
            "assets/components/panels_enclosures",
            "assets/components/refrigeration",
            "assets/components/hvac",
            "assets/components/lighting",
            "assets/components/alarms_safety",
            "assets/components/sensors_transducers",
            "assets/components/symbols_markers",
            "assets/components/logos",
            "assets/components/legends",
            "assets/components/custom",
            "assets/thumbnails",
            "assets/thumbnails/controllers",
            "assets/thumbnails/expansion_modules",
            "assets/thumbnails/electrical_power",
            "assets/thumbnails/network_data",
            "assets/thumbnails/panels_enclosures",
            "assets/thumbnails/refrigeration",
            "assets/thumbnails/hvac",
            "assets/thumbnails/lighting",
            "assets/thumbnails/alarms_safety",
            "assets/thumbnails/sensors_transducers",
            "assets/thumbnails/symbols_markers",
            "assets/thumbnails/logos",
            "assets/thumbnails/legends",
            "assets/thumbnails/custom",
            "assets/workbook_images",
            "assets/reference_pages",
            "assets/reference_pages/custom",
            "assets/originals",
            "assets/originals/pdf",
            "assets/originals/svg",
            "assets/originals/source",
            "staging",
            "inbox",
            "processed",
            "retired",
            "_archive",
            "inbox/processed",
        ):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index(self._empty_index())

    def _empty_index(self) -> dict:
        return {
            "schemaVersion": "0.2",
            "connectorStyles": [],
            "symbols": [],
            "components": [],
            "referencePages": [],
            "stats": {},
        }

    def _write_index(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_config(self) -> dict:
        self.ensure()
        try:
            cfg = json.loads(self.config_path.read_text(encoding="utf-8")) if self.config_path.exists() else {}
        except Exception:  # noqa: BLE001
            cfg = {}
        if "masterLibraryRoot" not in cfg:
            cfg["masterLibraryRoot"] = str(self.default_master_root)
        return cfg

    def _write_config(self, cfg: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_master_root(self) -> str:
        return str(self._read_config().get("masterLibraryRoot") or self.default_master_root)

    def set_master_root(self, root_path: str | Path) -> dict:
        p = Path(root_path).expanduser().resolve()
        if not p.exists() or not p.is_dir():
            return {"ok": False, "error": f"Invalid library root: {p}"}
        cfg = self._read_config()
        cfg["masterLibraryRoot"] = str(p)
        self._write_config(cfg)
        return {"ok": True, "masterLibraryRoot": str(p)}

    # ---- seed import --------------------------------------------------------
    def import_seed(self) -> dict:
        """Copy the seed library into .docs/library (merge). Never deletes the seed."""
        if not self.seed.is_dir():
            return {"ok": False, "error": f"Seed folder not found: {self.seed}"}
        self.dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for src in self.seed.rglob("*"):
            rel = src.relative_to(self.seed)
            dest = self.dir / rel
            if src.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied += 1
        data = self._raw_load()
        self._curate_components(data)
        self._dedupe_components(data)
        self.save(data)
        data = self.load()
        return {"ok": True, "filesCopied": copied, "componentCount": len(data.get("components", []))}

    # ---- read/write ---------------------------------------------------------
    def _raw_load(self) -> dict:
        self.ensure()
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = self._empty_index()
        return data

    def _normalize_status(self, c: dict) -> None:
        status = str(c.get("status") or "").lower().strip()
        if status.startswith("retired"):
            c["status"] = "retired"
            return
        # Legacy/default mappings.
        if status in ("", "candidate_private_review", "review", "needs-review"):
            c["status"] = "needs_review"
            return
        if status == "reference-page":
            c["status"] = "reference_page"
            return
        if status not in STATUSES:
            c["status"] = "needs_review"

    def _component_haystack(self, c: dict) -> str:
        return " ".join(
            [
                str(c.get("displayName", "")),
                str(c.get("shortName", "")),
                str(c.get("partNumber", "")),
                " ".join(c.get("aliases", []) or []),
                " ".join(c.get("tags", []) or []),
                str((c.get("source") or {}).get("sourceFile", "")),
                str((c.get("source") or {}).get("sourceLocation", "")),
                str(c.get("nearbyText", "")),
            ]
        ).lower()

    def _asset_abs(self, c: dict) -> Path | None:
        ap = str(c.get("assetPath") or "")
        if not ap:
            return None
        return self.asset_path(ap)

    def _image_meta(self, p: Path) -> tuple[int, int, int, str | None]:
        size = p.stat().st_size if p.exists() else 0
        w = h = 0
        ph = None
        if Image is not None and p.suffix.lower() != ".svg":
            try:
                with Image.open(p) as im:
                    w, h = im.size
                    ph = self._average_hash(im)
            except Exception:  # noqa: BLE001
                pass
        return w, h, size, ph

    def _average_hash(self, im) -> str:
        g = im.convert("L").resize((8, 8))
        px = list(g.getdata())
        avg = sum(px) / len(px)
        bits = "".join("1" if v >= avg else "0" for v in px)
        return f"{int(bits, 2):016x}"

    def _hamming(self, a: str, b: str) -> int:
        try:
            return (int(a, 16) ^ int(b, 16)).bit_count()
        except Exception:  # noqa: BLE001
            return 999

    def _compute_hashes(self, c: dict) -> None:
        p = self._asset_abs(c)
        if not p or not p.exists():
            return
        if not c.get("sha256"):
            c["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        w, h, size, ph = self._image_meta(p)
        if w and h:
            c["width"] = c.get("width") or w
            c["height"] = c.get("height") or h
            c["aspectRatio"] = round(w / h, 4) if h else None
        c["fileSize"] = size
        if ph:
            c["perceptualHash"] = ph

    def _is_reference_page(self, c: dict) -> bool:
        hay = self._component_haystack(c)
        asset_path = str(c.get("assetPath") or "").lower()
        if "/reference_pages/" in asset_path:
            return True
        if any(k in hay for k in ("blueprint", "floor plan", "floorplan", "reference page", "workflow diagram")):
            return True
        w = int(c.get("width") or c.get("defaultWidth") or 0)
        h = int(c.get("height") or c.get("defaultHeight") or 0)
        if w and h:
            # Keep this strict to avoid reclassifying ordinary device cards.
            if w >= 2200 or h >= 2200:
                return True
            ratio = max(w / max(h, 1), h / max(w, 1))
            if ratio >= 3.6:
                return True
        return False

    def _squash_duplicates_in_index(self, data: dict) -> None:
        comps = data.get("components", [])
        out: list[dict] = []
        seen_ids: set[str] = set()
        seen_asset: set[str] = set()
        for c in comps:
            cid = str(c.get("id") or "")
            ap = str(c.get("assetPath") or "")
            if cid and cid in seen_ids:
                continue
            if ap and ap in seen_asset:
                continue
            if cid:
                seen_ids.add(cid)
            if ap:
                seen_asset.add(ap)
            out.append(c)
        if len(out) != len(comps):
            data["components"] = out

    def _is_confident_approved(self, c: dict) -> bool:
        # Conservative approval gate: only obviously well-labeled items are approved.
        cat = str(c.get("category") or "").lower()
        if cat in {"review", "reference-page"}:
            return False
        hay = self._component_haystack(c)
        display = str(c.get("displayName") or "").lower()
        short = str(c.get("shortName") or "").lower()
        part = str(c.get("partNumber") or "").lower()
        strict = f" {display} {short} {part} "
        if cat == "logos":
            return "h-e-b" in strict or "heb" in strict or "singh360" in strict
        if cat == "controllers":
            return bool(re.search(r"\bpr0650\b|\bpr0680\b|\bpr0751\b|\bpr0652\b", strict))
        if cat == "expansion":
            return bool(re.search(r"\bpr066[0-3]\b", strict))
        if cat == "electrical":
            return any(k in strict for k in ("contactor", "relay", "power supply", "breaker", "disconnect"))
        if cat == "alarms":
            return any(k in strict for k in ("strobe", "entrapment", "leak indicator", "door alarm"))
        if cat == "network":
            return any(k in strict for k in ("data manager", "orbit", "idf", "mdf", "bacnet", "switch"))
        if cat == "panels":
            return any(k in strict for k in ("lcp", "wicp", "ccg", "panel"))
        if cat == "sensors":
            return any(k in strict for k in ("sensor", "transducer", "temperature", "humidity", "door switch"))
        if cat in {"refrigeration", "lighting", "symbols", "legends"}:
            return any(k in strict for k in ("rack", "evaporator", "condenser", "dimming", "marker", "legend"))
        return any(w in hay for w in ("pr0650", "pr0660", "contactor", "data manager", "logo"))

    def _curate_components(self, data: dict) -> None:
        from core.library_taxonomy import classify

        self._squash_duplicates_in_index(data)
        for c in data.get("components", []):
            self._normalize_status(c)
            self._compute_hashes(c)
            if c.get("curated") is True:
                continue
            source_type = str((c.get("source") or {}).get("sourceType") or "").lower()
            # Keep explicit import mappings stable unless user curates later.
            if source_type in {"rdm-layout-editor", "local-library-folder"}:
                if not c.get("defaultLabel"):
                    c["defaultLabel"] = c.get("partNumber") or c.get("shortName") or c.get("displayName")
                c["insertWithLabel"] = c.get("insertWithLabel", True)
                if str(c.get("status") or "") not in STATUSES:
                    c["status"] = "needs_review"
                continue
            full_hay = self._component_haystack(c)
            aspect = c.get("aspectRatio")
            cat, canon = classify(
                str(c.get("displayName", "")),
                str(c.get("shortName", "")),
                str(c.get("partNumber", "")),
                float(aspect) if isinstance(aspect, (int, float)) else None,
            )
            # Context-aware overrides from extracted text/source metadata.
            if any(k in full_hay for k in ("h-e-b", "heb logo", "singh360 logo", "client logo")):
                cat, canon = ("logos", "H-E-B Logo" if "h-e-b" in full_hay or "heb" in full_hay else None)
            elif "contactor" in full_hay:
                cat, canon = ("electrical", "Contactor")
            elif "amber" in full_hay and "strobe" in full_hay:
                cat, canon = ("alarms", "Amber Strobe")
            elif "red" in full_hay and "strobe" in full_hay:
                cat, canon = ("alarms", "Red Strobe")
            if self._is_reference_page(c):
                cat = "reference-page"
            c["category"] = cat
            if canon:
                c["displayName"] = canon
            # Status assignment by confidence/safety.
            source_type = str((c.get("source") or {}).get("sourceType") or "").lower()
            if source_type == "inbox" and str(c.get("status") or "") in {"needs_review", "candidate"}:
                c["status"] = "needs_review"
            elif cat == "review":
                c["status"] = "needs_review"
            elif cat == "reference-page":
                c["status"] = "reference_page"
            elif self._is_confident_approved(c):
                c["status"] = "approved"
            else:
                c["status"] = "needs_review"
            # Default label policy.
            if cat in {"logos", "symbols", "legends", "reference-page"}:
                c["insertWithLabel"] = False
            else:
                c["insertWithLabel"] = True
            if not c.get("defaultLabel"):
                c["defaultLabel"] = c.get("partNumber") or c.get("shortName") or c.get("displayName")

    def _dedupe_components(self, data: dict) -> None:
        comps = data.get("components", [])
        # Exact duplicates by sha256.
        by_sha: dict[str, list[dict]] = {}
        for c in comps:
            sha = str(c.get("sha256") or "")
            if sha:
                by_sha.setdefault(sha, []).append(c)
        for sha, grp in by_sha.items():
            if len(grp) <= 1:
                continue
            gid = f"dup-{sha[:10]}"
            # Keep first as canonical; others duplicate unless curated/retired.
            grp_sorted = sorted(grp, key=lambda x: str(x.get("id") or ""))
            for i, c in enumerate(grp_sorted):
                c["duplicateGroupId"] = gid
                if i == 0:
                    c["isDuplicateCanonical"] = True
                elif c.get("status") not in {"retired", "approved"}:
                    c["status"] = "duplicate"
                    c["isDuplicateCanonical"] = False

        # Near duplicates via perceptual hash.
        with_ph = [c for c in comps if c.get("perceptualHash")]
        seen_pairs: set[tuple[str, str]] = set()
        for i in range(len(with_ph)):
            a = with_ph[i]
            for j in range(i + 1, len(with_ph)):
                b = with_ph[j]
                key = tuple(sorted((str(a.get("id")), str(b.get("id")))))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                if self._hamming(str(a.get("perceptualHash")), str(b.get("perceptualHash"))) <= 4:
                    gid = a.get("duplicateGroupId") or b.get("duplicateGroupId") or f"dup-near-{uuid.uuid4().hex[:8]}"
                    a["duplicateGroupId"] = gid
                    b["duplicateGroupId"] = gid
                    if not a.get("isDuplicateCanonical"):
                        a["isDuplicateCanonical"] = True
                    if b.get("status") not in {"approved", "retired"}:
                        b["status"] = "duplicate"
                        b["isDuplicateCanonical"] = False

    def _derive_categories(self, comps: list[dict], *, include_statuses: set[str]) -> list[dict]:
        cats: dict[str, int] = {}
        for c in comps:
            st = str(c.get("status") or "needs_review")
            if st not in include_statuses:
                continue
            cat = (c.get("category") or "uncategorized").lower()
            cats[cat] = cats.get(cat, 0) + 1
        return [{"id": k, "count": v} for k, v in sorted(cats.items())]

    def load(self) -> dict:
        data = self._raw_load()
        self._curate_components(data)
        self._dedupe_components(data)
        # default-visible categories are based on approved only.
        comps = data.get("components", [])
        data["categoriesApproved"] = self._derive_categories(comps, include_statuses={"approved"})
        data["categories"] = self._derive_categories(comps, include_statuses={"approved", "candidate", "needs_review", "duplicate", "reference_page"})
        data["statusCounts"] = {
            st: sum(1 for c in comps if str(c.get("status") or "") == st)
            for st in sorted(STATUSES)
        }
        data["paths"] = {
            "root": str(self.dir),
            "masterLibraryRoot": self.get_master_root(),
            "inbox": str(self.dir / "inbox"),
            "components": str(self.dir / "assets" / "components"),
            "referencePages": str(self.dir / "assets" / "reference_pages"),
            "thumbnails": str(self.dir / "assets" / "thumbnails"),
        }
        self.save(data)
        return data
        # Derive category counts for the panel filter.
        cats: dict[str, int] = {}
        for c in data.get("components", []):
            if c.get("status", "").startswith("retired"):
                continue
            cat = (c.get("category") or "uncategorized").lower()
            cats[cat] = cats.get(cat, 0) + 1
        data["categories"] = [{"id": k, "count": v} for k, v in sorted(cats.items())]
        return data

    def save(self, data: dict) -> None:
        self._write_index(data)

    def asset_path(self, rel: str) -> Path | None:
        """Resolve an asset path safely inside .docs/library (no traversal)."""
        rel = rel.replace("\\", "/").lstrip("/")
        # Component assetPath values are stored with a leading "library/" prefix.
        if rel.startswith("library/"):
            rel = rel[len("library/"):]
        base = self.dir.resolve()
        target = (self.dir / rel).resolve()
        if base != target and base not in target.parents:
            return None
        if not target.is_file():
            return None
        return target

    # ---- component ops ------------------------------------------------------
    def get_component(self, comp_id: str) -> dict | None:
        for c in self.load().get("components", []):
            if c.get("id") == comp_id:
                return c
        return None

    def retire_component(self, comp_id: str) -> bool:
        data = self.load()
        found = False
        for c in data.get("components", []):
            if c.get("id") == comp_id:
                c["status"] = "retired"
                found = True
                break
        if found:
            self.save(data)
        return found

    def restore_component(self, comp_id: str) -> bool:
        data = self.load()
        found = False
        for c in data.get("components", []):
            if c.get("id") == comp_id:
                c["status"] = "approved"
                found = True
                break
        if found:
            self.save(data)
        return found

    ALLOWED_FIELDS = {
        "displayName",
        "shortName",
        "category",
        "partNumber",
        "aliases",
        "tags",
        "notes",
        "defaultLabel",
        "labelPosition",
        "labelLinked",
        "insertWithLabel",
        "status",
    }

    def update_component(self, comp_id: str, patch: dict) -> dict | None:
        data = self.load()
        for c in data.get("components", []):
            if c.get("id") == comp_id:
                rename_asset_file = bool(patch.get("renameAssetFile", False))
                for k, v in patch.items():
                    if k in self.ALLOWED_FIELDS:
                        if k == "status":
                            vv = str(v).strip().lower()
                            if vv not in STATUSES:
                                continue
                        c[k] = v
                # Optional safe file rename to match displayName.
                if rename_asset_file and c.get("assetPath"):
                    ap = self._asset_abs(c)
                    if ap and ap.exists():
                        safe_stem = re.sub(r"[^A-Za-z0-9._ -]+", "", str(c.get("displayName") or ap.stem)).strip() or ap.stem
                        safe_stem = safe_stem.replace(" ", "_")
                        new_ap = ap.with_name(f"{safe_stem}{ap.suffix.lower()}")
                        if new_ap.exists() and new_ap != ap:
                            new_ap = ap.with_name(f"{safe_stem}_{uuid.uuid4().hex[:6]}{ap.suffix.lower()}")
                        try:
                            ap.rename(new_ap)
                            rel_asset = f"library/{new_ap.relative_to(self.dir).as_posix()}"
                            c["assetPath"] = rel_asset
                            # Thumbnail rename/update.
                            if c.get("thumbnailPath"):
                                old_tp = self.dir / str(c.get("thumbnailPath")).replace("library/", "", 1)
                                if old_tp.exists():
                                    new_tp = old_tp.with_name(f"{safe_stem}.jpg")
                                    if new_tp.exists() and new_tp != old_tp:
                                        new_tp = old_tp.with_name(f"{safe_stem}_{uuid.uuid4().hex[:6]}.jpg")
                                    old_tp.rename(new_tp)
                                    c["thumbnailPath"] = f"library/{new_tp.relative_to(self.dir).as_posix()}"
                        except Exception:  # noqa: BLE001
                            pass
                # Mark as user-curated so auto-categorize won't overwrite it.
                c["curated"] = True
                self.save(data)
                return c
        return None

    def delete_component(self, comp_id: str) -> bool:
        """Remove a component entry from the index. Does NOT delete assets on disk."""
        data = self.load()
        before = len(data.get("components", []))
        data["components"] = [c for c in data.get("components", []) if c.get("id") != comp_id]
        if len(data["components"]) == before:
            return False
        self.save(data)
        return True

    def find_usage(self, docs_dir: Path, comp_id: str) -> list[dict]:
        """Return project/page usages for a library component by matching its
        assetPath against canvas image src values."""
        c = self.get_component(comp_id)
        if not c:
            return []
        ap = str(c.get("assetPath") or "")
        if not ap:
            return []
        needle = f"/api/library/assets/{ap}"
        hits: list[dict] = []
        for p in sorted((docs_dir / "projects").glob("*/project.json")):
            try:
                proj = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            pid = proj.get("id") or p.parent.name
            for page in proj.get("pages", []) or []:
                objs = page.get("canvasObjects") or []
                if any(str(o.get("src") or "") == needle for o in objs if isinstance(o, dict)):
                    hits.append({
                        "projectId": pid,
                        "pageId": page.get("id"),
                        "sheetCode": page.get("displaySheetCode") or page.get("sheetCode"),
                        "sheetTitle": page.get("sheetTitle"),
                    })
        return hits

    def set_component_status(self, comp_id: str, status: str) -> bool:
        status = status.strip().lower()
        if status not in STATUSES:
            return False
        data = self.load()
        for c in data.get("components", []):
            if c.get("id") == comp_id:
                c["status"] = status
                c["curated"] = True
                self.save(data)
                return True
        return False

    def bulk_update(self, ids: list[str], patch: dict) -> dict:
        data = self.load()
        updated = 0
        idset = set(ids)
        for c in data.get("components", []):
            if c.get("id") not in idset:
                continue
            for k, v in patch.items():
                if k in self.ALLOWED_FIELDS:
                    if k == "status" and str(v).strip().lower() not in STATUSES:
                        continue
                    c[k] = v
            c["curated"] = True
            updated += 1
        if updated:
            self.save(data)
        return {"ok": True, "updated": updated}

    def _new_component_from_file(self, path: Path, *, status: str = "needs_review") -> dict:
        stem = path.stem
        clean = re.sub(r"[_\-]+", " ", stem).strip()[:120] or "Needs Review"
        cid = f"custom_{uuid.uuid4().hex[:10]}"
        rel_asset = f"library/assets/components/custom/{path.name}"
        thumb_name = f"custom_{uuid.uuid4().hex[:10]}.jpg"
        thumb_rel = f"library/assets/thumbnails/custom/{thumb_name}"
        comp = {
            "id": cid,
            "displayName": clean,
            "shortName": clean,
            "category": "review",
            "aliases": [],
            "tags": ["custom", "inbox"],
            "assetKind": "image",
            "assetPath": rel_asset,
            "thumbnailPath": thumb_rel,
            "status": status,
            "insertWithLabel": True,
            "defaultLabel": clean,
            "source": {
                "sourceType": "inbox",
                "sourceFile": path.name,
                "sourceLocation": "inbox",
            },
        }
        self._compute_hashes(comp)
        # Generate thumbnail when PIL is available.
        ap = self.asset_path(rel_asset)
        tp = self.dir / thumb_rel.replace("library/", "", 1)
        if ap and tp and Image is not None and ap.suffix.lower() != ".svg":
            try:
                tp.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(ap) as im:
                    im.thumbnail((256, 256))
                    im.convert("RGB").save(tp, "JPEG", quality=86)
            except Exception:  # noqa: BLE001
                pass
        return comp

    def _upsert_component_by_sha(self, data: dict, comp: dict) -> tuple[bool, dict]:
        sha = comp.get("sha256")
        if not sha:
            data.setdefault("components", []).append(comp)
            return True, comp
        for c in data.get("components", []):
            if c.get("sha256") == sha:
                return False, c
        data.setdefault("components", []).append(comp)
        return True, comp

    def _copy_to_custom_components(self, src: Path) -> Path:
        dst = self.dir / "assets" / "components" / "custom" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Avoid name collisions.
        if dst.exists():
            dst = dst.with_name(f"{dst.stem}_{uuid.uuid4().hex[:6]}{dst.suffix.lower()}")
        shutil.copy2(src, dst)
        return dst

    def _copy_to_rdm_components(self, src: Path, rel_folder: Path) -> Path:
        dst = self.dir / "assets" / "components" / "rdm_layout_editor" / rel_folder / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Avoid collisions while preserving folder structure.
        if dst.exists():
            dst = dst.with_name(f"{dst.stem}_{uuid.uuid4().hex[:6]}{dst.suffix.lower()}")
        shutil.copy2(src, dst)
        return dst

    def _safe_title(self, name: str) -> str:
        s = re.sub(r"[_\-]+", " ", (name or "").strip())
        s = re.sub(r"\s+", " ", s)
        # Preserve PR part codes and mixed alnum chunks.
        out = []
        for tok in s.split(" "):
            up = tok.upper()
            if re.fullmatch(r"PR\d{3,5}", up):
                out.append(up)
            elif tok.isupper() and 2 <= len(tok) <= 8:
                out.append(tok)
            elif re.fullmatch(r"[A-Za-z]*\d+[A-Za-z0-9]*", tok):
                out.append(tok)
            else:
                out.append(tok.capitalize())
        return " ".join(out).strip() or "Needs Review"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _canon_category_from_folder(self, folder_name: str) -> str:
        f = (folder_name or "").strip().lower()
        # Folder-based master mode: preserve distinct folder categories.
        if f in {
            "alarm", "alarms_safety", "controllers", "custom", "electrical",
            "electrical_power", "equipment", "expansion_modules", "hvac", "legends",
            "lighting", "logos", "network", "panel", "panels_enclosures",
            "refrigeration", "sensors_transducers", "symbol", "symbols_markers",
            "uncategorized",
        }:
            return f
        if f in {"hvac", "ahu"}:
            return "sensors"
        if f in {"refrigeration", "tank"}:
            return "refrigeration"
        if f in {"light", "lighting"}:
            return "lighting"
        if f in {"panel", "panels", "enclosure", "enclosures"}:
            return "panels"
        if f in {"symbol", "symbols", "marker", "markers", "pipes", "pipe"}:
            return "symbols"
        if f in {"logo", "logos"}:
            return "logos"
        if f in {"network", "data", "network_data"}:
            return "network"
        if f in {"electrical", "power", "electrical_power"}:
            return "electrical"
        if f in {"alarms", "alarm", "safety", "alarms_safety"}:
            return "alarms"
        if f in {"sensors", "sensor", "transducers", "sensors_transducers"}:
            return "sensors"
        if f in {"controllers", "controller"}:
            return "controllers"
        if f in {"expansion", "expansion_modules", "modules"}:
            return "expansion"
        if f in {"legend", "legends"}:
            return "legends"
        return "review"

    def _category_folder_name(self, category: str) -> str:
        cat = (category or "review").strip().lower()
        if cat in {
            "alarm", "alarms_safety", "controllers", "custom", "electrical",
            "electrical_power", "equipment", "expansion_modules", "hvac", "legends",
            "lighting", "logos", "network", "panel", "panels_enclosures",
            "refrigeration", "sensors_transducers", "symbol", "symbols_markers",
            "uncategorized",
        }:
            return cat
        return {
            "controllers": "controllers",
            "expansion": "expansion_modules",
            "electrical": "electrical_power",
            "network": "network_data",
            "panels": "panels_enclosures",
            "refrigeration": "refrigeration",
            "lighting": "lighting",
            "alarms": "alarms_safety",
            "sensors": "sensors_transducers",
            "symbols": "symbols_markers",
            "logos": "logos",
            "legends": "legends",
            "review": "custom",
            "reference-page": "custom",
        }.get(cat, "custom")

    def _clean_display_from_filename(self, file_name: str) -> str:
        stem = Path(file_name).stem
        s = stem
        s = re.sub(r"^[0-9a-f]{8,}[_\-]?", "", s, flags=re.I)
        s = re.sub(r"[_\-]+", " ", s)
        s = re.sub(r"\bthumbnail\b", "", s, flags=re.I)
        s = re.sub(r"\s+", " ", s).strip()
        # normalize logo labels
        low = s.lower()
        if low in {"heb logo", "h e b logo", "heb"}:
            return "H-E-B Logo"
        if low in {"singh360 logo", "singh 360 logo"}:
            return "Singh360 Logo"
        return self._safe_title(s)

    def _is_thumbnail_source_path(self, p: Path) -> bool:
        parts = [x.lower() for x in p.parts]
        return "thumbnails" in parts

    def _thumbnail_dest_for(self, category: str, component_stem: str) -> tuple[str, Path]:
        thumb_folder = self._category_folder_name(category)
        thumb_name = f"{component_stem}_{uuid.uuid4().hex[:8]}.jpg"
        thumb_rel = f"library/assets/thumbnails/{thumb_folder}/{thumb_name}"
        thumb_abs = self.dir / "assets" / "thumbnails" / thumb_folder / thumb_name
        return thumb_rel, thumb_abs

    def _build_thumbnail(self, src_abs: Path, thumb_abs: Path) -> None:
        if Image is None:
            return
        if src_abs.suffix.lower() == ".svg":
            return
        try:
            thumb_abs.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(src_abs) as im:
                im.thumbnail((256, 256))
                im.convert("RGB").save(thumb_abs, "JPEG", quality=86)
        except Exception:  # noqa: BLE001
            return

    def _render_pdf_first_page(self, pdf_abs: Path, out_png_abs: Path, *, dpi: int = 300) -> tuple[bool, str]:
        if fitz is None:
            return False, "PyMuPDF is not installed. Install dependency 'PyMuPDF' to import PDF components."
        try:
            out_png_abs.parent.mkdir(parents=True, exist_ok=True)
            doc = fitz.open(pdf_abs)
            if doc.page_count < 1:
                return False, f"PDF has no pages: {pdf_abs}"
            page = doc.load_page(0)
            mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix.save(out_png_abs)
            doc.close()
            return True, ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    def _rdm_classify(self, src_folder: str, stem: str) -> tuple[str, str, list[str], bool]:
        """Return (category, display_name, tags, high_confidence)."""
        f = (src_folder or "").strip().lower()
        n = (stem or "").strip().lower()
        display = self._safe_title(stem)

        # Folder-led defaults.
        if f == "refrigeration":
            category = "refrigeration"
        elif f == "light":
            category = "lighting"
        elif f == "ahu":
            category = "sensors"
        elif f == "pipes":
            category = "symbols"
        elif f == "tank":
            category = "refrigeration"
        else:
            category = "review"

        high = category != "review"
        tags = [*RDM_TAGS]

        # Filename overrides.
        if "traffic lights off" in n:
            category, display, high = "alarms", "Traffic Lights Off", True
            tags.append("traffic")
        elif "traffic lights on" in n:
            category, display, high = "alarms", "Traffic Lights On", True
            tags.append("traffic")
        elif "red strobe" in n or "red alarm" in n:
            category, display, high = "alarms", "Red Strobe", True
        elif "amber strobe" in n or "amber alarm" in n:
            category, display, high = "alarms", "Amber Strobe", True
        elif "pump" in n:
            category, display, high = "refrigeration", "Pump", True
        elif "compressor" in n:
            category, display, high = "refrigeration", "Compressor", True
        elif "valve open" in n:
            category, display, high = "refrigeration", "Valve Open", True
        elif "valve closed" in n:
            category, display, high = "refrigeration", "Valve Closed", True
        elif "coldroom" in n:
            category, display, high = "refrigeration", "Coldroom", True
        elif "vessel" in n:
            category, display, high = "refrigeration", "Vessel", True
        elif "data manager" in n or re.search(r"\bdmt\b", n) or re.search(r"\bdm\b", n):
            category, display, high = "network", "Data Manager", True
        elif "intuitiveplant" in n:
            category, display, high = "controllers", "RDM IntuitivePlant Controller", True
        elif re.search(r"\bpr\d{3,5}\b", n):
            pn = re.search(r"\bpr\d{3,5}\b", n)
            part = pn.group(0).upper() if pn else ""
            tail = n.replace(part.lower(), "").strip()
            tail_disp = self._safe_title(tail) if tail else ""
            display = f"{part}{(' ' + tail_disp) if tail_disp else ''}".strip()
            category, high = "controllers", True
        elif "mercury switch" in n:
            category, display, high = "controllers", "Mercury Switch", True
        elif "mercury" in n:
            category, display, high = "controllers", self._safe_title(stem if "2" in n else "Mercury Controller"), True

        tags.append((src_folder or "other").strip().lower() or "other")
        # normalize + dedupe tags
        norm_tags = []
        seen = set()
        for t in tags:
            tv = re.sub(r"\s+", "-", t.strip().lower())
            if tv and tv not in seen:
                seen.add(tv)
                norm_tags.append(tv)
        return category, display, norm_tags, high

    def _is_forbidden_rdm_root(self, p: Path) -> bool:
        s = str(p.resolve())
        low = s.lower().rstrip("\\/")
        # Block broad roots.
        if re.fullmatch(r"[a-z]:", low):
            return True
        if low in {r"c:\windows", r"c:\program files", r"c:\program files (x86)"}:
            return True
        return False

    def import_rdm_folder(
        self,
        folder_path: str | Path,
        *,
        dry_run: bool = False,
        source_name: str = "RDM Layout Editor 3",
        auto_approve: bool = True,
        reset_rdm_import: bool = False,
    ) -> dict:
        """Import official RDM image library folder into local .docs library.

        Reads files recursively from the provided folder (no writes there), copies
        assets to .docs/library/assets/components/rdm_layout_editor/, builds
        thumbnails, and upserts components with dedupe + curated-safe updates.
        """
        self.ensure()
        src_root = Path(folder_path).expanduser().resolve()
        if not src_root.exists() or not src_root.is_dir():
            return {"ok": False, "error": f"RDM folder not found or not a directory: {src_root}"}
        if self._is_forbidden_rdm_root(src_root):
            return {"ok": False, "error": f"Refusing unsafe broad/system path: {src_root}"}

        data = self.load()

        if reset_rdm_import and not dry_run:
            kept = []
            for c in data.get("components", []):
                st = str((c.get("source") or {}).get("sourceType") or "").lower()
                if st == "rdm-layout-editor":
                    continue
                kept.append(c)
            data["components"] = kept

        # Existing hashes for dedupe checks.
        by_sha = {str(c.get("sha256") or ""): c for c in data.get("components", []) if c.get("sha256")}
        ph_pool = [(str(c.get("perceptualHash") or ""), c) for c in data.get("components", []) if c.get("perceptualHash")]

        scanned = 0
        added = 0
        skipped_duplicates = 0
        updated = 0
        needs_review = 0
        errors: list[str] = []
        cat_counts: dict[str, int] = {}
        dry_preview: list[dict] = []

        for p in sorted(src_root.rglob("*")):
            if p.is_dir() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            scanned += 1
            rel = p.relative_to(src_root)
            folder_name = rel.parts[0] if rel.parts else "Other"
            category, display_name, tags, high = self._rdm_classify(folder_name, p.stem)
            cat_counts[category] = cat_counts.get(category, 0) + 1

            try:
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p}: {exc}")
                continue

            # Exact duplicate skip/update.
            existing = by_sha.get(sha)
            if existing is not None:
                skipped_duplicates += 1
                # If not curated, keep metadata fresher for source/tags/category.
                if existing.get("curated") is not True:
                    existing["source"] = {
                        "sourceType": "rdm-layout-editor",
                        "sourceFile": p.name,
                        "sourceLocation": str(rel.parent).replace("\\", "/"),
                        "sourceName": source_name,
                    }
                    existing["tags"] = sorted({*(existing.get("tags") or []), *tags})
                    existing["category"] = category
                    existing["displayName"] = display_name
                    existing["defaultLabel"] = display_name
                    if auto_approve and high:
                        existing["status"] = "approved"
                    updated += 1
                if dry_run:
                    dry_preview.append({
                        "file": str(rel).replace("\\", "/"),
                        "category": category,
                        "displayName": display_name,
                        "action": "skip-duplicate",
                    })
                continue

            # Near-duplicate by perceptual hash.
            w, h, fsize, ph = self._image_meta(p)
            near_dup = False
            if ph:
                for eph, _ in ph_pool:
                    if eph and self._hamming(ph, eph) <= 4:
                        near_dup = True
                        break
            if near_dup:
                skipped_duplicates += 1
                if dry_run:
                    dry_preview.append({
                        "file": str(rel).replace("\\", "/"),
                        "category": category,
                        "displayName": display_name,
                        "action": "skip-near-duplicate",
                    })
                continue

            if dry_run:
                dry_preview.append({
                    "file": str(rel).replace("\\", "/"),
                    "category": category,
                    "displayName": display_name,
                    "action": "add",
                })
                continue

            try:
                copied = self._copy_to_rdm_components(p, rel.parent)
                rel_asset = f"library/{copied.relative_to(self.dir).as_posix()}"
                thumb_name = f"rdm_{uuid.uuid4().hex[:12]}.jpg"
                thumb_rel = f"library/assets/thumbnails/rdm_layout_editor/{thumb_name}"

                comp = {
                    "id": f"rdm_{uuid.uuid4().hex[:10]}",
                    "displayName": display_name,
                    "shortName": display_name,
                    "category": category,
                    "aliases": [],
                    "tags": tags,
                    "assetKind": "image",
                    "assetPath": rel_asset,
                    "thumbnailPath": thumb_rel,
                    "status": "approved" if (auto_approve and high) else "needs_review",
                    "insertWithLabel": True,
                    "defaultLabel": display_name,
                    "source": {
                        "sourceType": "rdm-layout-editor",
                        "sourceFile": p.name,
                        "sourceLocation": str(rel.parent).replace("\\", "/"),
                        "sourceName": source_name,
                    },
                    "width": w or None,
                    "height": h or None,
                    "fileSize": fsize,
                    "sha256": sha,
                    "perceptualHash": ph,
                }

                # Thumbnail generation.
                ap = self.asset_path(rel_asset)
                tp = self.dir / thumb_rel.replace("library/", "", 1)
                if ap and tp and Image is not None and ap.suffix.lower() != ".svg":
                    try:
                        tp.parent.mkdir(parents=True, exist_ok=True)
                        with Image.open(ap) as im:
                            im.thumbnail((256, 256))
                            im.convert("RGB").save(tp, "JPEG", quality=86)
                    except Exception:  # noqa: BLE001
                        pass

                data.setdefault("components", []).append(comp)
                by_sha[sha] = comp
                if ph:
                    ph_pool.append((ph, comp))
                if comp["status"] == "needs_review":
                    needs_review += 1
                added += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p}: {exc}")

        if not dry_run:
            self._curate_components(data)
            self._dedupe_components(data)
            self.save(data)

        return {
            "ok": True,
            "scanned": scanned,
            "added": added,
            "skippedDuplicates": skipped_duplicates,
            "updated": updated,
            "needsReview": needs_review,
            "categories": cat_counts,
            "errors": errors,
            "dryRun": dry_run,
            "preview": dry_preview[:300],
        }

    def import_local_folder(
        self,
        folder_path: str | Path,
        *,
        dry_run: bool = False,
        reset_clean: bool = False,
        source_name: str = "Local Library Folder",
    ) -> dict:
        """Import/reset from a local folder (single source of truth workflow)."""
        self.ensure()
        src_root = Path(folder_path).expanduser().resolve()
        if not src_root.exists() or not src_root.is_dir():
            return {"ok": False, "error": f"Folder not found or not a directory: {src_root}"}

        data = self.load()

        archived_old_entries = 0
        if reset_clean and not dry_run:
            kept = []
            for c in data.get("components", []):
                if c.get("curated") is True:
                    kept.append(c)
                else:
                    c["status"] = "retired"
                    c["archivedAt"] = self._now_iso()
                    archived_old_entries += 1
                    kept.append(c)
            data["components"] = kept

        # Build a set of non-thumbnail stems to detect thumbnail-only assets.
        non_thumb_stems: set[str] = set()
        all_files = [p for p in src_root.rglob("*") if p.is_file()]
        for p in all_files:
            if p.suffix.lower() in IMAGE_EXTS | {".pdf"} and not self._is_thumbnail_source_path(p):
                non_thumb_stems.add(p.stem.lower())

        by_sha = {str(c.get("sha256") or ""): c for c in data.get("components", []) if c.get("sha256")}
        scanned = 0
        added = 0
        updated = 0
        skipped_duplicates = 0
        pdf_converted = 0
        needs_review = 0
        errors: list[str] = []
        cat_counts: dict[str, int] = {}
        preview: list[dict] = []

        for src in sorted(all_files):
            ext = src.suffix.lower()
            if ext not in IMAGE_EXTS and ext != ".pdf":
                continue
            scanned += 1
            rel = src.relative_to(src_root)
            rel_str = rel.as_posix()
            folder_hint = rel.parts[0] if rel.parts else "custom"
            if rel.parts and rel.parts[0].lower() in {"assets", "components", "thumbnails", "originals"} and len(rel.parts) > 1:
                folder_hint = rel.parts[1]
            if rel.parts and rel.parts[0].lower() == "assets" and len(rel.parts) > 2 and rel.parts[1].lower() in {"components", "thumbnails"}:
                folder_hint = rel.parts[2]
            category = self._canon_category_from_folder(folder_hint)
            display_name = self._clean_display_from_filename(src.name)
            source_quality = "thumbnail_only" if (self._is_thumbnail_source_path(src) and src.stem.lower() not in non_thumb_stems) else "full"
            if source_quality == "thumbnail_only":
                needs_review += 1
            cat_counts[category] = cat_counts.get(category, 0) + 1

            # PDF conversion path.
            actual_image_src = src
            original_pdf_rel = ""
            rendered_rel = ""
            render_dpi = 0
            if ext == ".pdf":
                cat_folder = self._category_folder_name(category)
                orig_pdf_name = f"{src.stem}_{uuid.uuid4().hex[:8]}.pdf"
                orig_pdf_abs = self.dir / "assets" / "originals" / "pdf" / orig_pdf_name
                rendered_name = f"{src.stem}_{uuid.uuid4().hex[:8]}.png"
                rendered_abs = self.dir / "assets" / "components" / cat_folder / rendered_name
                original_pdf_rel = f"library/assets/originals/pdf/{orig_pdf_name}"
                rendered_rel = f"library/assets/components/{cat_folder}/{rendered_name}"
                if not dry_run:
                    try:
                        orig_pdf_abs.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, orig_pdf_abs)
                        ok, msg = self._render_pdf_first_page(orig_pdf_abs, rendered_abs, dpi=300)
                        if not ok:
                            errors.append(f"{rel_str}: {msg}")
                            continue
                        pdf_converted += 1
                        actual_image_src = rendered_abs
                        render_dpi = 300
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{rel_str}: {exc}")
                        continue
                else:
                    preview.append({"file": rel_str, "category": category, "displayName": display_name, "action": "pdf-convert"})

            # Compute SHA from real source image bytes (or converted image if PDF).
            try:
                sha = hashlib.sha256(actual_image_src.read_bytes() if actual_image_src.exists() else src.read_bytes()).hexdigest()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel_str}: {exc}")
                continue

            existing = by_sha.get(sha)
            if existing is not None:
                skipped_duplicates += 1
                if existing.get("curated") is not True:
                    existing["source"] = {
                        "sourceType": "local-library-folder",
                        "sourceFile": src.name,
                        "sourceLocation": str(rel.parent).replace("\\", "/"),
                        "sourceName": source_name,
                    }
                    existing["category"] = category
                    existing["tags"] = sorted({*(existing.get("tags") or []), "local", "library-sync"})
                    existing["sourceQuality"] = source_quality
                    updated += 1
                continue

            if dry_run:
                preview.append({"file": rel_str, "category": category, "displayName": display_name, "action": "add"})
                continue

            try:
                cat_folder = self._category_folder_name(category)
                if ext == ".pdf":
                    comp_abs = actual_image_src
                    rel_asset = rendered_rel
                else:
                    comp_name = f"{src.stem}_{uuid.uuid4().hex[:8]}{src.suffix.lower()}"
                    comp_abs = self.dir / "assets" / "components" / cat_folder / comp_name
                    comp_abs.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, comp_abs)
                    rel_asset = f"library/assets/components/{cat_folder}/{comp_name}"

                thumb_rel, thumb_abs = self._thumbnail_dest_for(category, Path(rel_asset).stem)
                self._build_thumbnail(comp_abs, thumb_abs)

                comp = {
                    "id": f"cmp_{sha[:12]}",
                    "displayName": display_name,
                    "shortName": display_name,
                    "category": category,
                    "aliases": [],
                    "tags": ["local", "library-sync"],
                    "assetKind": "image",
                    "assetPath": rel_asset,
                    "thumbnailPath": thumb_rel,
                    "status": "needs_review" if source_quality == "thumbnail_only" else "approved",
                    "insertWithLabel": True,
                    "defaultLabel": display_name,
                    "sourceQuality": source_quality,
                    "source": {
                        "sourceType": "local-library-folder",
                        "sourceFile": src.name,
                        "sourceLocation": str(rel.parent).replace("\\", "/"),
                        "sourceName": source_name,
                    },
                    "sha256": sha,
                }
                if ext == ".pdf":
                    comp["sourceType"] = "pdf"
                    comp["originalPdfPath"] = original_pdf_rel
                    comp["renderedImagePath"] = rel_asset
                    comp["pageNumber"] = 1
                    comp["renderDpi"] = render_dpi

                self._compute_hashes(comp)
                data.setdefault("components", []).append(comp)
                by_sha[sha] = comp
                added += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{rel_str}: {exc}")

        if not dry_run:
            self._curate_components(data)
            self._dedupe_components(data)
            self.save(data)

        return {
            "ok": True,
            "scanned": scanned,
            "added": added,
            "updated": updated,
            "skippedDuplicates": skipped_duplicates,
            "pdfConverted": pdf_converted,
            "needsReview": needs_review,
            "archivedOldEntries": archived_old_entries,
            "categories": cat_counts,
            "errors": errors,
            "dryRun": dry_run,
            "preview": preview[:300],
        }

    def refresh_from_master_root(self, *, dry_run: bool = False, reset_clean: bool = False) -> dict:
        root = self.get_master_root()
        return self.import_local_folder(root, dry_run=dry_run, reset_clean=reset_clean, source_name="Master Library Root")

    def sync_names_from_files(self) -> dict:
        data = self.load()
        changed = 0
        for c in data.get("components", []):
            if c.get("curated") is True:
                continue
            ap = self._asset_abs(c)
            if not ap:
                continue
            new_name = self._clean_display_from_filename(ap.name)
            if new_name and new_name != c.get("displayName"):
                c["displayName"] = new_name
                c["shortName"] = new_name
                c["defaultLabel"] = c.get("partNumber") or new_name
                changed += 1
        if changed:
            self.save(data)
        return {"ok": True, "changed": changed}

    def rebuild_thumbnails(self) -> dict:
        data = self.load()
        built = 0
        missing = 0
        for c in data.get("components", []):
            ap = self._asset_abs(c)
            if not ap:
                continue
            cat = self._category_folder_name(str(c.get("category") or "review"))
            if c.get("thumbnailPath"):
                tp = self.dir / str(c.get("thumbnailPath")).replace("library/", "", 1)
            else:
                t_rel, tp = self._thumbnail_dest_for(cat, ap.stem)
                c["thumbnailPath"] = t_rel
            if not tp.exists():
                missing += 1
            self._build_thumbnail(ap, tp)
            if tp.exists():
                built += 1
        self.save(data)
        return {"ok": True, "rebuilt": built, "missingBefore": missing}

    def archive_dirty_extracted_assets(self) -> dict:
        data = self.load()
        changed = 0
        for c in data.get("components", []):
            if c.get("curated") is True:
                continue
            st = str(c.get("status") or "").lower()
            src_type = str((c.get("source") or {}).get("sourceType") or "").lower()
            if src_type in {"rdm-layout-editor", "local-library-folder"}:
                continue
            if st in {"needs_review", "duplicate", "candidate"}:
                c["status"] = "retired"
                c["archivedAt"] = self._now_iso()
                changed += 1
        if changed:
            self.save(data)
        return {"ok": True, "archived": changed}

    def rescan_inbox(self) -> dict:
        inbox = self.dir / "inbox"
        processed = self.dir / "inbox" / "processed"
        data = self.load()
        added = 0
        duplicates = 0
        for p in sorted(inbox.iterdir() if inbox.exists() else []):
            if p.is_dir() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            copied = self._copy_to_custom_components(p)
            comp = self._new_component_from_file(copied, status="needs_review")
            created, _ = self._upsert_component_by_sha(data, comp)
            if created:
                added += 1
            else:
                duplicates += 1
            processed.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(p), str(processed / p.name))
            except Exception:  # noqa: BLE001
                pass
        self._curate_components(data)
        self._dedupe_components(data)
        self.save(data)
        return {"ok": True, "added": added, "duplicates": duplicates}

    def rescan_library_assets(self) -> dict:
        """Pick up manually-added files under assets/components/custom and
        assets/reference_pages/custom that are not yet indexed."""
        data = self.load()
        added = 0
        updated = 0
        missing = 0
        roots = [
            self.dir / "assets" / "components",
            self.dir / "assets" / "reference_pages" / "custom",
        ]

        # Mark missing files first.
        for c in data.get("components", []):
            ap = self._asset_abs(c)
            if not ap:
                c["missing"] = True
                missing += 1
            else:
                c["missing"] = False

        # Hash index for existing components to detect moved/renamed files.
        by_sha: dict[str, dict] = {str(c.get("sha256") or ""): c for c in data.get("components", []) if c.get("sha256")}

        for root in roots:
            if not root.exists():
                continue
            for p in sorted(root.rglob("*")):
                if p.is_dir() or p.suffix.lower() not in IMAGE_EXTS:
                    continue
                rel_asset = f"library/{p.relative_to(self.dir).as_posix()}"
                exists = any(str(c.get("assetPath") or "") == rel_asset for c in data.get("components", []))
                if exists:
                    continue

                # Try matching by SHA to update moved paths.
                try:
                    sha = hashlib.sha256(p.read_bytes()).hexdigest()
                except Exception:  # noqa: BLE001
                    sha = ""
                if sha and sha in by_sha:
                    c0 = by_sha[sha]
                    old = str(c0.get("assetPath") or "")
                    if old != rel_asset:
                        c0["assetPath"] = rel_asset
                        c0["missing"] = False
                        if c0.get("curated") is not True:
                            new_name = self._clean_display_from_filename(p.name)
                            c0["displayName"] = new_name
                            c0["shortName"] = new_name
                            c0["defaultLabel"] = c0.get("partNumber") or new_name
                        updated += 1
                    continue

                comp = self._new_component_from_file(p, status="needs_review")
                comp["assetPath"] = rel_asset
                if "reference_pages" in rel_asset:
                    comp["category"] = "reference-page"
                    comp["status"] = "reference_page"
                created, _ = self._upsert_component_by_sha(data, comp)
                if created:
                    added += 1
        self._curate_components(data)
        self._dedupe_components(data)
        self.save(data)
        return {"ok": True, "added": added, "updated": updated, "missing": missing}

    def add_component_upload(self, src_file: Path, *, display_name: str, category: str, part_number: str = "",
                             approve: bool = False) -> dict:
        copied = self._copy_to_custom_components(src_file)
        data = self.load()
        comp = self._new_component_from_file(copied, status="approved" if approve else "needs_review")
        comp["displayName"] = display_name.strip() or comp["displayName"]
        comp["shortName"] = comp["displayName"]
        comp["category"] = (category or "review").strip().lower()
        comp["partNumber"] = part_number.strip()
        comp["defaultLabel"] = comp["partNumber"] or comp["displayName"]
        created, existing = self._upsert_component_by_sha(data, comp)
        self._curate_components(data)
        self._dedupe_components(data)
        self.save(data)
        return {"ok": True, "created": created, "component": comp if created else existing}

    def auto_categorize(self) -> dict:
        data = self.load()
        before = json.dumps(data.get("components", []), sort_keys=True)
        self._curate_components(data)
        self._dedupe_components(data)
        after = json.dumps(data.get("components", []), sort_keys=True)
        if before != after:
            self.save(data)
        return {"ok": True, "changed": 0 if before == after else 1, "total": len(data.get("components", []))}
