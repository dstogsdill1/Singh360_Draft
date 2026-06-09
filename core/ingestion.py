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
import re
import shutil
import tempfile
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


# --------------------------------------------------------------------------
# Local vector-PDF blueprint ingestion (deterministic, PyMuPDF — no Azure)
# --------------------------------------------------------------------------
#
# WHY THIS EXISTS
#   Azure DI `prebuilt-layout` hunts for TABLES, not CAD symbols. Point it at a
#   vector floor-plan blueprint and it returns 0 spatial anchors, so the render
#   falls back to an auto-grid. A blueprint's true positions live in its OWN
#   text layer: PyMuPDF reads every printed token with its exact (x, y) on the
#   page canvas. We match those tokens against the project's known keys (asset
#   Names, relay/contactor refs) and pin each match to its true coordinate.
#
# HONESTY CONTRACT (no hallucination)
#   Only text ACTUALLY PRINTED on the sheet becomes an anchor. If a luminaire
#   is drawn as vector linework with no selectable type tag, it yields NO
#   anchor here (it is not silently invented). The scan reports exactly how
#   many keys matched so the operator can see coverage at a glance.

def _norm_token(tok: str) -> str:
    """Strip surrounding quotes/parens/punctuation; upper-case for matching."""
    return tok.strip().strip("\"'()[]{}.,:;").upper()


