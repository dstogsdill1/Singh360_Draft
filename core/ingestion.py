"""core/ingestion.py — spatial + tabular ingestion.

Two deterministic-first capabilities:

1. Grid reconstruction of Azure Document Intelligence `prebuilt-layout` table
   cells, using the exact 2D-array technique from the upstream parser
   (Singh360_Parser/scripts/.../03_refrigeration_map.py:load_grid):

       grid = [["" for _ in range(maxc + 1)] for _ in range(maxr + 1)]

   This consumes the SAME `*_DI_tables.csv` schema the parser already emits
   (table_index,row_index,col_index,row_span,col_span,kind,content), so the
   two tools are interoperable with zero re-extraction.

2. Spatial anchoring: convert Azure DI 8-point bounding polygons (4 points x
   {x,y}, in inches) into normalized canvas centers (cx, cy, w, h). These
   anchors let the render engines pin shapes to true floor-plan positions
   instead of an auto-grid.

The live Azure call (analyze_layout) mirrors the parser's 01_azure_di.py but
imports azure-ai-documentintelligence / PyMuPDF lazily, so the deterministic
CSV path runs with the standard library alone.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import config

# DI table-cell CSV schema produced by Singh360_Parser/01_azure_di.py.
DI_TABLE_FIELDS = (
    "table_index",
    "row_index",
    "col_index",
    "row_span",
    "col_span",
    "kind",
    "content",
)


@dataclass
class SpatialNode:
    """A floor-plan anchor recovered from a bounding polygon."""

    key: str  # normalized label used to match an asset Name
    cx: float  # center X (inches, page space)
    cy: float  # center Y (inches, page space)
    w: float
    h: float
    page: int = 1
    source: str = ""  # provenance: file:page or DI region id


@dataclass
class LayoutResult:
    """Result of an ingestion pass."""

    tables: dict[int, list[list[str]]] = field(default_factory=dict)
    spatial: list[SpatialNode] = field(default_factory=list)
    page_width_in: float = config.PAGE_WIDTH_IN
    page_height_in: float = config.PAGE_HEIGHT_IN
    flags: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Polygon geometry (deterministic, pure-stdlib math)
# --------------------------------------------------------------------------
def polygon_points(polygon: list[float]) -> list[tuple[float, float]]:
    """Turn a flat [x1,y1,x2,y2,...] polygon into (x,y) pairs.

    Azure DI layout returns 8 floats (4 corners). We accept any even length.
    """
    if not polygon or len(polygon) % 2 != 0:
        return []
    return [(polygon[i], polygon[i + 1]) for i in range(0, len(polygon), 2)]


def polygon_centroid(polygon: list[float]) -> tuple[float, float]:
    pts = polygon_points(polygon)
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def polygon_bbox(polygon: list[float]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, width, height) of the polygon's bounding box."""
    pts = polygon_points(polygon)
    if not pts:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def normalize_polygon(
    polygon: list[float],
    src_w_in: float,
    src_h_in: float,
    dst_w_in: float = config.PAGE_WIDTH_IN,
    dst_h_in: float = config.PAGE_HEIGHT_IN,
    *,
    flip_y: bool = True,
) -> tuple[float, float, float, float]:
    """Map a DI polygon (page-inch space) onto the target canvas (inches).

    Azure DI uses a top-left origin (Y grows downward). Visio uses a
    bottom-left origin (Y grows upward); when `flip_y` is True we invert Y so
    floor-plan nodes land the right way up on the Visio canvas. Returns the
    shape center (cx, cy) and size (w, h) in destination inches.
    """
    cx, cy = polygon_centroid(polygon)
    _, _, w, h = polygon_bbox(polygon)
    sx = (dst_w_in / src_w_in) if src_w_in else 1.0
    sy = (dst_h_in / src_h_in) if src_h_in else 1.0
    out_cx = cx * sx
    out_cy = (src_h_in - cy) * sy if flip_y else cy * sy
    return (out_cx, out_cy, max(w * sx, 0.1), max(h * sy, 0.1))


# --------------------------------------------------------------------------
# Deterministic table grid reconstruction (upstream-compatible)
# --------------------------------------------------------------------------
def load_di_tables_csv(path: str | Path) -> dict[int, list[list[str]]]:
    """Read a parser-style *_DI_tables.csv and rebuild dense 2D grids.

    Returns {table_index: grid} where grid[row][col] == cell content.
    """
    path = Path(path)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by_table: dict[int, list[dict]] = {}
    for r in rows:
        by_table.setdefault(int(r["table_index"]), []).append(r)

    grids: dict[int, list[list[str]]] = {}
    for ti, cells in by_table.items():
        maxr = max(int(c["row_index"]) for c in cells)
        maxc = max(int(c["col_index"]) for c in cells)
        # The exact reconstruction technique used upstream:
        grid = [["" for _ in range(maxc + 1)] for _ in range(maxr + 1)]
        for c in cells:
            grid[int(c["row_index"])][int(c["col_index"])] = c["content"]
        grids[ti] = grid
    return grids


