from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import requests
from PIL import Image

BODY_W = 1598.0
BODY_H = 866.0
SHEET_H = 1056.0


def api_get(base: str, path: str) -> Any:
    r = requests.get(base.rstrip('/') + path, timeout=45)
    r.raise_for_status()
    return r.json()


def api_post(base: str, path: str, **kwargs: Any) -> Any:
    r = requests.post(base.rstrip('/') + path, timeout=120, **kwargs)
    r.raise_for_status()
    return r.json()


def choose(items: list[Any], label: str, formatter) -> Any:
    if not items:
        raise RuntimeError(f'No {label} found.')
    print(f'\nChoose {label}:')
    for idx, item in enumerate(items, 1):
        print(f'  {idx}. {formatter(item)}')
    while True:
        raw = input(f'{label} number: ').strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]


def upload_image(base: str, project_id: str, path: Path) -> str:
    with path.open('rb') as fh:
        r = requests.post(
            f'{base.rstrip("/")}/api/projects/{project_id}/assets',
            files={'file': (path.name, fh, 'image/png')},
            timeout=120,
        )
    r.raise_for_status()
    return r.json()['asset']['url']


def component_lookup(base: str) -> dict[str, dict[str, Any]]:
    try:
        data = api_get(base, '/api/lib?includeLegacy=1&includeRetired=0')
        return {str(c.get('id')): c for c in data.get('components', [])}
    except Exception:
        return {}


def parse_component_name(name: str) -> tuple[str, str] | None:
    m = re.search(r'S360_COMPONENT_ID=([^|]+)\|VARIANT=([^|]+)', name or '', re.I)
    return (m.group(1), m.group(2).lower()) if m else None


def map_geometry(manifest: dict[str, Any], obj: dict[str, Any]) -> tuple[float, float, float, float]:
    sw = float(manifest.get('slideWidthPt') or 960)
    sh = float(manifest.get('slideHeightPt') or 540)
    # A 17x11 Singh360 template reserves the lower title-block region. Other
    # slide ratios are treated as a full-slide rough layout.
    ratio = sw / sh if sh else 1.0
    if abs(ratio - (17 / 11)) < 0.08:
        import_height = sh * (BODY_H / SHEET_H)
    else:
        import_height = sh
    scale = min(BODY_W / sw, BODY_H / import_height)
    ox = (BODY_W - sw * scale) / 2
    oy = (BODY_H - import_height * scale) / 2
    left = ox + float(obj.get('leftPt') or 0) * scale
    top = oy + float(obj.get('topPt') or 0) * scale
    width = float(obj.get('widthPt') or 1) * scale
    height = float(obj.get('heightPt') or 1) * scale
    return left, top, width, height


def image_object(src: str, image_path: Path | None, geom: tuple[float, float, float, float], obj: dict[str, Any]) -> dict[str, Any]:
    left, top, target_w, target_h = geom
    px_w = px_h = 1
    if image_path and image_path.exists():
        with Image.open(image_path) as im:
            px_w, px_h = im.size
    return {
        'id': f'obj_ppt_{uuid.uuid4().hex[:12]}',
        'type': 'image',
        'left': left,
        'top': top,
        'width': px_w,
        'height': px_h,
        'scaleX': target_w / max(px_w, 1),
        'scaleY': target_h / max(px_h, 1),
        'angle': float(obj.get('rotation') or 0),
        'originX': 'left',
        'originY': 'top',
        'src': src,
        'objName': str(obj.get('name') or 'PowerPoint object'),
        'crossOrigin': 'anonymous',
        'source': {'type': 'powerpoint', 'slide': obj.get('slideIndex')},
    }


def text_object(text: str, geom: tuple[float, float, float, float], obj: dict[str, Any]) -> dict[str, Any]:
    left, top, width, height = geom
    return {
        'id': f'obj_ppt_{uuid.uuid4().hex[:12]}',
        'type': 'textbox',
        'left': left,
        'top': top,
        'width': width,
        'height': height,
        'scaleX': 1,
        'scaleY': 1,
        'angle': float(obj.get('rotation') or 0),
        'originX': 'left',
        'originY': 'top',
        'text': text,
        'fontSize': 14,
        'fontFamily': 'Arial',
        'fill': '#111111',
        'objName': str(obj.get('name') or 'PowerPoint text'),
        'source': {'type': 'powerpoint', 'slide': obj.get('slideIndex')},
    }


def objects_for_slide(base: str, project_id: str, folder: Path, manifest: dict[str, Any], slide: dict[str, Any], library: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in slide.get('objects', []):
        obj = dict(raw)
        obj['slideIndex'] = slide.get('slideIndex')
        geom = map_geometry(manifest, obj)
        component_ref = parse_component_name(str(obj.get('name') or ''))
        if component_ref:
            cid, variant = component_ref
            component = library.get(cid)
            if component:
                src = component.get('edgeUrl') if variant == 'edge' else component.get('sourceUrl')
                src = src or component.get('sourceUrl') or component.get('edgeUrl')
                if src:
                    output.append(image_object(src, None, geom, obj))
                    continue
        image_name = str(obj.get('image') or '')
        image_path = folder / image_name if image_name else None
        if image_path and image_path.is_file():
            src = upload_image(base, project_id, image_path)
            output.append(image_object(src, image_path, geom, obj))
        elif str(obj.get('text') or '').strip():
            output.append(text_object(str(obj['text']), geom, obj))
    return output


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--server', default='http://127.0.0.1:8766')
    ap.add_argument('--mode', choices=['overlay', 'new-pages'], default='overlay')
    args = ap.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    folder = manifest_path.parent
    projects = api_get(args.server, '/api/projects').get('projects', [])
    project_item = choose(projects, 'project', lambda p: f"{p.get('projectName') or p.get('projectDisplayName') or p.get('id')} [{p.get('id')}]")
    project_id = project_item['id']
    project = api_get(args.server, f'/api/projects/{project_id}')
    pages = project.get('pages', [])
    library = component_lookup(args.server)

    if args.mode == 'overlay':
        page = choose(pages, 'target page', lambda p: f"{p.get('sheetCode','')}  {p.get('sheetTitle','')}")
        all_objs: list[dict[str, Any]] = []
        for slide in manifest.get('slides', []):
            all_objs.extend(objects_for_slide(args.server, project_id, folder, manifest, slide, library))
        page['canvasObjects'] = list(page.get('canvasObjects') or []) + all_objs
        print(f'Adding {len(all_objs)} objects to {page.get("sheetTitle")}...')
    else:
        for slide in manifest.get('slides', []):
            objs = objects_for_slide(args.server, project_id, folder, manifest, slide, library)
            idx = len(pages) + 1
            pages.append({
                'id': f'page_ppt_{uuid.uuid4().hex[:12]}',
                'order': idx,
                'include': True,
                'sheetCode': f'PPT {idx}',
                'displaySheetCode': f'PPT {idx}',
                'sheetTitle': str(slide.get('title') or f'PowerPoint Slide {slide.get("slideIndex")}'),
                'sheetTab': f'PowerPoint Slide {slide.get("slideIndex")}',
                'pageType': 'canvas',
                'templateId': 'ansi-b-standard',
                'linkedWorksheetId': '',
                'blocks': [],
                'canvasObjects': objs,
                'underlays': [],
                'notes': 'Imported from PowerPoint.',
                'revisionRows': [],
            })
            print(f'Created page with {len(objs)} objects: {slide.get("title")}')

    project['pages'] = pages
    api_post(args.server, f'/api/projects/{project_id}', json=project)
    print('\nDONE')
    print(f'Open: {args.server}/app?project={project_id}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
