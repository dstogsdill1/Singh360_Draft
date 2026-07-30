import {
  ActiveSelection,
  Canvas,
  FabricImage,
  util,
  type FabricObject,
} from 'fabric';
import { assignFreshCanvasObjectIds, newCanvasObjectId } from './model/canvasObjectIdentity';

const CLIPBOARD_PREFIX = 'SINGH360_CANVAS_V1:';
const SERIAL_PROPS = [
  'objectId',
  'assemblyId',
  'assemblyName',
  'objName',
  'sourceUrl',
  'symCategory',
  'symAcronym',
  'arrowStart',
  'arrowEnd',
  'connectorKind',
  'pointsData',
  'label',
  'stylePreset',
  'wireNumber',
  'labelStart',
  'labelMiddle',
  'labelEnd',
  'layer',
  'pdfSource',
  'pdfPage',
  'pdfDpi',
  'pdfCrop',
  'lockMovementX',
  'lockMovementY',
  'lockScalingX',
  'lockScalingY',
  'lockRotation',
  'editable',
  'selectable',
  'evented',
];

interface SinghClipboardPayload {
  version: 1;
  objects: Record<string, unknown>[];
}

const canvases = new Set<Canvas>();
let lastCanvas: Canvas | null = null;

function canvasElement(canvas: Canvas): HTMLCanvasElement | null {
  const candidate = (canvas as unknown as { upperCanvasEl?: HTMLCanvasElement }).upperCanvasEl;
  return candidate || null;
}

function visible(canvas: Canvas): boolean {
  const element = canvasElement(canvas);
  if (!element?.isConnected) return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 20 && rect.height > 20;
}

function remember(canvas: Canvas): void {
  canvases.add(canvas);
  if (visible(canvas)) lastCanvas = canvas;
}

function currentCanvas(): Canvas | null {
  if (lastCanvas && visible(lastCanvas)) return lastCanvas;
  const candidates = Array.from(canvases).filter(visible);
  const withSelection = candidates.find((canvas) => !!canvas.getActiveObject());
  lastCanvas = withSelection || candidates[candidates.length - 1] || null;
  return lastCanvas;
}

function installCanvasTracking(): void {
  const globalKey = '__singh360ClipboardCanvasTracking';
  const globalObject = window as unknown as Record<string, unknown>;
  if (globalObject[globalKey]) return;
  globalObject[globalKey] = true;

  const prototype = Canvas.prototype as unknown as Record<string, unknown>;

  const originalRequest = prototype.requestRenderAll as (...args: unknown[]) => unknown;
  if (typeof originalRequest === 'function') {
    prototype.requestRenderAll = function trackedRequest(this: Canvas, ...args: unknown[]) {
      remember(this);
      return originalRequest.apply(this, args);
    };
  }

  const originalRender = prototype.renderAll as (...args: unknown[]) => unknown;
  if (typeof originalRender === 'function') {
    prototype.renderAll = function trackedRender(this: Canvas, ...args: unknown[]) {
      remember(this);
      return originalRender.apply(this, args);
    };
  }

  const originalSetActive = prototype.setActiveObject as (...args: unknown[]) => unknown;
  if (typeof originalSetActive === 'function') {
    prototype.setActiveObject = function trackedSetActive(this: Canvas, ...args: unknown[]) {
      remember(this);
      lastCanvas = this;
      return originalSetActive.apply(this, args);
    };
  }
}

function dataUrlToBlob(dataUrl: string): Promise<Blob> {
  return fetch(dataUrl).then((response) => response.blob());
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('Could not read clipboard image.'));
    reader.readAsDataURL(blob);
  });
}

function activePayload(canvas: Canvas): SinghClipboardPayload | null {
  const active = canvas.getActiveObject();
  if (!active) return null;

  return {
    version: 1,
    objects: [
      active.toObject(SERIAL_PROPS) as Record<string, unknown>,
    ],
  };
}

function parsePayload(text: string): SinghClipboardPayload | null {
  if (!text.startsWith(CLIPBOARD_PREFIX)) return null;
  try {
    const payload = JSON.parse(text.slice(CLIPBOARD_PREFIX.length)) as SinghClipboardPayload;
    if (payload.version !== 1 || !Array.isArray(payload.objects)) return null;
    return payload;
  } catch {
    return null;
  }
}

async function addSerializedPayload(
  canvas: Canvas,
  payload: SinghClipboardPayload,
): Promise<boolean> {
  if (!payload.objects.length) return false;

  try {
    const objects = await util.enlivenObjects(
      payload.objects.map((object) => assignFreshCanvasObjectIds(object)),
    ) as FabricObject[];
    if (!objects.length) return false;

    const added: FabricObject[] = [];
    for (const object of objects) {
      object.set({
        left: (object.left ?? 0) + 24,
        top: (object.top ?? 0) + 24,
        selectable: true,
        evented: true,
      });
      object.setCoords();
      canvas.add(object);
      added.push(object);
    }

    if (added.length === 1) {
      canvas.setActiveObject(added[0]);
    } else {
      canvas.setActiveObject(new ActiveSelection(added, { canvas }));
    }
    canvas.requestRenderAll();
    remember(canvas);
    return true;
  } catch (error) {
    console.error('Singh360 editable clipboard paste failed', error);
    return false;
  }
}

