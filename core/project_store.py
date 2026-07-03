"""core/project_store.py — local project package storage.

Organizes each project into a clear, discoverable folder under
``.docs/projects/<slug>__<id>/`` with sources/assets/exports/debug subfolders.
Loads legacy ``.docs/<id>.json`` projects for backward compatibility and
migrates them on the next save.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SUBFOLDERS = (
    "sources/workbook",
    "sources/csv",
    "sources/pdf",
    "sources/vsdx",
    "assets/images",
    "assets/images/excel",
    "assets/underlays",
    "assets/screenshots",
    "exports/pdf",
    "exports/package",
    "debug/screenshots",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    """Windows-safe folder slug."""
    s = re.sub(r"[^A-Za-z0-9._ -]+", "", (name or "").strip())
    s = re.sub(r"[ _]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    return (s or "project")[:60]


class ProjectStore:
    def __init__(self, docs_dir: Path):
        self.docs = Path(docs_dir)
        self.projects_dir = self.docs / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    # ── paths ────────────────────────────────────────────────────────────
    def legacy_json(self, project_id: str) -> Path:
        return self.docs / f"{project_id}.json"

    def find_dir(self, project_id: str) -> Path | None:
        for d in self.projects_dir.glob(f"*__{project_id}"):
            if d.is_dir():
                return d
        return None

    def _display_name(self, data: dict[str, Any], project_id: str) -> str:
        meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
        return (
            data.get("projectDisplayName")
            or meta.get("projectName")
            or data.get("sourceWorkbookName")
            or meta.get("sourceFile")
            or project_id
        )

    def dir_for(self, project_id: str, data: dict[str, Any] | None = None) -> Path:
        existing = self.find_dir(project_id)
        if existing:
            return existing
        slug = slugify(self._display_name(data or {}, project_id))
        return self.projects_dir / f"{slug}__{project_id}"

    def ensure_folders(self, project_dir: Path) -> None:
        for sub in _SUBFOLDERS:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)

    def assets_images_dir(self, project_id: str, data: dict[str, Any] | None = None) -> Path:
        d = self.dir_for(project_id, data)
        p = d / "assets" / "images"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def assets_excel_dir(self, project_id: str, data: dict[str, Any] | None = None) -> Path:
        d = self.dir_for(project_id, data)
        p = d / "assets" / "images" / "excel"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def sources_dir(self, project_id: str, kind: str, data: dict[str, Any] | None = None) -> Path:
        d = self.dir_for(project_id, data)
        p = d / "sources" / kind
        p.mkdir(parents=True, exist_ok=True)
        return p

    def exports_pdf_dir(self, project_id: str, data: dict[str, Any] | None = None) -> Path:
        d = self.dir_for(project_id, data)
        p = d / "exports" / "pdf"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── read / write ─────────────────────────────────────────────────────
    def read_path(self, project_id: str) -> Path | None:
        d = self.find_dir(project_id)
        if d and (d / "project.json").is_file():
            return d / "project.json"
        legacy = self.legacy_json(project_id)
        if legacy.is_file():
            return legacy
        return None

    def load(self, project_id: str) -> dict[str, Any] | None:
        p = self.read_path(project_id)
        if not p:
            return None
        return json.loads(p.read_text("utf-8"))

    def save(self, project_id: str, data: dict[str, Any]) -> Path:
        project_dir = self.dir_for(project_id, data)
        self.ensure_folders(project_dir)

        data["projectFolder"] = str(project_dir)
        data["projectSlug"] = project_dir.name.split("__", 1)[0]
        data["projectDisplayName"] = self._display_name(data, project_id)
        data["lastSavedAt"] = _utcnow()

        (project_dir / "project.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Migrate: drop legacy flat file once saved into the folder structure.
        legacy = self.legacy_json(project_id)
        try:
            if legacy.is_file():
                legacy.unlink()
        except OSError:
            pass
        return project_dir / "project.json"

    def rename(self, project_id: str, new_name: str) -> Path:
        """Rename the display name and move the folder to the new slug."""
        data = self.load(project_id)
        if data is None:
            raise FileNotFoundError(project_id)
        meta = data.setdefault("metadata", {})
        meta["projectName"] = new_name
        data["projectDisplayName"] = new_name

        old_dir = self.find_dir(project_id)
        new_slug = slugify(new_name)
        new_dir = self.projects_dir / f"{new_slug}__{project_id}"
        if old_dir and old_dir.resolve() != new_dir.resolve() and not new_dir.exists():
            old_dir.rename(new_dir)
        return self.save(project_id, data)

    def list_projects(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for d in self.projects_dir.glob("*__*"):
            pj = d / "project.json"
            if not pj.is_file():
                continue
            try:
                data = json.loads(pj.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            pid = d.name.rsplit("__", 1)[-1]
            meta = data.get("metadata", {})
            out.append(
                {
                    "id": pid,
                    "projectName": meta.get("projectName") or data.get("projectDisplayName") or "Untitled Project",
                    "modified": data.get("modified", ""),
                    "folder": str(d),
                }
            )
        # legacy flat files
        for p in self.docs.glob("*.json"):
            try:
                data = json.loads(p.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            out.append(
                {
                    "id": p.stem,
                    "projectName": data.get("metadata", {}).get("projectName") or "Untitled Project",
                    "modified": data.get("modified", ""),
                    "folder": str(self.docs),
                }
            )
        return out
