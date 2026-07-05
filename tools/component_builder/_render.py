"""_render.py -- black/white symbol rendering for the component builder.

Two families of output, both black-and-white and both derived from *real* data
(never a bare placeholder rectangle):

1. Image-derived variants from a curated source image:
   grayscale, highcontrast, nobg (transparent bg), edges, silhouette, outline,
   lineart (cleaned technical line-art).

2. Procedural device symbols drawn from catalog geometry (terminal counts,
   ports, template family) for rows that have a specific templateType. These
   preserve terminal rows, screens, ports and the equipment's characteristic
   shape, so a controller looks like a controller and a contactor looks like a
   contactor.
"""
from __future__ import annotations

from pathlib import Path

try:
    import numpy as np  # type: ignore
    HAVE_NUMPY = True
except Exception:  # pragma: no cover
    HAVE_NUMPY = False

try:
    import cv2  # type: ignore
    HAVE_CV2 = True
except Exception:  # pragma: no cover
    HAVE_CV2 = False

# Variant sets by category family. Logos keep the source image and only get a
# light grayscale/high-contrast pass (no destructive silhouette/edges).
IMAGE_VARIANTS_DEFAULT = [
    "grayscale", "highcontrast", "nobg", "edges", "silhouette", "outline", "lineart",
]
IMAGE_VARIANTS_LOGO = ["grayscale", "highcontrast"]

ALL_IMAGE_VARIANTS = [
    "grayscale", "highcontrast", "nobg", "edges", "silhouette", "outline", "lineart",
]


def variants_for_category(category: str) -> list[str]:
    if (category or "").lower() == "logos":
        return list(IMAGE_VARIANTS_LOGO)
    return list(IMAGE_VARIANTS_DEFAULT)


# ---------------------------------------------------------------------------
# Image-derived variants
# ---------------------------------------------------------------------------
def _fit(im, max_size: int):
    from PIL import Image  # type: ignore

    w, h = im.size
    if max(w, h) <= max_size:
        return im
    s = max_size / float(max(w, h))
    return im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)


def _foreground_mask(rgb, white_thresh: int = 244):
    lum = rgb[..., :3].mean(axis=2)
    return lum < white_thresh


def generate_image_variants(src_path: Path, out_dir: Path, variants: list[str],
                            max_size: int, replace: bool) -> list[dict]:
    """Write requested variants. Returns list of {variant, path} written."""
    from PIL import Image, ImageFilter, ImageOps  # type: ignore

    written: list[dict] = []
    try:
        im = Image.open(src_path)
    except Exception:
        return written
    im = im.convert("RGBA")
    im = _fit(im, max_size)
    out_dir.mkdir(parents=True, exist_ok=True)
    rgba = np.array(im) if HAVE_NUMPY else None
    gray = ImageOps.grayscale(im.convert("RGB"))

    def save(name: str, img) -> None:
        target = out_dir / f"{name}.png"
        if target.exists() and not replace:
            written.append({"variant": name, "path": target})
            return
        img.save(target)
        written.append({"variant": name, "path": target})

    if "grayscale" in variants:
        save("grayscale", gray)

    if "highcontrast" in variants:
        hc = ImageOps.autocontrast(gray, cutoff=2)
        save("highcontrast", hc)

    mask = _foreground_mask(rgba) if HAVE_NUMPY else None

    if "nobg" in variants and HAVE_NUMPY:
        out = rgba.copy()
        out[..., 3] = np.where(mask, 255, 0).astype("uint8")
        save("nobg", Image.fromarray(out, "RGBA"))

    if "edges" in variants:
        if HAVE_CV2 and HAVE_NUMPY:
            g = np.array(gray)
            e = cv2.Canny(g, 60, 160)
            save("edges", Image.fromarray(255 - e))
        else:
            e = ImageOps.autocontrast(gray).filter(ImageFilter.FIND_EDGES)
            e = ImageOps.invert(e).point(lambda p: 0 if p < 170 else 255)
            save("edges", e)

    if "lineart" in variants:
        # cleaned technical line-art: crisp black strokes on white, denoised
        base = ImageOps.autocontrast(gray, cutoff=1)
        edge = base.filter(ImageFilter.FIND_EDGES)
        edge = ImageOps.invert(edge)
        edge = edge.filter(ImageFilter.MedianFilter(size=3))
        edge = edge.point(lambda p: 0 if p < 165 else 255)
        save("lineart", edge)

    if ("silhouette" in variants or "outline" in variants) and HAVE_NUMPY:
        sil = np.zeros(rgba.shape[:2] + (4,), dtype="uint8")
        sil[mask] = (0, 0, 0, 255)
        sil_img = Image.fromarray(sil, "RGBA")
        if "silhouette" in variants:
            save("silhouette", sil_img)
        if "outline" in variants:
            alpha = sil_img.split()[3]
            edge = alpha.filter(ImageFilter.FIND_EDGES)
            # thicken the outline slightly for visibility
            edge = edge.filter(ImageFilter.MaxFilter(3))
            black = Image.new("RGBA", sil_img.size, (0, 0, 0, 255))
            black.putalpha(edge)
            save("outline", black)

    return written


