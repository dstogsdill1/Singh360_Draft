from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.properties import CalcProperties

HELP_VERSION = "2026.07.22-status-sync-1"
SCHEMA_VERSION = "5.0"
STATUS_LABELS = {
    "draft": "Draft",
    "draft_confirmed": "Draft Confirmed",
    "public": "Public",
    "public_confirmed": "Public Confirmed",
}
TAB_COLORS = {
    "draft": "F28C28",
    "draft_confirmed": "76B852",
    "public": "2D7DD2",
    "public_confirmed": "14845A",
    "excluded": "9AA3AB",
    "control": "252C34",
    "help": "276FA8",
}
INDEX_HEADERS = [
    "Include", "Order", "Sheet Code", "Sheet Tab", "Page Title", "Family",
    "Page Type", "Notes", "Render Profile", "Split Mode", "Page ID",
    "Parent Page ID", "Issue Status", "Source Mode", "Sync Direction",
    "Last Sync UTC", "Workbook Hash", "App Hash",
]


class WorkbookSyncError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_status(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return raw if raw in STATUS_LABELS else "draft"


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def project_hash(project: dict[str, Any]) -> str:
    payload = {
        "metadata": project.get("metadata", {}),
        "pages": [
            {
                "id": p.get("id"),
                "order": p.get("order"),
                "include": p.get("include", True),
                "sheetCode": p.get("sheetCode"),
                "sheetTitle": p.get("sheetTitle"),
                "sheetTab": p.get("sheetTab"),
                "issueStatus": normalize_status(p.get("issueStatus")),
            }
            for p in project.get("pages", [])
            if isinstance(p, dict)
        ],
    }
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _workbook_path(store: Any, project_id: str, project: dict[str, Any]) -> Path | None:
    # S360 external-workbook-link path priority.
    sync = project.get('workbookSync') if isinstance(project.get('workbookSync'), dict) else {}
    configured = str(sync.get('workbook') or '').strip()
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured)))
    folder = store.sources_dir(project_id, "workbook", project)
    preferred = str(project.get("sourceWorkbookName") or project.get("metadata", {}).get("sourceFile") or "").strip()
    if preferred:
        candidate = folder / Path(preferred).name
        if candidate.is_file():
            return candidate
    files = sorted([*folder.glob("*.xlsx"), *folder.glob("*.xlsm")], key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


# S360 DEAD LOCK SELF-HEAL V13
def _pid_is_running(pid: int) -> bool:
    # Return True only when the recorded lock owner still exists.
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information,
                False,
                pid,
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        return False


@contextmanager
def _project_lock(store: Any, project_id: str, project: dict[str, Any]):
    project_dir = store.dir_for(project_id, project)
    project_dir.mkdir(parents=True, exist_ok=True)
    lock = project_dir / ".workbook-status-sync.lock"
    if lock.exists():
        age = datetime.now().timestamp() - lock.stat().st_mtime
        owner_pid = 0
        try:
            payload = json.loads(lock.read_text(encoding="utf-8"))
            owner_pid = int(payload.get("pid") or 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            owner_pid = 0

        # Keep a real active lock. Remove a dead-process lock immediately
        # instead of blocking the project for 30 minutes after a crash/close.
        if owner_pid and _pid_is_running(owner_pid) and age < 1800:
            raise WorkbookSyncError(
                f"Workbook sync is already running in process {owner_pid}. Lock: {lock}"
            )
        if not owner_pid and age < 30:
            raise WorkbookSyncError(
                f"Workbook sync lock was just created and cannot yet be verified. Lock: {lock}"
            )
        lock.unlink(missing_ok=True)
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"pid": os.getpid(), "created": utcnow()}, indent=2))
        yield
    finally:
        lock.unlink(missing_ok=True)


def _backup_workbook(path: Path, store: Any, project_id: str) -> Path:
    backup_dir = store.docs / "backups" / "workbook_status_sync" / project_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    target = backup_dir / f"{stamp}_{path.name}"
    shutil.copy2(path, target)
    backups = sorted(backup_dir.glob(f"*_{path.name}"), key=lambda p: p.name)
    for old in backups[:-20]:
        old.unlink(missing_ok=True)
    return target


