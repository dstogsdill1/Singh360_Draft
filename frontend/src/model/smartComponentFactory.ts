import {
  Circle,
  Group,
  Line,
  Rect,
  Textbox,
  type FabricObject,
} from 'fabric';
import type {
  SmartBankLayout,
  SmartComponentConfig,
  SmartContactorBankConfig,
  SmartPanelEnclosureConfig,
  SmartPowerMonitorPackConfig,
  SmartRelayBankConfig,
  SmartTerminalBankConfig,
} from './types';
import {
  normalizeSmartComponentConfig,
  smartContactorLabels,
  smartComponentDisplayName,
} from './smartComponents';

const INK = '#111827';
const BLUE = '#12539b';
const LIGHT_BLUE = '#eaf2fb';
const GOLD = '#f3b61f';
const LIGHT_GRAY = '#f8fafc';

function identify<T extends FabricObject>(object: T, name: string, role?: string): T {
  Object.assign(object as unknown as Record<string, unknown>, {
    objName: name,
    ...(role ? { smartRole: role } : {}),
  });
  return object;
}

function text(
  value: string,
  options: ConstructorParameters<typeof Textbox>[1],
  name: string,
  role?: string,
): Textbox {
  return identify(new Textbox(value, {
    fontFamily: 'Arial',
    fill: INK,
    editable: true,
    splitByGrapheme: false,
    ...options,
  }), name, role);
}

function rect(
  options: ConstructorParameters<typeof Rect>[0],
  name: string,
  role?: string,
): Rect {
  return identify(new Rect(options), name, role);
}

function group(
  children: FabricObject[],
  name: string,
  role?: string,
  options: ConstructorParameters<typeof Group>[1] = {},
): Group {
  return identify(new Group(children, {
    originX: 'left',
    originY: 'top',
    subTargetCheck: true,
    ...options,
  }), name, role);
}

function numberedLabel(prefix: string, start: number, index: number, autoNumber: boolean): string {
  return `${prefix || ''}${autoNumber ? start + index : ''}` || String(start + index);
}

function bankPosition(
  index: number,
  layout: SmartBankLayout,
  gridColumns: number,
  itemWidth: number,
  itemHeight: number,
  spacing: number,
): { left: number; top: number } {
  if (layout === 'vertical') {
    return { left: 0, top: index * (itemHeight + spacing) };
  }
  if (layout === 'grid') {
    const columns = Math.max(1, gridColumns);
    return {
      left: (index % columns) * (itemWidth + spacing),
      top: Math.floor(index / columns) * (itemHeight + spacing),
    };
  }
  return { left: index * (itemWidth + spacing), top: 0 };
}

function withSmartMetadata(object: Group, config: SmartComponentConfig): Group {
  const normalized = normalizeSmartComponentConfig(config, config.kind);
  const name = smartComponentDisplayName(normalized);
  Object.assign(object as unknown as Record<string, unknown>, {
    objName: name,
    assemblyId: `smart:${normalized.kind}`,
    assemblyName: name,
    smartComponentType: normalized.kind,
    smartConfig: normalized,
    smartComponentVersion: 1,
  });
  return object;
}

