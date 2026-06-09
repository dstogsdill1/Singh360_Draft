"""extractors/lighting_plan.py — vector lighting / EMS controls plan PDFs.

THE SPATIAL BREAKTHROUGH (reverse-engineered from HEB #109 Bunker Hills).

A lighting "EMS CONTROLS PLAN" sheet is a vector PDF drawn to scale on an
Arch D sheet (3024 x 2160 pt == 42 x 30 in at 72 dpi). It carries two kinds of
deterministically-extractable spatial anchors:

  * LCP zone markers — text like "LCP-1" .. "LCP-4" placed across the floor at
    the spots each Lighting Control Panel governs. Many instances per panel.
  * Fixture-type tags — short codes (B1, T10, FN12, UL924, ...) marking lit
    locations and the egress/exit fixtures.

We pull each marker's PDF coordinate and convert it to Visio/Arch-D inches with
a bottom-left origin (Y is flipped), so the panels and their controlled zones
can be overlaid on the canvas at ABSOLUTE positions — the prep step for SA#31.

Output into the shared ProjectModel:
  * one PANEL node per distinct LCP, placed at the centroid of its markers
  * one LIGHTING zone node per marker instance, parented to its LCP, at the
    marker's true X/Y (inches)
  * one LIGHTING node per distinct fixture-type tag (legend), with the first
    seen X/Y, count carried in attrs

Coordinates live in node.attrs as "x"/"y" (inches, bottom-left origin) so they
survive JSON round-trips and flow through floorplan_layout -> spatial_layout.

No-hallucination rule: only text actually printed on the sheet becomes a node.
Bitmap-only sheets (no vector text) are flagged for the Azure DI path.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.model import ProjectModel, Node, NodeKind, slug

import config

# 72 pt == 1 in. Arch D landscape.
_PT_PER_IN = 72.0

# "LCP-1", 'LCP 2', "LCP#3", quoted or not.
_LCP_RE = re.compile(r'LCP[\s#\-]*?(\d{1,2})', re.I)
# fixture-type tag: 1-3 letters + 1-3 digits + optional trailing letter (B1, T10, FN12, UL924)
_FIX_RE = re.compile(r'^[A-Z]{1,3}\d{1,3}[A-Z]?$')
# tokens that look like tags but are really notes/dimensions we don't want
_FIX_SKIP = {"E1", "E5", "DE1"}  # sheet numbers, not fixtures


def extract(path: str | Path, model: ProjectModel) -> None:
    path = Path(path)
    model.note_source(str(path))
    try:
        import fitz  # PyMuPDF
    except ImportError:
        model.flag("review", f"{path.name}: install PyMuPDF to read lighting plans", path.name)
        return

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        model.flag("blocked", f"could not open {path.name}: {exc}", path.name)
        return

    # Pass 1: collect every marker's RAW pdf-point coordinate (top-left origin).
    raw_lcp: dict[str, list[tuple[float, float, int]]] = {}   # name -> [(px, py, page)]
    raw_fix: dict[str, list[tuple[float, float, int]]] = {}   # tag  -> [(px, py, page)]
    total_words = 0
    all_pts: list[tuple[float, float]] = []

    for pno in range(doc.page_count):
        page = doc[pno]
        try:
            words = page.get_text("words")
        except Exception:  # noqa: BLE001
            continue
        total_words += len(words)
        for w in words:
            x0, y0, x1, y1, tok = w[0], w[1], w[2], w[3], w[4].strip()
            if not tok:
                continue
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            m = _LCP_RE.search(tok)
            if m:
                name = f"LCP-{int(m.group(1))}"
                raw_lcp.setdefault(name, []).append((cx, cy, pno + 1))
                all_pts.append((cx, cy))
                continue
            up = tok.upper()
            if _FIX_RE.match(up) and up not in _FIX_SKIP:
                raw_fix.setdefault(up, []).append((cx, cy, pno + 1))
                all_pts.append((cx, cy))

    doc.close()

    if total_words == 0:
        model.flag(
            "blocked",
            f"{path.name}: no vector text — bitmap lighting plan, route to Azure DI",
            path.name,
        )
        return

    if not all_pts:
        model.flag(
            "review",
            f"{path.name}: vector text present but no LCP/fixture tags matched — verify naming",
            path.name,
        )
        return

    # Fit the markers' true bounding box onto the Arch D drawing area so every
    # marker lands on the sheet while preserving exact RELATIVE geometry. The
    # source PDFs are drawn 1:1 to Arch D but the text layer's origin is not
    # always the page origin, so a proportional fit (not a naive /72) is the
    # deterministic, on-canvas-safe mapping. Y is flipped (bottom-left origin).
    page_w, page_h = config.page_size("archd")
    margin = config.PAGE_MARGIN_IN
    fit = _Fit(all_pts, page_w, page_h, margin)

    # --- LCP panels + their controlled zones -----------------------------
    placed_zones = 0
    for name, hits in sorted(raw_lcp.items()):
        pts = [fit.map(px, py) for px, py, _ in hits]
        cx = round(sum(p[0] for p in pts) / len(pts), 3)
        cy = round(sum(p[1] for p in pts) / len(pts), 3)
        panel_id = slug("lcp", name)
        model.add_node(Node(
            id=panel_id, kind=NodeKind.PANEL, name=name,
            attrs={
                "kind": "lcp", "control_type": "Lighting Control Panel",
                "zones": str(len(hits)), "x": str(cx), "y": str(cy),
            },
            source=f"{path.name} (centroid of {len(hits)} markers)",
        ))
        for i, (px, py, pg) in enumerate(hits, 1):
            xi, yi = fit.map(px, py)
            model.add_node(Node(
                id=slug("lzone", name, str(i)),
                kind=NodeKind.LIGHTING, name=f"{name} zone {i}",
                parent=panel_id,
                attrs={"kind": "lighting_zone", "lcp": name,
                       "x": str(round(xi, 3)), "y": str(round(yi, 3))},
                source=f"{path.name} p{pg}",
            ))
            placed_zones += 1

    # --- fixture-type tags (legend / egress) -----------------------------
    for tag, hits in sorted(raw_fix.items()):
        px, py, pg = hits[0]
        xi, yi = fit.map(px, py)
        model.add_node(Node(
            id=slug("fixture", tag),
            kind=NodeKind.LIGHTING, name=tag,
            attrs={"kind": "fixture", "fixture_type": tag,
                   "count": str(len(hits)),
                   "x": str(round(xi, 3)), "y": str(round(yi, 3))},
            source=f"{path.name} p{pg}",
        ))

    n_lcp = len(raw_lcp)
    n_fix = len(raw_fix)
    model.flag(
        "info",
        f"Lighting plan {path.name}: {n_lcp} LCP panels, {placed_zones} control "
        f"zones, {n_fix} fixture types — placed at absolute X/Y on the Arch D sheet",
        path.name,
    )


class _Fit:
    """Linear fit of a raw PDF-point bbox onto the Arch-D drawing area.

    Maps source (px, py) [top-left origin] -> canvas inches (bottom-left
    origin), preserving aspect ratio and centering, so true relative geometry
    is kept while every marker stays on the sheet.
    """

    def __init__(self, pts: list[tuple[float, float]], page_w: float,
                 page_h: float, margin: float) -> None:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.minx, self.maxx = min(xs), max(xs)
        self.miny, self.maxy = min(ys), max(ys)
        src_w = max(self.maxx - self.minx, 1e-6)
        src_h = max(self.maxy - self.miny, 1e-6)
        avail_w = page_w - 2 * margin
        avail_h = page_h - 2 * margin
        self.scale = min(avail_w / src_w, avail_h / src_h)
        # center the fitted bbox in the drawing area
        self.off_x = margin + (avail_w - src_w * self.scale) / 2.0
        self.off_y = margin + (avail_h - src_h * self.scale) / 2.0
        self.page_h = page_h
        self.margin = margin

    def map(self, px: float, py: float) -> tuple[float, float]:
        x = self.off_x + (px - self.minx) * self.scale
        # flip Y: PDF top-left -> canvas bottom-left
        y_from_top = self.off_y + (py - self.miny) * self.scale
        y = self.page_h - y_from_top
        return x, y

