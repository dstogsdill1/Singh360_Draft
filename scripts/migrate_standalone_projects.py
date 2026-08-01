#!/usr/bin/env python3
"""Plan or apply the protected Singh360 standalone-project migration.

The command is dry-run by default. It edits only the three protected
``project.json`` files and never opens or writes a workbook. Before an apply it
stores exact pre-migration JSON bytes, a SHA-256 manifest, the approved plan,
and a one-command rollback helper under ``<docs>/_migration_backups``.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping
import uuid


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.standalone_project import (  # noqa: E402
    _is_cover as _standalone_is_cover,
    _is_generated_index_continuation as _standalone_is_generated_index_continuation,
    _is_index as _standalone_is_index,
    archive_project,
    migrate_project_to_standalone,
)


CANONICAL_MI_TIENDA_ID = "a214bea233ee4dcc"
LEGACY_MI_TIENDA_ID = "5e1bf02aedd84307"
SA31_ID = "95d85da603864a62"
CANONICAL_MI_TIENDA_NAME = "Mi Tienda 03 / 829"
CANONICAL_MI_TIENDA_PACKAGE_NAME = "Mi_Tienda_03_829"
ARCHIVED_MI_TIENDA_NAME = "ARCHIVED — Mi Tienda 03 / 829 — Legacy Workbook-Synced"

PROTECTED_PROJECTS: tuple[dict[str, str], ...] = (
    {
        "projectId": CANONICAL_MI_TIENDA_ID,
        "role": "canonical_mi_tienda_829",
        "description": "Convert Layout Sandbox in place to canonical Mi Tienda 03 / 829.",
    },
    {
        "projectId": LEGACY_MI_TIENDA_ID,
        "role": "archive_legacy_mi_tienda_829",
        "description": "Archive the legacy workbook-synced Mi Tienda project by metadata only.",
    },
    {
        "projectId": SA31_ID,
        "role": "sa31_detach_only",
        "description": "Detach SA31 from workbook authority without normalizing any page.",
    },
)


class MigrationSafetyError(RuntimeError):
    """Raised when protected migration preconditions are not satisfied."""


def _timestamp(value: str | None = None) -> str:
    if value is not None:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("now must be non-empty when supplied")
        return cleaned
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_project(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise MigrationSafetyError(f"Project JSON is not an object: {path}")
    return value


def _project_bytes(project: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(project), ensure_ascii=False, indent=2).encode("utf-8")


def _relative_inside(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise MigrationSafetyError(f"Protected project path is outside docs directory: {path}") from exc


def _find_project_paths(docs_dir: Path, project_id: str) -> list[Path]:
    candidates: list[Path] = []
    projects_dir = docs_dir / "projects"
    if projects_dir.is_dir():
        candidates.extend(
            path for path in projects_dir.glob(f"*__{project_id}/project.json") if path.is_file()
        )
    legacy = docs_dir / f"{project_id}.json"
    if legacy.is_file():
        candidates.append(legacy)
    unique: dict[str, Path] = {}
    for path in candidates:
        unique[str(path.resolve())] = path
    return sorted(unique.values(), key=lambda item: str(item).casefold())


_PAGE_NUMBER_FIELDS = {"order", "pageNumber", "pageTotal"}
_COVER_MANAGED_FIELDS = {
    *_PAGE_NUMBER_FIELDS,
    "pageType",
    "pageFamily",
    "managedPage",
    "appManaged",
    "include",
    "sheetCode",
    "displaySheetCode",
    "sheetTitle",
    "sheetTab",
    "templateId",
}
_INDEX_MANAGED_FIELDS = {
    *_PAGE_NUMBER_FIELDS,
    "pageType",
    "pageFamily",
    "managedPage",
    "appManaged",
    "include",
    "sheetCode",
    "displaySheetCode",
    "sheetTitle",
    "sheetTab",
    "templateId",
    "renderMode",
    "normalizedHeaderStyle",
    "standaloneIndex",
    "indexRowsPerPage",
    "indexRowsOnPage",
    "indexPageCount",
}
_INDEX_CONTINUATION_MANAGED_FIELDS = {
    *_INDEX_MANAGED_FIELDS,
    "pageGroupId",
    "continuationOf",
    "continuationIndex",
    "generatedContinuation",
    "indexContinuation",
    "generatedIndexContinuation",
    "archivedAt",
    "archivedReason",
    "archivedFromIndex",
    "lastArchivedAt",
    "lastArchivedReason",
    "lastArchivedFromIndex",
    "restoredAt",
    "createdAt",
}


def _page_role(page: Mapping[str, Any]) -> str:
    """Use the same managed-page classification as the migration transform."""
    if _standalone_is_generated_index_continuation(page):
        return "index_continuation"
    if _standalone_is_cover(page):
        return "cover"
    if _standalone_is_index(page):
        return "index"
    return ""


def _page_collections(
    project: Mapping[str, Any],
    *,
    role: str,
    phase: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    active_raw = project.get("pages") or []
    archived_raw = project.get("archivedPages") or []
    if not isinstance(active_raw, list) or any(not isinstance(page, Mapping) for page in active_raw):
        raise MigrationSafetyError(f"{role}: {phase} pages must be a list of page objects")
    if not isinstance(archived_raw, list) or any(not isinstance(page, Mapping) for page in archived_raw):
        raise MigrationSafetyError(f"{role}: {phase} archivedPages must be a list of page objects")
    active = [deepcopy(dict(page)) for page in active_raw]
    archived = [deepcopy(dict(page)) for page in archived_raw]
    identities = [str(page.get("id") or "").strip() for page in [*active, *archived]]
    if any(not identity for identity in identities):
        raise MigrationSafetyError(f"{role}: {phase} project contains a page without a stable ID")
    duplicates = sorted(
        identity for identity in set(identities) if identities.count(identity) > 1
    )
    if duplicates:
        raise MigrationSafetyError(
            f"{role}: {phase} project page IDs are not unique: {duplicates}"
        )
    return active, archived, {
        str(page["id"]): page for page in [*active, *archived]
    }


def _without_fields(page: Mapping[str, Any], fields: set[str]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in page.items() if key not in fields}


def _assert_visual_payload_preserved(
    before_page: Mapping[str, Any],
    after_page: Mapping[str, Any],
    *,
    role: str,
    page_id: str,
) -> None:
    before_canvas = deepcopy(before_page.get("canvasObjects") or [])
    after_canvas = deepcopy(after_page.get("canvasObjects") or [])
    if before_canvas != after_canvas:
        raise MigrationSafetyError(
            f"{role}: managed page {page_id} changed canvasObjects/annotations/components"
        )

    before_blocks = deepcopy(before_page.get("blocks") or [])
    after_blocks = deepcopy(after_page.get("blocks") or [])
    page_role = _page_role(before_page)
    if page_role == "cover" and before_blocks != after_blocks:
        inserted_cover_block = (
            len(after_blocks) == len(before_blocks) + 1
            and isinstance(after_blocks[0], Mapping)
            and after_blocks[0].get("type") == "cover"
            and after_blocks[1:] == before_blocks
        )
        if not inserted_cover_block:
            raise MigrationSafetyError(
                f"{role}: managed Cover {page_id} changed existing blocks"
            )
    elif page_role != "cover" and before_blocks != after_blocks:
        raise MigrationSafetyError(
            f"{role}: managed page {page_id} changed blocks"
        )


def _assert_canonical_pages_preserved(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    role: str,
) -> None:
    before_active, before_archived, before_by_id = _page_collections(
        before, role=role, phase="before"
    )
    after_active, after_archived, after_by_id = _page_collections(
        after, role=role, phase="after"
    )
    before_ids = set(before_by_id)
    after_ids = set(after_by_id)
    missing = sorted(before_ids - after_ids)
    if missing:
        raise MigrationSafetyError(f"{role}: page IDs were lost: {missing}")

    base_covers = [page for page in after_active if _page_role(page) == "cover"]
    base_indexes = [page for page in after_active if _page_role(page) == "index"]
    if len(base_covers) != 1 or len(base_indexes) != 1:
        raise MigrationSafetyError(
            f"{role}: migration must produce exactly one managed Cover and one base Sheet Index"
        )

    for page_id in sorted(after_ids - before_ids):
        if not _page_role(after_by_id[page_id]):
            raise MigrationSafetyError(
                f"{role}: migration added non-managed page {page_id}"
            )

    before_non_managed_active = [
        str(page["id"]) for page in before_active if not _page_role(page)
    ]
    after_non_managed_active = [
        str(page["id"])
        for page in after_active
        if str(page["id"]) in set(before_non_managed_active)
    ]
    if before_non_managed_active != after_non_managed_active:
        raise MigrationSafetyError(
            f"{role}: existing non-managed page order changed"
        )

    after_active_ids = {str(page["id"]) for page in after_active}
    after_archived_ids = {str(page["id"]) for page in after_archived}
    for before_page in [*before_active, *before_archived]:
        page_id = str(before_page["id"])
        after_page = after_by_id[page_id]
        managed_role = _page_role(before_page)
        if not managed_role:
            expected_collection = (
                after_active_ids if before_page in before_active else after_archived_ids
            )
            if page_id not in expected_collection:
                raise MigrationSafetyError(
                    f"{role}: non-managed page {page_id} changed active/archive state"
                )
            if _without_fields(before_page, _PAGE_NUMBER_FIELDS) != _without_fields(
                after_page, _PAGE_NUMBER_FIELDS
            ):
                changed = sorted(
                    key
                    for key in set(before_page) | set(after_page)
                    if key not in _PAGE_NUMBER_FIELDS
                    and before_page.get(key) != after_page.get(key)
                )
                raise MigrationSafetyError(
                    f"{role}: non-managed page {page_id} changed protected fields: {changed}"
                )
            continue

        if _page_role(after_page) != managed_role:
            raise MigrationSafetyError(
                f"{role}: managed page {page_id} changed role from {managed_role!r}"
            )
        _assert_visual_payload_preserved(
            before_page, after_page, role=role, page_id=page_id
        )
        allowed = {
            "cover": _COVER_MANAGED_FIELDS,
            "index": _INDEX_MANAGED_FIELDS,
            "index_continuation": _INDEX_CONTINUATION_MANAGED_FIELDS,
        }[managed_role]
        protected_before = _without_fields(before_page, {"blocks", "canvasObjects", *allowed})
        protected_after = _without_fields(after_page, {"blocks", "canvasObjects", *allowed})
        # Normalization may add its generated explanatory note only when a
        # managed page previously had no note field at all.
        if "notes" not in before_page:
            protected_after.pop("notes", None)
        if protected_before != protected_after:
            changed = sorted(
                key
                for key in set(protected_before) | set(protected_after)
                if protected_before.get(key) != protected_after.get(key)
            )
            raise MigrationSafetyError(
                f"{role}: managed page {page_id} changed non-approved fields: {changed}"
            )


def _assert_preserved(before: Mapping[str, Any], after: Mapping[str, Any], role: str) -> None:
    if str(before.get("id") or "") != str(after.get("id") or ""):
        raise MigrationSafetyError(f"{role}: project identity changed")
    for key in ("assets", "savedAssemblies", "sources"):
        if deepcopy(before.get(key) or []) != deepcopy(after.get(key) or []):
            raise MigrationSafetyError(f"{role}: {key} changed during metadata migration")
    _page_collections(before, role=role, phase="before")
    _page_collections(after, role=role, phase="after")
    if role == "canonical_mi_tienda_829":
        _assert_canonical_pages_preserved(before, after, role)
    elif role in {"archive_legacy_mi_tienda_829", "sa31_detach_only"}:
        if deepcopy(before.get("pages") or []) != deepcopy(after.get("pages") or []):
            raise MigrationSafetyError(f"{role}: active page content/order changed")
        if deepcopy(before.get("archivedPages") or []) != deepcopy(after.get("archivedPages") or []):
            raise MigrationSafetyError(f"{role}: archived page content/order changed")


def _transform_project(project: Mapping[str, Any], role: str, timestamp: str) -> dict[str, Any]:
    before = deepcopy(dict(project))
    if role == "canonical_mi_tienda_829":
        staged = deepcopy(before)
        metadata = deepcopy(staged.get("metadata")) if isinstance(staged.get("metadata"), Mapping) else {}
        metadata["projectName"] = CANONICAL_MI_TIENDA_NAME
        metadata["storeNumber"] = "829"
        if not str(metadata.get("drawingPackageFileName") or "").strip():
            metadata["drawingPackageFileName"] = CANONICAL_MI_TIENDA_PACKAGE_NAME
        staged["metadata"] = metadata
        after = migrate_project_to_standalone(
            staged,
            now=timestamp,
            canonical_display_name=CANONICAL_MI_TIENDA_NAME,
            archived=False,
            normalize_managed_pages=True,
        )
    elif role == "archive_legacy_mi_tienda_829":
        staged = deepcopy(before)
        staged["projectDisplayName"] = ARCHIVED_MI_TIENDA_NAME
        metadata = deepcopy(staged.get("metadata")) if isinstance(staged.get("metadata"), Mapping) else {}
        metadata["projectName"] = ARCHIVED_MI_TIENDA_NAME
        staged["metadata"] = metadata
        after = archive_project(
            staged,
            reason="Superseded by canonical Mi Tienda 03 / 829 project a214bea233ee4dcc.",
            now=timestamp,
        )
    elif role == "sa31_detach_only":
        after = migrate_project_to_standalone(
            before,
            now=timestamp,
            archived=False,
            normalize_managed_pages=False,
        )
    else:
        raise MigrationSafetyError(f"Unknown protected migration role: {role}")
    _assert_preserved(before, after, role)
    return after


def _summary(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    legacy = after.get("legacyWorkbookReference") if isinstance(after.get("legacyWorkbookReference"), Mapping) else {}
    return {
        "before": {
            "displayName": str(before.get("projectDisplayName") or ""),
            "projectMode": str(before.get("projectMode") or ""),
            "archived": bool(before.get("archived")),
            "pageCount": len(before.get("pages") or []),
            "archivedPageCount": len(before.get("archivedPages") or []),
            "assetCount": len(before.get("assets") or []),
            "savedAssemblyCount": len(before.get("savedAssemblies") or []),
        },
        "after": {
            "displayName": str(after.get("projectDisplayName") or ""),
            "projectMode": str(after.get("projectMode") or ""),
            "archived": bool(after.get("archived")),
            "pageCount": len(after.get("pages") or []),
            "archivedPageCount": len(after.get("archivedPages") or []),
            "assetCount": len(after.get("assets") or []),
            "savedAssemblyCount": len(after.get("savedAssemblies") or []),
            "workbookSyncStatus": str((after.get("workbookSync") or {}).get("status") or ""),
            "legacyWorkbookReferenceFields": sorted(str(key) for key in legacy),
        },
    }


def build_migration_plan(
    docs_dir: str | Path,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Build a read-only protected-project migration plan.

    This function never creates directories, backups, or reports. It reads only
    the three protected project JSON files.
    """

    docs = Path(docs_dir).expanduser().resolve()
    generated_at = _timestamp(now)
    actions: list[dict[str, Any]] = []
    blockers: list[str] = []
    if not docs.is_dir():
        blockers.append(f"Docs directory does not exist: {docs}")
    else:
        for definition in PROTECTED_PROJECTS:
            project_id = definition["projectId"]
            paths = _find_project_paths(docs, project_id)
            action: dict[str, Any] = {**definition, "foundPaths": [str(path) for path in paths]}
            if len(paths) != 1:
                state = "missing" if not paths else "ambiguous"
                action.update({"state": state, "needsChange": False})
                blockers.append(f"{project_id}: expected exactly one project.json, found {len(paths)}")
                actions.append(action)
                continue
            path = paths[0]
            try:
                relative = _relative_inside(path, docs)
                before = _read_project(path)
                if str(before.get("id") or "") != project_id:
                    raise MigrationSafetyError(
                        f"project.json identity {before.get('id')!r} does not match protected ID {project_id}"
                    )
                after = _transform_project(before, definition["role"], generated_at)
                before_sha = _sha256_file(path)
                # A normal project save may serialize the same logical JSON
                # with a trailing newline or a different key order. Migration
                # idempotence is about project state, not byte formatting: do
                # not rewrite an already-migrated live package merely to
                # canonicalize its JSON representation.
                needs_change = before != after
                after_sha = (
                    _sha256_bytes(_project_bytes(after))
                    if needs_change
                    else before_sha
                )
                action.update(
                    {
                        "state": "ready",
                        "path": str(path),
                        "relativePath": relative,
                        "beforeSha256": before_sha,
                        "afterSha256": after_sha,
                        "needsChange": needs_change,
                        "summary": _summary(before, after),
                    }
                )
            except Exception as exc:
                action.update({"state": "blocked", "needsChange": False, "error": str(exc)})
                blockers.append(f"{project_id}: {exc}")
            actions.append(action)
    return {
        "schemaVersion": 1,
        "mode": "dry-run",
        "docsDir": str(docs),
        "generatedAt": generated_at,
        "protectedProjectIds": [item["projectId"] for item in PROTECTED_PROJECTS],
        "safeToApply": not blockers,
        "blockers": blockers,
        "actions": actions,
        "filesThatWouldBeWritten": [
            action.get("relativePath") for action in actions if action.get("needsChange")
        ],
        "workbooksTouched": [],
    }


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if _sha256_file(temporary) != _sha256_bytes(payload):
            raise OSError(f"Temporary file failed SHA-256 readback: {temporary}")
        os.replace(temporary, path)
        if _sha256_file(path) != _sha256_bytes(payload):
            raise OSError(f"Replaced file failed SHA-256 readback: {path}")
    finally:
        temporary.unlink(missing_ok=True)