function panelEnclosure(config: SmartPanelEnclosureConfig): Group {
  const width = config.width;
  const height = config.height;
  const headerHeight = 58;
  const padding = 16;
  const gridTop = headerHeight + 18;
  const gridHeight = Math.max(80, height - gridTop - padding);
  const cellWidth = (width - padding * 2) / config.deviceColumns;
  const cellHeight = gridHeight / config.deviceRows;
  const panelType = config.panelType === 'CUSTOM'
    ? (config.customPanelType.trim() || 'CUSTOM')
    : config.panelType;
  const children: FabricObject[] = [
    rect({
      left: 0,
      top: 0,
      width,
      height,
      fill: '#ffffff',
      stroke: INK,
      strokeWidth: 3,
      rx: 8,
      ry: 8,
    }, 'Panel Enclosure Frame', 'panel-frame'),
    rect({
      left: 0,
      top: 0,
      width,
      height: headerHeight,
      fill: GOLD,
      stroke: INK,
      strokeWidth: 2,
      rx: 8,
      ry: 8,
    }, 'Panel Header Band', 'panel-header-band'),
    text(config.header || 'PANEL', {
      left: 16,
      top: 8,
      width: width - 132,
      fontSize: 13,
      fontWeight: 'bold',
    }, 'Panel Header', 'panel-header'),
    text(config.title || panelType, {
      left: 16,
      top: 26,
      width: width - 132,
      fontSize: 21,
      fontWeight: 'bold',
    }, 'Panel Title', 'panel-title'),
    text(panelType, {
      left: width - 108,
      top: 18,
      width: 92,
      fontSize: 16,
      fontWeight: 'bold',
      textAlign: 'right',
    }, 'Panel Type', 'panel-type'),
  ];

  for (let row = 0; row < config.deviceRows; row += 1) {
    for (let column = 0; column < config.deviceColumns; column += 1) {
      const index = row * config.deviceColumns + column;
      const left = padding + column * cellWidth;
      const top = gridTop + row * cellHeight;
      children.push(rect({
        left,
        top,
        width: cellWidth,
        height: cellHeight,
        fill: (row + column) % 2 ? LIGHT_GRAY : '#ffffff',
        stroke: '#64748b',
        strokeWidth: 1,
      }, `Panel Device Cell ${index + 1}`, 'panel-device-cell'));
      children.push(text(config.deviceLabels[index] ?? '', {
        left: left + 6,
        top: top + Math.max(5, cellHeight / 2 - 8),
        width: Math.max(24, cellWidth - 12),
        fontSize: Math.max(8, Math.min(13, cellHeight * 0.2)),
        textAlign: 'center',
      }, `Panel Device ${index + 1}`, 'panel-device-label'));
    }
  }

  return withSmartMetadata(group(children, smartComponentDisplayName(config)), config);
}

function contactor(config: SmartContactorBankConfig, index: number, label: string): Group {
  const width = 104;
  const height = 112;
  const poleCount = Number(config.physicalPoles.slice(0, 1)) || 1;
  const children: FabricObject[] = [
    rect({
      left: 0,
      top: 0,
      width,
      height,
      fill: '#ffffff',
      stroke: INK,
      strokeWidth: 2,
      rx: 5,
      ry: 5,
    }, `${label} Contactor Body`, 'contactor-body'),
    text(label, {
      left: 8,
      top: 7,
      width: width - 16,
      fontSize: 18,
      fontWeight: 'bold',
      textAlign: 'center',
    }, `${label} Contactor Label`, 'device-label'),
    text(`PHYSICAL ${config.physicalPoles}`, {
      left: 6,
      top: 34,
      width: width - 12,
      fontSize: 9,
      fontWeight: 'bold',
      textAlign: 'center',
    }, `${label} Physical Poles`, 'physical-poles-label'),
  ];
  const poleStart = (width - poleCount * 20) / 2;
  for (let pole = 0; pole < poleCount; pole += 1) {
    const x = poleStart + pole * 20 + 10;
    children.push(identify(new Line([x, 51, x, 74], {
      stroke: INK,
      strokeWidth: 3,
    }), `${label} Physical Pole ${pole + 1}`, 'physical-pole'));
    children.push(identify(new Circle({
      left: x - 4,
      top: 47,
      radius: 4,
      fill: '#ffffff',
      stroke: INK,
      strokeWidth: 1,
    }), `${label} Pole Terminal ${pole + 1}`, 'physical-pole-terminal'));
  }
  children.push(text(`SCHEDULED: ${config.scheduledPoles || '—'}`, {
    left: 6,
    top: 87,
    width: width - 12,
    fontSize: 9,
    textAlign: 'center',
  }, `${label} Scheduled Poles`, 'scheduled-poles'));
  return group(children, `Contactor ${label}`, 'contactor-device');
}

function contactorBank(config: SmartContactorBankConfig): Group {
  const itemWidth = 104;
  const itemHeight = 112;
  const labels = smartContactorLabels(config);
  const children = labels.map((label, index) => {
    const device = contactor(config, index, label);
    device.set(bankPosition(
      index,
      config.layout,
      config.gridColumns,
      itemWidth,
      itemHeight,
      config.spacing,
    ));
    return device;
  });
  return withSmartMetadata(group(children, smartComponentDisplayName(config)), config);
}

