from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.library_v2 import LibraryV2  # noqa: E402

OUT = ROOT / "docs" / "component-library"
BACKUP_ROOT = ROOT / ".docs" / "archive"


def slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (value or "").strip()).strip("-").lower()
    return s or "component"


def rel_asset(path: Path) -> str:
    return path.relative_to(OUT).as_posix()


def copy_variant(lib: LibraryV2, rel: str, dest_dir: Path, base_name: str) -> str:
    if not rel:
        return ""
    src = (lib.root / rel).resolve()
    try:
        src.relative_to(lib.root.resolve())
    except ValueError:
        return ""
    if not src.is_file():
        return ""
    ext = src.suffix.lower() or ".bin"
    dest = dest_dir / f"{base_name}{ext}"
    shutil.copy2(src, dest)
    return rel_asset(dest)


def parse_remote() -> tuple[str, str]:
    owner, repo = "dstogsdill1", "Singh360_SmartDraw"
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=ROOT, text=True
        ).strip()
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            owner, repo = m.group(1), m.group(2)
    except Exception:
        pass
    return owner, repo


def active_status(c: dict) -> bool:
    if bool(c.get("retired")):
        return False
    return str(c.get("status") or "").strip().lower() not in {
        "retired",
        "archive",
        "archived",
        "deleted",
    }


def generate_static_index(owner: str, repo: str) -> str:
    template = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Singh360 Component Library</title>
