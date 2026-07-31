"""Apply the canonical LSc/LSg/LS/LSb migration to one library root."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.leak_sensor_standard import apply_leak_sensor_standard


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-dir", type=Path, default=Path(os.environ.get("SINGH360_DOCS_DIR", ".docs")))
    args = parser.parse_args()
    print(json.dumps(apply_leak_sensor_standard(args.docs_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
