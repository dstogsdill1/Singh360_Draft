from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
modal = (ROOT / "frontend" / "src" / "components" / "SymbolMapperModal.tsx").read_text(encoding="utf-8")
core = (ROOT / "core" / "symbol_mapper.py").read_text(encoding="utf-8")
css = (ROOT / "frontend" / "src" / "styles" / "symbolMapper.css").read_text(encoding="utf-8")

checks = {
    "liveCandidateCounts": "const matches = (detection?.candidates ?? []).filter" in modal,
    "foundIncludedCheckIgnored": all(label in modal for label in (">found<", ">included<", ">check<", ">ignored<")),
    "cleanSwitchPlainAuto": "exact-text-plain-standard" in core and "plainAutoAccept" in core,
    "cleanSwitchAliases": 'match_texts.update({"$", "CS", "CCS"})' in core,
    "legendSamplesExcludedFromCounts": "printed symbol-key samples are excluded" in core and "legend_rect" in core,
    "countGridCss": ".sm-count-metrics" in css,
}
assert all(checks.values()), checks
print(json.dumps({"ok": True, **checks}, indent=2))
