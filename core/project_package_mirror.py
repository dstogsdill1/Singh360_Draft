"""Atomic, one-way project package export for external mirror folders."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .template_platform import TemplatePlatformError, sha256_file


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _move_directory(source: Path, destination: Path) -> None:
    """Move a complete package, with a OneDrive-compatible verified fallback."""
    try:
        os.replace(source, destination)
        return
    except PermissionError:
        pass
    source_paths = {
        str(path.relative_to(source))
        for path in source.rglob("*") if path.is_file()
    }
    if destination.exists():
        for path in destination.rglob("*"):
            if path.is_file() and str(path.relative_to(destination)) not in source_paths:
                path.unlink()
    else:
        destination.mkdir(parents=True)
    manifest = source / "project_manifest.json"
    for path in (item for item in source.rglob("*") if item.is_file()):
        if path == manifest:
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    if manifest.is_file():
        shutil.copy2(manifest, destination / manifest.name)
    source_files = {
        str(path.relative_to(source)): sha256_file(path)
        for path in source.rglob("*") if path.is_file()
    }
    destination_files = {
        str(path.relative_to(destination)): sha256_file(path)
        for path in destination.rglob("*") if path.is_file()
    }
    if source_files != destination_files:
        shutil.rmtree(destination, ignore_errors=True)
        raise TemplatePlatformError("External package promotion verification failed.")
    shutil.rmtree(source, ignore_errors=True)


def export_project_mirror(
    project_dir: Path,
    project: dict[str, Any],
    destination_root: Path,
    structure_zip: Path,
) -> dict[str, Any]:
    project_dir = Path(project_dir).resolve()
    destination_root = Path(destination_root).expanduser().resolve()
    if not destination_root.is_dir():
        raise TemplatePlatformError(f"External mirror folder is unavailable: {destination_root}")
    if not structure_zip.is_file():
        raise TemplatePlatformError("External package structure template is missing.")

    package_name = f"{project.get('id')} - {project.get('metadata', {}).get('projectName', 'Singh360 Project')}"
    package_name = "".join(ch if ch.isalnum() or ch in " ._-" else "-" for ch in package_name).strip()
    final = destination_root / package_name
    temp = Path(tempfile.mkdtemp(prefix=f".{package_name}.", dir=destination_root))
    backup: Path | None = None
    try:
        with zipfile.ZipFile(structure_zip) as bundle:
            for member in bundle.infolist():
                parts = Path(member.filename).parts
                relative = Path(*parts[1:]) if len(parts) > 1 else Path()
                if not relative.parts or any(part == ".." for part in relative.parts):
                    continue
                target = temp / relative
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)

        mapping = {
            project_dir / "project.json": temp / "01_Project_Admin" / "project.json",
            project_dir / "source_library.json": temp / "02_Source_Library" / "source_library.json",
            project_dir / "data" / "workbook.json": temp / "03_Data_Workspace" / "workbook.json",
        }
        workbook = Path(str(project.get("workbookSync", {}).get("workbook") or ""))
        if workbook.is_file():
            mapping[workbook] = temp / "03_Data_Workspace" / workbook.name
        for source, target in mapping.items():
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        for folder_name, destination_name in (
            ("sources", "02_Source_Library/files"),
            ("assets", "04_Drawing_Assets"),
            ("exports", "06_Exports"),
        ):
            source = project_dir / folder_name
            if source.is_dir():
                shutil.copytree(source, temp / destination_name, dirs_exist_ok=True)

        package_zip = temp / "06_Exports" / "project_package.zip"
        package_zip.parent.mkdir(parents=True, exist_ok=True)
        shutil.make_archive(str(package_zip.with_suffix("")), "zip", project_dir)
        files = []
        for path in sorted(item for item in temp.rglob("*") if item.is_file()):
            files.append({
                "path": str(path.relative_to(temp)).replace("\\", "/"),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            })
        manifest = {
            "schemaVersion": 1,
            "projectId": project.get("id"),
            "projectName": project.get("metadata", {}).get("projectName"),
            "exportedAt": _utcnow(),
            "sourceOfTruth": "local-singh360-project-package",
            "oneWayExport": True,
            "files": files,
        }
        manifest_path = temp / "project_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest_hash = sha256_file(manifest_path)

        if final.exists():
            backup = destination_root / f"{package_name}.previous-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            _move_directory(final, backup)
        _move_directory(temp, final)
        return {
            "path": str(final), "manifestPath": str(final / "project_manifest.json"),
            "manifestSha256": manifest_hash, "fileCount": len(files),
            "previousPackage": str(backup) if backup else "", "exportedAt": _utcnow(),
        }
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        if backup and backup.exists() and not final.exists():
            _move_directory(backup, final)
        raise
