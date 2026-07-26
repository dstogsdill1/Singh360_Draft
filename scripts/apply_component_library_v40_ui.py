#!/usr/bin/env python3
"""Apply the scoped V40 Component Library UI integration.

This patcher is intentionally idempotent and uniquely anchored. It is used by
CI and by the controlled Windows installer until the generated source changes
are committed from the verified live installation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: anchor count was {count}, expected 1")
    return text.replace(old, new, 1)


def verify(root: Path) -> dict[str, Any]:
    panel_path = root / "frontend" / "src" / "components" / "LibraryPanelV2.tsx"
    modal_path = root / "frontend" / "src" / "components" / "SymbolLegendModal.tsx"
    panel = panel_path.read_text(encoding="utf-8")
    modal = modal_path.read_text(encoding="utf-8")
    required_panel = [
        "const MAPPER_SYMBOL_COLLECTION = 'Refrigeration Controls Symbols';",
        "const PLAN_MARKER_COLLECTION = 'Singh360 Plan Markers';",
        "Mapper Highlights ({mapperSymbolCount})",
        "Plan Markers ({planMarkerCount})",
        "singh360-plan-marker-legend",
    ]
    required_modal = [
        "stringField(item, 'symbolUrl') ||",
        "exact library assets linked",
    ]
    missing = [token for token in required_panel if token not in panel]
    missing.extend(token for token in required_modal if token not in modal)
    if missing:
        raise PatchError(f"V40 UI integration is incomplete: {missing}")
    return {
        "ok": True,
        "panel": str(panel_path),
        "modal": str(modal_path),
        "mapperQuickFilter": True,
        "planMarkerQuickFilter": True,
        "savedLegendExactAssetSupport": True,
    }


def apply(root: Path) -> dict[str, Any]:
    panel_path = root / "frontend" / "src" / "components" / "LibraryPanelV2.tsx"
    modal_path = root / "frontend" / "src" / "components" / "SymbolLegendModal.tsx"
    if not panel_path.is_file() or not modal_path.is_file():
        raise PatchError("V40 UI source files were not found.")

    panel = panel_path.read_text(encoding="utf-8")
    panel_changed = False
    if "const PLAN_MARKER_COLLECTION = 'Singh360 Plan Markers';" not in panel:
        panel = replace_once(
            panel,
            "const REFRIGERATION_SYMBOL_COLLECTION = 'Refrigeration Controls Symbols';",
            "const MAPPER_SYMBOL_COLLECTION = 'Refrigeration Controls Symbols';\n"
            "const PLAN_MARKER_COLLECTION = 'Singh360 Plan Markers';",
            "collection constants",
        )
        panel = replace_once(
            panel,
            "  'Symbols / Markers',\n  'Needs Review',",
            "  'Symbols / Markers',\n"
            "  'Refrigeration Controls Symbols',\n"
            "  'Singh360 Plan Markers',\n"
            "  'Safety Signage',\n"
            "  'Callout Numbers',\n"
            "  'Needs Review',",
            "collection presets",
        )
        panel = replace_once(
            panel,
            """  const refrigerationSymbolCount = useMemo(
    () => components.filter(
      (component) => !isRetired(component)
        && collectionFor(component) === REFRIGERATION_SYMBOL_COLLECTION,
    ).length,
    [components],
  );
""",
            """  const mapperSymbolCount = useMemo(
    () => components.filter(
      (component) => !isRetired(component)
        && collectionFor(component) === MAPPER_SYMBOL_COLLECTION,
    ).length,
    [components],
  );
  const planMarkerCount = useMemo(
    () => components.filter(
      (component) => !isRetired(component)
        && collectionFor(component) === PLAN_MARKER_COLLECTION,
    ).length,
    [components],
  );
