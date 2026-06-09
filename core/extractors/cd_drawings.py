"""extractors/cd_drawings.py — construction drawing PDFs.

Reuses the proven deterministic-first approach from the rest of the toolchain:
pull the embedded text from each drawing PDF (PyMuPDF). Schedule pages (rack
schedules, panel schedules) have rich extractable text; bitmap-heavy sheets
return little and are flagged for the Azure DI path (core/ingestion.py).

This extractor records a lightweight DEVICE node per drawing with its detected
discipline + a text snippet, so the drawing is traceable in the model. Deep
table extraction is delegated to core.ingestion / core.schedule_adapter.
"""
from __future__ import annotations

from pathlib import Path

from core.model import ProjectModel, Node, NodeKind, slug


def extract(path: str | Path, model: ProjectModel) -> None:
    path = Path(path)
    model.note_source(str(path))
    try:
        import fitz  # PyMuPDF
    except ImportError:
        model.flag("review", f"{path.name}: install PyMuPDF to scan CD drawings", path.name)
        return

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        model.flag("blocked", f"could not open {path.name}: {exc}", path.name)
        return

    text_chars = 0
    pages_with_text = 0
    snippet = ""
    for i in range(doc.page_count):
        t = doc[i].get_text("text").strip()
        if t:
            pages_with_text += 1
            text_chars += len(t)
            if not snippet:
                snippet = t[:600]
    doc.close()

    model.add_node(Node(
        id=slug("drawing", path.stem),
        kind=NodeKind.DEVICE, name=path.stem,
        attrs={"kind": "drawing", "pages": str(doc.page_count if hasattr(doc, "page_count") else ""),
               "text_pages": str(pages_with_text), "snippet": snippet},
        source=path.name,
    ))

    if text_chars < 200:
        model.flag(
            "blocked",
            f"{path.name}: little/no extractable text — bitmap heavy, route to Azure DI",
            path.name,
        )
    else:
        model.flag("info", f"CD drawing {path.name}: {text_chars} text chars across {pages_with_text} pages", path.name)
