"""core/intake.py — Stage 1: inventory & classify a raw project folder.

Point this at any messy HEB project folder (CD drawings, EMS dumps, xlsx
worksheets, panel pptx, survey photos, scope-of-work docs) and it produces a
deterministic INVENTORY that says, for every file: which SOURCE TYPE it is and
which EXTRACTOR will handle it. This is how the app "identifies a data dump of
drawings and scope of work."

No files are moved or modified — intake is read-only and emits a manifest.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path


# Source types map 1:1 to extractors (see core/extractors/).
SOURCE_TYPES = (
    "emerson_dump",     # controller dump.xml / export.zip
    "cad_worksheet",    # HEB CAD/CDC worksheet .xlsx (point-to-point I/O matrix)
    "ems_worksheet",    # EMS I/O worksheet .xlsx
    "rdm_tdb",          # RDM TDB layout .xlsx
    "panel_config",     # panel configuration .pptx / .pdf
    "cd_drawings",      # construction drawing PDFs by discipline
    "kwh360_assets",    # kWh360 input .csv
    "survey_photos",    # field photos
    "scope_of_work",    # task orders / scope docs
    "unknown",
)

# Discipline tags seen in HEB CD sets (used to sub-classify drawings).
DISCIPLINES = {
    "EMS": "ems", "REFG": "refrigeration", "REFR": "refrigeration", "R-": "refrigeration",
    "ELEC": "electrical", "E-": "electrical", "MECH": "mechanical", "M-": "mechanical",
    "PLBG": "plumbing", "P-": "plumbing", "MEPR": "mepr", "MEP": "mep",
    "EQUIP": "equipment", "Q-": "equipment", "ARCH": "architectural", "A-": "architectural",
    "CIVIL": "civil", "C-": "civil", "STRUCT": "structural", "S-": "structural",
}

_IMG_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tif", ".tiff"}


@dataclass
class FileEntry:
    path: str
    rel: str
    name: str
    ext: str
    size: int
    source_type: str
    extractor: str
    discipline: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Inventory:
    root: str
    files: list[FileEntry] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "counts": self.counts,
            "by_source": self._by_source(),
            "files": [f.to_dict() for f in self.files],
        }

    def _by_source(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.files:
            out[f.source_type] = out.get(f.source_type, 0) + 1
        return out

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path


def _discipline_of(text: str) -> str:
    up = text.upper()
    for token, disc in DISCIPLINES.items():
        if token in up:
            return disc
    return ""


def classify(path: Path, root: Path) -> FileEntry:
    """Classify one file into a source type + the extractor that handles it."""
    name = path.name
    up = name.upper()
    ext = path.suffix.lower()
    rel = str(path.relative_to(root))
    rel_up = rel.upper()
    size = path.stat().st_size if path.exists() else 0
    disc = _discipline_of(rel)

    src = "unknown"
    note = ""

    # --- by name signature first (most specific) ---
    if "DUMP" in up and ext in {".xml", ".zip"}:
        src = "emerson_dump"; note = "Emerson controller database dump"
    elif "EXPORT" in up and ext == ".zip":
        src = "emerson_dump"; note = "Emerson per-controller CSV export bundle"
    elif ("CAD WORKSHEET" in up or "CDC WORKSHEET" in up or "CAD WKSHT" in up
          or ("CAD" in up and "WORKSHEET" in up) or ("CDC" in up and "WORKSHEET" in up)) \
            and ext in {".xlsx", ".xls", ".xlsb"}:
        src = "cad_worksheet"; note = "HEB CAD/CDC worksheet (point-to-point I/O matrix)"
    elif ("WORKSHEET" in up or "WKSHT" in up) and ("EMS" in up or "EM " in up or "EM-" in up) and ext in {".xlsx", ".xls"}:
        src = "ems_worksheet"; note = "EMS worksheet (procurement/inventory tracker)"
    elif "RDM" in up and "TDB" in up and ext in {".xlsx", ".xls"}:
        src = "rdm_tdb"; note = "RDM TDB layout"
    elif ("SUPPK" in up or ("RACK" in rel_up and "HUSSMANN" in rel_up)) and ext == ".xml":
        src = "emerson_dump"; note = "Hussmann/Emerson rack controller export (XML)"
    elif ("PANEL" in up and ("CONFIG" in up or "CONFIGURATION" in up)) and ext in {".pptx", ".pdf", ".ppt"}:
        src = "panel_config"; note = "Control panel configuration"
    elif ("EMS LAYOUT" in up or "EMS-LAYOUT" in up or "SUB-METERING" in up or "PANEL" in up) and ext in {".pptx", ".ppt"}:
        src = "panel_config"; note = "EMS / panel layout deck"
    elif ("KWH360" in up or "KWH 360" in up) and ext == ".csv":
        src = "kwh360_assets"; note = "kWh360 asset inventory (11-column)"
    elif ("SCOPE" in up or "TASK ORDER" in up or "TASKORDER" in up) and ext in {".pdf", ".docx", ".doc"}:
        src = "scope_of_work"; note = "Scope of work / task order"
    # --- by location + extension ---
    elif ext == ".pdf" and (disc or "DRAWING" in rel_up or "CD" in rel_up or "CONSTRUCTION" in rel_up):
        src = "cd_drawings"; note = f"CD drawing ({disc or 'discipline'})"
    elif ext in _IMG_EXT and ("PHOTO" in rel_up or "SURVEY" in rel_up or "PIC" in rel_up):
        src = "survey_photos"; note = "Field survey photo"
    # --- generic fallbacks ---
    elif ext in {".xlsx", ".xls"} and "EMS" in rel_up:
        src = "ems_worksheet"; note = "EMS spreadsheet (review which kind)"
    elif ext == ".pdf":
        src = "cd_drawings"; note = "PDF drawing/document"
    elif ext == ".csv":
        src = "kwh360_assets"; note = "CSV asset/data table"
    elif ext in _IMG_EXT:
        src = "survey_photos"; note = "Image"

    return FileEntry(
        path=str(path), rel=rel, name=name, ext=ext, size=size,
        source_type=src, extractor=src if src != "unknown" else "", discipline=disc, note=note,
    )


# Skip noise / temp / system files.
_SKIP = re.compile(r"(^~\$|desktop\.ini$|\.tmp$|thumbs\.db$|\.ds_store$)", re.I)


def inventory(root: str | Path, max_files: int = 20000) -> Inventory:
    """Walk a project folder and classify every file. Read-only."""
    root = Path(root)
    inv = Inventory(root=str(root))
    if not root.exists():
        return inv

    count = 0
    for p in root.rglob("*"):
        if count >= max_files:
            break
        if not p.is_file():
            continue
        if _SKIP.search(p.name):
            continue
        try:
            inv.files.append(classify(p, root))
            count += 1
        except (OSError, ValueError):
            continue

    inv.counts = {
        "total": len(inv.files),
        "classified": sum(1 for f in inv.files if f.source_type != "unknown"),
        "unknown": sum(1 for f in inv.files if f.source_type == "unknown"),
    }
    return inv


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m core.intake <project-folder> [out.json]")
        raise SystemExit(2)
    inv = inventory(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else None
    bysrc = inv._by_source()
    print(f"Inventoried {inv.counts['total']} files under {inv.root}")
    for src in SOURCE_TYPES:
        if bysrc.get(src):
            print(f"  {bysrc[src]:>5}  {src}")
    if out:
        print("wrote", inv.save(out))


if __name__ == "__main__":
    main()
