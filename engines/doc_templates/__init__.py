"""engines/doc_templates — Stage 5: turn the ProjectModel into deliverable sheets.

Each template reads ONLY the canonical ProjectModel (core/model.py) and emits a
DiagramGraph (core/data_orchestrator) that the existing render engines turn into
.vsdx / .vson. One model -> many sheet types -> many formats.

Registry maps a deliverable key -> builder(model) -> DiagramGraph.
"""
from __future__ import annotations

from . import io_schedule, network_layout, floorplan_layout

REGISTRY = {
    "io_schedule": io_schedule.build,
    "network_layout": network_layout.build,
    "floorplan_layout": floorplan_layout.build,
}

__all__ = ["REGISTRY"]
