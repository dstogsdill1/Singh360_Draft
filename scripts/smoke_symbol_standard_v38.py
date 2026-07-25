#!/usr/bin/env python3
"""Isolated validation for the Singh360 Symbol/Library V38 install."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.install_symbol_standard_v38",
            "--repo",
            str(REPO),
            *args,
        ],
        check=True,
        cwd=REPO,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="s360_symbol_v38_") as temp:
        docs = Path(temp) / ".docs"
        report = Path(temp) / "install-report.json"
        run("--docs", str(docs), "--report", str(report))
        first = json.loads(report.read_text(encoding="utf-8"))
        assert first["symbols"] == 15
        run("--docs", str(docs), "--check")
        second_report = Path(temp) / "second-report.json"
        run("--docs", str(docs), "--report", str(second_report))
        second = json.loads(second_report.read_text(encoding="utf-8"))
        assert second["libraryAdded"] == 0, second
        assert second["retiredExactDuplicates"] == 0, second
        run("--docs", str(docs), "--check")

        template = json.loads(
            (docs / "symbol_mapper" / "templates" / "standard.json").read_text(encoding="utf-8")
        )
        keys = [row["key"] for row in template["symbols"]]
        assert len(keys) == 15
        assert len(keys) == len(set(keys))
        by_code = {}
        for row in template["symbols"]:
            by_code.setdefault(row["code"], []).append(row["label"])
        assert {code: labels for code, labels in by_code.items() if len(labels) > 1} == {
            "S": ["LIQUID LINE SOLENOID VALVE 120V", "CLEAN SWITCH"]
        }
        ls2 = next(row for row in template["symbols"] if row["code"] == "LS2")
        li2 = next(row for row in template["symbols"] if row["code"] == "LI2")
        assert ls2["glyph"] == "LS₂"
        assert li2["glyph"] == "LI₂"
        assert ls2["pattern"] == "split-vertical"
        assert li2["pattern"] == "split-vertical"
        print("Symbol/Library V38 isolated validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