function relay(config: SmartRelayBankConfig, index: number): Group {
  const width = 86;
  const height = 72;
  const label = numberedLabel(config.prefix, config.startNumber, index, config.autoNumber);
  const children: FabricObject[] = [
    rect({
      left: 0,
      top: 0,
      width,
      height,
      fill: '#ffffff',
      stroke: BLUE,
      strokeWidth: 2,
      rx: 5,
      ry: 5,
    }, `${label} Relay Body`, 'relay-body'),
    identify(new Circle({
      left: 27,
      top: 24,
      radius: 16,
      fill: LIGHT_BLUE,
      stroke: BLUE,
      strokeWidth: 2,
    }), `${label} Relay Coil`, 'relay-coil'),
    text(label, {
      left: 8,
      top: 5,
      width: width - 16,
      fontSize: 16,
      fontWeight: 'bold',
      textAlign: 'center',
    }, `${label} Relay Label`, 'device-label'),
    text('RELAY', {
      left: 8,
      top: 51,
      width: width - 16,
      fontSize: 9,
      textAlign: 'center',
    }, `${label} Relay Type`, 'relay-type'),
  ];
  return group(children, `Relay ${label}`, 'relay-device');
}

function relayBank(config: SmartRelayBankConfig): Group {
  const itemWidth = 86;
  const itemHeight = 72;
  const children = Array.from({ length: config.quantity }, (_, index) => {
    const device = relay(config, index);
    device.set(bankPosition(
      index,
      config.layout,
      config.gridColumns,
      itemWidth,
      itemHeight,
      config.spacing,
    ));
    return device;
  });
  return withSmartMetadata(group(children, smartComponentDisplayName(config)), config);
}

function powerMonitorPack(config: SmartPowerMonitorPackConfig): Group {
  const width = 360;
  const height = 230;
  const terminalBank = config.terminalBank === 'CUSTOM'
    ? (config.customTerminalBank.trim() || 'CUSTOM')
    : config.terminalBank;
  const ctType = config.ctType === 'Custom'
    ? (config.customCtType.trim() || 'Custom')
    : config.ctType;
  const children: FabricObject[] = [
    rect({
      left: 0,
      top: 0,
      width,
      height,
      fill: '#ffffff',
      stroke: BLUE,
      strokeWidth: 3,
      rx: 8,
      ry: 8,
    }, 'Power Monitor Pack Frame', 'power-monitor-frame'),
    rect({
      left: 0,
      top: 0,
      width,
      height: 52,
      fill: BLUE,
      stroke: BLUE,
      strokeWidth: 1,
      rx: 8,
      ry: 8,
    }, 'Power Monitor Header Band', 'power-monitor-header'),
    text(config.model, {
      left: 14,
      top: 10,
      width: 112,
      fontSize: 24,
      fontWeight: 'bold',
      fill: '#ffffff',
    }, 'Power Monitor Model', 'power-monitor-model'),
    text('POWER MONITOR PACK', {
      left: 126,
      top: 17,
      width: 218,
      fontSize: 14,
      fontWeight: 'bold',
      textAlign: 'right',
      fill: '#ffffff',
    }, 'Power Monitor Pack Title', 'power-monitor-title'),
    text(`MOUNT: ${config.mount}`, {
      left: 18,
      top: 68,
      width: 145,
      fontSize: 14,
      fontWeight: 'bold',
    }, 'Power Monitor Mount', 'power-monitor-mount'),
    text(`TERMINAL BANK: ${terminalBank}`, {
      left: 18,
      top: 94,
      width: 220,
      fontSize: 14,
      fontWeight: 'bold',
    }, 'Power Monitor Terminal Bank', 'terminal-bank-label'),
    text(`CTS: ${config.ctQuantity} × ${ctType}`, {
      left: 18,
      top: 120,
      width: 310,
      fontSize: 14,
      fontWeight: 'bold',
    }, 'Power Monitor CT Schedule', 'ct-schedule'),
  ];

  const shownCts = Math.min(config.ctQuantity, 12);
  for (let index = 0; index < shownCts; index += 1) {
    const left = 20 + (index % 6) * 48;
    const top = 157 + Math.floor(index / 6) * 35;
    children.push(identify(new Circle({
      left,
      top,
      radius: 12,
      fill: LIGHT_BLUE,
      stroke: BLUE,
      strokeWidth: 2,
    }), `CT ${index + 1}`, 'ct-symbol'));
    children.push(text(String(index + 1), {
      left: left + 3,
      top: top + 5,
      width: 18,
      fontSize: 9,
      textAlign: 'center',
    }, `CT ${index + 1} Label`, 'ct-label'));
  }
  if (config.ctQuantity > shownCts) {
    children.push(text(`+${config.ctQuantity - shownCts} CT`, {
      left: 308,
      top: 177,
      width: 44,
      fontSize: 10,
      fontWeight: 'bold',
      textAlign: 'center',
    }, 'Additional CT Count', 'ct-overflow'));
  }

  return withSmartMetadata(group(children, smartComponentDisplayName(config)), config);
}

