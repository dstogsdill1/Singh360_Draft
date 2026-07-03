from __future__ import annotations

from pathlib import Path


def import_pdf(path: str | Path) -> dict:
    pdf = Path(path)
    return {
        "type": "pdf",
        "name": pdf.name,
        "path": str(pdf),
        "pages": [],
        "status": "attached",
        "note": "PDF attached as underlay source; page extraction is milestone-2.",
    }
