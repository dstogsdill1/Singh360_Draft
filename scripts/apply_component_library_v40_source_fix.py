#!/usr/bin/env python3
"""Apply the scoped V40 optional legacy-regulator verification fix.

The direct-placement Plan Marker library always includes EEPR and EPR. Legacy
standalone regulator cards are preserved and normalized when they already exist,
but a clean V39 runtime does not contain those older cards and must not fail the
V40 migration merely because they were never installed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OLD_BLOCK = '''    for cid in KEEP_REGULATOR_IDS:
        if by_id.get(cid) is None:
            raise InstallError(f"Required regulator component is missing: {cid}")
    if by_id["s360_rdm_eepr_electronic"].get("shortName") != "EEPR":
        raise InstallError("Electronic regulator is not normalized to EEPR")
    if by_id["s360_rdm_eepr_mechanical"].get("shortName") != "EPR":
        raise InstallError("Mechanical regulator is not normalized to EPR")
'''

NEW_BLOCK = '''    electronic = by_id.get("s360_rdm_eepr_electronic")
    mechanical = by_id.get("s360_rdm_eepr_mechanical")
    if electronic is not None and electronic.get("shortName") != "EEPR":
        raise InstallError("Existing electronic regulator is not normalized to EEPR")
    if mechanical is not None and mechanical.get("shortName") != "EPR":
        raise InstallError("Existing mechanical regulator is not normalized to EPR")
'''


def verify(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if NEW_BLOCK not in text:
        raise RuntimeError("V40 optional legacy-regulator source fix is not installed.")
    return {"ok": True, "path": str(path), "optionalLegacyRegulators": True}


def apply(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    changed = False
    if NEW_BLOCK not in text:
        count = text.count(OLD_BLOCK)
        if count != 1:
            raise RuntimeError(f"V40 legacy-regulator anchor count was {count}, expected 1")
        text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
        compile(text, str(path), "exec")
        path.write_text(text, encoding="utf-8")
        changed = True
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
