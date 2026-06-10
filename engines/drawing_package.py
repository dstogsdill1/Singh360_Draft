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

        body = []
        body.append(self._overview_section(graph, nodes, groups, stamp))
        body.append(self._components_section(groups))
        body.append(self._connections_section(graph, id_to_label))
        body.append(self._buildlist_section(nodes))
        body.append(self._flags_section(graph))

        tabs = [
            ("overview", "Overview"),
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
  ul.list {{ margin:0; padding-left:18px; }}
  ul.list li {{ margin:3px 0; }}
  .toast {{ position:fixed; bottom:20px; left:50%; transform:translateX(-50%);
            background:var(--navy); color:#fff; padding:10px 18px; border-radius:8px;
            font-size:13px; opacity:0; transition:opacity .2s; pointer-events:none; }}
  .toast.show {{ opacity:1; }}
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
</script>
</body>
</html>
"""
