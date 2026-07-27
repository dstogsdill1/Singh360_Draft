"""Project-local file explorer and workbook workspace services.

This module restores the useful, project-local parts of the historical
template-platform implementation without requiring a schema-v2 migration.
Existing project packages remain authoritative and their source files are
indexed non-destructively into a virtual folder tree.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, BinaryIO

from openpyxl import load_workbook
from werkzeug.utils import secure_filename


STANDARD_FOLDERS = [
    "Drawings",
    "Converted Schedules",
    "Survey Photos",
    "References",
    "Assets",
    "Symbol-Mapped Drawings",
    "Manual Layouts",
    "Programming",
    "Commissioning",
    "Archive",
]
SAFE_EXTENSIONS = {
    ".pdf": "pdf",
    ".png": "images",
    ".jpg": "images",
    ".jpeg": "images",
    ".webp": "images",
    ".svg": "images",
    ".xlsx": "spreadsheets",
    ".xlsm": "spreadsheets",
    ".csv": "csv",
    ".txt": "text",
    ".md": "text",
    ".json": "text",
    ".log": "text",
    ".doc": "documents",
    ".docx": "documents",
    ".rtf": "text",
    ".odt": "documents",
    ".ods": "spreadsheets",
    ".ppt": "documents",
    ".pptx": "documents",
}
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_ZIP_BYTES = 500 * 1024 * 1024
MAX_ZIP_MEMBERS = 2_000
FILE_ID_RE = re.compile(r"^[a-f0-9]{16}$")


class ProjectWorkspaceError(ValueError):
    """User-correctable project workspace error."""


class WorkbookRevisionConflict(ProjectWorkspaceError):
    """The browser tried to save an outdated workbook document."""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_virtual_path(value: str) -> str:
    raw = str(value or "").replace("\\", "/").strip("/")
    if not raw:
        return ""
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if any(
        part in {".", ".."}
        or not re.fullmatch(r'[^<>:"|?*\x00-\x1f]+', part)
        or part.endswith((".", " "))
        for part in parts
    ):
        raise ProjectWorkspaceError("The project folder path is unsafe.")
    return "/".join(parts)


def _legacy_virtual_folder(relative_path: Path) -> str:
    first = relative_path.parts[0].casefold() if relative_path.parts else ""
    suffix = relative_path.suffix.casefold()
    if first == "workbook" or first == "spreadsheets" or suffix in {
        ".xlsx",
        ".xlsm",
        ".csv",
        ".ods",
    }:
        return "Converted Schedules"
    if first == "pdf":
        return "Drawings"
    if first == "images" and suffix == ".pdf":
        return "Symbol-Mapped Drawings"
    if first == "images":
        return "Assets"
    if first == "documents":
        return "References"
    return "References"


class ProjectFileLibrary:
    """Virtual project file tree backed by files inside one project package."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        self.manifest_path = self.project_dir / "source_library.json"
        self.sources_root = self.project_dir / "sources"

    @staticmethod
    def empty() -> dict[str, Any]:
        return {
            "schemaVersion": 3,
            "folders": list(STANDARD_FOLDERS),
            "archivedFolders": [],
            "files": [],
            "conversionQueue": [],
            "importReports": [],
        }

    def _read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return self.empty()
        try:
            payload = json.loads(self.manifest_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectWorkspaceError(
                "The Project Files index is unreadable."
            ) from exc
        payload["schemaVersion"] = 3
        payload.setdefault("folders", [])
        payload.setdefault("archivedFolders", [])
        payload.setdefault("files", payload.pop("sources", []))
        payload.setdefault("conversionQueue", [])
        payload.setdefault("importReports", [])
        payload["folders"] = list(
            dict.fromkeys([*STANDARD_FOLDERS, *payload["folders"]])
        )
        for record in payload["files"]:
            record.setdefault("fileType", record.pop("sourceType", "other"))
            record.setdefault("virtualPath", "")
            record.setdefault(
                "relativePath",
                f"{record['virtualPath']}/{record.get('originalFileName', '')}".strip(
                    "/"
                ),
            )
        return payload

    def _discover_existing(self, known_paths: set[str]) -> list[dict[str, Any]]:
        if not self.sources_root.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.sources_root.rglob("*")):
            if not path.is_file():
                continue
            local_path = path.relative_to(self.project_dir).as_posix()
            if local_path in known_paths:
                continue
            relative = path.relative_to(self.sources_root)
            virtual_path = _legacy_virtual_folder(relative)
            suffix = path.suffix.casefold()
            record_id = hashlib.sha256(
                f"project-file:{local_path}".encode("utf-8")
            ).hexdigest()[:16]
            records.append(
                {
                    "id": record_id,
                    "originalFileName": path.name,
                    "storedFileName": path.name,
                    "mediaType": suffix.lstrip(".") or "file",
                    "fileType": SAFE_EXTENSIONS.get(suffix, "other"),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "dateAdded": datetime.fromtimestamp(
                        path.stat().st_mtime, timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "version": 1,
                    "status": "active",
                    "virtualPath": virtual_path,
                    "relativePath": f"{virtual_path}/{path.name}",
                    "localProjectPath": local_path,
                    "tags": [],
                    "notes": "",
                    "discovered": True,
                }
            )
        return records

    def load(self) -> dict[str, Any]:
        payload = self._read_manifest()
        known = {
            str(item.get("localProjectPath") or "")
            for item in payload["files"]
        }
        payload["files"] = [
            *payload["files"],
            *self._discover_existing(known),
        ]
        discovered_folders = [
            str(item.get("virtualPath") or "") for item in payload["files"]
        ]
        payload["folders"] = sorted(
            dict.fromkeys(
                folder
                for folder in [*STANDARD_FOLDERS, *payload["folders"], *discovered_folders]
                if folder
            ),
            key=str.casefold,
        )
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        payload["schemaVersion"] = 3
        atomic_json_write(self.manifest_path, payload)

    def create_folder(self, virtual_path: str) -> str:
        folder = safe_virtual_path(virtual_path)
        if not folder:
            raise ProjectWorkspaceError("A folder name is required.")
        payload = self.load()
        if folder not in payload["folders"]:
            payload["folders"].append(folder)
            payload["folders"].sort(key=str.casefold)
            self._save(payload)
        return folder

    def upload(
        self,
        stream: BinaryIO,
        original_name: str,
        virtual_path: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_name = secure_filename(Path(str(original_name)).name)
        suffix = Path(clean_name).suffix.casefold()
        file_type = SAFE_EXTENSIONS.get(suffix)
        if not clean_name or not file_type:
            raise ProjectWorkspaceError(
                f"Unsupported or unsafe project file: {original_name}"
            )
        folder = safe_virtual_path(virtual_path)
        # Materialize existing records before creating the destination. Otherwise
        # the just-written content-addressed file would be rediscovered as a
        # second legacy record during this same upload.
        payload = self.load()
        record_id = uuid.uuid4().hex[:16]
        destination_dir = self.sources_root / "library" / folder
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{record_id}__{clean_name}"
        digest = hashlib.sha256()
        total = 0
        try:
            with destination.open("xb") as handle:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise ProjectWorkspaceError(
                            "Project files may not exceed 100 MB each."
                        )
                    digest.update(chunk)
                    handle.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

        existing = [
            item
            for item in payload["files"]
            if item.get("originalFileName") == original_name
            and item.get("virtualPath", "") == folder
        ]
        record = {
            "id": record_id,
            "originalFileName": original_name,
            "storedFileName": destination.name,
            "mediaType": suffix.lstrip("."),
            "fileType": file_type,
            "size": total,
            "sha256": digest.hexdigest(),
            "dateAdded": utcnow(),
            "addedBy": str((metadata or {}).get("addedBy") or ""),
            "version": len(existing) + 1,
            "status": "active",
            "virtualPath": folder,
            "relativePath": f"{folder}/{original_name}".strip("/"),
            "localProjectPath": destination.relative_to(
                self.project_dir
            ).as_posix(),
            "tags": list((metadata or {}).get("tags") or []),
            "notes": str((metadata or {}).get("notes") or ""),
        }
        for old in existing:
            if old.get("status") == "active":
                old["status"] = "superseded"
                old["supersededBy"] = record_id
                record["supersedes"] = old["id"]
        payload["files"].append(record)
        if folder and folder not in payload["folders"]:
            payload["folders"].append(folder)
        self._save(payload)
        return record

    def import_zip(
        self, stream: BinaryIO, original_name: str, virtual_path: str = ""
    ) -> dict[str, Any]:
        root = safe_virtual_path(virtual_path)
        fd, temp_name = tempfile.mkstemp(
            prefix=".project-files-", suffix=".zip", dir=self.project_dir
        )
        os.close(fd)
        archive_path = Path(temp_name)
        imported: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []
        created_folders: set[str] = set()
        try:
            with archive_path.open("wb") as handle:
                shutil.copyfileobj(stream, handle)
            if archive_path.stat().st_size > MAX_ZIP_BYTES:
                raise ProjectWorkspaceError("ZIP imports may not exceed 500 MB.")
            with zipfile.ZipFile(archive_path) as bundle:
                members = bundle.infolist()
                if len(members) > MAX_ZIP_MEMBERS:
                    raise ProjectWorkspaceError("ZIP contains too many entries.")
                if sum(item.file_size for item in members) > MAX_ZIP_BYTES:
                    raise ProjectWorkspaceError(
                        "ZIP expands beyond the 500 MB safety limit."
                    )
                for member in members:
                    try:
                        member_path = safe_virtual_path(member.filename)
                        if not member_path:
                            continue
                        member_folder = Path(member_path).parent.as_posix()
                        if member_folder == ".":
                            member_folder = ""
                        destination_folder = "/".join(
                            part for part in (root, member_folder) if part
                        )
                        if member.is_dir():
                            if destination_folder:
                                self.create_folder(destination_folder)
                                created_folders.add(destination_folder)
                            continue
                        if member.flag_bits & 0x1:
                            raise ProjectWorkspaceError(
                                "Encrypted ZIP entries are not supported."
                            )
                        if member.file_size > MAX_FILE_BYTES:
                            raise ProjectWorkspaceError(
                                "ZIP member exceeds the 100 MB file limit."
                            )
                        with bundle.open(member) as source:
                            imported.append(
                                self.upload(
                                    source,
                                    Path(member_path).name,
                                    destination_folder,
                                    {
                                        "notes": (
                                            f"Imported from {original_name}:"
                                            f"{member.filename}"
                                        )
                                    },
                                )
                            )
                    except Exception as exc:
                        rejected.append(
                            {"path": member.filename, "reason": str(exc)}
                        )
            payload = self.load()
            report = {
                "id": uuid.uuid4().hex[:16],
                "archive": original_name,
                "imported": len(imported),
                "createdFolders": sorted(created_folders),
                "rejected": rejected,
                "createdAt": utcnow(),
            }
            payload["importReports"].append(report)
            self._save(payload)
            return {"report": report, "files": imported}
        finally:
            archive_path.unlink(missing_ok=True)

    def _file(self, payload: dict[str, Any], file_id: str) -> dict[str, Any]:
        if not FILE_ID_RE.fullmatch(file_id):
            raise ProjectWorkspaceError("Invalid project file ID.")
        for record in payload["files"]:
            if record.get("id") == file_id:
                return record
        raise ProjectWorkspaceError("Project file was not found.")

    def resolve(self, file_id: str) -> tuple[dict[str, Any], Path]:
        payload = self.load()
        record = self._file(payload, file_id)
        path = (self.project_dir / str(record["localProjectPath"])).resolve()
        try:
            path.relative_to(self.project_dir)
        except ValueError as exc:
            raise ProjectWorkspaceError(
                "Project file path escaped the project package."
            ) from exc
        if not path.is_file():
            raise ProjectWorkspaceError("Project file is missing.")
        return record, path

    def rename_file(self, file_id: str, name: str) -> dict[str, Any]:
        safe_name = Path(str(name).replace("\\", "/")).name.strip()
        if (
            not safe_name
            or safe_name in {".", ".."}
            or safe_name != str(name).strip()
            or not safe_virtual_path(safe_name)
        ):
            raise ProjectWorkspaceError("A safe file name is required.")
        payload = self.load()
        record = self._file(payload, file_id)
        record["originalFileName"] = safe_name
        record["relativePath"] = (
            f"{record.get('virtualPath', '')}/{safe_name}".strip("/")
        )
        record["renamedAt"] = utcnow()
        self._save(payload)
        return record

    def move_file(self, file_id: str, destination: str) -> dict[str, Any]:
        folder = safe_virtual_path(destination)
        payload = self.load()
        record = self._file(payload, file_id)
        record["virtualPath"] = folder
        record["relativePath"] = (
            f"{folder}/{record['originalFileName']}".strip("/")
        )
        record["movedAt"] = utcnow()
        if folder and folder not in payload["folders"]:
            payload["folders"].append(folder)
        self._save(payload)
        return record

    def archive_file(self, file_id: str) -> dict[str, Any]:
        payload = self.load()
        record = self._file(payload, file_id)
        record["status"] = "archived"
        record["archivedAt"] = utcnow()
        self._save(payload)
        return record

    def restore_file(self, file_id: str) -> dict[str, Any]:
        payload = self.load()
        record = self._file(payload, file_id)
        record["status"] = "active"
        record.pop("archivedAt", None)
        record["restoredAt"] = utcnow()
        self._save(payload)
        return record

    def _relocate_folder(
        self, payload: dict[str, Any], old_path: str, new_path: str
    ) -> None:
        old = safe_virtual_path(old_path)
        new = safe_virtual_path(new_path)
        if not old or not new or old == new:
            raise ProjectWorkspaceError(
                "Choose a different source and destination folder."
            )
        if old not in payload["folders"]:
            raise ProjectWorkspaceError("Project folder was not found.")
        if new == old or new.startswith(f"{old}/"):
            raise ProjectWorkspaceError(
                "A folder cannot be moved inside itself."
            )
        rewritten: list[str] = []
        for folder in payload["folders"]:
            if folder == old or folder.startswith(f"{old}/"):
                rewritten.append(f"{new}{folder[len(old):]}")
            else:
                rewritten.append(folder)
        payload["folders"] = sorted(dict.fromkeys(rewritten), key=str.casefold)
        for record in payload["files"]:
            current = str(record.get("virtualPath") or "")
            if current == old or current.startswith(f"{old}/"):
                record["virtualPath"] = f"{new}{current[len(old):]}"
                record["relativePath"] = (
                    f"{record['virtualPath']}/{record['originalFileName']}"
                )

    def rename_folder(self, path: str, name: str) -> str:
        current = safe_virtual_path(path)
        parent = Path(current).parent.as_posix()
        if parent == ".":
            parent = ""
        safe_name = safe_virtual_path(name)
        if "/" in safe_name:
            raise ProjectWorkspaceError("Enter one folder name.")
        destination = "/".join(
            part for part in (parent, safe_name) if part
        )
        payload = self.load()
        self._relocate_folder(payload, current, destination)
        self._save(payload)
        return destination

    def move_folder(self, path: str, destination: str) -> str:
        current = safe_virtual_path(path)
        parent = safe_virtual_path(destination)
        moved = "/".join(
            part for part in (parent, Path(current).name) if part
        )
        payload = self.load()
        self._relocate_folder(payload, current, moved)
        self._save(payload)
        return moved

    def archive_folder(self, path: str) -> str:
        current = safe_virtual_path(path)
        if current == "Archive" or current.startswith("Archive/"):
            raise ProjectWorkspaceError("This folder is already archived.")
        destination = f"Archive/{current}"
        payload = self.load()
        self._relocate_folder(payload, current, destination)
        for record in payload["files"]:
            folder = str(record.get("virtualPath") or "")
            if folder == destination or folder.startswith(f"{destination}/"):
                record["status"] = "archived"
                record["archivedAt"] = utcnow()
        payload["archivedFolders"].append(
            {"path": destination, "restorePath": current, "archivedAt": utcnow()}
        )
        self._save(payload)
        return destination

    def restore_folder(self, path: str) -> str:
        archived = safe_virtual_path(path)
        payload = self.load()
        entry = next(
            (
                item
                for item in payload["archivedFolders"]
                if item.get("path") == archived
            ),
            None,
        )
        if not entry:
            raise ProjectWorkspaceError(
                "This folder does not have a restore location."
            )
        destination = safe_virtual_path(str(entry["restorePath"]))
        self._relocate_folder(payload, archived, destination)
        for record in payload["files"]:
            folder = str(record.get("virtualPath") or "")
            if folder == destination or folder.startswith(f"{destination}/"):
                record["status"] = "active"
                record.pop("archivedAt", None)
        payload["archivedFolders"].remove(entry)
        self._save(payload)
        return destination

    def preview(self, file_id: str) -> dict[str, Any]:
        record, path = self.resolve(file_id)
        result: dict[str, Any] = {
            "file": record,
            "kind": record["fileType"],
            "previewError": "",
        }
        try:
            suffix = path.suffix.casefold()
            if suffix in {".xlsx", ".xlsm"}:
                workbook = load_workbook(
                    path,
                    read_only=True,
                    data_only=False,
                    keep_vba=suffix == ".xlsm",
                )
                result["sheets"] = workbook.sheetnames
                sheet = workbook[workbook.sheetnames[0]]
                result["grid"] = [
                    ["" if value is None else str(value) for value in row]
                    for row in sheet.iter_rows(
                        max_row=50, max_col=20, values_only=True
                    )
                ]
                workbook.close()
            elif suffix == ".csv":
                text = path.read_text("utf-8", errors="replace")[:100_000]
                result["text"] = text
                result["grid"] = list(csv.reader(text.splitlines()))[:100]
            elif suffix in {".txt", ".md", ".json", ".log", ".rtf"}:
                result["text"] = path.read_text(
                    "utf-8", errors="replace"
                )[:100_000]
            elif suffix == ".pdf":
                import fitz

                pdf = fitz.open(path)
                result["pageCount"] = pdf.page_count
                result["pageSizes"] = [
                    {"width": page.rect.width, "height": page.rect.height}
                    for page in list(pdf)[:25]
                ]
                pdf.close()
            elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                from PIL import Image

                with Image.open(path) as image:
                    result["dimensions"] = {
                        "width": image.width,
                        "height": image.height,
                    }
            else:
                result["fallback"] = "metadata"
        except Exception as exc:
            result["previewError"] = f"{type(exc).__name__}: {exc}"
        return result


def _json_cell_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def workbook_file_to_document(path: Path) -> dict[str, Any]:
    workbook = load_workbook(
        path,
        data_only=False,
        keep_vba=path.suffix.casefold() == ".xlsm",
    )
    sheets: list[dict[str, Any]] = []
    for sheet in workbook.worksheets:
        cells: dict[str, Any] = {}
        for row in sheet.iter_rows(
            min_row=1,
            max_row=min(sheet.max_row, 5_000),
            max_col=min(sheet.max_column, 200),
        ):
            for cell in row:
                if cell.value is not None:
                    value = _json_cell_value(cell.value)
                    cells[cell.coordinate] = (
                        {"f": value}
                        if isinstance(value, str) and value.startswith("=")
                        else {"v": value}
                    )
        sheets.append(
            {
                "id": uuid.uuid4().hex[:16],
                "name": sheet.title,
                "cells": cells,
                "styles": {},
                "merges": [str(item) for item in sheet.merged_cells.ranges],
                "rowHeights": {
                    str(index): dimension.height
                    for index, dimension in sheet.row_dimensions.items()
                    if dimension.height
                },
                "columnWidths": {
                    key: dimension.width
                    for key, dimension in sheet.column_dimensions.items()
                    if dimension.width
                },
                "archived": sheet.sheet_state != "visible",
            }
        )
    workbook.close()
    return {"revision": 0, "updatedAt": utcnow(), "sheets": sheets}


def project_to_workbook_document(project: dict[str, Any]) -> dict[str, Any]:
    def coordinate(row: int, column: int) -> str:
        current = column + 1
        letters = ""
        while current:
            current, remainder = divmod(current - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row + 1}"

    def dimensions(value: Any, *, columns: bool) -> dict[str, float]:
        if isinstance(value, dict):
            return {
                str(key): float(item)
                for key, item in value.items()
                if isinstance(item, (int, float)) and item > 0
            }
        if isinstance(value, list):
            output: dict[str, float] = {}
            for index, item in enumerate(value):
                if not isinstance(item, (int, float)) or item <= 0:
                    continue
                key = coordinate(0, index)[:-1] if columns else str(index + 1)
                output[key] = float(item)
            return output
        return {}

    sheets: list[dict[str, Any]] = []
    for index, worksheet in enumerate(project.get("worksheets") or []):
        cells: dict[str, Any] = {}
        for row_index, row in enumerate(worksheet.get("grid") or [], 1):
            for column_index, value in enumerate(row, 1):
                if value in (None, ""):
                    continue
                current = column_index
                letters = ""
                while current:
                    current, remainder = divmod(current - 1, 26)
                    letters = chr(65 + remainder) + letters
                cells[f"{letters}{row_index}"] = {"v": value}
        sheets.append(
            {
                "id": str(
                    worksheet.get("id")
                    or hashlib.sha256(
                        f"worksheet:{index}".encode("utf-8")
                    ).hexdigest()[:16]
                ),
                "name": str(worksheet.get("name") or f"Sheet {index + 1}"),
                "cells": cells,
                "styles": dict(worksheet.get("styles") or {}),
                "merges": [
                    (
                        f"{coordinate(int(item['startRow']), int(item['startCol']))}:"
                        f"{coordinate(int(item['endRow']), int(item['endCol']))}"
                    )
                    if isinstance(item, dict)
                    and all(
                        key in item
                        for key in ("startRow", "startCol", "endRow", "endCol")
                    )
                    else str(item)
                    for item in (worksheet.get("mergedCells") or [])
                ],
                "rowHeights": dimensions(
                    worksheet.get("rowHeights")
                    or worksheet.get("rowHeightsPx")
                    or {},
                    columns=False,
                ),
                "columnWidths": dimensions(
                    worksheet.get("columnWidths")
                    or worksheet.get("colWidthsPx")
                    or {},
                    columns=True,
                ),
                "archived": not bool(worksheet.get("visible", True)),
            }
        )
    return {"revision": 0, "updatedAt": utcnow(), "sheets": sheets}


class WorkbookDocumentStore:
    """JSON workbook mirror used by the browser-only Data Workspace."""

    def __init__(self, project_dir: Path):
        self.path = Path(project_dir) / "data" / "workbook.json"
        self.history = Path(project_dir) / "backups" / "workbook"

    def load(self, project: dict[str, Any]) -> dict[str, Any]:
        if self.path.is_file():
            return json.loads(self.path.read_text("utf-8"))
        return project_to_workbook_document(project)

    def save(
        self,
        project: dict[str, Any],
        expected_revision: int,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        current = self.load(project)
        if int(current.get("revision") or 0) != int(expected_revision):
            raise WorkbookRevisionConflict(
                "Data Workspace revision conflict: "
                f"expected {expected_revision}, current {current.get('revision', 0)}."
            )
        if self.path.is_file():
            self.history.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                self.path,
                self.history
                / f"workbook_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}.json",
            )
        saved = dict(document)
        saved["revision"] = int(current.get("revision") or 0) + 1
        saved["updatedAt"] = utcnow()
        atomic_json_write(self.path, saved)
        return saved

    def import_file(
        self,
        project: dict[str, Any],
        source_path: Path,
        display_name: str,
    ) -> dict[str, Any]:
        current = self.load(project)
        suffix = source_path.suffix.casefold()
        if suffix in {".xlsx", ".xlsm"}:
            imported = workbook_file_to_document(source_path)
        elif suffix == ".csv":
            with source_path.open(
                "r", encoding="utf-8-sig", errors="replace", newline=""
            ) as handle:
                rows = list(csv.reader(handle))
            cells: dict[str, Any] = {}
            for row_index, row in enumerate(rows[:5_000], 1):
                for column_index, value in enumerate(row[:200], 1):
                    current_column = column_index
                    letters = ""
                    while current_column:
                        current_column, remainder = divmod(
                            current_column - 1, 26
                        )
                        letters = chr(65 + remainder) + letters
                    if value != "":
                        cells[f"{letters}{row_index}"] = {"v": value}
            imported = {
                "sheets": [
                    {
                        "id": uuid.uuid4().hex[:16],
                        "name": Path(display_name).stem[:31],
                        "cells": cells,
                        "styles": {},
                        "merges": [],
                        "rowHeights": {},
                        "columnWidths": {},
                        "archived": False,
                    }
                ]
            }
        else:
            raise ProjectWorkspaceError(
                "Only XLSX, XLSM, and CSV files can be sent to Data Workspace."
            )

        existing_names = {
            str(sheet.get("name") or "").casefold()
            for sheet in current.get("sheets") or []
        }
        for sheet in imported.get("sheets") or []:
            base = str(sheet.get("name") or "Imported")[:27]
            candidate = base
            counter = 2
            while candidate.casefold() in existing_names:
                candidate = f"{base[:26]} {counter}"
                counter += 1
            sheet["name"] = candidate
            sheet["id"] = uuid.uuid4().hex[:16]
            existing_names.add(candidate.casefold())
            current.setdefault("sheets", []).append(sheet)
        return self.save(
            project,
            int(current.get("revision") or 0),
            current,
        )