# ---------------------------------------------------------------------------
# Procedural symbols
# ---------------------------------------------------------------------------
def _canvas(w: int, h: int):
    from PIL import Image, ImageDraw  # type: ignore

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _font(size: int):
    from PIL import ImageFont  # type: ignore

    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_center(draw, box, text, fill=(0, 0, 0, 255), size=None):
    x0, y0, x1, y1 = box
    fnt = _font(size or max(12, int((y1 - y0) * 0.5)))
    try:
        tb = draw.textbbox((0, 0), text, font=fnt)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
    except Exception:
        tw, th = draw.textlength(text, font=fnt), size or 12
    draw.text(((x0 + x1 - tw) / 2, (y0 + y1 - th) / 2), text, font=fnt, fill=fill)


def _rect(draw, x0, y0, x1, y1, lw, fill=None):
    """Rectangle with coordinates normalized so x1>=x0 and y1>=y0."""
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    draw.rectangle([xa, ya, xb, yb], outline=(0, 0, 0, 255), width=lw, fill=fill)


def _terminal_row(draw, x0, x1, y, count, lw, budget, up=True):
    """Draw `count` terminal ticks with small square pads along a horizontal edge.

    `budget` is the available margin outside the body edge; ticks stay within it.
    """
    if not count or count <= 0:
        return
    step = (x1 - x0) / (count + 1)
    pad = int(min(step * 0.28, budget * 0.42))
    pad = max(3, pad)
    leg = int(min(pad * 1.6, budget * 0.85))
    for i in range(1, count + 1):
        cx = x0 + step * i
        y2 = y - leg if up else y + leg
        draw.line([(cx, y), (cx, y2)], fill=(0, 0, 0, 255), width=lw)
        _rect(draw, cx - pad / 2, y2, cx + pad / 2,
              (y2 - pad) if up else (y2 + pad), lw)


def _port_col(draw, y0, y1, x, count, lw, budget, left=True):
    if not count or count <= 0:
        return
    step = (y1 - y0) / (count + 1)
    leg = int(min(max(6, step * 0.4), budget * 0.85))
    r = max(3, leg // 3)
    for i in range(1, count + 1):
        cy = y0 + step * i
        x2 = x - leg if left else x + leg
        draw.line([(x, cy), (x2, cy)], fill=(0, 0, 0, 255), width=lw)
        draw.ellipse([x2 - r, cy - r, x2 + r, cy + r], outline=(0, 0, 0, 255), width=lw)


def _device_outline(draw, W, H, top, bottom, left, right, lw, screen=False):
    mx = max(int(W * 0.12), 8)
    my = max(int(H * 0.12), 8)
    x0, y0, x1, y1 = mx, my, W - mx, H - my
    try:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=max(2, int(min(W, H) * 0.04)),
                               outline=(0, 0, 0, 255), width=lw)
    except Exception:
        _rect(draw, x0, y0, x1, y1, lw)
    if screen:
        body_h = y1 - y0
        sm = max(4, int(min(W, H) * 0.05))
        sy1 = y0 + sm + int(body_h * 0.45)
        _rect(draw, x0 + sm, y0 + sm, x1 - sm, sy1, lw)
    _terminal_row(draw, x0, x1, y0, top, lw, my, up=True)
    _terminal_row(draw, x0, x1, y1, bottom, lw, my, up=False)
    _port_col(draw, y0, y1, x0, left, lw, mx, left=True)
    _port_col(draw, y0, y1, x1, right, lw, mx, left=False)
    return (x0, y0, x1, y1)


