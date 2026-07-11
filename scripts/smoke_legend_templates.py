"""Smoke: legend template store save/list round-trip."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.legend_template_store import LegendTemplateStore


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    store = LegendTemplateStore(tmp)
    rows = [
        {"id": "li", "label": "LI — Leak Indicator Horn/Strobe", "componentId": "sym_li", "enabled": True},
        {"id": "da", "label": "DA — Door Open Horn/Strobe", "componentId": "sym_da", "enabled": True},
    ]
    entry = store.save_template(
        name="Refrigeration / WICP Symbols",
        category="refrigeration",
        title="Symbol Legend",
        rows=rows,
    )
    listed = store.list_templates()
    payload = store.get_template(entry["id"])
    problems: list[str] = []
    if len(listed) != 1:
        problems.append(f"expected 1 template, got {len(listed)}")
    if not payload or len(payload.get("rows") or []) != 2:
        problems.append("payload rows missing")
    if not store.delete_template(entry["id"]):
        problems.append("delete failed")
    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        raise SystemExit(1)
    print("OK — legend template save/list/delete round-trip")


if __name__ == "__main__":
    main()
