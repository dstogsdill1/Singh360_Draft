from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from core.workbook_quality_manager import audit_workbook, repair_workbook


class FakeStore:
    def __init__(self, root: Path):
        self.docs = root / ".docs"
        self.docs.mkdir(parents=True, exist_ok=True)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dash = (root / "frontend/src/components/ProjectDashboard.tsx").read_text(encoding="utf-8")
    manager = (root / "core/workbook_link_manager.py").read_text(encoding="utf-8")
    server = (root / "server.py").read_text(encoding="utf-8")
    app = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
    ai = (root / "docs/SINGH360_AI_ASSISTANT_GUIDE.md").read_text(encoding="utf-8")
    page_manager = (root / "frontend/src/components/PageManagerModal.tsx").read_text(encoding="utf-8")

    checks = {
        "safeSyncModal": "SyncDecisionModal" in dash,
        "noAmbiguousButtons": "Use Workbook → Update App" not in dash and "Use App → Update Workbook" not in dash,
        "resolutionBackups": "create_resolution_backup" in manager,
        "pageManager": "PageManagerModal" in dash and "Page Manager / Editor" in dash,
        "projectDelete": "DeleteProjectModal" in dash and "deleteProject" in dash,
        "workbookInspector": "WorkbookQualityModal" in dash and "Workbook Inspector / Repair" in dash,
        "aiGuide": "AI-Ready Instructions" in dash and "Exact project workflow" in ai,
        "deepLink": "S360 PAGE MANAGER DEEP LINK V1" in app,
        "qualityRoutes": "/workbook-quality" in server,
        "aiRoutes": "/api/docs/ai-guide" in server,
        "localFirstSave": "save_local_then_try_sync" in server,
        "legacyStringCompatibility": ".replaceAll(" not in page_manager and ".replace(/_/g, ' ')" in page_manager,
        "typedStatusCallback": "(letter: string)" in page_manager,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
