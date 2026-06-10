"""core/idf_builder.py — deterministic IDF (network frame) setup rules engine.

Encodes the IDF gathering/naming/grouping rules supplied by the Singh360
draftsman (Kyle Crow) in
``sample_data/Singh360 Inc Mail - Visual studios IDF information.pdf``.

That email is "step one" of IDF setup: gather + normalize the data, then assign
each item to the correct IDF. This module is ONLY the deterministic data-shaping
layer — pure functions with stable output that can be unit-verified against the
email's own worked examples (see ``_selftest`` at the bottom and run this file
directly). Nothing here invents a value: unknown codes pass through and are
reported, never guessed (no-hallucination rule).

Three input families (source schedule -> structured IDF records):

  * Racks   (from the equipment schedule)
      Each rack gets **2 drops**: one for the SuperPAC, and one for the loop OR
      cascade controller depending on rack type (CO2 cascade racks -> cascade
      controller; everything else -> loop controller).

  * Cases   (from the circuit schedule)
      Sorted alphanumerically by Rack + Circuit. The IDF case name strips the
      product designator from the full circuit name:
          RADA01  -> RA01        (R + rack-letter + circuit-number)
          RABK02a -> RA02
      Multiple cases on the same lineup get lowercase a/b/c designators:
          RADA01 (3 cases) -> RA01a, RA01b, RA01c
      Q3-SP / Q3-MV cases carry **2 coils**, named with two trailing lowercase
      letters (case-letter + coil-letter):
          RADA01 case 1 coil 1 -> RA01aa
          RADA01 case 1 coil 2 -> RA01ab
      Case description = full circuit name + case type + temperature + product:
          "RADA01a MD Fresh Dairy"
        case type codes:  MD = Multideck, WI = Wide-Island, RI = Reach-in;
                          Service / 2-deck / 3-deck stay as written.
        temperature:      Fresh or Frozen.
        product:          matches the 2-letter designator (DA in RADA = Dairy).

  * WICP    (from the refrigeration controls general notes)
      Walk-In Control Panels are separated into their own group per panel.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Confirmed vocabulary (grounded in the draftsman email — do not invent)
# --------------------------------------------------------------------------
# Case-type codes. MD/WI/RI are expanded for reference; Service/2-deck/3-deck
# "stay the same" per the email, so they map to themselves.
CASE_TYPE_NAMES: dict[str, str] = {
    "MD": "Multideck",
    "WI": "Wide-Island",
    "RI": "Reach-in",
    "SERVICE": "Service",
    "2-DECK": "2-deck",
    "3-DECK": "3-deck",
}

# Case types that carry two coils per case (-> two trailing letters).
TWO_COIL_CASE_TYPES: frozenset[str] = frozenset({"Q3-SP", "Q3-MV"})

# Product designators confirmed by the email's worked examples (RADA = Dairy,
# RABK = Bakery). Additional HEB department codes are intentionally NOT
# hardcoded — unknown codes are returned blank and flagged for confirmation.
PRODUCT_NAMES: dict[str, str] = {
    "DA": "Dairy",
    "BK": "Bakery",
}

_LETTERS = "abcdefghijklmnopqrstuvwxyz"

# Full circuit name: rack token (R + A-Z) + 2-letter product + circuit number
# (+ optional trailing lowercase lineup letters from the source schedule).
_CIRCUIT_RE = re.compile(r"^\s*(R[A-Z])([A-Z]{2})(\d+)([a-z]*)\s*$", re.IGNORECASE)


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ParsedCircuit:
    """The decomposed parts of a full circuit name (e.g. ``RADA01a``)."""

    raw: str            # "RADA01a"
    rack_token: str     # "RA"
    product_code: str   # "DA"
    circuit_no: str     # "01"  (leading zeros preserved)
    suffix: str         # ""    source lineup letter(s), if any

    @property
    def idf_base(self) -> str:
        """IDF base name = rack token + circuit number (product stripped)."""
        return f"{self.rack_token}{self.circuit_no}"


@dataclass(frozen=True)
class IdfCase:
    """One IDF-assigned case (or coil), fully named and described."""

    idf_name: str        # "RA01a" or "RA01aa"
    full_circuit: str    # "RADA01a"
    rack_token: str      # "RA"
    circuit_no: str      # "01"
    case_letter: str     # "a"  ("" only for a lone single-coil case)
    coil_letter: str     # ""   or "a"/"b" for two-coil case types
    case_type: str       # "MD"
    temperature: str     # "Fresh"
    product: str         # "Dairy"
    description: str     # "RADA01a MD Fresh Dairy"
    source: str = ""


@dataclass(frozen=True)
class RackDrop:
    """One IDF drop assigned to a rack (each rack gets exactly two)."""

    rack: str            # "RACK A"
    drop_no: int         # 1 or 2
    purpose: str         # "SuperPAC" | "Loop Controller" | "Cascade Controller"
    source: str = ""


@dataclass
class WicpGroup:
    """A WICP panel and the rooms/controllers grouped under it."""

    panel: str
    rows: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------
# Circuit parsing + naming
# --------------------------------------------------------------------------
def parse_circuit_name(raw: str) -> ParsedCircuit | None:
    """Decompose a full circuit name, or ``None`` if it does not match.

    >>> parse_circuit_name("RADA01").idf_base
    'RA01'
    >>> parse_circuit_name("RABK02a").idf_base
    'RA02'
    """
    m = _CIRCUIT_RE.match(raw or "")
    if not m:
        return None
    rack, prod, num, suf = m.groups()
    return ParsedCircuit(
        raw=raw.strip(),
        rack_token=rack.upper(),
        product_code=prod.upper(),
        circuit_no=num,
        suffix=suf.lower(),
    )


def circuit_sort_key(parsed: ParsedCircuit) -> tuple[str, int, str]:
    """Sort key for alphanumeric Rack+Circuit ordering (RA01 before RA02)."""
    try:
        n = int(parsed.circuit_no)
    except ValueError:
        n = 0
    return (parsed.rack_token, n, parsed.suffix)


def case_letter(index: int) -> str:
    """0 -> 'a', 1 -> 'b', ... (wraps to 'aa'-style only beyond 26)."""
    if index < len(_LETTERS):
        return _LETTERS[index]
    # Spreadsheet-style overflow (aa, ab, ...) — rare for a single lineup.
    first, second = divmod(index - len(_LETTERS), len(_LETTERS))
    return _LETTERS[first] + _LETTERS[second]


def is_two_coil(case_type: str) -> bool:
    """True for Q3-SP / Q3-MV case types (two coils per case)."""
    return (case_type or "").strip().upper() in {c.upper() for c in TWO_COIL_CASE_TYPES}


def product_name(code: str) -> str:
    """Expand a 2-letter product designator, or '' if not confirmed."""
    return PRODUCT_NAMES.get((code or "").strip().upper(), "")


def temperature_label(value: str) -> str:
    """Normalize a temp value to 'Fresh' or 'Frozen' (else pass through).

    MT (medium temp) -> Fresh and LT (low temp) -> Frozen follow standard HEB
    refrigeration group naming (see the equipment schedule's MT/LT GROUP rows).
    Anything unrecognized is returned unchanged rather than guessed.
    """
    v = (value or "").strip()
    if not v:
        return ""
    low = v.lower()
    if "froz" in low or low in ("lt", "low", "low temp", "frz"):
        return "Frozen"
    if "fresh" in low or low in ("mt", "med", "med temp", "medium temp"):
        return "Fresh"
    return v


def case_description(
    full_circuit: str, case_type: str, temperature: str, product: str
) -> str:
    """Join the four description parts, skipping any that are blank.

    >>> case_description("RADA01a", "MD", "Fresh", "Dairy")
    'RADA01a MD Fresh Dairy'
    """
    parts = [p.strip() for p in (full_circuit, case_type, temperature, product) if p and p.strip()]
    return " ".join(parts)


def build_lineup_cases(
    circuit: str | ParsedCircuit,
    n_cases: int,
    case_type: str = "",
    temperature: str = "",
    *,
    full_circuit: str | None = None,
    source: str = "",
) -> list[IdfCase]:
    """Build the IDF case (and coil) records for one circuit lineup.

    Naming rules, exactly per the draftsman email:
      * single single-coil case on a lineup -> base name only ('RA01').
      * multiple single-coil cases          -> a/b/c suffixes ('RA01a'...).
      * Q3-SP / Q3-MV (two coils)            -> case-letter + coil-letter,
        always present even for a lone case  ('RA01aa', 'RA01ab').
    """
    parsed = parse_circuit_name(circuit) if isinstance(circuit, str) else circuit
    if parsed is None:
        return []
    base = parsed.idf_base
    full = full_circuit or parsed.raw
    product = product_name(parsed.product_code)
    temp = temperature_label(temperature)
    two_coil = is_two_coil(case_type)
    out: list[IdfCase] = []
    for i in range(max(n_cases, 0)):
        cl = case_letter(i)
        if two_coil:
            for ci in range(2):
                coil = case_letter(ci)
                name = f"{base}{cl}{coil}"
                out.append(
                    IdfCase(
                        idf_name=name,
                        full_circuit=full,
                        rack_token=parsed.rack_token,
                        circuit_no=parsed.circuit_no,
                        case_letter=cl,
                        coil_letter=coil,
                        case_type=case_type,
                        temperature=temp,
                        product=product,
                        description=case_description(full, case_type, temp, product),
                        source=source,
                    )
                )
        else:
            cl_use = cl if n_cases > 1 else ""
            name = f"{base}{cl_use}"
            out.append(
                IdfCase(
                    idf_name=name,
                    full_circuit=full,
                    rack_token=parsed.rack_token,
                    circuit_no=parsed.circuit_no,
                    case_letter=cl_use,
                    coil_letter="",
                    case_type=case_type,
                    temperature=temp,
                    product=product,
                    description=case_description(full, case_type, temp, product),
                    source=source,
                )
            )
    return out


# --------------------------------------------------------------------------
# Rack drops
# --------------------------------------------------------------------------
def rack_controller_kind(*type_texts: str) -> str:
    """'Cascade Controller' for CO2 cascade racks, else 'Loop Controller'.

    Looks at any rack descriptor text (System Application, Rack Model, type).
    """
    blob = " ".join(t.upper() for t in type_texts if t)
    return "Cascade Controller" if "CASCADE" in blob else "Loop Controller"


def rack_drops(rack_name: str, *type_texts: str, source: str = "") -> list[RackDrop]:
    """Each rack gets 2 drops: SuperPAC + (loop|cascade) controller."""
    controller = rack_controller_kind(*type_texts)
    return [
        RackDrop(rack=rack_name, drop_no=1, purpose="SuperPAC", source=source),
        RackDrop(rack=rack_name, drop_no=2, purpose=controller, source=source),
    ]


# --------------------------------------------------------------------------
# WICP grouping
# --------------------------------------------------------------------------
def group_wicps_by_panel(rows: list[dict], panel_key: str = "panel") -> list[WicpGroup]:
    """Group WICP rows into one group per panel, preserving first-seen order.

    Each row is a dict; ``panel_key`` (default 'panel') names the column that
    holds the WICP panel id (e.g. 'WICP 01'). Rows with a blank panel are
    grouped under '' so they remain visible rather than dropped.
    """
    order: list[str] = []
    groups: dict[str, WicpGroup] = {}
    for row in rows:
        panel = str(row.get(panel_key, "") or "").strip()
        if panel not in groups:
            groups[panel] = WicpGroup(panel=panel)
            order.append(panel)
        groups[panel].rows.append(row)
    return [groups[p] for p in order]


# --------------------------------------------------------------------------
# Self-verification against the draftsman email's worked examples
# --------------------------------------------------------------------------
def _selftest() -> None:
    # --- Case name derivation (product designator stripped) ---------------
    assert parse_circuit_name("RADA01").idf_base == "RA01"
    assert parse_circuit_name("RABK02a").idf_base == "RA02"
    assert parse_circuit_name("not-a-circuit") is None

    # --- Sort order: RA01 before RA02 -------------------------------------
    a = parse_circuit_name("RADA01")
    b = parse_circuit_name("RABK02a")
    assert circuit_sort_key(a) < circuit_sort_key(b)

    # --- Product expansion (confirmed only) -------------------------------
    assert product_name("DA") == "Dairy"
    assert product_name("BK") == "Bakery"
    assert product_name("ZZ") == ""  # unknown -> blank, never guessed

    # --- Single case -> base name, no letter ------------------------------
    one = build_lineup_cases("RADA01", 1, "MD", "Fresh")
    assert [c.idf_name for c in one] == ["RA01"], [c.idf_name for c in one]

    # --- 3 cases on one lineup -> a/b/c -----------------------------------
    three = build_lineup_cases("RADA01", 3, "MD", "Fresh")
    assert [c.idf_name for c in three] == ["RA01a", "RA01b", "RA01c"]

    # --- Q3-SP / Q3-MV: 2 coils per case -> aa/ab -------------------------
    coils = build_lineup_cases("RADA01", 1, "Q3-SP", "Fresh", full_circuit="RADA01")
    assert [c.idf_name for c in coils] == ["RA01aa", "RA01ab"], [c.idf_name for c in coils]
    coils2 = build_lineup_cases("RADA01", 2, "Q3-MV", "Frozen")
    assert [c.idf_name for c in coils2] == ["RA01aa", "RA01ab", "RA01ba", "RA01bb"]

    # --- Description format -----------------------------------------------
    desc = build_lineup_cases("RADA01a", 1, "MD", "Fresh", full_circuit="RADA01a")[0].description
    assert desc == "RADA01a MD Fresh Dairy", desc

    # --- Rack drops: SuperPAC + loop/cascade by rack type -----------------
    cascade = rack_drops("RACK A", "CO2 CASCADE SPLIT")
    assert [d.purpose for d in cascade] == ["SuperPAC", "Cascade Controller"]
    loop = rack_drops("RACK B", "MT")
    assert [d.purpose for d in loop] == ["SuperPAC", "Loop Controller"]

    # --- WICP grouping by panel -------------------------------------------
    wicp_rows = [
        {"panel": "WICP 01", "room": "Dairy Cooler"},
        {"panel": "WICP 01", "room": "Dairy Cooler"},
        {"panel": "WICP 02", "room": "Bakery Freezer"},
    ]
    groups = group_wicps_by_panel(wicp_rows)
    assert [g.panel for g in groups] == ["WICP 01", "WICP 02"]
    assert len(groups[0].rows) == 2

    print("idf_builder self-test: PASS (all draftsman-email examples verified)")


if __name__ == "__main__":
    _selftest()
