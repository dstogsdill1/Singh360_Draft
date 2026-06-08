"""Singh360_SmartDraw — deterministic MEP/R diagram generator.

Transforms upstream Singh360_Parser assets (the 11-column app schedule),
relay/contactor control matrices, network port assignments, and optional
Azure Document Intelligence spatial polygons into:

  * SmartDraw VisualScript JSON (VSON)  -> engines/smartdraw_vson.py
  * Microsoft Visio packages (VSDX)     -> engines/visio_vsdx.py

Design rules (inherited from Singh360 AGENTS.md non-negotiables):
  1. No hallucination — unknown values stay blank and are flagged.
  2. Deterministic first — vector/CSV parsing before any OCR.
  3. Traceability — every node/edge carries a source file:row provenance.
  4. Code-only — no customer data committed (see .gitignore + sample_data/).
"""
from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["__version__"]
