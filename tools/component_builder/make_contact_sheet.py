#!/usr/bin/env python3
"""make_contact_sheet.py -- human-review HTML contact sheet.

Builds a single self-contained HTML page from the master catalog (or the legacy
manifest_review.csv). Each card shows the real source image beside every B/W
candidate variant, the catalog metadata, and editable approve/reject + chosen
variant + notes fields. A per-category count summary is shown at the top.

Decisions are stored in the browser's localStorage and can be exported to a CSV
(id, decision, chosenVariant, notes) that export_approved_symbols.py understands.

Output:
    .docs/component_builder/work/contact_sheets/index.html

Usage:
    python tools/component_builder/make_contact_sheet.py \
        --manifest Singh360_Component_Master_Catalog.csv --source-root sources --open
"""
from __future__ import annotations

import argparse
import html
import os
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _catalog  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CB_ROOT = REPO_ROOT / ".docs" / "component_builder"
CONTACT_DIR = CB_ROOT / "work" / "contact_sheets"
MANIFEST_DEFAULT = CB_ROOT / "approved" / "manifest_review.csv"

# Preferred candidate display order.
VARIANT_ORDER = ["device", "lineart", "outline", "silhouette", "edges",
                 "highcontrast", "nobg", "grayscale"]


def _href(target: Path, base: Path) -> str:
    return os.path.relpath(target, base).replace("\\", "/")


def find_candidates(row: dict) -> list[Path]:
    d = _catalog.candidate_dir(row)
    if not d.exists():
        return []
    pngs = {p.stem: p for p in d.glob("*.png")}
    ordered = [pngs.pop(v) for v in VARIANT_ORDER if v in pngs]
    ordered += [pngs[k] for k in sorted(pngs)]
    return ordered


CSS = """
:root { --bd:#d0d5dd; --mut:#667085; --ok:#12805c; --no:#b42318; }
* { box-sizing:border-box; }
body { font-family:system-ui,Segoe UI,Roboto,sans-serif; margin:0; background:#f7f8fa; color:#101828; }
header { position:sticky; top:0; background:#101828; color:#fff; padding:12px 20px; z-index:10;
         display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
header h1 { font-size:16px; margin:0; }
header .stat { color:#98a2b3; font-size:13px; }
button { cursor:pointer; border:1px solid var(--bd); background:#fff; border-radius:8px; padding:8px 12px; font-size:13px; }
button.primary { background:#2e6fdb; color:#fff; border-color:#2e6fdb; }
.summary { padding:12px 20px; background:#fff; border-bottom:1px solid var(--bd); display:flex; gap:8px; flex-wrap:wrap; }
.chip { border:1px solid var(--bd); border-radius:999px; padding:4px 10px; font-size:12px; background:#f9fafb; }
.chip b { color:#101828; } .chip span { color:var(--mut); }
main { padding:20px; display:grid; gap:16px; grid-template-columns:repeat(auto-fill,minmax(560px,1fr)); }
.card { background:#fff; border:1px solid var(--bd); border-radius:12px; overflow:hidden; }
.card.review { border-color:#fda29b; }
.body { display:grid; grid-template-columns:280px 1fr; }
.pane { padding:12px; } .pane h3 { margin:0 0 8px; font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--mut); }
.imgwrap { background:conic-gradient(#eee 25%,#fff 0 50%,#eee 0 75%,#fff 0) 0/20px 20px;
           border:1px solid var(--bd); border-radius:8px; min-height:160px; display:flex; align-items:center; justify-content:center; }
.imgwrap img { max-width:100%; max-height:240px; display:block; }
.cands { display:flex; gap:8px; flex-wrap:wrap; }
.cand { border:2px solid transparent; border-radius:8px; padding:4px; cursor:pointer; text-align:center; font-size:10px; color:var(--mut); }
.cand.sel { border-color:#2e6fdb; }
.cand img { width:92px; height:92px; object-fit:contain;
            background:conic-gradient(#eee 25%,#fff 0 50%,#eee 0 75%,#fff 0) 0/12px 12px; border-radius:4px; }
.meta { padding:12px; border-top:1px solid var(--bd); display:grid; grid-template-columns:120px 1fr; gap:6px 10px; font-size:13px; align-items:center; }
.meta label { color:var(--mut); } .meta .val { font-weight:600; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }
.badge.review { background:#fef3f2; color:var(--no); } .badge.ok { background:#ecfdf3; color:var(--ok); }
.decision { display:flex; gap:12px; } .decision label { display:flex; align-items:center; gap:4px; font-weight:600; cursor:pointer; }
textarea { width:100%; border:1px solid var(--bd); border-radius:8px; padding:6px; font:inherit; resize:vertical; }
.empty { color:var(--no); font-size:12px; }
"""

JS = r"""
const KEY='singh360_contact_review';
function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
function save(s){localStorage.setItem(KEY,JSON.stringify(s))}
let state=load();
function set(id,k,v){state[id]=state[id]||{};state[id][k]=v;save(state);render(id)}
function pick(id,variant){set(id,'chosenVariant',variant)}
function render(id){document.querySelectorAll(`[data-cand='${id}']`).forEach(el=>{
  el.classList.toggle('sel', el.dataset.variant===(state[id]&&state[id].chosenVariant));});}
function hydrate(){document.querySelectorAll('.card').forEach(card=>{const id=card.dataset.id;const s=state[id]||{};
  if(s.decision){const r=card.querySelector(`input[name='dec_${id}'][value='${s.decision}']`);if(r)r.checked=true;}
  if(s.notes){const t=card.querySelector(`textarea[data-notes='${id}']`);if(t)t.value=s.notes;}
  render(id);});}
function exportCsv(){const rows=[['id','decision','chosenVariant','notes']];
  Object.keys(state).forEach(id=>{const s=state[id]||{};rows.push([id,s.decision||'',s.chosenVariant||'',(s.notes||'').replace(/\n/g,' ')]);});
  const csv=rows.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(',')).join('\n');
  const blob=new Blob([csv],{type:'text/csv'});const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download='review_decisions.csv';a.click();}
window.addEventListener('DOMContentLoaded',hydrate);
"""


