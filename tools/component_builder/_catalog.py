"""_catalog.py -- shared loader + path resolution for the component builder.

Supports two manifest shapes:

1. The Singh360 master catalog CSV (columns include ``componentId`` /
   ``sourceImageFile`` / ``templateType`` ...). This is the curated intake.
2. The workbench's own ``manifest_review.csv`` (columns ``id`` / ``sourcePath``
   ...) produced by build_inventory in the legacy inventory flow.

Both are normalized into a common row dict so the candidate generator and
contact-sheet builder can treat them identically.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / ".docs" / "library" / "singh360_component_master_package"
CANDIDATES_DIR = REPO_ROOT / ".docs" / "component_builder" / "work" / "symbol_candidates"


def slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip()).strip("_").lower()
    return s or "misc"


def candidate_dir(row: dict) -> Path:
    return CANDIDATES_DIR / slug(row["manufacturer"]) / slug(row["category"]) / (row.get("id") or "unknown")

# templateType values specific enough to draw a *procedural* symbol from when no
# source image exists. Anything not in this set (e.g. bare "image_symbol") must
# fall back to needsReview instead of a generic placeholder.
SPECIFIC_TEMPLATES = {
    "controller_tdb",
    "stepper_module",
    "mini_io",
    "probe_board",
    "module_terminal_row",
    "contactor",
    "breaker",
    "power_supply",
    "terminal_block",
    "enclosure",
    "sensor",
    "fan",
    "pump",
    "valve",
    "din_rail",
    "alarm_strobe",
}

CATALOG_MARKERS = {"componentId", "sourceImageFile", "templateType"}


def _to_int(val: str | None):
    if val is None:
        return None
    v = str(val).strip()
    if v == "" or v.lower() == "nan":
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _to_bool(val: str | None) -> bool:
    return str(val).strip().lower() in {"true", "yes", "y", "1", "needs_review"}


def resolve_manifest(arg: str | None) -> Path | None:
    """Find the manifest file from a possibly-bare name, searching sane places."""
    if not arg:
        return None
    p = Path(arg)
    tries = [
        p,
        Path.cwd() / p,
        REPO_ROOT / p,
        PACKAGE_DIR / p,
        PACKAGE_DIR / p.name,
    ]
    for t in tries:
        if t.exists() and t.is_file():
            return t.resolve()
    # last resort: glob by name under the library tree
    for hit in (REPO_ROOT / ".docs" / "library").rglob(p.name):
        if hit.is_file():
            return hit.resolve()
    return None


def resolve_source_root(arg: str | None, manifest_dir: Path) -> Path:
    """Resolve --source-root; defaults to the manifest's own directory."""
    if not arg:
        return manifest_dir
    p = Path(arg)
    tries = [p, manifest_dir / p, REPO_ROOT / p, Path.cwd() / p, PACKAGE_DIR / p]
    for t in tries:
        if t.exists() and t.is_dir():
            return t.resolve()
    return manifest_dir


def resolve_source_image(sif: str | None, manifest_dir: Path,
                         source_root: Path) -> Path | None:
    """Locate the real source image referenced by a catalog row.

    ``sourceImageFile`` in the catalog is like ``sources/controllers/x.png`` and
    is relative to the package (manifest) directory, but we also try the
    explicit --source-root with/without a leading ``sources/`` segment.
    """
    if not sif:
        return None
    sif = str(sif).replace("\\", "/").strip()
    if not sif:
        return None
    rel = Path(sif)
    tries = [manifest_dir / rel, source_root / rel]
    parts = rel.parts
    if parts and parts[0].lower() == "sources":
        stripped = Path(*parts[1:]) if len(parts) > 1 else Path(rel.name)
        tries += [source_root / stripped, manifest_dir / "sources" / stripped]
    tries.append(source_root / rel.name)
    for t in tries:
        try:
            if t.exists() and t.is_file():
                return t.resolve()
        except OSError:
            continue
    return None


def is_catalog(fieldnames: list[str] | None) -> bool:
    return bool(fieldnames) and bool(CATALOG_MARKERS & set(fieldnames))


