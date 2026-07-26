#!/usr/bin/env python3
"""Compatibility smoke entry point for the exact V39 symbol components."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.smoke_symbol_standard_v39 import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
