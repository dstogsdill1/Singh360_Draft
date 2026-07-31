import type {
  SmartBankLayout,
  SmartComponentConfig,
  SmartComponentType,
} from './types';

type PanelType = Extract<SmartComponentConfig, { kind: 'panel-enclosure' }>['panelType'];
type PhysicalPoles = Extract<SmartComponentConfig, { kind: 'contactor-bank' }>['physicalPoles'];
type ContactorConfig = Extract<SmartComponentConfig, { kind: 'contactor-bank' }>;
type PowerModel = Extract<SmartComponentConfig, { kind: 'power-monitor-pack' }>['model'];
type PowerMount = Extract<SmartComponentConfig, { kind: 'power-monitor-pack' }>['mount'];
type CtType = Extract<SmartComponentConfig, { kind: 'power-monitor-pack' }>['ctType'];

export const SMART_COMPONENT_CHOICES: ReadonlyArray<{
  kind: SmartComponentType;
  label: string;
  description: string;
}> = [
  {
    kind: 'panel-enclosure',
    label: 'Panel Enclosure',
    description: 'WICP, LCP, PCP, CCP, REMS, or custom panel with an editable device grid.',
  },
  {
    kind: 'contactor-bank',
    label: 'Contactor Bank',
    description: 'Numbered and spare 1P, 2P, or 3P contactors with optional duplicate-preserving custom labels.',
  },
  {
    kind: 'relay-bank',
    label: 'Relay Bank',
    description: 'Auto-numbered relays arranged horizontally, vertically, or in a grid.',
  },
  {
    kind: 'power-monitor-pack',
    label: 'Power Monitor Pack',
    description: 'PS48, PS24, PS12, or PS3 pack with mounting, terminal-bank, and CT details.',
  },
  {
    kind: 'terminal-bank',
    label: 'Terminal Bank',
    description: 'Numbered editable terminal strip with horizontal or vertical layout.',
  },
  {
    kind: 'labeled-device',
    label: 'Labeled Device Block',
    description: 'Generic editable device block for non-model-specific equipment.',
  },
];

export const SMART_COMPONENT_LABELS: Record<SmartComponentType, string> = Object.fromEntries(
  SMART_COMPONENT_CHOICES.map((item) => [item.kind, item.label]),
) as Record<SmartComponentType, string>;

