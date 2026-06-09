"""core/validate.py — Stage 4: cross-check the model, flag gaps (no guessing).

Adds `review`/`blocked`/`info` flags to the model for things a human should
confirm before the documents go out:
  * relays with no load named
  * I/O points with no cable number
  * duplicate cable numbers on the same board
  * circuits/cases with no parent rack or suction group
  * nodes with no source provenance
This never edits data — it only reports.
"""
from __future__ import annotations

from collections import defaultdict

from core.model import ProjectModel, NodeKind, PointKind


def validate(model: ProjectModel) -> dict:
    counts = {"review": 0, "blocked": 0, "info": 0}
    before = len(model.flags)

    for node in model.nodes.values():
        # provenance
        if not node.source:
            model.flag("review", f"node '{node.name}' has no source provenance", node.id)

        cables: dict[str, int] = defaultdict(int)
        for p in node.points:
            if p.cable:
                cables[p.cable] += 1
            else:
                model.flag("review", f"{node.name}: point '{p.label}' has no cable number", node.id)
            if p.kind == PointKind.RELAY and not p.load:
                model.flag("review", f"{node.name}: relay '{p.label}' has no load named", node.id)
        for cable, c in cables.items():
            if c > 1:
                model.flag("review", f"{node.name}: cable #{cable} used {c} times", node.id)

        # topology: circuits should hang off a rack/suction group
        if node.kind == NodeKind.CIRCUIT and not node.parent:
            model.flag("review", f"circuit '{node.name}' is not tied to a rack/suction group", node.id)

    added = len(model.flags) - before
    for f in model.flags[before:]:
        counts[f.level] = counts.get(f.level, 0) + 1

    model.flag("info", f"Validation added {added} findings", "validate")
    return {"added": added, **counts}


def report(model: ProjectModel) -> str:
    lines = ["VALIDATION REPORT", "=" * 50]
    s = model.summary()
    lines.append(f"Project: {s['store'] or s['project_id'] or '(unnamed)'}")
    lines.append(f"Nodes: {s['nodes']}  Points: {s['points']}  Sources: {s['sources']}")
    lines.append("-" * 50)
    by_level = {"blocked": [], "review": [], "info": []}
    for f in model.flags:
        by_level.setdefault(f.level, []).append(f)
    for level in ("blocked", "review", "info"):
        items = by_level.get(level, [])
        if not items:
            continue
        lines.append(f"{level.upper()} ({len(items)})")
        for f in items[:40]:
            lines.append(f"  - {f.message}")
        if len(items) > 40:
            lines.append(f"  … and {len(items) - 40} more")
    return "\n".join(lines)
