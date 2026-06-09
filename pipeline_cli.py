"""pipeline_cli.py — run the whole EMS pipeline on a project folder.

  python pipeline_cli.py "<project-folder>" --name "HEB Seguin #716" \
      --out output/seguin716 --sheets io_schedule,network_layout

Stages: intake -> extract/merge -> validate -> document (model -> .vsdx/.vson).
Outputs land locally (never on the read-only source drive).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core.intake import inventory  # noqa: E402
from core.merge import build_model  # noqa: E402
from core.validate import validate, report  # noqa: E402
from engines import smartdraw_vson, visio_vsdx  # noqa: E402
from engines.spatial_layout import compute_spatial_layout  # noqa: E402
from engines.doc_templates import REGISTRY as SHEETS  # noqa: E402
import config  # noqa: E402

# sheets that should use the 2D floor-plan canvas + absolute placement
_SPATIAL_SHEETS = {"floorplan_layout"}


def _args(argv=None):
    p = argparse.ArgumentParser(prog="singh360-ems-pipeline")
    p.add_argument("folder", help="raw project folder to ingest")
    p.add_argument("--name", default="", help="store / project title")
    p.add_argument("--project-id", default="", dest="project_id")
    p.add_argument("--out", default="output/project", help="output directory")
    p.add_argument("--sheets", default="io_schedule,network_layout",
                   help="comma list of deliverables: " + ",".join(SHEETS))
    p.add_argument("--targets", default="vsdx,vson", help="render targets")
    p.add_argument("--canvas", default="archd",
                   help="page preset for spatial sheets: letter|tabloid|archc|archd|arche")
    p.add_argument("--cap", type=int, default=200, help="max files per source type")
    return p.parse_args(argv)


def run(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (a.name or "project")).strip("_") or "project"

    # 1) intake
    inv = inventory(a.folder)
    inv.save(out / f"{safe}_inventory.json")
    print(f"[1] intake: {inv.counts['total']} files; by source:")
    for k, v in sorted(inv._by_source().items(), key=lambda x: -x[1]):
        print(f"      {v:>5}  {k}")

    # 2+3) merge -> model
    model = build_model(a.folder, project_id=a.project_id, store=a.name, inv=inv, limit_per_type=a.cap)
    s = model.summary()
    print(f"[2] model: {s['nodes']} nodes, {s['points']} I/O points")
    for k, v in s["by_kind"].items():
        print(f"      {v:>5}  {k}")

    # 4) validate
    vc = validate(model)
    model.save(out / f"{safe}_model.json")
    (out / f"{safe}_validation.txt").write_text(report(model), encoding="utf-8")
    print(f"[3] validate: +{vc['added']} findings ({vc.get('review',0)} review, {vc.get('blocked',0)} blocked)")

    # 5) document
    sheets = [x.strip() for x in a.sheets.split(",") if x.strip() in SHEETS]
    targets = {t.strip().lower() for t in a.targets.split(",")}
    written = []
    for key in sheets:
        graph = SHEETS[key](model)
        base = f"{safe}_{key}"
        spatial = key in _SPATIAL_SHEETS
        if "vson" in targets:
            path = smartdraw_vson.VsonGenerator().render(graph, out / f"{base}.vson")
            ok, probs = smartdraw_vson.validate(path)
            written.append((path, "OK" if ok else f"FAIL {probs}"))
        if "vsdx" in targets:
            if spatial:
                pw, ph = config.page_size(a.canvas)
                writer = visio_vsdx.VsdxWriter(page_w=pw, page_h=ph,
                                               layout_fn=compute_spatial_layout)
            else:
                writer = visio_vsdx.VsdxWriter()
            path = writer.write(graph, out / f"{base}.vsdx")
            ok, probs = visio_vsdx.validate_vsdx(path)
            written.append((path, "OK" if ok else f"FAIL {probs}"))

    print(f"[4] documents: {len(written)} files")
    for path, status in written:
        print(f"      {status:>4}  {path.name}")
    print(f"\nOutputs in {out}")
    return 0 if all(st == "OK" for _, st in written) else 2


def main() -> None:
    raise SystemExit(run(_args()))


if __name__ == "__main__":
    main()
