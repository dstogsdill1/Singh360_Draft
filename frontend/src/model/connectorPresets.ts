/**
 * Singh360 connector line presets — a single source of truth shared by the
 * Draw-tab preset buttons and the "Insert Legend" grouped object so the legend
 * always matches the strokes that get drawn.
 */
export type DashStyle = 'solid' | 'dashed' | 'dotted' | 'dash-dot';

export interface ConnectorPreset {
  id: string;
  label: string;
  stroke: string;
  dash: DashStyle;
  strokeWidth: number;
  arrowEnd?: boolean;
}

export const CONNECTOR_PRESETS: ConnectorPreset[] = [
  { id: 'cat6', label: 'CAT6', stroke: '#00a651', dash: 'solid', strokeWidth: 2 },
  { id: 'fiber', label: 'Fiber', stroke: '#f28c28', dash: 'dashed', strokeWidth: 2 },
  { id: 'bacnet', label: 'BACnet', stroke: '#12539b', dash: 'dashed', strokeWidth: 2 },
  { id: 'canbus', label: 'CANbus', stroke: '#f2c200', dash: 'dash-dot', strokeWidth: 2 },
  { id: 'line-voltage', label: 'Line Voltage', stroke: '#111111', dash: 'solid', strokeWidth: 2 },
  { id: 'control', label: 'Control Wiring', stroke: '#888888', dash: 'solid', strokeWidth: 2 },
  { id: 'power', label: 'Power', stroke: '#111111', dash: 'solid', strokeWidth: 3 },
  { id: 'reference', label: 'Reference', stroke: '#888888', dash: 'dashed', strokeWidth: 2 },
];

/** Convert a dash style into a Fabric strokeDashArray for the given width. */
export function dashArray(dash: DashStyle, width: number): number[] | undefined {
  switch (dash) {
    case 'dashed':
      return [Math.max(6, width * 3), Math.max(4, width * 2)];
    case 'dotted':
      return [width, Math.max(3, width * 2)];
    case 'dash-dot':
      return [Math.max(8, width * 4), width * 2, width, width * 2];
    default:
      return undefined;
  }
}
