"""engines/drawing_package.py — copy-paste-ready project drawing package (HTML).

A different output philosophy from the .vson/.vsdx engines: instead of trying to
emit a finished, exact diagram file, this produces a single self-contained HTML
**drawing package** that grips *every* component of a project together in clean,
copy-paste-ready tables. The operator opens it, copies any schedule/table (TSV
to clipboard or a downloaded CSV), and builds the drawing by hand in SmartDraw or
Microsoft Visio with all the data already organized and named.

What it consolidates from the DiagramGraph (the fused project model):

  * Overview      — project, generated stamp, component counts by category/group.
  * Components    — one copyable table per group (Refrigeration, EMS Control,
                    Lighting, Network, …) with every node + its attributes.
  * Connections   — the full relationship list (hierarchy / control / network).
  * Build list    — a flat, printable bill of materials with tick boxes.
  * Flags/Sources — validation flags + source provenance (traceability).

Deterministic + no hallucination: it only renders what the graph already holds.
Blank cells stay blank. Every row carries its `source` provenance. Each table is
both a real HTML `<table>` (drag-select straight into Visio/Excel) and wired to
"Copy (TSV)" / "Download CSV" buttons for friction-free paste.
"""
from __future__ import annotations

import datetime
import html
import re
from pathlib import Path

from engines import svg_diagram

# Attribute columns shown first (when present); the rest follow alphabetically.
_PREFERRED_ATTR_ORDER = [
    "fixture", "make", "control_type", "control", "panel", "voltage",
    "set_point_f", "area", "connected_raw", "ip", "switch", "port", "vlan",
    "sub_form", "issue_desc", "issue_reco", "issue_assign", "spatial_source",
]

# Friendly column headers for known attribute keys.
_ATTR_LABELS = {
    "fixture": "Fixture / Rack / Make",
    "make": "Make",
    "control_type": "Control Type",
    "control": "Control Schedule",
    "panel": "Panel / Circuit",
    "voltage": "Voltage",
    "set_point_f": "Set Point (F)",
    "area": "Area / Served",
    "connected_raw": "Connected (raw)",
    "ip": "IP",
    "switch": "Switch",
    "port": "Port",
    "vlan": "VLAN",
    "sub_form": "Description",
    "issue_desc": "Scope / Issue",
    "issue_reco": "Recommendation",
    "issue_assign": "Assigned To",
    "spatial_source": "Spatial Source",
}

_EDGE_KIND_LABEL = {
    "hierarchy": "Serves / parent",
    "control": "Control",
    "network": "Network",
}


def _thumb(label: str, inner: str) -> str:
    return (
        "<figure class='sym'>"
        "<svg viewBox='0 0 160 110' width='160' height='110'>"
        "<rect x='0' y='0' width='160' height='110' rx='8' fill='#fff' stroke='#d7dee6'/>"
        f"{inner}</svg>"
        f"<figcaption>{html.escape(label)}</figcaption></figure>"
    )


