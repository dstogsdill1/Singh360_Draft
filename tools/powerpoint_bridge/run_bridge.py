from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--kind', choices=['selection','slides'], required=True)
    ap.add_argument('--server', default='http://127.0.0.1:8766')
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='S360_PPT_') as td:
        ps = here / 'export_powerpoint.ps1'
        mode = 'Selection' if args.kind == 'selection' else 'Slides'
        cmd = ['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ps),'-Mode',mode,'-OutputDir',td]
        if args.kind == 'slides':
            raw = input('Slide numbers (example 1,3,5) or ALL: ').strip() or 'ALL'
            cmd += ['-SlideNumbers',raw]
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode:
            print(result.stdout); print(result.stderr, file=sys.stderr); return result.returncode
        lines = [x.strip() for x in result.stdout.splitlines() if x.strip()]
        manifest = Path(lines[-1]) if lines else Path(td) / 'manifest.json'
        if not manifest.is_file():
            print(result.stdout); print('PowerPoint export did not produce a manifest.', file=sys.stderr); return 1
        send_mode = 'overlay' if args.kind == 'selection' else 'new-pages'
        return subprocess.call([sys.executable, str(here/'send_manifest.py'),'--manifest',str(manifest),'--server',args.server,'--mode',send_mode])

if __name__ == '__main__':
    raise SystemExit(main())
