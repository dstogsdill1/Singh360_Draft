"""Safe SVG delivery helpers.

Fabric and browser ``HTMLImageElement`` loading need explicit intrinsic SVG
dimensions.  The component library's V39/V40 markers have a square viewBox but
were generated without width/height, so different browser paths inferred
incompatible image bounds.  Normalize the served bytes without modifying the
protected component-library files on disk.
"""
from __future__ import annotations

import re


_SVG_TAG_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_VIEWBOX_RE = re.compile(
    r"""(?<!\S)viewBox\s*=\s*(?P<quote>["'])
        \s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?[\s,]+
        [-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?[\s,]+
        (?P<width>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)[\s,]+
        (?P<height>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)
        \s*(?P=quote)""",
    re.IGNORECASE | re.VERBOSE,
)
_WIDTH_RE = re.compile(r"(?<!\S)width\s*=", re.IGNORECASE)
_HEIGHT_RE = re.compile(r"(?<!\S)height\s*=", re.IGNORECASE)


def _dimension(value: str) -> str | None:
    try:
        number = float(value)
    except ValueError:
        return None
    if not (number > 0):
        return None
    return str(int(number)) if number.is_integer() else f"{number:g}"


def add_intrinsic_svg_dimensions(payload: bytes) -> bytes:
    """Add missing numeric width/height from the root SVG viewBox.

    Invalid, non-UTF-8, already-sized, or viewBox-less content is returned byte
    for byte unchanged.
    """

    has_bom = payload.startswith(b"\xef\xbb\xbf")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return payload

    tag_match = _SVG_TAG_RE.search(text)
    if tag_match is None:
        return payload
    tag = tag_match.group(0)
    has_width = _WIDTH_RE.search(tag) is not None
    has_height = _HEIGHT_RE.search(tag) is not None
    if has_width and has_height:
        return payload

    viewbox = _VIEWBOX_RE.search(tag)
    if viewbox is None:
        return payload
    width = _dimension(viewbox.group("width"))
    height = _dimension(viewbox.group("height"))
    if width is None or height is None:
        return payload

    attributes = ""
    if not has_width:
        attributes += f' width="{width}"'
    if not has_height:
        attributes += f' height="{height}"'
    normalized_tag = tag[:4] + attributes + tag[4:]
    normalized = text[: tag_match.start()] + normalized_tag + text[tag_match.end() :]
    encoded = normalized.encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if has_bom else encoded