def _headers(ws) -> dict[str, int]:
    result: dict[str, int] = {}
    for col in range(1, max(ws.max_column, len(INDEX_HEADERS)) + 1):
        value = str(ws.cell(4, col).value or "").strip()
        if value:
            result[value.casefold()] = col
    for idx, header in enumerate(INDEX_HEADERS, start=1):
        if header.casefold() not in result:
            ws.cell(4, idx, header)
            result[header.casefold()] = idx
    return result


def _ensure_help_sheet(wb) -> None:
    if "00_HELP" in wb.sheetnames:
        ws = wb["00_HELP"]
    else:
        ws = wb.create_sheet("00_HELP", 2)
    ws.sheet_properties.tabColor = TAB_COLORS["help"]
    ws["A1"] = "SINGH360 DRAFT — QUICK HELP"
    ws["A1"].font = Font(size=20, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="252C34")
    if "A1:J2" not in {str(rng) for rng in ws.merged_cells.ranges}:
        ws.merge_cells("A1:J2")
    ws["A3"] = f"Help version {HELP_VERSION}. This control tab never publishes."
    if "A3:J3" not in {str(rng) for rng in ws.merged_cells.ranges}:
        ws.merge_cells("A3:J3")
    ws["A5"] = "PAGE STATUS — FOUR DISTINCT STAGES"
    if "A5:J5" not in {str(rng) for rng in ws.merged_cells.ranges}:
        ws.merge_cells("A5:J5")
    ws["A5"].fill = PatternFill("solid", fgColor="F28C28")
    ws["A5"].font = Font(bold=True, color="FFFFFF")
    ws["A6"], ws["B6"], ws["C6"] = "Status", "Meaning", "Workbook tab"
    data = [
        ("Draft", "Initial creation and active development.", "Orange"),
        ("Draft Confirmed", "Engineer reviewed and confirmed the draft.", "Light green"),
        ("Public", "Approved to go out for bid or external review.", "Blue"),
        ("Public Confirmed", "Final approved publication before as-builts.", "Dark green"),
    ]
    for row, item in enumerate(data, start=7):
        for col, value in enumerate(item, start=1):
            ws.cell(row, col, value)
    ws["A12"] = "INCLUDE / EXCLUDE IS SEPARATE"
    if "A12:J12" not in {str(rng) for rng in ws.merged_cells.ranges}:
        ws.merge_cells("A12:J12")
    ws["A12"].fill = PatternFill("solid", fgColor="276FA8")
    ws["A12"].font = Font(bold=True, color="FFFFFF")
    ws["A13"] = "Include = YES"
    ws["B13"] = "Appears in Sheet Index, Page X of Y, and export."
    ws["A14"] = "Include = NO"
    ws["B14"] = "Remains visible/editable, turns gray, and is omitted from export."
    ws["A17"] = "Open detailed app help"
    ws["B17"] = "http://127.0.0.1:8766/app?help=1"
    ws["B17"].hyperlink = ws["B17"].value
    ws["B17"].style = "Hyperlink"
    ws["A19"] = "Documentation rule"
    ws["B19"] = "The app and workbook Help Version must match. Tests fail when workflow code changes without help updates."
    for col, width in {"A": 24, "B": 84, "C": 18}.items():
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=1, max_row=24, min_col=1, max_col=10):
        for cell in row:
            cell.alignment = Alignment(vertical="center", wrap_text=True)


