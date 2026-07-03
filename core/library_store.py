"""core/library_store.py — local component-library storage.

The component library is a LOCAL/private store under .docs/library (gitignored).
It is seeded (imported) from the unzipped Singh360_Component_Library_Seed folder
and read by the editor's Component Library panel. Extracted/reference-derived
images stay local and are never committed.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


class LibraryStore:
    def __init__(self, docs_dir: Path, repo_root: Path) -> None:
        self.dir = docs_dir / "library"
        self.assets = self.dir / "assets"
        self.seed = repo_root / "Singh360_Component_Library_Seed" / "library"
        self.index_path = self.dir / "library.json"

    # ---- filesystem helpers -------------------------------------------------
    def ensure(self) -> None:
        for sub in ("assets/components", "assets/thumbnails", "assets/workbook_images", "assets/reference_pages", "staging"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index(self._empty_index())

    def _empty_index(self) -> dict:
        return {"schemaVersion": "0.1", "connectorStyles": [], "symbols": [], "components": [], "referencePages": [], "stats": {}}

    def _write_index(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
        data = self.load()
        return {"ok": True, "filesCopied": copied, "componentCount": len(data.get("components", []))}

    # ---- read/write ---------------------------------------------------------
    def load(self) -> dict:
        self.ensure()
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = self._empty_index()
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

    ALLOWED_FIELDS = {"displayName", "shortName", "category", "partNumber", "aliases", "tags", "notes",
                      "defaultLabel", "labelPosition", "labelLinked", "status"}

    def update_component(self, comp_id: str, patch: dict) -> dict | None:
        data = self.load()
        for c in data.get("components", []):
            if c.get("id") == comp_id:
                for k, v in patch.items():
                    if k in self.ALLOWED_FIELDS:
                        c[k] = v
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

    # Keyword → category rules are defined in core.library_taxonomy (canonical).

    def auto_categorize(self) -> dict:
        """Bucket components using the canonical EMS/RDM taxonomy and, where
        confident (part numbers, logos), canonicalize the display name. Never
        touches user-curated items, and never deletes files. Marks unknowns as
        'review' / status 'needs-review'."""
        from core.library_taxonomy import classify

        data = self.load()
        changed = 0
        for c in data.get("components", []):
            if c.get("curated") is True:
                continue
            w = c.get("defaultWidth") or c.get("width") or 0
            h = c.get("defaultHeight") or c.get("height") or 0
            aspect = (w / h) if (w and h) else None
            cat, canon = classify(
                str(c.get("displayName", "")),
                str(c.get("shortName", "")),
                str(c.get("partNumber", "")),
                aspect,
            )
            touched = False
            if (c.get("category") or "").lower() != cat:
                c["category"] = cat
                touched = True
            if canon and c.get("displayName") != canon:
                c["displayName"] = canon
                touched = True
            if cat == "review":
                if c.get("status") != "needs-review":
                    c["status"] = "needs-review"
                    touched = True
            if touched:
                changed += 1
        if changed:
            self.save(data)
        return {"ok": True, "changed": changed, "total": len(data.get("components", []))}
