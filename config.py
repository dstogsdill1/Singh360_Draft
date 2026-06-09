"""Central configuration for Singh360_SmartDraw.

Loads optional Azure Document Intelligence credentials from a gitignored
.env file, defines canvas/unit constants shared by both render engines, and
maps the upstream app `Category` vocabulary to deterministic visual styles.

No secrets are hardcoded. Azure keys are read only from the environment / .env.
The category list is grounded in the Singh360 bulk-upload template header
(see Singh360_Parser/Sample_Data_File_For_Service_Assets_Bulk_Upload.csv).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- .env (optional) -----------------------------------------------------
try:  # python-dotenv is optional; the deterministic path never needs it.
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover - absence is fine
    pass

# --- Azure Document Intelligence (optional live spatial ingestion) --------
AZURE_DI_ENDPOINT = os.getenv("AZURE_DI_ENDPOINT", "").strip()
AZURE_DI_KEY = os.getenv("AZURE_DI_KEY", "").strip()
DEFAULT_DPI = int(os.getenv("SMARTDRAW_DPI", "200"))

# --- Canonical upstream schema (11-column Singh360 app upload format) ------
APP_COLUMNS: list[str] = [
    "Category",
    "Unit/Type",
    "Name",
    "Connected/Area Served/Refrigerant/Number Of Racks",
    "Fixture Type/Rack Type/Suction Temp/Make",
    "Control Type",
    "Design Temperature Set Point (F)",
    "Issue-Desc",
    "Issue-Reco",
    "Issue-Assign to",
    "Sub Form Category",
]
NAME_COL = "Name"
CATEGORY_COL = "Category"
UNIT_TYPE_COL = "Unit/Type"
# The "Connected/..." column is the relational edge: a row's value here names
# the PARENT node (another row's Name) — e.g. Circuit -> Loop, Compressor ->
# Loop, Condenser -> Rack, Fixture -> Panel.
PARENT_REF_COL = "Connected/Area Served/Refrigerant/Number Of Racks"

# --- Unit constants ------------------------------------------------------
# Visio is natively inches; SmartDraw VisualScript uses points (1in = 72pt).
POINTS_PER_INCH = 72.0
EMU_PER_INCH = 914400

# Default Visio page (Tabloid landscape comfortably holds large schedules).
PAGE_WIDTH_IN = 17.0
PAGE_HEIGHT_IN = 11.0
PAGE_MARGIN_IN = 0.75

# Page-size presets (inches, landscape). Learned from the HEB gold EMS .vsdx,
# which uses Arch D (42x30) at 1:1 scale with a bottom-left origin.
PAGE_PRESETS = {
    "letter": (11.0, 8.5),
    "tabloid": (17.0, 11.0),
    "ledger": (17.0, 11.0),
    "archc": (24.0, 18.0),
    "archd": (42.0, 30.0),   # HEB EMS sheet size
    "arche": (48.0, 36.0),
}


def page_size(name: str) -> tuple[float, float]:
    """Return (width, height) in inches for a preset name (default tabloid)."""
    return PAGE_PRESETS.get((name or "").strip().lower(), (PAGE_WIDTH_IN, PAGE_HEIGHT_IN))

# Default auto-grid shape geometry (inches).
SHAPE_W_IN = 1.9
SHAPE_H_IN = 0.6
COL_GAP_IN = 0.55
ROW_GAP_IN = 1.15


# --- Category -> deterministic style map ---------------------------------
@dataclass(frozen=True)
class CategoryStyle:
    """Visual style for a node category.

    `visio_master` is a *hint* only. Binding a real master requires a mapped
    .vssx (see engines/visio_vsdx.py MasterLibrary). When no stencil is
    supplied the engine falls back to inline rectangle geometry — flagged,
    never silently approximated.
    """

    fill: str  # hex fill   "#RRGGBB"
    line: str  # hex stroke "#RRGGBB"
    text: str  # hex text   "#RRGGBB"
    visio_master: str = "Generic"
    shape_kind: str = "rectangle"  # rectangle | rounded | hexagon | cylinder


# Colors grounded in the app Category vocabulary. Sub-types (relay/contactor/
# network/load) used by the control + network graphs are appended below.
CATEGORY_STYLES: dict[str, CategoryStyle] = {
    "Refrigeration": CategoryStyle("#1F6FEB", "#0B3D91", "#FFFFFF", "RefrigUnit", "cylinder"),
    "EMS": CategoryStyle("#8957E5", "#3A1D6E", "#FFFFFF", "Controller", "rounded"),
    "Lighting": CategoryStyle("#E3B341", "#7A5C00", "#1A1A1A", "LightFixture"),
    "HVAC": CategoryStyle("#2EA043", "#10491F", "#FFFFFF", "RTU"),
    "Electrical": CategoryStyle("#DA3633", "#6E1110", "#FFFFFF", "Panel"),
    "Plumbing": CategoryStyle("#1F9EDB", "#0B4F6E", "#FFFFFF", "Plumb"),
    "Energy Monitoring": CategoryStyle("#57606A", "#24292F", "#FFFFFF", "Meter"),
    "Hydroponics SAT": CategoryStyle("#3FB950", "#10491F", "#1A1A1A", "Grow"),
    "Hydroponics Cx": CategoryStyle("#2EA043", "#10491F", "#FFFFFF", "Grow"),
    "Boilers/DHW": CategoryStyle("#BC4C00", "#5A2400", "#FFFFFF", "Boiler", "cylinder"),
    # Synthetic categories used by the control + network sub-graphs:
    "Relay": CategoryStyle("#D29922", "#7A5C00", "#1A1A1A", "Relay", "rounded"),
    "Contactor": CategoryStyle("#BF8700", "#5A4100", "#FFFFFF", "Contactor", "rounded"),
    "Network": CategoryStyle("#1F2937", "#0B0F14", "#FFFFFF", "Switch", "hexagon"),
}
DEFAULT_STYLE = CategoryStyle("#D0D7DE", "#57606A", "#1A1A1A", "Generic")

# Edge styling by relationship kind.
EDGE_STYLES: dict[str, dict[str, str]] = {
    "hierarchy": {"line": "#57606A", "pattern": "solid"},
    "control": {"line": "#BF8700", "pattern": "dash"},
    "network": {"line": "#1F6FEB", "pattern": "dot"},
}


def style_for(category: str) -> CategoryStyle:
    """Return the style for a category, falling back to a neutral default."""
    return CATEGORY_STYLES.get((category or "").strip(), DEFAULT_STYLE)


def have_azure() -> bool:
    """True when both Azure DI endpoint and key are configured."""
    return bool(AZURE_DI_ENDPOINT and AZURE_DI_KEY)