def _backup_root(docs: Path, timestamp: str) -> Path:
    token = re.sub(r"[^0-9A-Za-z]+", "", timestamp) or "migration"
    base = docs / "_migration_backups" / f"standalone_layout_{token}"
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = base.with_name(f"{base.name}_{suffix}")
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, _project_bytes(value))


def _rollback_script() -> str:
    return '''#!/usr/bin/env python3
"""Restore project.json files captured before a standalone migration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid

def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument("--docs-dir", default="")
args = parser.parse_args()
root = Path(__file__).resolve().parent
mapping = json.loads((root / "rollback-map.json").read_text(encoding="utf-8"))
docs = Path(args.docs_dir or mapping["docsDir"]).expanduser().resolve()
for item in mapping["files"]:
    backup = root / item["backupRelative"]
    target = docs / item["targetRelative"]
    if sha(backup) != item["sha256"]:
        raise SystemExit(f"Backup hash mismatch: {backup}")
    target.resolve().relative_to(docs)
    current = sha(target)
    if current not in {item["sha256"], item["expectedCurrentSha256"]}:
        raise SystemExit(f"Project changed after migration; refusing to overwrite: {target}")
for item in mapping["files"]:
    backup = root / item["backupRelative"]
    target = docs / item["targetRelative"]
    if sha(target) == item["sha256"]:
        continue
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.rollback.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(backup.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    if sha(target) != item["sha256"]:
        raise SystemExit(f"Restored hash mismatch: {target}")
print(json.dumps({"ok": True, "restored": len(mapping["files"]), "docsDir": str(docs)}, indent=2))
'''