<style>
:root{--nav:#0c1730;--bg:#f5f7fb;--card:#fff;--line:#d9deea;--ink:#172033;--muted:#68748a;--accent:#315efb}
*{box-sizing:border-box}body{margin:0;font:14px Arial,Helvetica,sans-serif;background:var(--bg);color:var(--ink)}
header{position:sticky;top:0;z-index:10;background:var(--nav);color:#fff;padding:12px 18px;display:flex;gap:12px;align-items:center}
header h1{font-size:18px;margin:0}.sub{font-size:12px;color:#c3cee3}.grow{flex:1}
.toolbar{position:sticky;top:59px;z-index:9;background:#fff;padding:10px 16px;border-bottom:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap}
.field,button{font:inherit;border:1px solid #b8c2d3;border-radius:5px;padding:8px;background:#fff}.field[type=search]{flex:1;min-width:260px}
.layout{display:grid;grid-template-columns:190px 1fr;min-height:calc(100vh - 115px)}aside{background:#fff;border-right:1px solid var(--line);padding:10px}
.cat{width:100%;display:flex;justify-content:space-between;border:1px solid transparent;background:transparent;padding:8px;text-align:left;border-radius:5px}
.cat.active,.cat:hover{background:#edf2ff;border-color:#bfd0ff}.main{padding:12px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:9px;display:flex;flex-direction:column;gap:7px;min-height:245px}
.thumb{height:135px;border:1px solid #e2e6ef;background:#fbfcfe;display:grid;place-items:center;overflow:hidden}.thumb img{max-width:100%;max-height:100%;object-fit:contain}
.name{font-weight:700}.meta{font-size:12px;color:var(--muted)}.actions{margin-top:auto;display:flex;gap:6px;flex-wrap:wrap}
button{cursor:pointer}.primary{background:var(--accent);border-color:var(--accent);color:#fff}.empty{padding:30px;text-align:center;color:var(--muted)}
@media(max-width:700px){.layout{display:block}aside{display:none}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body>
<header><div><h1>Singh360 Component Library</h1><div class="sub">Published active components - copy or download Real and Edge representations.</div></div>
<div class="grow"></div><a style="color:#fff" href="https://github.com/__OWNER__/__REPO__">GitHub repository</a></header>
<div class="toolbar"><input id="q" class="field" type="search" placeholder="Search name, part, label, alias...">
<select id="rep" class="field"><option value="real">Real</option><option value="edge">Edge</option></select><button id="reload">Reload</button></div>
<div class="layout"><aside id="cats"></aside><main class="main"><div id="stats" class="meta"></div><div id="grid" class="grid"></div></main></div>
<script>
let all=[],category='all';const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function variant(c){const r=$('#rep').value;return r==='edge'?(c.edge||c.real):(c.real||c.edge)}
function filtered(){const q=$('#q').value.trim().toLowerCase();return all.filter(c=>(category==='all'||c.category===category)&&(!q||[c.displayName,c.partNumber,c.defaultLabel,(c.aliases||[]).join(' '),c.category].join(' ').toLowerCase().includes(q)))}
async function copyImage(url){const res=await fetch(url);if(!res.ok)throw new Error('Image fetch failed');const blob=await res.blob();const img=await createImageBitmap(blob);const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;canvas.getContext('2d').drawImage(img,0,0);const png=await new Promise(r=>canvas.toBlob(r,'image/png'));await navigator.clipboard.write([new ClipboardItem({'image/png':png})]);}
function download(url,name){const a=document.createElement('a');a.href=url;a.download=name||'';a.click()}
function renderCats(){const counts={};all.forEach(c=>counts[c.category]=(counts[c.category]||0)+1);const cats=['all',...Object.keys(counts).sort()];$('#cats').innerHTML=cats.map(x=>`<button class="cat ${category===x?'active':''}" data-c="${esc(x)}"><span>${x==='all'?'All categories':esc(x.replaceAll('_',' '))}</span><b>${x==='all'?all.length:counts[x]}</b></button>`).join('');document.querySelectorAll('.cat').forEach(b=>b.onclick=()=>{category=b.dataset.c;render()})}
function render(){renderCats();const items=filtered();$('#stats').textContent=`${items.length} visible - ${all.length} active components`;$('#grid').innerHTML=items.length?items.map(c=>{const u=variant(c);return`<article class="card"><div class="thumb">${u?`<img loading="lazy" src="${esc(u)}">`:'No image'}</div><div class="name">${esc(c.displayName)}</div><div class="meta">${esc(c.category.replaceAll('_',' '))}${c.partNumber?' - '+esc(c.partNumber):''}</div><div class="actions"><button class="primary copy" ${u?'':'disabled'}>Copy Image</button><button class="dl" ${u?'':'disabled'}>Download</button></div></article>`}).join(''):'<div class="empty">No matching components.</div>';document.querySelectorAll('.card').forEach((el,i)=>{const c=items[i],u=variant(c);el.querySelector('.copy').onclick=async()=>{try{await copyImage(u);el.querySelector('.copy').textContent='Copied';setTimeout(()=>el.querySelector('.copy').textContent='Copy Image',1200)}catch(e){alert(e.message)}};el.querySelector('.dl').onclick=()=>download(u,`${c.displayName}-${$('#rep').value}`)})}
async function load(){const r=await fetch('catalog.json',{cache:'no-store'});all=await r.json();render()}
$('#q').oninput=render;$('#rep').onchange=render;$('#reload').onclick=load;load();
</script></body></html>'''
    return template.replace("__OWNER__", html.escape(owner)).replace("__REPO__", html.escape(repo))


def main() -> int:
    owner, repo = parse_remote()
    lib = LibraryV2(ROOT / ".docs")
    lib.ensure()
    data = lib.load(include_legacy=True)
    components = [c for c in data.get("components", []) if active_status(c)]

    if OUT.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_ROOT / f"published_component_library_{stamp}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(OUT, backup, dirs_exist_ok=True)
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True, exist_ok=True)

    published: list[dict] = []
    for c in sorted(
        components,
        key=lambda x: (str(x.get("category")), str(x.get("displayName"))),
    ):
        cid = slug(str(c.get("id") or c.get("displayName") or "component"))
        category = slug(str(c.get("category") or "custom"))
        dest = OUT / "assets" / category / cid
        dest.mkdir(parents=True, exist_ok=True)
        real_rel = copy_variant(lib, str(c.get("sourceFile") or ""), dest, "real")
        edge_rel = copy_variant(
            lib,
            str(c.get("edgeFile") or c.get("symbolFile") or ""),
            dest,
            "edge",
        )
        if not real_rel and not edge_rel:
            shutil.rmtree(dest, ignore_errors=True)
            continue
        published.append(
            {
                "id": c.get("id") or cid,
                "displayName": c.get("displayName") or cid,
                "category": c.get("category") or "custom",
                "partNumber": c.get("partNumber") or "",
                "defaultLabel": c.get("defaultLabel") or "",
                "aliases": c.get("aliases") or [],
                "real": real_rel,
                "edge": edge_rel,
            }
        )

    (OUT / "catalog.json").write_text(
        json.dumps(published, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "index.html").write_text(
        generate_static_index(owner, repo),
        encoding="utf-8",
    )
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "README.md").write_text(
        f"# Singh360 Component Library\n\nPublished active components: **{len(published)}**\n\n"
        f"GitHub Pages: https://{owner}.github.io/{repo}/component-library/\n",
        encoding="utf-8",
    )
    print(f"Published {len(published)} active components to {OUT}")
    if published:
        print(f"First asset: {published[0].get('real') or published[0].get('edge')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
