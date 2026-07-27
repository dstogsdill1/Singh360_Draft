from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tabs = (root / "frontend/src/components/PageTabs.tsx").read_text(encoding="utf-8")
    css = (root / "frontend/src/styles/app.css").read_text(encoding="utf-8")

    assert "const navigator = (" in tabs
    assert tabs.count("{navigator}") >= 2
    assert 'className="page-tabs-controls page-tabs-controls-right"' in tabs
    assert tabs.count('title="Scroll tabs left"') >= 2
    assert tabs.count('title="Scroll tabs right"') >= 2
    assert "onClick={() => scroll(-1)}" in tabs
    assert "onClick={() => scroll(1)}" in tabs
    assert ".page-tabs-shell" in css
    assert ".page-tabs-controls-right .page-nav-popover" in css
    print("bottom tab controls source smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
