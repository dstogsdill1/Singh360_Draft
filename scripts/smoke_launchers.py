"""Static launcher and canonical product-identity smoke checks."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BATS = {"START_SINGH360_DRAFT.bat", "STOP_SINGH360_DRAFT.bat"}


def main() -> int:
    problems: list[str] = []
    root_bats = {path.name for path in ROOT.glob("*.bat")}
    if root_bats != EXPECTED_BATS:
        problems.append(f"root BAT files are {sorted(root_bats)!r}, expected {sorted(EXPECTED_BATS)!r}")

    unexpected_scripts = sorted(
        path.name
        for pattern in ("*.cmd", "*.ps1")
        for path in ROOT.glob(pattern)
    )
    if unexpected_scripts:
        problems.append(f"unexpected root launcher scripts: {unexpected_scripts}")

    start = (ROOT / "START_SINGH360_DRAFT.bat").read_text(encoding="utf-8")
    stop = (ROOT / "STOP_SINGH360_DRAFT.bat").read_text(encoding="utf-8")
    required_start = (
        "title Singh360 Draft",
        'set "SINGH360_PORT=8766"',
        "http://127.0.0.1:8766/app",
        "call npm.cmd run build",
    )
    for token in required_start:
        if token not in start:
            problems.append(f"start launcher is missing {token!r}")
    if "if not exist node_modules call npm.cmd ci" not in start:
        problems.append("start launcher does not return from conditional npm ci")
    if "?project=" in start or "ngrok" in start.casefold() or "829" in start:
        problems.append("start launcher is not generic Project Home")
    if "title Stop Singh360 Draft" not in stop or "$port=8766" not in stop:
        problems.append("stop launcher name or port is incorrect")

    obsolete_root = sorted(
        path.name
        for path in ROOT.iterdir()
        if path.is_file()
        and any(
            token in path.name.casefold()
            for token in ("ngrok", "live", "829", "reset", "patch", "cleanup")
        )
    )
    if obsolete_root:
        problems.append(f"obsolete root files remain: {obsolete_root}")

    frontend_index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    if "<title>Singh360 Draft — Drawing Package Editor</title>" not in frontend_index:
        problems.append("browser title is not Singh360 Draft")

    if problems:
        print("LAUNCHER/IDENTITY PROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK: exactly two canonical launchers open Singh360 Draft Project Home.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
