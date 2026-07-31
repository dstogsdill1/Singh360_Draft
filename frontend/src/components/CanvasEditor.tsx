import { useEffect, useRef } from 'react';
import { Canvas, Rect, Circle, Textbox, Line, Group, ActiveSelection, FabricImage, filters, util, type FabricObject } from 'fabric';
import type { BusOptions, CalloutSetConfig, CanvasApi, CanvasSelection, ImageCropPlacement, ImageCropRect, ImageCropState, LibraryComponentInsertMeta, LineStyle, PlacedSymbolEditorConfig, QuickAssemblyId, SavedAssembly, SmartComponentConfig, SmartComponentType, SymbolLegendInsertConfig } from '../model/types';
import { Connector } from './connector';
import { CONNECTOR_PRESETS, dashArray, type DashStyle } from '../model/connectorPresets';
import { BODY_W, BODY_H } from '../model/sheetGeometry';
import { normalizeAssetUrl, normalizeCanvasObjects } from '../model/assetUrl';
import { loadSafeFabricImage, repairSerializedComponentSvgImages } from '../model/fabricImageLoader';
import { scaleImageToSize, standardSymbolSize, SYMBOL_SIZE_SMALL } from '../model/symbolSizing';
import { assignFreshCanvasObjectIds, newCanvasObjectId } from '../model/canvasObjectIdentity';
import { buildSmartComponent } from '../model/smartComponentFactory';
import { normalizeSmartComponentConfig, SMART_COMPONENT_CHOICES } from '../model/smartComponents';
import { buildCalloutSet } from '../model/calloutFactory';
import { normalizeCalloutSetConfig } from '../model/callouts';

interface Props {
  serialized: Record<string, unknown>[];
  onSerializedChange: (value: Record<string, unknown>[]) => void;
  registerApi: (api: CanvasApi | null) => void;
  onSelectionChange: (sel: CanvasSelection | null) => void;
  activeTool: string;
  onToolConsumed: () => void;
  snap: boolean;
  overlayMode: boolean;
}

const CANVAS_W = BODY_W;
const CANVAS_H = BODY_H;
const SNAP = 16;
const SER_PROPS = ['objectId', 'assemblyId', 'assemblyName', 'objName', 'sourceUrl', 'symCategory', 'symAcronym', 'libraryComponentId', 'libraryCollection', 'favorite', 'placedSymbolType', 'placedSymbolConfig', 'placedSymbolRole', 'calloutComponentType', 'calloutConfig', 'calloutVersion', 'calloutRole', 'smartComponentType', 'smartConfig', 'smartComponentVersion', 'smartRole', 'smartParentId', 'smartParentType', 'smartParentConfig', 'smartParentName', 'subTargetCheck', 'arrowStart', 'arrowEnd', 'connectorKind', 'pointsData', 'label', 'stylePreset', 'wireNumber', 'labelStart', 'labelMiddle', 'labelEnd', 'layer', 'pdfSource', 'pdfPage', 'pdfDpi', 'pdfCrop', 'lockMovementX', 'lockMovementY', 'lockScalingX', 'lockScalingY', 'lockRotation', 'editable', 'selectable', 'evented', 'visible', 'textBoxFill', 'textBoxFillOpacity', 'textBoxStroke', 'textBoxStrokeWidth', 'textBoxPadding', 'textBoxRadius'];
const SMART_COMPONENT_TYPES = new Set<SmartComponentType>(
  SMART_COMPONENT_CHOICES.map((item) => item.kind),
);

function ensureFabricObjectIds(object: FabricObject, fresh = false): void {
  const record = object as unknown as Record<string, unknown>;
  if (fresh || typeof record.objectId !== 'string' || !record.objectId) record.objectId = newCanvasObjectId();
  const children = (object as unknown as { getObjects?: () => FabricObject[] }).getObjects?.() || [];
  children.forEach((child) => ensureFabricObjectIds(child, fresh));
}

// S360 POWERPOINT TEXT BOX FORMATTING V1
type S360PowerPointTextBox = Textbox & {
  textBoxFill?: string;
  textBoxFillOpacity?: number;
  textBoxStroke?: string;
  textBoxStrokeWidth?: number;
  textBoxPadding?: number;
  textBoxRadius?: number;
};

