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

    def find_all_dirs(self, project_id: str) -> list[Path]:
        """All folders that belong to this project ID (canonical + stale dups)."""
        return sorted(
            (d for d in self.projects_dir.glob(f"*__{project_id}") if d.is_dir()),
            key=lambda d: d.name.lower(),
        )

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
        """Rename the display name and move the folder to the new slug.

        Consolidates onto a single canonical folder for this project ID. If a
        folder with the target slug already exists for the SAME project ID it is
        reused (never duplicated); any other stale folders for this ID are moved
        aside to ``projects/_archive/`` rather than deleted.
        """
        data = self.load(project_id)
        if data is None:
            raise FileNotFoundError(project_id)
        meta = data.setdefault("metadata", {})
        meta["projectName"] = new_name
        data["projectDisplayName"] = new_name

        new_slug = slugify(new_name)
        new_dir = self.projects_dir / f"{new_slug}__{project_id}"
        existing = self.find_all_dirs(project_id)
        # The folder currently holding the freshest project.json (the one we loaded).
        source_dir = next((d for d in existing if (d / "project.json").is_file()), None)

        if not new_dir.exists():
            # Move the source folder to the new slug if we have one; else it will be created.
            if source_dir is not None and source_dir.resolve() != new_dir.resolve():
                source_dir.rename(new_dir)
        else:
            # Target slug already exists for this ID — reuse it. Copy over the
            # freshest project.json if the source differs, then archive the source.
            if source_dir is not None and source_dir.resolve() != new_dir.resolve():
                (new_dir / "project.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                self._archive_dir(source_dir)

        # Archive any remaining stale duplicates for this ID.
        for d in self.find_all_dirs(project_id):
            if d.resolve() != new_dir.resolve():
                self._archive_dir(d)

        return self.save(project_id, data)

    # ── duplicate-folder hygiene ─────────────────────────────────────────
    @property
    def archive_dir(self) -> Path:
        p = self.projects_dir / "_archive"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _archive_dir(self, folder: Path) -> Path:
        """Move a stale duplicate folder into projects/_archive/ (never delete)."""
        dest = self.archive_dir / folder.name
        n = 1
        while dest.exists():
            dest = self.archive_dir / f"{folder.name}.dup{n}"
            n += 1
        folder.rename(dest)
        return dest

    def detect_duplicate_folders(self, project_id: str) -> list[str]:
        """Return non-canonical folder paths for this project ID (excess dups)."""
        dirs = self.find_all_dirs(project_id)
        if len(dirs) <= 1:
            return []
        canonical = self.find_dir(project_id)
        return [str(d) for d in dirs if canonical and d.resolve() != canonical.resolve()]

    def archive_duplicate_folders(self, project_id: str) -> list[str]:
        """Archive all non-canonical folders for this project ID. Returns moved paths."""
        canonical = self.find_dir(project_id)
        moved: list[str] = []
        for d in self.find_all_dirs(project_id):
            if canonical and d.resolve() != canonical.resolve():
                moved.append(str(self._archive_dir(d)))
        return moved

    def list_projects(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        # Count folders per project ID so we can flag duplicates in the listing.
        id_counts: dict[str, int] = {}
        for d in self.projects_dir.glob("*__*"):
            if d.is_dir():
                pid = d.name.rsplit("__", 1)[-1]
                id_counts[pid] = id_counts.get(pid, 0) + 1
        seen: set[str] = set()
        for d in self.projects_dir.glob("*__*"):
            pj = d / "project.json"
            if not pj.is_file():
                continue
            try:
                data = json.loads(pj.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            pid = d.name.rsplit("__", 1)[-1]
            if pid in seen:
                continue  # only list the canonical (first) folder per ID
            seen.add(pid)
            meta = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
            out.append(
                {
                    "id": pid,
                    "projectName": meta.get("projectName") or data.get("projectDisplayName") or "Untitled Project",
                    "modified": data.get("modified", "") or data.get("lastSavedAt", ""),
                    "lastSavedAt": data.get("lastSavedAt", ""),
                    "folder": str(d),
                    "packageFile": data.get("drawingPackageFileName")
                    or meta.get("drawingPackageFileName")
                    or "",
                    "sourceWorkbook": data.get("sourceWorkbookName")
                    or meta.get("sourceFile")
                    or "",
                    "duplicateFolders": max(0, id_counts.get(pid, 1) - 1),
                }
            )
        # legacy flat files
        for p in self.docs.glob("*.json"):
            if p.stem in seen:
                continue
            try:
                data = json.loads(p.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            out.append(
                {
                    "id": p.stem,
                    "projectName": data.get("metadata", {}).get("projectName") or "Untitled Project",
                    "modified": data.get("modified", ""),
                    "lastSavedAt": data.get("lastSavedAt", ""),
                    "folder": str(self.docs),
                    "packageFile": data.get("drawingPackageFileName", ""),
                    "sourceWorkbook": data.get("sourceWorkbookName", ""),
                    "duplicateFolders": 0,
                }
            )
        out.sort(key=lambda r: str(r.get("modified") or r.get("lastSavedAt") or ""), reverse=True)
        return out
