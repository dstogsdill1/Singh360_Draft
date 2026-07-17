
import os, re, json, csv, shutil, hashlib, datetime, pathlib
from typing import Any, Dict, List, Tuple

REPO_MARKER = "server.py"
LIBRARY_DIR = pathlib.Path(".docs") / "library"
EXPORT_JSON = LIBRARY_DIR / "component_builder_export.json"
MANIFEST_JSON = LIBRARY_DIR / "manifest.json"

CATEGORIES = [
    "Controllers",
    "Expansion Modules",
    "Panels / Enclosures",
    "Network / Data",
    "Electrical / Power",
    "Sensors / Transducers",
    "Alarms / Safety",
    "Refrigeration Devices",
    "HVAC",
    "Lighting Devices",
    "Symbols / Markers",
    "Legends",
    "Logos",
    "Reference Pages",
    "Unknown / Needs Review",
]

def repo_root(start=None):
    p = pathlib.Path(start or os.getcwd()).resolve()
    for candidate in [p] + list(p.parents):
        if (candidate / ".docs").exists() or (candidate / REPO_MARKER).exists():
            return candidate
    return p

def now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def squash(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower()).strip()

def component_text(c: Dict[str, Any]) -> str:
    parts = []
    for k in [
        "id","name","displayName","defaultLabel","shortName","category","manufacturer",
        "partNumber","aliases","tags","notes","sourcePath","edgePath","bwPath","source",
        "file","filename","path","sourceFile","edgeFile","bwFile"
    ]:
        v = c.get(k)
        if isinstance(v, list):
            parts += [str(x) for x in v]
        elif v:
            parts.append(str(v))
    return " ".join(parts)

def ensure_list(v):
    if not v: return []
    if isinstance(v, list): return v
    if isinstance(v, str): return [x.strip() for x in re.split(r"[,;|]", v) if x.strip()]
    return [str(v)]

def title_keep_acronyms(text):
    if not text: return text
    keep = {
        "li":"LI", "da":"DA", "ls":"LS", "lsc":"LSc", "ea":"EA", "es":"ES", "ds":"DS",
        "idf":"IDF", "mdf":"MDF", "wicp":"WICP", "lcp":"LCP", "pcp":"PCP", "ccp":"CCP",
        "rdm":"RDM", "ems":"EMS", "bacnet":"BACnet", "cat6":"CAT6", "canbus":"CANbus",
        "oat":"OAT", "lt":"LT", "ct":"CT", "eev":"EEV", "llsv":"LLSV", "co2":"CO2",
        "ps48":"PS48", "ps24":"PS24", "ps12":"PS12", "ps3":"PS3", "tdb":"TDB",
    }
    words = re.split(r"(\s+|-|/)", text)
    out = []
    for w in words:
        key = re.sub(r"[^a-z0-9]", "", w.lower())
        if key in keep:
            out.append(keep[key])
        elif w.strip() and re.match(r"^[a-z]", w):
            out.append(w[:1].upper() + w[1:].lower())
        else:
            out.append(w)
    return "".join(out)

def clean_display_name(raw):
    s = str(raw or "").strip()
    s = re.sub(r"(?i)^symbol[_\s-]+", "", s)
    s = re.sub(r"(?i)^sym[_\s-]+", "", s)
    s = re.sub(r"(?i)\bsource\b", "", s)
    s = re.sub(r"(?i)\bedge\b", "", s)
    s = re.sub(r"(?i)\bb[\s/_-]*w\b", "", s)
    s = re.sub(r"(?i)\bbold\b", "", s)
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return title_keep_acronyms(s)

def image_paths(c: Dict[str, Any]) -> List[str]:
    paths = []
    for k in ["sourcePath","edgePath","bwPath","sourceFile","edgeFile","bwFile","file","filename","path","src"]:
        v = c.get(k)
        if v and isinstance(v, str) and re.search(r"\.(png|jpg|jpeg|svg|webp)$", v, re.I):
            paths.append(v)
    variants = c.get("variants")
    if isinstance(variants, dict):
        for v in variants.values():
            if isinstance(v, str) and re.search(r"\.(png|jpg|jpeg|svg|webp)$", v, re.I):
                paths.append(v)
            elif isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, str) and re.search(r"\.(png|jpg|jpeg|svg|webp)$", vv, re.I):
                        paths.append(vv)
    return list(dict.fromkeys(paths))

