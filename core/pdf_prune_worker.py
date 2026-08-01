"""Memory-isolated worker for vector PDF crop pruning."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import time
from pathlib import Path

import fitz
import pikepdf


_PATH_OPERATORS = {"m", "l", "c", "v", "y", "h", "re"}
_PAINT_OPERATORS = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*", "n"}


def _multiply_matrix(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    )


def _path_signature(path: list[pikepdf.ContentStreamInstruction]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (str(instruction.operator), tuple(str(value) for value in instruction.operands))
        for instruction in path
    )


def _deduplicate_redundant_strokes(source: Path, page_index: int, output: Path) -> dict[str, int]:
    """Remove exact repeat stroke paths from pathological flat CAD streams.

    Some born-digital drawing PDFs contain hundreds of thousands of identical
    opaque strokes at the same coordinates. Repainting the same vector path does
    not change ideal PDF output, but it makes Chromium and Acrobat process every
    duplicate. This retains every distinct path and all text/images.
    """
    with pikepdf.Pdf.open(source) as document:
        page = document.pages[page_index]
        unsafe_graphics_states: set[str] = set()
        resources = page.get("/Resources", pikepdf.Dictionary())
        for name, graphics_state in resources.get("/ExtGState", pikepdf.Dictionary()).items():
            stroke_alpha = float(graphics_state.get("/CA", 1.0))
            blend_mode = str(graphics_state.get("/BM", "/Normal"))
            if stroke_alpha < 1.0 or blend_mode != "/Normal":
                unsafe_graphics_states.add(str(name))
        operations = pikepdf.parse_content_stream(page)
        retained: list[pikepdf.ContentStreamInstruction] = []
        path: list[pikepdf.ContentStreamInstruction] = []
        clipping_operator: str | None = None
        seen: collections.Counter[tuple[object, ...]] = collections.Counter()
        removed = 0
        state: dict[str, object] = {
            "ctm": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            "width": "1",
            "stroke": ("G", ("0",)),
            "cap": "0",
            "join": "0",
            "dash": None,
            "graphicsState": None,
            "clip": None,
        }
        stack: list[dict[str, object]] = []
        for instruction in operations:
            operator = str(instruction.operator)
            if operator in _PATH_OPERATORS:
                path.append(instruction)
                continue
            if operator in {"W", "W*"}:
                path.append(instruction)
                clipping_operator = operator
                continue
            if operator in _PAINT_OPERATORS:
                if (
                    operator == "S"
                    and clipping_operator is None
                    and path
                    and state["graphicsState"] not in unsafe_graphics_states
                ):
                    key = (
                        _path_signature(path),
                        state["ctm"],
                        state["width"],
                        state["stroke"],
                        state["cap"],
                        state["join"],
                        state["dash"],
                        state["graphicsState"],
                        state["clip"],
                    )
                    seen[key] += 1
                    if seen[key] > 1:
                        removed += 1
                    else:
                        retained.extend(path)
                        retained.append(instruction)
                else:
                    retained.extend(path)
                    retained.append(instruction)
                if clipping_operator is not None:
                    clip_description = (
                        str(state["clip"]),
                        clipping_operator,
                        _path_signature(path),
                    )
                    state["clip"] = hashlib.sha256(repr(clip_description).encode()).hexdigest()[:20]
                path = []
                clipping_operator = None
                continue

            if path:
                retained.extend(path)
                path = []
                clipping_operator = None
            if operator == "q":
                stack.append(state.copy())
            elif operator == "Q":
                state = stack.pop() if stack else state
            elif operator == "cm":
                matrix = tuple(float(value) for value in instruction.operands)
                state["ctm"] = tuple(
                    round(value, 8)
                    for value in _multiply_matrix(state["ctm"], matrix)  # type: ignore[arg-type]
                )
            elif operator == "w":
                state["width"] = str(instruction.operands[0])
            elif operator in {"G", "RG", "K", "CS", "SC", "SCN"}:
                state["stroke"] = (operator, tuple(str(value) for value in instruction.operands))
            elif operator == "J":
                state["cap"] = str(instruction.operands[0])
            elif operator == "j":
                state["join"] = str(instruction.operands[0])
            elif operator == "d":
                state["dash"] = tuple(str(value) for value in instruction.operands)
            elif operator == "gs":
                state["graphicsState"] = str(instruction.operands[0])
            retained.append(instruction)

        if path:
            retained.extend(path)
        page.Contents = document.make_stream(pikepdf.unparse_content_stream(retained))
        document.save(output, compress_streams=True, recompress_flate=True)
        return {
            "sourceOperations": len(operations),
            "retainedOperations": len(retained),
            "deduplicatedVectorStrokes": removed,
            "uniqueStrokeSignatures": len(seen),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = [float(value) for value in args.clip.split(",")]
    if len(values) != 4:
        raise ValueError("clip requires four coordinates")
    started = time.perf_counter()
    source = fitz.open(args.source)
    filtered_source = args.output.with_name(f".{args.output.stem}.filtered-source.pdf")
    deduplication: dict[str, int] = {
        "sourceOperations": 0,
        "retainedOperations": 0,
        "deduplicatedVectorStrokes": 0,
        "uniqueStrokeSignatures": 0,
    }
    try:
        if args.page < 0 or args.page >= source.page_count:
            raise ValueError("source page is out of range")
        source.select([args.page])
        page = source[0]
        media = fitz.Rect(page.rect)
        clip = fitz.Rect(*values) & media
        if clip.is_empty or clip.width <= 0 or clip.height <= 0:
            raise ValueError("source crop is empty")
        crop_fraction = clip.get_area() / max(1.0, media.get_area())
        decoded_content_bytes = sum(
            len(source.xref_stream(xref) or b"")
            for xref in (page.get_contents() or [])
        )
        should_deduplicate = (
            crop_fraction >= 0.10
            and decoded_content_bytes >= 10_000_000
            and not page.get_xobjects()
        )
        if should_deduplicate:
            source.close()
            deduplication = _deduplicate_redundant_strokes(
                args.source,
                args.page,
                filtered_source,
            )
            source = fitz.open(filtered_source)
            source.select([args.page])
            page = source[0]
            media = fitz.Rect(page.rect)
            clip = fitz.Rect(*values) & media
        page.clip_to_rect(clip)
        page.set_cropbox(clip)
        page.clean_contents(sanitize=True)
        source.save(
            args.output,
            garbage=4,
            clean=True,
            deflate=True,
            deflate_images=True,
            deflate_fonts=True,
        )
        audit = {
            "sourcePageArea": round(media.get_area(), 3),
            "cropArea": round(clip.get_area(), 3),
            "cropFraction": round(clip.get_area() / max(1.0, media.get_area()), 6),
            "prepareMs": round((time.perf_counter() - started) * 1000.0, 2),
            **deduplication,
        }
    finally:
        source.close()
        filtered_source.unlink(missing_ok=True)
    audit["outputBytes"] = args.output.stat().st_size
    print(json.dumps(audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
