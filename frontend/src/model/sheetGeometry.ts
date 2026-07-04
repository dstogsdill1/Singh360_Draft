/**
 * Single source of truth for the sheet coordinate system.
 *
 * Every consumer (on-screen editor, Fabric overlay canvas, and the Playwright
 * print/export renderer) must use these exact numbers so that an object placed
 * at a body coordinate in the editor lands at the same place in the exported
 * PDF. Zoom is applied as a CSS transform on the parent, so these pixel
 * dimensions are scale-independent and never change stored object coordinates.
 *
 * Layout (px, at design scale):
 *   SHEET  1632 x 1056  (17" x 11" @ 96dpi)
 *   frame inset 8px, inner border 1px
 *   BODY   = the drawing area above the title block
 *   TITLE BLOCK sits below the body inside the frame
 *
 * The BODY_W/BODY_H below must match the `.sheet-body` and `.np-overlay-layer`
 * CSS box in sheet.css and the Fabric canvas in CanvasEditor.tsx.
 */
export const SHEET_W = 1632;
export const SHEET_H = 1056;

// Printable drawing body (matches .sheet-body in sheet.css).
export const BODY_W = 1598;
export const BODY_H = 866;

// Body offset from the sheet's top-left (frame inset + inner padding).
export const BODY_LEFT = 17;
export const BODY_TOP = 17;

// Title block occupies the strip below the body.
export const TITLE_BLOCK_H = 142;

// Design grid cell sizes in body pixels (0.25" ≈ 24px at this design scale).
export const GRID_SIZES: Record<string, number> = {
  '0.125in': 12,
  '0.25in': 24,
  '0.5in': 48,
  '1in': 96,
};
export const DEFAULT_GRID = 48;