""",
            "collection counts",
        )
        panel = replace_once(
            panel,
            """        <div className="libv2-row libv2-quick-filters">
          <button
            className={collection === REFRIGERATION_SYMBOL_COLLECTION ? 'active' : undefined}
            style={collection === REFRIGERATION_SYMBOL_COLLECTION
              ? { fontWeight: 800, background: '#e0f2fe', borderColor: '#0284c7' }
              : undefined}
            aria-pressed={collection === REFRIGERATION_SYMBOL_COLLECTION}
            onClick={() => {
              setCollection((current) => current === REFRIGERATION_SYMBOL_COLLECTION
                ? 'all'
                : REFRIGERATION_SYMBOL_COLLECTION);
              setCategory('all');
              setQuery('');
            }}
          >
            Refrigeration Symbols ({refrigerationSymbolCount})
          </button>
          {collection !== 'all' && (
            <button onClick={() => setCollection('all')}>Show All Components</button>
          )}
        </div>
""",
            """        <div className="libv2-row libv2-quick-filters">
          <button
            className={collection === MAPPER_SYMBOL_COLLECTION ? 'active' : undefined}
            aria-pressed={collection === MAPPER_SYMBOL_COLLECTION}
            title="Square highlighted symbols used by Symbol Mapper on existing drawings"
            onClick={() => {
              setCollection((current) => current === MAPPER_SYMBOL_COLLECTION ? 'all' : MAPPER_SYMBOL_COLLECTION);
              setCategory('all');
              setQuery('');
            }}
          >
            Mapper Highlights ({mapperSymbolCount})
          </button>
          <button
            className={collection === PLAN_MARKER_COLLECTION ? 'active' : undefined}
            aria-pressed={collection === PLAN_MARKER_COLLECTION}
            title="Simple colored-ring markers for direct placement on plan and layout pages"
            onClick={() => {
              setCollection((current) => current === PLAN_MARKER_COLLECTION ? 'all' : PLAN_MARKER_COLLECTION);
              setCategory('all');
              setQuery('');
            }}
          >
            Plan Markers ({planMarkerCount})
          </button>
          {collection !== 'all' && (
            <button onClick={() => setCollection('all')}>Show All Components</button>
          )}
        </div>
""",
            "quick filters",
        )
        panel = replace_once(
            panel,
            """  const preferredLegendTemplate = legendTemplates.find((template) => template.id === 'singh360-refrigeration-symbols-standard')
    || legendTemplates.find((template) => template.name === 'Singh360 Refrigeration Symbols')
    || legendTemplates[0];
""",
            """  const preferredLegendTemplate = legendTemplates.find((template) => template.id === 'singh360-plan-marker-legend')
    || legendTemplates.find((template) => template.id === 'singh360-refrigeration-symbols-standard')
    || legendTemplates[0];
""",
            "preferred legend",
        )
        panel_path.write_text(panel, encoding="utf-8")
        panel_changed = True

    modal = modal_path.read_text(encoding="utf-8")
    modal_changed = False
    old_symbol_url = "symbolUrl: rendererVersion === CANONICAL_RENDERER ? assets.get(key) : undefined,"
    new_symbol_url = "symbolUrl: stringField(item, 'symbolUrl') || (rendererVersion === CANONICAL_RENDERER ? assets.get(key) : undefined),"
    if new_symbol_url not in modal:
        modal = replace_once(modal, old_symbol_url, new_symbol_url, "saved legend exact asset")
        modal_changed = True
    old_status = "`${template.name || 'Saved legend'} loaded · ${next.length} symbols · exact V39 assets linked`"
    new_status = "`${template.name || 'Saved legend'} loaded · ${next.length} symbols · exact library assets linked`"
    if new_status not in modal:
        modal = replace_once(modal, old_status, new_status, "saved legend status")
        modal_changed = True
    if modal_changed:
        modal_path.write_text(modal, encoding="utf-8")

    result = verify(root)
    result.update({"panelChanged": panel_changed, "modalChanged": modal_changed})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    result = verify(root) if args.check else apply(root)
    text = json.dumps(result, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"PATCH ERROR: {exc}")
        raise SystemExit(2)