class VectorPdfIngestor:
    """Read a vector PDF blueprint and pin known keys to their true X/Y.

    Deterministic and local: needs only PyMuPDF (``fitz``), no network, no
    Azure. Page space (PDF points, top-left origin) is mapped onto the target
    canvas in inches with Visio's bottom-left origin (Y flipped), so anchors
    land the right way up. The PDF is assumed drawn to the canvas aspect (HEB
    blueprints are Arch D 42x30 at 72 dpi == 1:1); a proportional page->canvas
    scale keeps every match on the sheet even if the page differs slightly.
    """

    def __init__(
        self,
        page_w_in: float = config.PAGE_WIDTH_IN,
        page_h_in: float = config.PAGE_HEIGHT_IN,
        *,
        anchor_w: float = config.SHAPE_W_IN,
        anchor_h: float = config.SHAPE_H_IN,
        endpoint: str = "",
        key: str = "",
    ) -> None:
        self.dst_w = page_w_in
        self.dst_h = page_h_in
        self.anchor_w = anchor_w
        self.anchor_h = anchor_h
        self.endpoint = (endpoint or config.AZURE_DI_ENDPOINT).strip()
        self.key = (key or config.AZURE_DI_KEY).strip()

    def available(self) -> bool:
        """True when Azure OCR is configured and can be used as fallback."""
        return bool(self.endpoint and self.key)

    def scan(
        self,
        pdf_path: str | Path,
        keymap: dict[str, str],
        pages: str = "1",
    ) -> LayoutResult:
        """Match ``keymap`` tokens against PDF text and return SpatialNodes.

        ``keymap`` maps an UPPER-CASE token (as it appears on the sheet) to the
        node key it should bind to (the id ``attach_spatial`` matches). Returns
        a LayoutResult whose ``spatial`` list carries one SpatialNode per match
        (first occurrence wins) plus coverage flags.
        """
        out = LayoutResult()
        pdf_path = Path(pdf_path)
        try:
            import fitz  # PyMuPDF
        except ImportError:
            out.flags.append(
                "PyMuPDF (fitz) not installed — run `pip install pymupdf` to "
                "scan vector PDF blueprints locally."
            )
            return out

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:  # noqa: BLE001
            out.flags.append(f"could not open {pdf_path.name}: {exc}")
            return out

        wanted = _parse_pages(pages, doc.page_count) or [0]
        # normalize keymap once
        norm_keys = {_norm_token(k): v for k, v in keymap.items() if k}
        seen: dict[str, SpatialNode] = {}
        total_tokens = 0

        for pno in wanted:
            page = doc[pno]
            pw_in = (page.rect.width or 1.0) / 72.0
            ph_in = (page.rect.height or 1.0) / 72.0
            sx = self.dst_w / pw_in if pw_in else 1.0
            sy = self.dst_h / ph_in if ph_in else 1.0
            try:
                words = page.get_text("words")
            except Exception:  # noqa: BLE001
                continue
            total_tokens += len(words)
            for w in words:
                x0, y0, x1, y1, raw = w[0], w[1], w[2], w[3], w[4]
                tok = _norm_token(raw)
                node_key = norm_keys.get(tok)
                if node_key is None or node_key in seen:
                    continue
                cx_pt = (x0 + x1) / 2.0
                cy_pt = (y0 + y1) / 2.0
                cx_in = (cx_pt / 72.0) * sx
                cy_in = self.dst_h - (cy_pt / 72.0) * sy  # flip Y -> bottom-left
                # clamp onto the sheet
                cx_in = min(max(cx_in, 0.0), self.dst_w)
                cy_in = min(max(cy_in, 0.0), self.dst_h)
                seen[node_key] = SpatialNode(
                    key=node_key,
                    cx=round(cx_in, 3),
                    cy=round(cy_in, 3),
                    w=self.anchor_w,
                    h=self.anchor_h,
                    page=pno + 1,
                    source=f"{pdf_path.name} p{pno + 1}",
                )

        out.page_width_in = self.dst_w
        out.page_height_in = self.dst_h
        out.spatial = list(seen.values())
        doc.close()

        matched = len(seen)
        keys_total = len(set(norm_keys.values()))

        # OCR fallback: if the vector text layer doesn't carry the tags, try a
        # raster OCR pass (local Tesseract first, then Azure prebuilt-read if
        # configured). This is only used when the blueprint actually needs it.
        if matched < keys_total:
            ocr_nodes, ocr_flags = self._scan_ocr_fallback(
                pdf_path=pdf_path,
                wanted=wanted,
                norm_keys=norm_keys,
                seen=seen,
            )
            for nid, sp in ocr_nodes.items():
                if nid not in seen:
                    seen[nid] = sp
            out.flags.extend(ocr_flags)
            matched = len(seen)

        if total_tokens == 0:
            out.flags.append(
                f"{pdf_path.name}: no selectable text — bitmap/vector-only "
                f"blueprint. No coordinates extractable here (route to OCR / "
                f"a tagged source); shapes are NOT pinned (would be an auto-grid)."
            )
        elif matched == 0:
            out.flags.append(
                f"{pdf_path.name}: {total_tokens} text tokens read, but NONE "
                f"matched the {keys_total} project keys. The fixture/panel tags "
                f"are drawn as vector linework, not text — nothing pinned "
                f"(no coordinates invented)."
            )
        else:
            out.flags.append(
                f"{pdf_path.name}: pinned {matched}/{keys_total} keys to true "
                f"X/Y from {total_tokens} text tokens."
            )
        return out

    def _scan_ocr_fallback(
        self,
        *,
        pdf_path: Path,
        wanted: list[int],
        norm_keys: dict[str, str],
        seen: dict[str, SpatialNode],
    ) -> tuple[dict[str, SpatialNode], list[str]]:
        """Try OCR when the text layer didn't yield enough matches."""
        nodes: dict[str, SpatialNode] = {}
        flags: list[str] = []
        pdf_path = Path(pdf_path)

        # 1) Local Tesseract OCR if the binary exists.
        tesseract_path = shutil.which("tesseract")
        if tesseract_path:
            try:
                import pytesseract
                from pytesseract import Output
                import fitz  # PyMuPDF
            except ImportError:
                flags.append(
                    "OCR fallback: pytesseract is not installed, so local OCR "
                    "could not run."
                )
            else:
                try:
                    doc = fitz.open(pdf_path)
                    for pno in wanted:
                        page = doc[pno]
                        dpi = 220
                        zoom = dpi / 72.0
                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                        tmp = Path(tempfile.gettempdir()) / f"{pdf_path.stem}_ocr_{pno+1}.png"
                        pix.save(tmp)
                        try:
                            data = pytesseract.image_to_data(
                                str(tmp),
                                output_type=Output.DICT,
                                config="--psm 11",
                            )
                        finally:
                            tmp.unlink(missing_ok=True)

                        page_w_in = (page.rect.width or 1.0) / 72.0
                        page_h_in = (page.rect.height or 1.0) / 72.0
                        sx = self.dst_w / page_w_in if page_w_in else 1.0
                        sy = self.dst_h / page_h_in if page_h_in else 1.0
                        for i, raw in enumerate(data.get("text", []) or []):
                            tok = _norm_token(str(raw))
                            if not tok:
                                continue
                            node_key = norm_keys.get(tok)
                            if node_key is None or node_key in seen or node_key in nodes:
                                continue
                            try:
                                conf = float(data.get("conf", ["-1"])[i])
                            except (TypeError, ValueError, IndexError):
                                conf = -1.0
                            if conf < 25:
                                continue
                            try:
                                left = float(data.get("left", [0])[i])
                                top = float(data.get("top", [0])[i])
                                width = float(data.get("width", [0])[i])
                                height = float(data.get("height", [0])[i])
                            except (TypeError, ValueError, IndexError):
                                continue
                            cx_pt = (left + width / 2.0) / dpi * 72.0
                            cy_pt = (top + height / 2.0) / dpi * 72.0
                            cx_in = min(max((cx_pt / 72.0) * sx, 0.0), self.dst_w)
                            cy_in = min(max(self.dst_h - (cy_pt / 72.0) * sy, 0.0), self.dst_h)
                            nodes[node_key] = SpatialNode(
                                key=node_key,
                                cx=round(cx_in, 3),
                                cy=round(cy_in, 3),
                                w=self.anchor_w,
                                h=self.anchor_h,
                                page=pno + 1,
                                source=f"{pdf_path.name} p{pno + 1} (OCR:tesseract)",
                            )
                    doc.close()
                except Exception as exc:  # noqa: BLE001
                    flags.append(f"OCR fallback via Tesseract failed: {exc}")

        # 2) Azure Document Intelligence prebuilt-read as a second OCR option.
        if not nodes and self.available():
            try:
                import fitz  # PyMuPDF
                from azure.ai.documentintelligence import DocumentIntelligenceClient
                from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
                from azure.core.credentials import AzureKeyCredential
            except ImportError:
                flags.append("Azure OCR fallback unavailable: install azure-ai-documentintelligence.")
            else:
                try:
                    doc = fitz.open(pdf_path)
                    sub = fitz.open()
                    for p in wanted:
                        sub.insert_pdf(doc, from_page=p, to_page=p)
                    data = sub.tobytes()
                    doc.close()
                    sub.close()

                    client = DocumentIntelligenceClient(self.endpoint, AzureKeyCredential(self.key))
                    poller = client.begin_analyze_document(
                        "prebuilt-read", AnalyzeDocumentRequest(bytes_source=data)
                    )
                    result = poller.result()

                    for p_index, page in enumerate(getattr(result, "pages", []) or []):
                        page_w_in = float(getattr(page, "width", self.dst_w) or self.dst_w)
                        page_h_in = float(getattr(page, "height", self.dst_h) or self.dst_h)
                        sx = self.dst_w / page_w_in if page_w_in else 1.0
                        sy = self.dst_h / page_h_in if page_h_in else 1.0
                        for word in getattr(page, "words", []) or []:
                            tok = _norm_token(str(getattr(word, "content", "")))
                            node_key = norm_keys.get(tok)
                            if node_key is None or node_key in seen or node_key in nodes:
                                continue
                            poly = list(getattr(word, "polygon", []) or [])
                            if len(poly) < 8:
                                continue
                            cx_pt = sum(poly[0::2]) / (len(poly) // 2)
                            cy_pt = sum(poly[1::2]) / (len(poly) // 2)
                            cx_in = min(max(cx_pt * sx, 0.0), self.dst_w)
                            cy_in = min(max(self.dst_h - cy_pt * sy, 0.0), self.dst_h)
                            nodes[node_key] = SpatialNode(
                                key=node_key,
                                cx=round(cx_in, 3),
                                cy=round(cy_in, 3),
                                w=self.anchor_w,
                                h=self.anchor_h,
                                page=p_index + 1,
                                source=f"{pdf_path.name} p{p_index + 1} (OCR:AzureRead)",
                            )
                    flags.append(
                        f"{pdf_path.name}: OCR fallback via Azure prebuilt-read matched "
                        f"{len(nodes)} key(s)."
                    )
                except Exception as exc:  # noqa: BLE001
                    flags.append(f"Azure OCR fallback failed: {exc}")

        if not nodes and not flags:
            flags.append(
                "OCR fallback unavailable: no Tesseract binary found and Azure OCR "
                "is not configured."
            )
        return nodes, flags

    def render_background_png(
        self,
        pdf_path: str | Path,
        out_png: str | Path,
        page: int = 0,
        dpi: int = 110,
    ) -> Path | None:
        """Rasterize a PDF page to PNG (the floor-plan background layer).

        Returns the written path, or None if PyMuPDF is unavailable. The image
        is a verifiable artifact the operator can SEE and overlay — we never
        claim a background is present without producing the pixels.
        """
        out_png = Path(out_png)
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return None
        try:
            doc = fitz.open(pdf_path)
            pg = doc[page]
            zoom = dpi / 72.0
            pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            out_png.parent.mkdir(parents=True, exist_ok=True)
            pix.save(out_png)
            doc.close()
        except Exception:  # noqa: BLE001
            return None
        return out_png


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