async function addImageBlob(canvas: Canvas, blob: Blob): Promise<boolean> {
  try {
    const dataUrl = await blobToDataUrl(blob);
    const image = await FabricImage.fromURL(dataUrl);
    const width = image.width || 1;
    const height = image.height || 1;
    const maxWidth = canvas.getWidth() * 0.7;
    const maxHeight = canvas.getHeight() * 0.7;
    const scale = Math.min(1, maxWidth / width, maxHeight / height);

    image.set({
      left: (canvas.getWidth() - width * scale) / 2,
      top: (canvas.getHeight() - height * scale) / 2,
      scaleX: scale,
      scaleY: scale,
      selectable: true,
      evented: true,
    });
    (image as unknown as Record<string, unknown>).objName = 'Clipboard image';
    (image as unknown as Record<string, unknown>).objectId = newCanvasObjectId();
    canvas.add(image);
    canvas.setActiveObject(image);
    canvas.requestRenderAll();
    remember(canvas);
    return true;
  } catch (error) {
    console.error('Singh360 image clipboard paste failed', error);
    return false;
  }
}

export async function copyActiveCanvasToSystemClipboard(
  showMessage = true,
): Promise<boolean> {
  const canvas = currentCanvas();
  const active = canvas?.getActiveObject();
  if (!canvas || !active) {
    if (showMessage) window.alert('Select the image or object first, then choose Copy.');
    return false;
  }

  const payload = activePayload(canvas);
  if (!payload) return false;
  const text = `${CLIPBOARD_PREFIX}${JSON.stringify(payload)}`;

  try {
    const clipboard = navigator.clipboard;
    if (!clipboard) throw new Error('Clipboard API is unavailable.');

    const itemParts: Record<string, Blob> = {
      'text/plain': new Blob([text], { type: 'text/plain' }),
    };

    try {
      const pngDataUrl = (
        active as FabricObject & {
          toDataURL: (options: Record<string, unknown>) => string;
        }
      ).toDataURL({
        format: 'png',
        multiplier: 2,
        enableRetinaScaling: true,
      });
      itemParts['image/png'] = await dataUrlToBlob(pngDataUrl);
    } catch (error) {
      console.warn('Editable clipboard copied without PNG preview', error);
    }

    if (clipboard.write && typeof ClipboardItem !== 'undefined') {
      await clipboard.write([new ClipboardItem(itemParts)]);
    } else if (clipboard.writeText) {
      await clipboard.writeText(text);
    } else {
      throw new Error('Clipboard write is unavailable.');
    }

    return true;
  } catch (error) {
    console.error('Singh360 clipboard copy failed', error);
    if (showMessage) {
      window.alert('The browser blocked clipboard access. Use Ctrl+C once the object is selected.');
    }
    return false;
  }
}

export async function pasteSystemClipboardToActiveCanvas(
  showMessage = true,
): Promise<boolean> {
  const canvas = currentCanvas();
  if (!canvas) {
    if (showMessage) window.alert('Open a drawing page before pasting.');
    return false;
  }

  try {
    const clipboard = navigator.clipboard;
    if (!clipboard?.read) {
      throw new Error('Clipboard read is unavailable.');
    }

    const items = await clipboard.read();

    for (const item of items) {
      if (!item.types.includes('text/plain')) continue;
      const text = await (await item.getType('text/plain')).text();
      const payload = parsePayload(text);
      if (payload && await addSerializedPayload(canvas, payload)) return true;
    }

    for (const item of items) {
      const imageType = item.types.find((type) => type.startsWith('image/'));
      if (!imageType) continue;
      const blob = await item.getType(imageType);
      if (await addImageBlob(canvas, blob)) return true;
    }

    if (showMessage) window.alert('The clipboard does not contain a Singh360 object or image.');
    return false;
  } catch (error) {
    console.error('Singh360 clipboard paste failed', error);
    if (showMessage) {
      window.alert('The browser blocked right-click Paste. Press Ctrl+V on the drawing page.');
    }
    return false;
  }
}

function installKeyboardBridge(): void {
  const globalKey = '__singh360ClipboardKeyboardBridge';
  const globalObject = window as unknown as Record<string, unknown>;
  if (globalObject[globalKey]) return;
  globalObject[globalKey] = true;

  window.addEventListener('keydown', (event) => {
    const key = event.key.toLowerCase();
    if (!(event.ctrlKey || event.metaKey)) return;

    const target = event.target as HTMLElement | null;
    if (
      target
      && (
        target.tagName === 'INPUT'
        || target.tagName === 'TEXTAREA'
        || target.isContentEditable
      )
    ) {
      return;
    }

    if (key === 'c' && currentCanvas()?.getActiveObject()) {
      event.preventDefault();
      event.stopImmediatePropagation();
      void copyActiveCanvasToSystemClipboard(false);
      return;
    }

    if (key === 'v') {
      event.stopImmediatePropagation();
    }
  }, true);

  window.addEventListener('paste', (event) => {
    const text = event.clipboardData?.getData('text/plain') || '';
    const payload = parsePayload(text);
    if (!payload) return;

    const canvas = currentCanvas();
    if (!canvas) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    void addSerializedPayload(canvas, payload);
  }, true);
}

installCanvasTracking();
installKeyboardBridge();