def _ensure_meta(wb, project: dict[str, Any]) -> None:
    ws = wb["00_PROJECT_META"] if "00_PROJECT_META" in wb.sheetnames else wb.create_sheet("00_PROJECT_META", 0)
    ws.sheet_properties.tabColor = TAB_COLORS["control"]
    existing: dict[str, int] = {}
    for row in range(1, max(ws.max_row, 30) + 1):
        key = str(ws.cell(row, 1).value or "").strip()
        if key:
            existing[key.casefold()] = row
    values = {
        "Workbook Schema Version": SCHEMA_VERSION,
        "Help Version": HELP_VERSION,
        "Issue Status Model": "Draft | Draft Confirmed | Public | Public Confirmed",
        "Drawing Set Control": "Include / Exclude is separate from Issue Status",
        "Sync Mode": "One User / Two-Way Page Manifest",
        "Linked Project ID": project.get("id", ""),
        "Last Sync UTC": utcnow(),
        "Last Sync Status": "Synchronized",
    }
    next_row = max(ws.max_row + 1, 17)
    for key, value in values.items():
        row = existing.get(key.casefold())
        if row is None:
            row = next_row
            next_row += 1
        ws.cell(row, 1, key)
        ws.cell(row, 2, value)
    row = existing.get("open help", next_row)
    ws.cell(row, 1, "Open Help")
    ws.cell(row, 2, "OPEN HELP — PAGE 3")
    ws.cell(row, 2).hyperlink = "#'00_HELP'!A1"
    ws.cell(row, 2).style = "Hyperlink"


def _ensure_index(wb):
    ws = wb["00_INDEX"] if "00_INDEX" in wb.sheetnames else wb.create_sheet("00_INDEX", 1)
    ws.sheet_properties.tabColor = TAB_COLORS["control"]
    headers = _headers(ws)
    ws["A2"] = "Only explicit YES rows publish. Issue Status is separate. Excluded pages remain visible/editable and gray."
    ws["K2"] = "OPEN HELP — PAGE 3"
    ws["K2"].hyperlink = "#'00_HELP'!A1"
    ws["K2"].style = "Hyperlink"
    status_col = headers["issue status"]
    include_col = headers["include"]
    status_letter = ws.cell(4, status_col).column_letter
    include_letter = ws.cell(4, include_col).column_letter
    status_dv = DataValidation(type="list", formula1='"Draft,Draft Confirmed,Public,Public Confirmed"', allow_blank=False)
    include_dv = DataValidation(type="list", formula1='"YES,NO"', allow_blank=False)
    ws.add_data_validation(status_dv)
    ws.add_data_validation(include_dv)
    status_dv.add(f"{status_letter}5:{status_letter}500")
    include_dv.add(f"{include_letter}5:{include_letter}500")
    return ws, headers


def _row_maps(ws, headers: dict[str, int]):
    by_id: dict[str, int] = {}
    by_tab: dict[str, int] = {}
    for row in range(5, ws.max_row + 1):
        page_id = str(ws.cell(row, headers["page id"]).value or "").strip()
        tab = str(ws.cell(row, headers["sheet tab"]).value or "").strip()
        if page_id:
            by_id[page_id] = row
        if tab:
            by_tab[tab.casefold()] = row
    return by_id, by_tab


def _tab_color(include: bool, status: str) -> str:
    if not include:
        return TAB_COLORS["excluded"]
    return TAB_COLORS.get(status, TAB_COLORS["draft"])


def _safe_sheet_name(wb, requested: str) -> str:
    base = re.sub(r"[\\/*?:\[\]]", "-", requested or "APP PAGE").strip()[:31] or "APP PAGE"
    if base not in wb.sheetnames:
        return base
    index = 2
    while True:
        suffix = f" {index}"
        candidate = (base[: 31 - len(suffix)] + suffix).strip()
        if candidate not in wb.sheetnames:
            return candidate
        index += 1


