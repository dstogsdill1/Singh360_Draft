#!/usr/bin/env python3
"""make_contact_sheet.py -- human-review HTML contact sheet.

Builds a single self-contained HTML page that pairs each source image with its
generated black/white candidate(s), plus the proposed metadata and editable
approve/reject + notes fields. The form state is saved to the browser's
localStorage and can be exported back to a CSV that export_approved_symbols.py
understands (columns: id, decision, chosenVariant, notes).

Output:
    .docs/component_builder/work/contact_sheets/index.html

Usage:
    python tools/component_builder/make_contact_sheet.py \
        [--manifest .docs/component_builder/approved/manifest_review.csv]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
WORK_DIR = CB_ROOT / "work"
CANDIDATES_DIR = WORK_DIR / "symbol_candidates"
CONTACT_DIR = WORK_DIR / "contact_sheets"
MANIFEST_DEFAULT = CB_ROOT / "approved" / "manifest_review.csv"


def _resolve(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (REPO_ROOT / p)


def _rel_href(target: Path, base: Path) -> str:
    """POSIX relative href from the HTML file's folder to target."""
    import os

    return os.path.relpath(target, base).replace("\\", "/")


def find_candidates(row: dict) -> list[Path]:
    mfr = row.get("manufacturer") or "generic"
    cat = row.get("category") or "custom"
    cid = row.get("id") or ""
    d = CANDIDATES_DIR / mfr / cat / cid
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.png"))


CSS = """
:root { --bd:#d0d5dd; --mut:#667085; --ok:#12805c; --no:#b42318; }
* { box-sizing: border-box; }
body { font-family: system-ui, Segoe UI, Roboto, sans-serif; margin: 0; background:#f7f8fa; color:#101828; }
header { position: sticky; top:0; background:#101828; color:#fff; padding:14px 20px; z-index:10;
         display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
header h1 { font-size:16px; margin:0; }
header .stat { color:#98a2b3; font-size:13px; }
button { cursor:pointer; border:1px solid var(--bd); background:#fff; border-radius:8px; padding:8px 12px; font-size:13px; }
button.primary { background:#2e6fdb; color:#fff; border-color:#2e6fdb; }
main { padding:20px; display:grid; gap:16px; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr)); }
.card { background:#fff; border:1px solid var(--bd); border-radius:12px; overflow:hidden; }
.card .body { display:grid; grid-template-columns: 1fr 1fr; }
.pane { padding:12px; }
.pane h3 { margin:0 0 8px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--mut); }
.imgwrap { background:conic-gradient(#eee 25%, #fff 0 50%, #eee 0 75%, #fff 0) 0/20px 20px;
           border:1px solid var(--bd); border-radius:8px; min-height:150px; display:flex; align-items:center; justify-content:center; }
.imgwrap img { max-width:100%; max-height:240px; display:block; }
.cands { display:flex; gap:8px; flex-wrap:wrap; }
.cand { border:2px solid transparent; border-radius:8px; padding:4px; cursor:pointer; text-align:center; font-size:10px; color:var(--mut); }
.cand.sel { border-color:#2e6fdb; }
.cand img { width:96px; height:96px; object-fit:contain;
            background:conic-gradient(#eee 25%, #fff 0 50%, #eee 0 75%, #fff 0) 0/12px 12px; border-radius:4px; }
.meta { padding:12px; border-top:1px solid var(--bd); display:grid; grid-template-columns: 110px 1fr; gap:6px 10px; font-size:13px; align-items:center; }
.meta label { color:var(--mut); }
.meta .val { font-weight:600; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }
.badge.review { background:#fef3f2; color:var(--no); }
.badge.ok { background:#ecfdf3; color:var(--ok); }
.decision { display:flex; gap:8px; }
.decision label { display:flex; align-items:center; gap:4px; font-weight:600; cursor:pointer; }
textarea { width:100%; border:1px solid var(--bd); border-radius:8px; padding:6px; font:inherit; resize:vertical; }
.empty { color:var(--no); font-size:12px; }
"""

