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


# Legacy folder (`.docs/library/assets/components/<cat>`) -> V2 canonical folder.
LEGACY_CATEGORY_MAP = {
    "alarm": "alarms_safety",
    "alarms_safety": "alarms_safety",
    "controllers": "controllers",
    "custom": "custom",
    "electrical": "electrical_power",
    "electrical_power": "electrical_power",
    "equipment": "custom",
    "expansion_modules": "expansion_modules",
    "hvac": "hvac",
    "legends": "symbols_markers",
    "lighting": "lighting",
    "logos": "logos",
    "network": "network_data",
    "network_data": "network_data",
    "panel": "panels_enclosures",
    "panels_enclosures": "panels_enclosures",
    "rdm_layout_editor": "custom",
    "refrigeration": "refrigeration",
    "sensors_transducers": "sensors_transducers",
    "symbol": "symbols_markers",
    "symbols_markers": "symbols_markers",
    "uncategorized": "custom",
}

# Bulk symbol generation never overwrites real logos/reference pages with a
# generated box — they stay as their source image.
SYMBOL_SKIP_CATEGORIES = {"logos", "reference_pages"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LibraryV2:
    def __init__(self, docs_dir: Path) -> None:
        self.docs = Path(docs_dir)
        self.root = self.docs / "library"
        self.components = self.root / "components"
        self.symbols = self.root / "symbols"
        self.thumbnails = self.root / "thumbnails"
        self.manifest_path = self.root / "manifest.json"
        self.aliases_path = self.root / "aliases.json"
        self.connectors_path = self.root / "connector_styles.json"
        self.archive = self.docs / "archive"
        self.projects = self.docs / "projects"
        self.exports = self.docs / "exports"

    # ---- scaffolding -----------------------------------------------------
    def ensure(self) -> None:
        for top in (self.projects, self.exports, self.archive, self.components, self.symbols, self.thumbnails):
            top.mkdir(parents=True, exist_ok=True)
        for cat in LIBRARY_CATEGORIES:
            (self.components / cat).mkdir(parents=True, exist_ok=True)
            (self.symbols / cat).mkdir(parents=True, exist_ok=True)
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

    def _approved_symbol_for(self, category: str, source_file_rel: str) -> str:
        """Return library-relative approved symbol path for a source file if present.

        Approved symbols live under `.docs/library/symbols/<category>/<stem>.svg`.
        """
        stem = Path(source_file_rel).stem
        candidate = self.symbols / category / f"{stem}.svg"
        if candidate.exists():
            return self._rel(candidate)
        return ""

    def _sync_symbol_links(self, manifest: dict) -> None:
        """Re-link manifest entries to approved symbols without generating any."""
        for comp in manifest.get("components", []):
            category = comp.get("category", "custom")
            source_rel = comp.get("sourceFile", "")
            approved = self._approved_symbol_for(category, source_rel)
            comp["symbolFile"] = approved
            comp["symbolStatus"] = "built" if approved else "not_built"

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
            self._sync_symbol_links(manifest)
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
        source_rel = self._rel(path)
        approved_symbol = self._approved_symbol_for(category, source_rel)
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
            "sourceFile": source_rel,
            "thumbnailFile": "",
            "symbolFile": approved_symbol,
            "symbolStatus": "built" if approved_symbol else "not_built",
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
            "source": {"file": source_rel},
            "createdAt": _now(),
        }

    # ---- thumbnails ------------------------------------------------------
    def rebuild_thumbnails(self, size: int = 256) -> dict:
        """Delete all thumbnails and regenerate from the manifest only.

        Writes ONLY into thumbnails/ — never creates a component source file.
        Component count is invariant across a rebuild.
        """
        self.ensure()
        self._clear_thumbnails()
        self.thumbnails.mkdir(parents=True, exist_ok=True)
        manifest = self._read_manifest()
        rebuilt = missing = 0
        for comp in manifest["components"]:
            src = self.root / comp.get("sourceFile", "")
            if not src.exists():
                missing += 1
                comp["thumbnailFile"] = ""
                continue
            thumb_rel = self._make_thumbnail(comp, src, size)
            comp["thumbnailFile"] = thumb_rel or ""
            if thumb_rel:
                rebuilt += 1
        self._write_manifest(manifest)
        return {"ok": True, "rebuilt": rebuilt, "missingSource": missing}

    def _clear_thumbnails(self) -> None:
        """Best-effort clear of the thumbnails dir (OneDrive/Windows can lock it)."""
        if not self.thumbnails.exists():
            return
        for p in sorted(self.thumbnails.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    p.rmdir()
            except Exception:  # noqa: BLE001
                pass

    def _make_thumbnail(self, comp: dict, src: Path, size: int) -> str | None:
        """Write a thumbnail into thumbnails/<cat>/ and return its library-relative
        path (or None). SVG is copied as vector; PDF is rendered first; raster
        images become .webp. Never points at a non-existent file.
        """
        cat = comp.get("category", "custom")
        out_dir = self.thumbnails / cat
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(comp.get("sourceFile", src.name)).stem
        ext = src.suffix.lower()

        # SVG: copy the vector as-is so the browser renders it directly.
        if ext == ".svg":
            dest = out_dir / f"{stem}.svg"
            try:
                shutil.copyfile(src, dest)
                return self._rel(dest)
            except Exception:  # noqa: BLE001
                return None

        # PDF: render the first page to a PNG, then thumbnail that.
        raster = src
        if ext == ".pdf":
            rendered = self._render_pdf_first_page(src, out_dir, stem)
            if rendered is None:
                return None
            raster = rendered

        if Image is None:
            return None
        dest = out_dir / f"{stem}.webp"
        try:
            with Image.open(raster) as im:
                im = im.convert("RGBA")
                im.thumbnail((size, size))
                bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                bg.alpha_composite(im)
                bg.convert("RGB").save(dest, "WEBP", quality=86)
            return self._rel(dest)
        except Exception:  # noqa: BLE001
            return None

    def _render_pdf_first_page(self, pdf: Path, out_dir: Path, stem: str) -> Path | None:
        """Render page 1 of a PDF to PNG (via PyMuPDF) for thumbnailing/insertion."""
        try:
            from core.pdf_renderer import render_page_to_png, is_available
        except Exception:  # noqa: BLE001
            return None
        if not is_available():
            return None
        png = out_dir / f"{stem}.pdfpage.png"
        result = render_page_to_png(pdf, 0, png, dpi=150)
        return png if result.get("ok") and png.exists() else None

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
        _ = comp_id
        return {
            "ok": False,
            "error": "Symbol Builder workflow not yet enabled. Open Component Builder.",
        }

    def generate_all_symbols(self, skip_categories: set[str] | None = None) -> dict:
        _ = skip_categories
        return {
            "ok": False,
            "error": "Symbol Builder workflow not yet enabled. Open Component Builder.",
            "generated": 0,
            "skipped": 0,
            "clearedSymbols": 0,
        }

    # ---- legacy migration (Phase 1/2) ------------------------------------
    @property
    def legacy_root(self) -> Path:
        return self.root / "assets" / "components"

    def _iter_legacy_sources(self):
        """Yield (top_folder, path) for legacy source files, skipping thumbnails
        and generated symbols. Category = the top-level legacy folder name."""
        lr = self.legacy_root
        if not lr.exists():
            return
        for cat_dir in sorted(lr.iterdir()):
            if not cat_dir.is_dir() or cat_dir.name.lower() in ("thumbnails", "rendered", "originals"):
                continue
            for p in sorted(cat_dir.rglob("*")):
                if not p.is_file() or p.name.startswith("."):
                    continue
                if "thumbnails" in {part.lower() for part in p.parts}:
                    continue
                if p.name.lower().endswith(SYMBOL_SUFFIX):
                    continue
                if p.suffix.lower() not in SOURCE_EXTS:
                    continue
                yield cat_dir.name.lower(), p

    def has_legacy(self) -> bool:
        for _ in self._iter_legacy_sources():
            return True
        return False

    def _existing_component_hashes(self) -> set[str]:
        hashes: set[str] = set()
        for cat in LIBRARY_CATEGORIES:
            d = self.components / cat
            if not d.exists():
                continue
            for p in d.rglob("*"):
                if p.is_file() and p.suffix.lower() in SOURCE_EXTS and not p.name.lower().endswith(SYMBOL_SUFFIX):
                    try:
                        hashes.add(self.content_hash(p))
                    except Exception:  # noqa: BLE001
                        pass
        return hashes

    def migrate_legacy(self, dry_run: bool = True, *, rebuild_thumbnails: bool = True,
                       generate_symbols: bool = False) -> dict:
        """Copy legacy `assets/components/<cat>` files into the V2 root.

        Never deletes legacy files; skips exact-SHA256 duplicates (already in V2
        or repeated within the legacy set). Archives the current manifest before
        applying. Dry-run returns a preview.
        """
        self.ensure()
        if not self.has_legacy():
            return {"ok": True, "legacyFound": 0, "note": "No legacy assets/components found."}

        seen = self._existing_component_hashes()
        legacy_counts: dict[str, int] = {}
        target_counts: dict[str, int] = {}
        plan: list[tuple[Path, str]] = []
        skipped_dupes = 0
        for top, path in self._iter_legacy_sources():
            legacy_counts[top] = legacy_counts.get(top, 0) + 1
            dest_cat = LEGACY_CATEGORY_MAP.get(top, "custom")
            try:
                h = self.content_hash(path)
            except Exception:  # noqa: BLE001
                continue
            if h in seen:
                skipped_dupes += 1
                continue
            seen.add(h)
            plan.append((path, dest_cat))
            target_counts[dest_cat] = target_counts.get(dest_cat, 0) + 1

        if dry_run:
            return {
                "ok": True, "dryRun": True,
                "legacyFound": sum(legacy_counts.values()),
                "legacyCategories": legacy_counts,
                "willCopy": len(plan),
                "willSkipDuplicates": skipped_dupes,
                "targetCategories": target_counts,
            }

        # Archive current manifest before mutating.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.archive.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            shutil.copyfile(self.manifest_path,
                            self.archive / f"library_manifest_before_migration_{stamp}.json")

        copied = 0
        for path, dest_cat in plan:
            dest_dir = self.components / dest_cat
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / path.name  # preserve readable filename
            i = 1
            while dest.exists():
                dest = dest_dir / f"{path.stem}-{i}{path.suffix}"
                i += 1
            try:
                shutil.copyfile(path, dest)
                copied += 1
            except Exception:  # noqa: BLE001
                pass

        refreshed = self.refresh()
        result = {
            "ok": True, "dryRun": False, "copied": copied,
            "skippedDuplicates": skipped_dupes,
            "legacyCategories": legacy_counts, "targetCategories": target_counts,
            "refresh": refreshed,
        }
        if rebuild_thumbnails:
            result["thumbnails"] = self.rebuild_thumbnails()
        if generate_symbols:
            result["symbols"] = {
                "ok": False,
                "error": "Symbol Builder workflow not yet enabled. Open Component Builder.",
            }
        return result

    # ---- physical duplicate cleanup (Phase 5) ----------------------------
    def clean_physical_duplicates(self, dry_run: bool = True) -> dict:
        """Scan components/<cat> for byte-identical files; keep one, archive rest."""
        self.ensure()
        groups: dict[str, list[Path]] = {}
        for cat in LIBRARY_CATEGORIES:
            d = self.components / cat
            if not d.exists():
                continue
            for p in sorted(d.iterdir()):
                if not p.is_file() or p.suffix.lower() not in SOURCE_EXTS:
                    continue
                if p.name.lower().endswith(SYMBOL_SUFFIX):
                    continue
                try:
                    groups.setdefault(self.content_hash(p), []).append(p)
                except Exception:  # noqa: BLE001
                    pass
        dup_groups = {h: ps for h, ps in groups.items() if len(ps) > 1}
        total_dupes = sum(len(ps) - 1 for ps in dup_groups.values())

        if dry_run:
            return {"ok": True, "dryRun": True, "duplicateGroups": len(dup_groups),
                    "duplicates": total_dupes}

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        arch_dir = self.archive / f"library_duplicates_{stamp}"
        arch_dir.mkdir(parents=True, exist_ok=True)
        archived = 0
        for ps in dup_groups.values():
            keeper = self._pick_keeper(ps)
            for p in ps:
                if p == keeper:
                    continue
                try:
                    dest = arch_dir / p.name
                    j = 1
                    while dest.exists():
                        dest = arch_dir / f"{p.stem}-{j}{p.suffix}"
                        j += 1
                    shutil.move(str(p), str(dest))
                    archived += 1
                except Exception:  # noqa: BLE001
                    pass
        self._prune_missing()
        result = {"ok": True, "dryRun": False, "archived": archived, "archiveDir": arch_dir.name}
        result["thumbnails"] = self.rebuild_thumbnails()
        return result

    @staticmethod
    def _pick_keeper(paths: list[Path]) -> Path:
        """Prefer a readable filename (no hash suffix) and higher resolution."""
        def score(p: Path) -> tuple:
            name = p.stem
            has_hash = 1 if re.search(r"_[0-9a-f]{8,}_|_[0-9a-f]{8,}$", name) else 0
            res = 0
            if Image is not None and p.suffix.lower() in IMAGE_EXTS and p.suffix.lower() != ".svg":
                try:
                    with Image.open(p) as im:
                        res = im.size[0] * im.size[1]
                except Exception:  # noqa: BLE001
                    res = 0
            # Lower has_hash is better; higher res better; shorter name better.
            return (has_hash, -res, len(name))
        return sorted(paths, key=score)[0]

    def _prune_missing(self) -> dict:
        """Drop manifest components whose source file no longer exists."""
        manifest = self._read_manifest()
        before = len(manifest["components"])
        manifest["components"] = [
            c for c in manifest["components"] if (self.root / c.get("sourceFile", "")).exists()
        ]
        removed = before - len(manifest["components"])
        self._write_manifest(manifest)
        return {"ok": True, "removed": removed}

    def archive_fake_symbols(self, dry_run: bool = True) -> dict:
        """Move generated `*.symbol.svg` under components/ to archive and clear
        manifest references, marking symbolStatus=not_built.
        """
        self.ensure()
        fake_paths = sorted(self.components.rglob(f"*{SYMBOL_SUFFIX}"))
        if dry_run:
            return {"ok": True, "dryRun": True, "fakeSymbols": len(fake_paths)}

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target = self.archive / f"fake_symbols_{stamp}"
        target.mkdir(parents=True, exist_ok=True)

        moved = 0
        for src in fake_paths:
            rel = src.relative_to(self.components)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(dst))
                moved += 1
            except Exception:  # noqa: BLE001
                pass

        manifest = self._read_manifest()
        cleared = 0
        for c in manifest.get("components", []):
            if c.get("symbolFile", "").endswith(SYMBOL_SUFFIX):
                c["symbolFile"] = ""
                c["symbolStatus"] = "not_built"
                c["updatedAt"] = _now()
                cleared += 1
        self._write_manifest(manifest)
        return {
            "ok": True,
            "dryRun": False,
            "moved": moved,
            "manifestCleared": cleared,
            "archiveDir": target.name,
        }

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
            "hasLegacy": self.has_legacy(),
            "libraryRoot": str(self.components),
            "counts": {
                "total": len(comps),
                "favorites": sum(1 for c in comps if c.get("favorite")),
                "needsReview": sum(1 for c in comps if c.get("needsReview")),
                "withSymbol": sum(
                    1
                    for c in comps
                    if c.get("symbolFile") and (self.root / c.get("symbolFile", "")).exists()
                ),
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