def _contactor(draw, W, H, top, bottom, lw):
    x0, y0, x1, y1 = int(W * 0.24), int(H * 0.2), int(W * 0.76), int(H * 0.8)
    draw.rectangle([x0, y0, x1, y1], outline=(0, 0, 0, 255), width=lw)
    top = top or 3
    bottom = bottom or 3
    budget = int(H * 0.16)
    _terminal_row(draw, x0, x1, y0, top, lw, budget, up=True)
    _terminal_row(draw, x0, x1, y1, bottom, lw, budget, up=False)
    # coil A1/A2 marks on the side
    cy = (y0 + y1) // 2
    draw.line([(x1, cy - 12), (x1 + int(W * 0.08), cy - 12)], fill=(0, 0, 0, 255), width=lw)
    draw.line([(x1, cy + 12), (x1 + int(W * 0.08), cy + 12)], fill=(0, 0, 0, 255), width=lw)
    return (x0, y0, x1, y1)


def _breaker(draw, W, H, lw):
    x0, y0, x1, y1 = int(W * 0.34), int(H * 0.18), int(W * 0.66), int(H * 0.82)
    draw.rectangle([x0, y0, x1, y1], outline=(0, 0, 0, 255), width=lw)
    cx = (x0 + x1) // 2
    draw.line([(cx, y0), (cx, y0 - int(H * 0.1))], fill=(0, 0, 0, 255), width=lw)
    draw.line([(cx, y1), (cx, y1 + int(H * 0.1))], fill=(0, 0, 0, 255), width=lw)
    # toggle lever
    draw.line([(cx, int(H * 0.4)), (cx + int(W * 0.12), int(H * 0.28))],
              fill=(0, 0, 0, 255), width=lw)
    draw.ellipse([cx - 6, int(H * 0.4) - 6, cx + 6, int(H * 0.4) + 6],
                 fill=(0, 0, 0, 255))
    return (x0, y0, x1, y1)


def _power_supply(draw, W, H, lw):
    x0, y0, x1, y1 = int(W * 0.22), int(H * 0.24), int(W * 0.78), int(H * 0.76)
    draw.rectangle([x0, y0, x1, y1], outline=(0, 0, 0, 255), width=lw)
    for i in range(1, 5):  # louvers
        yy = y0 + (y1 - y0) * i / 6
        draw.line([(x0 + 10, yy), (x0 + int(W * 0.18), yy)], fill=(0, 0, 0, 255), width=lw)
    _terminal_row(draw, x0, x1, y1, 4, lw, int(H * 0.18), up=False)
    return (x0, y0, x1, y1)


def _terminal_block(draw, W, H, count, lw):
    count = count or 6
    y0, y1 = int(H * 0.38), int(H * 0.62)
    x0, x1 = int(W * 0.12), int(W * 0.88)
    step = (x1 - x0) / count
    for i in range(count):
        cx0 = x0 + step * i
        draw.rectangle([cx0, y0, cx0 + step * 0.86, y1], outline=(0, 0, 0, 255), width=lw)
        ccx = cx0 + step * 0.43
        draw.ellipse([ccx - 4, (y0 + y1) / 2 - 4, ccx + 4, (y0 + y1) / 2 + 4],
                     outline=(0, 0, 0, 255), width=lw)
    return (x0, y0, x1, y1)


