#!/usr/bin/env python3
"""Apply scoped V40 source fixes before validation and live migration.

The patch makes legacy standalone EEPR/EPR cards optional on a clean V39
runtime and hardens curation so obsolete generated marker cards are retired,
while the V39 mapper collection, callouts, safety signs, signage legend, real
equipment, and unrelated user assets remain active.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OLD_REGULATOR_BLOCK = '''    for cid in KEEP_REGULATOR_IDS:
        if by_id.get(cid) is None:
            raise InstallError(f"Required regulator component is missing: {cid}")
    if by_id["s360_rdm_eepr_electronic"].get("shortName") != "EEPR":
        raise InstallError("Electronic regulator is not normalized to EEPR")
    if by_id["s360_rdm_eepr_mechanical"].get("shortName") != "EPR":
        raise InstallError("Mechanical regulator is not normalized to EPR")
'''

NEW_REGULATOR_BLOCK = '''    electronic = by_id.get("s360_rdm_eepr_electronic")
    mechanical = by_id.get("s360_rdm_eepr_mechanical")
    if electronic is not None and electronic.get("shortName") != "EEPR":
        raise InstallError("Existing electronic regulator is not normalized to EEPR")
    if mechanical is not None and mechanical.get("shortName") != "EPR":
        raise InstallError("Existing mechanical regulator is not normalized to EPR")
'''

OLD_RETIRE_BLOCK = '''def should_retire(component: dict[str, Any]) -> bool:
    cid = str(component.get("id") or "").strip()
    if cid in OBSOLETE_IDS or cid.startswith("callout_number_"):
        return True
    name = norm(component.get("displayName") or component.get("name") or component.get("defaultLabel"))
    if LINE_CARD_RE.fullmatch(name):
        return True
    generated = cid.startswith("s360_") or str(component.get("assetKind") or "").startswith("singh360-") or str(component.get("collection") or "").startswith("RDM Standard")
    return generated and name in EXACT_JUNK_NAMES
'''

NEW_RETIRE_BLOCK = '''def should_retire(component: dict[str, Any]) -> bool:
    cid = str(component.get("id") or "").strip()
    if cid in OBSOLETE_IDS or cid.startswith("callout_number_"):
        return True
    name = norm(component.get("displayName") or component.get("name") or component.get("defaultLabel"))
    if LINE_CARD_RE.fullmatch(name):
        return True
    collection = str(component.get("collection") or "")
    category = str(component.get("category") or "").lower()
    if cid in KEEP_SIGN_IDS or cid in KEEP_REGULATOR_IDS:
        return False
    if cid.startswith("callout-number-"):
        return False
    if collection == MAPPER_COLLECTION:
        return False
    if name == "signage legend":
        return False
    generated = (
        cid.startswith("s360_")
        or str(component.get("assetKind") or "").startswith("singh360-")
        or collection.startswith("RDM Standard")
    )
    if generated and category == "symbols_markers":
        return True
    return generated and name in EXACT_JUNK_NAMES
'''


def verify(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    missing: list[str] = []
    if NEW_REGULATOR_BLOCK not in text:
        missing.append("optional legacy regulator verification")
    if NEW_RETIRE_BLOCK not in text:
        missing.append("generated marker retirement rule")
    if missing:
        raise RuntimeError(f"V40 scoped source fixes are incomplete: {missing}")
    return {
        "ok": True,
        "path": str(path),
        "optionalLegacyRegulators": True,
        "retireObsoleteGeneratedMarkers": True,
        "preserveMapperCalloutsSignsAndEquipment": True,
    }


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in text:
        return text, False
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"V40 {label} anchor count was {count}, expected 1")
    return text.replace(old, new, 1), True


def apply(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    changed = False
    text, did_change = replace_once(
        text,
        OLD_REGULATOR_BLOCK,
        NEW_REGULATOR_BLOCK,
        "legacy-regulator",
    )
    changed = changed or did_change
    text, did_change = replace_once(
        text,
        OLD_RETIRE_BLOCK,
        NEW_RETIRE_BLOCK,
        "generated-marker-retirement",
    )
    changed = changed or did_change
    if changed:
        compile(text, str(path), "exec")
        path.write_text(text, encoding="utf-8")
    result = verify(path)
    result["changed"] = changed
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    path = args.repo.resolve() / "scripts" / "install_component_library_v40.py"
    if not path.is_file():
        raise SystemExit(f"V40 installer was not found: {path}")
    result = verify(path) if args.check else apply(path)
    text = json.dumps(result, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
