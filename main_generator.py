"""main_generator.py — Singh360_SmartDraw CLI control surface.

Pipeline:
  (optional) Azure DI / DI-tables CSV  ->  core.ingestion (spatial anchors)
  assets.csv + control_matrix.csv + network.csv  ->  core.data_orchestrator
  DiagramGraph  ->  engines.smartdraw_vson (.vson)  +  engines.visio_vsdx (.vsdx)

Run from the Singh360_SmartDraw folder, e.g.:

  python main_generator.py \
      --assets sample_data/assets.csv \
      --control sample_data/control_matrix.csv \
      --network sample_data/network.csv \
      --name "HEB SA31 Demo" --out-dir output --targets vson,vsdx

Spatial overlay (optional):
  --di-tables path/to/REFRIG_p3to4_DI_tables.csv     (deterministic, offline)
  --pdf plan.pdf --pages 3-4                          (live Azure DI)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import config  # noqa: E402
from core import ingestion  # noqa: E402
from core.data_orchestrator import DataOrchestrator  # noqa: E402
from engines import smartdraw_vson, visio_vsdx  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="singh360-smartdraw",
        description="Render Singh360 assets into SmartDraw VSON + Visio VSDX.",
    )
    p.add_argument("--assets", help="11-column app schedule CSV")
    p.add_argument(
        "--schedule-xlsx",
        dest="schedule_xlsx",
        help="Raw MEP schedule workbook (SA#31-style .xlsx); converted to "
        "canonical assets.csv + control_matrix.csv via core.schedule_adapter",
    )
    p.add_argument("--control", help="Relay/Contactor/Load control matrix CSV")
    p.add_argument("--network", help="Device/Switch/Port network CSV")
    p.add_argument("--di-tables", dest="di_tables", help="Parser *_DI_tables.csv")
    p.add_argument("--pdf", help="PDF for live Azure DI layout (needs creds)")
    p.add_argument(
        "--floorplan",
        help="Vector PDF blueprint scanned LOCALLY (PyMuPDF) to pin shapes to "
        "their true X/Y by matching asset/relay/contactor keys — no Azure.",
    )
    p.add_argument("--pages", default="1", help="1-based page spec for --pdf")
    p.add_argument("--name", default="Singh360 Diagram", help="Document title")
    p.add_argument("--out-dir", dest="out_dir", default="output", help="Output dir")
    p.add_argument(
        "--targets",
        default="vson,vsdx",
        help="Comma list: vson,vsdx",
    )
    p.add_argument("--layout", default="hierarchy", help="VSON auto-layout family")
    p.add_argument("--vssx", help="Optional .vssx stencil for Visio masters")
    return p.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in args.name).strip("_")
    safe = safe or "diagram"

    adapter_flags: list[str] = []
    # 0) Optional: convert a raw MEP schedule workbook to canonical CSVs first.
    if getattr(args, "schedule_xlsx", None):
        from core import schedule_adapter

        conv = schedule_adapter.convert(args.schedule_xlsx, out_dir / "_canonical")
        adapter_flags = list(conv.flags)
        if conv.assets_csv is None:
            print(
                "ERROR: schedule adapter produced no asset rows from "
                f"{args.schedule_xlsx}.",
                file=sys.stderr,
            )
            for fl in adapter_flags:
                print(f"  ! {fl}", file=sys.stderr)
            return 3
        args.assets = str(conv.assets_csv)
        if conv.control_csv and not args.control:
            args.control = str(conv.control_csv)
        adapter_flags.append(
            f"Adapter: {conv.fixture_count} fixtures, "
            f"{conv.contactor_count} contactors from {Path(args.schedule_xlsx).name}"
        )

    if not args.assets:
        print(
            "ERROR: provide --assets <csv> or --schedule-xlsx <workbook>.",
            file=sys.stderr,
        )
        return 2

    # 1) Build the relational graph.
    orch = DataOrchestrator(name=args.name)
    orch.load_assets(args.assets)
    if args.control:
        orch.load_control_matrix(args.control)
    if args.network:
        orch.load_network(args.network)
    orch.graph.flags.extend(adapter_flags)

    # 2) Optional spatial overlay.
    spatial = []
    if args.pdf:
        ing = ingestion.AzureLayoutIngestor()
        result = ing.analyze_pdf(args.pdf, args.pages)
        spatial = result.spatial
        ing.write_tables_csv(result, out_dir / f"{safe}_DI_tables.csv")
        orch.graph.flags.extend(result.flags)
    elif args.di_tables:
        # Deterministic offline path: reconstruct grids (no spatial polygons in
        # the CSV schema, so this enriches table provenance only).
        grids = ingestion.load_di_tables_csv(args.di_tables)
        orch.graph.flags.append(
            f"Loaded {len(grids)} DI table grid(s) from {Path(args.di_tables).name}"
        )
    if spatial:
        orch.attach_spatial(spatial)

    # 2b) Local vector-PDF blueprint: pin shapes to their TRUE X/Y by matching
    #     the project's keys against the blueprint's own text layer (no Azure).
    floorplan_png = None
    if getattr(args, "floorplan", None):
        from core.ingestion import VectorPdfIngestor

        ing = VectorPdfIngestor()
        keymap: dict[str, str] = {}
        for nid, node in orch.graph.nodes.items():
            for tok in (nid, getattr(node, "label", "") or nid):
                if tok:
                    keymap[str(tok)] = nid
            if ":" in nid:  # "Relay:R1" / "Contactor:C1" -> bare "R1" / "C1"
                keymap[nid.split(":", 1)[1]] = nid
        fp_result = ing.scan(args.floorplan, keymap, args.pages)
        orch.attach_spatial(fp_result.spatial)
        orch.graph.flags.extend(fp_result.flags)
        floorplan_png = ing.render_background_png(
            args.floorplan, out_dir / f"{safe}_floorplan.png"
        )
        if floorplan_png:
            orch.graph.flags.append(
                f"Floor-plan background rasterized -> {floorplan_png.name} "
                f"(overlay/background layer; embed in the sheet to underlay shapes)."
            )

    graph = orch.build()
    # 3) Render targets.
    targets = {t.strip().lower() for t in args.targets.split(",") if t.strip()}
    written: list[Path] = []
    reports: list[str] = []

    if "vson" in targets:
        gen = smartdraw_vson.VsonGenerator(layout=args.layout)
        vson_path = gen.render(graph, out_dir / f"{safe}.vson")
        ok, problems = smartdraw_vson.validate(vson_path)
        written.append(vson_path)
        reports.append(f"VSON  {'OK ' if ok else 'FAIL'} {vson_path.name}")
        reports.extend(f"        - {p}" for p in problems)

    if "vsdx" in targets:
        masters = visio_vsdx.MasterLibrary(args.vssx) if args.vssx else None
        writer = visio_vsdx.VsdxWriter(master_library=masters)
        vsdx_path = writer.write(graph, out_dir / f"{safe}.vsdx")
        ok, problems = visio_vsdx.validate_vsdx(vsdx_path)
        written.append(vsdx_path)
        reports.append(f"VSDX  {'OK ' if ok else 'FAIL'} {vsdx_path.name}")
        reports.extend(f"        - {p}" for p in problems)
        for fl in writer.flags:
            graph.flags.append(fl)

    _print_report(graph, written, reports)
    # Exit non-zero if any validator reported a problem.
    return 0 if all("FAIL" not in r for r in reports) else 2


def _print_report(graph, written, reports) -> None:
    s = graph.summary()
    print("\n" + "=" * 64)
    print(f"  Singh360_SmartDraw — {graph.name}")
    print("=" * 64)
    print(
        f"  graph: {s['nodes']} nodes / {s['edges']} edges "
        f"({s['edges_hierarchy']} hierarchy, {s['edges_control']} control, "
        f"{s['edges_network']} network) across {s['groups']} groups"
    )
    print("-" * 64)
    print("  RELATIONAL FLOW (coordinate -> auto-aligned shape):")
    print("   spatial polygon centroid  ->  normalized (cx,cy,w,h)")
    print("   asset Name                ->  Shape node + embedded data[]")
    print("   Connected/Area Served col ->  hierarchy connector (auto-route)")
    print("   Relay->Contactor->Load    ->  control connectors (dashed)")
    print("   Device->Switch/Port       ->  network connectors (dotted)")
    print("-" * 64)
    for r in reports:
        print("  " + r)
    if graph.flags:
        print("-" * 64)
        print("  FLAGS:")
        for fl in graph.flags:
            print(f"   ! {fl}")
    print("-" * 64)
    print("  WROTE:")
    for w in written:
        print(f"   -> {w}")
    print("=" * 64 + "\n")


def main() -> None:
    raise SystemExit(run(_parse_args()))


if __name__ == "__main__":
    main()