# Clean, self-contained illustrations of the core lighting-control symbols so the
# operator SEES what they are importing (same family as the EMS library SVGs).
_SYMBOL_THUMBS = "".join([
    _thumb("Lighting Contactor", (
        "<rect x='20' y='26' width='52' height='58' fill='#fff' stroke='#5A4100' stroke-width='1.5'/>"
        "<rect x='20' y='26' width='52' height='14' fill='#BF8700'/>"
        "<text x='46' y='36' text-anchor='middle' font-size='8' fill='#fff'>CONTACTOR</text>"
        "<text x='46' y='66' text-anchor='middle' font-size='14' fill='#5A4100' font-weight='700'>C1</text>"
        "<line x1='72' y1='55' x2='84' y2='55' stroke='#BF8700' stroke-width='2'/>"
        "<circle cx='90' cy='62' r='5' fill='none' stroke='#BF8700' stroke-width='2'/>"
        "<line x1='95' y1='62' x2='138' y2='62' stroke='#BF8700' stroke-width='2'/>"
        "<rect x='112' y='44' width='30' height='20' fill='#fff' stroke='#5A4100'/>"
        "<text x='127' y='57' text-anchor='middle' font-size='7' fill='#42505e'>load</text>")),
    _thumb("Lighting Control Panel", (
        "<rect x='30' y='14' width='100' height='86' rx='3' fill='#fff' stroke='#0B3D91' stroke-width='1.5'/>"
        "<rect x='30' y='14' width='100' height='16' fill='#1F6FEB'/>"
        "<text x='80' y='26' text-anchor='middle' font-size='8' fill='#fff'>LCP-1</text>"
        + "".join(f"<rect x='{38+i*15}' y='40' width='11' height='20' fill='#eef2f7' stroke='#0B3D91'/>" for i in range(6))
        + "<text x='80' y='80' text-anchor='middle' font-size='7' fill='#42505e'>contactor bank</text>")),
    _thumb("Light Fixture", (
        "<rect x='44' y='40' width='72' height='22' rx='3' fill='#fff' stroke='#7A5C00' stroke-width='1.5'/>"
        "<text x='80' y='55' text-anchor='middle' font-size='12' fill='#7A5C00' font-weight='700'>C1</text>"
        "<path d='M80 62 v14 M66 80 h28 M70 86 h20 M74 92 h12' stroke='#E3B341' stroke-width='2' fill='none'/>"
        "<text x='80' y='30' text-anchor='middle' font-size='7' fill='#42505e'>fixture type</text>")),
    _thumb("Network Switch", (
        "<rect x='20' y='44' width='120' height='26' rx='4' fill='#1F2937'/>"
        "<text x='28' y='60' font-size='8' fill='#fff'>SWITCH</text>"
        + "".join(f"<rect x='{86+i*7}' y='52' width='5' height='10' fill='#7fb0d4'/>" for i in range(7))
        + "<line x1='40' y1='70' x2='40' y2='86' stroke='#1F6FEB' stroke-width='2'/>"
        "<line x1='60' y1='70' x2='60' y2='86' stroke='#2EA043' stroke-width='2'/>"
        "<text x='80' y='98' text-anchor='middle' font-size='7' fill='#42505e'>ties controllers to the network</text>")),
    _thumb("Output Relay", (
        "<rect x='24' y='24' width='40' height='62' fill='#fff' stroke='#7A5C00' stroke-width='1.5'/>"
        "<rect x='24' y='24' width='40' height='13' fill='#D29922'/>"
        "<text x='44' y='34' text-anchor='middle' font-size='7' fill='#1a1a1a'>RELAY</text>"
        "<text x='44' y='66' text-anchor='middle' font-size='12' fill='#7A5C00' font-weight='700'>R1</text>"
        "<line x1='64' y1='55' x2='130' y2='55' stroke='#D29922' stroke-width='2'/>"
        "<circle cx='120' cy='55' r='4' fill='#D29922'/>"
        "<text x='96' y='48' text-anchor='middle' font-size='7' fill='#42505e'>switches a load</text>")),
    _thumb("RDM Data Manager", (
        "<rect x='30' y='26' width='100' height='58' rx='3' fill='#fff' stroke='#3A1D6E' stroke-width='1.5'/>"
        "<rect x='30' y='26' width='100' height='15' fill='#8957E5'/>"
        "<text x='80' y='37' text-anchor='middle' font-size='7' fill='#fff'>RDM DATA MANAGER</text>"
        "<circle cx='48' cy='56' r='5' fill='#8957E5'/>"
        "<text x='80' y='60' text-anchor='middle' font-size='7' fill='#42505e'>site brain</text>"
        "<text x='80' y='74' text-anchor='middle' font-size='7' fill='#42505e'>talks to every controller</text>")),
])



def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "x"


def _e(text: object) -> str:
    """HTML-escape a cell value (None/blank -> '')."""
    return html.escape("" if text is None else str(text))


