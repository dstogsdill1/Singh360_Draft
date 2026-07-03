"""core/library_taxonomy.py — canonical EMS/RDM component taxonomy.

Used by the library auto-categorizer to bucket components into friendly
categories and, where confident (part numbers, logos), canonicalize the name.
Keyword matching is done against displayName / shortName / partNumber only
(extraction tags are too noisy).
"""
from __future__ import annotations

# Canonical category id -> display label (shown in the panel dropdown).
CATEGORIES: list[tuple[str, str]] = [
    ("controllers", "Controllers"),
    ("expansion", "Expansion Modules"),
    ("panels", "Panels / Enclosures"),
    ("network", "Network / Data"),
    ("electrical", "Electrical / Power"),
    ("sensors", "Sensors / Transducers"),
    ("alarms", "Alarms / Safety"),
    ("refrigeration", "Refrigeration Devices"),
    ("lighting", "Lighting Devices"),
    ("symbols", "Symbols / Markers"),
    ("legends", "Legends"),
    ("logos", "Logos"),
    ("reference-page", "Reference Pages"),
    ("review", "Unknown / Needs Review"),
]

# Ordered rules: (category, [keywords lowercased], canonical_name_or_None).
# First match wins, so put the most specific keywords first.
RULES: list[tuple[str, list[str], str | None]] = [
    # Logos (high confidence, safe to relabel).
    ("logos", ["h-e-b", "h e b", "heb logo", "heb "], "H-E-B Logo"),
    ("logos", ["singh360", "singh 360"], "Singh360 Logo"),
    ("logos", ["logo"], None),
    # Controllers (part numbers are reliable).
    ("controllers", ["pr0650cd", "pr0650-cd", "pr0650 cd"], "PR0650CD-TDB Programmable Controller"),
    ("controllers", ["pr0751"], "PR0751-IP Remote Expansion Controller"),
    ("controllers", ["pr0650-cct", "pr0650 cct"], "PR0650-CCT Circuit Controller"),
    ("controllers", ["pr0652"], "PR0652-CCT Circuit Controller"),
    ("controllers", ["pr0680"], "PR0680CD-TDB Programmable Controller"),
    ("controllers", ["pr0650", "tdb controller"], "PR0650CD-TDB Programmable Controller"),
    # Expansion modules.
    ("expansion", ["pr0660"], "PR0660 Stepper Expansion Module"),
    ("expansion", ["pr0661"], "PR0661 Plant I/O Expansion Module"),
    ("expansion", ["pr0662"], "PR0662 Plant I/O Expansion Module"),
    ("expansion", ["pr0663"], "PR0663 Expansion Module"),
    ("expansion", ["stepper valve", "eepr", "eev", "expansion module"], None),
    # Network / data.
    ("network", ["data manager"], "Data Manager"),
    ("network", ["orbit", "touchxl"], "Orbit TouchXL"),
    ("network", ["bacnet router"], "BACnet Router"),
    ("network", ["rdm idf", " idf"], "RDM IDF"),
    ("network", [" mdf", "patch panel", "network switch", "switch stack"], None),
    # Electrical / power.
    ("electrical", ["contactor"], "Contactor"),
    ("electrical", ["relay"], "Relay"),
    ("electrical", ["power supply"], "Power Supply"),
    ("electrical", ["breaker", "disconnect"], None),
    ("electrical", ["powerscout", "wattnode", "dent power", "power monitor", " ct "], None),
    # Panels / enclosures.
    ("panels", [" lcp", "lighting control panel"], "LCP — Lighting Control Panel"),
    ("panels", ["wicp", "walk-in control"], "WICP — Walk-In Control Panel"),
    ("panels", [" ccg"], "CCG Panel"),
    ("panels", [" dle", " pmp", "enclosure", "control panel", "control box"], None),
    # Sensors / transducers.
    ("sensors", ["temperature sensor", "temp sensor", "room temp"], "Temperature Sensor"),
    ("sensors", ["light level"], "Light Level Sensor"),
    ("sensors", ["leak sensor", "refrigerant leak"], "Refrigerant Leak Sensor"),
    ("sensors", ["transducer", "pressure sensor", "humidity", "door switch", "sensor"], None),
    # Alarms / safety.
    ("alarms", ["entrapment switch", " es "], "ES — Entrapment Switch"),
    ("alarms", ["entrapment alarm", " ea "], "EA — Entrapment Alarm"),
    ("alarms", ["leak indicator", " li "], "LI — Leak Indicator"),
    ("alarms", ["door alarm", " da "], "DA — Door Alarm"),
    ("alarms", ["horn", "strobe", "beacon", "alarm"], None),
    # Refrigeration / lighting / legends.
    ("refrigeration", ["condenser", "evaporator", "suction group", "case controller", " rack "], None),
    ("lighting", ["lighting contactor", "dimming", "light sensor", "lighting override"], None),
    ("legends", ["legend"], None),
    # Reference pages (page-sized crops / drawings).
    ("reference-page", ["blueprint", "floor plan", "floorplan", "elevation", "one-line", "one line",
                        "layout", "schematic", "reference page"], None),
]


def classify(display_name: str, short_name: str = "", part_number: str = "",
             aspect: float | None = None) -> tuple[str, str | None]:
    """Return (category_id, canonical_name_or_None). Falls back to review."""
    hay = f" {display_name} {short_name} {part_number} ".lower()
    for cat, keys, canon in RULES:
        if any(k in hay for k in keys):
            return cat, canon
    # Very wide/short images are likely page/reference crops.
    if aspect is not None and (aspect >= 3.0 or aspect <= 0.33):
        return "reference-page", None
    return "review", None