def _write_companion_sheet(wb, page: dict[str, Any], project_id: str) -> str:
    requested = str(page.get("sheetTab") or page.get("sheetTitle") or "APP PAGE")
    tab = _safe_sheet_name(wb, requested)
    ws = wb.create_sheet(tab)
    ws["A1"] = "SINGH360 APP PAGE COMPANION"
    ws["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="252C34")
    ws.merge_cells("A1:H2")
    values = [
        ("Sheet Code", page.get("displaySheetCode") or page.get("sheetCode") or "NEW"),
        ("Page Title", page.get("sheetTitle") or "Untitled Sheet"),
        ("Page ID", page.get("id") or ""),
    ]
    for row, (label, value) in enumerate(values, start=4):
        ws.cell(row, 1, label)
        ws.cell(row, 2, value)
        ws.cell(row, 1).font = Font(bold=True)
        ws.cell(row, 1).fill = PatternFill("solid", fgColor="E6EBEF")
    ws["A8"] = "This page is managed in Singh360 Draft. Drawings, highlights, crops, and canvas objects remain app-owned."
    ws.merge_cells("A8:H10")
    ws["A12"] = "Open project"
    ws["B12"] = f"http://127.0.0.1:8766/app?project={project_id}"
    ws["B12"].hyperlink = ws["B12"].value
    ws["B12"].style = "Hyperlink"
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 65
    return tab


def sync_project_from_workbook(project_id: str, project: dict[str, Any], store: Any) -> dict[str, Any]:
    path = _workbook_path(store, project_id, project)
    if path is None:
        return project
    if not path.is_file():
        raise WorkbookSyncError(f'The linked workbook was not found: {path}')
    with _project_lock(store, project_id, project):
        try:
            wb = load_workbook(path, keep_vba=path.suffix.lower() == ".xlsm", data_only=False, read_only=False)
        except PermissionError as exc:
            raise WorkbookSyncError("The linked workbook is open or locked. Close Excel, then reopen the project.") from exc
        try:
            if "00_INDEX" not in wb.sheetnames:
                return project
            ws, headers = _ensure_index(wb)
            pages = deepcopy(project.get("pages", []))
            page_by_id = {str(p.get("id") or ""): p for p in pages if isinstance(p, dict) and p.get("id")}
            page_by_tab = {str(p.get("sheetTab") or "").casefold(): p for p in pages if isinstance(p, dict) and p.get("sheetTab")}
            changed = False
            for row in range(5, ws.max_row + 1):
                page_id = str(ws.cell(row, headers["page id"]).value or "").strip()
                tab = str(ws.cell(row, headers["sheet tab"]).value or "").strip()
                if not page_id and not tab:
                    continue
                page = page_by_id.get(page_id) or page_by_tab.get(tab.casefold())
                if page is None:
                    continue
                code = str(ws.cell(row, headers["sheet code"]).value or page.get("sheetCode") or "NEW")
                patch = {
                    "include": str(ws.cell(row, headers["include"]).value or "NO").strip().upper() == "YES",
                    "order": int(ws.cell(row, headers["order"]).value or page.get("order") or 9999),
                    "sheetCode": code,
                    "displaySheetCode": code,
                    "sheetTab": tab or page.get("sheetTab"),
                    "sheetTitle": str(ws.cell(row, headers["page title"]).value or page.get("sheetTitle") or "Untitled Sheet"),
                    "issueStatus": normalize_status(ws.cell(row, headers["issue status"]).value),
                    "parentPageId": str(ws.cell(row, headers["parent page id"]).value or ""),
                    "sourceMode": str(ws.cell(row, headers["source mode"]).value or "Workbook"),
                    "syncDirection": str(ws.cell(row, headers["sync direction"]).value or "Both"),
                }
                for key, value in patch.items():
                    if page.get(key) != value:
                        page[key] = value
                        changed = True
            project = {**project, "pages": sorted(pages, key=lambda p: int(p.get("order") or 9999))}
            project.setdefault("metadata", {})["helpVersion"] = HELP_VERSION
            project["workbookSync"] = {**dict(project.get("workbookSync") or {}),
                "mode": "one-user-two-way-manifest",
                "workbook": str(path),
                "lastSyncUtc": utcnow(),
                "workbookHash": file_hash(path),
                "appHash": project_hash(project),
            }
            if changed:
                store.save(project_id, project)
            return project
        finally:
            wb.close()


def sync_project_to_workbook(project_id: str, project: dict[str, Any], store: Any) -> dict[str, Any]:
    path = _workbook_path(store, project_id, project)
    if path is None:
        return project
    if not path.is_file():
        raise WorkbookSyncError(f'The linked workbook was not found: {path}')
    with _project_lock(store, project_id, project):
        _backup_workbook(path, store, project_id)
        try:
            wb = load_workbook(path, keep_vba=path.suffix.lower() == ".xlsm", data_only=False, read_only=False)
        except PermissionError as exc:
            raise WorkbookSyncError("The linked workbook is open or locked. Close Excel and save again.") from exc
        temp: Path | None = None
        try:
            _ensure_help_sheet(wb)
            _ensure_meta(wb, project)
            ws, headers = _ensure_index(wb)
            by_id, by_tab = _row_maps(ws, headers)
            stamp = utcnow()
            app_digest = project_hash(project)
            pages = sorted(project.get("pages", []), key=lambda p: int(p.get("order") or 9999))
            for order, page in enumerate(pages, start=1):
                if not isinstance(page, dict):
                    continue
                page_id = str(page.get("id") or "").strip()
                tab = str(page.get("sheetTab") or "").strip()
                row = by_id.get(page_id) or by_tab.get(tab.casefold())
                if row is None:
                    row = max(ws.max_row + 1, 5)
                if tab not in wb.sheetnames:
                    tab = _write_companion_sheet(wb, page, project_id)
                    page["sheetTab"] = tab
                include = bool(page.get("include", True))
                status = normalize_status(page.get("issueStatus"))
                values = {
                    "include": "YES" if include else "NO",
                    "order": order,
                    "sheet code": page.get("displaySheetCode") or page.get("sheetCode") or "NEW",
                    "sheet tab": tab,
                    "page title": page.get("sheetTitle") or "Untitled Sheet",
                    "family": page.get("pageFamily") or "",
                    "page type": page.get("pageType") or "",
                    "notes": page.get("notes") or "",
                    "render profile": page.get("renderProfile") or page.get("layoutProfile") or "",
                    "split mode": page.get("splitMode") or "",
                    "page id": page_id,
                    "parent page id": page.get("parentPageId") or "",
                    "issue status": STATUS_LABELS[status],
                    "source mode": page.get("sourceMode") or ("Workbook" if page.get("linkedWorksheetId") else "App"),
                    "sync direction": page.get("syncDirection") or "Both",
                    "last sync utc": stamp,
                    "app hash": app_digest,
                }
                for key, value in values.items():
                    ws.cell(row, headers[key], value)
                wb[tab].sheet_properties.tabColor = _tab_color(include, status)

            for control in ("00_PROJECT_META", "00_INDEX"):
                if control in wb.sheetnames:
                    wb[control].sheet_properties.tabColor = TAB_COLORS["control"]
            if "00_HELP" in wb.sheetnames:
                wb["00_HELP"].sheet_properties.tabColor = TAB_COLORS["help"]
            control_names = [name for name in ("00_PROJECT_META", "00_INDEX", "00_HELP") if name in wb.sheetnames]
            page_names = [str(p.get("sheetTab") or "") for p in pages if str(p.get("sheetTab") or "") in wb.sheetnames]
            remaining = [name for name in wb.sheetnames if name not in control_names and name not in page_names]
            wb._sheets = [wb[name] for name in control_names + page_names + remaining]
            if wb.calculation is None:
                wb.calculation = CalcProperties(
                    calcMode="auto",
                    fullCalcOnLoad=True,
                    forceFullCalc=True,
                )
            else:
                wb.calculation.fullCalcOnLoad = True
                wb.calculation.forceFullCalc = True
                wb.calculation.calcMode = "auto"

            fd, temp_name = tempfile.mkstemp(prefix=path.stem + "_", suffix=path.suffix, dir=path.parent)
            os.close(fd)
            temp = Path(temp_name)
            wb.save(temp)
            os.replace(temp, path)
            temp = None

            project.setdefault("metadata", {})["helpVersion"] = HELP_VERSION
            project["workbookSync"] = {**dict(project.get("workbookSync") or {}),
                "mode": "one-user-two-way-manifest",
                "workbook": str(path),
                "lastSyncUtc": stamp,
                "workbookHash": file_hash(path),
                "appHash": app_digest,
            }
            return project
        except PermissionError as exc:
            raise WorkbookSyncError("The linked workbook is open or locked. Close Excel and save again.") from exc
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
            wb.close()