class DrawingPackageGenerator:
    """Render a DiagramGraph into a single copy-paste-ready HTML package."""

    def __init__(self, project_name: str = "", subtitle: str = "") -> None:
        self.project_name = project_name
        self.subtitle = subtitle or "Project Drawing Package"

    # -- public ----------------------------------------------------------
    def render(self, graph, out_path: str | Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        title = self.project_name or getattr(graph, "name", "Singh360 Project")
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        nodes = list(graph.nodes.values())
        id_to_label = {n.id: n.label for n in nodes}
        groups = self._grouped(nodes)
        source_summary = self._source_summary(graph, nodes)

        body = []
        body.append(self._drawing_section(graph, title))
        body.append(self._start_here_section(title, source_summary))
        body.append(self._overview_section(graph, nodes, groups, stamp))
        body.append(self._source_map_section(source_summary))
        body.append(self._components_section(groups))
        body.append(self._connections_section(graph, id_to_label))
        body.append(self._buildlist_section(nodes))
        body.append(self._flags_section(graph))

        tabs = [
            ("drawing", "⭐ The Drawing"),
            ("start", "Start Here"),
            ("overview", "Overview"),
            ("source", "How It Was Derived"),
            ("components", "Components"),
            ("connections", "Connections"),
            ("buildlist", "Build List"),
            ("flags", "Flags & Sources"),
        ]
        html_doc = _PAGE.format(
            title=_e(title),
            subtitle=_e(self.subtitle),
            stamp=_e(stamp),
            tabbar="".join(
                f'<button class="tab{" active" if i == 0 else ""}" '
                f'data-tab="{tid}" onclick="showTab(\'{tid}\')">{_e(label)}</button>'
                for i, (tid, label) in enumerate(tabs)
            ),
            sections="\n".join(body),
        )
        out_path.write_text(html_doc, encoding="utf-8")
        return out_path

    # -- sections --------------------------------------------------------
    def _grouped(self, nodes) -> dict:
        out: dict[str, list] = {}
        for n in nodes:
            out.setdefault(n.group or n.category or "Ungrouped", []).append(n)
        # Deterministic group order, nodes sorted by label within each group.
        for g in out.values():
            g.sort(key=lambda n: (n.category, str(n.label)))
        return dict(sorted(out.items(), key=lambda kv: kv[0].lower()))

    def _attr_columns(self, group_nodes) -> list[str]:
        present = set()
        for n in group_nodes:
            for k, v in n.attrs.items():
                if str(v).strip():
                    present.add(k)
        ordered = [k for k in _PREFERRED_ATTR_ORDER if k in present]
        ordered += sorted(k for k in present if k not in _PREFERRED_ATTR_ORDER)
        return ordered

    def _source_summary(self, graph, nodes) -> dict:
        """Summarize the source files behind the graph for the guide tabs."""
        node_counts: dict[str, int] = {}
        edge_counts: dict[str, int] = {}
        for n in nodes:
            src = (n.source or "").split(":", 1)[0] or "(unknown)"
            node_counts[src] = node_counts.get(src, 0) + 1
        for ed in graph.edges:
            src = (ed.source_ref or "").split(":", 1)[0] or "(unknown)"
            edge_counts[src] = edge_counts.get(src, 0) + 1
        return {"nodes": node_counts, "edges": edge_counts}

    def _drawing_section(self, graph, title) -> str:
        """The actual rendered picture, embedded inline + downloadable."""
        try:
            svg = svg_diagram.build_svg(graph, title=title, subtitle=self.subtitle, embed=True)
        except Exception as exc:  # never let a render error kill the package
            svg = (
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 600 120' width='600' "
                "height='120'><rect width='600' height='120' fill='#fff' stroke='#d7dee6'/>"
                f"<text x='20' y='60' font-size='13' fill='#b00'>Drawing render failed: {_e(exc)}</text></svg>"
            )
        return (
            "<section id='drawing' class='tabpane active'>"
            "<div class='cardhead' style='margin-bottom:10px'>"
            "<h3 style='font-size:16px'>This is your drawing — the actual picture, built from your data</h3>"
            "<div class='btns'>"
            "<button class='btn' onclick='downloadDrawingSvg()'>Download drawing (SVG)</button>"
            "<button class='btn ghost' onclick='printDrawingLandscape()'>Print drawing (Landscape PDF)</button>"
            "<button class='btn ghost' onclick='window.print()'>Print full package</button>"
            "</div></div>"
            "<p class='muted' style='margin:0 0 12px'>This is a real, finished diagram — not a table. "
            "Open it, print it, or drop the downloaded <b>.svg</b> straight onto a SmartDraw / Visio "
            "canvas as your starting drawing. Every box is a component from your schedule; every line "
            "is a real relationship (control = gold dashed, network = blue dotted, serves = grey).</p>"
            f"<div id='drawingWrap' style='overflow:auto; border:1px solid #d7dee6; border-radius:10px; "
            f"background:#fff; padding:8px'>{svg}</div>"
            "<div class='card' style='margin-top:12px'><h3>Final deliverable workflow (match your 109 process)</h3>"
            "<ol class='steps'>"
            "<li>Use <b>Download drawing (SVG)</b> and insert that SVG into SmartDraw on a blank sheet.</li>"
            "<li>Set page orientation to <b>Landscape</b> in SmartDraw, then resize/fit the drawing to page.</li>"
            "<li>Make any final manual edits/notes to match your issued layout style.</li>"
            "<li>Export from SmartDraw as <b>PDF</b> (this is your final issued product).</li>"
            "</ol>"
            "<p class='muted'>If you just need a quick one-page draft PDF directly from this package, click "
            "<b>Print drawing (Landscape PDF)</b>.</p></div>"
            "</section>"
        )

    def _start_here_section(self, title, source_summary) -> str:
        input_files = ", ".join(sorted(k for k in source_summary["nodes"].keys() if k != "(unknown)"))
        return (
            "<section id='start' class='tabpane'>"
            # --- three honest ways to use this ---
            "<div class='card'><h3>Three ways to use this document</h3>"
            "<div class='grid2'>"
            "<div class='waybox'><div class='waynum'>1</div><b>Just want the picture?</b>"
            "<p class='muted'>Open the <b>\u2b50 The Drawing</b> tab. Click <b>Download drawing (SVG)</b> "
            "and drag that file onto a blank SmartDraw or Visio canvas \u2014 the whole layout drops in "
            "as editable shapes. For a one-click draft, use <b>Print drawing (Landscape PDF)</b>.</p></div>"
            "<div class='waybox'><div class='waynum'>2</div><b>Want to build it with library symbols?</b>"
            "<p class='muted'>Follow the <b>Get the symbols into SmartDraw</b> steps below, then place "
            "each symbol on your floor plan using the <b>Components</b> tab as the checklist.</p></div>"
            "<div class='waybox'><div class='waynum'>3</div><b>Just want the raw data?</b>"
            "<p class='muted'>Use the <b>Components</b> and <b>Build List</b> tabs. <b>Copy (TSV)</b> "
            "or <b>Download CSV</b> pastes the shape data into SmartDraw / Visio / Excel.</p></div>"
            "</div></div>"
            # --- honest note about TSV ---
            "<div class='card' style='border-left:4px solid var(--blue)'>"
            "<h3>Why \u201cCopy (TSV)\u201d only pastes text (and how to get the pictures)</h3>"
            "<p class='lead'>TSV is <b>data</b> \u2014 the names, panels, and settings that fill in a shape\u2019s "
            "fields. It is not an image, so pasting it gives you text, not symbols. That is expected.</p>"
            "<p class='muted'>To get <b>pictures</b> you have two options: (a) the <b>\u2b50 The Drawing</b> tab "
            "downloads the finished diagram as an image, or (b) import the EMS symbol library once (steps "
            "below) so the symbols live in your SmartDraw sidebar, then you place them and paste the TSV "
            "data onto them.</p></div>"
            # --- the working SmartDraw method (canvas staging) ---
            "<div class='card'><h3>Get the symbols into SmartDraw (the method that actually works)</h3>"
            "<p class='muted'>SmartDraw has <b>no bulk \u201cupload a library\u201d button</b>. The Symbol "
            "Libraries popup only makes an <i>empty</i> library. You fill it by staging each symbol on the "
            "canvas, then dragging it into the library. Do this once.</p>"
            "<ol class='steps'>"
            "<li>Open the <b>EMS component library</b> page and click <b>Export for SmartDraw / Visio</b> "
            "to download the <code>Singh360_*.svg</code> symbol files.</li>"
            "<li>In SmartDraw, close the Symbol Libraries popup and go to your blank drawing.</li>"
            "<li>Make sure your <b>Singh360 EMS Hardware</b> library is showing in the left sidebar "
            "(use the search box or <b>More</b> to pin it).</li>"
            "<li><b>Insert \u2192 Picture</b> (or drag an <code>.svg</code> from your folder) to drop one "
            "symbol onto the white canvas.</li>"
            "<li>Drag that symbol from the canvas <b>into the Singh360 EMS Hardware panel</b> on the left. "
            "Name it when prompted (e.g. \u201cLighting Contactor\u201d).</li>"
            "<li>Press <b>Delete</b> to remove the staging copy from the canvas. The symbol now lives in "
            "your library permanently.</li>"
            "<li>Repeat for the rest. Then drag your library symbols onto the floor plan to build the "
            "drawing, using the <b>Components</b> tab as the placement checklist.</li>"
            "</ol></div>"
            # --- what the symbols look like (inline pictures) ---
            "<div class='card'><h3>What the symbols look like</h3>"
            "<p class='muted'>These are the EMS library symbols you are importing \u2014 the same artwork "
            "exported as SVG:</p>"
            f"<div class='symgrid'>{_SYMBOL_THUMBS}</div></div>"
            # --- what this package is ---
            "<div class='card'><h3>What this package is</h3>"
            f"<p class='lead'>This HTML is the complete drawing document for <b>{_e(title)}</b>: the "
            "rendered picture, the component checklist, the connections, and the build list \u2014 all in "
            "one file.</p>"
            "<p class='muted'><b>Final product expectation:</b> the issued deliverable is the PDF you "
            "export from SmartDraw after final manual layout/annotation. This package is your source kit.</p>"
            f"<p class='muted'><b>Source data behind it:</b> {_e(input_files or 'none recorded')}</p>"
            "</div>"
            "</section>"
        )

    def _source_map_section(self, source_summary) -> str:
        src_rows = []
        for src, count in sorted(source_summary["nodes"].items(), key=lambda kv: (-kv[1], kv[0])):
            edge_count = source_summary["edges"].get(src, 0)
            src_rows.append(
                f"<tr><td>{_e(src)}</td><td class='num'>{count}</td><td class='num'>{edge_count}</td><td>feeds the component tables / connections tab</td></tr>"
            )
        if not src_rows:
            src_rows.append("<tr><td colspan='4' class='muted'>No source files recorded.</td></tr>")

        derivation_rows = []
        for src in sorted(source_summary["nodes"].keys()):
            if src == "(unknown)":
                continue
            derivation_rows.append(
                f"<tr><td>{_e(src)}</td><td>{_e(self._source_description(src))}</td></tr>"
            )

        return (
            "<section id='source' class='tabpane'>"
            "<div class='grid2'>"
            "<div class='card'><h3>How this was derived</h3>"
            "<table class='data'><thead><tr><th>Source file</th><th>Nodes</th><th>Edges</th><th>What it feeds</th></tr></thead>"
            f"<tbody>{''.join(src_rows)}</tbody></table>"
            "</div>"
            "<div class='card'><h3>Plain-English derivation</h3>"
            "<table class='data'><thead><tr><th>File</th><th>Meaning</th></tr></thead>"
            f"<tbody>{''.join(derivation_rows) if derivation_rows else '<tr><td colspan=\"2\" class=\"muted\">No derivation notes.</td></tr>'}</tbody></table>"
            "</div>"
            "</div>"
            "<div class='card'><h3>Build order</h3>"
            "<ol class='steps'>"
            "<li><b>assets.csv</b> gives you the base components (panel, controller, sensors, zones).</li>"
            "<li><b>control_matrix.csv</b> gives you the control chain (relay → contactor → load).</li>"
            "<li><b>network.csv</b> gives you the comms path (device → switch → port).</li>"
            "<li>The package HTML turns those rows into copyable tables and a checklist.</li>"
            "</ol>"
            "</div>"
            "</section>"
        )

    def _source_description(self, src: str) -> str:
        src_low = (src or "").lower()
        if "assets" in src_low:
            return "Base schedule rows: panels, controllers, zones, and component names."
        if "control" in src_low:
            return "Relay / contactor / load rows: the control chain for lighting and loads."
        if "network" in src_low:
            return "Network rows: device, switch, and port assignments."
        return "Project data source used to populate the package tables."

    def _overview_section(self, graph, nodes, groups, stamp) -> str:
        by_cat: dict[str, int] = {}
        for n in nodes:
            by_cat[n.category or "—"] = by_cat.get(n.category or "—", 0) + 1
        edge_kinds: dict[str, int] = {}
        for ed in graph.edges:
            edge_kinds[ed.kind] = edge_kinds.get(ed.kind, 0) + 1

        cat_rows = "".join(
            f"<tr><td>{_e(c)}</td><td class='num'>{n}</td></tr>"
            for c, n in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        grp_rows = "".join(
            f"<tr><td>{_e(g)}</td><td class='num'>{len(ns)}</td></tr>"
            for g, ns in groups.items()
        )
        edge_rows = "".join(
            f"<tr><td>{_e(_EDGE_KIND_LABEL.get(k, k))}</td><td class='num'>{v}</td></tr>"
            for k, v in sorted(edge_kinds.items())
        ) or "<tr><td colspan='2' class='muted'>No connections recorded.</td></tr>"

        cards = (
            f"<div class='stat'><div class='big'>{len(nodes)}</div><div>Components</div></div>"
            f"<div class='stat'><div class='big'>{len(graph.edges)}</div><div>Connections</div></div>"
            f"<div class='stat'><div class='big'>{len(groups)}</div><div>Groups</div></div>"
            f"<div class='stat'><div class='big'>{len(getattr(graph, 'flags', []))}</div><div>Flags</div></div>"
        )
        return (
            "<section id='overview' class='tabpane active'>"
            "<div class='statrow'>" + cards + "</div>"
            "<p class='lead'>This package consolidates every component for the "
            "project so you can copy any table straight into <b>SmartDraw</b> or "
            "<b>Microsoft Visio</b> and assemble the drawing yourself. Use "
            "<b>Copy (TSV)</b> to paste into a sheet, or <b>Download CSV</b> for "
            "data-import / shape-data linking.</p>"
            "<div class='grid2'>"
            "<div class='card'><h3>Components by category</h3>"
            "<table class='data'><thead><tr><th>Category</th><th>Count</th></tr></thead>"
            f"<tbody>{cat_rows}</tbody></table></div>"
            "<div class='card'><h3>Components by group</h3>"
            "<table class='data'><thead><tr><th>Group</th><th>Count</th></tr></thead>"
            f"<tbody>{grp_rows}</tbody></table></div>"
            "<div class='card'><h3>Connections by type</h3>"
            "<table class='data'><thead><tr><th>Type</th><th>Count</th></tr></thead>"
            f"<tbody>{edge_rows}</tbody></table></div>"
            f"<div class='card'><h3>Generated</h3><p class='muted'>{_e(stamp)}</p>"
            "<p class='muted'>Singh360_SmartDraw drawing package. Deterministic — "
            "values come only from the source schedules; blank means not provided.</p>"
            "</div>"
            "</div>"
            "</section>"
        )

    def _components_section(self, groups) -> str:
        if not groups:
            return ("<section id='components' class='tabpane'>"
                    "<p class='muted'>No components.</p></section>")
        cards = []
        for gname, gnodes in groups.items():
            attr_cols = self._attr_columns(gnodes)
            tid = "tbl-" + _slug(gname)
            head = ["Name", "Type", "Category"] + [
                _ATTR_LABELS.get(c, c.replace("_", " ").title()) for c in attr_cols
            ] + ["Source"]
            thead = "".join(f"<th>{_e(h)}</th>" for h in head)
            rows = []
            for n in gnodes:
                cells = [n.label, n.unit_type, n.category]
                cells += [n.attrs.get(c, "") for c in attr_cols]
                cells.append(n.source)
                rows.append("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in cells) + "</tr>")
            cards.append(
                f"<div class='card'><div class='cardhead'>"
                f"<h3>{_e(gname)} <span class='pill'>{len(gnodes)}</span></h3>"
                f"<div class='btns'>"
                f"<button class='btn' onclick=\"copyTable('{tid}')\">Copy (TSV)</button>"
                f"<button class='btn ghost' onclick=\"downloadCsv('{tid}','{_slug(gname)}.csv')\">Download CSV</button>"
                f"</div></div>"
                f"<div class='scroll'><table id='{tid}' class='data grip'>"
                f"<thead><tr>{thead}</tr></thead><tbody>{''.join(rows)}</tbody>"
                f"</table></div></div>"
            )
        return "<section id='components' class='tabpane'>" + "".join(cards) + "</section>"

    def _connections_section(self, graph, id_to_label) -> str:
        if not graph.edges:
            return ("<section id='connections' class='tabpane'>"
                    "<p class='muted'>No connections recorded.</p></section>")
        rows = []
        for ed in graph.edges:
            rows.append(
                "<tr>"
                f"<td>{_e(id_to_label.get(ed.source, ed.source))}</td>"
                f"<td>{_e(id_to_label.get(ed.target, ed.target))}</td>"
                f"<td>{_e(_EDGE_KIND_LABEL.get(ed.kind, ed.kind))}</td>"
                f"<td>{_e(ed.label)}</td>"
                f"<td>{_e(ed.source_ref)}</td>"
                "</tr>"
            )
        return (
            "<section id='connections' class='tabpane'>"
            "<div class='card'><div class='cardhead'>"
            "<h3>All connections <span class='pill'>" + str(len(graph.edges)) + "</span></h3>"
            "<div class='btns'>"
            "<button class='btn' onclick=\"copyTable('tbl-conn')\">Copy (TSV)</button>"
            "<button class='btn ghost' onclick=\"downloadCsv('tbl-conn','connections.csv')\">Download CSV</button>"
            "</div></div>"
            "<div class='scroll'><table id='tbl-conn' class='data grip'><thead><tr>"
            "<th>From</th><th>To</th><th>Type</th><th>Relationship</th><th>Source</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>"
            "</section>"
        )

    def _buildlist_section(self, nodes) -> str:
        ordered = sorted(nodes, key=lambda n: (n.category, str(n.label)))
        rows = []
        for n in ordered:
            where = n.attrs.get("area") or n.attrs.get("panel") or n.attrs.get("connected_raw") or ""
            rows.append(
                "<tr>"
                "<td data-noexport><input type='checkbox'></td>"
                f"<td>{_e(n.category)}</td>"
                f"<td>{_e(n.label)}</td>"
                f"<td>{_e(n.unit_type)}</td>"
                f"<td>{_e(where)}</td>"
                "</tr>"
            )
        return (
            "<section id='buildlist' class='tabpane'>"
            "<div class='card'><div class='cardhead'>"
            "<h3>Build checklist <span class='pill'>" + str(len(ordered)) + "</span></h3>"
            "<div class='btns'>"
            "<button class='btn' onclick=\"copyTable('tbl-build')\">Copy (TSV)</button>"
            "<button class='btn ghost' onclick=\"downloadCsv('tbl-build','build_list.csv')\">Download CSV</button>"
            "<button class='btn ghost' onclick=\"window.print()\">Print</button>"
            "</div></div>"
            "<p class='muted'>Every component in one flat list — tick each off as "
            "you place it on the sheet.</p>"
            "<div class='scroll'><table id='tbl-build' class='data grip'><thead><tr>"
            "<th data-noexport>Done</th><th>Category</th><th>Component</th>"
            "<th>Type</th><th>Location / Served</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>"
            "</section>"
        )

    def _flags_section(self, graph) -> str:
        flags = list(getattr(graph, "flags", []))
        sources = sorted({n.source.split(":")[0] for n in graph.nodes.values() if n.source})
        flag_items = "".join(f"<li>{_e(f)}</li>" for f in flags) or \
            "<li class='muted'>No flags — clean run.</li>"
        src_items = "".join(f"<li>{_e(s)}</li>" for s in sources) or \
            "<li class='muted'>No sources recorded.</li>"
        return (
            "<section id='flags' class='tabpane'>"
            "<div class='grid2'>"
            "<div class='card'><h3>Flags</h3><ul class='list'>" + flag_items + "</ul></div>"
            "<div class='card'><h3>Source files (traceability)</h3>"
            "<ul class='list'>" + src_items + "</ul></div>"
            "</div></section>"
        )


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate(path: str | Path) -> tuple[bool, list[str]]:
    """Confirm the package is a non-empty HTML doc with the expected structure."""
    path = Path(path)
    problems: list[str] = []
    if not path.exists():
        return False, [f"{path.name} was not written"]
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) < 200:
        problems.append("package HTML is suspiciously small")
    for marker in ("<html", "Drawing Package", "id='overview'", "copyTable"):
        if marker not in text:
            problems.append(f"missing expected marker: {marker}")
    return (not problems), problems


# --------------------------------------------------------------------------
# Page template (self-contained: inline CSS + JS, no external assets)
# --------------------------------------------------------------------------
_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Drawing Package</title>
<style>
  :root {{ --navy:#0b3d63; --blue:#0e8fd0; --ink:#1a2733; --line:#d7dee6;
           --bg:#eef2f7; --card:#ffffff; --muted:#6b7a8c; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:14px/1.45 -apple-system,Segoe UI,Roboto,Arial,sans-serif;
          color:var(--ink); background:var(--bg); }}
  header {{ background:linear-gradient(135deg,var(--navy),#0a2c47); color:#fff;
            padding:18px 22px; }}
  header h1 {{ margin:0; font-size:20px; letter-spacing:.2px; }}
  header .sub {{ opacity:.85; font-size:13px; margin-top:3px; }}
  header .stamp {{ opacity:.7; font-size:12px; margin-top:2px; }}
  .tabs {{ display:flex; gap:4px; background:var(--navy); padding:0 14px;
           position:sticky; top:0; z-index:5; flex-wrap:wrap; }}
  .tab {{ background:transparent; border:0; color:#cfe3f3; padding:11px 16px;
          font-size:13px; cursor:pointer; border-bottom:3px solid transparent; }}
  .tab:hover {{ color:#fff; }}
  .tab.active {{ color:#fff; border-bottom-color:var(--blue); font-weight:600; }}
  main {{ padding:18px 22px 60px; max-width:1280px; margin:0 auto; }}
  .tabpane {{ display:none; }}
  .tabpane.active {{ display:block; }}
  .lead {{ color:var(--ink); max-width:900px; }}
  .statrow {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
           padding:14px 18px; min-width:120px; text-align:center; }}
  .stat .big {{ font-size:26px; font-weight:700; color:var(--navy); }}
  .grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr));
            gap:14px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
           padding:14px 16px; margin-bottom:14px; }}
  .card h3 {{ margin:0 0 10px; font-size:15px; color:var(--navy); }}
  .cardhead {{ display:flex; justify-content:space-between; align-items:center;
               gap:10px; flex-wrap:wrap; }}
  .cardhead h3 {{ margin:0; }}
  .pill {{ background:var(--blue); color:#fff; border-radius:999px; font-size:12px;
           padding:1px 9px; margin-left:6px; vertical-align:middle; }}
  .btns {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .btn {{ background:var(--blue); color:#fff; border:0; border-radius:7px;
          padding:7px 12px; font-size:12.5px; cursor:pointer; }}
  .btn:hover {{ filter:brightness(1.06); }}
  .btn.ghost {{ background:#fff; color:var(--navy); border:1px solid var(--blue); }}
  .scroll {{ overflow:auto; max-height:62vh; border:1px solid var(--line);
             border-radius:8px; }}
  table.data {{ border-collapse:collapse; width:100%; font-size:13px; }}
  table.data th {{ position:sticky; top:0; background:var(--navy); color:#fff;
                   text-align:left; padding:8px 10px; font-weight:600;
                   white-space:nowrap; }}
  table.data td {{ padding:7px 10px; border-bottom:1px solid var(--line);
                   vertical-align:top; }}
  table.data tbody tr:nth-child(even) {{ background:#f6f9fc; }}
  table.data td.num, table.data th:last-child {{ }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .muted {{ color:var(--muted); }}
    .steps {{ margin:0; padding-left:18px; }}
    .steps li {{ margin:6px 0; }}
  ul.list {{ margin:0; padding-left:18px; }}
  ul.list li {{ margin:3px 0; }}
  .toast {{ position:fixed; bottom:20px; left:50%; transform:translateX(-50%);
            background:var(--navy); color:#fff; padding:10px 18px; border-radius:8px;
            font-size:13px; opacity:0; transition:opacity .2s; pointer-events:none; }}
  .toast.show {{ opacity:1; }}  .waybox {{ background:#f6f9fc; border:1px solid var(--line); border-radius:10px;
             padding:12px 14px; position:relative; }}
  .waynum {{ width:26px; height:26px; border-radius:50%; background:var(--blue); color:#fff;
             font-weight:700; display:flex; align-items:center; justify-content:center;
             margin-bottom:6px; }}
  code {{ background:#eef2f7; border:1px solid var(--line); border-radius:4px;
          padding:1px 5px; font-size:12px; }}
  .symgrid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
              gap:12px; }}
  figure.sym {{ margin:0; text-align:center; }}
    figure.sym figcaption {{ font-size:12px; color:var(--navy); font-weight:600; margin-top:4px; }}
    @page {{ size: landscape; margin: 0.35in; }}
    @media print {{ .tabs,.btns,header .stamp {{ display:none; }}
                  .tabpane {{ display:block !important; }} .scroll {{ max-height:none; }} }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="stamp">Generated {stamp} · Singh360_SmartDraw</div>
</header>
<nav class="tabs">{tabbar}</nav>
<main>
{sections}
</main>
<div class="toast" id="toast"></div>
<script>
  function showTab(id) {{
    document.querySelectorAll('.tabpane').forEach(function(p){{ p.classList.remove('active'); }});
    document.querySelectorAll('.tab').forEach(function(t){{ t.classList.remove('active'); }});
    var pane = document.getElementById(id); if (pane) pane.classList.add('active');
    var btn = document.querySelector('.tab[data-tab="'+id+'"]'); if (btn) btn.classList.add('active');
  }}
  function tableMatrix(id) {{
    var t = document.getElementById(id); if (!t) return [];
    function cols(tr) {{
      var out = [];
      tr.querySelectorAll('th,td').forEach(function(c){{
        if (c.hasAttribute('data-noexport')) return;
        out.push((c.innerText||'').replace(/\\t/g,' ').replace(/\\r?\\n/g,' ').trim());
      }});
      return out;
    }}
    var rows = [];
    var head = t.querySelector('thead tr'); if (head) rows.push(cols(head));
    t.querySelectorAll('tbody tr').forEach(function(tr){{ rows.push(cols(tr)); }});
    return rows;
  }}
  function toast(msg) {{
    var el = document.getElementById('toast'); el.textContent = msg; el.classList.add('show');
    setTimeout(function(){{ el.classList.remove('show'); }}, 1400);
  }}
  function copyTable(id) {{
    var tsv = tableMatrix(id).map(function(r){{ return r.join('\\t'); }}).join('\\n');
    navigator.clipboard.writeText(tsv).then(function(){{ toast('Copied — paste into SmartDraw / Visio / Excel'); }},
      function(){{ toast('Copy failed — select the table manually'); }});
  }}
  function downloadCsv(id, filename) {{
    var csv = tableMatrix(id).map(function(r){{
      return r.map(function(c){{
        return /[",\\n]/.test(c) ? '"' + c.replace(/"/g,'""') + '"' : c;
      }}).join(',');
    }}).join('\\r\\n');
    var blob = new Blob([csv], {{type:'text/csv;charset=utf-8'}});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = filename; a.click();
    setTimeout(function(){{ URL.revokeObjectURL(a.href); }}, 1500);
    toast('Downloaded ' + filename);
  }}
  function downloadDrawingSvg() {{
    var wrap = document.getElementById('drawingWrap');
    var svg = wrap ? wrap.querySelector('svg') : null;
    if (!svg) {{ toast('No drawing to download'); return; }}
    var src = '<?xml version="1.0" encoding="UTF-8"?>\\n' + svg.outerHTML;
    var blob = new Blob([src], {{type:'image/svg+xml;charset=utf-8'}});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'drawing.svg'; a.click();
    setTimeout(function(){{ URL.revokeObjectURL(a.href); }}, 1500);
    toast('Downloaded drawing.svg — drop it onto a SmartDraw / Visio canvas');
  }}
    function printDrawingLandscape() {{
        var wrap = document.getElementById('drawingWrap');
        var svg = wrap ? wrap.querySelector('svg') : null;
        if (!svg) {{ toast('No drawing to print'); return; }}
        var w = window.open('', '_blank');
        if (!w) {{ toast('Popup blocked — allow popups to print'); return; }}
        var doc = [
            '<!doctype html><html><head><meta charset="utf-8"><title>Drawing PDF</title>',
            '<style>@page{{size:landscape;margin:0.25in;}}html,body{{margin:0;background:#fff;}}',
            'body{{display:flex;align-items:flex-start;justify-content:center;padding:0.1in;}}',
            'svg{{width:100%;height:auto;max-height:95vh;}}</style></head><body>',
            svg.outerHTML,
            '<script>window.onload=function(){{window.print();}};<\\/script></body></html>'
        ].join('');
        w.document.open();
        w.document.write(doc);
        w.document.close();
    }}
</script>
</body>
</html>
"""
