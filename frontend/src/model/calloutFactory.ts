import {
  Circle,
  Group,
  Rect,
  Textbox,
  type FabricObject,
} from 'fabric';
import type {
  CalloutEntry,
  CalloutSetConfig,
} from './types';
import {
  calloutSetDisplayName,
  normalizeCalloutSetConfig,
} from './callouts';

interface MarkerResult {
  object: FabricObject | null;
  width: number;
  height: number;
}

function identify<T extends FabricObject>(object: T, name: string, role: string): T {
  Object.assign(object as unknown as Record<string, unknown>, {
    objName: name,
    calloutRole: role,
  });
  return object;
}

function rowName(entry: CalloutEntry, index: number): string {
  return entry.callout || entry.label || entry.description || `Row ${index + 1}`;
}

function marker(
  entry: CalloutEntry,
  index: number,
  config: CalloutSetConfig,
): MarkerResult {
  const size = config.markerSize;
  const value = entry.callout;
  const name = rowName(entry, index);
  const fontSize = Math.max(
    10,
    Math.min(size * 0.45, (size * 1.5) / Math.max(1.7, value.length * 0.62)),
  );

  if (config.markerShape === 'none') {
    if (!value) return { object: null, width: 0, height: size };
    const width = Math.max(36, Math.min(190, value.length * fontSize * 0.72 + 12));
    const plain = identify(new Textbox(value, {
      left: 0,
      top: Math.max(0, size / 2 - fontSize * 0.65),
      width,
      fontFamily: 'Arial',
      fontSize,
      fontWeight: 'bold',
      textAlign: 'center',
      fill: config.textColor,
      editable: true,
      splitByGrapheme: false,
    }), `${name} Callout Text`, 'callout-marker-label');
    return { object: plain, width, height: size };
  }

  const markerHeight = config.markerShape === 'pill'
    ? Math.max(28, Math.round(size * 0.72))
    : size;
  const markerWidth = config.markerShape === 'pill'
    ? Math.max(Math.round(size * 1.45), value.length * fontSize * 0.72 + 24)
    : size;
  const frame = config.markerShape === 'round'
    ? new Circle({
      left: 0,
      top: 0,
      radius: size / 2,
      fill: config.fill,
      stroke: config.stroke,
      strokeWidth: 3,
    })
    : new Rect({
      left: 0,
      top: 0,
      width: markerWidth,
      height: markerHeight,
      rx: config.markerShape === 'pill' ? markerHeight / 2 : 4,
      ry: config.markerShape === 'pill' ? markerHeight / 2 : 4,
      fill: config.fill,
      stroke: config.stroke,
      strokeWidth: 3,
    });
  const label = new Textbox(value, {
    left: 5,
    top: Math.max(2, markerHeight / 2 - fontSize * 0.62),
    width: markerWidth - 10,
    fontFamily: 'Arial',
    fontSize,
    fontWeight: 'bold',
    textAlign: 'center',
    fill: config.textColor,
    editable: true,
    splitByGrapheme: false,
  });
  const object = identify(new Group([
    identify(frame, `${name} Callout Frame`, 'callout-marker-frame'),
    identify(label, `${name} Callout Value`, 'callout-marker-label'),
  ], {
    originX: 'left',
    originY: 'top',
    subTargetCheck: true,
  }), `${name} Callout`, 'callout-marker');
  return { object, width: markerWidth, height: markerHeight };
}

function calloutItem(
  entry: CalloutEntry,
  index: number,
  config: CalloutSetConfig,
): Group {
  const markerResult = marker(entry, index, config);
  const name = rowName(entry, index);
  const children: FabricObject[] = [];
  const hasText = Boolean(entry.label || entry.description);
  const textLeft = markerResult.width + (markerResult.width && hasText ? 12 : 0);
  const textWidth = hasText ? 240 : 0;
  const labelHeight = entry.label ? 24 : 0;
  const descriptionHeight = entry.description ? 38 : 0;
  const contentHeight = Math.max(markerResult.height, labelHeight + descriptionHeight, 1);

  if (markerResult.object) {
    markerResult.object.set({
      left: 0,
      top: Math.max(0, (contentHeight - markerResult.height) / 2),
    });
    children.push(markerResult.object);
  }
  if (entry.label) {
    children.push(identify(new Textbox(entry.label, {
      left: textLeft,
      top: Math.max(0, contentHeight / 2 - (descriptionHeight ? 28 : 12)),
      width: textWidth,
      fontFamily: 'Arial',
      fontSize: 17,
      fontWeight: 'bold',
      fill: config.textColor,
      editable: true,
      splitByGrapheme: false,
    }), `${name} Label`, 'callout-entry-label'));
  }
  if (entry.description) {
    children.push(identify(new Textbox(entry.description, {
      left: textLeft,
      top: Math.max(labelHeight, contentHeight / 2 + (entry.label ? 1 : -10)),
      width: textWidth,
      fontFamily: 'Arial',
      fontSize: 13,
      fill: config.textColor,
      editable: true,
      splitByGrapheme: false,
    }), `${name} Description`, 'callout-entry-text'));
  }
  if (!children.length) {
    children.push(identify(new Rect({
      left: 0,
      top: 0,
      width: 1,
      height: Math.max(1, config.markerSize),
      fill: 'transparent',
      strokeWidth: 0,
    }), `Blank Callout Row ${index + 1}`, 'callout-blank-row'));
  }
  return identify(new Group(children, {
    originX: 'left',
    originY: 'top',
    subTargetCheck: true,
  }), name, 'callout-entry');
}

