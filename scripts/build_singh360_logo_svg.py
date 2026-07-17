"""Build pixel-exact Singh360 logo SVG from source PNG."""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
SRC = Path(
    r"C:\Users\DarrinStogsdill\.cursor\projects\c-Users-DarrinStogsdill-OneDrive-Homeland-Development-Services-LLC-Desktop-Singh360-SmartDraw\assets\c__Users_DarrinStogsdill_AppData_Roaming_Cursor_User_workspaceStorage_0ed545f4d7188ba4c8364018ac4ac42b_images_singh360-logo-flat-476bd275-3784-4e1c-91e3-9799ec4e9ab0.png"
)
PNG_OUT = ASSETS / "singh360-logo-source.png"
PNG_OUT_BLACK = ASSETS / "singh360-logo-source-black.png"
SVG_EMBED = ASSETS / "singh360-logo.svg"
SVG_EMBED_BLACK = ASSETS / "singh360-logo-black.svg"
SVG_VECTOR = ASSETS / "singh360-logo-vector.svg"
DESKTOP = Path.home() / "OneDrive - Homeland Development Services LLC" / "Desktop"


def composite_on_black(im: Image.Image) -> Image.Image:
    rgba = im.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    bg.paste(rgba, (0, 0), rgba)
    return bg


def png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def write_embedded_svg(
    png_bytes: bytes,
    width: int,
    height: int,
    out: Path,
    *,
    black_background: bool = False,
) -> None:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    bg_rect = '  <rect width="100%" height="100%" fill="#000000"/>\n' if black_background else ""
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="SINGH360">
{bg_rect}  <image width="{width}" height="{height}" xlink:href="data:image/png;base64,{b64}"/>
</svg>
"""
    out.write_text(svg, encoding="utf-8")


def write_traced_svg(src_png: Path, out: Path, logical_w: int, logical_h: int) -> None:
    import vtracer

    im = Image.open(src_png).convert("RGBA")
    up_w, up_h = logical_w * 8, logical_h * 8
    up = im.resize((up_w, up_h), Image.Resampling.LANCZOS)
    tmp = ASSETS / "_singh360_trace_src.png"
    up.save(tmp)
    vtracer.convert_image_to_svg_py(
        str(tmp),
        str(out),
        colormode="color",
        hierarchical="stacked",
        mode="spline",
        filter_speckle=1,
        color_precision=8,
        layer_difference=6,
        corner_threshold=60,
        length_threshold=2,
        max_iterations=10,
        splice_threshold=45,
        path_precision=4,
    )
    tmp.unlink(missing_ok=True)
    svg = out.read_text(encoding="utf-8")
    svg = re.sub(r'width="\d+"', f'width="{logical_w}"', svg, count=1)
    svg = re.sub(r'height="\d+"', f'height="{logical_h}"', svg, count=1)
    svg = svg.replace(f'width="{logical_w * 8}"', f'width="{logical_w}"', 1)
    svg = svg.replace(f'height="{logical_h * 8}"', f'height="{logical_h}"', 1)
    if 'viewBox=' not in svg:
        svg = svg.replace(
            f'width="{logical_w}"',
            f'viewBox="0 0 {logical_w * 8} {logical_h * 8}" width="{logical_w}"',
            1,
        )
    out.write_text(svg, encoding="utf-8")


def resolve_source() -> Path:
    candidates = [
        SRC,
        ASSETS / "singh360-logo-source.png",
        DESKTOP / "singh360-logo-source.png",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise SystemExit("Source PNG missing. Place singh360-logo-source.png in docs/assets/")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    source = resolve_source()

    im = Image.open(source).convert("RGBA")
    w, h = im.size
    transparent_png = png_bytes(im)
    black_png = png_bytes(composite_on_black(im))
    PNG_OUT.write_bytes(transparent_png)
    PNG_OUT_BLACK.write_bytes(black_png)

    write_embedded_svg(transparent_png, w, h, SVG_EMBED, black_background=False)
    write_embedded_svg(black_png, w, h, SVG_EMBED_BLACK, black_background=True)
    write_traced_svg(PNG_OUT, SVG_VECTOR, w, h)

    if DESKTOP.exists():
        for name in (
            "singh360-logo.svg",
            "singh360-logo-black.svg",
            "singh360-logo-vector.svg",
            "singh360-logo-source.png",
        ):
            src = ASSETS / name
            if src.exists():
                (DESKTOP / name).write_bytes(src.read_bytes())
        (DESKTOP / "singh360-logo-flat.svg").write_bytes(SVG_EMBED.read_bytes())

    print(f"Source: {w}x{h}")
    print(f"Transparent SVG:  {SVG_EMBED}")
    print(f"Black-bg SVG:     {SVG_EMBED_BLACK}")
    print(f"Vector trace:     {SVG_VECTOR}")
    print(f"PNG (transparent): {PNG_OUT}")


if __name__ == "__main__":
    main()
