"""extractors/emerson_dump.py — Emerson E2/CPC controller dump.xml + export.zip.

The richest source. dump.xml is the live controller database:
  <dump><controller nw="7" slv="10"><param name="S01 Span 1" value="500.0"
  units="psi"/> ... <pack num="1">... <cond num="1">... <case>...</controller>

We import lazily and accept either a dump.xml file or a *_dump.zip / *_export.zip
(we read the .xml or per-controller .csv members without extracting to disk).
Findings become BOARD nodes (one per controller) carrying their params as
attrs, plus RACK/pack hints where present.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from core.model import ProjectModel, Node, NodeKind, slug


def _iter_dump_bytes(path: Path):
    """Yield (member_name, xml_bytes) for dump.xml, possibly inside a .zip."""
    if path.suffix.lower() == ".xml":
        yield path.name, path.read_bytes()
        return
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith("dump.xml"):
                    yield n, z.read(n)


def _iter_export_csvs(path: Path):
    """Yield (member_name, text) for each per-controller CSV in an export.zip."""
    if path.suffix.lower() != ".zip":
        return
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.lower().endswith(".csv"):
                try:
                    yield n, z.read(n).decode("utf-8", "replace")
                except KeyError:
                    continue


def extract(path: str | Path, model: ProjectModel) -> None:
    path = Path(path)
    model.note_source(str(path))
    name_up = path.name.upper()

    # --- export.zip: per-controller CSV value dumps -> DEVICE nodes ---
    if "EXPORT" in name_up and path.suffix.lower() == ".zip":
        controllers = 0
        for member, _text in _iter_export_csvs(path):
            ctrl = Path(member).stem
            nid = slug("ctrl", ctrl)
            model.add_node(Node(
                id=nid, kind=NodeKind.DEVICE, name=ctrl,
                attrs={"export": member}, source=f"{path.name}:{member}",
            ))
            controllers += 1
        model.flag("info", f"Emerson export: {controllers} controller value files indexed", path.name)
        return

    # --- dump.xml: controller database ---
    found_dump = False
    for member, data in _iter_dump_bytes(path):
        found_dump = True
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            model.flag("blocked", f"dump.xml parse failed in {member}: {exc}", path.name)
            continue
        _parse_dump_root(root, model, f"{path.name}:{member}")

    if not found_dump and path.suffix.lower() == ".zip":
        model.flag("review", f"{path.name}: no dump.xml member found in zip", path.name)


def _txt(el, tag: str) -> str:
    child = el.find(tag)
    if child is not None and child.text:
        return re.sub(r"\s+", " ", child.text).strip()
    return ""


def _parse_dump_root(root, model: ProjectModel, ref: str) -> None:
    controllers = list(root.iter("controller"))
    if not controllers:
        # Some dumps wrap controllers differently; only take elements that have
        # a network address (nw/slv) AND own params — avoids grabbing the deep
        # numeric sub-address nodes (e.g. "001-3-02") as phantom controllers.
        controllers = [
            el for el in root.iter()
            if el.find("param") is not None and (el.get("nw") or el.get("slv"))
        ]

    n_ctrl = 0
    n_param = 0
    for ci, ctrl in enumerate(controllers):
        nw = ctrl.get("nw", "")
        slv = ctrl.get("slv", "")
        addr = _txt(ctrl, "name") or _txt(ctrl, "index") or _txt(ctrl, "id") or f"Controller {ci + 1}"
        alias = _txt(ctrl, "alias")
        # The alias is the human label (e.g. "FTYPE_PCC", "Udev 1", "Section 3");
        # the name is a board:cell:point address (e.g. "001-3-02"). Prefer alias
        # for display, keep the address as an attribute for traceability.
        cname = alias or addr
        nid = slug("ctrl", addr, nw, slv) or slug("ctrl", str(ci))

        attrs: dict[str, str] = {"address": addr}
        if nw:
            attrs["nw"] = nw
        if slv:
            attrs["slv"] = slv
        ctype = _txt(ctrl, "type")
        if ctype:
            attrs["type_code"] = ctype

        # Collect params (including nested <params><param/>) as attributes.
        params = list(ctrl.iter("param"))
        for p in params[:80]:
            pn = p.get("name", "").strip()
            pv = p.get("value", "").strip()
            pu = p.get("units", "").strip()
            if pn and pv:
                attrs[pn] = (pv + (" " + pu if pu else "")).strip()
        n_param += len(params)

        # Classify by ADDRESS structure (the dump's <pack> is just a number, so
        # it is NOT a rack signal): a top-level address (no dash, e.g. "001") is
        # a controller BOARD; a sub-address ("001-3-02") is a point/sub-device.
        # Racks come from the schedule/worksheet, not from this dump.
        kind = NodeKind.BOARD if "-" not in addr else NodeKind.DEVICE
        if alias.upper().startswith("FTYPE_PCC"):
            kind = NodeKind.BOARD

        model.add_node(Node(
            id=nid, kind=kind, name=cname, attrs=attrs, source=ref,
        ))
        n_ctrl += 1

    model.flag("info", f"Emerson dump: {n_ctrl} controllers, {n_param} parameters parsed", ref)
