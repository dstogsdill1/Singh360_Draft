/**
 * Singh360 connector line presets — a single source of truth shared by the
 * Draw-tab preset buttons and the "Insert Legend" grouped object so the legend
 * always matches the strokes that get drawn.
 *
 * These drawings may print in BLACK AND WHITE, so every preset is distinguished
 * by BOTH color AND a line style + weight that still reads in grayscale
 * (solid/dashed/dotted/dash-dot/long-dash and thin/medium/heavy widths).
 */
export type DashStyle = 'solid' | 'dashed' | 'dotted' | 'dash-dot' | 'long-dash';

export interface ConnectorPreset {
  id: string;
  label: string;
  stroke: string;
  dash: DashStyle;
  strokeWidth: number;
  arrowEnd?: boolean;
}

export const CONNECTOR_PRESETS: ConnectorPreset[] = [
  // color + grayscale-safe style/weight pairing (no two share the same style+weight)
  { id: 'cat6', label: 'CAT6', stroke: '#00a651', dash: 'solid', strokeWidth: 2 },
  { id: 'fiber', label: 'Fiber', stroke: '#f28c28', dash: 'long-dash', strokeWidth: 2 },
  { id: 'bacnet', label: 'BACnet', stroke: '#12539b', dash: 'dashed', strokeWidth: 2 },
  { id: 'canbus', label: 'CANbus', stroke: '#e0a800', dash: 'dash-dot', strokeWidth: 2 },
  { id: 'line-voltage', label: 'Line Voltage', stroke: '#111111', dash: 'solid', strokeWidth: 3 },
  { id: 'control', label: 'Control Wiring', stroke: '#888888', dash: 'dashed', strokeWidth: 1 },
  { id: 'power', label: 'Power', stroke: '#111111', dash: 'solid', strokeWidth: 5 },
  { id: 'reference', label: 'Existing / Reference', stroke: '#888888', dash: 'dotted', strokeWidth: 2 },
];

/** Convert a dash style into a Fabric strokeDashArray for the given width. */
export function dashArray(dash: DashStyle, width: number): number[] | undefined {
  switch (dash) {
    case 'dashed':
      return [Math.max(6, width * 3), Math.max(4, width * 2)];
    case 'long-dash':
      return [Math.max(14, width * 7), Math.max(6, width * 3)];
    case 'dotted':
      return [width, Math.max(3, width * 2)];
    case 'dash-dot':
      return [Math.max(8, width * 4), width * 2, width, width * 2];
    default:
      return undefined;
  }
}