function terminalBank(config: SmartTerminalBankConfig): Group {
  const terminalWidth = 38;
  const terminalHeight = 52;
  const children: FabricObject[] = [
    text(config.label || 'TERMINAL BANK', {
      left: 0,
      top: 0,
      width: config.layout === 'horizontal'
        ? Math.max(160, config.quantity * (terminalWidth + config.spacing))
        : 180,
      fontSize: 14,
      fontWeight: 'bold',
    }, 'Terminal Bank Label', 'terminal-bank-title'),
  ];
  for (let index = 0; index < config.quantity; index += 1) {
    const left = config.layout === 'horizontal' ? index * (terminalWidth + config.spacing) : 0;
    const top = 28 + (config.layout === 'vertical' ? index * (terminalHeight + config.spacing) : 0);
    const terminalLabel = `${config.prefix}${config.startNumber + index}`;
    children.push(rect({
      left,
      top,
      width: terminalWidth,
      height: terminalHeight,
      fill: '#fffdf2',
      stroke: INK,
      strokeWidth: 1.5,
    }, `Terminal ${terminalLabel}`, 'terminal'));
    children.push(text(terminalLabel, {
      left: left + 2,
      top: top + 17,
      width: terminalWidth - 4,
      fontSize: 10,
      fontWeight: 'bold',
      textAlign: 'center',
    }, `Terminal ${terminalLabel} Label`, 'terminal-label'));
  }
  return withSmartMetadata(group(children, smartComponentDisplayName(config)), config);
}

function labeledDevice(config: Extract<SmartComponentConfig, { kind: 'labeled-device' }>): Group {
  const children: FabricObject[] = [
    rect({
      left: 0,
      top: 0,
      width: config.width,
      height: config.height,
      fill: '#ffffff',
      stroke: INK,
      strokeWidth: 2,
      rx: 6,
      ry: 6,
    }, 'Device Block Frame', 'device-frame'),
    text(config.label || 'DEVICE', {
      left: 10,
      top: 14,
      width: config.width - 20,
      fontSize: Math.max(12, Math.min(22, config.height * 0.2)),
      fontWeight: 'bold',
      textAlign: 'center',
    }, 'Device Label', 'device-label'),
    text(config.secondaryLabel, {
      left: 10,
      top: Math.max(42, config.height * 0.5),
      width: config.width - 20,
      fontSize: Math.max(9, Math.min(14, config.height * 0.13)),
      textAlign: 'center',
    }, 'Device Secondary Label', 'device-secondary-label'),
  ];
  const terminalSpacing = config.width / Math.max(1, config.terminalCount + 1);
  for (let index = 0; index < config.terminalCount; index += 1) {
    const x = terminalSpacing * (index + 1);
    children.push(identify(new Line([x, config.height - 12, x, config.height + 10], {
      stroke: INK,
      strokeWidth: 2,
    }), `Device Terminal ${index + 1}`, 'device-terminal'));
  }
  return withSmartMetadata(group(children, smartComponentDisplayName(config)), config);
}

export function buildSmartComponent(config: SmartComponentConfig): Group {
  const normalized = normalizeSmartComponentConfig(config, config.kind);
  switch (normalized.kind) {
    case 'panel-enclosure':
      return panelEnclosure(normalized);
    case 'contactor-bank':
      return contactorBank(normalized);
    case 'relay-bank':
      return relayBank(normalized);
    case 'power-monitor-pack':
      return powerMonitorPack(normalized);
    case 'terminal-bank':
      return terminalBank(normalized);
    case 'labeled-device':
      return labeledDevice(normalized);
  }
}
