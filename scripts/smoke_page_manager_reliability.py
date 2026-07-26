from __future__ import annotations

import json
from pathlib import Path
import tempfile

import core.workbook_link_manager as link_manager


class FakeStore:
    def __init__(self, root: Path):
        self.docs = root / ".docs"
        self.docs.mkdir(parents=True, exist_ok=True)
        self.saved = []
    def save(self, project_id, project):
        self.saved.append(json.loads(json.dumps(project)))
        return self.docs / "project.json"
    def load(self, project_id):
        return json.loads(json.dumps(self.saved[-1])) if self.saved else None
    def sources_dir(self, project_id, kind, project=None):
        path = self.docs / "projects" / project_id / "sources" / kind
        path.mkdir(parents=True, exist_ok=True)
        return path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dashboard = (root / "frontend/src/components/ProjectDashboard.tsx").read_text(encoding="utf-8")
    modal = (root / "frontend/src/components/PageManagerModal.tsx").read_text(encoding="utf-8")
    client = (root / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    server = (root / "server.py").read_text(encoding="utf-8")
    workbook_sync = (root / "core/workbook_status_sync.py").read_text(encoding="utf-8")
    manager = (root / "core/workbook_link_manager.py").read_text(encoding="utf-8")

    original_status = link_manager.status_payload
    try:
        link_manager.status_payload = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("simulated workbook status failure")
        )
        with tempfile.TemporaryDirectory(prefix="s360_local_first_") as temp:
            store = FakeStore(Path(temp))
            project = {"id": "project123", "pages": [], "metadata": {}, "worksheets": []}
            try:
                saved = link_manager.save_local_then_try_sync("project123", project, store)
            except link_manager.WorkbookSyncError:
                saved = store.saved[-1]
            assert len(store.saved) >= 2
            assert saved["workbookSync"]["status"] == "pending"
            assert "Workbook save failed" in saved["workbookSync"]["warning"]
            assert Path(saved["workbookSync"]["runtimeLog"]).is_file()
    finally:
        link_manager.status_payload = original_status

    checks = {
        "dedicatedClient": "savePageInclusion" in client,
        "dedicatedRoute": "/page-inclusion" in server,
        "dashboardUsesDedicatedSave": "savePageInclusion(project.id" in dashboard,
        "dashboardDoesNotSaveFullProject": "await saveProject(next)" not in dashboard,
        "pageGridManager": "page-thumbnail-grid" in modal and "visiblePages.map" in modal,
        "readableCards": "Selected workbook" not in modal and "Open This Page in Editor" in modal,
        "clearSaveLabel": "Save Drawing Set Selection" in modal,
        "closeWithoutSaving": "Close Without Saving" in modal,
        "calcPropertiesAvailable": "CalcProperties" in workbook_sync,
        "catchAllWorkbookFailure": "except Exception as exc:" in manager and "_record_runtime_sync_failure" in manager,
        "localFirstFunctional": True,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
