from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET


NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def import_vsdx(path: str | Path) -> dict:
    vsdx = Path(path)
    pages: list[str] = []

    try:
        with zipfile.ZipFile(vsdx, "r") as zf:
            rels_path = "visio/pages/_rels/pages.xml.rels"
            if rels_path in zf.namelist():
                rels = ET.fromstring(zf.read(rels_path))
                for rel in rels.findall("rel:Relationship", NS):
                    target = rel.attrib.get("Target", "")
                    if target:
                        pages.append(target)
    except Exception:
        pages = []

    return {
        "type": "vsdx",
        "name": vsdx.name,
        "path": str(vsdx),
        "pages": pages,
        "status": "attached",
        "note": "VSDX semantic extraction is future milestone; current import captures page targets if discoverable.",
    }
