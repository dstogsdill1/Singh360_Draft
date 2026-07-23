from __future__ import annotations

import json
from pathlib import Path
import tempfile

from openpyxl import Workbook

from core.workbook_link_manager import status_payload, set_link


class FakeStore:
    def __init__(self, root: Path):
        self.root = root
        self.docs = root / ".docs"
        self.docs.mkdir(parents=True, exist_ok=True)
    def dir_for(self, project_id, project=None):
        p = self.docs / "projects" / f"test__{project_id}"
        p.mkdir(parents=True, exist_ok=True)
        return p
    def sources_dir(self, project_id, kind, project=None):
        p = self.dir_for(project_id, project) / "sources" / kind
        p.mkdir(parents=True, exist_ok=True)
        return p
    def save(self, project_id, project):
        target = self.dir_for(project_id, project) / "project.json"
        target.write_text(json.dumps(project, indent=2), encoding="utf-8")
        return target


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    app_path = root / "frontend/src/App.tsx"
    repository_mode = app_path.is_file()
    app = app_path.read_text(encoding="utf-8") if repository_mode else ""
    client = (root / "frontend/src/api/client.ts").read_text(encoding="utf-8") if repository_mode else ""
    dash = (root / "frontend/src/components/ProjectDashboard.tsx").read_text(encoding="utf-8")
    ribbon = (root / "frontend/src/components/Ribbon.tsx").read_text(encoding="utf-8") if repository_mode else ""
    server = (root / "server.py").read_text(encoding="utf-8") if repository_mode else ""
    sync = (root / "core/workbook_status_sync.py").read_text(encoding="utf-8") if repository_mode else ""
    types = (root / "frontend/src/model/types.ts").read_text(encoding="utf-8") if repository_mode else ""
    start = (root / "start-local.ps1").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="s360_home_") as temp:
        folder = Path(temp)
        workbook = folder / "project.xlsx"
        wb = Workbook()
        wb.active.title = "00_PROJECT_META"
        wb.active["A1"], wb.active["B1"] = "Linked Project ID", "project123"
        wb.create_sheet("00_INDEX")
        wb.save(workbook)
        wb.close()

        store = FakeStore(folder)
        project = {
            "id": "project123",
            "metadata": {"projectName": "Test"},
            "pages": [],
            "worksheets": [],
        }
        linked, state = set_link("project123", project, store, str(workbook))
        assert state["status"] == "review_required", state
        assert status_payload("project123", linked, store)["path"] == str(workbook)

    checks = {
        "repositoryOrPayloadMode": True,
        "dashboardDefault": (not repository_mode) or ("appMode !== 'editor'" in app and "<ProjectDashboard" in app),
        "dashboardTools": all(x in dash for x in ("Run Symbol Mapper", "Build Symbol Legend", "Component Library", "Drawing Set / Export PDF")),
        "externalLinkApi": (not repository_mode) or ("linkWorkbookPath" in client and "/workbook-link/pick" in client),
        "nativePickerRoute": (not repository_mode) or "choose_workbook_path_native" in server,
        "localFirstSave": (not repository_mode) or "save_local_then_try_sync" in server,
        "structuralServerPatchApplied": (not repository_mode) or "maybe_pull_on_open(project_id, doc, store)" in server,
        "workbookFailureDoesNotReturn409": (not repository_mode) or "Workbook synchronization failed." not in server,
        "homeButton": (not repository_mode) or "Project Home" in ribbon,
        "externalPathPreferred": (not repository_mode) or ("external-workbook-link" in sync or "workbookSync" in sync),
        "fetchOnStart": "fetch origin --prune" in start and "pull --ff-only" in start,
        "dirtyTreeProtected": "Updates were fetched but not pulled over local work" in start,
        "dashboardCss": "PROJECT HOME + EXTERNAL WORKBOOK LINK" in (root / "frontend/src/styles/projectDashboard.css").read_text(encoding="utf-8"),
        "projectLastSavedType": (not repository_mode) or "lastSavedAt?: string;" in types,
        "dashboardLastSaveFallback": "project.lastSavedAt || project.modified" in dash,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