def _enclosure(draw, W, H, lw):
    x0, y0, x1, y1 = int(W * 0.16), int(H * 0.14), int(W * 0.84), int(H * 0.86)
    draw.rectangle([x0, y0, x1, y1], outline=(0, 0, 0, 255), width=lw)
    draw.rectangle([x0 + 10, y0 + 10, x1 - 10, y1 - 10], outline=(0, 0, 0, 255), width=max(1, lw - 1))  # door seam
    r = max(4, int(W * 0.015))
    for (sx, sy) in [(x0 + 20, y0 + 20), (x1 - 20, y0 + 20), (x0 + 20, y1 - 20), (x1 - 20, y1 - 20)]:
        draw.ellipse([sx - r, sy - r, sx + r, sy + r], outline=(0, 0, 0, 255), width=lw)  # corner screws
    # knockouts on top edge
    for i in range(1, 4):
        kx = x0 + (x1 - x0) * i / 4
        draw.ellipse([kx - r, y0 - r, kx + r, y0 + r], outline=(0, 0, 0, 255), width=lw)
    # label field
    lx0, lx1 = x0 + int(W * 0.12), x1 - int(W * 0.12)
    ly0, ly1 = int(H * 0.44), int(H * 0.56)
    draw.rectangle([lx0, ly0, lx1, ly1], outline=(0, 0, 0, 255), width=lw)
    return (lx0, ly0, lx1, ly1)


def _sensor(draw, W, H, lw):
    cx, cy, r = W // 2, int(H * 0.42), int(W * 0.2)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 0, 0, 255), width=lw)
    draw.line([(cx, cy + r), (cx, cy + r + int(H * 0.18))], fill=(0, 0, 0, 255), width=lw)
    return (cx - r, cy - r, cx + r, cy + r)


def _fan(draw, W, H, lw):
    cx, cy, r = W // 2, H // 2, int(W * 0.28)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 0, 0, 255), width=lw)
    import math

    for a in range(0, 360, 90):
        rad = math.radians(a)
        draw.line([(cx, cy), (cx + r * 0.8 * math.cos(rad), cy + r * 0.8 * math.sin(rad))],
                  fill=(0, 0, 0, 255), width=lw)
        draw.arc([cx - r, cy - r, cx + r, cy + r], a, a + 55, fill=(0, 0, 0, 255), width=lw)
    return (cx - r, cy - r, cx + r, cy + r)


def _pump(draw, W, H, lw):
    cx, cy, r = W // 2, H // 2, int(W * 0.26)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 0, 0, 255), width=lw)
    draw.polygon([(cx - r * 0.4, cy - r * 0.5), (cx - r * 0.4, cy + r * 0.5),
                  (cx + r * 0.6, cy)], outline=(0, 0, 0, 255), width=lw)
    return (cx - r, cy - r, cx + r, cy + r)


def _valve(draw, W, H, lw, closed=False):
    cx, cy = W // 2, H // 2
    w, h = int(W * 0.24), int(H * 0.2)
    left = [(cx - w, cy - h), (cx - w, cy + h), (cx, cy)]
    right = [(cx + w, cy - h), (cx + w, cy + h), (cx, cy)]
    fill = (0, 0, 0, 255) if closed else None
    draw.polygon(left, outline=(0, 0, 0, 255), width=lw, fill=fill)
    draw.polygon(right, outline=(0, 0, 0, 255), width=lw, fill=fill)
    return (cx - w, cy - h, cx + w, cy + h)