def build_card(row: dict, base: Path) -> str:
    cid = html.escape(row["id"])
    src = Path(row["sourcePath"]) if row["sourcePath"] else None
    src_href = _href(src, base) if (src and src.exists()) else ""
    needs = row["needsReview"]
    badge = ('<span class="badge review">NEEDS REVIEW</span>' if needs
             else '<span class="badge ok">catalog-classified</span>')

    cands = find_candidates(row)
    if cands:
        cand_html = "".join(
            f'<div class="cand" data-cand="{cid}" data-variant="{html.escape(p.stem)}" '
            f'onclick="pick(\'{cid}\',\'{html.escape(p.stem)}\')">'
            f'<img src="{_href(p, base)}" alt="{html.escape(p.stem)}"><br>{html.escape(p.stem)}</div>'
            for p in cands)
    else:
        cand_html = '<p class="empty">No candidates yet. Run make_line_art_candidates.py.</p>'

    if src_href:
        src_html = f'<img src="{src_href}">'
    elif row["templateSpecific"]:
        src_html = '<span class="empty">no source image &mdash; procedural template</span>'
    else:
        src_html = '<span class="empty">no source image</span>'

    def field(label: str, key: str) -> str:
        v = row.get(key) or "&mdash;"
        return f'<label>{label}</label><span class="val">{html.escape(str(v))}</span>'

    return f"""
<div class="card{' review' if needs else ''}" data-id="{cid}">
  <div class="body">
    <div class="pane"><h3>Source image</h3><div class="imgwrap">{src_html}</div></div>
    <div class="pane"><h3>B/W candidates</h3><div class="cands">{cand_html}</div></div>
  </div>
  <div class="meta">
    <label>Display name</label><span class="val">{html.escape(row['displayName'])}</span>
    {field('Manufacturer','manufacturer')}
    {field('Category','category')}
    {field('Part number','partNumber')}
    {field('Template','templateType')}
    <label>Status</label><span class="val">{badge}</span>
    <label>Decision</label>
    <span class="decision">
      <label><input type="radio" name="dec_{cid}" value="approve" onclick="set('{cid}','decision','approve')"> Approve</label>
      <label><input type="radio" name="dec_{cid}" value="reject" onclick="set('{cid}','decision','reject')"> Reject</label>
    </span>
    <label>Notes</label>
    <textarea data-notes="{cid}" rows="2" placeholder="review notes...">{html.escape(row.get('notes',''))}</textarea>
  </div>
</div>"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=str(MANIFEST_DEFAULT),
                    help="Master catalog CSV or manifest_review.csv.")
    ap.add_argument("--source-root", default=None,
                    help="Root folder for catalog sourceImageFile paths (e.g. 'sources').")
    ap.add_argument("--out", default=str(CONTACT_DIR / "index.html"))
    ap.add_argument("--open", action="store_true", help="Open the contact sheet in a browser.")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = _catalog.resolve_manifest(args.manifest)
    if not manifest:
        print(f"[error] manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    source_root = _catalog.resolve_source_root(args.source_root, manifest.parent)
    rows, _catalog_mode = _catalog.load_rows(manifest, source_root)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base = out_path.parent

    cards = "\n".join(build_card(r, base) for r in rows)
    review_count = sum(1 for r in rows if r["needsReview"])
    with_source = sum(1 for r in rows if r["sourceExists"])

    summary = _catalog.category_summary(rows)
    chips = "".join(
        f'<span class="chip"><b>{html.escape(c["category"])}</b> '
        f'<span>{c["total"]} total &middot; {c["withSource"]} img &middot; '
        f'{c["proceduralOnly"]} proc &middot; {c["needsReview"]} review</span></span>'
        for c in summary)

    doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Singh360 Component Builder - Contact Sheet</title>
<style>{CSS}</style></head><body>
<header>
  <h1>Singh360 Component Builder &mdash; Symbol Review</h1>
  <span class="stat">{len(rows)} item(s) &middot; {with_source} with source image &middot; {review_count} need review</span>
  <button class="primary" onclick="exportCsv()">Export decisions CSV</button>
  <span class="stat">Decisions autosave in this browser (localStorage).</span>
</header>
<div class="summary">{chips}</div>
<main>
{cards}
</main>
<script>{JS}</script>
</body></html>"""

    out_path.write_text(doc, encoding="utf-8")
    print(f"[ok] contact sheet for {len(rows)} item(s) -> {_catalog.rel_to_repo(out_path)}")
    print(f"[ok] {with_source} with source image, {review_count} need review.")
    print("\n[category summary]")
    print(f"  {'category':22} {'total':>5} {'src':>5} {'proc':>5} {'review':>7}")
    for c in summary:
        print(f"  {c['category']:22} {c['total']:>5} {c['withSource']:>5} "
              f"{c['proceduralOnly']:>5} {c['needsReview']:>7}")
    if args.open:
        try:
            webbrowser.open(out_path.as_uri())
        except Exception as exc:  # pragma: no cover
            print(f"[warn] could not open browser: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
