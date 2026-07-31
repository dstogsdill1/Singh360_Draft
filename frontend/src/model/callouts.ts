import type {
  CalloutEntry,
  CalloutFamily,
  CalloutLayout,
  CalloutMarkerShape,
  CalloutSetConfig,
} from './types';

const FAMILIES = new Set<CalloutFamily>(['round', 'square', 'block']);
const LAYOUTS = new Set<CalloutLayout>(['horizontal', 'vertical', 'grid']);
const MARKER_SHAPES = new Set<CalloutMarkerShape>(['round', 'square', 'pill', 'none']);
const MAX_CALLOUT_ROWS = 200;

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function numberValue(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function integerValue(value: unknown, fallback: number, min: number, max: number): number {
  return Math.round(numberValue(value, fallback, min, max));
}

function option<T extends string>(value: unknown, choices: Set<T>, fallback: T): T {
  return typeof value === 'string' && choices.has(value as T) ? value as T : fallback;
}

function hasOwn(source: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, key);
}

export function emptyCalloutEntry(): CalloutEntry {
  return {
    callout: '',
    label: '',
    description: '',
    text: '',
  };
}

export function cloneCalloutEntries(entries: CalloutEntry[]): CalloutEntry[] {
  return entries.map((entry) => ({ ...entry }));
}

export function calloutFamilyLabel(family: CalloutFamily): string {
  if (family === 'round') return 'Round Callouts';
  if (family === 'square') return 'Square Callouts';
  return 'Callout Blocks / Lists';
}

export function defaultCalloutSetConfig(family: CalloutFamily): CalloutSetConfig {
  return {
    kind: 'callout-set',
    family,
    setName: family === 'block'
      ? 'Equipment Callouts'
      : family === 'round' ? 'Round Callouts' : 'Square Callouts',
    title: family === 'block' ? 'CALLOUTS' : '',
    entries: [emptyCalloutEntry()],
    markerShape: family === 'round' ? 'round' : 'square',
    layout: family === 'block' ? 'vertical' : 'horizontal',
    gridColumns: family === 'block' ? 1 : 10,
    markerSize: family === 'block' ? 42 : 72,
    spacing: family === 'block' ? 8 : 12,
    fill: '#ffffff',
    stroke: '#111827',
    textColor: '#111827',
  };
}

/**
 * Normalize old and current saved callout rows without trimming cell values.
 *
 * Legacy rows were `{label, text}` where `label` was drawn inside the marker
 * and `text` was the adjacent description. They are upgraded losslessly to
 * `{callout, label, description}` when a project is opened.
 */
export function normalizeCalloutEntries(value: unknown): CalloutEntry[] {
  const raw = Array.isArray(value) ? value : [];
  const entries = raw.slice(0, MAX_CALLOUT_ROWS).map((item) => {
    if (typeof item === 'string') {
      return {
        callout: item,
        label: '',
        description: '',
        text: '',
      };
    }
    const source = record(item);
    const isCurrent = hasOwn(source, 'callout') || hasOwn(source, 'description');
    if (isCurrent) {
      const description = text(source.description, text(source.text));
      return {
        callout: text(source.callout),
        label: text(source.label),
        description,
        text: description,
      };
    }
    const legacyCallout = text(source.label);
    const legacyLabel = text(source.text);
    return {
      callout: legacyCallout,
      label: legacyLabel,
      description: '',
      text: '',
    };
  });
  return entries.length ? entries : [emptyCalloutEntry()];
}

export function normalizeCalloutSetConfig(
  value: unknown,
  fallbackFamily: CalloutFamily = 'round',
): CalloutSetConfig {
  const source = record(value);
  const family = option(source.family, FAMILIES, fallbackFamily);
  const fallback = defaultCalloutSetConfig(family);
  return {
    kind: 'callout-set',
    family,
    setName: text(source.setName, fallback.setName),
    title: text(source.title, fallback.title),
    entries: normalizeCalloutEntries(source.entries),
    markerShape: option(source.markerShape, MARKER_SHAPES, fallback.markerShape),
    layout: option(source.layout, LAYOUTS, fallback.layout),
    gridColumns: integerValue(source.gridColumns, fallback.gridColumns, 1, 20),
    markerSize: integerValue(source.markerSize, fallback.markerSize, 24, 160),
    spacing: integerValue(source.spacing, fallback.spacing, 0, 80),
    fill: text(source.fill, fallback.fill),
    stroke: text(source.stroke, fallback.stroke),
    textColor: text(source.textColor, fallback.textColor),
  };
}

/**
 * Parse Excel/TSV clipboard text into editable callout rows.
 *
 * - 1 column: Label
 * - 2 columns: Callout + Label
 * - 3+ columns: Callout + Label + Description (extra cells stay tab-separated)
 */
export function parseCalloutClipboardText(value: string): CalloutEntry[] {
  if (!value) return [];
  const lines = value.replace(/\r\n?/g, '\n').split('\n');
  while (lines.length && lines[lines.length - 1] === '') lines.pop();
  return lines.slice(0, MAX_CALLOUT_ROWS).map((line) => {
    const cells = line.split('\t');
    if (cells.length === 1) {
      return {
        callout: '',
        label: cells[0],
        description: '',
        text: '',
      };
    }
    const description = cells.length >= 3 ? cells.slice(2).join('\t') : '';
    return {
      callout: cells[0],
      label: cells[1],
      description,
      text: description,
    };
  });
}

export function numericCalloutEntries(
  start: number,
  end: number,
  prefix = '',
): CalloutEntry[] {
  const first = Math.max(-9999, Math.min(9999, Math.round(start)));
  const last = Math.max(-9999, Math.min(9999, Math.round(end)));
  const step = last >= first ? 1 : -1;
  const count = Math.min(MAX_CALLOUT_ROWS, Math.abs(last - first) + 1);
  return Array.from({ length: count }, (_, index) => ({
    callout: `${prefix}${first + index * step}`,
    label: '',
    description: '',
    text: '',
  }));
}

export function calloutSetDisplayName(config: CalloutSetConfig): string {
  const fallback = calloutFamilyLabel(config.family);
  return `${fallback} — ${config.setName.trim() || fallback}`;
}
