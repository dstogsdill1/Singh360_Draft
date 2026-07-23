from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    files = {
        "types": (root / "frontend/src/model/types.ts").read_text(encoding="utf-8"),
        "tabs": (root / "frontend/src/components/PageTabs.tsx").read_text(encoding="utf-8"),
        "sheets": (root / "frontend/src/components/SheetManager.tsx").read_text(encoding="utf-8"),
        "toolbar": (root / "frontend/src/components/ViewportToolbar.tsx").read_text(encoding="utf-8"),
        "doc": (root / "frontend/src/components/DocumentView.tsx").read_text(encoding="utf-8"),
        "app": (root / "frontend/src/App.tsx").read_text(encoding="utf-8"),
        "main": (root / "frontend/src/main.tsx").read_text(encoding="utf-8"),
        "server": (root / "server.py").read_text(encoding="utf-8"),
        "project_model": (root / "core/project_model.py").read_text(encoding="utf-8"),
        "package_index": (root / "frontend/src/model/packageIndex.ts").read_text(encoding="utf-8"),
        "sync": (root / "core/workbook_status_sync.py").read_text(encoding="utf-8"),
        "status": (root / "frontend/src/model/pageStatus.ts").read_text(encoding="utf-8"),
        "help": (root / "frontend/src/components/HelpCenter.tsx").read_text(encoding="utf-8"),
        "css": (root / "frontend/src/styles/statusHelp.css").read_text(encoding="utf-8"),
    }
    checks = {
        "fourStatuses": all(x in files["status"] for x in ("draft", "draft_confirmed", "public", "public_confirmed")),
        "includeSeparate": "status-excluded" in files["status"] and "Included in Drawing Set" in files["toolbar"],
        "excludedTabsVisible": "const visible = [...pages]" in files["tabs"] and "pages.filter((p) => p.include)" not in files["tabs"],
        "excludedOrderPreserved": "S360 EXCLUDED PAGES STAY IN POSITION" in files["package_index"],
        "sheetManagerStatus": "sheet-status-select" in files["sheets"],
        "toolbarStatus": "vt-issue-status" in files["toolbar"],
        "persistentHelp": "Open Help" in files["toolbar"] and "HelpCenter" in files["app"],
        "helpVersion": "2026.07.22-status-sync-1" in files["status"] and "2026.07.22-status-sync-1" in files["sync"],
        "getSync": "sync_project_from_workbook" in files["server"],
        "saveSync": "sync_project_to_workbook" in files["server"],
        "workbookSyncPreserved": "workbookSync" in files["project_model"],
        "workbookTabColors": "sheet_properties.tabColor" in files["sync"],
        "oneUserLock": ".workbook-status-sync.lock" in files["sync"],
        "workbookBackup": "workbook_status_sync" in files["sync"],
        "stylesheet": "statusHelp.css" in files["main"],
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
