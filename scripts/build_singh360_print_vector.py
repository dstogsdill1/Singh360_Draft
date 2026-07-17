"""Build print-ready vector Singh360 logo (EPS/SVG/PDF) from source PNG."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
DESKTOP = Path.home() / "OneDrive - Homeland Development Services LLC" / "Desktop"

SOURCE = ASSETS / "singh360-logo-source.png"
MASTER_SVG = ASSETS / "singh360-print-master.svg"
TRACE_TMP = ASSETS / "_singh360_print_trace_src.png"

LOGICAL_W = 300
LOGICAL_H = 51
UPSCALE = 8

BRAND_BLUE = "#3079B4"
WHITE_FILLS = {
    "#ffffff",
    "#fefefe",
    "#feffff",
    "#fff",
    "#eaf1f6",
    "#ecf2f8",
    "#f2f7fa",
    "#fefeff",
}


def resolve_source() -> Path:
    candidates = [
        SOURCE,
        DESKTOP / "singh360-logo-source.png",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise SystemExit("Source PNG missing: docs/assets/singh360-logo-source.png")


def composite_on_black(im: Image.Image) -> Image.Image:
    rgba = im.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    bg.paste(rgba, (0, 0), rgba)
    return bg.convert("RGB")


def prepare_trace_input(source: Path) -> tuple[Path, int, int]:
    im = Image.open(source).convert("RGBA")
    w, h = im.size
    # Trace from black background so white building/icon regions remain distinct.
    black = composite_on_black(im)
    up_w, up_h = w * UPSCALE, h * UPSCALE
    upscaled = black.resize((up_w, up_h), Image.Resampling.LANCZOS)
    ASSETS.mkdir(parents=True, exist_ok=True)
    upscaled.save(TRACE_TMP)
    return TRACE_TMP, w, h


def trace_to_svg(trace_png: Path, out: Path, logical_w: int, logical_h: int) -> None:
    import vtracer

    vtracer.convert_image_to_svg_py(
        str(trace_png),
        str(out),
        colormode="color",
        hierarchical="stacked",
        mode="spline",
        filter_speckle=10,
        color_precision=5,
        layer_difference=10,
        corner_threshold=75,
        length_threshold=6.0,
        max_iterations=10,
        splice_threshold=45,
        path_precision=3,
    )
    svg = out.read_text(encoding="utf-8")
    up_w, up_h = logical_w * UPSCALE, logical_h * UPSCALE
    svg = re.sub(r'width="\d+"', f'width="{logical_w}"', svg, count=1)
    svg = re.sub(r'height="\d+"', f'height="{logical_h}"', svg, count=1)
    if "viewBox=" not in svg:
        svg = svg.replace(
            f'width="{logical_w}"',
            f'viewBox="0 0 {up_w} {up_h}" width="{logical_w}"',
            1,
        )
    else:
        svg = re.sub(
            r'viewBox="0 0 \d+ \d+"',
            f'viewBox="0 0 {up_w} {up_h}"',
            svg,
            count=1,
        )
    out.write_text(svg, encoding="utf-8")


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _is_near_white(fill: str) -> bool:
    fill = fill.strip().lower()
    if fill in WHITE_FILLS:
        return True
    m = re.match(r"#([0-9a-f]{6})", fill)
    if not m:
        return False
    r, g, b = _hex_to_rgb("#" + m.group(1))
    return r >= 230 and g >= 230 and b >= 230


def _path_in_icon_region(transform: str) -> bool:
    m = re.search(r"translate\(([\d.+-]+),\s*([\d.+-]+)\)", transform)
    if not m:
        return True
    x = float(m.group(1))
    y = float(m.group(2))
    return x <= 80 * UPSCALE and y <= 40 * UPSCALE


def post_process_svg(svg_path: Path, logical_w: int, logical_h: int) -> str:
    raw = svg_path.read_text(encoding="utf-8")
    if re.search(r"<image\b", raw, re.I):
        raise SystemExit("Trace output contains embedded raster — aborting.")
    if re.search(r"<text\b", raw, re.I):
        raise SystemExit("Trace output contains live text — aborting.")

    def add_stroke(match: re.Match[str]) -> str:
        tag = match.group(0)
        fill_m = re.search(r'fill="([^"]+)"', tag)
        transform_m = re.search(r'transform="([^"]+)"', tag)
        if not fill_m or not _is_near_white(fill_m.group(1)):
            return tag
        if transform_m and not _path_in_icon_region(transform_m.group(1)):
            return tag
        if 'stroke="' in tag:
            return tag
        stroke_w = max(1.0, 0.5 * UPSCALE)
        return tag.replace(
            "/>",
            f' stroke="{BRAND_BLUE}" stroke-width="{stroke_w:.2f}" stroke-linejoin="round"/>',
        )

    body = re.sub(r"^.*?<svg[^>]*>", "", raw, count=1, flags=re.S)
    body = re.sub(r"</svg>\s*$", "", body)
    body = re.sub(r"<path[^>]*/>", add_stroke, body)

    up_w, up_h = logical_w * UPSCALE, logical_h * UPSCALE
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {up_w} {up_h}" '
        f'width="{logical_w}" height="{logical_h}" role="img" '
        'aria-label="SINGH360 — Making difference in energy solutions">\n'
        f"{body}\n</svg>\n"
    )
    svg_path.write_text(svg, encoding="utf-8")
    return svg


def count_paths(svg: str) -> int:
    return len(re.findall(r"<path\b", svg, re.I))


def find_inkscape() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Inkscape\bin\inkscape.exe"),
        Path(r"C:\Program Files\Inkscape\inkscape.exe"),
    ]
    for path in candidates:
        if path.exists():
            return path
    found = shutil.which("inkscape")
    return Path(found) if found else None


def export_with_inkscape(inkscape: Path, svg_path: Path, dest: Path, export_type: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(inkscape),
        str(svg_path),
        f"--export-type={export_type}",
        f"--export-filename={dest}",
        "--export-background=#ffffff",
        "--export-background-opacity=1",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def validate_outputs(svg_path: Path, eps_path: Path, pdf_path: Path, svg_text: str) -> dict:
    results: dict[str, object] = {}
    results["path_count"] = count_paths(svg_text)
    results["has_raster_svg"] = bool(re.search(r"<image\b|data:image", svg_text, re.I))
    results["has_text_svg"] = bool(re.search(r"<text\b|@font-face", svg_text, re.I))
    results["svg_size_kb"] = round(svg_path.stat().st_size / 1024, 1)

    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_text)
    if vb:
        vw, vh = float(vb.group(1)), float(vb.group(2))
        ratio = vw / vh
        target = LOGICAL_W / LOGICAL_H
        results["aspect_ratio_ok"] = abs(ratio - target) / target <= 0.02
    else:
        results["aspect_ratio_ok"] = False

    eps_text = eps_path.read_text(encoding="latin-1", errors="ignore") if eps_path.exists() else ""
    results["eps_header_ok"] = eps_text.startswith("%!PS-Adobe")
    results["eps_has_fonttype"] = "/FontType" in eps_text
    results["eps_has_image_data"] = "image" in eps_text.lower() and "/DeviceRGB" in eps_text
    results["pdf_exists"] = pdf_path.exists()
    results["eps_size_kb"] = round(eps_path.stat().st_size / 1024, 1) if eps_path.exists() else 0
    results["pdf_size_kb"] = round(pdf_path.stat().st_size / 1024, 1) if pdf_path.exists() else 0
    return results


def main() -> int:
    source = resolve_source()
    trace_png, w, h = prepare_trace_input(source)
    print(f"Trace input: {trace_png} ({w * UPSCALE}x{h * UPSCALE} on black, export on white)")

    trace_to_svg(trace_png, MASTER_SVG, w, h)
    svg_text = post_process_svg(MASTER_SVG, w, h)
    paths = count_paths(svg_text)
    print(f"Master SVG: {MASTER_SVG} ({paths} paths)")

    if paths > 800:
        print(f"WARNING: high path count ({paths}) — may be noisy", file=sys.stderr)
    elif paths < 50:
        print(f"WARNING: low path count ({paths}) — may be over-simplified", file=sys.stderr)

    trace_png.unlink(missing_ok=True)

    desktop_svg = DESKTOP / "singh360-logo-vector.svg"
    desktop_eps = DESKTOP / "singh360-logo-vector.eps"
    desktop_pdf = DESKTOP / "singh360-logo-vector.pdf"

    shutil.copy2(MASTER_SVG, ASSETS / "singh360-logo-vector.svg")
    shutil.copy2(MASTER_SVG, desktop_svg)

    inkscape = find_inkscape()
    if not inkscape:
        print("ERROR: Inkscape not found — install with: winget install Inkscape.Inkscape", file=sys.stderr)
        return 1

    print(f"Inkscape: {inkscape}")
    export_with_inkscape(inkscape, MASTER_SVG, desktop_eps, "eps")
    export_with_inkscape(inkscape, MASTER_SVG, desktop_pdf, "pdf")
    export_with_inkscape(inkscape, MASTER_SVG, desktop_svg, "svg")

    shutil.copy2(desktop_eps, ASSETS / "singh360-logo-vector.eps")
    shutil.copy2(desktop_pdf, ASSETS / "singh360-logo-vector.pdf")

    validation = validate_outputs(desktop_svg, desktop_eps, desktop_pdf, desktop_svg.read_text(encoding="utf-8"))
    print("\n=== Validation ===")
    for key, val in validation.items():
        print(f"  {key}: {val}")

    print("\n=== Deliverables ===")
    for path in (desktop_eps, desktop_svg, desktop_pdf):
        print(f"  {path} ({round(path.stat().st_size / 1024, 1)} KB)")

    illustrator = Path(r"C:\Program Files\Adobe")
    ai_possible = any(illustrator.glob("Adobe Illustrator*")) if illustrator.exists() else False
    print(f"\n  .ai file: {'skipped — Illustrator not installed' if not ai_possible else 'available'}")

    if validation["has_raster_svg"] or validation["has_text_svg"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
