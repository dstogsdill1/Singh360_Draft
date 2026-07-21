"""Deterministic single-page PDF symbol mapping for Singh360 Draft.

The symbol mapper is deliberately independent from project.json.  Sessions live
under ``.docs/symbol_mapper`` and never modify a customer PDF in place.  The
frontend may copy the reviewed PNG into a project asset only after the user
explicitly chooses "Add page to project".

Accuracy policy
---------------
* exact text + enclosing vector marker: accepted by default;
* visual-template-only or text-only evidence: review required;
* final export contains accepted candidates only.

The module uses PyMuPDF for PDF inspection/render/export.  OpenCV is optional:
when installed it supplies review-only visual template candidates for scanned or
flattened drawings.  It is never allowed to silently auto-accept a detection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import time
import uuid
from typing import Any, Iterable, Sequence

try:
    import fitz  # type: ignore
except Exception as exc:  # pragma: no cover - handled at runtime
    fitz = None  # type: ignore[assignment]
    _FITZ_IMPORT_ERROR = exc
else:
    _FITZ_IMPORT_ERROR = None

try:  # Optional, review-only visual matching.
    import cv2  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


SESSION_ID_RE = re.compile(r"^[a-f0-9]{24}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ALLOWED_ASSETS = {
    "source.pdf",
    "source.png",
    "review.pdf",
    "review.png",
    "final.pdf",
    "final.png",
    "session.json",
    "detection.json",
}
DEFAULT_PREVIEW_DPI = 72
DEFAULT_VISUAL_DPI = 144
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_CLASSES = 64
MAX_CANDIDATES = 10000


class SymbolMapperError(RuntimeError):
    """User-safe symbol mapper failure."""


@dataclass(frozen=True)
class _ShapeEvidence:
    found: bool
    shape: str
    rect: tuple[float, float, float, float] | None


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_filename(name: str) -> str:
    base = Path(name or "drawing.pdf").name
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    return base or "drawing.pdf"


def _hex_color(value: Any, fallback: str = "#ffcc00") -> str:
    text = str(value or "").strip()
    return text.lower() if HEX_RE.match(text) else fallback


def _rgb01(value: str) -> tuple[float, float, float]:
    value = _hex_color(value)
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (1, 3, 5))  # type: ignore[return-value]


def _rect_tuple(rect: "fitz.Rect") -> tuple[float, float, float, float]:
    return (round(rect.x0, 3), round(rect.y0, 3), round(rect.x1, 3), round(rect.y1, 3))


def _rect_from_payload(value: Any, page_rect: "fitz.Rect") -> "fitz.Rect | None":
    if not isinstance(value, dict):
        return None
    try:
        x0 = float(value.get("x0", 0.0))
        y0 = float(value.get("y0", 0.0))
        x1 = float(value.get("x1", 0.0))
        y1 = float(value.get("y1", 0.0))
    except (TypeError, ValueError):
        return None

    # The frontend sends normalized coordinates.  PDF-point coordinates are also
    # accepted for test and recovery tooling.
    if all(0.0 <= n <= 1.000001 for n in (x0, y0, x1, y1)):
        x0, x1 = x0 * page_rect.width, x1 * page_rect.width
        y0, y1 = y0 * page_rect.height, y1 * page_rect.height
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    rect = fitz.Rect(left, top, right, bottom)
    rect &= page_rect
    if rect.width < 2 or rect.height < 2:
        return None
    return rect


def _center(rect: "fitz.Rect") -> tuple[float, float]:
    return ((rect.x0 + rect.x1) / 2.0, (rect.y0 + rect.y1) / 2.0)


def _distance(a: "fitz.Rect", b: "fitz.Rect") -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return math.hypot(ax - bx, ay - by)


def _iou(a: "fitz.Rect", b: "fitz.Rect") -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    denom = a.get_area() + b.get_area() - inter.get_area()
    return inter.get_area() / denom if denom > 0 else 0.0


def _marker_rect(target: "fitz.Rect", size_pt: float) -> "fitz.Rect":
    cx, cy = _center(target)
    side = max(float(size_pt), target.width + 5.0, target.height + 5.0)
    return fitz.Rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)


def _normalize_class(raw: Any, index: int, page_rect: "fitz.Rect") -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    code = str(raw.get("code") or "").strip()
    label = str(raw.get("label") or "").strip()
    if not code and not raw.get("templateBox"):
        return None
    class_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw.get("id") or f"class_{index + 1}"))[:80]
    expected = str(raw.get("shape") or "auto").lower()
    if expected not in {"auto", "circle", "square"}:
        expected = "auto"
    pattern = str(raw.get("pattern") or "solid").lower()
    if pattern not in {
        "solid",
        "outline",
        "double-outline",
        "split-vertical",
        "split-horizontal",
        "diagonal",
        "crosshatch",
    }:
        pattern = "solid"
    try:
        marker_size = max(8.0, min(72.0, float(raw.get("markerSizePt") or 18.0)))
    except (TypeError, ValueError):
        marker_size = 18.0
    template_rect = _rect_from_payload(raw.get("templateBox"), page_rect)
    return {
        "id": class_id,
        "code": code,
        "codeUpper": code.upper(),
        "label": label,
        "shape": expected,
        "color": _hex_color(raw.get("color"), "#ffcc00"),
        "color2": _hex_color(raw.get("color2"), "#12539b"),
        "pattern": pattern,
        "markerSizePt": marker_size,
        "templateBox": _rect_tuple(template_rect) if template_rect else None,
        "visualEnabled": bool(raw.get("visualEnabled", True)) and template_rect is not None,
    }


def _class_public(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    out.pop("codeUpper", None)
    return out


def _small_vector_markers(page: "fitz.Page") -> list[dict[str, Any]]:
    """Reduce potentially hundreds of thousands of CAD paths to marker-sized boxes."""
    markers: list[dict[str, Any]] = []
    try:
        # ``get_cdrawings`` returns the same path geometry in a compact tuple
        # representation and is dramatically faster on CAD-heavy sheets (where
        # ``get_drawings`` can spend minutes materializing hundreds of thousands
        # of Point / Rect objects).
        drawings = page.get_cdrawings() if hasattr(page, "get_cdrawings") else page.get_drawings()
    except Exception:
        return markers
    for drawing in drawings:
        raw_rect = drawing.get("rect")
        try:
            rect = raw_rect if isinstance(raw_rect, fitz.Rect) else fitz.Rect(raw_rect)
        except Exception:
            continue
        width, height = rect.width, rect.height
        if not (3.5 <= width <= 64.0 and 3.5 <= height <= 64.0):
            continue
        ratio = width / height if height else 999.0
        if not (0.45 <= ratio <= 2.2):
            continue
        items = drawing.get("items") or []
        kinds = {str(item[0]) for item in items if item}
        shape = "circle" if "c" in kinds else "square"
        markers.append({"rect": rect, "shape": shape})
    return markers


def _shape_evidence(
    hit: "fitz.Rect",
    markers: Sequence[dict[str, Any]],
    expected: str,
) -> _ShapeEvidence:
    cx, cy = _center(hit)
    best: tuple[float, dict[str, Any]] | None = None
    for marker in markers:
        rect = marker["rect"]
        if not (rect.x0 - 1.5 <= cx <= rect.x1 + 1.5 and rect.y0 - 1.5 <= cy <= rect.y1 + 1.5):
            continue
        if rect.width < max(3.5, hit.width * 0.65) or rect.height < max(3.5, hit.height * 0.65):
            continue
        shape = marker["shape"]
        if expected != "auto" and shape != expected:
            continue
        score = _distance(hit, rect) + abs(rect.width - rect.height) * 0.05
        if best is None or score < best[0]:
            best = (score, marker)
    if best is None:
        return _ShapeEvidence(False, "", None)
    marker = best[1]
    return _ShapeEvidence(True, str(marker["shape"]), _rect_tuple(marker["rect"]))


def _candidate_id(class_id: str, method: str, rect: "fitz.Rect") -> str:
    raw = f"{class_id}|{method}|{rect.x0:.3f}|{rect.y0:.3f}|{rect.x1:.3f}|{rect.y1:.3f}"
    return sha256(raw.encode("utf-8")).hexdigest()[:20]


def _text_candidates(
    page: "fitz.Page",
    classes: Sequence[dict[str, Any]],
    markers: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_code: dict[str, list[dict[str, Any]]] = {}
    for cls in classes:
        code = cls["codeUpper"]
        if code:
            by_code.setdefault(code, []).append(cls)
    if not by_code:
        return []

    candidates: list[dict[str, Any]] = []
    words = page.get_text("words") or []
    for word in words:
        if len(word) < 5:
            continue
        text = str(word[4]).strip()
        matching = by_code.get(text.upper())
        if not matching:
            continue
        hit = fitz.Rect(float(word[0]), float(word[1]), float(word[2]), float(word[3]))
        for cls in matching:
            evidence = _shape_evidence(hit, markers, cls["shape"])
            accepted = evidence.found
            # Single-character codes and unboxed exact words always remain review
            # items unless the enclosing vector marker is present.
            status = "accepted" if accepted else "review"
            score = 1.0 if accepted else (0.72 if len(text) > 1 else 0.55)
            candidates.append(
                {
                    "id": _candidate_id(cls["id"], "text", hit),
                    "classId": cls["id"],
                    "code": cls["code"],
                    "label": cls["label"],
                    "bbox": _rect_tuple(hit),
                    "markerBox": _rect_tuple(_marker_rect(hit, cls["markerSizePt"])),
                    "method": "text+vector" if accepted else "text-only",
                    "evidence": ["exact-text"] + ([f"vector-{evidence.shape}"] if accepted else []),
                    "score": score,
                    "status": status,
                    "accepted": accepted,
                    "shapeRect": evidence.rect,
                    "text": text,
                }
            )
    return candidates


def _render_gray(page: "fitz.Page", dpi: int) -> "Any":
    if cv2 is None or np is None:
        return None
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), colorspace=fitz.csGRAY, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return arr.copy()


def _local_maxima(score: "Any", threshold: float, max_points: int = 2000) -> list[tuple[int, int, float]]:
    if cv2 is None or np is None:
        return []
    dilated = cv2.dilate(score, np.ones((3, 3), dtype=np.uint8))
    ys, xs = np.where((score >= threshold) & (score >= dilated - 1e-7))
    points = [(int(x), int(y), float(score[y, x])) for x, y in zip(xs, ys)]
    points.sort(key=lambda item: item[2], reverse=True)
    return points[:max_points]


def _nms(rects: Iterable[tuple["fitz.Rect", float]], iou_threshold: float = 0.25) -> list[tuple["fitz.Rect", float]]:
    ordered = sorted(rects, key=lambda item: item[1], reverse=True)
    kept: list[tuple[fitz.Rect, float]] = []
    for rect, score in ordered:
        if any(_iou(rect, other) >= iou_threshold or _distance(rect, other) < min(rect.width, rect.height) * 0.45 for other, _ in kept):
            continue
        kept.append((rect, score))
    return kept


def _visual_candidates(
    page: "fitz.Page",
    classes: Sequence[dict[str, Any]],
    existing: Sequence[dict[str, Any]],
    dpi: int = DEFAULT_VISUAL_DPI,
) -> tuple[list[dict[str, Any]], str | None]:
    if cv2 is None or np is None:
        return [], "OpenCV is not installed; visual template matching was skipped."
    enabled = [cls for cls in classes if cls.get("visualEnabled") and cls.get("templateBox")]
    if not enabled:
        return [], None

    gray = _render_gray(page, dpi)
    if gray is None:
        return [], "The page could not be rendered for visual template matching."
    edge_page = cv2.Canny(gray, 60, 160)
    scale = dpi / 72.0
    page_rect = page.rect
    existing_rects = [(fitz.Rect(item["markerBox"]), item["classId"]) for item in existing]
    out: list[dict[str, Any]] = []

    for cls in enabled:
        source = fitz.Rect(cls["templateBox"])
        px = fitz.Rect(source.x0 * scale, source.y0 * scale, source.x1 * scale, source.y1 * scale)
        x0 = max(0, int(math.floor(px.x0)))
        y0 = max(0, int(math.floor(px.y0)))
        x1 = min(gray.shape[1], int(math.ceil(px.x1)))
        y1 = min(gray.shape[0], int(math.ceil(px.y1)))
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        template_gray = gray[y0:y1, x0:x1]
        template_edge = cv2.Canny(template_gray, 50, 150)
        if int(np.count_nonzero(template_edge)) < 8:
            continue

        proposed: list[tuple[fitz.Rect, float]] = []
        for factor in (0.90, 1.00, 1.10):
            tw = max(8, int(round(template_edge.shape[1] * factor)))
            th = max(8, int(round(template_edge.shape[0] * factor)))
            if tw >= edge_page.shape[1] or th >= edge_page.shape[0]:
                continue
            tpl = cv2.resize(template_edge, (tw, th), interpolation=cv2.INTER_NEAREST)
            result = cv2.matchTemplate(edge_page, tpl, cv2.TM_CCOEFF_NORMED)
            # A conservative threshold keeps this review list usable.  These are
            # never auto-accepted regardless of score.
            for x, y, match_score in _local_maxima(result, 0.79):
                rect = fitz.Rect(x / scale, y / scale, (x + tw) / scale, (y + th) / scale)
                rect &= page_rect
                if rect.is_empty:
                    continue
                proposed.append((rect, match_score))

        for rect, match_score in _nms(proposed)[:600]:
            # Do not duplicate a deterministic hit for the same class.
            if any(class_id == cls["id"] and (_iou(rect, existing_rect) > 0.15 or _distance(rect, existing_rect) < cls["markerSizePt"] * 0.6) for existing_rect, class_id in existing_rects):
                continue
            marker = _marker_rect(rect, cls["markerSizePt"])
            out.append(
                {
                    "id": _candidate_id(cls["id"], "visual", rect),
                    "classId": cls["id"],
                    "code": cls["code"],
                    "label": cls["label"],
                    "bbox": _rect_tuple(rect),
                    "markerBox": _rect_tuple(marker),
                    "method": "visual-template",
                    "evidence": ["template-correlation"],
                    "score": round(match_score, 4),
                    "status": "review",
                    "accepted": False,
                    "shapeRect": None,
                    "text": "",
                }
            )
            if len(out) >= MAX_CANDIDATES:
                return out, "Visual candidate limit reached; narrow the symbol crop or disable visual matching for noisy classes."
    return out, None


def _clip_line_to_rect(
    p0: tuple[float, float],
    p1: tuple[float, float],
    rect: "fitz.Rect",
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Liang-Barsky segment clipping."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - rect.x0, rect.x1 - x0, y0 - rect.y0, rect.y1 - y0)
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:
                return None
            continue
        t = qi / pi
        if pi < 0:
            u1 = max(u1, t)
        else:
            u2 = min(u2, t)
        if u1 > u2:
            return None
    return ((x0 + u1 * dx, y0 + u1 * dy), (x0 + u2 * dx, y0 + u2 * dy))


def _draw_hatch(page: "fitz.Page", rect: "fitz.Rect", color: tuple[float, float, float], reverse: bool = False) -> None:
    step = max(3.0, rect.width / 5.0)
    span = rect.width + rect.height
    offset = -rect.height
    while offset <= rect.width:
        if reverse:
            p0 = (rect.x0 + offset, rect.y0)
            p1 = (rect.x0 + offset + rect.height, rect.y1)
        else:
            p0 = (rect.x0 + offset, rect.y1)
            p1 = (rect.x0 + offset + rect.height, rect.y0)
        clipped = _clip_line_to_rect(p0, p1, rect)
        if clipped:
            page.draw_line(clipped[0], clipped[1], color=color, width=0.8, stroke_opacity=0.8, overlay=True)
        offset += step


def _draw_marker(page: "fitz.Page", marker_rect: "fitz.Rect", cls: dict[str, Any], *, review: bool = False) -> None:
    rect = marker_rect & page.rect
    if rect.is_empty:
        return
    color1 = _rgb01(cls["color"])
    color2 = _rgb01(cls["color2"])
    pattern = cls["pattern"]
    opacity = 0.20 if not review else 0.08
    outline = color1 if not review else (0.35, 0.35, 0.35)

    if pattern == "solid":
        page.draw_rect(rect, color=outline, fill=color1, width=1.2, fill_opacity=opacity, stroke_opacity=0.95, overlay=True)
    elif pattern == "outline":
        page.draw_rect(rect, color=outline, width=1.5, stroke_opacity=0.95, overlay=True)
    elif pattern == "double-outline":
        page.draw_rect(rect, color=outline, width=1.2, stroke_opacity=0.95, overlay=True)
        inset = fitz.Rect(rect.x0 + 2.2, rect.y0 + 2.2, rect.x1 - 2.2, rect.y1 - 2.2)
        if inset.width > 2 and inset.height > 2:
            page.draw_rect(inset, color=color2, width=0.9, stroke_opacity=0.9, overlay=True)
    elif pattern == "split-vertical":
        mid = (rect.x0 + rect.x1) / 2
        page.draw_rect(fitz.Rect(rect.x0, rect.y0, mid, rect.y1), fill=color1, color=None, fill_opacity=opacity, overlay=True)
        page.draw_rect(fitz.Rect(mid, rect.y0, rect.x1, rect.y1), fill=color2, color=None, fill_opacity=opacity, overlay=True)
        page.draw_rect(rect, color=outline, width=1.2, stroke_opacity=0.95, overlay=True)
    elif pattern == "split-horizontal":
        mid = (rect.y0 + rect.y1) / 2
        page.draw_rect(fitz.Rect(rect.x0, rect.y0, rect.x1, mid), fill=color1, color=None, fill_opacity=opacity, overlay=True)
        page.draw_rect(fitz.Rect(rect.x0, mid, rect.x1, rect.y1), fill=color2, color=None, fill_opacity=opacity, overlay=True)
        page.draw_rect(rect, color=outline, width=1.2, stroke_opacity=0.95, overlay=True)
    else:
        page.draw_rect(rect, color=outline, fill=color1, width=1.2, fill_opacity=opacity * 0.65, stroke_opacity=0.95, overlay=True)
        _draw_hatch(page, rect, color2, reverse=False)
        if pattern == "crosshatch":
            _draw_hatch(page, rect, color2, reverse=True)

    if review:
        # A small corner tick differentiates unaccepted candidates without hiding
        # the source symbol or relying on viewer-specific blur/glow effects.
        tick = min(4.0, rect.width / 4.0)
        page.draw_line((rect.x0, rect.y0), (rect.x0 + tick, rect.y0), color=outline, width=1.0, overlay=True)
        page.draw_line((rect.x0, rect.y0), (rect.x0, rect.y0 + tick), color=outline, width=1.0, overlay=True)


def _render_overlay_pdf(
    source: Path,
    output_pdf: Path,
    candidates: Sequence[dict[str, Any]],
    classes: Sequence[dict[str, Any]],
    *,
    include_review: bool,
) -> None:
    class_by_id = {item["id"]: item for item in classes}
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    # Copy first, then append only the new overlay streams incrementally.  This is
    # both safer and dramatically faster than rewriting / recompressing an entire
    # CAD-heavy PDF.  It also leaves the source file byte-for-byte untouched.
    shutil.copy2(source, output_pdf)
    try:
        with fitz.open(output_pdf) as doc:
            page = doc[0]
            for item in candidates:
                accepted = bool(item.get("accepted")) or str(item.get("status")) == "accepted"
                if not accepted and not include_review:
                    continue
                if not accepted and str(item.get("status")) == "rejected":
                    continue
                cls = class_by_id.get(str(item.get("classId")))
                if not cls:
                    continue
                try:
                    marker = fitz.Rect(item.get("markerBox") or item.get("bbox"))
                except Exception:
                    continue
                _draw_marker(page, marker, cls, review=not accepted)
            doc.saveIncr()
    except Exception:
        try:
            output_pdf.unlink()
        except OSError:
            pass
        raise


def _render_png(pdf_path: Path, out_path: Path, dpi: int = DEFAULT_PREVIEW_DPI) -> dict[str, int]:
    with fitz.open(pdf_path) as doc:
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
        pix.save(out_path)
        return {"width": pix.width, "height": pix.height, "dpi": dpi}


def _summary(candidates: Sequence[dict[str, Any]], classes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cls in classes:
        items = [item for item in candidates if item.get("classId") == cls["id"]]
        rows.append(
            {
                "classId": cls["id"],
                "code": cls["code"],
                "label": cls["label"],
                "accepted": sum(bool(item.get("accepted")) or item.get("status") == "accepted" for item in items),
                "review": sum(not bool(item.get("accepted")) and item.get("status") == "review" for item in items),
                "rejected": sum(item.get("status") == "rejected" for item in items),
                "total": len(items),
            }
        )
    return rows


class SymbolMapperStore:
    """File-backed symbol-mapper session store."""

    def __init__(self, root: Path):
        if fitz is None:
            raise RuntimeError(f"PyMuPDF is required for Symbol Mapper: {_FITZ_IMPORT_ERROR}")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        if not SESSION_ID_RE.fullmatch(session_id or ""):
            raise SymbolMapperError("Invalid symbol mapper session id.")
        path = (self.root / session_id).resolve()
        if self.root.resolve() not in path.parents:
            raise SymbolMapperError("Invalid symbol mapper session path.")
        return path

    def _read_json(self, session_id: str, name: str = "session.json") -> dict[str, Any]:
        path = self._session_dir(session_id) / name
        if not path.is_file():
            raise SymbolMapperError("Symbol mapper session was not found.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SymbolMapperError("Symbol mapper session data is unreadable.") from exc
        if not isinstance(data, dict):
            raise SymbolMapperError("Symbol mapper session data is invalid.")
        return data

    def _write_json(self, session_id: str, name: str, payload: dict[str, Any]) -> None:
        path = self._session_dir(session_id) / name
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)

    def create_session(self, filename: str, content: bytes) -> dict[str, Any]:
        if not content:
            raise SymbolMapperError("The uploaded PDF is empty.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise SymbolMapperError("The uploaded PDF exceeds the 64 MB limit.")
        safe_name = _safe_filename(filename)
        if not safe_name.lower().endswith(".pdf"):
            raise SymbolMapperError("Symbol Mapper accepts a single-page PDF only.")
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise SymbolMapperError("The uploaded file is not a readable PDF.") from exc
        with doc:
            if getattr(doc, "needs_pass", False):
                raise SymbolMapperError("Password-protected PDFs are not supported.")
            if doc.page_count != 1:
                raise SymbolMapperError("Upload exactly one PDF page.")
            page = doc[0]
            page_rect = page.rect
            if page_rect.width <= 0 or page_rect.height <= 0:
                raise SymbolMapperError("The PDF page has invalid dimensions.")
            session_id = uuid.uuid4().hex[:24]
            session_dir = self._session_dir(session_id)
            session_dir.mkdir(parents=True, exist_ok=False)
            source = session_dir / "source.pdf"
            source.write_bytes(content)
            source_png = session_dir / "source.png"
            pix = page.get_pixmap(matrix=fitz.Matrix(DEFAULT_PREVIEW_DPI / 72.0, DEFAULT_PREVIEW_DPI / 72.0), alpha=False)
            pix.save(source_png)
            text = page.get_text("text") or ""
            metadata = {
                "id": session_id,
                "createdAt": _utcnow(),
                "sourceName": safe_name,
                "sourceSha256": sha256(content).hexdigest(),
                "pageCount": 1,
                "page": {
                    "widthPt": round(page_rect.width, 3),
                    "heightPt": round(page_rect.height, 3),
                    "rotation": int(page.rotation or 0),
                    "previewWidth": pix.width,
                    "previewHeight": pix.height,
                    "previewDpi": DEFAULT_PREVIEW_DPI,
                    "hasText": bool(text.strip()),
                    "wordCount": len(page.get_text("words") or []),
                },
                "previewUrl": f"/api/symbol-mapper/sessions/{session_id}/assets/source.png",
                "visualMatchingAvailable": cv2 is not None and np is not None,
            }
            self._write_json(session_id, "session.json", metadata)
            return metadata

    def detect(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._read_json(session_id)
        raw_classes = payload.get("classes") if isinstance(payload, dict) else None
        if not isinstance(raw_classes, list) or not raw_classes:
            raise SymbolMapperError("Add at least one symbol class before running detection.")
        if len(raw_classes) > MAX_CLASSES:
            raise SymbolMapperError(f"A maximum of {MAX_CLASSES} symbol classes is supported per session.")

        source = self._session_dir(session_id) / "source.pdf"
        with fitz.open(source) as doc:
            page = doc[0]
            classes = [item for idx, raw in enumerate(raw_classes) if (item := _normalize_class(raw, idx, page.rect))]
            if not classes:
                raise SymbolMapperError("No valid symbol classes were supplied.")
            markers = _small_vector_markers(page)
            candidates = _text_candidates(page, classes, markers)
            visual, visual_warning = _visual_candidates(page, classes, candidates)
            candidates.extend(visual)

        # Candidate IDs are deterministic; keep the best duplicate only.
        by_id: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            existing = by_id.get(candidate["id"])
            if existing is None or float(candidate.get("score", 0)) > float(existing.get("score", 0)):
                by_id[candidate["id"]] = candidate
        candidates = list(by_id.values())[:MAX_CANDIDATES]
        candidates.sort(key=lambda item: (str(item.get("classId")), float(item["bbox"][1]), float(item["bbox"][0])))

        detection = {
            "sessionId": session_id,
            "createdAt": _utcnow(),
            "sourceSha256": session["sourceSha256"],
            "classes": [_class_public(item) for item in classes],
            "candidates": candidates,
            "summary": _summary(candidates, classes),
            "warnings": [warning for warning in [visual_warning] if warning],
            "policy": {
                "autoAccepted": "exact text plus an enclosing vector marker",
                "reviewRequired": "text-only and visual-template-only candidates",
                "finalExport": "accepted candidates only",
            },
        }
        self._write_json(session_id, "detection.json", detection)
        review_pdf = self._session_dir(session_id) / "review.pdf"
        review_png = self._session_dir(session_id) / "review.png"
        _render_overlay_pdf(source, review_pdf, candidates, classes, include_review=True)
        _render_png(review_pdf, review_png)
        detection.update(
            {
                "reviewPdfUrl": f"/api/symbol-mapper/sessions/{session_id}/assets/review.pdf",
                "reviewPngUrl": f"/api/symbol-mapper/sessions/{session_id}/assets/review.png",
            }
        )
        return detection

    def render(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self._read_json(session_id)
        saved = self._read_json(session_id, "detection.json")
        classes_raw = payload.get("classes", saved.get("classes")) if isinstance(payload, dict) else saved.get("classes")
        candidates_raw = payload.get("candidates", saved.get("candidates")) if isinstance(payload, dict) else saved.get("candidates")
        if not isinstance(classes_raw, list) or not isinstance(candidates_raw, list):
            raise SymbolMapperError("Run detection before rendering a reviewed result.")

        source = self._session_dir(session_id) / "source.pdf"
        with fitz.open(source) as doc:
            page_rect = doc[0].rect
        classes = [item for idx, raw in enumerate(classes_raw) if (item := _normalize_class(raw, idx, page_rect))]
        class_ids = {item["id"] for item in classes}
        candidates: list[dict[str, Any]] = []
        for raw in candidates_raw[:MAX_CANDIDATES]:
            if not isinstance(raw, dict) or raw.get("classId") not in class_ids:
                continue
            try:
                bbox = fitz.Rect(raw.get("bbox"))
                marker = fitz.Rect(raw.get("markerBox") or raw.get("bbox"))
            except Exception:
                continue
            if bbox.is_empty or marker.is_empty:
                continue
            status = str(raw.get("status") or ("accepted" if raw.get("accepted") else "review"))
            if status not in {"accepted", "review", "rejected"}:
                status = "review"
            item = dict(raw)
            item["bbox"] = _rect_tuple(bbox)
            item["markerBox"] = _rect_tuple(marker)
            item["status"] = status
            item["accepted"] = status == "accepted"
            candidates.append(item)

        final_pdf = self._session_dir(session_id) / "final.pdf"
        final_png = self._session_dir(session_id) / "final.png"
        _render_overlay_pdf(source, final_pdf, candidates, classes, include_review=False)
        image_meta = _render_png(final_pdf, final_png)

        # Direct evidence that source content was not overwritten.
        source_hash_after = sha256(source.read_bytes()).hexdigest()
        if source_hash_after != session["sourceSha256"]:
            raise SymbolMapperError("Source PDF integrity check failed; export was stopped.")
        with fitz.open(source) as original, fitz.open(final_pdf) as rendered:
            if original.page_count != rendered.page_count or original[0].rect != rendered[0].rect:
                raise SymbolMapperError("Rendered PDF geometry does not match the uploaded source page.")

        result = {
            "sessionId": session_id,
            "renderedAt": _utcnow(),
            "sourceSha256": session["sourceSha256"],
            "outputSha256": sha256(final_pdf.read_bytes()).hexdigest(),
            "acceptedCount": sum(item["accepted"] for item in candidates),
            "reviewCount": sum(item["status"] == "review" for item in candidates),
            "rejectedCount": sum(item["status"] == "rejected" for item in candidates),
            "summary": _summary(candidates, classes),
            "pdfUrl": f"/api/symbol-mapper/sessions/{session_id}/assets/final.pdf",
            "pngUrl": f"/api/symbol-mapper/sessions/{session_id}/assets/final.png",
            "png": image_meta,
            "sourceName": session["sourceName"],
        }
        return result

    def asset_path(self, session_id: str, name: str) -> Path:
        safe_name = Path(name or "").name
        if safe_name not in ALLOWED_ASSETS:
            raise SymbolMapperError("Unknown symbol mapper asset.")
        path = self._session_dir(session_id) / safe_name
        if not path.is_file():
            raise SymbolMapperError("Symbol mapper asset was not found.")
        return path

    def delete_session(self, session_id: str) -> None:
        path = self._session_dir(session_id)
        if not path.is_dir():
            return

        # Antivirus, browser downloads, and Flask test responses can briefly hold
        # a Windows file handle after the PDF bytes have been read. Retry a few
        # times rather than turning a momentary lock into a 500 response.
        last_error: OSError | None = None
        for delay in (0.0, 0.08, 0.20, 0.45, 0.90):
            if delay:
                time.sleep(delay)
            try:
                shutil.rmtree(path)
                return
            except FileNotFoundError:
                return
            except OSError as exc:
                last_error = exc

        raise SymbolMapperError(
            "This Symbol Mapper session is still in use. Close any open PDF "
            "download or preview, then try deleting it again."
        ) from last_error