function s360RoundedBoxPath(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

const s360TextBoxPrototype = Textbox.prototype as unknown as {
  _renderBackground?: (this: Textbox, ctx: CanvasRenderingContext2D) => void;
  __s360PowerPointTextBoxPatched?: boolean;
};

if (!s360TextBoxPrototype.__s360PowerPointTextBoxPatched) {
  const originalRenderBackground = s360TextBoxPrototype._renderBackground;
  s360TextBoxPrototype._renderBackground = function s360TextBoxBackground(
    this: Textbox,
    ctx: CanvasRenderingContext2D,
  ) {
    if (originalRenderBackground) originalRenderBackground.call(this, ctx);
    const box = this as S360PowerPointTextBox;
    const fill = String(box.textBoxFill || 'transparent');
    const stroke = String(box.textBoxStroke || 'transparent');
    const strokeWidth = Math.max(0, Number(box.textBoxStrokeWidth || 0));
    const padding = Math.max(0, Number(box.textBoxPadding ?? 8));
    const radius = Math.max(0, Number(box.textBoxRadius || 0));
    const opacity = Math.max(0, Math.min(1, Number(box.textBoxFillOpacity ?? 1)));
    const textWidth = Math.max(1, Number(box.width || 1));
    const textHeight = Math.max(1, Number(box.height || 1));
    const width = textWidth + padding * 2;
    const height = textHeight + padding * 2;
    const x = -textWidth / 2 - padding;
    const y = -textHeight / 2 - padding;

    if ((fill && fill !== 'transparent') || (stroke && stroke !== 'transparent' && strokeWidth > 0)) {
      ctx.save();
      s360RoundedBoxPath(ctx, x, y, width, height, radius);
      if (fill && fill !== 'transparent') {
        ctx.globalAlpha = opacity;
        ctx.fillStyle = fill;
        ctx.fill();
      }
      if (stroke && stroke !== 'transparent' && strokeWidth > 0) {
        ctx.globalAlpha = 1;
        ctx.strokeStyle = stroke;
        ctx.lineWidth = strokeWidth;
        ctx.stroke();
      }
      ctx.restore();
    }
  };
  s360TextBoxPrototype.__s360PowerPointTextBoxPatched = true;
}

function summarize(obj: FabricObject): CanvasSelection {
  const anyObj = obj as unknown as Record<string, unknown>;
  const isText = obj.type === 'textbox' || obj.type === 'text' || 'fontSize' in obj;
  const isTextBox = isText && (obj.type === 'textbox' || obj.type === 'text');
  const isConnector = obj.type === 'Connector' || 'arrowEnd' in obj;
  const isImage = obj.type === 'image';
  const isGroup = obj.type === 'group';
  const objectName = typeof anyObj.objName === 'string' ? anyObj.objName : '';
  const smartComponentType = typeof anyObj.smartComponentType === 'string'
    && SMART_COMPONENT_TYPES.has(anyObj.smartComponentType as SmartComponentType)
    ? anyObj.smartComponentType as SmartComponentType
    : undefined;
  const smartConfig = smartComponentType && anyObj.smartConfig
    ? normalizeSmartComponentConfig(anyObj.smartConfig, smartComponentType)
    : undefined;
  const calloutConfig = anyObj.calloutComponentType === 'callout-set' && anyObj.calloutConfig
    ? normalizeCalloutSetConfig(anyObj.calloutConfig)
    : undefined;
  const placedSymbolConfig = anyObj.placedSymbolConfig && typeof anyObj.placedSymbolConfig === 'object'
    ? anyObj.placedSymbolConfig as Record<string, unknown>
    : {};
  const sourceUrl = typeof anyObj.sourceUrl === 'string' ? anyObj.sourceUrl : undefined;
  const isPlacedSymbol = anyObj.placedSymbolType === 'library-symbol'
    || Boolean(sourceUrl)
    || isImage;
  const isLegend = isGroup && /legend|marker/i.test(objectName);
  const dashArr = anyObj.strokeDashArray as number[] | undefined | null;
  const dash = !dashArr || dashArr.length === 0 ? 'solid'
    : dashArr.length === 2 && dashArr[0] <= 3 ? 'dotted'
    : dashArr.length >= 4 ? 'dash-dot'
    : dashArr.length === 2 && dashArr[0] >= 14 ? 'long-dash'
    : 'dashed';
  return {
    type: (obj.type as string) || 'object',
    name: objectName || undefined,
    fill: typeof anyObj.fill === 'string' ? (anyObj.fill as string) : '',
    stroke: typeof anyObj.stroke === 'string' ? (anyObj.stroke as string) : '',
    strokeWidth: (anyObj.strokeWidth as number) ?? 1,
    opacity: typeof anyObj.opacity === 'number' ? (anyObj.opacity as number) : 1,
    fontSize: typeof anyObj.fontSize === 'number' ? (anyObj.fontSize as number) : undefined,
    bold: anyObj.fontWeight === 'bold' || anyObj.fontWeight === 700,
    italic: anyObj.fontStyle === 'italic',
    underline: anyObj.underline === true,
    textAlign: typeof anyObj.textAlign === 'string' ? (anyObj.textAlign as string) : undefined,
    isText,
    text: isText && typeof anyObj.text === 'string' ? anyObj.text : undefined,
    isTextBox,
    textBoxFill: typeof anyObj.textBoxFill === 'string' ? anyObj.textBoxFill : 'transparent',
    textBoxFillOpacity: typeof anyObj.textBoxFillOpacity === 'number' ? anyObj.textBoxFillOpacity : 1,
    textBoxStroke: typeof anyObj.textBoxStroke === 'string' ? anyObj.textBoxStroke : 'transparent',
    textBoxStrokeWidth: typeof anyObj.textBoxStrokeWidth === 'number' ? anyObj.textBoxStrokeWidth : 0,
    textBoxPadding: typeof anyObj.textBoxPadding === 'number' ? anyObj.textBoxPadding : 8,
    textBoxRadius: typeof anyObj.textBoxRadius === 'number' ? anyObj.textBoxRadius : 0,
    isConnector,
    connectorKind: typeof anyObj.connectorKind === 'string' ? (anyObj.connectorKind as CanvasSelection['connectorKind']) : (isConnector ? 'line' : undefined),
    pointsCount: Array.isArray(anyObj.pointsData) ? anyObj.pointsData.length : (isConnector ? 2 : undefined),
    label: typeof anyObj.label === 'string' ? (anyObj.label as string) : undefined,
    isImage,
    isGroup,
    isLegend,
    smartComponentType,
    smartConfig,
    calloutConfig,
    sourceUrl,
    symbolLabel: typeof placedSymbolConfig.label === 'string' ? placedSymbolConfig.label : '',
    symCategory: typeof anyObj.symCategory === 'string' ? anyObj.symCategory : '',
    libraryComponentId: typeof anyObj.libraryComponentId === 'string' ? anyObj.libraryComponentId : undefined,
    favorite: anyObj.favorite === true,
    isPlacedSymbol,
    pdfSource: typeof anyObj.pdfSource === 'string' ? (anyObj.pdfSource as string) : undefined,
    pdfPage: typeof anyObj.pdfPage === 'number' ? (anyObj.pdfPage as number) : undefined,
    pdfDpi: typeof anyObj.pdfDpi === 'number' ? (anyObj.pdfDpi as number) : undefined,
    pdfCrop: typeof anyObj.pdfCrop === 'string' ? (anyObj.pdfCrop as string) : undefined,
    dash: isConnector ? dash : undefined,
    arrowStart: anyObj.arrowStart === true,
    arrowEnd: anyObj.arrowEnd === true,
    x: Math.round(obj.left ?? 0),
    y: Math.round(obj.top ?? 0),
    width: Math.round((obj.width ?? 0) * (obj.scaleX ?? 1)),
    height: Math.round((obj.height ?? 0) * (obj.scaleY ?? 1)),
    angle: Math.round(obj.angle ?? 0),
    locked: obj.lockMovementX === true,
  };
}

function makeText(x: number, y: number) {
  const text = new Textbox('Text', {
    left: x,
    top: y,
    width: 200,
    fontSize: 20,
    fill: '#111111',
    padding: 6,
  }) as S360PowerPointTextBox;
  Object.assign(text, {
    objName: 'Text Box',
    textBoxFill: 'transparent',
    textBoxFillOpacity: 1,
    textBoxStroke: 'transparent',
    textBoxStrokeWidth: 0,
    textBoxPadding: 8,
    textBoxRadius: 0,
  });
  return text;
}
function makePageTitle(text: string) {
  const t = new Textbox((text || 'PAGE TITLE').toUpperCase(), {
    left: 40, top: 24, width: 900, fontSize: 30, fontWeight: 'bold', fill: '#111',
    fontFamily: 'Arial', charSpacing: 40, underline: true,
  });
  (t as unknown as Record<string, unknown>).objName = 'Page Title';
  return t;
}
function makeSectionHeader(text: string) {
  const t = new Textbox(text || 'Section Header', {
    left: 40, top: 90, width: 700, fontSize: 20, fontWeight: 'bold', fill: '#12539b', fontFamily: 'Arial',
  });
  (t as unknown as Record<string, unknown>).objName = 'Section Header';
  return t;
}
function makeNote(text: string) {
  const t = new Textbox(text || 'Note', {
    left: 40, top: 140, width: 460, fontSize: 13, fontStyle: 'italic', fill: '#444', fontFamily: 'Arial',
  });
  (t as unknown as Record<string, unknown>).objName = 'Note';
  return t;
}
function makeRect(x: number, y: number) {
  return new Rect({ left: x, top: y, width: 180, height: 90, fill: 'transparent', stroke: '#111', strokeWidth: 1.5 });
}
function makeCircle(x: number, y: number) {
  return new Circle({ left: x, top: y, radius: 60, fill: 'transparent', stroke: '#111', strokeWidth: 1.5 });
}
function makeLine(x: number, y: number) {
  return new Connector([x, y, x + 200, y], { stroke: '#111', strokeWidth: 2, arrowEnd: false });
}
function makeArrow(x: number, y: number) {
  return new Connector([x, y, x + 200, y], { stroke: '#111', strokeWidth: 2, arrowEnd: true });
}
function makePolyline(x: number, y: number) {
  return new Connector([x, y, x + 120, y + 40], {
    stroke: '#111',
    strokeWidth: 2,
    arrowEnd: false,
    connectorKind: 'polyline',
    pointsData: [
      { x, y },
      { x: x + 120, y: y + 40 },
    ],
  });
}
function makeElbow(x: number, y: number) {
  return new Connector([x, y, x + 180, y + 80], {
    stroke: '#111',
    strokeWidth: 2,
    arrowEnd: false,
    connectorKind: 'elbow',
    pointsData: [
      { x, y },
      { x: x + 180, y },
      { x: x + 180, y: y + 80 },
    ],
  });
}
function makeBracket(x: number, y: number) {
  return new Connector([x, y, x + 50, y + 70], {
    stroke: '#f2c200',
    strokeWidth: 2,
    arrowEnd: false,
    connectorKind: 'polyline',
    pointsData: [
      { x, y },
      { x: x + 26, y },
      { x: x + 26, y: y + 20 },
      { x: x + 52, y: y + 35 },
      { x: x + 26, y: y + 50 },
      { x: x + 26, y: y + 70 },
      { x, y: y + 70 },
    ],
  });
}
function makeDashedBox(x: number, y: number, style: LineStyle) {
  const sw = style.strokeWidth || 1.6;
  return new Rect({
    left: x,
    top: y,
    width: 240,
    height: 140,
    fill: 'transparent',
    stroke: style.stroke || '#f28c28',
    strokeWidth: sw,
    strokeDashArray: dashArray((style.dash || 'dashed') as DashStyle, sw) || [8, 4],
  });
}

function wantsBw(url: string): boolean {
  try {
    const u = new URL(url, window.location.origin);
    return u.searchParams.get('bw') === '1';
  } catch {
    return /[?&]bw=1(?:&|$)/.test(url);
  }
}

/** Compute the 9 canonical snap points for an object (8 edge/corner + centre). */
function objectSnapPoints(obj: FabricObject): Array<{ x: number; y: number }> {
  const bb = obj.getBoundingRect();
  const x0 = bb.left;
  const y0 = bb.top;
  const x1 = bb.left + bb.width;
  const y1 = bb.top + bb.height;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return [
    { x: cx, y: y0 }, // top-center
    { x: cx, y: y1 }, // bottom-center
    { x: x0, y: cy }, // left-center
    { x: x1, y: cy }, // right-center
    { x: x0, y: y0 }, // top-left
    { x: x1, y: y0 }, // top-right
    { x: x0, y: y1 }, // bottom-left
    { x: x1, y: y1 }, // bottom-right
    { x: cx, y: cy }, // centre
  ];
}

/** If `px,py` is within `threshold` pixels of any snap point on any object in
 *  `canvas` (excluding guide lines and the object being drawn), return the snap
 *  point; otherwise return `{x:px, y:py}` unchanged. */
function snapToNearestPort(
  canvas: Canvas,
  px: number,
  py: number,
  exclude: FabricObject | null,
  excludeGuides: FabricObject[],
  threshold = 18,
): { x: number; y: number } {
  let best = { x: px, y: py };
  let bestDist = threshold;
  for (const obj of canvas.getObjects()) {
    if (obj === exclude) continue;
    if (excludeGuides.includes(obj)) continue;
    if ((obj as unknown as Record<string, unknown>).excludeFromExport) continue;
    for (const pt of objectSnapPoints(obj)) {
      const d = Math.hypot(pt.x - px, pt.y - py);
      if (d < bestDist) { bestDist = d; best = pt; }
    }
  }
  return best;
}

function applyBwIfRequested(img: FabricImage, url: string) {
  if (!wantsBw(url)) return;
  img.filters = [new filters.Grayscale()];
  img.applyFilters();
}

type RenderedImageAudit = {
  name: string;
  sourceUrl: string;
  width: number;
  height: number;
  cropX: number;
  cropY: number;
  pixelCount: number;
  pixelWidthRatio: number;
  pixelHeightRatio: number;
};

type RenderAuditWindow = Window & typeof globalThis & {
  __S360_CANVAS_RENDER_AUDIT__?: () => RenderedImageAudit[];
  __S360_LAYOUT_WORKFLOW_AUDIT__?: {
    objects: () => Record<string, unknown>[];
    selectByName: (name: string) => boolean;
    selectAllByName: (name: string) => number;
    selectByNames: (names: string[]) => number;
    screenPointByName: (name: string) => { x: number; y: number } | null;
    deselect: () => void;
  };
};

function renderedSvgImageAudit(objects: FabricObject[]): RenderedImageAudit[] {
  const results: RenderedImageAudit[] = [];
  const visit = (items: FabricObject[]) => {
    items.forEach((obj) => {
      if (obj.type === 'group') {
        visit((obj as Group).getObjects());
        return;
      }
      if (obj.type !== 'image') return;
      const img = obj as FabricImage;
      const rec = img as unknown as Record<string, unknown>;
      const sourceUrl = String(rec.sourceUrl || img.getSrc() || '');
      if (!/\.svg(?:$|[?#])/i.test(sourceUrl)) return;
      const rendered = img.toCanvasElement();
      const ctx = rendered.getContext('2d', { willReadFrequently: true });
      if (!ctx || rendered.width < 1 || rendered.height < 1) return;
      const pixels = ctx.getImageData(0, 0, rendered.width, rendered.height).data;
      let minX = rendered.width;
      let minY = rendered.height;
      let maxX = -1;
      let maxY = -1;
      let pixelCount = 0;
      for (let y = 0; y < rendered.height; y += 1) {
        for (let x = 0; x < rendered.width; x += 1) {
          if (pixels[(y * rendered.width + x) * 4 + 3] < 8) continue;
          minX = Math.min(minX, x);
          minY = Math.min(minY, y);
          maxX = Math.max(maxX, x);
          maxY = Math.max(maxY, y);
          pixelCount += 1;
        }
      }
      const pixelWidth = maxX >= minX ? maxX - minX + 1 : 0;
      const pixelHeight = maxY >= minY ? maxY - minY + 1 : 0;
      results.push({
        name: String(rec.objName || ''),
        sourceUrl,
        width: Number(img.width || 0) * Number(img.scaleX ?? 1),
        height: Number(img.height || 0) * Number(img.scaleY ?? 1),
        cropX: Number(img.cropX || 0),
        cropY: Number(img.cropY || 0),
        pixelCount,
        pixelWidthRatio: pixelWidth / rendered.width,
        pixelHeightRatio: pixelHeight / rendered.height,
      });
    });
  };
  visit(objects);
  return results;
}

type Bounds = { left: number; top: number; width: number; height: number };

function selectedCanvasObjects(canvas: Canvas): FabricObject[] {
  const active = canvas.getActiveObject();
  if (!active) return [];
  return active.type === 'activeselection'
    ? (active as ActiveSelection).getObjects()
    : [active];
}

function combinedBounds(objects: FabricObject[]): Bounds | null {
  if (!objects.length) return null;
  const boxes = objects.map((object) => object.getBoundingRect());
  const left = Math.min(...boxes.map((box) => box.left));
  const top = Math.min(...boxes.map((box) => box.top));
  const right = Math.max(...boxes.map((box) => box.left + box.width));
  const bottom = Math.max(...boxes.map((box) => box.top + box.height));
  return { left, top, width: right - left, height: bottom - top };
}

function moveCanvasObjects(objects: FabricObject[], dx: number, dy: number): void {
  objects.forEach((object) => {
    object.set({
      left: (object.left ?? 0) + dx,
      top: (object.top ?? 0) + dy,
    });
    object.setCoords();
  });
}

function makeEditableTree(object: FabricObject): void {
  object.set({ selectable: true, evented: true });
  const record = object as unknown as Record<string, unknown>;
  if (object.type === 'textbox' || object.type === 'text') record.editable = true;
  const children = (object as unknown as { getObjects?: () => FabricObject[] }).getObjects?.() || [];
  if (children.length) record.subTargetCheck = true;
  children.forEach(makeEditableTree);
}

function fitObjectInsidePage(object: FabricObject, maxWidth = CANVAS_W * 0.82, maxHeight = CANVAS_H * 0.76): void {
  const width = Math.max(1, Number(object.width || 1));
  const height = Math.max(1, Number(object.height || 1));
  const scale = Math.min(1, maxWidth / width, maxHeight / height);
  object.set({ scaleX: scale, scaleY: scale });
}

function placeObjectInOpenArea(canvas: Canvas, object: FabricObject): void {
  const width = Math.max(1, Number(object.width || 1) * Number(object.scaleX ?? 1));
  const height = Math.max(1, Number(object.height || 1) * Number(object.scaleY ?? 1));
  const existing = canvas.getObjects()
    .filter((candidate) => (candidate as unknown as Record<string, unknown>).excludeFromExport !== true)
    .map((candidate) => candidate.getBoundingRect());
  const margin = 16;
  const step = 32;
  const maxLeft = Math.max(margin, CANVAS_W - width - margin);
  const maxTop = Math.max(margin, CANVAS_H - height - margin);
  for (let top = margin; top <= maxTop; top += step) {
    for (let left = margin; left <= maxLeft; left += step) {
      const overlaps = existing.some((bounds) =>
        left < bounds.left + bounds.width + margin
        && left + width + margin > bounds.left
        && top < bounds.top + bounds.height + margin
        && top + height + margin > bounds.top);
      if (!overlaps) {
        object.set({ left, top });
        return;
      }
    }
  }
  const offset = canvas.getObjects().length * 18;
  object.set({
    left: Math.min(maxLeft, margin + (offset % Math.max(step, maxLeft))),
    top: Math.min(maxTop, margin + (offset % Math.max(step, maxTop))),
  });
}

export default function CanvasEditor({
  serialized,
  onSerializedChange,
  registerApi,
  onSelectionChange,
  activeTool,
  onToolConsumed,
  snap,
  overlayMode,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fabricRef = useRef<Canvas | null>(null);

  // Latest-prop refs so long-lived Fabric handlers read current values.
  const toolRef = useRef(activeTool);
  const snapRef = useRef(snap);
  const overlayModeRef = useRef(overlayMode);
  const consumeRef = useRef(onToolConsumed);
  const onSelRef = useRef(onSelectionChange);
  const onSerRef = useRef(onSerializedChange);
  // Style applied to NEW lines drawn with the Line/Arrow/Polyline tools. Driven
  // by the Draw-tab controls + presets via the `setLineStyle` API method.
  const lineStyleRef = useRef<LineStyle>({
    stroke: '#111111', dash: 'solid', strokeWidth: 2, arrowStart: false, arrowEnd: false,
  });
  toolRef.current = activeTool;
  snapRef.current = snap;
  overlayModeRef.current = overlayMode;
  consumeRef.current = onToolConsumed;
  onSelRef.current = onSelectionChange;
  onSerRef.current = onSerializedChange;

  // Undo/redo history of serialized snapshots.
  const historyRef = useRef<string[]>([]);
  const histIdxRef = useRef(-1);
  const restoringRef = useRef(false);
  // Connector currently being drawn (multi-point click placement).
  const creatingPolyRef = useRef<Connector | null>(null);
  // Committed absolute vertices while building a line (preview point excluded).
  const polyCommittedRef = useRef<Array<{ x: number; y: number }>>([]);
  // Drag-to-draw: the scene point where a Line/Arrow drag started, so we can
  // finish the line on mouse-up when the user drags rather than click-clicks.
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  // RAW (un-snapped) mouse-down position — used ONLY to tell a click apart from
  // a drag. Comparing the release against the snapped start caused lines near
  // components to finish instantly (the snap offset looked like a drag).
  const downRawRef = useRef<{ x: number; y: number } | null>(null);
  // Finalizes any in-progress line (set inside the mount effect). Called when the
  // tool changes so the user can NEVER get stuck mid-draw.
  const finalizeRef = useRef<(() => void) | null>(null);
  // Transient alignment guide lines (never serialized/exported).
  const guidesRef = useRef<FabricObject[]>([]);
  // Cursor position (scene coords) while a connector tool is active. Drives the
  // render-overlay snap dots which are DRAWN directly on the canvas context and
  // never added as objects, so they cannot interfere with click hit-testing.
  const hoverRef = useRef<{ x: number; y: number } | null>(null);
  const objectClipboardRef = useRef<FabricObject | null>(null);
  const lastAssemblySelectionRef = useRef<FabricObject | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    let isTearingDown = false;
    const canvas = new Canvas(canvasRef.current, {
      width: CANVAS_W,
      height: CANVAS_H,
      selection: true,
      selectionKey: 'ctrlKey',
      altSelectionKey: 'shiftKey',
      backgroundColor: '',
      targetFindTolerance: 12,
      perPixelTargetFind: false,
    });
    fabricRef.current = canvas;
    const auditWindow = window as RenderAuditWindow;
    const renderAuditEnabled = new URLSearchParams(window.location.search).get('renderAudit') === '1';
    const workflowAuditEnabled = new URLSearchParams(window.location.search).get('workflowAudit') === '1';
    if (renderAuditEnabled) {
      auditWindow.__S360_CANVAS_RENDER_AUDIT__ = () => renderedSvgImageAudit(canvas.getObjects());
    }
    if (workflowAuditEnabled) {
      auditWindow.__S360_LAYOUT_WORKFLOW_AUDIT__ = {
        objects: () => normalizeCanvasObjects((canvas.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]),
        selectByName: (name: string) => {
          const object = canvas.getObjects().find((candidate) =>
            String((candidate as unknown as Record<string, unknown>).objName || '') === name,
          );
          if (!object) return false;
          canvas.setActiveObject(object);
          canvas.requestRenderAll();
          onSelRef.current(summarize(object));
          return true;
        },
        selectAllByName: (name: string) => {
          const objects = canvas.getObjects().filter((candidate) =>
            String((candidate as unknown as Record<string, unknown>).objName || '') === name,
          );
          if (!objects.length) return 0;
          const active = objects.length === 1 ? objects[0] : new ActiveSelection(objects, { canvas });
          canvas.setActiveObject(active);
          canvas.requestRenderAll();
          lastAssemblySelectionRef.current = active;
          onSelRef.current(summarize(active));
          return objects.length;
        },
        selectByNames: (names: string[]) => {
          const wanted = new Set(names);
          const objects = canvas.getObjects().filter((candidate) =>
            wanted.has(String((candidate as unknown as Record<string, unknown>).objName || '')),
          );
          if (!objects.length) return 0;
          const active = objects.length === 1 ? objects[0] : new ActiveSelection(objects, { canvas });
          canvas.setActiveObject(active);
          canvas.requestRenderAll();
          lastAssemblySelectionRef.current = active;
          onSelRef.current(summarize(active));
          return objects.length;
        },
        screenPointByName: (name: string) => {
          const object = canvas.getObjects().find((candidate) =>
            String((candidate as unknown as Record<string, unknown>).objName || '') === name,
          );
          if (!object) return null;
          const bounds = object.getBoundingRect();
          const rect = canvas.upperCanvasEl.getBoundingClientRect();
          return {
            x: rect.left + ((bounds.left + bounds.width / 2) / CANVAS_W) * rect.width,
            y: rect.top + ((bounds.top + bounds.height / 2) / CANVAS_H) * rect.height,
          };
        },
        deselect: () => {
          canvas.discardActiveObject();
          canvas.requestRenderAll();
          onSelRef.current(null);
        },
      };
    }

    // Robust pointer → scene mapping. The sheet is rendered inside a CSS
    // `transform: scale(...)` wrapper (the zoom), and Fabric's own
    // getScenePoint can return stale/wrong coordinates because it does not
    // observe an ancestor's CSS transform. We map from the live on-screen
    // bounding rect of the upper canvas straight to internal canvas units,
    // which is always correct regardless of zoom or device pixel ratio.
    const scenePoint = (e: MouseEvent | PointerEvent | TouchEvent): { x: number; y: number } => {
      const el = canvas.upperCanvasEl;
      const rect = el.getBoundingClientRect();
      const evt = e as MouseEvent;
      const clientX = evt.clientX ?? 0;
      const clientY = evt.clientY ?? 0;
      // rect is the on-screen (CSS-scaled) size; CANVAS_W/H are the internal
      // logical units. Their ratio is exactly the current zoom scale.
      const scaleX = rect.width > 0 ? CANVAS_W / rect.width : 1;
      const scaleY = rect.height > 0 ? CANVAS_H / rect.height : 1;
      return { x: (clientX - rect.left) * scaleX, y: (clientY - rect.top) * scaleY };
    };

    const persist = () => {
      if (restoringRef.current || isTearingDown) return;
      const objects = (canvas.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[];
      onSerRef.current(normalizeCanvasObjects(objects));
    };
    const pushHistory = () => {
      if (restoringRef.current || isTearingDown) return;
      const snapshot = JSON.stringify(canvas.toObject(SER_PROPS));
      const hist = historyRef.current.slice(0, histIdxRef.current + 1);
      hist.push(snapshot);
      historyRef.current = hist;
      histIdxRef.current = hist.length - 1;
    };
    const onChanged = () => {
      if (isTearingDown) return;
      persist();
      pushHistory();
    };
    const isGuideObj = (o: FabricObject | undefined | null) =>
      !!o && (o as unknown as Record<string, unknown>).excludeFromExport === true;

    if (serialized.length) {
      // S360 LIVE PDF OBJECT REPAIR V1
      // Export-only clones intentionally hide their raster PDF preview. A prior
      // interrupted save or copied object must never leave the live editor faded
      // or invisible. Restore direct PDF objects to an opaque visible preview.
      // Loading the server-confirmed snapshot emits Fabric object:added events.
      // Those are a render/hydration echo, not user edits, so suppress the
      // persistence listeners until the full snapshot is mounted.
      restoringRef.current = true;
      void (async () => {
        const normalized = normalizeCanvasObjects(serialized);
        const componentRepair = await repairSerializedComponentSvgImages(normalized);
        if (isTearingDown) return;
        let repairedPdfObjects = false;
        const liveObjects = componentRepair.objects.map((raw) => {
          const obj: Record<string, unknown> = { ...raw };
          if (typeof obj.pdfSource === 'string' && obj.pdfSource.trim()) {
            if (obj.visible === false || Number(obj.opacity ?? 1) !== 1 || obj.excludeFromExport === true) repairedPdfObjects = true;
            obj.visible = true;
            obj.opacity = 1;
            delete obj.excludeFromExport;
          }
          return obj;
        });
        await canvas.loadFromJSON({ version: '6', objects: liveObjects });
        if (isTearingDown) return;
        canvas.getObjects().forEach((o) => {
          ensureFabricObjectIds(o);
          styleForSelection(o);
        });
        canvas.renderAll();
        historyRef.current = [JSON.stringify(canvas.toObject(SER_PROPS))];
        histIdxRef.current = 0;
        restoringRef.current = false;
        if (repairedPdfObjects || componentRepair.repaired > 0) {
          onSerRef.current(normalizeCanvasObjects((canvas.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        }
      })().catch((error) => {
        restoringRef.current = false;
        console.error('Canvas object hydration failed', error);
      });
    } else {
      historyRef.current = [JSON.stringify(canvas.toObject(SER_PROPS))];
      histIdxRef.current = 0;
    }

    canvas.on('object:modified', onChanged);
    canvas.on('object:added', (e) => {
      if (isTearingDown || isGuideObj(e?.target)) return;
      if (e?.target) ensureFabricObjectIds(e.target);
      onChanged();
    });
    canvas.on('object:removed', (e) => { if (isTearingDown || isGuideObj(e?.target)) return; onChanged(); });
    canvas.on('selection:created', () => {
      const o = canvas.getActiveObject();
      if (o) {
        lastAssemblySelectionRef.current = o;
        onSelRef.current(summarize(o));
      }
    });
    canvas.on('selection:updated', () => {
      const o = canvas.getActiveObject();
      if (o) {
        lastAssemblySelectionRef.current = o;
        onSelRef.current(summarize(o));
      }
    });
    canvas.on('selection:cleared', () => onSelRef.current(null));
    const onCanvasContextMenu = (event: MouseEvent) => {
      const target = canvas.findTarget(event);
      if (target) {
        canvas.setActiveObject(target);
        lastAssemblySelectionRef.current = target;
        onSelRef.current(summarize(target));
      } else {
        canvas.discardActiveObject();
        onSelRef.current(null);
      }
      canvas.requestRenderAll();
    };
    canvas.upperCanvasEl?.addEventListener('contextmenu', onCanvasContextMenu);

    const clearGuides = () => {
      if (!guidesRef.current.length) return;
      guidesRef.current.forEach((g) => canvas.remove(g));
      guidesRef.current = [];
    };

    // ── Port snap dots drawn as a RENDER OVERLAY (never added as objects) ──
    // Drawing straight on the context after Fabric renders means the dots are
    // pure decoration: they never appear in the object list, never fire events,
    // and cannot interfere with click/drag hit-testing (the previous
    // add/remove-on-mousemove approach was doing exactly that).
    canvas.on('after:render', () => {
      const hover = hoverRef.current;
      if (!hover || !isLineTool(toolRef.current)) return;
      const ctx = canvas.getContext();
      const objs = canvas.getObjects();
      let nearest: { x: number; y: number } | null = null;
      let nd = 20;
      const all: Array<{ x: number; y: number }> = [];
      for (const o of objs) {
        if (o === creatingPolyRef.current) continue;
        if ((o as unknown as Record<string, unknown>).excludeFromExport) continue;
        const bb = o.getBoundingRect();
        const ocx = bb.left + bb.width / 2;
        const ocy = bb.top + bb.height / 2;
        if (Math.hypot(ocx - hover.x, ocy - hover.y) > Math.max(bb.width, bb.height) / 2 + 220) continue;
        for (const pt of objectSnapPoints(o)) {
          all.push(pt);
          const d = Math.hypot(pt.x - hover.x, pt.y - hover.y);
          if (d < nd) { nd = d; nearest = pt; }
        }
      }
      ctx.save();
      for (const pt of all) {
        const isNear = !!nearest && pt.x === nearest.x && pt.y === nearest.y;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, isNear ? 7 : 4, 0, Math.PI * 2);
        ctx.fillStyle = isNear ? '#16a34a' : '#2563eb';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
    });

    const addVGuide = (x: number) => {
      const ln = new Line([x, 0, x, CANVAS_H], { stroke: '#e5006d', strokeWidth: 1, selectable: false, evented: false });
      (ln as unknown as Record<string, unknown>).excludeFromExport = true;
      guidesRef.current.push(ln);
      canvas.add(ln);
    };
    const addHGuide = (y: number) => {
      const ln = new Line([0, y, CANVAS_W, y], { stroke: '#e5006d', strokeWidth: 1, selectable: false, evented: false });
      (ln as unknown as Record<string, unknown>).excludeFromExport = true;
      guidesRef.current.push(ln);
      canvas.add(ln);
    };

    canvas.on('object:moving', (e) => {
      const t = e.target;
      if (!t) return;
      if (t.lockMovementX || t.lockMovementY) {
        t.setCoords();
        canvas.requestRenderAll();
        return;
      }
      // Connectors are native Polylines — let Fabric translate the whole object
      // (its absolute vertices are derived from the object transform).
      if (t instanceof Connector) {
        t.setCoords();
        canvas.requestRenderAll();
        return;
      }
      clearGuides();
      const w = (t.width ?? 0) * (t.scaleX ?? 1);
      const h = (t.height ?? 0) * (t.scaleY ?? 1);
      const cx = (t.left ?? 0) + w / 2;
      const cy = (t.top ?? 0) + h / 2;
      const TH = 8;

      // Candidate X/Y alignment lines: page center + other objects' centers/edges.
      const xs: number[] = [CANVAS_W / 2];
      const ys: number[] = [CANVAS_H / 2];
      canvas.getObjects().forEach((o) => {
        if (o === t || guidesRef.current.includes(o)) return;
        const ow = (o.width ?? 0) * (o.scaleX ?? 1);
        const oh = (o.height ?? 0) * (o.scaleY ?? 1);
        const ol = o.left ?? 0;
        const ot = o.top ?? 0;
        xs.push(ol + ow / 2, ol, ol + ow);
        ys.push(ot + oh / 2, ot, ot + oh);
      });

      // Snap X: align this object's center to the closest candidate.
      let bestX: number | null = null;
      for (const x of xs) {
        if (Math.abs(cx - x) < TH) { bestX = x; break; }
      }
      if (bestX !== null) {
        t.set({ left: bestX - w / 2 });
        addVGuide(bestX);
      }
      let bestY: number | null = null;
      for (const y of ys) {
        if (Math.abs(cy - y) < TH) { bestY = y; break; }
      }
      if (bestY !== null) {
        t.set({ top: bestY - h / 2 });
        addHGuide(bestY);
      }

      // Grid snap (when Snap is on) — applied after alignment snap.
      if (snapRef.current && bestX === null && bestY === null) {
        t.set({
          left: Math.round((t.left ?? 0) / SNAP) * SNAP,
          top: Math.round((t.top ?? 0) / SNAP) * SNAP,
        });
      }
      canvas.requestRenderAll();
    });
    canvas.on('mouse:up', (opt) => {
      clearGuides();
      // Drag-to-draw: if a Line/Arrow was started on mouse-down and the pointer
      // has since moved a meaningful distance, finish it here on release. This
      // makes simple lines behave like every other app (press → drag → release),
      // while still allowing two-click placement for people who prefer it.
      const poly = creatingPolyRef.current;
      const start = dragStartRef.current;
      const downRaw = downRawRef.current;
      if (poly && start && downRaw && (poly.connectorKind === 'line' || poly.connectorKind === 'arrow')) {
        // Compare RAW SCREEN positions: a real drag moves the cursor >8px on
        // screen. A click (even one that snapped its start to a port) stays put,
        // so it is NOT mistaken for a drag and waits for the 2nd click instead.
        const ue = opt.e as MouseEvent;
        const movedScreen = Math.hypot((ue.clientX ?? 0) - downRaw.x, (ue.clientY ?? 0) - downRaw.y);
        if (movedScreen > 8) {
          const p = scenePoint(opt.e);
          const sp = (v: number) => (snapRef.current ? Math.round(v / SNAP) * SNAP : v);
          let end = { x: sp(p.x), y: sp(p.y) };
          try {
            end = snapToNearestPort(canvas, end.x, end.y, poly, guidesRef.current);
          } catch { /* ignore */ }
          polyCommittedRef.current = [start, end];
          poly.setAbsPoints([start, end]);
          dragStartRef.current = null;
          downRawRef.current = null;
          finishLine(true);
          return;
        }
      }
      // Not a drag → keep the in-progress line alive and wait for the second
      // click (two-click placement). Only the drag-detection state is reset.
      downRawRef.current = null;
      canvas.requestRenderAll();
    });
    // ---- Simple multi-point line placement ---------------------------------
    // Line / Arrow / Polyline all work the SAME way: click to drop each point,
    // move to preview the next segment, double-click or Enter to finish, Esc to
    // cancel, Backspace to remove the last point. Elbow adds square corners.
    const styleForNewLine = (tool: string) => {
      const s = lineStyleRef.current;
      const kind =
        tool === 'arrow' ? 'arrow' : tool === 'elbow' ? 'elbow' : tool === 'polyline' ? 'polyline' : 'line';
      return {
        stroke: s.stroke || '#111',
        strokeWidth: s.strokeWidth || 2,
        strokeDashArray: dashArray(s.dash as DashStyle, s.strokeWidth || 2),
        arrowStart: s.arrowStart,
        arrowEnd: tool === 'arrow' ? true : s.arrowEnd,
        connectorKind: kind as 'line' | 'arrow' | 'polyline' | 'elbow',
      };
    };
    const isLineTool = (t: string) => t === 'line' || t === 'arrow' || t === 'polyline' || t === 'elbow';
    const isMultiPoint = (kind: string) => kind === 'polyline' || kind === 'elbow';

    canvas.on('mouse:down', (opt) => {
      const tool = toolRef.current;
      // Alt+drag on an existing object leaves a duplicate behind (Visio/PPT style).
      const nativeEvt = opt.e as MouseEvent | undefined;
      if (tool === 'select' && nativeEvt?.altKey && opt.target && !creatingPolyRef.current) {
        const orig = opt.target;
        const ol = orig.left ?? 0;
        const ot = orig.top ?? 0;
        void orig.clone(SER_PROPS).then((clone: FabricObject) => {
          ensureFabricObjectIds(clone, true);
          clone.set({ left: ol, top: ot });
          (clone as unknown as Record<string, unknown>).objName = (orig as unknown as Record<string, unknown>).objName;
          canvas.add(clone);
          canvas.requestRenderAll();
          persist();
        });
        // The original keeps dragging, so the copy stays at the start position.
      }
      // While actively building a line, EVERY click drops a point.
      const building = !!creatingPolyRef.current;
      // FIX: for any draw tool (line/arrow/polyline/elbow/text/rect/circle)
      // we must NEVER return early just because opt.target is non-null.
      // Returning early here was blocking drawing on pages that already have
      // components on them (opt.target was set even with skipTargetFind=true
      // in certain Fabric v6 builds when clicking near existing objects).
      const isDrawTool = isLineTool(tool) || tool === 'text' || tool === 'rectangle' || tool === 'circle';
      if (!building && !isDrawTool) return; // only exit in pure select mode
      const p = scenePoint(opt.e);
      const sp = (v: number) => (snapRef.current ? Math.round(v / SNAP) * SNAP : v);

      if (isLineTool(tool) || building) {
        const kind = (creatingPolyRef.current?.connectorKind ?? tool) as string;
        const isElbow = kind === 'elbow';
        // Port-snap: snap to object connection points first, then grid.
        const gridX = sp(p.x);
        const gridY = sp(p.y);
        let snapped = { x: gridX, y: gridY };
        try {
          snapped = snapToNearestPort(canvas, gridX, gridY, creatingPolyRef.current, guidesRef.current);
        } catch { /* port-snap failure must never block drawing */ }
        const px = snapped.x;
        const py = snapped.y;
        if (!creatingPolyRef.current) {
          // First click: start the line at this point.
          polyCommittedRef.current = [{ x: px, y: py }];
          dragStartRef.current = { x: px, y: py };
          // Store the RAW SCREEN position (client px) so click-vs-drag detection
          // is independent of zoom and unaffected by port snapping.
          const de = opt.e as MouseEvent;
          downRawRef.current = { x: de.clientX ?? 0, y: de.clientY ?? 0 };
          try {
            // IMPORTANT: never create a ZERO-LENGTH connector (both points equal).
            // Fabric's Polyline math + poly controls choke on degenerate geometry
            // and throw, which silently aborted every draw. Seed the 2nd point a
            // hair away; mouse:move immediately replaces it with the live cursor.
            const conn = new Connector([{ x: px, y: py }, { x: px + 1, y: py }], {
              ...styleForNewLine(tool),
            });
            canvas.add(conn);
            canvas.setActiveObject(conn);
            creatingPolyRef.current = conn;
            canvas.requestRenderAll();
          } catch (err) {
            creatingPolyRef.current = null;
            polyCommittedRef.current = [];
          }
        } else {
          // Subsequent click: commit the next point.
          const conn = creatingPolyRef.current;
          const committed = polyCommittedRef.current;
          const prev = committed[committed.length - 1];
          if (isElbow && prev) {
            committed.push({ x: px, y: prev.y }, { x: px, y: py });
          } else {
            committed.push({ x: px, y: py });
          }
          conn.setAbsPoints(committed);
          canvas.requestRenderAll();
          // Simple Line / Arrow = exactly two points → finish now (auto-select).
          if (!isMultiPoint(kind) && committed.length >= 2) {
            finishLine(true);
          }
        }
        return;
      }

      let obj: FabricObject | null = null;
      if (tool === 'text') obj = makeText(p.x, p.y);
      else if (tool === 'rectangle') obj = makeRect(p.x, p.y);
      else if (tool === 'circle') obj = makeCircle(p.x, p.y);
      if (obj) {
        canvas.add(obj);
        canvas.setActiveObject(obj);
        canvas.requestRenderAll();
      }
      consumeRef.current();
    });
    canvas.on('mouse:move', (opt) => {
      const tool = toolRef.current;
      // Track the cursor for the render-overlay snap dots (hover feedback),
      // even before the first click so the user sees where things will snap.
      if (isLineTool(tool)) {
        const hp = scenePoint(opt.e);
        hoverRef.current = { x: hp.x, y: hp.y };
        canvas.requestRenderAll();
      } else if (hoverRef.current) {
        hoverRef.current = null;
        canvas.requestRenderAll();
      }
      const poly = creatingPolyRef.current;
      if (!poly) return;
      const p = scenePoint(opt.e);
      const sp = (v: number) => (snapRef.current ? Math.round(v / SNAP) * SNAP : v);
      // Port-snap the preview endpoint too.
      const gridX = sp(p.x);
      const gridY = sp(p.y);
      let snapped = { x: gridX, y: gridY };
      try {
        snapped = snapToNearestPort(canvas, gridX, gridY, poly, guidesRef.current);
      } catch { /* port-snap failure must never block preview */ }
      const px = snapped.x;
      const py = snapped.y;
      const committed = polyCommittedRef.current;
      const display = [...committed];
      const prev = committed[committed.length - 1];
      if (poly.connectorKind === 'elbow' && prev) {
        display.push({ x: px, y: prev.y }, { x: px, y: py });
      } else {
        display.push({ x: px, y: py });
      }
      if (display.length < 2) display.push({ x: px, y: py });
      poly.setAbsPoints(display);
      canvas.requestRenderAll();
    });

    // Finish the in-progress line: keep it, select it, and (by default) return to
    // the Select tool so the user can immediately move/edit it.
    const finishLine = (backToSelect = true) => {
      const poly = creatingPolyRef.current;
      if (!poly) return;
      creatingPolyRef.current = null;
      dragStartRef.current = null;
      downRawRef.current = null;
      const committed = polyCommittedRef.current;
      const finalPts = committed.length >= 2 ? committed : poly.getAbsPoints();
      poly.setAbsPoints(finalPts);
      poly.setCoords();
      polyCommittedRef.current = [];
      canvas.setActiveObject(poly);
      canvas.requestRenderAll();
      onChanged();
      if (backToSelect) consumeRef.current();
    };
    // Silently wrap up a half-drawn line when the tool changes (keep if >=2 pts,
    // otherwise drop it) — prevents ever getting stuck mid-draw.
    finalizeRef.current = () => {
      const poly = creatingPolyRef.current;
      if (!poly) return;
      dragStartRef.current = null;
      downRawRef.current = null;
      const committed = polyCommittedRef.current;
      if (committed.length >= 2) {
        creatingPolyRef.current = null;
        poly.setAbsPoints(committed);
        poly.setCoords();
        polyCommittedRef.current = [];
        onChanged();
      } else {
        canvas.remove(poly);
        creatingPolyRef.current = null;
        polyCommittedRef.current = [];
      }
      canvas.requestRenderAll();
    };

    const onKeyDown = (ev: KeyboardEvent) => {
      // Escape = "I'm done." Keep whatever line you've drawn (>=2 points), select
      // it, and drop back to the Select tool. A barely-started line is discarded.
      // You can NEVER get trapped in a drawing tool.
      if (ev.key === 'Escape') {
        if (creatingPolyRef.current) {
          if (polyCommittedRef.current.length >= 2) {
            finishLine();
          } else {
            canvas.remove(creatingPolyRef.current);
            creatingPolyRef.current = null;
            polyCommittedRef.current = [];
            canvas.requestRenderAll();
            if (toolRef.current !== 'select') consumeRef.current();
          }
        } else if (toolRef.current !== 'select') {
          consumeRef.current();
        }
        return;
      }
      const poly = creatingPolyRef.current;
      if (!poly) return;
      if (ev.key === 'Backspace') {
        ev.preventDefault();
        const committed = polyCommittedRef.current;
        if (committed.length > 1) {
          committed.pop();
          poly.setAbsPoints(committed.length >= 2 ? committed : [...committed, committed[0]]);
          canvas.requestRenderAll();
        }
        return;
      }
      if (ev.key === 'Enter') {
        ev.preventDefault();
        finishLine();
      }
    };
    const onDblClick = (ev: MouseEvent) => {
      if (!creatingPolyRef.current) return;
      ev.preventDefault();
      ev.stopPropagation();
      finishLine();
    };
    window.addEventListener('keydown', onKeyDown);
    canvas.upperCanvasEl?.addEventListener('dblclick', onDblClick);

    return () => {
      isTearingDown = true;
      window.removeEventListener('keydown', onKeyDown);
      canvas.upperCanvasEl?.removeEventListener('dblclick', onDblClick);
      canvas.upperCanvasEl?.removeEventListener('contextmenu', onCanvasContextMenu);
      if (renderAuditEnabled) delete auditWindow.__S360_CANVAS_RENDER_AUDIT__;
      if (workflowAuditEnabled) delete auditWindow.__S360_LAYOUT_WORKFLOW_AUDIT__;
      void canvas.dispose();
      fabricRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // While ANY draw tool is active, turn OFF Fabric's object selection + target
  // finding so every click is a pure coordinate capture (drop a point / start a
  // shape) instead of selecting/"highlighting" whatever is under the cursor.
  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;
    // Any half-drawn line is wrapped up before the mode switches, so changing
    // tools/tabs can never leave the canvas stuck in "building" mode.
    finalizeRef.current?.();
    const drawing = activeTool !== 'select';
    canvas.selection = !drawing;
    canvas.skipTargetFind = drawing;
    canvas.defaultCursor = drawing ? 'crosshair' : 'default';
    canvas.hoverCursor = drawing ? 'crosshair' : 'move';
    // Keep pointer→scene mapping correct after any zoom/layout change.
    canvas.calcOffset();
    if (drawing) {
      canvas.discardActiveObject();
    } else if (hoverRef.current) {
      // Leaving a draw tool: drop the hover so the snap-dot overlay disappears.
      hoverRef.current = null;
    }
    canvas.requestRenderAll();
  }, [activeTool]);

  // NOTE: overlay pointer-events are driven purely by React/CSS in NormalizedPage
  // (`overlayInteractive`). A previous DOM-walking hover pass-through was removed
  // because Fabric v6 wraps the <canvas> in a `.canvas-container`, so the effect
  // targeted the wrong elements and objects became unselectable.

  // Apply clear, high-contrast selection handles so users can see what's selected.
  const styleForSelection = (obj: FabricObject) => {
    obj.set({
      borderColor: '#12539b',
      cornerColor: '#12539b',
      cornerStrokeColor: '#ffffff',
      cornerSize: 11,
      transparentCorners: false,
      borderScaleFactor: 2,
    });
  };

  const addObj = (obj: FabricObject) => {
    const c = fabricRef.current;
    if (!c) return;
    styleForSelection(obj);
    c.add(obj);
    c.setActiveObject(obj);
    c.requestRenderAll();
  };

  const restore = (idx: number) => {
    const c = fabricRef.current;
    if (!c || idx < 0 || idx >= historyRef.current.length) return;
    restoringRef.current = true;
    void c.loadFromJSON(JSON.parse(historyRef.current[idx])).then(() => {
      c.renderAll();
      histIdxRef.current = idx;
      restoringRef.current = false;
      onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
    });
  };

  useEffect(() => {
    const api: CanvasApi = {
      captureCanvas: () => {
        const c = fabricRef.current;
        if (!c) return [];
        return normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
      },
      addText: () => addObj(makeText(200, 160)),
      addRect: () => addObj(makeRect(200, 200)),
      addCircle: () => addObj(makeCircle(200, 200)),
      addLine: () => addObj(makeLine(200, 260)),
      addArrow: () => addObj(makeArrow(200, 320)),
      addPolyline: () => addObj(makePolyline(200, 340)),
      addElbow: () => addObj(makeElbow(200, 360)),
      addBracket: () => addObj(makeBracket(260, 260)),
      addDashedBox: () => addObj(makeDashedBox(220, 220, lineStyleRef.current)),
      setLineStyle: (style: LineStyle) => { lineStyleRef.current = style; },
      startBus: (opts: BusOptions) => {
        const c = fabricRef.current;
        if (!c) return;
        // Place N evenly-spaced parallel connectors across the page middle. Each
        // carries its label; the whole harness is selected so it can be dragged
        // into position as one gesture.
        const x1 = Math.round(CANVAS_W * 0.3);
        const x2 = Math.round(CANVAS_W * 0.7);
        const y0 = Math.round(CANVAS_H * 0.45 - ((opts.count - 1) * opts.spacing) / 2);
        const added: FabricObject[] = [];
        for (let i = 0; i < opts.count; i++) {
          const y = y0 + i * opts.spacing;
          const label = opts.labels[i] || '';
          const conn = new Connector([{ x: x1, y }, { x: x2, y }], {
            stroke: opts.stroke,
            strokeWidth: opts.strokeWidth,
            strokeDashArray: dashArray(opts.dash as DashStyle, opts.strokeWidth),
            connectorKind: opts.orthogonal ? 'elbow' : 'line',
            stylePreset: opts.presetId,
            label,
            labelMiddle: label,
            objName: label ? `Bus ${label}` : `Bus wire ${i + 1}`,
          });
          styleForSelection(conn);
          c.add(conn);
          added.push(conn);
          if (label) {
            const lbl = new Textbox(label, {
              left: x1 - 54, top: y - 9, width: 48, fontSize: 11,
              fontFamily: 'Arial', textAlign: 'right', fill: '#111',
            });
            (lbl as unknown as Record<string, unknown>).objName = `Bus Label ${label}`;
            c.add(lbl);
            added.push(lbl);
          }
        }
        if (added.length > 1) {
          const sel = new ActiveSelection(added, { canvas: c });
          c.setActiveObject(sel);
        } else if (added.length === 1) {
          c.setActiveObject(added[0]);
        }
        c.requestRenderAll();
      },
      addPageTitle: (text: string) => addObj(makePageTitle(text)),
      addSectionHeader: (text: string) => addObj(makeSectionHeader(text)),
      addNote: (text: string) => addObj(makeNote(text)),
      addImage: (url: string, name?: string, at?: { clientX: number; clientY: number }) => {
        const c = fabricRef.current;
        if (!c) return;
        const assetUrl = normalizeAssetUrl(url) || url;
        void loadSafeFabricImage(assetUrl).then((img) => {
          applyBwIfRequested(img, assetUrl);
          const maxW = CANVAS_W * 0.6;
          const maxH = CANVAS_H * 0.6;
          const iw = img.width || 1;
          const ih = img.height || 1;
          const scale = Math.min(1, maxW / iw, maxH / ih);
          let left = (CANVAS_W - iw * scale) / 2;
          let top = (CANVAS_H - ih * scale) / 2;
          // If a drop point is supplied, place the image centered on that point.
          const el = canvasRef.current;
          if (at && el) {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
              const px = ((at.clientX - rect.left) / rect.width) * CANVAS_W;
              const py = ((at.clientY - rect.top) / rect.height) * CANVAS_H;
              left = px - (iw * scale) / 2;
              top = py - (ih * scale) / 2;
            }
          }
          img.set({ left, top, scaleX: scale, scaleY: scale });
          (img as unknown as Record<string, unknown>).objName = name || 'image';
          styleForSelection(img);
          c.add(img);
          c.setActiveObject(img);
          c.requestRenderAll();
        });
      },
      addPdfCrop: (url: string, name: string, opts?: { underlay?: boolean; opacity?: number; meta?: { pdfSource: string; pdfPage: number; pdfDpi: number; pdfCrop?: string } }) => {
        const c = fabricRef.current;
        if (!c) return;
        return FabricImage.fromURL(url, { crossOrigin: 'anonymous' }).then((img) => {
          const iw = img.width || 1;
          const ih = img.height || 1;
          // Fit a crisp crop to ~70% of the sheet body; a locked underlay fills
          // the whole body faintly and sits behind everything.
          const underlay = !!opts?.underlay;
          const maxW = CANVAS_W * 0.98;
          const maxH = CANVAS_H * 0.98;
          const scale = Math.min(1, maxW / iw, maxH / ih);
          const left = (CANVAS_W - iw * scale) / 2;
          const top = (CANVAS_H - ih * scale) / 2;
          img.set({ left, top, scaleX: scale, scaleY: scale });
          const anyImg = img as unknown as Record<string, unknown>;
          anyImg.objName = name;
          if (opts?.meta) {
            anyImg.pdfSource = opts.meta.pdfSource;
            anyImg.pdfPage = opts.meta.pdfPage;
            anyImg.pdfDpi = opts.meta.pdfDpi;
            if (opts.meta.pdfCrop) anyImg.pdfCrop = opts.meta.pdfCrop;
          }
          styleForSelection(img);
          if (underlay) {
            img.set({ opacity: opts?.opacity ?? 1, lockMovementX: true, lockMovementY: true, lockScalingX: true, lockScalingY: true, lockRotation: true, selectable: true });
          }
          c.add(img);
          if (underlay) c.sendObjectToBack(img);
          c.setActiveObject(img);
          c.requestRenderAll();
        });
      },
      // S360 IMAGE CROP API START
      getSelectedImageCrop: (): ImageCropState | null => {
        const c = fabricRef.current;
        const active = c?.getActiveObject();
        if (!c || !active || active.type !== 'image') return null;
        const img = active as FabricImage;
        const element = img.getElement() as HTMLImageElement;
        const naturalWidth = Number(element?.naturalWidth || element?.width || img.width || 1);
        const naturalHeight = Number(element?.naturalHeight || element?.height || img.height || 1);
        const cropX = Number(img.cropX || 0);
        const cropY = Number(img.cropY || 0);
        const cropWidth = Number(img.width || naturalWidth);
        const cropHeight = Number(img.height || naturalHeight);
        const rec = img as unknown as Record<string, unknown>;
        return {
          sourceUrl: img.getSrc(),
          name: String(rec.objName || 'Selected image'),
          naturalWidth,
          naturalHeight,
          crop: {
            x: Math.max(0, Math.min(1, cropX / naturalWidth)),
            y: Math.max(0, Math.min(1, cropY / naturalHeight)),
            width: Math.max(0.01, Math.min(1, cropWidth / naturalWidth)),
            height: Math.max(0.01, Math.min(1, cropHeight / naturalHeight)),
          },
          locked: Boolean(img.lockMovementX || img.lockScalingX || img.lockRotation),
        };
      },
      applySelectedImageCrop: (crop: ImageCropRect, placement: ImageCropPlacement = 'keep') => {
        const c = fabricRef.current;
        const active = c?.getActiveObject();
        if (!c || !active || active.type !== 'image') return;
        const img = active as FabricImage;
        const element = img.getElement() as HTMLImageElement;
        const naturalWidth = Number(element?.naturalWidth || element?.width || img.width || 1);
        const naturalHeight = Number(element?.naturalHeight || element?.height || img.height || 1);
        const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
        let x = clamp(Number(crop.x || 0), 0, 0.99) * naturalWidth;
        let y = clamp(Number(crop.y || 0), 0, 0.99) * naturalHeight;
        let width = clamp(Number(crop.width || 1), 0.01, 1) * naturalWidth;
        let height = clamp(Number(crop.height || 1), 0.01, 1) * naturalHeight;
        width = Math.min(width, naturalWidth - x);
        height = Math.min(height, naturalHeight - y);

        if (placement === 'fill') {
          const targetRatio = CANVAS_W / CANVAS_H;
          const ratio = width / height;
          if (ratio > targetRatio) {
            const nextWidth = height * targetRatio;
            x += (width - nextWidth) / 2;
            width = nextWidth;
          } else if (ratio < targetRatio) {
            const nextHeight = width / targetRatio;
            y += (height - nextHeight) / 2;
            height = nextHeight;
          }
        }

        const oldScaleX = img.scaleX ?? 1;
        const oldScaleY = img.scaleY ?? 1;
        const oldWidth = Number(img.width || naturalWidth);
        const oldHeight = Number(img.height || naturalHeight);
        const renderedWidth = oldWidth * oldScaleX;
        const renderedHeight = oldHeight * oldScaleY;
        const oldCenter = img.getCenterPoint();
        // "Apply crop" keeps the same on-page footprint. Fit/fill below can then
        // deliberately resize the cropped result to the drawing body.
        let scaleX = renderedWidth / width;
        let scaleY = renderedHeight / height;
        let left = oldCenter.x - renderedWidth / 2;
        let top = oldCenter.y - renderedHeight / 2;
        if (placement === 'fit') {
          const scale = Math.min((CANVAS_W * 0.98) / width, (CANVAS_H * 0.98) / height);
          scaleX = scale;
          scaleY = scale;
          left = (CANVAS_W - width * scale) / 2;
          top = (CANVAS_H - height * scale) / 2;
        } else if (placement === 'fill') {
          scaleX = CANVAS_W / width;
          scaleY = CANVAS_H / height;
          left = 0;
          top = 0;
        }

        img.set({
          cropX: x,
          cropY: y,
          width,
          height,
          scaleX,
          scaleY,
          left,
          top,
          originX: 'left',
          originY: 'top',
        });
        img.setCoords();
        c.requestRenderAll();
        const objects = normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
        onSerRef.current(objects);
        const snapshot = JSON.stringify(c.toObject(SER_PROPS));
        const history = historyRef.current.slice(0, histIdxRef.current + 1);
        history.push(snapshot);
        historyRef.current = history;
        histIdxRef.current = history.length - 1;
        onSelRef.current(summarize(img));
      },
      resetSelectedImageCrop: () => {
        const c = fabricRef.current;
        const active = c?.getActiveObject();
        if (!c || !active || active.type !== 'image') return;
        const img = active as FabricImage;
        const element = img.getElement() as HTMLImageElement;
        const naturalWidth = Number(element?.naturalWidth || element?.width || img.width || 1);
        const naturalHeight = Number(element?.naturalHeight || element?.height || img.height || 1);
        const center = img.getCenterPoint();
        const renderedWidth = Number(img.width || naturalWidth) * (img.scaleX ?? 1);
        const renderedHeight = Number(img.height || naturalHeight) * (img.scaleY ?? 1);
        const scaleX = renderedWidth / naturalWidth;
        const scaleY = renderedHeight / naturalHeight;
        img.set({
          cropX: 0,
          cropY: 0,
          width: naturalWidth,
          height: naturalHeight,
          scaleX,
          scaleY,
          left: center.x - renderedWidth / 2,
          top: center.y - renderedHeight / 2,
          originX: 'left',
          originY: 'top',
        });
        img.setCoords();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(img));
      },
      // S360 IMAGE CROP API END
      addComponent: (
        url: string,
        name: string,
        label: string | null,
        at?: { clientX: number; clientY: number },
        meta?: LibraryComponentInsertMeta,
      ) => {
        const c = fabricRef.current;
        if (!c) return Promise.resolve();
        const assetUrl = normalizeAssetUrl(url) || url;
        return loadSafeFabricImage(assetUrl).then((img) => {
          applyBwIfRequested(img, assetUrl);
          const size = standardSymbolSize({
            category: meta?.category,
            defaultWidth: meta?.defaultWidth,
            defaultHeight: meta?.defaultHeight,
            acronym: meta?.acronym,
            name,
          });
          const iw = img.width || 1;
          const ih = img.height || 1;
          const scale = scaleImageToSize(iw, ih, size.w, size.h);
          const renderW = iw * scale;
          const renderH = ih * scale;
          let left = (CANVAS_W - renderW) / 2;
          let top = (CANVAS_H - renderH) / 2;
          const el = canvasRef.current;
          if (at && el) {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
              left = ((at.clientX - rect.left) / rect.width) * CANVAS_W - renderW / 2;
              top = ((at.clientY - rect.top) / rect.height) * CANVAS_H - renderH / 2;
            }
          }
          left = Math.max(0, Math.min(Math.max(0, CANVAS_W - renderW), left));
          top = Math.max(0, Math.min(Math.max(0, CANVAS_H - renderH), top));
          img.set({
            left: 0,
            top: 0,
            scaleX: scale,
            scaleY: scale,
            originX: 'left',
            originY: 'top',
          });
          Object.assign(img as unknown as Record<string, unknown>, {
            objName: `${name} Image`,
            sourceUrl: assetUrl,
            placedSymbolRole: 'placed-symbol-image',
          });
          if (meta?.category) (img as unknown as Record<string, unknown>).symCategory = meta.category;
          if (meta?.acronym) (img as unknown as Record<string, unknown>).symAcronym = meta.acronym;
          const lbl = new Textbox(label || '', {
            left: 0,
            top: renderH + 6,
            width: Math.max(120, renderW),
            fontSize: 14,
            fontFamily: 'Arial',
            textAlign: 'center',
            fill: '#111',
            editable: true,
            visible: Boolean(label),
          });
          Object.assign(lbl as unknown as Record<string, unknown>, {
            objName: `${name} Label`,
            placedSymbolRole: 'placed-symbol-label',
          });
          const placed = new Group([img, lbl], {
            left,
            top,
            originX: 'left',
            originY: 'top',
            subTargetCheck: true,
          });
          Object.assign(placed as unknown as Record<string, unknown>, {
            objName: name,
            sourceUrl: assetUrl,
            symCategory: meta?.category || '',
            symAcronym: meta?.acronym || '',
            libraryComponentId: meta?.libraryComponentId || '',
            libraryCollection: meta?.collection || '',
            favorite: meta?.favorite === true,
            placedSymbolType: 'library-symbol',
            placedSymbolConfig: {
              name,
              label: label || '',
              category: meta?.category || '',
            },
          });
          ensureFabricObjectIds(placed, true);
          makeEditableTree(placed);
          styleForSelection(placed);
          c.add(placed);
          c.setActiveObject(placed);
          lastAssemblySelectionRef.current = placed;
          c.requestRenderAll();
          onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
          onSelRef.current(summarize(placed));
        }).catch((err) => {
          console.error('Component image load failed', { name, assetUrl, err });
          window.alert(`Could not load component "${name}". Refresh the library or replace its source image.`);
          c.discardActiveObject();
          onSelRef.current(null);
        });
      },
      addComponentPair: (sourceUrl: string, symbolUrl: string, name: string, label: string | null, at?: { clientX: number; clientY: number }) => {
        const c = fabricRef.current;
        if (!c) return;
        // Load both images, then place source on the left and the B/W symbol to
        // its right, each with an optional label, and select them together.
        void Promise.all([
          loadSafeFabricImage(sourceUrl),
          loadSafeFabricImage(symbolUrl),
        ]).then(([srcImg, symImg]) => {
          const maxW = CANVAS_W * 0.3;
          const maxH = CANVAS_H * 0.3;
          const fit = (im: FabricImage) => Math.min(1, maxW / (im.width || 1), maxH / (im.height || 1));
          const sScale = fit(srcImg);
          const ySymScale = fit(symImg);
          const sW = (srcImg.width || 1) * sScale;
          const sH = (srcImg.height || 1) * sScale;
          const symW = (symImg.width || 1) * ySymScale;
          const gap = 40;
          const totalW = sW + gap + symW;
          let originX = (CANVAS_W - totalW) / 2;
          let originY = (CANVAS_H - sH) / 2;
          const el = canvasRef.current;
          if (at && el) {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
              originX = ((at.clientX - rect.left) / rect.width) * CANVAS_W - totalW / 2;
              originY = ((at.clientY - rect.top) / rect.height) * CANVAS_H - sH / 2;
            }
          }
          const added: FabricObject[] = [];
          const place = (im: FabricImage, left: number, scale: number, tag: string) => {
            const iw = (im.width || 1) * scale;
            const ih = (im.height || 1) * scale;
            im.set({ left, top: originY, scaleX: scale, scaleY: scale });
            (im as unknown as Record<string, unknown>).objName = `${name} (${tag})`;
            styleForSelection(im);
            c.add(im);
            added.push(im);
            if (label) {
              const lbl = new Textbox(`${label}${tag === 'symbol' ? ' (B/W)' : ''}`, {
                left,
                top: originY + ih + 6,
                width: Math.max(120, iw),
                fontSize: 13,
                fontFamily: 'Arial',
                textAlign: 'center',
                fill: '#111',
              });
              (lbl as unknown as Record<string, unknown>).objName = `${name} (${tag}) Label`;
              c.add(lbl);
              added.push(lbl);
            }
          };
          place(srcImg, originX, sScale, 'source');
          symImg.filters = [new filters.Grayscale()];
          symImg.applyFilters();
          place(symImg, originX + sW + gap, ySymScale, 'symbol');
          if (added.length > 1) {
            const sel = new ActiveSelection(added, { canvas: c });
            c.setActiveObject(sel);
          } else if (added.length === 1) {
            c.setActiveObject(added[0]);
          }
          c.requestRenderAll();
        });
      },
      addLegend: (presetIds?: string[]) => {
        const c = fabricRef.current;
        if (!c) return;
        const chosen = presetIds && presetIds.length
          ? CONNECTOR_PRESETS.filter((p) => presetIds.includes(p.id))
          : CONNECTOR_PRESETS;
        const rowH = 26;
        const padX = 14;
        const padY = 14;
        const sampleW = 54;
        const titleH = 26;
        const boxW = 240;
        const boxH = titleH + padY + chosen.length * rowH + padY;
        const parts: FabricObject[] = [];
        // Frame + title.
        parts.push(new Rect({ left: 0, top: 0, width: boxW, height: boxH, fill: '#ffffff', stroke: '#333', strokeWidth: 1.5, rx: 3, ry: 3 }));
        parts.push(new Textbox('CONNECTOR LEGEND', {
          left: padX, top: 6, width: boxW - padX * 2, fontSize: 13, fontWeight: 'bold',
          fontFamily: 'Arial', fill: '#111', textAlign: 'left',
        }));
        chosen.forEach((p, i) => {
          const cy = titleH + padY + i * rowH + rowH / 2;
          const line = new Line([padX, cy, padX + sampleW, cy], {
            stroke: p.stroke,
            strokeWidth: p.strokeWidth,
            strokeDashArray: dashArray(p.dash, p.strokeWidth),
            strokeLineCap: 'round',
          });
          parts.push(line);
          parts.push(new Textbox(p.label, {
            left: padX + sampleW + 12, top: cy - 9, width: boxW - (padX + sampleW + 12) - padX,
            fontSize: 13, fontFamily: 'Arial', fill: '#111', textAlign: 'left',
          }));
        });
        const grp = new Group(parts, { left: CANVAS_W * 0.62, top: CANVAS_H * 0.12 });
        (grp as unknown as Record<string, unknown>).objName = 'Connector Legend';
        styleForSelection(grp);
        c.add(grp);
        c.setActiveObject(grp);
        c.requestRenderAll();
      },
      addSymbolLegend: async (config: SymbolLegendInsertConfig) => {
        const c = fabricRef.current;
        if (!c) return;
        const rows = config.rows.filter((row) => row.label.trim());
        if (!rows.length) return;

        const columns = config.columns === 2 ? 2 : 1;
        const markerSize = Math.max(18, Math.min(42, config.markerSize ?? SYMBOL_SIZE_SMALL));
        const rowH = Math.max(30, markerSize + 7);
        const pad = 12;
        const titleH = 30;
        const colW = 360;
        const rowsPerColumn = Math.ceil(rows.length / columns);
        const boxW = colW * columns;
        const boxH = titleH + pad + rowsPerColumn * rowH + pad;
        const parts: FabricObject[] = [];
        const title = (config.title || 'SYMBOLS KEY:').trim().toUpperCase();

        if (config.frame) {
          parts.push(new Rect({ left: 0, top: 0, width: boxW, height: boxH, fill: '#fff', stroke: '#111', strokeWidth: 1 }));
        }
        parts.push(new Textbox(title, {
          left: pad,
          top: 4,
          width: boxW - pad * 2,
          fontSize: 13,
          fontWeight: 'bold',
          fontFamily: 'Arial',
          fill: '#111',
          editable: true,
        }));

        const addFallbackMarker = (row: typeof rows[number], x: number, y: number) => {
          const highlighted = row.highlighted ?? config.highlighted ?? true;
          if (highlighted) {
            const color1 = row.color || '#ffd400';
            const color2 = row.color2 || color1;
            const pattern = row.pattern || 'solid';
            if (pattern === 'split-vertical') {
              parts.push(new Rect({ left: x, top: y, width: markerSize / 2, height: markerSize, fill: color1, opacity: 0.22, strokeWidth: 0 }));
              parts.push(new Rect({ left: x + markerSize / 2, top: y, width: markerSize / 2, height: markerSize, fill: color2, opacity: 0.22, strokeWidth: 0 }));
              parts.push(new Line([x, y, x, y + markerSize], { stroke: color1, strokeWidth: 2 }));
              parts.push(new Line([x, y, x + markerSize / 2, y], { stroke: color1, strokeWidth: 2 }));
              parts.push(new Line([x, y + markerSize, x + markerSize / 2, y + markerSize], { stroke: color1, strokeWidth: 2 }));
              parts.push(new Line([x + markerSize, y, x + markerSize, y + markerSize], { stroke: color2, strokeWidth: 2 }));
              parts.push(new Line([x + markerSize / 2, y, x + markerSize, y], { stroke: color2, strokeWidth: 2 }));
              parts.push(new Line([x + markerSize / 2, y + markerSize, x + markerSize, y + markerSize], { stroke: color2, strokeWidth: 2 }));
              parts.push(new Line([x + markerSize / 2, y + 1, x + markerSize / 2, y + markerSize - 1], { stroke: '#333', strokeWidth: 0.6, opacity: 0.65 }));
            } else {
              parts.push(new Rect({
                left: x,
                top: y,
                width: markerSize,
                height: markerSize,
                fill: color1,
                opacity: 0.22,
                stroke: color1,
                strokeWidth: 2,
              }));
            }
          }

          const shape = row.shape || (String(row.code || row.acronym || '').toUpperCase() === 'CC' ? 'square' : 'circle');
          const symbolSize = markerSize * 0.72;
          const symbolX = x + (markerSize - symbolSize) / 2;
          const symbolY = y + (markerSize - symbolSize) / 2;
          if (shape === 'circle') {
            parts.push(new Circle({ left: symbolX, top: symbolY, radius: symbolSize / 2, fill: 'transparent', stroke: '#111', strokeWidth: 1 }));
          } else if (shape === 'square') {
            parts.push(new Rect({ left: symbolX, top: symbolY, width: symbolSize, height: symbolSize, fill: 'transparent', stroke: '#111', strokeWidth: 1 }));
          }
          const glyph = String(row.glyph || row.code || row.acronym || '').trim();
          if (glyph) {
            parts.push(new Textbox(glyph, {
              left: x,
              top: y + markerSize * 0.29,
              width: markerSize,
              fontSize: glyph.length > 2 ? markerSize * 0.28 : markerSize * 0.36,
              fontWeight: 'bold',
              fontFamily: 'Arial',
              fill: '#111',
              textAlign: 'center',
              editable: true,
            }));
          }
        };

        const loadedMarkers = await Promise.all(rows.map(async (row) => {
          const rawUrl = String(row.symbolUrl || '').trim();
          if (!rawUrl) return null;
          const assetUrl = normalizeAssetUrl(rawUrl) || rawUrl;
          try {
            const img = await loadSafeFabricImage(assetUrl);
            const iw = img.width || 1;
            const ih = img.height || 1;
            const scale = scaleImageToSize(iw, ih, markerSize, markerSize);
            img.set({ scaleX: scale, scaleY: scale, originX: 'left', originY: 'top' });
            const rec = img as unknown as Record<string, unknown>;
            rec.objName = `Legend ${row.code || row.acronym || row.label}`;
            rec.symCategory = row.category || 'symbols_markers';
            rec.symAcronym = row.acronym || row.code || '';
            rec.sourceUrl = assetUrl;
            return img;
          } catch {
            return null;
          }
        }));

        rows.forEach((row, index) => {
          const column = Math.floor(index / rowsPerColumn);
          const rowIndex = index % rowsPerColumn;
          const baseX = column * colW;
          const rowTop = titleH + pad + rowIndex * rowH;
          const markerX = baseX + pad;
          const markerY = rowTop + (rowH - markerSize) / 2;
          const canonicalMarker = loadedMarkers[index];
          if (canonicalMarker) {
            canonicalMarker.set({ left: markerX, top: markerY });
            canonicalMarker.setCoords();
            parts.push(canonicalMarker);
          } else {
            addFallbackMarker(row, markerX, markerY);
          }

          parts.push(new Textbox(row.label, {
            left: markerX + markerSize + 10,
            top: rowTop + (rowH - 14) / 2,
            width: colW - markerSize - pad * 2 - 12,
            fontSize: 11.5,
            fontFamily: 'Arial',
            fill: '#111',
            editable: true,
            splitByGrapheme: false,
          }));
        });

        const group = new Group(parts, {
          left: CANVAS_W * 0.56,
          top: CANVAS_H * 0.08,
          originX: 'left',
          originY: 'top',
          subTargetCheck: true,
        });
        (group as unknown as Record<string, unknown>).objName =
          title === 'GENERATED SYMBOL KEY'
            ? 'Generated Symbol Key'
            : title === 'SIGNAGE LEGEND'
              ? 'Signage Legend'
              : 'Singh360 Symbol Legend';
        styleForSelection(group);
        c.add(group);
        c.setActiveObject(group);
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      addQuickAssembly: async (kind: QuickAssemblyId) => {
        const c = fabricRef.current;
        if (!c || kind === 'generated-symbol-key' || kind === 'signage-legend') return;
        const parts: FabricObject[] = [];
        let name = '';
        if (kind === 'signage-marker-trio') {
          name = 'Signage Marker Trio';
          const urls = [
            '/api/lib/asset/symbols/symbols_markers/rdm_sign_leak_dne.svg',
            '/api/lib/asset/symbols/symbols_markers/rdm_sign_person_trapped.svg',
            '/api/lib/asset/symbols/symbols_markers/rdm_sign_help_trapped.svg',
          ];
          const loaded = await Promise.all(urls.map(async (url, index) => {
            try {
              const image = await loadSafeFabricImage(url);
              const scale = scaleImageToSize(image.width || 1, image.height || 1, 92, 92);
              image.set({ left: index * 116, top: 0, scaleX: scale, scaleY: scale });
              Object.assign(image as unknown as Record<string, unknown>, {
                objName: `Signage Marker ${index + 1}`,
                sourceUrl: url,
                symCategory: 'symbols_markers',
              });
              return image as FabricObject;
            } catch {
              const fallback = new Rect({ left: index * 116, top: 0, width: 92, height: 92, fill: '#fff8cc', stroke: '#d12b2b', strokeWidth: 4 });
              (fallback as unknown as Record<string, unknown>).objName = `Signage Marker ${index + 1}`;
              return fallback;
            }
          }));
          parts.push(...loaded);
        } else if (kind === 'callout-block') {
          name = 'Callout Block';
          const number = new Textbox('1', { left: 0, top: 0, width: 48, height: 48, fontSize: 25, fontWeight: 'bold', textAlign: 'center', fill: '#111', editable: true });
          const ring = new Circle({ left: 0, top: 0, radius: 24, fill: '#fff', stroke: '#111', strokeWidth: 2 });
          number.set({ top: 9 });
          const note = new Textbox('EDIT CALLOUT NOTE', { left: 68, top: 4, width: 260, fontSize: 16, fill: '#111', editable: true });
          const leader = new Connector([24, 50, 24, 112, 170, 112], { stroke: '#111', strokeWidth: 2, arrowEnd: true, connectorKind: 'elbow' });
          Object.assign(number as unknown as Record<string, unknown>, { objName: 'Callout Number' });
          Object.assign(note as unknown as Record<string, unknown>, { objName: 'Callout Note' });
          Object.assign(leader as unknown as Record<string, unknown>, { objName: 'Callout Leader' });
          parts.push(ring, number, note, leader);
        } else {
          name = 'WICP Annotation Pack';
          const title = new Textbox('WICP ANNOTATION', { left: 0, top: 0, width: 310, fontSize: 19, fontWeight: 'bold', fill: '#12539b', editable: true });
          const note = new Textbox('EDIT WICP NOTE', { left: 0, top: 40, width: 310, fontSize: 15, fill: '#111', editable: true });
          const box = new Rect({ left: -10, top: -10, width: 340, height: 112, fill: '#fff', stroke: '#12539b', strokeWidth: 2, rx: 5, ry: 5 });
          const leader = new Connector([160, 102, 160, 166, 245, 166], { stroke: '#12539b', strokeWidth: 2, arrowEnd: true, connectorKind: 'elbow' });
          Object.assign(title as unknown as Record<string, unknown>, { objName: 'WICP Annotation Title' });
          Object.assign(note as unknown as Record<string, unknown>, { objName: 'WICP Annotation Note' });
          Object.assign(leader as unknown as Record<string, unknown>, { objName: 'WICP Annotation Leader' });
          parts.push(box, title, note, leader);
        }
        const group = new Group(parts, { left: CANVAS_W * 0.42, top: CANVAS_H * 0.18, subTargetCheck: true });
        Object.assign(group as unknown as Record<string, unknown>, {
          objName: name,
          assemblyId: kind,
          assemblyName: name,
        });
        ensureFabricObjectIds(group, true);
        styleForSelection(group);
        c.add(group);
        c.setActiveObject(group);
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      addSmartComponent: (config: SmartComponentConfig) => {
        const c = fabricRef.current;
        if (!c) return;
        const normalized = normalizeSmartComponentConfig(config, config.kind);
        const object = buildSmartComponent(normalized);
        ensureFabricObjectIds(object, true);
        makeEditableTree(object);
        fitObjectInsidePage(object);
        placeObjectInOpenArea(c, object);
        object.setCoords();
        styleForSelection(object);
        c.add(object);
        c.setActiveObject(object);
        lastAssemblySelectionRef.current = object;
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(object));
      },
      updateSelectedSmartComponent: (config: SmartComponentConfig) => {
        const c = fabricRef.current;
        const active = c?.getActiveObject();
        if (!c || !active) return;
        const activeRecord = active as unknown as Record<string, unknown>;
        if (
          typeof activeRecord.smartComponentType !== 'string'
          || !SMART_COMPONENT_TYPES.has(activeRecord.smartComponentType as SmartComponentType)
        ) {
          window.alert('Select one grouped smart component first.');
          return;
        }
        if (active.lockMovementX || active.lockScalingX || active.lockRotation) {
          window.alert('Unlock the smart component before editing its parameters.');
          return;
        }
        const center = active.getCenterPoint();
        const oldObjectId = typeof activeRecord.objectId === 'string' ? activeRecord.objectId : '';
        const normalized = normalizeSmartComponentConfig(config, config.kind);
        const replacement = buildSmartComponent(normalized);
        ensureFabricObjectIds(replacement, true);
        if (oldObjectId) {
          (replacement as unknown as Record<string, unknown>).objectId = oldObjectId;
        }
        makeEditableTree(replacement);
        fitObjectInsidePage(replacement);
        replacement.set({
          angle: active.angle ?? 0,
          opacity: active.opacity ?? 1,
        });
        replacement.setPositionByOrigin(center, 'center', 'center');
        replacement.setCoords();
        styleForSelection(replacement);
        c.remove(active);
        c.add(replacement);
        c.setActiveObject(replacement);
        lastAssemblySelectionRef.current = replacement;
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(replacement));
      },
      addCalloutSet: (config: CalloutSetConfig) => {
        const c = fabricRef.current;
        if (!c) return;
        const normalized = normalizeCalloutSetConfig(config, config.family);
        const object = buildCalloutSet(normalized);
        ensureFabricObjectIds(object, true);
        makeEditableTree(object);
        fitObjectInsidePage(object);
        placeObjectInOpenArea(c, object);
        object.setCoords();
        styleForSelection(object);
        c.add(object);
        c.setActiveObject(object);
        lastAssemblySelectionRef.current = object;
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(object));
      },
      updateSelectedCalloutSet: (config: CalloutSetConfig) => {
        const c = fabricRef.current;
        const active = c?.getActiveObject();
        if (!c || !active) return;
        const record = active as unknown as Record<string, unknown>;
        if (record.calloutComponentType !== 'callout-set' || !record.calloutConfig) {
          window.alert('Select one editable callout set or block first.');
          return;
        }
        if (active.lockMovementX || active.lockScalingX || active.lockRotation) {
          window.alert('Unlock the callout before editing it.');
          return;
        }
        const center = active.getCenterPoint();
        const objectId = typeof record.objectId === 'string' ? record.objectId : '';
        const normalized = normalizeCalloutSetConfig(config, config.family);
        const replacement = buildCalloutSet(normalized);
        ensureFabricObjectIds(replacement, true);
        if (objectId) {
          (replacement as unknown as Record<string, unknown>).objectId = objectId;
        }
        makeEditableTree(replacement);
        fitObjectInsidePage(replacement);
        replacement.set({
          angle: active.angle ?? 0,
          opacity: active.opacity ?? 1,
        });
        replacement.setPositionByOrigin(center, 'center', 'center');
        replacement.setCoords();
        styleForSelection(replacement);
        c.remove(active);
        c.add(replacement);
        c.setActiveObject(replacement);
        lastAssemblySelectionRef.current = replacement;
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(replacement));
      },
      updateSelectedPlacedSymbol: (config: PlacedSymbolEditorConfig) => {
        const c = fabricRef.current;
        const active = c?.getActiveObject();
        if (!c || !active) return;
        if (active.lockMovementX || active.lockScalingX || active.lockRotation) {
          window.alert('Unlock the symbol before editing it.');
          return;
        }
        const record = active as unknown as Record<string, unknown>;
        const previousName = String(record.objName || 'Placed Symbol');
        const children = (active as unknown as { getObjects?: () => FabricObject[] }).getObjects?.() || [];
        const labelObject = children.find((child) =>
          (child as unknown as Record<string, unknown>).placedSymbolRole === 'placed-symbol-label',
        );
        if (labelObject && (labelObject.type === 'textbox' || labelObject.type === 'text')) {
          labelObject.set({
            text: config.label,
            visible: Boolean(config.label),
          });
          const labelRecord = labelObject as unknown as Record<string, unknown>;
          labelRecord.objName = `${config.name} Label`;
          if (typeof labelRecord.initDimensions === 'function') {
            (labelRecord.initDimensions as () => void)();
          }
          labelObject.set('dirty', true);
        } else if (active.type === 'image') {
          const legacyLabel = c.getObjects().find((candidate) =>
            String((candidate as unknown as Record<string, unknown>).objName || '') === `${previousName} Label`,
          );
          if (legacyLabel && (legacyLabel.type === 'textbox' || legacyLabel.type === 'text')) {
            legacyLabel.set({ text: config.label, visible: Boolean(config.label) });
            (legacyLabel as unknown as Record<string, unknown>).objName = `${config.name} Label`;
            legacyLabel.setCoords();
          }
        }
        Object.assign(record, {
          objName: config.name,
          symCategory: config.category,
          favorite: config.favorite,
          placedSymbolConfig: {
            name: config.name,
            label: config.label,
            category: config.category,
          },
        });
        if (active.width) active.set('scaleX', config.width / active.width);
        if (active.height) active.set('scaleY', config.height / active.height);
        active.set('opacity', config.opacity);
        active.set('dirty', true);
        active.setCoords();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(active));
      },
      captureSelectedAssembly: () => {
        const c = fabricRef.current;
        const active = c?.getActiveObject() || lastAssemblySelectionRef.current;
        if (!c || !active) return null;
        const serialized = active.toObject(SER_PROPS) as Record<string, unknown>;
        if (active.type === 'activeselection') {
          serialized.type = 'Group';
          serialized.objName = String(serialized.objName || 'Selection Assembly');
          serialized.assemblyName = String(serialized.assemblyName || serialized.objName);
          serialized.subTargetCheck = true;
        }
        return normalizeCanvasObjects([serialized])[0] || null;
      },
      addSavedAssembly: async (assembly: SavedAssembly) => {
        const c = fabricRef.current;
        if (!c) return;
        const serialized = assignFreshCanvasObjectIds(assembly.object);
        const [object] = await util.enlivenObjects([serialized]) as FabricObject[];
        if (!object) return;
        object.set({
          left: Math.max(24, (object.left ?? 0) + 24),
          top: Math.max(24, (object.top ?? 0) + 24),
          selectable: true,
          evented: true,
        });
        Object.assign(object as unknown as Record<string, unknown>, {
          assemblyId: assembly.id,
          assemblyName: assembly.name,
          objName: assembly.name,
        });
        ensureFabricObjectIds(object, true);
        makeEditableTree(object);
        styleForSelection(object);
        object.setCoords();
        c.add(object);
        c.setActiveObject(object);
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      normalizeSymbolSize: () => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        if (!active) return;
        const objs: FabricObject[] = active.type === 'activeselection'
          ? (active as ActiveSelection).getObjects()
          : active.type === 'group'
            ? (active as Group).getObjects().filter((o) => o.type === 'image')
            : active.type === 'image'
              ? [active]
              : [];
        const images = objs.filter((o) => o.type === 'image');
        if (!images.length) return;
        images.forEach((obj) => {
          const img = obj as FabricImage;
          const name = String((img as unknown as Record<string, unknown>).objName || '');
          if (name.startsWith('Legend ') || name.includes('Label')) return;
          const rec = img as unknown as Record<string, unknown>;
          const size = standardSymbolSize({
            name,
            category: String(rec.symCategory || ''),
            acronym: String(rec.symAcronym || ''),
          });
          const iw = img.width || 1;
          const ih = img.height || 1;
          const cx = (img.left ?? 0) + (iw * (img.scaleX ?? 1)) / 2;
          const cy = (img.top ?? 0) + (ih * (img.scaleY ?? 1)) / 2;
          const scale = scaleImageToSize(iw, ih, size.w, size.h);
          img.set({
            scaleX: scale,
            scaleY: scale,
            left: cx - (iw * scale) / 2,
            top: cy - (ih * scale) / 2,
            originX: 'left',
            originY: 'top',
          });
          img.setCoords();
        });
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      deleteSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o) {
          const objs = o.type === 'activeselection'
            ? (o as unknown as { getObjects: () => FabricObject[] }).getObjects()
            : [o];
          const locked = objs.filter((obj) => obj.lockMovementX || obj.lockScalingX || obj.lockRotation);
          if (locked.length) {
            window.alert('Locked objects were not deleted. Unlock them first.');
          }
          objs.filter((obj) => !(obj.lockMovementX || obj.lockScalingX || obj.lockRotation)).forEach((obj) => c.remove(obj));
          c.discardActiveObject();
          c.requestRenderAll();
          onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        }
      },
      copySelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o) return;
        void o.clone(SER_PROPS).then((clone: FabricObject) => {
          objectClipboardRef.current = clone;
        });
      },
      pasteCopied: () => {
        const c = fabricRef.current;
        if (!c || !objectClipboardRef.current) return;
        const serialized = objectClipboardRef.current.toObject(SER_PROPS) as Record<string, unknown>;
        if (objectClipboardRef.current.type === 'activeselection') {
          serialized.type = 'Group';
          serialized.subTargetCheck = true;
        }
        const fresh = assignFreshCanvasObjectIds(serialized);
        void util.enlivenObjects([fresh]).then((objects) => {
          const pasted = (objects as FabricObject[])[0];
          if (!pasted) return;
          ensureFabricObjectIds(pasted, true);
          makeEditableTree(pasted);
          pasted.set({ left: (pasted.left ?? 0) + 24, top: (pasted.top ?? 0) + 24 });
          styleForSelection(pasted);
          c.add(pasted);
          c.setActiveObject(pasted);
          c.requestRenderAll();
          onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        });
      },
      duplicateSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o) return;
        const objs = o.type === 'activeselection'
          ? (o as unknown as { getObjects: () => FabricObject[] }).getObjects()
          : [o];
        if (objs.some((obj) => obj.lockMovementX || obj.lockScalingX || obj.lockRotation)) {
          window.alert('Locked objects were not duplicated. Unlock them first.');
          return;
        }
        const serialized = o.toObject(SER_PROPS) as Record<string, unknown>;
        if (o.type === 'activeselection') {
          serialized.type = 'Group';
          serialized.subTargetCheck = true;
        }
        const fresh = assignFreshCanvasObjectIds(serialized);
        void util.enlivenObjects([fresh]).then((objects) => {
          const clone = (objects as FabricObject[])[0];
          if (!clone) return;
          ensureFabricObjectIds(clone, true);
          makeEditableTree(clone);
          clone.set({ left: (o.left ?? 0) + 12, top: (o.top ?? 0) + 12 });
          (clone as unknown as Record<string, unknown>).objName = (o as unknown as Record<string, unknown>).objName;
          styleForSelection(clone);
          c.add(clone);
          c.setActiveObject(clone);
          c.requestRenderAll();
          onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        });
      },
      unlockAll: () => {
        const c = fabricRef.current;
        if (!c) return;
        c.getObjects().forEach((o) => {
          o.set({ lockMovementX: false, lockMovementY: false, lockScalingX: false, lockScalingY: false, lockRotation: false });
          if ('editable' in o) o.set('editable', true);
          o.setCoords();
        });
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      undo: () => restore(histIdxRef.current - 1),
      redo: () => restore(histIdxRef.current + 1),
      group: () => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        if (active && active.type === 'activeselection') {
          const sel = active as ActiveSelection;
          const objs = sel.getObjects();
          if (objs.some((o) => o.lockMovementX || o.lockScalingX || o.lockRotation)) {
            window.alert('Locked objects cannot be grouped. Unlock them first.');
            return;
          }
          const grp = new Group(objs);
          ensureFabricObjectIds(grp);
          const childRecords = objs.map((object) => object as unknown as Record<string, unknown>);
          const smartParentIds = new Set(
            childRecords.map((record) => String(record.smartParentId || '')).filter(Boolean),
          );
          if (smartParentIds.size === 1 && childRecords.every((record) => record.smartParentConfig)) {
            const source = childRecords[0];
            Object.assign(grp as unknown as Record<string, unknown>, {
              smartComponentType: source.smartParentType,
              smartConfig: source.smartParentConfig,
              smartComponentVersion: 1,
              objName: source.smartParentName,
              assemblyId: `smart:${String(source.smartParentType || '')}`,
              assemblyName: source.smartParentName,
              subTargetCheck: true,
            });
            childRecords.forEach((record) => {
              delete record.smartParentId;
              delete record.smartParentType;
              delete record.smartParentConfig;
              delete record.smartParentName;
            });
          }
          objs.forEach((o) => c.remove(o));
          c.add(grp);
          c.setActiveObject(grp);
          lastAssemblySelectionRef.current = grp;
          c.requestRenderAll();
          onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        }
      },
      ungroup: () => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        if (!active || active.type !== 'group') {
          window.alert('Select a group, assembly, or smart component first.');
          return;
        }

        const group = active as Group & { toActiveSelection?: () => ActiveSelection };
        const groupRecord = group as unknown as Record<string, unknown>;
        if (
          typeof groupRecord.smartComponentType === 'string'
          && groupRecord.smartConfig
        ) {
          const parentId = String(groupRecord.objectId || newCanvasObjectId());
          group.getObjects().forEach((object) => {
            Object.assign(object as unknown as Record<string, unknown>, {
              smartParentId: parentId,
              smartParentType: groupRecord.smartComponentType,
              smartParentConfig: groupRecord.smartConfig,
              smartParentName: groupRecord.objName || groupRecord.assemblyName || 'Smart Component',
            });
          });
        }
        if (typeof group.toActiveSelection === 'function') {
          const selection = group.toActiveSelection();
          c.setActiveObject(selection);
          lastAssemblySelectionRef.current = selection;
          c.requestRenderAll();
          onSelRef.current({
            ...summarize(selection),
            name: 'Editable legend parts',
          });
          onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
          return;
        }

        const items = group.removeAll();
        const left = group.left ?? 0;
        const top = group.top ?? 0;
        c.remove(group);
        items.forEach((object) => {
          object.set({
            left: left + (object.left ?? 0),
            top: top + (object.top ?? 0),
          });
          object.setCoords();
          c.add(object as FabricObject);
        });
        const selection = new ActiveSelection(items as FabricObject[], { canvas: c });
        c.setActiveObject(selection);
        lastAssemblySelectionRef.current = selection;
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      bringForward: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o && !(o.lockMovementX || o.lockScalingX || o.lockRotation)) { c.bringObjectForward(o); c.requestRenderAll(); onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[])); }
      },
      sendBackward: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o && !(o.lockMovementX || o.lockScalingX || o.lockRotation)) { c.sendObjectBackwards(o); c.requestRenderAll(); onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[])); }
      },
      bringToFront: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o && !(o.lockMovementX || o.lockScalingX || o.lockRotation)) { c.bringObjectToFront(o); c.requestRenderAll(); onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[])); }
      },
      sendToBack: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o && !(o.lockMovementX || o.lockScalingX || o.lockRotation)) { c.sendObjectToBack(o); c.requestRenderAll(); onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[])); }
      },
      alignObjects: (direction) => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        const objs = selectedCanvasObjects(c);
        if (!objs.length) return;
        const bbs = objs.map((o) => ({ o, b: o.getBoundingRect() }));
        if (
          direction === 'page-center-h'
          || direction === 'page-center-v'
          || direction === 'page-center-both'
        ) {
          const bounds = combinedBounds(objs);
          if (!bounds) return;
          const dx = direction === 'page-center-v'
            ? 0
            : CANVAS_W / 2 - (bounds.left + bounds.width / 2);
          const dy = direction === 'page-center-h'
            ? 0
            : CANVAS_H / 2 - (bounds.top + bounds.height / 2);
          moveCanvasObjects(objs, dx, dy);
        } else if (direction === 'left') {
          const minL = Math.min(...bbs.map(({ b }) => b.left));
          bbs.forEach(({ o, b }) => { o.set('left', minL + (o.left ?? 0) - b.left); o.setCoords(); });
        } else if (direction === 'right') {
          const maxR = Math.max(...bbs.map(({ b }) => b.left + b.width));
          bbs.forEach(({ o, b }) => { o.set('left', (o.left ?? 0) + (maxR - (b.left + b.width))); o.setCoords(); });
        } else if (direction === 'center') {
          const minL = Math.min(...bbs.map(({ b }) => b.left));
          const maxR = Math.max(...bbs.map(({ b }) => b.left + b.width));
          const midX = (minL + maxR) / 2;
          bbs.forEach(({ o, b }) => { o.set('left', (o.left ?? 0) + (midX - (b.left + b.width / 2))); o.setCoords(); });
        } else if (direction === 'top') {
          const minT = Math.min(...bbs.map(({ b }) => b.top));
          bbs.forEach(({ o, b }) => { o.set('top', minT + (o.top ?? 0) - b.top); o.setCoords(); });
        } else if (direction === 'bottom') {
          const maxB = Math.max(...bbs.map(({ b }) => b.top + b.height));
          bbs.forEach(({ o, b }) => { o.set('top', (o.top ?? 0) + (maxB - (b.top + b.height))); o.setCoords(); });
        } else if (direction === 'middle') {
          const minT = Math.min(...bbs.map(({ b }) => b.top));
          const maxB = Math.max(...bbs.map(({ b }) => b.top + b.height));
          const midY = (minT + maxB) / 2;
          bbs.forEach(({ o, b }) => { o.set('top', (o.top ?? 0) + (midY - (b.top + b.height / 2))); o.setCoords(); });
        }
        active?.setCoords();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      distributeObjects: (direction) => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        const objs = selectedCanvasObjects(c);
        if (objs.length < 3) return;
        const sorted = direction === 'horizontal'
          ? [...objs].sort((a, b) => {
            const ab = a.getBoundingRect();
            const bb = b.getBoundingRect();
            return (ab.left + ab.width / 2) - (bb.left + bb.width / 2);
          })
          : [...objs].sort((a, b) => {
            const ab = a.getBoundingRect();
            const bb = b.getBoundingRect();
            return (ab.top + ab.height / 2) - (bb.top + bb.height / 2);
          });
        const bbs = sorted.map((o) => ({ o, b: o.getBoundingRect() }));
        if (direction === 'horizontal') {
          const firstCenter = bbs[0].b.left + bbs[0].b.width / 2;
          const lastBox = bbs[bbs.length - 1].b;
          const lastCenter = lastBox.left + lastBox.width / 2;
          const step = (lastCenter - firstCenter) / (bbs.length - 1);
          bbs.slice(1, -1).forEach(({ o, b }, index) => {
            const targetCenter = firstCenter + step * (index + 1);
            o.set('left', (o.left ?? 0) + targetCenter - (b.left + b.width / 2));
            o.setCoords();
          });
        } else {
          const firstCenter = bbs[0].b.top + bbs[0].b.height / 2;
          const lastBox = bbs[bbs.length - 1].b;
          const lastCenter = lastBox.top + lastBox.height / 2;
          const step = (lastCenter - firstCenter) / (bbs.length - 1);
          bbs.slice(1, -1).forEach(({ o, b }, index) => {
            const targetCenter = firstCenter + step * (index + 1);
            o.set('top', (o.top ?? 0) + targetCenter - (b.top + b.height / 2));
            o.setCoords();
          });
        }
        active?.setCoords();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      equalSpaceObjects: (direction) => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        const objs = selectedCanvasObjects(c);
        if (objs.length < 3) return;
        const bbs = objs
          .map((object) => ({ object, bounds: object.getBoundingRect() }))
          .sort((a, b) => direction === 'horizontal'
            ? a.bounds.left - b.bounds.left
            : a.bounds.top - b.bounds.top);
        if (direction === 'horizontal') {
          const totalWidth = bbs.reduce((sum, item) => sum + item.bounds.width, 0);
          const first = bbs[0].bounds;
          const last = bbs[bbs.length - 1].bounds;
          const span = last.left + last.width - first.left;
          const gap = (span - totalWidth) / (bbs.length - 1);
          let cursor = first.left;
          bbs.forEach(({ object, bounds }) => {
            object.set('left', (object.left ?? 0) + cursor - bounds.left);
            object.setCoords();
            cursor += bounds.width + gap;
          });
        } else {
          const totalHeight = bbs.reduce((sum, item) => sum + item.bounds.height, 0);
          const first = bbs[0].bounds;
          const last = bbs[bbs.length - 1].bounds;
          const span = last.top + last.height - first.top;
          const gap = (span - totalHeight) / (bbs.length - 1);
          let cursor = first.top;
          bbs.forEach(({ object, bounds }) => {
            object.set('top', (object.top ?? 0) + cursor - bounds.top);
            object.setCoords();
            cursor += bounds.height + gap;
          });
        }
        active?.setCoords();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      centerInPanel: (direction) => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        const selected = selectedCanvasObjects(c);
        if (!selected.length) return;
        const isPanel = (object: FabricObject) =>
          (object as unknown as Record<string, unknown>).smartComponentType === 'panel-enclosure';
        const availablePanels = c.getObjects().filter(isPanel);
        let panel = selected.find(isPanel);
        const targets = selected.filter((object) => object !== panel);
        if (!panel) {
          const targetBounds = combinedBounds(targets);
          if (targetBounds) {
            const targetCenter = {
              x: targetBounds.left + targetBounds.width / 2,
              y: targetBounds.top + targetBounds.height / 2,
            };
            panel = availablePanels.find((candidate) => {
              const bounds = candidate.getBoundingRect();
              return targetCenter.x >= bounds.left
                && targetCenter.x <= bounds.left + bounds.width
                && targetCenter.y >= bounds.top
                && targetCenter.y <= bounds.top + bounds.height;
            }) || [...availablePanels].sort((a, b) => {
              const ab = a.getBoundingRect();
              const bb = b.getBoundingRect();
              const ad = Math.hypot(
                ab.left + ab.width / 2 - targetCenter.x,
                ab.top + ab.height / 2 - targetCenter.y,
              );
              const bd = Math.hypot(
                bb.left + bb.width / 2 - targetCenter.x,
                bb.top + bb.height / 2 - targetCenter.y,
              );
              return ad - bd;
            })[0];
          }
        }
        if (!panel || !targets.length) {
          window.alert('Select one or more devices and a Panel Enclosure, or place the devices over a panel first.');
          return;
        }
        const targetBounds = combinedBounds(targets);
        if (!targetBounds) return;
        const panelBounds = panel.getBoundingRect();
        const panelRecord = panel as unknown as Record<string, unknown>;
        const panelConfig = normalizeSmartComponentConfig(panelRecord.smartConfig, 'panel-enclosure');
        const headerRatio = panelConfig.kind === 'panel-enclosure'
          ? Math.min(0.35, 58 / Math.max(1, panelConfig.height))
          : 0;
        const interior = {
          left: panelBounds.left,
          top: panelBounds.top + panelBounds.height * headerRatio,
          width: panelBounds.width,
          height: panelBounds.height * (1 - headerRatio),
        };
        const dx = direction === 'vertical'
          ? 0
          : interior.left + interior.width / 2 - (targetBounds.left + targetBounds.width / 2);
        const dy = direction === 'horizontal'
          ? 0
          : interior.top + interior.height / 2 - (targetBounds.top + targetBounds.height / 2);
        moveCanvasObjects(targets, dx, dy);
        active?.setCoords();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      matchObjectSize: (which) => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        const objs = active?.type === 'activeselection'
          ? (active as unknown as { getObjects: () => FabricObject[] }).getObjects()
          : [];
        if (objs.length < 2) return;
        // Use the first selected object as the reference.
        const ref = objs[0].getBoundingRect();
        objs.slice(1).forEach((o) => {
          if ((which === 'width' || which === 'both') && o.width) o.set('scaleX', ref.width / (o.width * (o.scaleX ?? 1)) * (o.scaleX ?? 1));
          if ((which === 'height' || which === 'both') && o.height) o.set('scaleY', ref.height / (o.height * (o.scaleY ?? 1)) * (o.scaleY ?? 1));
          o.setCoords();
        });
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      updateSelected: (patch) => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o) return;
      // S360 TEXT BOX PATCH APPLICATION
      const textBoxPatch = patch as Partial<CanvasSelection>;
      const textBoxObjects: FabricObject[] = o.type === 'activeselection'
        ? (o as ActiveSelection).getObjects()
        : [o];
      textBoxObjects.forEach((item) => {
        if (item.type !== 'textbox' && item.type !== 'text') return;
        const rec = item as unknown as Record<string, unknown>;
        if (textBoxPatch.textBoxFill !== undefined) rec.textBoxFill = textBoxPatch.textBoxFill;
        if (textBoxPatch.textBoxFillOpacity !== undefined) rec.textBoxFillOpacity = textBoxPatch.textBoxFillOpacity;
        if (textBoxPatch.textBoxStroke !== undefined) rec.textBoxStroke = textBoxPatch.textBoxStroke;
        if (textBoxPatch.textBoxStrokeWidth !== undefined) rec.textBoxStrokeWidth = textBoxPatch.textBoxStrokeWidth;
        if (textBoxPatch.textBoxPadding !== undefined) rec.textBoxPadding = textBoxPatch.textBoxPadding;
        if (textBoxPatch.textBoxRadius !== undefined) rec.textBoxRadius = textBoxPatch.textBoxRadius;
        item.dirty = true;
      });
        if ((o.lockMovementX || o.lockScalingX || o.lockRotation) && patch.locked !== false) return;
        const anyO = o as unknown as Record<string, unknown>;
        if (patch.fill !== undefined) o.set('fill', patch.fill);
        if (patch.stroke !== undefined) o.set('stroke', patch.stroke);
        if (patch.strokeWidth !== undefined) o.set('strokeWidth', patch.strokeWidth);
        if (patch.opacity !== undefined) o.set('opacity', patch.opacity);
        if (patch.name !== undefined) anyO.objName = patch.name;
        if (patch.text !== undefined && 'text' in o) {
          o.set('text', patch.text);
          if (typeof anyO.initDimensions === 'function') (anyO.initDimensions as () => void)();
        }
        if (patch.x !== undefined) o.set('left', patch.x);
        if (patch.y !== undefined) o.set('top', patch.y);
        if (patch.angle !== undefined) o.set('angle', patch.angle);
        if (patch.width !== undefined && o.width) o.set('scaleX', patch.width / o.width);
        if (patch.height !== undefined && o.height) o.set('scaleY', patch.height / o.height);
        // Text props — use .set() so Fabric recomputes glyph metrics + re-renders.
        let textChanged = false;
        if (patch.fontSize !== undefined && 'fontSize' in o) { o.set('fontSize', patch.fontSize); textChanged = true; }
        if (patch.bold !== undefined && 'fontWeight' in o) { o.set('fontWeight', patch.bold ? 'bold' : 'normal'); textChanged = true; }
        if (patch.italic !== undefined && 'fontStyle' in o) { o.set('fontStyle', patch.italic ? 'italic' : 'normal'); textChanged = true; }
        if (patch.underline !== undefined && 'underline' in o) { o.set('underline', patch.underline); textChanged = true; }
        if (patch.textAlign !== undefined && 'textAlign' in o) { o.set('textAlign', patch.textAlign); textChanged = true; }
        if (textChanged && typeof anyO.initDimensions === 'function') {
          (anyO.initDimensions as () => void)();
          o.set('dirty', true);
        }
        // Connector / line style props.
        if (patch.dash !== undefined) {
          const w = (anyO.strokeWidth as number) ?? patch.strokeWidth ?? 2;
          o.set('strokeDashArray', dashArray(patch.dash as never, w));
        }
        if (patch.arrowEnd !== undefined && 'arrowEnd' in o) anyO.arrowEnd = patch.arrowEnd;
        if (patch.arrowStart !== undefined && 'arrowStart' in o) anyO.arrowStart = patch.arrowStart;
        if (patch.label !== undefined && 'label' in o) anyO.label = patch.label;
        if (patch.locked !== undefined) {
          o.set({
            lockMovementX: patch.locked,
            lockMovementY: patch.locked,
            lockScalingX: patch.locked,
            lockScalingY: patch.locked,
            lockRotation: patch.locked,
          });
          if ('editable' in o) o.set('editable', !patch.locked);
        }
        o.set('dirty', true);
        o.setCoords();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(o));
      },
      reverseConnectorDirection: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.reverseDirection();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      addVertexToSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.addVertexAtMidpoint();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      deleteVertexFromSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.deleteVertex();
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
      },
      convertSelectedConnector: (kind) => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.convertKind(kind);
        c.requestRenderAll();
        onSerRef.current(normalizeCanvasObjects((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]));
        onSelRef.current(summarize(o));
      },
    };
    registerApi(api);
    return () => registerApi(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registerApi]);

  return (
    <div
      className="canvas-wrap"
      data-action="canvas-selection"
      data-help-id="object.select"
      aria-label="Drawing canvas objects"
      tabIndex={0}
    >
      <canvas ref={canvasRef} className="canvas-surface" />
    </div>
  );
}