def _din_rail(draw, W, H, lw):
    y0, y1 = int(H * 0.42), int(H * 0.58)
    x0, x1 = int(W * 0.08), int(W * 0.92)
    # top-hat profile
    draw.line([(x0, y1), (x0, y0 + 6), (x0 + 14, y0), (x1 - 14, y0), (x1, y0 + 6), (x1, y1)],
              fill=(0, 0, 0, 255), width=lw, joint="curve")
    for i in range(1, 12):  # slots
        sx = x0 + (x1 - x0) * i / 12
        draw.line([(sx, y0 + 4), (sx, y0 + (y1 - y0) * 0.5)], fill=(0, 0, 0, 255), width=max(1, lw - 1))
    return (x0, y0, x1, y1)


def _alarm_strobe(draw, W, H, lw):
    import math

    cx = W // 2
    bx0, bx1, by0, by1 = int(W * 0.36), int(W * 0.64), int(H * 0.5), int(H * 0.74)
    draw.rectangle([bx0, by0, bx1, by1], outline=(0, 0, 0, 255), width=lw)  # base
    dr = int(W * 0.16)
    draw.arc([cx - dr, by0 - dr, cx + dr, by0 + dr], 180, 360, fill=(0, 0, 0, 255), width=lw)  # dome
    for a in (200, 235, 305, 340):  # radiating light lines
        rad = math.radians(a)
        draw.line([(cx + dr * math.cos(rad), by0 + dr * math.sin(rad)),
                   (cx + dr * 1.7 * math.cos(rad), by0 + dr * 1.7 * math.sin(rad))],
                  fill=(0, 0, 0, 255), width=lw)
    return (bx0, by0, bx1, by1)


def procedural_symbol(row: dict, out_path: Path, size: int = 512) -> Path | None:
    """Draw a template-specific B/W symbol from catalog geometry."""
    template = (row.get("templateType") or "").strip()
    wu = row.get("widthUnits") or 4
    hu = row.get("heightUnits") or 3
    aspect = max(0.55, min(2.0, wu / hu)) if (wu and hu) else 1.3
    if aspect >= 1:
        W, H = size, int(size / aspect)
    else:
        W, H = int(size * aspect), size
    lw = max(2, max(W, H) // 150)
    label = row.get("defaultLabel") or row.get("displayName") or ""
    top = row.get("topTerminals")
    bottom = row.get("bottomTerminals")
    left = row.get("leftPorts")
    right = row.get("rightPorts")

    img, draw = _canvas(W, H)
    label_box = None

    if template == "controller_tdb":
        label_box = _device_outline(draw, W, H, top, bottom, left, right, lw, screen=True)
        label_box = (label_box[0], (label_box[1] + label_box[3]) // 2, label_box[2], label_box[3])
    elif template in {"stepper_module", "mini_io", "probe_board", "module_terminal_row"}:
        label_box = _device_outline(draw, W, H, top or 8, bottom or 8, left, right, lw)
    elif template == "contactor":
        label_box = _contactor(draw, W, H, top, bottom, lw)
    elif template == "breaker":
        label_box = _breaker(draw, W, H, lw)
    elif template == "power_supply":
        label_box = _power_supply(draw, W, H, lw)
    elif template == "terminal_block":
        label_box = _terminal_block(draw, W, H, row.get("widthUnits"), lw)
    elif template == "enclosure":
        label_box = _enclosure(draw, W, H, lw)
    elif template == "sensor":
        label_box = _sensor(draw, W, H, lw)
    elif template == "fan":
        label_box = _fan(draw, W, H, lw)
    elif template == "pump":
        label_box = _pump(draw, W, H, lw)
    elif template == "valve":
        closed = "closed" in (row.get("displayName", "").lower())
        label_box = _valve(draw, W, H, lw, closed=closed)
    elif template == "din_rail":
        label_box = _din_rail(draw, W, H, lw)
    elif template == "alarm_strobe":
        label_box = _alarm_strobe(draw, W, H, lw)
    else:
        return None  # not specific enough -> caller marks needsReview

    if label and label_box:
        short = label if len(label) <= 14 else label[:13] + "\u2026"
        _text_center(draw, label_box, short, size=max(14, int(W * 0.05)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
