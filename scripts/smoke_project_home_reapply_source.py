from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    server = (root / "server.py").read_text(encoding="utf-8")
    checks = {
        "managerImport": "from core.workbook_link_manager import (" in server,
        "localFirstSave": "store.save(project_id, data)" in server and '"local_autosave"' in server,
        "explicitWorkbookSync": "save_local_then_try_sync(project_id, doc, store)" in server,
        "openSync": "maybe_pull_on_open(project_id, doc, store)" in server,
        "noBlocking409": "Workbook synchronization failed." not in server,
        "routes": "/workbook-link" in server,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    print(json.dumps({"ok": True, **checks}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
