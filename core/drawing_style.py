"""core/drawing_style.py — Milestone 4A drawing style standard (Phase 4).

Single source of truth for the black-and-white professional EMS/CAD drawing
standard: page defaults, typography, line/connector presets, and the category
defaults (symbol kind, device type, default ports) consumed by the component
library (manifest v2) and the symbol generator.

Everything here is deterministic data — no I/O, no hallucinated vendor values.
Colour is only ever an optional *screen* aid; every preset is defined so the
export is readable in pure black-and-white.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Page defaults --------------------------------------------------------
# ANSI B / 17x11 landscape is the working default; 8.5x11 scales down.
DEFAULT_SHEET = "ansi_b"
SHEET_SIZES_IN: dict[str, tuple[float, float]] = {
    "ansi_a": (11.0, 8.5),   # Letter landscape (scale-down target)
    "ansi_b": (17.0, 11.0),  # Tabloid / ledger — default working sheet
    "arch_b": (18.0, 12.0),
    "arch_c": (24.0, 18.0),
    "arch_d": (36.0, 24.0),
}

# Typography (points). Overflow creates continuation sheets — never scroll.
TYPE_SCALE = {
    "body_min": 7.5,
    "body_max": 9.0,
    "table_min": 6.5,
    "table_max": 8.0,
    "header_min": 10.0,
    "header_max": 12.0,
    "title_min": 14.0,
    "title_max": 18.0,
}

# Underlays (floor plans / PDF pages) render faint and locked.
UNDERLAY_GRAY_MIN = 0.10   # 10%
UNDERLAY_GRAY_MAX = 0.25   # 25%

# Equipment symbols: black stroke, white fill.
SYMBOL_STROKE = "#000000"
SYMBOL_FILL = "#FFFFFF"
SYMBOL_STROKE_W_MIN = 1.0   # pt
SYMBOL_STROKE_W_MAX = 1.5   # pt

# Existing vs new equipment.
EXISTING_STROKE = "#8A8A8A"     # light gray
EXISTING_DASH = "6 4"           # dashed
NEW_STROKE = "#000000"          # solid black


@dataclass(frozen=True)
class ConnectorPreset:
    """A named line/connector style. `dash` is an SVG dash-array ('' = solid)."""

    id: str
    label: str
    stroke: str = "#000000"
    width: float = 1.0        # pt
    dash: str = ""            # '' solid | 'a b' pattern
    double: bool = False      # heavy parallel/double line (power)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "stroke": self.stroke,
            "width": self.width,
            "dash": self.dash,
            "double": self.double,
            "note": self.note,
        }


# Phase 4 line presets. All readable in black-and-white by shape/dash/weight,
# not colour. Colour values stay black/gray so exports never rely on hue.
CONNECTOR_PRESETS: list[ConnectorPreset] = [
    ConnectorPreset("cat6", "CAT6 / Data", "#000000", 1.0, "", False, "solid thin black"),
    ConnectorPreset("fiber", "FIBER", "#000000", 1.0, "12 5", False, "long dash"),
    ConnectorPreset("bacnet", "BACnet / MS-TP", "#000000", 1.0, "6 3 1 3", False, "dash-dot"),
    ConnectorPreset("canbus", "CANbus", "#000000", 1.0, "1 3", False, "dotted"),
    ConnectorPreset("control", "Control Wiring", "#3A3A3A", 1.0, "", False, "thin solid gray/black"),
    ConnectorPreset("line_voltage", "Line Voltage", "#000000", 2.0, "", False, "heavy solid black"),
    ConnectorPreset("power", "Power", "#000000", 2.25, "", True, "heavy double / parallel"),
    ConnectorPreset("reference", "EXISTING / Reference", "#8A8A8A", 1.0, "6 4", False, "light gray dashed"),
]

CONNECTOR_PRESET_IDS = [p.id for p in CONNECTOR_PRESETS]


def connector_styles_payload() -> dict:
    """Serializable default written to library/connector_styles.json."""
    return {
        "version": 1,
        "presets": [p.to_dict() for p in CONNECTOR_PRESETS],
    }


def connector_preset(preset_id: str) -> ConnectorPreset:
    """Return a preset by id (defaults to CAT6/Data if unknown)."""
    for p in CONNECTOR_PRESETS:
        if p.id == preset_id:
            return p
    return CONNECTOR_PRESETS[0]


# --- Category defaults ----------------------------------------------------
# Folder name == category id. These defaults feed manifest v2 (type, size,
# label position, ports) and the symbol generator (symbol kind).
@dataclass(frozen=True)
class CategoryDefault:
    label: str
    type: str            # device | panel | sensor | alarm | connector | logo | reference
    symbol_kind: str     # controller | enclosure | device | siren | marker | logo | reference
    width: int = 120
    height: int = 42
    label_position: str = "bottom"
    ports: list[dict] = field(default_factory=list)


def _lr_ports(power_bottom: bool = False) -> list[dict]:
    ports = [
        {"id": "left", "x": 0.0, "y": 0.5, "kind": "data"},
        {"id": "right", "x": 1.0, "y": 0.5, "kind": "data"},
    ]
    if power_bottom:
        ports.append({"id": "bottom", "x": 0.5, "y": 1.0, "kind": "power"})
    return ports


CATEGORY_DEFAULTS: dict[str, CategoryDefault] = {
    "controllers": CategoryDefault("Controllers", "device", "controller", 120, 42, "bottom", _lr_ports(True)),
    "expansion_modules": CategoryDefault("Expansion Modules", "device", "controller", 108, 40, "bottom", _lr_ports(True)),
    "panels_enclosures": CategoryDefault("Panels / Enclosures", "panel", "enclosure", 140, 96, "top", _lr_ports(True)),
    "electrical_power": CategoryDefault("Electrical / Power", "device", "device", 96, 48, "bottom", _lr_ports(True)),
    "network_data": CategoryDefault("Network / Data", "device", "device", 132, 40, "bottom", _lr_ports(False)),
    "sensors_transducers": CategoryDefault("Sensors / Transducers", "sensor", "marker", 40, 40, "bottom",
                                           [{"id": "signal", "x": 0.5, "y": 1.0, "kind": "signal"}]),
    "alarms_safety": CategoryDefault("Alarms / Safety", "alarm", "siren", 44, 44, "bottom",
                                     [{"id": "signal", "x": 0.5, "y": 1.0, "kind": "signal"}]),
    "refrigeration": CategoryDefault("Refrigeration", "device", "device", 120, 56, "bottom", _lr_ports(True)),
    "hvac": CategoryDefault("HVAC", "device", "device", 120, 64, "bottom", _lr_ports(True)),
    "lighting": CategoryDefault("Lighting", "device", "device", 108, 44, "bottom", _lr_ports(True)),
    "logos": CategoryDefault("Logos", "logo", "logo", 140, 60, "none", []),
    "symbols_markers": CategoryDefault("Symbols / Markers", "connector", "marker", 40, 40, "bottom", []),
    "reference_pages": CategoryDefault("Reference Pages", "reference", "reference", 320, 240, "none", []),
    "custom": CategoryDefault("Custom", "device", "device", 120, 42, "bottom", _lr_ports(False)),
}

# The canonical category folders scanned by Refresh Library (Phase 0).
LIBRARY_CATEGORIES = list(CATEGORY_DEFAULTS.keys())


def category_default(category: str) -> CategoryDefault:
    return CATEGORY_DEFAULTS.get(category, CATEGORY_DEFAULTS["custom"])
