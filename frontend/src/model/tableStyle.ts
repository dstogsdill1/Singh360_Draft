// Canonical Singh360 table style map — the single source of truth for workbook
// source preview and normalized output rendering (Milestone 4B, Phase A).
//
// These colors must match the CSS in styles/sheet.css and any server-side
// rendering. Do not fork these values elsewhere; import from here.

export const TABLE_COLORS = {
  /** Gold/orange controller / section header bar. */
  controllerHeader: '#FFC000',
  /** Dark sheet title / header bar. */
  darkHeader: '#20252B',
  /** Gray column header. */
  columnHeader: '#D9D9D9',
  /** Alternating body row light gray. */
  altRow: '#F4F6F8',
  /** Warning / verify highlight. */
  verify: '#FFF2A8',
  /** Issue / stop highlight. */
  stop: '#F8C9CE',
  /** Pass / done highlight. */
  done: '#C6E7C6',
} as const;

/** Named highlight swatches offered in the table right-click menu. */
export const HIGHLIGHT_SWATCHES: Array<{ label: string; color: string }> = [
  { label: 'Verify (Yellow)', color: TABLE_COLORS.verify },
  { label: 'Controller (Gold)', color: TABLE_COLORS.controllerHeader },
  { label: 'Done (Green)', color: TABLE_COLORS.done },
  { label: 'Stop (Red)', color: TABLE_COLORS.stop },
  { label: 'Column (Gray)', color: TABLE_COLORS.columnHeader },
];