JS = """
const KEY = 'singh360_contact_review';
function load(){ try { return JSON.parse(localStorage.getItem(KEY)||'{}'); } catch(e){ return {}; } }
function save(s){ localStorage.setItem(KEY, JSON.stringify(s)); }
let state = load();
function set(id, k, v){ state[id]=state[id]||{}; state[id][k]=v; save(state); render(id); }
function pick(id, variant){ set(id,'chosenVariant',variant); }
function render(id){
  document.querySelectorAll(`[data-cand='${id}']`).forEach(el=>{
    el.classList.toggle('sel', el.dataset.variant===(state[id]&&state[id].chosenVariant));
  });
}
function hydrate(){
  document.querySelectorAll('.card').forEach(card=>{
    const id=card.dataset.id; const s=state[id]||{};
    if(s.decision){ const r=card.querySelector(`input[name='dec_${id}'][value='${s.decision}']`); if(r) r.checked=true; }
    if(s.notes){ const t=card.querySelector(`textarea[data-notes='${id}']`); if(t) t.value=s.notes; }
    render(id);
  });
}
function exportCsv(){
  const rows=[['id','decision','chosenVariant','notes']];
  Object.keys(state).forEach(id=>{ const s=state[id]||{};
    rows.push([id, s.decision||'', s.chosenVariant||'', (s.notes||'').replace(/\\n/g,' ')]); });
  const csv=rows.map(r=>r.map(c=>'\"'+String(c).replace(/\"/g,'\"\"')+'\"').join(',')).join('\\n');
  const blob=new Blob([csv],{type:'text/csv'}); const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download='review_decisions.csv'; a.click();
}
window.addEventListener('DOMContentLoaded', hydrate);
"""


def build_card(row: dict, base: Path) -> str:
    cid = html.escape(row.get("id", ""))
    src = _resolve(row.get("sourcePath", ""))
    src_href = _rel_href(src, base) if src.exists() else ""
    needs = row.get("needsReview", "false") == "true"
    badge = ('<span class="badge review">NEEDS REVIEW</span>' if needs
             else '<span class="badge ok">auto-classified</span>')

    cands = find_candidates(row)
    if cands:
        cand_html = "".join(
            f'<div class="cand" data-cand="{cid}" data-variant="{html.escape(p.stem)}" '
            f'onclick="pick(\'{cid}\',\'{html.escape(p.stem)}\')">'
            f'<img src="{_rel_href(p, base)}" alt="{html.escape(p.stem)}"><br>{html.escape(p.stem)}</div>'
            for p in cands
        )
    else:
        cand_html = '<p class="empty">No candidates yet. Run make_line_art_candidates.py.</p>'

    def field(label: str, key: str) -> str:
        return (f'<label>{label}</label>'
                f'<span class="val">{html.escape(row.get(key, "") or "&mdash;")}</span>')

    return f"""
<div class="card" data-id="{cid}">
  <div class="body">
    <div class="pane">
      <h3>Source image</h3>
      <div class="imgwrap">{('<img src="'+src_href+'">') if src_href else '<span class="empty">source missing</span>'}</div>
    </div>
    <div class="pane">
      <h3>B/W candidates</h3>
      <div class="cands">{cand_html}</div>
    </div>
  </div>
  <div class="meta">
    <label>Display name</label><span class="val">{html.escape(row.get('displayName',''))}</span>
    {field('Manufacturer','manufacturer')}
    {field('Category','category')}
    {field('Part number','partNumber')}
    <label>Status</label><span class="val">{badge}</span>
    <label>Decision</label>
    <span class="decision">
      <label><input type="radio" name="dec_{cid}" value="approve" onclick="set('{cid}','decision','approve')"> Approve</label>
      <label><input type="radio" name="dec_{cid}" value="reject" onclick="set('{cid}','decision','reject')"> Reject</label>
    </span>
    <label>Notes</label>
    <textarea data-notes="{cid}" rows="2" placeholder="review notes..."
      oninput="set('{cid}','notes',this.value)"></textarea>
  </div>
</div>"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(MANIFEST_DEFAULT))
    ap.add_argument("--out", default=str(CONTACT_DIR / "index.html"))
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import sys

    args = parse_args(argv)
    manifest = _resolve(args.manifest)
    if not manifest.exists():
        print(f"[error] manifest not found: {manifest}\n"
              "        run build_inventory.py first.", file=sys.stderr)
        return 2

    out_path = _resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base = out_path.parent

    with manifest.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    cards = "\n".join(build_card(r, base) for r in rows)
    review_count = sum(1 for r in rows if r.get("needsReview") == "true")

    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Singh360 Component Builder - Contact Sheet</title>
<style>{CSS}</style>
</head><body>
<header>
  <h1>Singh360 Component Builder &mdash; Symbol Review</h1>
  <span class="stat">{len(rows)} item(s) &middot; {review_count} need review</span>
  <button class="primary" onclick="exportCsv()">Export decisions CSV</button>
  <span class="stat">Decisions save automatically in this browser (localStorage).</span>
</header>
<main>
{cards}
</main>
<script>{JS}</script>
</body></html>"""

    out_path.write_text(doc, encoding="utf-8")
    rel = out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path
    print(f"[ok] contact sheet for {len(rows)} item(s) -> {rel}")
    print(f"[note] open it in a browser; use 'Export decisions CSV' to feed "
          "export_approved_symbols.py --decisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