# --------------------------------------------------------------------------
# Optional live Azure DI layout pass (lazy imports)
# --------------------------------------------------------------------------
class AzureLayoutIngestor:
    """Thin wrapper around Azure DI `prebuilt-layout`.

    Mirrors Singh360_Parser/scripts/weis908/01_azure_di.py but additionally
    captures table bounding polygons as SpatialNodes. Heavy SDKs are imported
    lazily so importing this module never requires Azure to be installed.
    """

    def __init__(self, endpoint: str = "", key: str = "") -> None:
        self.endpoint = (endpoint or config.AZURE_DI_ENDPOINT).strip()
        self.key = (key or config.AZURE_DI_KEY).strip()

    def available(self) -> bool:
        return bool(self.endpoint and self.key)

    def analyze_pdf(self, pdf_path: str | Path, pages: str = "1") -> LayoutResult:
        """Run layout on a PDF page range and return tables + spatial anchors.

        `pages` is a 1-based spec like "3-4" or "1,3". Requires
        azure-ai-documentintelligence and PyMuPDF (see requirements.txt).
        """
        if not self.available():
            raise RuntimeError(
                "Azure DI endpoint/key not configured. Set AZURE_DI_ENDPOINT "
                "and AZURE_DI_KEY in the .env, or use the --di-tables "
                "deterministic CSV path instead."
            )
        # Lazy, optional dependencies.
        import fitz  # PyMuPDF
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.credentials import AzureKeyCredential

        pdf_path = Path(pdf_path)
        doc = fitz.open(pdf_path)
        wanted = _parse_pages(pages, doc.page_count)
        sub = fitz.open()
        for p in wanted:
            sub.insert_pdf(doc, from_page=p, to_page=p)
        data = sub.tobytes()
        doc.close()
        sub.close()

        client = DocumentIntelligenceClient(self.endpoint, AzureKeyCredential(self.key))
        poller = client.begin_analyze_document(
            "prebuilt-layout", AnalyzeDocumentRequest(bytes_source=data)
        )
        result = poller.result()

        out = LayoutResult()
        di_pages = getattr(result, "pages", []) or []
        if di_pages:
            first = di_pages[0]
            out.page_width_in = float(getattr(first, "width", config.PAGE_WIDTH_IN))
            out.page_height_in = float(getattr(first, "height", config.PAGE_HEIGHT_IN))

        for ti, table in enumerate(getattr(result, "tables", []) or []):
            cells = list(table.cells)
            maxr = max((c.row_index for c in cells), default=0)
            maxc = max((c.column_index for c in cells), default=0)
            grid = [["" for _ in range(maxc + 1)] for _ in range(maxr + 1)]
            for c in cells:
                grid[c.row_index][c.column_index] = (c.content or "").replace("\n", " ")
            out.tables[ti] = grid

            # Spatial anchor for the table as a whole (first bounding region).
            regions = getattr(table, "bounding_regions", None) or []
            if regions:
                poly = list(getattr(regions[0], "polygon", []) or [])
                if poly:
                    cx, cy, w, h = normalize_polygon(
                        poly, out.page_width_in, out.page_height_in
                    )
                    out.spatial.append(
                        SpatialNode(
                            key=f"table_{ti}",
                            cx=cx,
                            cy=cy,
                            w=w,
                            h=h,
                            page=getattr(regions[0], "page_number", 1),
                            source=f"{pdf_path.name}:table{ti}",
                        )
                    )
        if not out.tables:
            out.flags.append("Azure DI returned no tables for the requested pages.")
        return out

    def write_tables_csv(self, result: LayoutResult, out_path: str | Path) -> Path:
        """Persist grids in the upstream-compatible *_DI_tables.csv schema."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(DI_TABLE_FIELDS)
            for ti, grid in result.tables.items():
                for ri, rrow in enumerate(grid):
                    for ci, val in enumerate(rrow):
                        if val:
                            w.writerow([ti, ri, ci, 1, 1, "", val])
        return out_path


def _parse_pages(spec: str, total: int) -> list[int]:
    """1-based page spec -> sorted 0-based indices (upstream-compatible)."""
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a) - 1, int(b)))
        else:
            out.add(int(part) - 1)
    return sorted(p for p in out if 0 <= p < total)