def rel_to_repo(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _normalize_catalog_row(row: dict, manifest_dir: Path, source_root: Path) -> dict:
    sif = row.get("sourceImageFile", "")
    src = resolve_source_image(sif, manifest_dir, source_root)
    template = (row.get("templateType") or "").strip()
    manufacturer = (row.get("manufacturer") or "").strip()
    category = (row.get("category") or "custom").strip() or "custom"

    source_exists = src is not None
    template_specific = template in SPECIFIC_TEMPLATES

    # A row is drawable if it has a real source image OR a specific template.
    drawable = source_exists or template_specific
    needs_review = _to_bool(row.get("needsReview")) or not drawable
    notes_bits = []
    if sif and not source_exists:
        notes_bits.append(f"source image not found: {sif}")
    if not sif and not source_exists:
        notes_bits.append("no source image in catalog")
    if not source_exists and not template_specific:
        notes_bits.append("no image and templateType not specific -> needsReview")
    if row.get("notes"):
        notes_bits.append(row["notes"].strip())

    return {
        "id": (row.get("componentId") or "").strip(),
        "displayName": (row.get("displayName") or "").strip(),
        "manufacturer": manufacturer or "Generic",
        "category": category,
        "partNumber": (row.get("partNumber") or "").strip(),
        "aliases": (row.get("aliases") or "").strip(),
        "sourceImageFile": sif,
        "sourcePath": str(src) if src else "",
        "sourceRel": rel_to_repo(src) if src else "",
        "sourceExists": source_exists,
        "templateType": template,
        "templateSpecific": template_specific,
        "drawable": drawable,
        "defaultLabel": (row.get("defaultLabel") or "").strip(),
        "topTerminals": _to_int(row.get("topTerminals")),
        "bottomTerminals": _to_int(row.get("bottomTerminals")),
        "leftPorts": _to_int(row.get("leftPorts")),
        "rightPorts": _to_int(row.get("rightPorts")),
        "widthUnits": _to_int(row.get("widthUnits")),
        "heightUnits": _to_int(row.get("heightUnits")),
        "symbolStatus": (row.get("symbolStatus") or "none").strip(),
        "needsReview": needs_review,
        "priority": (row.get("priority") or "").strip(),
        "notes": " | ".join(b for b in notes_bits if b),
    }


def _normalize_legacy_row(row: dict, manifest_dir: Path, source_root: Path) -> dict:
    sp = row.get("sourcePath", "")
    src = None
    if sp:
        cand = Path(sp)
        if not cand.is_absolute():
            cand = REPO_ROOT / cand
        src = cand if cand.exists() else resolve_source_image(sp, manifest_dir, source_root)
    return {
        "id": row.get("id", ""),
        "displayName": row.get("displayName", ""),
        "manufacturer": row.get("manufacturer", "Generic"),
        "category": row.get("category", "custom") or "custom",
        "partNumber": row.get("partNumber", ""),
        "aliases": row.get("aliases", ""),
        "sourceImageFile": sp,
        "sourcePath": str(src) if src else "",
        "sourceRel": rel_to_repo(src) if src else "",
        "sourceExists": src is not None,
        "templateType": "",
        "templateSpecific": False,
        "drawable": src is not None,
        "defaultLabel": row.get("displayName", ""),
        "topTerminals": None, "bottomTerminals": None,
        "leftPorts": None, "rightPorts": None,
        "widthUnits": None, "heightUnits": None,
        "symbolStatus": row.get("symbolStatus", "none"),
        "needsReview": _to_bool(row.get("needsReview")),
        "priority": "",
        "notes": row.get("notes", ""),
    }


def category_summary(rows: list[dict]) -> list[dict]:
    """Per-category counts: total, withSource, procedural-eligible, needsReview."""
    cats: dict[str, dict] = {}
    for r in rows:
        c = r.get("category") or "custom"
        d = cats.setdefault(c, {"category": c, "total": 0, "withSource": 0,
                                "proceduralOnly": 0, "needsReview": 0})
        d["total"] += 1
        if r.get("sourceExists"):
            d["withSource"] += 1
        elif r.get("templateSpecific"):
            d["proceduralOnly"] += 1
        if r.get("needsReview"):
            d["needsReview"] += 1
    return sorted(cats.values(), key=lambda x: x["category"])


def load_rows(manifest: Path, source_root: Path) -> tuple[list[dict], bool]:
    """Return (normalized_rows, is_catalog)."""
    manifest_dir = manifest.parent
    with manifest.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        catalog = is_catalog(fieldnames)
        rows: list[dict] = []
        for raw in reader:
            # skip completely blank trailing lines
            if not any((v or "").strip() for v in raw.values()):
                continue
            if catalog:
                norm = _normalize_catalog_row(raw, manifest_dir, source_root)
            else:
                norm = _normalize_legacy_row(raw, manifest_dir, source_root)
            if not norm["id"] and not norm["displayName"]:
                continue
            rows.append(norm)
    return rows, catalog
