#!/usr/bin/env python3
"""Compatibility entry point for the exact Singh360 symbol standard installer.

V38 previously generated rejected emblem-style assets. Keep this module name so
existing launchers remain valid, but route all work through the verified V39
map-marker migration.
"""
from scripts.install_symbol_standard_v39 import InstallError, main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallError as exc:
        print(f"INSTALL ERROR: {exc}")
        raise SystemExit(2)
