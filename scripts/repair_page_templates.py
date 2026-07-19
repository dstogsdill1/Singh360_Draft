"""One-time repair for duplicate Singh360 page templates."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.page_template_store import PageTemplateStore


def main() -> int:
    docs = ROOT / ".docs"
    store = PageTemplateStore(docs)
    result = store.repair_duplicates()
    templates = store.list_templates()

    print(
        f"[OK] Page-template repair complete: "
        f"{result['kept']} kept, {result['removed']} duplicate/orphan file set(s) removed."
    )
    for template in templates:
        print(
            f"     {template.get('name')} "
            f"[{template.get('pageType')}] "
            f"thumbnail={'yes' if template.get('hasThumbnail') else 'no'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