const SMART_TYPES = new Set<SmartComponentType>(SMART_COMPONENT_CHOICES.map((item) => item.kind));
const PANEL_TYPES = new Set<PanelType>(['WICP', 'LCP', 'PCP', 'CCP', 'REMS', 'CUSTOM']);
const BANK_LAYOUTS = new Set<SmartBankLayout>(['horizontal', 'vertical', 'grid']);
const PHYSICAL_POLES = new Set<PhysicalPoles>(['1P', '2P', '3P']);
const POWER_MODELS = new Set<PowerModel>(['PS48', 'PS24', 'PS12', 'PS3']);
const MOUNTS = new Set<PowerMount>(['WALL', 'DIN']);
const CT_TYPES = new Set<CtType>(['Split-core', 'Solid-core', 'Rogowski', 'Custom']);

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function stringValue(value: unknown, fallback: string): string {
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

function optionValue<T extends string>(value: unknown, choices: Set<T>, fallback: T): T {
  return typeof value === 'string' && choices.has(value as T) ? value as T : fallback;
}

export function parseSmartContactorCustomLabels(value: string): string[] {
  if (!value) return [];
  const labels = value.replace(/\r\n?/g, '\n').split('\n').slice(0, 20);
  while (labels.length && labels[labels.length - 1] === '') labels.pop();
  return labels;
}

function normalizedCustomLabels(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const labels = value.slice(0, 20).map((item) => String(item ?? ''));
  while (labels.length && labels[labels.length - 1] === '') labels.pop();
  return labels;
}

export function smartContactorLabels(config: ContactorConfig): string[] {
  if (config.customLabels.length) return [...config.customLabels];
  const numbered = Array.from({ length: config.numberedCount }, (_, index) =>
    `${config.prefix || ''}${config.autoNumber ? config.startNumber + index : ''}`
      || String(config.startNumber + index));
  const spares = Array.from({ length: config.spareCount }, () => config.spareLabel);
  return [...numbered, ...spares];
}

export function defaultSmartComponentConfig(kind: SmartComponentType): SmartComponentConfig {
  switch (kind) {
    case 'panel-enclosure':
      return {
        kind,
        panelType: 'LCP',
        customPanelType: '',
        title: 'LCP-1',
        width: 560,
        height: 420,
        header: 'LIGHTING CONTROL PANEL',
        deviceRows: 3,
        deviceColumns: 4,
        deviceLabels: Array.from({ length: 12 }, (_, index) => `DEVICE ${index + 1}`),
      };
    case 'contactor-bank':
      return {
        kind,
        prefix: 'C',
        startNumber: 1,
        numberedCount: 4,
        spareCount: 0,
        spareLabel: 'SPARE',
        customLabels: [],
        quantity: 4,
        physicalPoles: '3P',
        scheduledPoles: '3P',
        layout: 'horizontal',
        gridColumns: 4,
        spacing: 18,
        autoNumber: true,
      };
    case 'relay-bank':
      return {
        kind,
        prefix: 'R',
        startNumber: 1,
        quantity: 4,
        layout: 'horizontal',
        gridColumns: 4,
        spacing: 18,
        autoNumber: true,
      };
    case 'power-monitor-pack':
      return {
        kind,
        model: 'PS48',
        mount: 'WALL',
        terminalBank: 'A',
        customTerminalBank: '',
        ctQuantity: 12,
        ctType: 'Split-core',
        customCtType: '',
      };
    case 'terminal-bank':
      return {
        kind,
        label: 'TERMINAL BANK A',
        prefix: 'A',
        startNumber: 1,
        quantity: 12,
        layout: 'horizontal',
        spacing: 4,
      };
    case 'labeled-device':
      return {
        kind,
        label: 'DEVICE',
        secondaryLabel: 'EDIT LABEL',
        width: 180,
        height: 100,
        terminalCount: 2,
      };
  }
}

export function normalizeSmartComponentConfig(
  value: unknown,
  fallbackKind: SmartComponentType = 'labeled-device',
): SmartComponentConfig {
  const source = record(value);
  const kind = typeof source.kind === 'string' && SMART_TYPES.has(source.kind as SmartComponentType)
    ? source.kind as SmartComponentType
    : fallbackKind;
  const fallback = defaultSmartComponentConfig(kind);

  switch (kind) {
    case 'panel-enclosure': {
      const base = fallback as Extract<SmartComponentConfig, { kind: 'panel-enclosure' }>;
      const deviceRows = integerValue(source.deviceRows, base.deviceRows, 1, 12);
      const deviceColumns = integerValue(source.deviceColumns, base.deviceColumns, 1, 12);
      const rawLabels = Array.isArray(source.deviceLabels)
        ? source.deviceLabels.map((item) => String(item ?? ''))
        : base.deviceLabels;
      const labelCount = deviceRows * deviceColumns;
      return {
        kind,
        panelType: optionValue(source.panelType, PANEL_TYPES, base.panelType),
        customPanelType: stringValue(source.customPanelType, base.customPanelType),
        title: stringValue(source.title, base.title),
        width: integerValue(source.width, base.width, 260, 1200),
        height: integerValue(source.height, base.height, 220, 720),
        header: stringValue(source.header, base.header),
        deviceRows,
        deviceColumns,
        deviceLabels: Array.from(
          { length: labelCount },
          (_, index) => rawLabels[index] ?? `DEVICE ${index + 1}`,
        ),
      };
    }
    case 'contactor-bank': {
      const base = fallback as Extract<SmartComponentConfig, { kind: 'contactor-bank' }>;
      const hasNewCounts = Object.prototype.hasOwnProperty.call(source, 'numberedCount')
        || Object.prototype.hasOwnProperty.call(source, 'spareCount');
      let numberedCount = integerValue(
        source.numberedCount,
        hasNewCounts
          ? base.numberedCount
          : integerValue(source.quantity, base.numberedCount, 1, 20),
        0,
        20,
      );
      let spareCount = integerValue(source.spareCount, base.spareCount, 0, 20);
      if (numberedCount + spareCount > 20) {
        spareCount = Math.max(0, 20 - numberedCount);
      }
      const customLabels = normalizedCustomLabels(source.customLabels);
      if (!customLabels.length && numberedCount + spareCount === 0) {
        numberedCount = 1;
      }
      const quantity = customLabels.length || numberedCount + spareCount;
      return {
        kind,
        prefix: stringValue(source.prefix, base.prefix),
        startNumber: integerValue(source.startNumber, base.startNumber, 0, 999),
        numberedCount,
        spareCount,
        spareLabel: stringValue(source.spareLabel, base.spareLabel),
        customLabels,
        quantity,
        physicalPoles: optionValue(source.physicalPoles, PHYSICAL_POLES, base.physicalPoles),
        scheduledPoles: stringValue(source.scheduledPoles, base.scheduledPoles),
        layout: optionValue(source.layout, BANK_LAYOUTS, base.layout),
        gridColumns: integerValue(source.gridColumns, base.gridColumns, 1, 10),
        spacing: integerValue(source.spacing, base.spacing, 0, 100),
        autoNumber: typeof source.autoNumber === 'boolean' ? source.autoNumber : base.autoNumber,
      };
    }
    case 'relay-bank': {
      const base = fallback as Extract<SmartComponentConfig, { kind: 'relay-bank' }>;
      return {
        kind,
        prefix: stringValue(source.prefix, base.prefix),
        startNumber: integerValue(source.startNumber, base.startNumber, 0, 999),
        quantity: integerValue(source.quantity, base.quantity, 1, 20),
        layout: optionValue(source.layout, BANK_LAYOUTS, base.layout),
        gridColumns: integerValue(source.gridColumns, base.gridColumns, 1, 10),
        spacing: integerValue(source.spacing, base.spacing, 0, 100),
        autoNumber: typeof source.autoNumber === 'boolean' ? source.autoNumber : base.autoNumber,
      };
    }
    case 'power-monitor-pack': {
      const base = fallback as Extract<SmartComponentConfig, { kind: 'power-monitor-pack' }>;
      const terminalBank = stringValue(source.terminalBank, base.terminalBank).toUpperCase();
      return {
        kind,
        model: optionValue(source.model, POWER_MODELS, base.model),
        mount: optionValue(source.mount, MOUNTS, base.mount),
        terminalBank: /^[A-L]$/.test(terminalBank) || terminalBank === 'CUSTOM'
          ? terminalBank
          : base.terminalBank,
        customTerminalBank: stringValue(source.customTerminalBank, base.customTerminalBank),
        ctQuantity: integerValue(source.ctQuantity, base.ctQuantity, 0, 48),
        ctType: optionValue(source.ctType, CT_TYPES, base.ctType),
        customCtType: stringValue(source.customCtType, base.customCtType),
      };
    }
    case 'terminal-bank': {
      const base = fallback as Extract<SmartComponentConfig, { kind: 'terminal-bank' }>;
      return {
        kind,
        label: stringValue(source.label, base.label),
        prefix: stringValue(source.prefix, base.prefix),
        startNumber: integerValue(source.startNumber, base.startNumber, 0, 999),
        quantity: integerValue(source.quantity, base.quantity, 1, 48),
        layout: source.layout === 'vertical' ? 'vertical' : 'horizontal',
        spacing: integerValue(source.spacing, base.spacing, 0, 40),
      };
    }
    case 'labeled-device': {
      const base = fallback as Extract<SmartComponentConfig, { kind: 'labeled-device' }>;
      return {
        kind,
        label: stringValue(source.label, base.label),
        secondaryLabel: stringValue(source.secondaryLabel, base.secondaryLabel),
        width: integerValue(source.width, base.width, 80, 600),
        height: integerValue(source.height, base.height, 60, 400),
        terminalCount: integerValue(source.terminalCount, base.terminalCount, 0, 12),
      };
    }
  }
}

export function smartComponentDisplayName(config: SmartComponentConfig): string {
  switch (config.kind) {
    case 'panel-enclosure':
      return `Panel Enclosure — ${config.title || config.panelType}`;
    case 'contactor-bank': {
      const labels = smartContactorLabels(config);
      if (config.customLabels.length) {
        const first = labels[0] || 'Custom';
        const last = labels[labels.length - 1] || 'Custom';
        return `Contactor Bank ${labels.length > 1 ? `${first}…${last}` : first} (${labels.length})`;
      }
      const first = `${config.prefix}${config.autoNumber ? config.startNumber : ''}`;
      const last = `${config.prefix}${config.autoNumber
        ? config.startNumber + config.numberedCount - 1
        : ''}`;
      const numbered = config.numberedCount > 1
        ? `${first}–${last}`
        : config.numberedCount === 1 ? first : '';
      const spares = config.spareCount
        ? `${config.spareCount} ${config.spareLabel || 'SPARE'}`
        : '';
      return `Contactor Bank ${[numbered, spares].filter(Boolean).join(' + ')}`;
    }
    case 'relay-bank': {
      const first = `${config.prefix}${config.autoNumber ? config.startNumber : ''}`;
      const last = `${config.prefix}${config.autoNumber ? config.startNumber + config.quantity - 1 : ''}`;
      return `Relay Bank ${config.quantity > 1 ? `${first}–${last}` : first}`;
    }
    case 'power-monitor-pack':
      return `Power Monitor Pack ${config.model}`;
    case 'terminal-bank':
      return config.label || 'Terminal Bank';
    case 'labeled-device':
      return config.label || 'Labeled Device Block';
  }
}