function markerSet(config: CalloutSetConfig): Group {
  const children = config.entries.map((entry, index) => calloutItem(entry, index, config));
  const maxWidth = Math.max(1, ...children.map((object) => object.width || 1));
  const maxHeight = Math.max(1, ...children.map((object) => object.height || 1));
  let horizontalOffset = 0;
  let verticalOffset = 0;
  children.forEach((object, index) => {
    if (config.layout === 'vertical') {
      object.set({ left: 0, top: verticalOffset });
      verticalOffset += (object.height || maxHeight) + config.spacing;
      return;
    }
    if (config.layout === 'grid') {
      const columns = Math.max(1, config.gridColumns);
      object.set({
        left: (index % columns) * (maxWidth + config.spacing),
        top: Math.floor(index / columns) * (maxHeight + config.spacing),
      });
      return;
    }
    object.set({ left: horizontalOffset, top: 0 });
    horizontalOffset += (object.width || maxWidth) + config.spacing;
  });
  return new Group(children, {
    originX: 'left',
    originY: 'top',
    subTargetCheck: true,
  });
}

function calloutBlock(config: CalloutSetConfig): Group {
  const count = Math.max(1, config.entries.length);
  const columns = config.layout === 'horizontal'
    ? count
    : config.layout === 'grid'
      ? Math.min(count, Math.max(1, config.gridColumns))
      : 1;
  const rows = Math.ceil(count / columns);
  const cellWidth = 440;
  const gap = config.spacing;
  const markerHeight = config.markerShape === 'pill'
    ? Math.max(28, Math.round(config.markerSize * 0.72))
    : config.markerSize;
  const rowHeight = Math.max(markerHeight + 16, 72);
  const headerHeight = config.title ? 48 : 0;
  const width = columns * cellWidth + Math.max(0, columns - 1) * gap;
  const height = headerHeight + 8 + rows * rowHeight + Math.max(0, rows - 1) * gap + 8;
  const children: FabricObject[] = [
    identify(new Rect({
      left: 0,
      top: 0,
      width,
      height,
      rx: 6,
      ry: 6,
      fill: config.fill,
      stroke: config.stroke,
      strokeWidth: 3,
    }), 'Callout Block Frame', 'callout-block-frame'),
  ];

  if (headerHeight) {
    children.push(identify(new Rect({
      left: 0,
      top: 0,
      width,
      height: headerHeight,
      rx: 6,
      ry: 6,
      fill: '#f3b61f',
      stroke: config.stroke,
      strokeWidth: 2,
    }), 'Callout Block Header Band', 'callout-block-header-band'));
    children.push(identify(new Textbox(config.title, {
      left: 12,
      top: 11,
      width: width - 24,
      fontFamily: 'Arial',
      fontSize: 20,
      fontWeight: 'bold',
      textAlign: 'center',
      fill: config.textColor,
      editable: true,
      splitByGrapheme: false,
    }), 'Callout Block Title', 'callout-block-title'));
  }

  config.entries.forEach((entry, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const left = column * (cellWidth + gap);
    const top = headerHeight + 8 + row * (rowHeight + gap);
    const markerResult = marker(entry, index, config);
    const markerLeft = left + 12;
    const markerTop = top + Math.max(0, (rowHeight - markerResult.height) / 2);
    if (markerResult.object) {
      markerResult.object.set({ left: markerLeft, top: markerTop });
      children.push(markerResult.object);
    }

    const textLeft = markerLeft + markerResult.width + (markerResult.width ? 14 : 0);
    const textWidth = cellWidth - (textLeft - left) - 12;
    const name = rowName(entry, index);
    if (entry.label) {
      children.push(identify(new Textbox(entry.label, {
        left: textLeft,
        top: top + (entry.description ? 14 : Math.max(8, rowHeight / 2 - 11)),
        width: textWidth,
        fontFamily: 'Arial',
        fontSize: 17,
        fontWeight: 'bold',
        fill: config.textColor,
        editable: true,
        splitByGrapheme: false,
      }), `${name} Label`, 'callout-entry-label'));
    }
    if (entry.description) {
      children.push(identify(new Textbox(entry.description, {
        left: textLeft,
        top: top + (entry.label ? 40 : Math.max(8, rowHeight / 2 - 10)),
        width: textWidth,
        fontFamily: 'Arial',
        fontSize: 13,
        fill: config.textColor,
        editable: true,
        splitByGrapheme: false,
      }), `${name} Description`, 'callout-entry-text'));
    }
    if (row < rows - 1) {
      children.push(identify(new Rect({
        left: left + 10,
        top: top + rowHeight - 1,
        width: cellWidth - 20,
        height: 1,
        fill: '#94a3b8',
        strokeWidth: 0,
      }), `Callout Row ${index + 1} Divider`, 'callout-row-divider'));
    }
  });

  return new Group(children, {
    originX: 'left',
    originY: 'top',
    subTargetCheck: true,
  });
}

export function buildCalloutSet(value: CalloutSetConfig): Group {
  const config = normalizeCalloutSetConfig(value, value.family);
  const object = config.family === 'block' ? calloutBlock(config) : markerSet(config);
  const name = calloutSetDisplayName(config);
  Object.assign(object as unknown as Record<string, unknown>, {
    objName: name,
    assemblyId: `callout:${config.family}`,
    assemblyName: name,
    calloutComponentType: 'callout-set',
    calloutConfig: config,
    calloutVersion: 2,
    subTargetCheck: true,
  });
  return object;
}