def apply_migration_plan(
    docs_dir: str | Path,
    plan: Mapping[str, Any] | None = None,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    """Apply a validated plan with exact JSON backups and automatic rollback."""

    docs = Path(docs_dir).expanduser().resolve()
    selected_plan = deepcopy(dict(plan)) if plan is not None else build_migration_plan(docs, now=now)
    if Path(str(selected_plan.get("docsDir") or "")).resolve() != docs:
        raise MigrationSafetyError("Plan docsDir does not match apply docsDir")
    if not selected_plan.get("safeToApply"):
        raise MigrationSafetyError("Migration plan is blocked: " + "; ".join(selected_plan.get("blockers") or []))

    actions = [action for action in selected_plan.get("actions") or [] if action.get("state") == "ready"]
    if len(actions) != len(PROTECTED_PROJECTS):
        raise MigrationSafetyError("Migration plan does not contain all protected project actions")
    for action in actions:
        path = docs / str(action["relativePath"])
        if not path.is_file() or _sha256_file(path) != action.get("beforeSha256"):
            raise MigrationSafetyError(f"Precondition hash changed for {action['projectId']}; rebuild the dry-run plan")

    changing = [action for action in actions if action.get("needsChange")]
    if not changing:
        result = deepcopy(selected_plan)
        result.update(
            {
                "mode": "apply",
                "applied": False,
                "changedProjectIds": [],
                "backupPath": "",
                "rollbackCommand": "",
                "workbooksTouched": [],
            }
        )
        return result

    generated_at = str(selected_plan.get("generatedAt") or _timestamp(now))
    backup_root = _backup_root(docs, generated_at)
    rollback_files: list[dict[str, str]] = []
    manifest_lines: list[str] = []
    for action in changing:
        target = docs / str(action["relativePath"])
        backup_relative = Path("project_json") / action["projectId"] / "project.json"
        backup = backup_root / backup_relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        payload = target.read_bytes()
        _atomic_write(backup, payload)
        before_sha = _sha256_bytes(payload)
        if before_sha != action["beforeSha256"]:
            raise MigrationSafetyError(f"Backup source hash changed for {action['projectId']}")
        rollback_files.append(
            {
                "projectId": action["projectId"],
                "targetRelative": str(action["relativePath"]),
                "backupRelative": backup_relative.as_posix(),
                "sha256": before_sha,
                "expectedCurrentSha256": action["afterSha256"],
            }
        )
        manifest_lines.append(f"{before_sha}  {backup_relative.as_posix()}")

    rollback_map = {"schemaVersion": 1, "docsDir": str(docs), "files": rollback_files}
    _write_json(backup_root / "rollback-map.json", rollback_map)
    _write_json(backup_root / "migration-plan.json", selected_plan)
    _atomic_write(backup_root / "manifest.sha256", ("\n".join(manifest_lines) + "\n").encode("utf-8"))
    _atomic_write(backup_root / "rollback_standalone_migration.py", _rollback_script().encode("utf-8"))

    changed_paths: list[Path] = []
    try:
        for action in changing:
            target = docs / str(action["relativePath"])
            before = _read_project(target)
            after = _transform_project(before, str(action["role"]), generated_at)
            payload = _project_bytes(after)
            if _sha256_bytes(payload) != action["afterSha256"]:
                raise MigrationSafetyError(f"Planned output changed for {action['projectId']}")
            _atomic_write(target, payload)
            changed_paths.append(target)
        for action in changing:
            target = docs / str(action["relativePath"])
            if _sha256_file(target) != action["afterSha256"]:
                raise MigrationSafetyError(f"Post-apply hash mismatch for {action['projectId']}")
    except Exception:
        for item in rollback_files:
            target = docs / item["targetRelative"]
            backup = backup_root / item["backupRelative"]
            _atomic_write(target, backup.read_bytes())
        raise

    result = deepcopy(selected_plan)
    result.update(
        {
            "mode": "apply",
            "applied": True,
            "changedProjectIds": [action["projectId"] for action in changing],
            "backupPath": str(backup_root),
            "manifestPath": str(backup_root / "manifest.sha256"),
            "rollbackCommand": f'"{sys.executable}" "{backup_root / "rollback_standalone_migration.py"}"',
            "workbooksTouched": [],
        }
    )
    _write_json(backup_root / "migration-result.json", result)
    return result


def _default_docs_dir() -> Path:
    configured = os.environ.get("SINGH360_DOCS_DIR")
    return Path(configured).expanduser() if configured else ROOT / ".docs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=_default_docs_dir(),
        help="Singh360 docs directory (default: SINGH360_DOCS_DIR or repository .docs)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the protected migration. Without this flag the command is read-only.",
    )
    args = parser.parse_args(argv)
    plan = build_migration_plan(args.docs_dir)
    try:
        report = apply_migration_plan(args.docs_dir, plan) if args.apply else plan
    except MigrationSafetyError as exc:
        report = {**plan, "mode": "apply", "applied": False, "error": str(exc)}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("safeToApply") else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARCHIVED_MI_TIENDA_NAME",
    "CANONICAL_MI_TIENDA_ID",
    "CANONICAL_MI_TIENDA_NAME",
    "LEGACY_MI_TIENDA_ID",
    "MigrationSafetyError",
    "PROTECTED_PROJECTS",
    "SA31_ID",
    "apply_migration_plan",
    "build_migration_plan",
    "main",
]