def resolve_path(root: pathlib.Path, p: str) -> pathlib.Path:
    raw = pathlib.Path(str(p).replace("\\", "/"))
    if raw.is_absolute():
        return raw
    return (root / raw).resolve()

def first_existing_image(root: pathlib.Path, c: Dict[str, Any]):
    for p in image_paths(c):
        rp = resolve_path(root, p)
        if rp.exists():
            return str(rp.relative_to(root).as_posix()) if str(rp).startswith(str(root)) else str(rp)
    return ""

def sha1_file(path: pathlib.Path):
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 512), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def load_json_file(path: pathlib.Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return json.loads(path.read_text())

def save_json_file(path: pathlib.Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def extract_components(data):
    if data is None:
        return [], None
    if isinstance(data, list):
        return data, "list"
    if isinstance(data, dict):
        for key in ["components", "items", "library", "assets"]:
            if isinstance(data.get(key), list):
                return data[key], key
    return [], None

def inject_components(data, key, comps):
    if data is None or key is None:
        return {"components": comps, "componentCount": len(comps)}
    if key == "list":
        return comps
    if isinstance(data, dict):
        data[key] = comps
        if "componentCount" in data:
            data["componentCount"] = len(comps)
        if "count" in data:
            data["count"] = len(comps)
        return data
    return {"components": comps, "componentCount": len(comps)}

def load_library(root: pathlib.Path):
    lib_root = root / LIBRARY_DIR
    export_data = load_json_file(root / EXPORT_JSON)
    manifest_data = load_json_file(root / MANIFEST_JSON)
    export_components, export_key = extract_components(export_data)
    manifest_components, manifest_key = extract_components(manifest_data)

    if export_components:
        comps = export_components
        source = "component_builder_export.json"
    elif manifest_components:
        comps = manifest_components
        source = "manifest.json"
    else:
        comps = []
        source = "none"

    # Deduplicate in-memory by id+paths, keeping all if unsure.
    return {
        "root": root,
        "source": source,
        "components": comps,
        "export_data": export_data,
        "export_key": export_key,
        "manifest_data": manifest_data,
        "manifest_key": manifest_key,
    }

def backup_library(root: pathlib.Path) -> pathlib.Path:
    lib = root / LIBRARY_DIR
    stamp = now_stamp()
    backup = lib / f"_metadata_backup_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for rel in [EXPORT_JSON, MANIFEST_JSON]:
        src = root / rel
        if src.exists():
            shutil.copy2(src, backup / src.name)
    # also backup top-level csv manifests if any
    for f in lib.rglob("*.csv"):
        if "_metadata_backup_" in str(f):
            continue
        try:
            rel = f.relative_to(lib)
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
        except Exception:
            pass
    return backup

def canonical_rules(c: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    text = component_text(c)
    sn = squash(text)
    tn = norm(text)
    changes = []
    out = dict(c)
    current_name = out.get("displayName") or out.get("name") or out.get("defaultLabel") or out.get("id") or ""

    def set_meta(display, category, part="", collection="", short="", aliases=None, status="approved", note=""):
        nonlocal changes
        if out.get("displayName") != display:
            changes.append(f"name->{display}")
        out["displayName"] = display
        out["name"] = display
        out["defaultLabel"] = short or display
        if short:
            out["shortName"] = short
        if category:
            out["category"] = category
        if collection:
            out["collection"] = collection
        if part:
            out["partNumber"] = part
        if aliases:
            old = ensure_list(out.get("aliases"))
            merged = []
            for a in old + aliases:
                if a and a not in merged:
                    merged.append(a)
            out["aliases"] = merged
        out["status"] = status
        out["retired"] = True if status in ["retired", "duplicate", "reference_page"] else bool(out.get("retired", False))
        if note:
            out["notes"] = (str(out.get("notes") or "") + (" | " if out.get("notes") else "") + note).strip()

    # hard junk / placeholders
    if re.search(r"\b(thumb only|thumbnail only)\b", tn):
        set_meta(clean_display_name(current_name) or "Thumbnail Only - Retired", "Unknown / Needs Review", status="retired", note="Retired: thumbnail-only item.")
        return out, changes
    if re.search(r"\b(stepper|intuity|intuitive review|mini tdb|\btdb\b)\b", tn) and not re.search(r"pr0?660|pr0?751|pr0?650|pr0?680|pr0?663|pr0?662|pr0?661", sn):
        # these may be real, but not enough metadata.
        set_meta(clean_display_name(current_name) or "Needs Review", "Unknown / Needs Review", status="needs_review", note="Needs review: ambiguous label without part number.")
        return out, changes

    # logos
    if re.search(r"\bheb\b.*logo|logo.*\bheb\b", tn):
        set_meta("H-E-B Logo", "Logos", collection="Logos", aliases=["HEB"], status="approved")
        return out, changes
    if re.search(r"singh\s*360|singh360", tn) and "logo" in tn:
        set_meta("Singh360 Logo", "Logos", collection="Logos", aliases=["SINGH360"], status="approved")
        return out, changes

    # controllers
    if "pr0650cdtdb" in sn or ("pr0650" in sn and "tdb" in sn):
        set_meta("PR0650CD-TDB Programmable TDB Controller", "Controllers", "PR0650CD-TDB", "RDM Controllers", aliases=["PR0650", "650", "TDB Controller"])
    elif "pr0680cdtdb" in sn or ("pr0680" in sn and "tdb" in sn):
        set_meta("PR0680CD-TDB Mini Programmable Controller", "Controllers", "PR0680CD-TDB", "RDM Controllers", aliases=["PR0680", "680", "Mini Controller"])
    elif "pr0751" in sn:
        set_meta("PR0751-IP Intuitive EEV Controller", "Controllers", "PR0751-IP", "RDM Controllers", aliases=["PR0751", "Intuitive EEV"])
    elif "pr0652" in sn:
        set_meta("PR0652-CCT Circuit Controller", "Controllers", "PR0652-CCT", "RDM Controllers", aliases=["PR0652", "652"])
    elif "pr0650cct" in sn:
        set_meta("PR0650-CCT Circuit Controller", "Controllers", "PR0650-CCT", "RDM Controllers", aliases=["CCT"])
    elif "pr0510" in sn or "kitheb" in sn or re.search(r"\b(data manager|dm touch|dmt)\b", tn):
        set_meta("RDM Data Manager", "Controllers", "PR0510-KitHEB", "RDM Controllers", "DM", aliases=["Data Manager", "DMT", "PR0510-KitHEB"])
    elif "pr0617" in sn or "touchxl" in sn or "touch xl" in tn or re.search(r"\borbit\b", tn):
        set_meta("RDM Orbit TouchXL Remote Workstation", "Controllers", "PR0617-OB-E-BK", "RDM Controllers", "Orbit", aliases=["TouchXL", "Touch XL", "PR0617"])

    # expansion modules
    elif "pr0660" in sn:
        set_meta("PR0660 Bottom Row Expansion Module", "Expansion Modules", "PR0660", "RDM Expansion Modules", aliases=["0660"])
    elif "pr0661" in sn:
        set_meta("PR0661 Plant I/O Expansion Module", "Expansion Modules", "PR0661", "RDM Expansion Modules", aliases=["0661", "Plant I/O"])
    elif "pr0662" in sn:
        set_meta("PR0662 Expansion Module Connector", "Expansion Modules", "PR0662", "RDM Expansion Modules", aliases=["0662", "Connector"])
    elif "pr0663" in sn:
        set_meta("PR0663 Mini I/O Expansion Board", "Expansion Modules", "PR0663", "RDM Expansion Modules", aliases=["0663", "Mini I/O"])

    # network/data
    elif "basrt" in sn or "bacnetrouter" in sn or "bacnetgateway" in sn:
        set_meta("BASRT-B BACnet Gateway / Router", "Network / Data", "BASRT-B", "HVAC / BACnet", aliases=["BACnet Router", "BACnet Gateway"])
    elif re.search(r"\brdm\s*idf\b|\bidf\s*switch\b|48\s*port\s*switch|switch\s*stack", tn):
        set_meta("RDM IDF 48-Port Switch Stack", "Network / Data", "RDM-IDF", "Network / RDM IDF", aliases=["RDM IDF", "48-Port Switch"])
    elif re.search(r"\bmdf\b|network rack|idf rack", tn):
        set_meta("MDF Rack / Network Rack", "Network / Data", "MDF-RACK", "Network / RDM IDF", aliases=["MDF", "Network Rack"])

    # power
    elif re.search(r"ps48|powerscout\s*48|dent\s*48", sn):
        set_meta("DENT PowerScout 48 HD", "Electrical / Power", "PS48HD-C-D-N", "Power Metering", aliases=["PowerScout 48 HD", "PowerScout PS48", "DENT PS48"])
    elif re.search(r"ps24|powerscout\s*24", sn):
        set_meta("DENT PowerScout 24 HD", "Electrical / Power", "PS24HD-C-D-N", "Power Metering", aliases=["PowerScout 24 HD", "PowerScout PS24", "DENT PS24"])
    elif re.search(r"ps12|powerscout\s*12", sn):
        set_meta("DENT PowerScout 12 HD", "Electrical / Power", "PS12HD-C-D-N", "Power Metering", aliases=["PowerScout 12 HD", "PowerScout PS12", "DENT PS12"])
    elif re.search(r"ps3|powerscout\s*3", sn):
        set_meta("DENT PowerScout 3 HD", "Electrical / Power", "PS3HD-C-D-N", "Power Metering", aliases=["PowerScout 3 HD", "PowerScout PS3", "DENT PS3"])
    elif "rogowski" in tn or "rocoil" in tn or "ctr36" in sn or "ct r36" in tn:
        set_meta("Rogowski Rope CT - 36 inch", "Electrical / Power", "CT-R36-A4U", "Power Metering", aliases=["RoCoil", "Rogowski CT"])
    elif "cthmc0100" in sn or "0100" in sn and "ct" in sn:
        set_meta("Mini Hinged Split-Core CT 100A", "Electrical / Power", "CT-HMC-0100-U", "Power Metering")
    elif "cthmc0200" in sn or "0200" in sn and "ct" in sn:
        set_meta("Mini Hinged Split-Core CT 200A", "Electrical / Power", "CT-HMC-0200-U", "Power Metering")
    elif "ctsmc0400" in sn or "0400" in sn and "ct" in sn:
        set_meta("Mini Split-Core CT 400A", "Electrical / Power", "CT-SMC-0400-U", "Power Metering")
    elif "ctsmc0600" in sn or "0600" in sn and "ct" in sn:
        set_meta("Mini Split-Core CT 600A", "Electrical / Power", "CT-SMC-0600-U", "Power Metering")
    elif "contactor" in tn and "lighting" in tn:
        if "1" in tn and "pole" in tn: pole="1-Pole"
        elif "2" in tn and "pole" in tn: pole="2-Pole"
        elif "3" in tn and "pole" in tn: pole="3-Pole"
        else: pole="Lighting"
        set_meta(f"{pole} Lighting Contactor", "Electrical / Power", "", "Lighting", aliases=["Contactor"])

    # panels / enclosures
    elif re.search(r"\bwicp\b|walk in control panel|walk-in control panel", tn):
        set_meta("WICP Walk-In Control Panel Enclosure", "Panels / Enclosures", "WICP", "Panels / Enclosures", "WICP")
    elif re.search(r"\blcp\b|lighting control panel", tn):
        set_meta("LCP Lighting Control Panel Enclosure", "Panels / Enclosures", "LCP", "Panels / Enclosures", "LCP")
    elif re.search(r"\bpcp\b|pharmacy control panel", tn):
        set_meta("PCP Pharmacy Control Panel Enclosure", "Panels / Enclosures", "PCP", "Panels / Enclosures", "PCP")
    elif re.search(r"\bccp\b|case control panel|ccg panel|dle panel", tn):
        set_meta("CCP Case Control Panel Enclosure", "Panels / Enclosures", "CCP", "Panels / Enclosures", "CCP")

    # sensors
    elif "pr0198" in sn or "lightlevel" in sn or "oat" in sn or re.search(r"\blt\b", tn):
        set_meta("Light Level Sensor / OAT", "Sensors / Transducers", "PR0198-10K2", "Lighting", "LT", aliases=["OAT", "Light Level"])
    elif "pr0250" in sn or "white air probe" in tn or "refrigeration temp" in tn:
        set_meta("10K2 Refrigeration Temp Probe", "Sensors / Transducers", "PR0250-P4", "Refrigeration IO", aliases=["Temp Probe"])
    elif "a cp r" in tn or "zone temp" in tn or "room temp" in tn or "space temp" in tn:
        set_meta("Zone Temperature Sensor", "Sensors / Transducers", "A/CP-R", "HVAC / BACnet", aliases=["Zone Temp", "Room Temp"])
    elif "a rh3" in tn or "humidity" in tn:
        set_meta("Indoor Temperature / RH Combo Sensor", "Sensors / Transducers", "A/RH3-CP-R", "HVAC / BACnet", aliases=["Temp/RH"])
    elif "bbq" in tn or "high temperature temp probe" in tn or "ttbbq" in tn:
        set_meta("High Temperature BBQ Stack Probe", "Sensors / Transducers", "X/CP-D-4-GD-HTF", "Refrigeration IO", aliases=["BBQ Stack", "High Temp"])

    # alarms/safety
    elif "ref lk 832" in tn or "reflk832" in sn or ("hfc" in tn and "leak" in tn) or ("ls" in tn and "refrigerant" in tn and "co2" not in tn):
        set_meta("LS HFC Refrigerant Leak Detector", "Alarms / Safety", "REF-LK-832", "WICP / Leak / Entrapment", "LS", aliases=["HFC Leak"])
    elif "ct1o" in sn or "ctio" in sn or ("co2" in tn and "leak" in tn) or "lsc" in sn:
        set_meta("LSc CO2 Refrigerant Leak Detector", "Alarms / Safety", "CT1O-A3D", "WICP / Leak / Entrapment", "LSc", aliases=["CO2 Leak"])
    elif "s360li" in sn or re.search(r"\bli\b", tn) and "leak" in tn:
        set_meta("LI Leak Indicator Horn/Strobe", "Alarms / Safety", "S360/LI", "WICP / Leak / Entrapment", "LI", aliases=["Leak Indicator"])
    elif "s360da" in sn or re.search(r"\bda\b", tn) and ("door" in tn or "alarm" in tn):
        set_meta("DA Door Open Annunciator/Strobe", "Alarms / Safety", "S360/DA", "WICP / Leak / Entrapment", "DA", aliases=["Door Alarm"])
    elif "s360ea" in sn or re.search(r"\bea\b", tn) and "entrap" in tn:
        set_meta("EA Entrapment Alarm Strobe", "Alarms / Safety", "S360/EA", "WICP / Leak / Entrapment", "EA", aliases=["Entrapment Alarm"])
    elif "5320" in sn or "entrapment switch" in tn or re.search(r"\bes\b", tn) and "entrap" in tn:
        set_meta("ES Entrapment Switch", "Alarms / Safety", "5320-0", "WICP / Leak / Entrapment", "ES", aliases=["Entrapment Switch Box"])
    elif "vip100" in sn or "door contact" in tn or "door switch" in tn:
        set_meta("Door Contact Switch", "Alarms / Safety", "VIP100-69L", "WICP / Leak / Entrapment", "DS", aliases=["Magnetic Door Contact"])
    elif "56pb" in sn or "silence" in tn:
        set_meta("Horn Silence Button", "Alarms / Safety", "56PB", "WICP / Leak / Entrapment")
    elif "cs24waw" in sn or ("amber" in tn and "strobe" in tn):
        set_meta("Amber High Temp Alarm Strobe", "Alarms / Safety", "CS-24WAW", "WICP / Leak / Entrapment")
    elif "cs24wrw" in sn or ("red" in tn and "strobe" in tn):
        set_meta("Red Rack / Computer Alarm Strobe", "Alarms / Safety", "CS-24WRW", "WICP / Leak / Entrapment")

    # refrigeration devices and problem duplicates
    elif "liquid line solenoid" in tn or "llsv" in tn:
        set_meta("LLSV Liquid Line Solenoid Valve", "Refrigeration Devices", "LLSV", "Refrigeration IO", aliases=["Liquid Line Solenoid"])
    elif re.search(r"\bvalve open\b|\bvalve closed\b|generic valve", tn):
        set_meta(clean_display_name(current_name) or "Valve Symbol - Needs Review", "Symbols / Markers", collection="Symbols / Layout Markers", status="needs_review", note="Needs review: generic valve symbol must not masquerade as LLSV if artwork is identical.")
    elif "defrost heater" in tn or "anti sweat" in tn or "heater" in tn:
        set_meta(clean_display_name(current_name) or "Heater Symbol - Needs Artwork", "Refrigeration Devices", collection="Refrigeration IO", status="needs_review", note="Needs distinct artwork; do not approve if image duplicates another heater.")
    elif "fan" in tn:
        set_meta(clean_display_name(current_name) or "Fan Symbol - Needs Review", "Refrigeration Devices", collection="Refrigeration IO", status="needs_review", note="Needs visual review; do not approve broken fan blade artwork.")

    # line legends
    elif re.search(r"line\s*cat6", tn) or (tn.strip() == "cat6"):
        set_meta("CAT6", "Symbols / Markers", "CAT6", "Symbols / Layout Markers")
    elif re.search(r"line\s*fiber", tn) or tn.strip() == "fiber":
        set_meta("Fiber", "Symbols / Markers", "FIBER", "Symbols / Layout Markers")
    elif re.search(r"line\s*control", tn):
        set_meta("Control Wiring", "Symbols / Markers", "CONTROL-WIRING", "Symbols / Layout Markers")
    elif re.search(r"line\s*existing", tn):
        set_meta("Existing / Reference", "Symbols / Markers", "EXISTING-REFERENCE", "Symbols / Layout Markers")
    elif re.search(r"line\s*voltage", tn):
        set_meta("Line Voltage", "Symbols / Markers", "LINE-VOLTAGE", "Symbols / Layout Markers")
    elif re.search(r"line\s*bacnet", tn):
        set_meta("BACnet", "Symbols / Markers", "BACNET-LINE", "Symbols / Layout Markers")
    elif re.search(r"line\s*canbus", tn):
        set_meta("CANbus", "Symbols / Markers", "CANBUS-LINE", "Symbols / Layout Markers")

    # reference pages
    elif re.search(r"blueprint|floor plan|sheet|page crop|reference page|layout page", tn):
        set_meta(clean_display_name(current_name) or "Reference Page", "Reference Pages", collection="Reference Pages", status="reference_page", note="Reference/page crop; hidden from normal component library.")

    else:
        # clean user-facing name but do not pretend it is approved
        cleaned = clean_display_name(current_name)
        if cleaned and cleaned != current_name:
            out["displayName"] = cleaned
            out["name"] = cleaned
            changes.append(f"clean name->{cleaned}")
        if not out.get("status"):
            out["status"] = "needs_review"
        if not out.get("category"):
            out["category"] = "Unknown / Needs Review"
        if out.get("status") == "needs_review":
            out["retired"] = True  # hidden in current app until approved in manager

    # no "sym" prefixes
    for fld in ["displayName", "name", "defaultLabel"]:
        if fld in out and isinstance(out[fld], str):
            new = clean_display_name(out[fld])
            if new and new != out[fld]:
                out[fld] = new
                changes.append(f"{fld} cleaned")
    return out, changes

def apply_canonical_first_pass(root: pathlib.Path, dry_run=True):
    state = load_library(root)
    comps = [dict(c) for c in state["components"]]
    report = []
    new = []
    for idx, c in enumerate(comps):
        before = dict(c)
        after, changes = canonical_rules(c)
        after.setdefault("id", before.get("id") or squash(after.get("displayName") or f"component_{idx}"))
        after.setdefault("displayName", clean_display_name(before.get("displayName") or before.get("name") or before.get("id") or f"Component {idx+1}"))
        after.setdefault("status", "needs_review")
        after.setdefault("category", "Unknown / Needs Review")
        after["previewPath"] = first_existing_image(root, after)
        new.append(after)
        if changes or before.get("displayName") != after.get("displayName") or before.get("category") != after.get("category") or before.get("status") != after.get("status"):
            report.append({
                "index": idx,
                "oldDisplayName": before.get("displayName") or before.get("name") or before.get("id") or "",
                "newDisplayName": after.get("displayName") or "",
                "oldCategory": before.get("category") or "",
                "newCategory": after.get("category") or "",
                "status": after.get("status") or "",
                "retired": after.get("retired", False),
                "partNumber": after.get("partNumber", ""),
                "changes": "; ".join(changes),
                "notes": after.get("notes", ""),
            })

    # flag duplicate image conflicts
    hashes = {}
    for i, c in enumerate(new):
        fp = c.get("previewPath") or first_existing_image(root, c)
        if not fp:
            continue
        rp = resolve_path(root, fp)
        h = sha1_file(rp)
        if not h:
            continue
        hashes.setdefault(h, []).append(i)
    for h, indexes in hashes.items():
        if len(indexes) < 2:
            continue
        names = {new[i].get("displayName","") for i in indexes}
        cats = {new[i].get("category","") for i in indexes}
        # If same image pretends to be different components, do not approve all.
        if len(names) > 1 or len(cats) > 1:
            for i in indexes:
                c = new[i]
                if c.get("status") == "approved" and any(w in norm(c.get("displayName","")) for w in ["heater", "fan", "valve", "sensor"]):
                    c["status"] = "needs_review"
                    c["retired"] = True
                c["duplicateImageHash"] = h
                c["needsArtworkReview"] = True
                c["notes"] = (str(c.get("notes") or "") + " | Same image is used by multiple different names; review before approval.").strip(" |")

    if not dry_run:
        backup = backup_library(root)
        export_data = state["export_data"]
        export_key = state["export_key"]
        manifest_data = state["manifest_data"]
        manifest_key = state["manifest_key"]
        save_json_file(root / EXPORT_JSON, inject_components(export_data, export_key, new))
        # Keep manifest in sync if it exists; otherwise create a light manifest.
        save_json_file(root / MANIFEST_JSON, inject_components(manifest_data, manifest_key, new))
    else:
        backup = None

    reports_dir = root / LIBRARY_DIR / "cleanup_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    csv_path = reports_dir / f"component_library_first_pass_{stamp}.csv"
    if report:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(report[0].keys()))
            writer.writeheader()
            writer.writerows(report)
    else:
        csv_path.write_text("No changes detected.\n", encoding="utf-8")
    return {"dryRun": dry_run, "componentCount": len(new), "changeCount": len(report), "reportCsv": str(csv_path), "backup": str(backup) if backup else ""}

def save_components(root: pathlib.Path, components: List[Dict[str, Any]]):
    state = load_library(root)
    backup = backup_library(root)
    save_json_file(root / EXPORT_JSON, inject_components(state["export_data"], state["export_key"], components))
    save_json_file(root / MANIFEST_JSON, inject_components(state["manifest_data"], state["manifest_key"], components))
    return {"saved": True, "count": len(components), "backup": str(backup)}

def missing_required(root: pathlib.Path, components: List[Dict[str, Any]], required: List[Dict[str, Any]]):
    hay = []
    for c in components:
        if c.get("retired") and c.get("status") != "approved":
            continue
        hay.append(squash(component_text(c)))
    missing = []
    for req in required:
        keys = [req.get("partNumber",""), req.get("displayName","")] + req.get("aliases", [])
        if not any(any(squash(k) and squash(k) in h for h in hay) for k in keys):
            missing.append(req)
    return missing

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    root = repo_root(args.root)
    result = apply_canonical_first_pass(root, dry_run=not args.apply)
    print(json.dumps(result, indent=2))
