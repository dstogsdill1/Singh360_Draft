from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CALLOUT_COUNT = 20
CALLOUT_PREFIX = "callout-number-"
CALLOUT_NAME_RE = re.compile(r"^callout\s+number\s+(\d+)$", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return fallback


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def callout_svg(number: int) -> str:
    font_size = 29 if number < 10 else 24
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
  <rect width="96" height="96" fill="white" fill-opacity="0"/>
  <circle cx="48" cy="48" r="38" fill="white" stroke="#111111" stroke-width="5"/>
  <text x="48" y="49" text-anchor="middle" dominant-baseline="middle"
        font-family="Arial, Helvetica, sans-serif" font-size="{font_size}"
        font-weight="700" fill="#111111">{number}</text>
</svg>
'''


def canonical_entry(number: int, relative_path: str) -> dict[str, Any]:
    component_id = f"{CALLOUT_PREFIX}{number:02d}"
    return {
        "id": component_id,
        "displayName": f"Callout Number {number}",
        "category": "symbols_markers",
        "categories": ["symbols_markers"],
        "partNumber": f"CALL-{number:02d}",
        "aliases": [f"callout {number}", f"number {number}", f"marker {number}", f"bubble {number}", str(number)],
        "defaultLabel": str(number),
        "shortName": str(number),
        "sourcePath": relative_path,
        "edgePath": relative_path,
        "bwPath": relative_path,
        "chosenVariant": "custom",
        "preferredEdgeVariant": "custom",
        "hasProcedural": False,
        "notes": "Canonical individual numbered callout marker.",
    }


def override_entry(number: int) -> dict[str, Any]:
    return {
        "id": f"{CALLOUT_PREFIX}{number:02d}",
        "origin": "override",
        "displayName": f"Callout Number {number}",
        "category": "symbols_markers",
        "categories": ["symbols_markers"],
        "collection": "Callout Numbers",
        "partNumber": f"CALL-{number:02d}",
        "aliases": [f"callout {number}", f"number {number}", f"marker {number}", f"bubble {number}", str(number)],
        "defaultLabel": str(number),
        "shortName": str(number),
        "defaultWidth": 44,
        "defaultHeight": 44,
        "favorite": True,
        "approved": True,
        "needsReview": False,
        "status": "approved",
        "retired": False,
        "updatedAt": now_iso(),
    }


def is_callout_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    component_id = str(entry.get("id") or "").strip().lower()
    if component_id.startswith(CALLOUT_PREFIX):
        return True
    name = str(entry.get("displayName") or "").strip()
    match = CALLOUT_NAME_RE.fullmatch(name)
    return bool(match and 1 <= int(match.group(1)) <= CALLOUT_COUNT)


def backup_existing(root: Path, paths: list[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / ".docs" / "patch_backups" / f"callout_numbers_{stamp}"
    for source in paths:
        if not source.exists():
            continue
        target = backup / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
    return backup


def install_callouts(root: Path) -> dict[str, Any]:
    root = root.resolve()
    docs = root / ".docs"
    library = docs / "library"
    builder_path = library / "component_builder_export.json"
    manifest_path = library / "manifest.json"
    callout_dir = library / "components" / "symbols_markers" / "callout_numbers"

    backup = backup_existing(root, [builder_path, manifest_path, callout_dir])
    callout_dir.mkdir(parents=True, exist_ok=True)

    canonical: list[dict[str, Any]] = []
    for number in range(1, CALLOUT_COUNT + 1):
        filename = f"callout-number-{number:02d}.svg"
        svg_path = callout_dir / filename
        svg_path.write_text(callout_svg(number), encoding="utf-8")
        canonical.append(canonical_entry(number, svg_path.relative_to(library).as_posix()))

    builder_raw = read_json(builder_path, {"version": "0.3", "components": []})
    if isinstance(builder_raw, list):
        builder_data: dict[str, Any] = {"version": "0.3", "components": builder_raw}
    elif isinstance(builder_raw, dict):
        builder_data = dict(builder_raw)
    else:
        builder_data = {"version": "0.3", "components": []}

    old_builder = builder_data.get("components")
    if not isinstance(old_builder, list):
        old_builder = []
    builder_data["version"] = builder_data.get("version") or "0.3"
    builder_data["components"] = canonical + [entry for entry in old_builder if not is_callout_entry(entry)]
    builder_data["updatedAt"] = now_iso()
    write_json(builder_path, builder_data)

    manifest = read_json(manifest_path, {"version": 2, "components": []})
    if not isinstance(manifest, dict):
        manifest = {"version": 2, "components": []}
    old_manifest = manifest.get("components")
    if not isinstance(old_manifest, list):
        old_manifest = []
    manifest["version"] = max(int(manifest.get("version") or 2), 2)
    manifest["components"] = [override_entry(n) for n in range(1, CALLOUT_COUNT + 1)] + [
        entry for entry in old_manifest if not is_callout_entry(entry)
    ]
    manifest["updatedAt"] = now_iso()
    write_json(manifest_path, manifest)

    expected_ids = [f"{CALLOUT_PREFIX}{n:02d}" for n in range(1, CALLOUT_COUNT + 1)]
    saved_builder = read_json(builder_path, {})
    saved_components = saved_builder.get("components") if isinstance(saved_builder, dict) else []
    first_ids = [str(entry.get("id") or "") for entry in (saved_components or [])[:CALLOUT_COUNT] if isinstance(entry, dict)]
    if first_ids != expected_ids:
        raise RuntimeError("Callout numbers were not placed first in the library.")

    missing = [n for n in range(1, CALLOUT_COUNT + 1) if not (callout_dir / f"callout-number-{n:02d}.svg").is_file()]
    if missing:
        raise RuntimeError(f"Missing generated callout SVGs: {missing}")

    return {
        "installed": CALLOUT_COUNT,
        "backup": str(backup),
        "builder": str(builder_path),
        "manifest": str(manifest_path),
        "componentFolder": str(callout_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    repo = Path(args.repo)
    if not (repo / "server.py").is_file():
        raise SystemExit(f"Singh360 repository not found: {repo}")
    result = install_callouts(repo)
    print(f"[OK] Installed {result['installed']} individual callout-number components.")
    print("[OK] Callout Number 1 through Callout Number 20 are first in the left library.")
    print(f"[OK] Library backup: {result['backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
