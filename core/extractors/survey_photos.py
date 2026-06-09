"""extractors/survey_photos.py — field survey photos.

Field photos are as-built evidence: model numbers, MAC addresses, panel
contents, and kWh360 captions ("Rack A", "RDM751 for 6 clr frzr"). We index
each photo as a node so it's traceable, and record any embedded caption.
Optional OCR (Azure DI / pytesseract) can be layered on later; until then we
flag photos as `review` evidence rather than inventing what they show.
"""
from __future__ import annotations

from pathlib import Path

from core.model import ProjectModel, Node, NodeKind, slug


def extract(path: str | Path, model: ProjectModel) -> None:
    path = Path(path)
    model.note_source(str(path))
    # The kWh360 workflow often encodes the subject in the file name.
    caption = path.stem.replace("_", " ").replace("-", " ").strip()
    model.add_node(Node(
        id=slug("photo", path.stem),
        kind=NodeKind.DEVICE, name=path.name,
        attrs={"kind": "survey_photo", "caption": caption},
        source=path.name,
    ))
    model.flag(
        "review",
        f"{path.name}: field photo indexed — OCR/caption review to confirm what it documents",
        path.name,
    )
