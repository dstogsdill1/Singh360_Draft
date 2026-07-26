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
    "data",
    "sources/workbook",
    "sources/spreadsheets",
    "sources/csv",
    "sources/pdf",
    "sources/images",
    "sources/documents",
    "sources/other",
    "sources/vsdx",
    "assets/images",
    "assets/images/excel",
    "assets/underlays",
    "assets/screenshots",
    "exports/pdf",
    "exports/workbook",
    "exports/package",
    "backups",
    "debug",
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

        target = project_dir / "project.json"
        # Snapshot the prior project.json before overwriting it (keep last 20) so a
        # bad save or accidental change can always be recovered.
        self._backup_before_write(project_dir, target)

        target.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # S360 INCREMENTAL SAFETY V12
        # The complete prior project.json is already backed up above. Writing a
        # separate snapshot for every page on every autosave created hundreds
        # of OneDrive filesystem writes for large packages. Page snapshots are
        # still created explicitly before page rebuild/recovery operations.
        # Migrate: drop legacy flat file once saved into the folder structure.
        legacy = self.legacy_json(project_id)
        try:
            if legacy.is_file():
                legacy.unlink()
        except OSError:
            pass
        return project_dir / "project.json"

    # ── backups / recovery ───────────────────────────────────────────────
    _MAX_BACKUPS = 20

    def backups_dir(self, project_dir: Path) -> Path:
        p = project_dir / "backups"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def page_snapshots_root(self, project_dir: Path) -> Path:
        p = project_dir / "page_snapshots"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _backup_before_write(self, project_dir: Path, target: Path) -> Path | None:
        """Copy the current project.json to backups/project_<ts>.json (keep 20)."""
        if not target.is_file():
            return None
        backups = self.backups_dir(project_dir)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]
        dest = backups / f"project_{stamp}.json"
        try:
            dest.write_bytes(target.read_bytes())
        except OSError:
            return None
        self._prune_backups(backups)
        return dest

    def _prune_backups(self, backups: Path) -> None:
        snaps = sorted(backups.glob("project_*.json"), key=lambda p: p.name)
        excess = len(snaps) - self._MAX_BACKUPS
        for old in snaps[: max(0, excess)]:
            try:
                old.unlink()
            except OSError:
                pass

    def _safe_page_id(self, page_id: str) -> str | None:
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", page_id or ""):
            return page_id
        return None

    def _page_counts(self, page: dict[str, Any]) -> dict[str, int]:
        canvas = page.get("canvasObjects") if isinstance(page.get("canvasObjects"), list) else []
        blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
        connectors = 0
        for obj in canvas:
            if not isinstance(obj, dict):
                continue
            typ = str(obj.get("type") or obj.get("connectorKind") or "").lower()
            if typ == "connector" or obj.get("connectorKind") or "pointsData" in obj:
                connectors += 1
        table_blocks = [b for b in blocks if isinstance(b, dict) and b.get("type") in {"table", "matrix"}]
        table_cells = 0
        for block in table_blocks:
            rows = block.get("rows") if isinstance(block.get("rows"), list) else []
            table_cells += sum(len(r) for r in rows if isinstance(r, list))
            headers = block.get("headers") if isinstance(block.get("headers"), list) else []
            table_cells += len(headers)
        return {
            "canvasObjects": len(canvas),
            "connectors": connectors,
            "tableBlocks": len(table_blocks),
            "tableCells": table_cells,
        }

    def write_page_snapshots(self, project_dir: Path, data: dict[str, Any]) -> None:
        """Write one compact-but-restorable snapshot per page after each save."""
        pages = data.get("pages") if isinstance(data.get("pages"), list) else []
        if not pages:
            return
        root = self.page_snapshots_root(project_dir)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = self._safe_page_id(str(page.get("id") or ""))
            if not page_id:
                continue
            page_dir = root / page_id
            page_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "projectId": data.get("id", ""),
                "pageId": page_id,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sheetTitle": page.get("sheetTitle", ""),
                "sheetCode": page.get("displaySheetCode") or page.get("sheetCode") or "",
                "counts": self._page_counts(page),
                "page": page,
            }
            try:
                (page_dir / f"page_{stamp}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self._prune_page_snapshots(page_dir)
            except OSError:
                continue

    def _prune_page_snapshots(self, page_dir: Path) -> None:
        snaps = sorted(page_dir.glob("page_*.json"), key=lambda p: p.name)
        excess = len(snaps) - self._MAX_BACKUPS
        for old in snaps[: max(0, excess)]:
            try:
                old.unlink()
            except OSError:
                pass

    def list_page_snapshots(self, project_id: str) -> list[dict[str, Any]]:
        d = self.find_dir(project_id)
        if not d:
            return []
        root = d / "page_snapshots"
        if not root.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for p in sorted(root.glob("*/page_*.json"), key=lambda x: x.name, reverse=True):
            try:
                payload = json.loads(p.read_text("utf-8"))
                stat = p.stat()
            except (json.JSONDecodeError, OSError):
                continue
            out.append({
                "name": p.name,
                "pageId": payload.get("pageId", p.parent.name),
                "savedAt": payload.get("timestamp") or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sheetTitle": payload.get("sheetTitle", ""),
                "sheetCode": payload.get("sheetCode", ""),
                "counts": payload.get("counts", {}),
                "sizeBytes": stat.st_size,
            })
        return out

    def restore_page_snapshot(self, project_id: str, page_id: str, snapshot_name: str) -> dict[str, Any] | None:
        safe_page_id = self._safe_page_id(page_id)
        if not safe_page_id:
            return None
        if not re.fullmatch(r"page_[0-9]{8}-[0-9]{6}-[0-9]{1,6}\.json", snapshot_name or ""):
            return None
        d = self.find_dir(project_id)
        if not d:
            return None
        src = d / "page_snapshots" / safe_page_id / snapshot_name
        if not src.is_file():
            return None
        try:
            payload = json.loads(src.read_text("utf-8"))
            page = payload.get("page")
            data = self.load(project_id)
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(page, dict) or not isinstance(data, dict):
            return None
        pages = data.get("pages") if isinstance(data.get("pages"), list) else []
        replaced = False
        next_pages = []
        for existing in pages:
            if isinstance(existing, dict) and existing.get("id") == safe_page_id:
                next_pages.append(page)
                replaced = True
            else:
                next_pages.append(existing)
        if not replaced:
            return None
        data["pages"] = next_pages
        return data if self.save(project_id, data) else None

    def save_pre_rebuild_page_snapshot(
        self, project_id: str, page_id: str, page: dict[str, Any]
    ) -> str | None:
        """Persist a page snapshot immediately before a toolbar rebuild."""
        safe_page_id = self._safe_page_id(page_id)
        if not safe_page_id or not isinstance(page, dict):
            return None
        d = self.find_dir(project_id)
        if not d:
            return None
        root = self.page_snapshots_root(d)
        page_dir = root / safe_page_id
        page_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]
        name = f"page_{stamp}.json"
        payload = {
            "projectId": project_id,
            "pageId": safe_page_id,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sheetTitle": page.get("sheetTitle", ""),
            "sheetCode": page.get("displaySheetCode") or page.get("sheetCode") or "",
            "counts": self._page_counts(page),
            "page": page,
            "rebuildBackup": True,
        }
        try:
            (page_dir / name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._prune_page_snapshots(page_dir)
        except OSError:
            return None
        return name

    def list_backups(self, project_id: str) -> list[dict[str, Any]]:
        """Return newest-first backup snapshots for a project."""
        d = self.find_dir(project_id)
        if not d:
            return []
        backups = d / "backups"
        if not backups.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for p in sorted(backups.glob("project_*.json"), key=lambda x: x.name, reverse=True):
            try:
                stat = p.stat()
            except OSError:
                continue
            out.append(
                {
                    "name": p.name,
                    "savedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "sizeBytes": stat.st_size,
                }
            )
        return out

    def restore_backup(self, project_id: str, backup_name: str) -> dict[str, Any] | None:
        """Restore a named backup as the live project.json (backing up current first)."""
        if not re.fullmatch(r"project_[0-9]{8}-[0-9]{6}-[0-9]{1,6}\.json", backup_name or ""):
            return None
        d = self.find_dir(project_id)
        if not d:
            return None
        src = d / "backups" / backup_name
        if not src.is_file():
            return None
        try:
            data = json.loads(src.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        # Snapshot current, then write the restored copy through the normal path.
        return data if self.save(project_id, data) else None

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
