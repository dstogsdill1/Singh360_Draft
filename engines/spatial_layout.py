"""engines/spatial_layout.py — 2D floor-plan placement (PinX/PinY).

Reverse-engineered from the HEB gold EMS .vsdx (Corpus Christi #069):
  * Sheets are Arch D (42x30 in), 1:1 scale, bottom-left origin.
  * Every shape is placed at an absolute center (PinX, PinY) in inches.
  * Equipment is grouped into spatial CLUSTERS on the canvas (IDF/MDF tables,
    rack areas, RTU rows) and wired with glued dynamic connectors.

This is the alternative to the org-chart `compute_layout` (depth-ranked tree).
Use it when you want shapes positioned on a 2D canvas — true to the gold sheets
and reusable for the SA#31 floor-plan overlays.

Placement strategy:
  1. Any node with a real anchor (node.x/node.y from spatial ingestion or a
     floor plan) keeps that absolute position — never overridden.
  2. Remaining nodes are packed by GROUP into rectangular clusters laid left to
     right, top to bottom, each cluster a tidy grid of shapes. Groups become
     visually distinct zones (like the gold's IDF/MDF/rack blocks).
"""
from __future__ import annotations

import math

import config
from core.data_orchestrator import DiagramGraph


def compute_spatial_layout(
    graph: DiagramGraph,
    page_w: float,
    page_h: float,
    margin: float = config.PAGE_MARGIN_IN,
    *,
    shape_w: float = config.SHAPE_W_IN,
    shape_h: float = config.SHAPE_H_IN,
    col_gap: float = config.COL_GAP_IN,
    row_gap: float = config.ROW_GAP_IN,
    cluster_gap: float = 1.4,
) -> dict[str, tuple[float, float, float, float]]:
    """Return {node_id: (cx, cy, w, h)} in inches, placed on a 2D canvas.

    cx/cy are shape CENTERS (PinX/PinY semantics), origin bottom-left.
    """
    coords: dict[str, tuple[float, float, float, float]] = {}

    # 1) keep real anchors
    free: list = []
    for nid, node in graph.nodes.items():
        if node.x is not None and node.y is not None:
            coords[nid] = (node.x, node.y, node.w or shape_w, node.h or shape_h)
        else:
            free.append((nid, node))
    if not free:
        return coords

    # 2) group the rest into clusters
    groups: dict[str, list] = {}
    for nid, node in free:
        gname = node.group or node.category or "Items"
        groups.setdefault(gname, []).append((nid, node))

    usable_w = page_w - 2 * margin
    cell_w = shape_w + col_gap
    cell_h = shape_h + row_gap

    # Cursor walks left->right, top->down placing whole clusters.
    cur_x = margin
    cur_y = page_h - margin            # top edge (we go downward)
    row_max_h = 0.0

    for gname in sorted(groups):
        members = sorted(groups[gname], key=lambda x: x[1].label.lower())
        n = len(members)
        # cluster grid: roughly square, capped to page width
        max_cols = max(1, int(usable_w // cell_w))
        cols = min(max_cols, max(1, int(math.ceil(math.sqrt(n)))))
        rows = int(math.ceil(n / cols))
        cluster_w = cols * cell_w
        cluster_h = rows * cell_h

        # wrap to a new row of clusters if this one overflows the page width
        if cur_x + cluster_w > page_w - margin and cur_x > margin:
            cur_x = margin
            cur_y -= row_max_h + cluster_gap
            row_max_h = 0.0

        # place members within the cluster (top-left of cluster = cur_x, cur_y)
        for idx, (nid, node) in enumerate(members):
            r = idx // cols
            c = idx % cols
            cx = cur_x + c * cell_w + shape_w / 2
            cy = cur_y - r * cell_h - shape_h / 2
            coords[nid] = (cx, cy, node.w or shape_w, node.h or shape_h)

        cur_x += cluster_w + cluster_gap
        row_max_h = max(row_max_h, cluster_h)

    return coords
