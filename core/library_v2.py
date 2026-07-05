"""core/library_v2.py — Milestone 4A clean component library (Phases 0 + 1).

Single active library root:

    .docs/library/components/<category>/<file>

`manifest.json` (next to `components/`) is the metadata source of truth.
`thumbnails/` is generated only and never scanned as source. `aliases.json`
and `connector_styles.json` sit beside the manifest.

Hard rules honoured here:
  * Refresh scans ONLY `.docs/library/components`.
  * Never scans thumbnails, projects, exports, archive, or generated assets.
  * Folder name is the default category; filename stem the default display name.
  * Content hash (SHA256) + perceptual hash block duplicates.
  * Running Refresh twice does not duplicate files/components (idempotent).
  * Rebuild Thumbnails deletes thumbnails and regenerates from the manifest.
  * Clean Duplicates moves duplicates to `.docs/archive/` after confirmation.

No file is silently renamed. In-app metadata edits persist to the manifest
immediately. Renaming the source file is an explicit action.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:  # Pillow is optional; hashing/thumbnails degrade gracefully without it.
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None

from core.drawing_style import (
    LIBRARY_CATEGORIES,
    category_default,
    connector_styles_payload,
)
from core.symbol_generator import generate_symbol_svg

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
PDF_EXT = {".pdf"}
SOURCE_EXTS = IMAGE_EXTS | PDF_EXT
SYMBOL_SUFFIX = ".symbol.svg"

MANIFEST_VERSION = 2
PHASH_THRESHOLD = 4  # Hamming distance for near-duplicate perceptual match.

# Fields a client may patch; edits persist to the manifest immediately.
EDITABLE_FIELDS = {
    "displayName",
    "category",
    "subcategory",
    "manufacturer",
    "partNumber",
    "aliases",
    "defaultLabel",
    "defaultWidth",
    "defaultHeight",
    "labelPosition",
    "approved",
    "needsReview",
    "favorite",
    "notes",
    "ports",
    "type",
}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip()).strip("-")
    return s or "component"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LibraryV2:
    def __init__(self, docs_dir: Path) -> None:
        self.docs = Path(docs_dir)
        self.root = self.docs / "library"
        self.components = self.root / "components"
        self.thumbnails = self.root / "thumbnails"
        self.manifest_path = self.root / "manifest.json"
        self.aliases_path = self.root / "aliases.json"
        self.connectors_path = self.root / "connector_styles.json"
        self.archive = self.docs / "archive"
        self.projects = self.docs / "projects"
        self.exports = self.docs / "exports"

    # ---- scaffolding -----------------------------------------------------
    def ensure(self) -> None:
        for top in (self.projects, self.exports, self.archive, self.components, self.thumbnails):
            top.mkdir(parents=True, exist_ok=True)
        for cat in LIBRARY_CATEGORIES:
            (self.components / cat).mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._write_manifest({"version": MANIFEST_VERSION, "components": [], "updatedAt": _now()})
        if not self.aliases_path.exists():
            self._write_json(self.aliases_path, {"version": 1, "aliases": {}})
        if not self.connectors_path.exists():
            self._write_json(self.connectors_path, connector_styles_payload())

    # ---- manifest I/O ----------------------------------------------------
    def _read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {"version": MANIFEST_VERSION, "components": [], "updatedAt": _now()}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"version": MANIFEST_VERSION, "components": [], "updatedAt": _now()}
        data.setdefault("version", MANIFEST_VERSION)
        data.setdefault("components", [])
        return data

    def _write_manifest(self, data: dict) -> None:
        data["updatedAt"] = _now()
        self._write_json(self.manifest_path, data)

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- hashing ---------------------------------------------------------
    @staticmethod
    def content_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def perceptual_hash(path: Path) -> str | None:
        """8x8 average hash → 16-hex string. None if Pillow/image unavailable."""
        if Image is None or path.suffix.lower() not in IMAGE_EXTS or path.suffix.lower() == ".svg":
            return None
        try:
            img = Image.open(path).convert("L").resize((8, 8))
        except Exception:  # noqa: BLE001
            return None
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p >= avg else "0" for p in pixels)
        return f"{int(bits, 2):016x}"

    @staticmethod
    def _phash_distance(a: str | None, b: str | None) -> int:
        if not a or not b:
            return 999
        try:
            return bin(int(a, 16) ^ int(b, 16)).count("1")
        except Exception:  # noqa: BLE001
            return 999

    # ---- source scan (ONLY components/) ----------------------------------
    def _iter_sources(self):
        """Yield (category, path) for every source file under components/<cat>/."""
        if not self.components.exists():
            return
        for cat_dir in sorted(self.components.iterdir()):
            if not cat_dir.is_dir() or cat_dir.name.startswith("."):
                continue
            category = cat_dir.name
            for path in sorted(cat_dir.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                name = path.name.lower()
                if name.endswith(SYMBOL_SUFFIX):  # generated symbols are not sources
                    continue
                if path.suffix.lower() not in SOURCE_EXTS:
                    continue
                yield category, path

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    # ---- refresh (idempotent) --------------------------------------------
    def refresh(self, dry_run: bool = False) -> dict:
        """Scan components/, add new files as manifest entries, block duplicates.

        Idempotent: a file already tracked (by sourceFile or content hash) is
        skipped. Near-duplicate images (perceptual hash within threshold) are
        flagged needsReview but still tracked so nothing is lost.
        """
        self.ensure()
        manifest = self._read_manifest()
        components: list[dict] = manifest["components"]

        by_source = {c.get("sourceFile"): c for c in components}
        by_hash = {c.get("contentHash"): c for c in components if c.get("contentHash")}

        scanned = added = skipped = duplicates = flagged = 0
        for category, path in self._iter_sources():
            scanned += 1
            rel = self._rel(path)
            if rel in by_source:
                skipped += 1
                continue
            chash = self.content_hash(path)
            if chash in by_hash:
                # Same bytes already tracked under a different path → duplicate.
                duplicates += 1
                skipped += 1
                continue
            phash = self.perceptual_hash(path)
            near = None
            for c in components:
                if self._phash_distance(phash, c.get("perceptualHash")) <= PHASH_THRESHOLD:
                    near = c
                    break
            if dry_run:
                added += 1
                by_hash[chash] = {"sourceFile": rel}
                by_source[rel] = {"sourceFile": rel}
                continue
            entry = self._new_entry(category, path, chash, phash)
            if near is not None:
                entry["needsReview"] = True
                entry["notes"] = (entry.get("notes") or "") + f"[near-dup of {near.get('id')}]"
                flagged += 1
            components.append(entry)
            by_source[rel] = entry
            by_hash[chash] = entry
            added += 1

        if not dry_run:
            self._write_manifest(manifest)
        return {
            "ok": True,
            "scanned": scanned,
            "added": added,
            "skipped": skipped,
            "duplicates": duplicates,
            "flaggedNearDup": flagged,
            "dryRun": dry_run,
        }

    def _new_entry(self, category: str, path: Path, chash: str, phash: str | None) -> dict:
        cd = category_default(category)
        stem = path.stem
        width = height = None
        if Image is not None and path.suffix.lower() in IMAGE_EXTS and path.suffix.lower() != ".svg":
            try:
                with Image.open(path) as im:
                    width, height = im.size
            except Exception:  # noqa: BLE001
                pass
        return {
            "id": f"{category}_{uuid.uuid4().hex[:10]}",
            "displayName": stem.replace("_", " ").strip() or stem,
            "category": category,
            "subcategory": "",
            "manufacturer": "",
            "partNumber": "",
            "aliases": [],
            "sourceFile": self._rel(path),
            "thumbnailFile": "",
            "symbolFile": "",
            "type": cd.type,
            "defaultLabel": stem,
            "defaultWidth": cd.width,
            "defaultHeight": cd.height,
            "labelPosition": cd.label_position,
            "ports": [dict(p) for p in cd.ports],
            "approved": True,
            "needsReview": False,
            "favorite": False,
            "notes": "",
            "contentHash": chash,
            "perceptualHash": phash,
            "imageWidth": width,
            "imageHeight": height,
            "source": {"file": self._rel(path)},
            "createdAt": _now(),
        }

    # ---- thumbnails ------------------------------------------------------
    def rebuild_thumbnails(self, size: int = 256) -> dict:
        """Delete all thumbnails and regenerate from the manifest only."""
        self.ensure()
        if self.thumbnails.exists():
            shutil.rmtree(self.thumbnails)
        self.thumbnails.mkdir(parents=True, exist_ok=True)
        manifest = self._read_manifest()
        rebuilt = missing = 0
        for comp in manifest["components"]:
            src = self.root / comp.get("sourceFile", "")
            if not src.exists():
                missing += 1
                comp["thumbnailFile"] = ""
                continue
            thumb_rel = self._thumb_rel(comp, src)
            thumb_path = self.root / thumb_rel
            if self._make_thumbnail(src, thumb_path, size):
                comp["thumbnailFile"] = thumb_rel
                rebuilt += 1
            else:
                comp["thumbnailFile"] = ""
        self._write_manifest(manifest)
        return {"ok": True, "rebuilt": rebuilt, "missingSource": missing}

    def _thumb_rel(self, comp: dict, src: Path) -> str:
        cat = comp.get("category", "custom")
        return f"thumbnails/{cat}/{src.stem}.webp"

    def _make_thumbnail(self, src: Path, dest: Path, size: int) -> bool:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() == ".svg":
            # SVG is already vector; copy as-is so the UI can render it directly.
            try:
                shutil.copyfile(src, dest.with_suffix(".svg"))
                return True
            except Exception:  # noqa: BLE001
                return False
        if Image is None:
            return False
        try:
            with Image.open(src) as im:
                im = im.convert("RGBA")
                im.thumbnail((size, size))
                bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                bg.alpha_composite(im)
                bg.convert("RGB").save(dest, "WEBP", quality=86)
            return True
        except Exception:  # noqa: BLE001
            return False

    # ---- clean duplicates ------------------------------------------------
    def clean_duplicates(self, dry_run: bool = True) -> dict:
        """Group by content hash; keep the first, archive the rest after confirm."""
        self.ensure()
        manifest = self._read_manifest()
        components = manifest["components"]
        groups: dict[str, list[dict]] = {}
        for c in components:
            key = c.get("contentHash") or c.get("id")
            groups.setdefault(key, []).append(c)

        dup_ids: list[str] = []
        for members in groups.values():
            if len(members) > 1:
                dup_ids.extend(m["id"] for m in members[1:])

        if dry_run:
            return {"ok": True, "duplicateGroups": sum(1 for m in groups.values() if len(m) > 1),
                    "duplicates": len(dup_ids), "dryRun": True}

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        arch_dir = self.archive / f"duplicates_{stamp}"
        arch_dir.mkdir(parents=True, exist_ok=True)
        archived = 0
        remaining = []
        dup_set = set(dup_ids)
        for c in components:
            if c["id"] in dup_set:
                src = self.root / c.get("sourceFile", "")
                if src.exists():
                    try:
                        shutil.move(str(src), str(arch_dir / src.name))
                    except Exception:  # noqa: BLE001
                        pass
                archived += 1
            else:
                remaining.append(c)
        manifest["components"] = remaining
        self._write_manifest(manifest)
        return {"ok": True, "archived": archived, "archiveDir": arch_dir.name, "dryRun": False}

    # ---- edits -----------------------------------------------------------
    def update_component(self, comp_id: str, patch: dict) -> dict:
        manifest = self._read_manifest()
        comp = next((c for c in manifest["components"] if c.get("id") == comp_id), None)
        if comp is None:
            return {"ok": False, "error": "Component not found."}
        for key, val in patch.items():
            if key in EDITABLE_FIELDS:
                comp[key] = val
        comp["updatedAt"] = _now()
        self._write_manifest(manifest)
        return {"ok": True, "component": comp}

    def rename_file_to_display(self, comp_id: str) -> dict:
        """Explicit action: rename source (+thumb/symbol) to the display name."""
        manifest = self._read_manifest()
        comp = next((c for c in manifest["components"] if c.get("id") == comp_id), None)
        if comp is None:
            return {"ok": False, "error": "Component not found."}
        src = self.root / comp.get("sourceFile", "")
        if not src.exists():
            return {"ok": False, "error": "Source file missing."}
        new_stem = _slug(comp.get("displayName", src.stem))
        new_src = src.with_name(new_stem + src.suffix)
        if new_src.exists() and new_src != src:
            return {"ok": False, "error": "Target filename already exists."}
        src.rename(new_src)
        comp["sourceFile"] = self._rel(new_src)
        # move symbol if present
        if comp.get("symbolFile"):
            old_sym = self.root / comp["symbolFile"]
            if old_sym.exists():
                new_sym = old_sym.with_name(new_stem + SYMBOL_SUFFIX)
                old_sym.rename(new_sym)
                comp["symbolFile"] = self._rel(new_sym)
        comp["updatedAt"] = _now()
        self._write_manifest(manifest)
        # thumbnail will refresh on next Rebuild Thumbnails
        return {"ok": True, "component": comp}

    # ---- symbol generation (Phase 3) -------------------------------------
    def generate_symbol(self, comp_id: str) -> dict:
        manifest = self._read_manifest()
        comp = next((c for c in manifest["components"] if c.get("id") == comp_id), None)
        if comp is None:
            return {"ok": False, "error": "Component not found."}
        src = self.root / comp.get("sourceFile", "")
        stem = src.stem if src.name else _slug(comp.get("displayName", "component"))
        svg = generate_symbol_svg(comp)
        sym_path = (self.components / comp.get("category", "custom") / f"{stem}{SYMBOL_SUFFIX}")
        sym_path.parent.mkdir(parents=True, exist_ok=True)
        sym_path.write_text(svg, encoding="utf-8")
        comp["symbolFile"] = self._rel(sym_path)
        comp["updatedAt"] = _now()
        self._write_manifest(manifest)
        return {"ok": True, "symbolFile": comp["symbolFile"]}

    # ---- read ------------------------------------------------------------
    def load(self) -> dict:
        self.ensure()
        manifest = self._read_manifest()
        comps = manifest["components"]
        counts: dict[str, int] = {}
        for c in comps:
            counts[c.get("category", "custom")] = counts.get(c.get("category", "custom"), 0) + 1
        categories = [{"id": cid, "label": category_default(cid).label, "count": counts.get(cid, 0)}
                      for cid in LIBRARY_CATEGORIES]
        return {
            "ok": True,
            "version": MANIFEST_VERSION,
            "components": comps,
            "categories": categories,
            "counts": {
                "total": len(comps),
                "favorites": sum(1 for c in comps if c.get("favorite")),
                "needsReview": sum(1 for c in comps if c.get("needsReview")),
            },
            "connectorStyles": self._read_connectors(),
        }

    def _read_connectors(self) -> dict:
        try:
            return json.loads(self.connectors_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return connector_styles_payload()

    # ---- add file --------------------------------------------------------
    def add_file(self, category: str, filename: str, data: bytes) -> dict:
        """Save an uploaded file into components/<category>/ then refresh it in."""
        self.ensure()
        cat = category if category in LIBRARY_CATEGORIES else "custom"
        dest_dir = self.components / cat
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = _slug(Path(filename).stem) + Path(filename).suffix.lower()
        dest = dest_dir / safe
        i = 1
        while dest.exists():
            dest = dest_dir / f"{_slug(Path(filename).stem)}-{i}{Path(filename).suffix.lower()}"
            i += 1
        dest.write_bytes(data)
        self.refresh()
        return {"ok": True, "saved": self._rel(dest)}

    def resolve_asset(self, rel: str) -> Path | None:
        """Path-traversal-safe resolution of a library-relative asset path."""
        target = (self.root / rel).resolve()
        if self.root.resolve() not in target.parents and target != self.root.resolve():
            return None
        return target if target.exists() else None
