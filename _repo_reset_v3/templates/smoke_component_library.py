"""Current Singh360 Draft component-library smoke test."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SINGH360_SKIP_SERVE", "1")
os.environ.setdefault("SINGH360_PORT", "8766")

import server  # noqa: E402


def main() -> int:
    client = server.app.test_client()
    problems: list[str] = []

    response = client.get("/api/lib?includeLegacy=1")
    if response.status_code != 200:
        print(response.get_data(as_text=True))
        return 1

    payload = response.get_json() or {}
    components = payload.get("components") or []
    categories = payload.get("categories") or []
    connectors = payload.get("connectorStyles") or []

    if not components:
        problems.append("active LibraryV2 component list is empty")
    if not categories:
        problems.append("LibraryV2 categories are missing")

    usable = [
        c for c in components
        if c.get("sourceUrl") or c.get("edgeUrl") or c.get("bwUrl") or c.get("symbolUrl")
    ]
    if components and not usable:
        problems.append("components loaded, but none has a usable asset URL")

    catalog = client.get("/component-catalog")
    if catalog.status_code != 200:
        problems.append(f"/component-catalog returned {catalog.status_code}")

    published = ROOT / "docs" / "component-library" / "index.html"
    published_catalog = ROOT / "docs" / "component-library" / "catalog.json"
    if not published.is_file():
        problems.append("published docs/component-library/index.html is missing")
    if not published_catalog.is_file():
        problems.append("published docs/component-library/catalog.json is missing")

    print(
        f"LibraryV2 components={len(components)} usable={len(usable)} "
        f"categories={len(categories)} connectorStyles={len(connectors)}"
    )
    print(
        f"component-catalog={catalog.status_code} "
        f"publishedIndex={published.is_file()} publishedCatalog={published_catalog.is_file()}"
    )

    if problems:
        print("CURRENT COMPONENT LIBRARY PROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("OK: current Singh360 component library smoke passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
