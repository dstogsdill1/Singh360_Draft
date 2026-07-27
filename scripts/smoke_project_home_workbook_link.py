from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project_store import ProjectStore
from core.workbook_link_manager import set_link, status_payload
from tests.generated_fixtures import write_workbook


def main() -> int:
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    client = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    dash = (ROOT / "frontend/src/components/ProjectDashboard.tsx").read_text(encoding="utf-8")
    ribbon = (ROOT / "frontend/src/components/Ribbon.tsx").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    sync = (ROOT / "core/workbook_status_sync.py").read_text(encoding="utf-8")
    types = (ROOT / "frontend/src/model/types.ts").read_text(encoding="utf-8")
    start = (ROOT / "START_SINGH360_DRAFT.bat").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="s360_home_") as temp:
        folder = Path(temp)
        workbook = write_workbook(folder / "sanitized-project.xlsx")
        store = ProjectStore(folder / ".docs")
        project_id = "a1a1a1a1a1a1a1a1"
        project = {
            "id": project_id,
            "metadata": {"projectName": "Sanitized Regression Project"},
            "pages": [],
            "worksheets": [],
            "sources": [],
        }
        linked, state = set_link(project_id, project, store, str(workbook))
        assert state["status"] == "in_sync", state
        assert status_payload(project_id, linked, store)["path"] == str(workbook)

    checks = {
        "dashboardDefault": "appMode !== 'editor'" in app and "<ProjectDashboard" in app,
        "genericProjectHome": "window.history.replaceState({}, '', '/app')" in app,
        "dashboardTools": all(
            label in dash
            for label in (
                "Run Symbol Mapper",
                "Symbol Maker / Legend Builder",
                "Component Library Browser",
                "Drawing Set / Export PDF",
            )
        ),
        "externalLinkApi": "linkWorkbookPath" in client and "/workbook-link/pick" in client,
        "pickerSelectedPathType": "selectedPath?: string;" in client,
        "nativePickerRoute": "choose_workbook_path_native" in server,
        "browseReturnsPathOnly": "selectedPath" in server,
        "localFirstSave": "store.save(project_id, data)" in server and '"local_autosave"' in server,
        "controlledWorkbookSync": "maybe_pull_on_open(project_id, doc, store)" in server,
        "dedicatedAuthorityWrite": "save_local_then_try_sync(project_id, doc, store)" in server,
        "homeButton": "Project Home" in ribbon,
        "externalPathPreferred": "external-workbook-link" in sync or "workbookSync" in sync,
        "canonicalLauncher": "title Singh360 Draft" in start
        and "SINGH360_PORT=8766" in start
        and "http://127.0.0.1:8766/app" in start,
        "dashboardCss": "PROJECT HOME + EXTERNAL WORKBOOK LINK"
        in (ROOT / "frontend/src/styles/projectDashboard.css").read_text(encoding="utf-8"),
        "projectLastSavedType": "lastSavedAt?: string;" in types,
        "dashboardLastSaveFallback": "project.lastSavedAt || project.modified" in dash,
        "browseKeepsSelectedPath": "setLinkPath(selected)" in dash,
        "pendingWorkbookSelection": "Selected workbook — not linked yet" in dash,
        "projectMismatchGuard": "_validate_workbook_project_name"
        in (ROOT / "core/workbook_link_manager.py").read_text(encoding="utf-8"),
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
