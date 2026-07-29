from __future__ import annotations

import unittest

from core.svg_asset import add_intrinsic_svg_dimensions


class SvgAssetDimensionsTest(unittest.TestCase):
    def test_adds_v39_v40_intrinsic_dimensions_from_viewbox(self) -> None:
        original = (
            b'<?xml version="1.0"?>\n'
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" '
            b'data-renderer="singh360-map-marker-v39"><circle cx="48" cy="48" r="30"/></svg>'
        )
        normalized = add_intrinsic_svg_dimensions(original)
        self.assertIn(b'<svg width="96" height="96"', normalized)
        self.assertIn(b'viewBox="0 0 96 96"', normalized)

    def test_preserves_existing_dimension_and_adds_only_missing_one(self) -> None:
        original = b"<svg width='160' viewBox='0, 0, 160, 96'></svg>"
        normalized = add_intrinsic_svg_dimensions(original)
        self.assertIn(b"<svg height=\"96\" width='160'", normalized)
        self.assertEqual(normalized.count(b"width="), 1)

    def test_already_sized_or_invalid_svg_is_byte_identical(self) -> None:
        sized = b"<svg width='96' height='96' viewBox='0 0 96 96'></svg>"
        no_viewbox = b"<svg><path d='M0 0'/></svg>"
        self.assertIs(add_intrinsic_svg_dimensions(sized), sized)
        self.assertIs(add_intrinsic_svg_dimensions(no_viewbox), no_viewbox)

    def test_preserves_utf8_bom(self) -> None:
        original = b"\xef\xbb\xbf<svg viewBox='0 0 12.5 8'></svg>"
        normalized = add_intrinsic_svg_dimensions(original)
        self.assertTrue(normalized.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b'width="12.5" height="8"', normalized)

    def test_stroke_width_is_not_mistaken_for_intrinsic_width(self) -> None:
        original = b"<svg stroke-width='4' viewBox='0 0 96 96'></svg>"
        normalized = add_intrinsic_svg_dimensions(original)
        self.assertIn(b'<svg width="96" height="96" stroke-width=', normalized)


if __name__ == "__main__":
    unittest.main()
