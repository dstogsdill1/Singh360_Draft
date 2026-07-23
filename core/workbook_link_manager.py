from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback
from typing import Any

from openpyxl import load_workbook

from core.workbook_status_sync import (
    WorkbookSyncError,
    file_hash,
    project_hash,
    sync_project_from_workbook,
    sync_project_to_workbook,
)


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_path(value: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(str(value or "").strip().strip('"')))
    if not expanded:
        raise WorkbookSyncError("No workbook path was provided.")
    return Path(expanded)


def internal_workbook_path(store: Any, project_id: str, project: dict[str, Any]) -> Path | None:
    folder = store.sources_dir(project_id, "workbook", project)
    preferred = str(project.get("sourceWorkbookName") or project.get("metadata", {}).get("sourceFile") or "").strip()
    if preferred:
        candidate = folder / Path(preferred).name
        if candidate.is_file():
            return candidate
    files = sorted(
        [*folder.glob("*.xlsx"), *folder.glob("*.xlsm")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def configured_workbook_path(store: Any, project_id: str, project: dict[str, Any]) -> tuple[Path | None, str]:
    sync = project.get("workbookSync") if isinstance(project.get("workbookSync"), dict) else {}
    configured = str(sync.get("workbook") or "").strip()
    if configured:
        return normalize_path(configured), "external"
    internal = internal_workbook_path(store, project_id, project)
    return internal, "internal" if internal else "none"


def workbook_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise WorkbookSyncError(f"The linked workbook was not found: {path}")
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise WorkbookSyncError("The linked file must be an .xlsx or .xlsm workbook.")
    try:
        wb = load_workbook(path, read_only=True, data_only=False, keep_vba=path.suffix.lower() == ".xlsm")
    except PermissionError as exc:
        raise WorkbookSyncError("The linked workbook is open or locked. Close Excel and try again.") from exc
    except Exception as exc:
        raise WorkbookSyncError(f"The linked workbook could not be read: {exc}") from exc
    try:
        if "00_PROJECT_META" not in wb.sheetnames or "00_INDEX" not in wb.sheetnames:
            raise WorkbookSyncError("This is not a Singh360 workbook. It must contain 00_PROJECT_META and 00_INDEX.")
        meta: dict[str, str] = {}
        ws = wb["00_PROJECT_META"]
        for row_number, row in enumerate(
            ws.iter_rows(min_row=1, min_col=1, max_col=2, values_only=True),
            start=1,
        ):
            if row_number > 80:
                break
            key = str(row[0] or "").strip()
            if key:
                meta[key.casefold()] = str(row[1] or "").strip()
        return {
            "path": str(path),
            "filename": path.name,
            "sheetCount": len(wb.sheetnames),
            "projectId": meta.get("linked project id", ""),
            "schemaVersion": meta.get("workbook schema version", ""),
            "helpVersion": meta.get("help version", ""),
            "projectName": meta.get("project name", "") or meta.get("project", ""),
            "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "size": path.stat().st_size,
            "sha256": file_hash(path),
        }
    finally:
        wb.close()


def status_payload(project_id: str, project: dict[str, Any], store: Any) -> dict[str, Any]:
    path, mode = configured_workbook_path(store, project_id, project)
    sync = project.get("workbookSync") if isinstance(project.get("workbookSync"), dict) else {}
    if path is None:
        return {
            "ok": True,
            "status": "not_linked",
            "mode": "none",
            "path": "",
            "message": "No workbook is linked. Choose the project workbook.",
        }
    if not path.is_file():
        return {
            "ok": True,
            "status": "missing",
            "mode": mode,
            "path": str(path),
            "message": "The linked workbook moved, was renamed, or is unavailable.",
        }
    try:
        meta = workbook_metadata(path)
    except WorkbookSyncError as exc:
        message = str(exc)
        status = "locked" if "open or locked" in message else "invalid"
        return {"ok": True, "status": status, "mode": mode, "path": str(path), "message": message}

    baseline_workbook = str(sync.get("workbookHash") or "")
    baseline_app = str(sync.get("appHash") or "")
    current_workbook = meta["sha256"]
    current_app = project_hash(project)

    if not baseline_workbook or not baseline_app:
        status = "review_required"
        message = "Workbook linked. Choose which version should establish the first synchronization."
    else:
        workbook_changed = current_workbook != baseline_workbook
        app_changed = current_app != baseline_app
        if workbook_changed and app_changed:
            status = "conflict"
            message = "Both the workbook and the app changed after the last sync."
        elif workbook_changed:
            status = "workbook_changed"
            message = "The workbook changed and can update the app."
        elif app_changed:
            status = "app_changed"
            message = "The app changed and can update the workbook."
        else:
            status = "in_sync"
            message = "The project and workbook match."

    project_meta_id = str(meta.get("projectId") or "")
    if project_meta_id and project_meta_id != project_id:
        status = "project_mismatch"
        message = f"The workbook is linked to project {project_meta_id}, not {project_id}."

    return {
        "ok": True,
        "status": status,
        "mode": mode,
        "path": str(path),
        "message": message,
        "workbook": meta,
        "baselineWorkbookHash": baseline_workbook,
        "baselineAppHash": baseline_app,
        "currentWorkbookHash": current_workbook,
        "currentAppHash": current_app,
        "lastSyncUtc": sync.get("lastSyncUtc", ""),
        "warning": sync.get("warning", ""),
    }


def _project_name(value: Any) -> str:
    return str(value or "").strip()


def _project_name_key(value: Any) -> str:
    return "".join(ch.lower() for ch in _project_name(value) if ch.isalnum())


def _current_project_name(project: dict[str, Any]) -> str:
    metadata = project.get("metadata") if isinstance(project.get("metadata"), dict) else {}
    return (
        _project_name(project.get("projectDisplayName"))
        or _project_name(metadata.get("projectName"))
        or _project_name(metadata.get("project"))
    )


def _validate_workbook_project_name(project: dict[str, Any], meta: dict[str, Any]) -> None:
    workbook_name = _project_name(meta.get("projectName"))
    current_name = _current_project_name(project)
    if not workbook_name or not current_name:
        return
    workbook_key = _project_name_key(workbook_name)
    current_key = _project_name_key(current_name)
    if workbook_key and current_key and workbook_key != current_key:
        raise WorkbookSyncError(
            "The selected workbook appears to belong to a different project. "
            f"Active project: {current_name}. Workbook project: {workbook_name}. "
            "Select the correct project on the left before confirming the workbook."
        )


def set_link(project_id: str, project: dict[str, Any], store: Any, path_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = normalize_path(path_value)
    meta = workbook_metadata(path)
    _validate_workbook_project_name(project, meta)
    project = dict(project)
    sync = dict(project.get("workbookSync") or {})
    sync.update({
        "mode": "external-workbook-link",
        "workbook": str(path),
        "status": "review_required",
        "linkedAt": utcnow(),
        "warning": "",
        "workbookHash": "",
        "appHash": "",
    })
    project["workbookSync"] = sync
    project["sourceWorkbookName"] = path.name
    # Keep the human-facing project identity tied to the real external file,
    # never the disposable temp_<project-id>.xlsx parser name.
    metadata = dict(project.get("metadata") or {})
    metadata["sourceFile"] = path.name
    project["metadata"] = metadata
    sources = list(project.get("sources") or [])
    for source in sources:
        if isinstance(source, dict) and str(source.get("type") or "").lower() == "workbook":
            source["name"] = path.name
            source["path"] = str(path)
    project["sources"] = sources

    # Keep a recovery copy inside the project package. The external path remains authoritative.
    try:
        internal = store.sources_dir(project_id, "workbook", project) / path.name
        if internal.resolve() != path.resolve():
            shutil.copy2(path, internal)
    except OSError:
        pass

    store.save(project_id, project)
    return project, status_payload(project_id, project, store)


def unlink(project_id: str, project: dict[str, Any], store: Any) -> dict[str, Any]:
    project = dict(project)
    project["workbookSync"] = {
        "mode": "unlinked",
        "status": "not_linked",
        "warning": "",
        "lastSyncUtc": "",
        "workbookHash": "",
        "appHash": "",
    }
    store.save(project_id, project)
    return project


def _baseline(project: dict[str, Any], path: Path, status: str = "in_sync") -> dict[str, Any]:
    project = dict(project)
    sync = dict(project.get("workbookSync") or {})
    sync.update({
        "mode": sync.get("mode") or "external-workbook-link",
        "workbook": str(path),
        "status": status,
        "warning": "",
        "lastSyncUtc": utcnow(),
        "workbookHash": file_hash(path),
        "appHash": project_hash(project),
    })
    project["workbookSync"] = sync
    return project


def _trim_resolution_backups(folder: Path, keep: int = 20) -> None:
    if not folder.is_dir():
        return
    entries = sorted(
        [item for item in folder.iterdir() if item.is_dir()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for stale in entries[keep:]:
        shutil.rmtree(stale, ignore_errors=True)


def create_resolution_backup(
    project_id: str,
    project: dict[str, Any],
    store: Any,
    workbook_path: Path,
    direction: str,
) -> Path:
    """Create a matched project/workbook snapshot before either side is changed."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    root = store.docs / "backups" / "workbook_resolution" / project_id
    target = root / stamp
    target.mkdir(parents=True, exist_ok=False)

    project_folder = store.dir_for(project_id, project)
    project_json = project_folder / "project.json"
    if project_json.is_file():
        shutil.copy2(project_json, target / "project_before.json")
    else:
        (target / "project_before.json").write_text(
            json.dumps(project, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    shutil.copy2(workbook_path, target / f"workbook_before{workbook_path.suffix.lower()}")
    (target / "resolution_manifest.json").write_text(
        json.dumps(
            {
                "createdUtc": utcnow(),
                "projectId": project_id,
                "direction": direction,
                "workbook": str(workbook_path),
                "projectHash": project_hash(project),
                "workbookHash": file_hash(workbook_path),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _trim_resolution_backups(root)
    return target


def resolve(project_id: str, project: dict[str, Any], store: Any, direction: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path, _ = configured_workbook_path(store, project_id, project)
    if path is None or not path.is_file():
        raise WorkbookSyncError("The linked workbook is missing. Relocate it first.")
    if direction not in {"workbook_to_app", "app_to_workbook", "baseline"}:
        raise WorkbookSyncError("Unknown synchronization direction.")

    backup = create_resolution_backup(project_id, project, store, path, direction)

    if direction == "workbook_to_app":
        project = sync_project_from_workbook(project_id, project, store)
    elif direction == "app_to_workbook":
        project = sync_project_to_workbook(project_id, project, store)

    project = _baseline(project, path)
    sync = dict(project.get("workbookSync") or {})
    sync["lastResolutionBackup"] = str(backup)
    sync["lastResolutionDirection"] = direction
    project["workbookSync"] = sync
    store.save(project_id, project)
    status = status_payload(project_id, project, store)
    status["resolutionBackup"] = str(backup)
    status["resolutionDirection"] = direction
    return project, status


def sync_auto(project_id: str, project: dict[str, Any], store: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    status = status_payload(project_id, project, store)
    state = status["status"]
    if state == "workbook_changed":
        return resolve(project_id, project, store, "workbook_to_app")
    if state == "app_changed":
        return resolve(project_id, project, store, "app_to_workbook")
    if state == "in_sync":
        return project, status
    if state == "review_required":
        raise WorkbookSyncError("Choose Use Workbook or Use App to establish the first synchronization.")
    if state == "conflict":
        raise WorkbookSyncError("Both sides changed. Choose Use Workbook or Use App.")
    raise WorkbookSyncError(status.get("message") or "Workbook synchronization is unavailable.")


def maybe_pull_on_open(project_id: str, project: dict[str, Any], store: Any) -> dict[str, Any]:
    status = status_payload(project_id, project, store)
    if status["status"] == "workbook_changed":
        project, status = resolve(project_id, project, store, "workbook_to_app")
    project = dict(project)
    sync = dict(project.get("workbookSync") or {})
    sync.update({
        "status": status["status"],
        "warning": "" if status["status"] in {"in_sync", "workbook_changed"} else status.get("message", ""),
        "observedAt": utcnow(),
    })
    project["workbookSync"] = sync
    return project


def _record_runtime_sync_failure(
    store: Any,
    project_id: str,
    stage: str,
    exc: Exception,
) -> str:
    folder = store.docs / "patch_logs" / "workbook_sync_runtime"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{project_id}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    target.write_text(
        json.dumps(
            {
                "createdUtc": utcnow(),
                "projectId": project_id,
                "stage": stage,
                "exceptionType": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return str(target)


def _pending_after_local_save(
    project: dict[str, Any],
    reason: str,
    warning: str,
    log_path: str = "",
) -> dict[str, Any]:
    project = dict(project)
    project["workbookSync"] = {
        **dict(project.get("workbookSync") or {}),
        "status": "pending",
        "pendingReason": reason,
        "warning": warning,
        "runtimeLog": log_path,
        "localProjectSavedAt": utcnow(),
    }
    return project


def save_local_then_try_sync(project_id: str, project: dict[str, Any], store: Any) -> dict[str, Any]:
    """Save project.json first; external workbook failures can never return a failed app save."""
    store.save(project_id, project)

    try:
        status = status_payload(project_id, project, store)
    except Exception as exc:
        log_path = _record_runtime_sync_failure(store, project_id, "status", exc)
        project = _pending_after_local_save(
            project,
            "status_error",
            f"Project saved locally. Workbook status check failed: {type(exc).__name__}: {exc}",
            log_path,
        )
        store.save(project_id, project)
        return project

    state = status["status"]
    if state == "not_linked":
        project = dict(project)
        project["workbookSync"] = {
            **dict(project.get("workbookSync") or {}),
            "status": "not_linked",
            "warning": "",
        }
        store.save(project_id, project)
        return project

    # S360 FAST SAFE SAVE V12
    # A normal project save must not rewrite a large external workbook when
    # the page manifest already matches. That unnecessary write caused slow
    # saves, workbook locks, and false SAVE FAILED badges.
    if state == "in_sync":
        project = dict(project)
        project["workbookSync"] = {
            **dict(project.get("workbookSync") or {}),
            "status": "in_sync",
            "warning": "",
            "observedAt": utcnow(),
        }
        return project

    if state in {
        "missing",
        "locked",
        "invalid",
        "project_mismatch",
        "review_required",
        "conflict",
        "workbook_changed",
    }:
        project = _pending_after_local_save(
            project,
            state,
            status.get("message", ""),
        )
        store.save(project_id, project)
        return project

    if state != "app_changed":
        project = _pending_after_local_save(
            project,
            state,
            status.get("message", "Workbook synchronization requires review."),
        )
        store.save(project_id, project)
        return project

    try:
        project, _ = resolve(project_id, project, store, "app_to_workbook")
        return project
    except Exception as exc:
        log_path = _record_runtime_sync_failure(store, project_id, "write", exc)
        project = _pending_after_local_save(
            project,
            "workbook_write_error",
            f"Project saved locally. Workbook update is pending: {type(exc).__name__}: {exc}",
            log_path,
        )
        store.save(project_id, project)
        return project


def choose_path_native() -> str:
    """Open a Windows workbook picker in its own STA process.

    Flask handles requests on worker threads. tkinter can display a dialog from
    those threads and then fail during cleanup, which produced the HTML 500 after
    the user selected a valid G: drive workbook. A separate PowerShell STA
    process owns the Windows Forms dialog and returns only the selected path.
    """
    if os.name != "nt":
        raise WorkbookSyncError(
            "Native workbook browsing is available only in the local Windows application."
        )

    script = r"""
Add-Type -AssemblyName System.Windows.Forms
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = 'Choose the Singh360 project workbook'
$dialog.Filter = 'Excel workbooks (*.xlsx;*.xlsm)|*.xlsx;*.xlsm|All files (*.*)|*.*'
$dialog.CheckFileExists = $true
$dialog.CheckPathExists = $true
$dialog.Multiselect = $false
$dialog.RestoreDirectory = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Out.Write($dialog.FileName)
}
"""
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-STA",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise WorkbookSyncError(
            "The Windows workbook picker failed."
            + (f" {detail}" if detail else "")
        )
    return (completed.stdout or "").strip()


def open_workbook(path: Path) -> None:
    if not path.is_file():
        raise WorkbookSyncError(f"The linked workbook was not found: {path}")
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def reveal_workbook(path: Path) -> None:
    if not path.exists():
        raise WorkbookSyncError(f"The linked workbook was not found: {path}")
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", f"/select,{path}"])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
