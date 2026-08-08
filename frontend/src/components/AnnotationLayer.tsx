import { useEffect, useRef, useState } from 'react';
import {
  Canvas,
  Line,
  PencilBrush,
  Rect,
  Textbox,
  type FabricObject,
} from 'fabric';
import { Connector } from './connector';
import { BODY_H, BODY_W } from '../model/sheetGeometry';
import { newCanvasObjectId } from '../model/canvasObjectIdentity';
import type {
  AnnotationApi,
  AnnotationSelection,
  AnnotationSettings,
  AnnotationStyle,
  AnnotationTool,
} from '../model/types';

interface Props {
  pageId: string;
  serialized: Record<string, unknown>[];
  settings: AnnotationSettings;
  active: boolean;
  tool: AnnotationTool;
  style: AnnotationStyle;
  exporting?: boolean;
  onSerializedChange?: (objects: Record<string, unknown>[]) => void;
  onSelectionChange?: (selection: AnnotationSelection | null) => void;
  onToolChange?: (tool: AnnotationTool) => void;
  registerApi?: (api: AnnotationApi | null) => void;
}

type AnnotationRecord = Record<string, unknown> & {
  annotationType?: string;
  annotationFillColor?: string;
  annotationFillOpacity?: number;
  annotationBackgroundColor?: string;
  annotationBackgroundOpacity?: number;
  annotationSmoothing?: number;
  objectId?: string;
};

type AnnotationAuditWindow = Window & {
  __S360_ANNOTATION_AUDIT__?: {
    objects: () => Record<string, unknown>[];
    selectByType: (type: string) => boolean;
    isTextEditing: () => boolean;
    canvasBounds: () => { left: number; top: number; width: number; height: number };
  };
};

const SER_PROPS = [
  'objectId',
  'annotationType',
  'annotationFillColor',
  'annotationFillOpacity',
  'annotationBackgroundColor',
  'annotationBackgroundOpacity',
  'annotationSmoothing',
  'arrowStart',
  'arrowEnd',
  'connectorKind',
  'pointsData',
  'objName',
  'selectable',
  'evented',
  'editable',
  'visible',
];

const VERSION = '6.0.0';
const NOOP = () => undefined;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function rgba(color: string, opacity: number): string {
  const value = color.trim();
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(value);
  const full = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(value);
  if (short) {
    const [r, g, b] = short.slice(1).map((part) => parseInt(`${part}${part}`, 16));
    return `rgba(${r}, ${g}, ${b}, ${clamp(opacity, 0, 1)})`;
  }
  if (full) {
    const [r, g, b] = full.slice(1).map((part) => parseInt(part, 16));
    return `rgba(${r}, ${g}, ${b}, ${clamp(opacity, 0, 1)})`;
  }
  return opacity <= 0 ? 'transparent' : value;
}

function annotationRecord(object: FabricObject): AnnotationRecord {
  return object as unknown as AnnotationRecord;
}

function annotationType(object: FabricObject): AnnotationSelection['annotationType'] {
  const value = String(annotationRecord(object).annotationType || '').toLowerCase();
  if (value === 'rectangle' || value === 'text' || value === 'arrow' || value === 'highlight' || value === 'pen') {
    return value;
  }
  if (object.type === 'textbox' || object.type === 'i-text' || object.type === 'text') return 'text';
  if (object.type === 'rect') return 'rectangle';
  if (object.type === 'Connector') return 'arrow';
  if (object.type === 'path') return 'pen';
  return 'highlight';
}

function ensureIdentity(object: FabricObject, kind?: AnnotationSelection['annotationType']): void {
  const record = annotationRecord(object);
  if (!record.objectId) record.objectId = newCanvasObjectId();
  if (kind) record.annotationType = kind;
}

function serialize(canvas: Canvas): Record<string, unknown>[] {
  const objects = (canvas.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[];
  return objects.map((object) => structuredClone(object));
}

function summarize(object: FabricObject): AnnotationSelection {
  const record = annotationRecord(object);
  const kind = annotationType(object);
  const isText = kind === 'text';
  return {
    objectId: String(record.objectId || ''),
    annotationType: kind,
    color: String(isText ? object.fill || '#d71920' : object.stroke || '#d71920'),
    opacity: Number(object.opacity ?? 1),
    strokeWidth: Number(object.strokeWidth ?? 1),
    fillColor: String(record.annotationFillColor || '#d71920'),
    fillOpacity: Number(record.annotationFillOpacity ?? 0),
    fontSize: Number((object as Textbox).fontSize || 18),
    bold: (object as Textbox).fontWeight === 'bold' || (object as Textbox).fontWeight === 700,
    backgroundColor: String(record.annotationBackgroundColor || '#ffffff'),
    backgroundOpacity: Number(record.annotationBackgroundOpacity ?? 0),
    smoothing: Number(record.annotationSmoothing ?? 2),
    arrowEnd: kind === 'arrow' ? Boolean((object as Connector).arrowEnd) : undefined,
  };
}

function applyRectangleFill(object: FabricObject): void {
  const record = annotationRecord(object);
  const fillColor = String(record.annotationFillColor || '#d71920');
  const fillOpacity = Number(record.annotationFillOpacity ?? 0);
  object.set({ fill: fillOpacity <= 0 ? 'transparent' : rgba(fillColor, fillOpacity) });
}

function applyTextBackground(object: FabricObject): void {
  const record = annotationRecord(object);
  const backgroundColor = String(record.annotationBackgroundColor || '#ffffff');
  const backgroundOpacity = Number(record.annotationBackgroundOpacity ?? 0);
  object.set({
    backgroundColor: backgroundOpacity <= 0
      ? 'transparent'
      : rgba(backgroundColor, backgroundOpacity),
  });
}

export default function AnnotationLayer({
  pageId,
  serialized,
  settings,
  active,
  tool,
  style,
  exporting = false,
  onSerializedChange = NOOP,
  onSelectionChange = NOOP,
  onToolChange = NOOP,
  registerApi = NOOP,
}: Props) {
  const canvasElementRef = useRef<HTMLCanvasElement | null>(null);
  const fabricRef = useRef<Canvas | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const activeRef = useRef(active);
  const exportingRef = useRef(exporting);
  const settingsRef = useRef(settings);
  const styleRef = useRef(style);
  const toolRef = useRef(tool);
  const onSerializedRef = useRef(onSerializedChange);
  const onSelectionRef = useRef(onSelectionChange);
  const onToolRef = useRef(onToolChange);
  const historyRef = useRef<string[]>([]);
  const historyIndexRef = useRef(-1);
  const restoringRef = useRef(false);
  const lastLoadedRef = useRef('');
  const lastEmittedRef = useRef('');
  const clipboardRef = useRef<FabricObject | null>(null);
  const loadObjectsRef = useRef<(objects: Record<string, unknown>[], resetHistory: boolean) => Promise<void>>();

  activeRef.current = active;
  exportingRef.current = exporting;
  settingsRef.current = settings;
  styleRef.current = style;
  toolRef.current = tool;
  onSerializedRef.current = onSerializedChange;
  onSelectionRef.current = onSelectionChange;
  onToolRef.current = onToolChange;

  useEffect(() => {
    if (!canvasElementRef.current) return;
    let disposed = false;
    const canvas = new Canvas(canvasElementRef.current, {
      width: BODY_W,
      height: BODY_H,
      backgroundColor: '',
      selection: false,
      targetFindTolerance: 12,
      perPixelTargetFind: false,
    });
    fabricRef.current = canvas;

    const canInteract = () => (
      activeRef.current
      && settingsRef.current.visible
      && !settingsRef.current.locked
      && !exportingRef.current
    );

    const applyInteraction = () => {
      const interactive = canInteract();
      const selecting = interactive && toolRef.current === 'select';
      canvas.selection = selecting;
      canvas.isDrawingMode = interactive && toolRef.current === 'pen';
      canvas.defaultCursor = interactive && toolRef.current !== 'select' ? 'crosshair' : 'default';
      canvas.hoverCursor = selecting ? 'move' : canvas.defaultCursor;
      if (canvas.isDrawingMode) {
        const brush = new PencilBrush(canvas);
        brush.color = styleRef.current.color;
        brush.width = styleRef.current.penWidth;
        brush.decimate = styleRef.current.smoothing;
        canvas.freeDrawingBrush = brush;
      }
      canvas.getObjects().forEach((object) => {
        object.set({
          selectable: selecting,
          evented: selecting,
          hasControls: selecting,
          hasBorders: selecting,
        });
        if (object instanceof Textbox) object.editable = selecting;
      });
      if (!selecting) {
        canvas.discardActiveObject();
        onSelectionRef.current(null);
      }
      canvas.requestRenderAll();
    };

    const snapshot = () => JSON.stringify({ version: VERSION, objects: serialize(canvas) });

    const pushHistory = () => {
      if (restoringRef.current) return;
      const value = snapshot();
      const previous = historyRef.current[historyIndexRef.current];
      if (value === previous) return;
      const next = historyRef.current.slice(0, historyIndexRef.current + 1);
      next.push(value);
      historyRef.current = next.slice(-100);
      historyIndexRef.current = historyRef.current.length - 1;
    };

    const emit = (recordHistory = true) => {
      if (disposed || restoringRef.current) return;
      const objects = serialize(canvas);
      const value = JSON.stringify(objects);
      lastLoadedRef.current = value;
      lastEmittedRef.current = value;
      if (recordHistory) pushHistory();
      onSerializedRef.current(objects);
    };

    const loadObjects = async (objects: Record<string, unknown>[], resetHistory: boolean) => {
      restoringRef.current = true;
      setHydrated(false);
      try {
        await canvas.loadFromJSON({ version: VERSION, objects });
        if (disposed) return;
        canvas.getObjects().forEach((object) => ensureIdentity(object));
        lastLoadedRef.current = JSON.stringify(objects);
        applyInteraction();
        const value = snapshot();
        if (resetHistory) {
          historyRef.current = [value];
          historyIndexRef.current = 0;
        }
        canvas.requestRenderAll();
      } finally {
        restoringRef.current = false;
        if (!disposed) setHydrated(true);
      }
    };
    loadObjectsRef.current = loadObjects;

    const restoreHistory = async (index: number) => {
      if (index < 0 || index >= historyRef.current.length) return;
      const parsed = JSON.parse(historyRef.current[index]) as {
        objects?: Record<string, unknown>[];
      };
      await loadObjects(parsed.objects ?? [], false);
      historyIndexRef.current = index;
      emit(false);
    };

    const scenePoint = (event: Event): { x: number; y: number } => {
      const rect = canvas.upperCanvasEl.getBoundingClientRect();
      const pointer = event as PointerEvent;
      return {
        x: clamp(((pointer.clientX - rect.left) / Math.max(1, rect.width)) * BODY_W, 0, BODY_W),
        y: clamp(((pointer.clientY - rect.top) / Math.max(1, rect.height)) * BODY_H, 0, BODY_H),
      };
    };

    let start: { x: number; y: number } | null = null;
    let draft: FabricObject | null = null;

    const selectCreated = (object: FabricObject) => {
      toolRef.current = 'select';
      onToolRef.current('select');
      applyInteraction();
      canvas.setActiveObject(object);
      canvas.requestRenderAll();
      onSelectionRef.current(summarize(object));
    };

    canvas.on('mouse:down', (event) => {
      if (!canInteract() || toolRef.current === 'select' || toolRef.current === 'pen') return;
      const point = scenePoint(event.e);
      start = point;
      const currentStyle = styleRef.current;
      if (toolRef.current === 'text') {
        const text = new Textbox('Text', {
          left: point.x,
          top: point.y,
          width: 240,
          fontFamily: 'Arial',
          fontSize: currentStyle.fontSize,
          fontWeight: currentStyle.bold ? 'bold' : 'normal',
          fill: currentStyle.color,
          opacity: currentStyle.opacity,
          padding: 6,
          editable: true,
        });
        ensureIdentity(text, 'text');
        Object.assign(annotationRecord(text), {
          annotationBackgroundColor: currentStyle.backgroundColor,
          annotationBackgroundOpacity: currentStyle.backgroundOpacity,
        });
        applyTextBackground(text);
        canvas.add(text);
        selectCreated(text);
        text.enterEditing();
        text.selectAll();
        emit();
        start = null;
        return;
      }
      if (toolRef.current === 'rectangle') {
        const rectangle = new Rect({
          left: point.x,
          top: point.y,
          width: 1,
          height: 1,
          fill: 'transparent',
          stroke: currentStyle.color,
          strokeWidth: currentStyle.strokeWidth,
          strokeUniform: true,
          opacity: currentStyle.opacity,
        });
        ensureIdentity(rectangle, 'rectangle');
        Object.assign(annotationRecord(rectangle), {
          annotationFillColor: currentStyle.fillColor,
          annotationFillOpacity: currentStyle.fillOpacity,
        });
        applyRectangleFill(rectangle);
        draft = rectangle;
      } else if (toolRef.current === 'arrow') {
        const arrow = new Connector([point.x, point.y, point.x + 1, point.y + 1], {
          stroke: currentStyle.color,
          strokeWidth: currentStyle.strokeWidth,
          opacity: currentStyle.opacity,
          arrowEnd: true,
          connectorKind: 'arrow',
          objName: 'Annotation Arrow',
        });
        ensureIdentity(arrow, 'arrow');
        draft = arrow;
      } else if (toolRef.current === 'highlight') {
        const highlight = new Line([point.x, point.y, point.x + 1, point.y + 1], {
          stroke: currentStyle.highlightColor,
          strokeWidth: currentStyle.highlightWidth,
          strokeLineCap: 'round',
          strokeUniform: true,
          opacity: currentStyle.highlightOpacity,
          globalCompositeOperation: 'multiply',
        });
        ensureIdentity(highlight, 'highlight');
        draft = highlight;
      }
      if (draft) canvas.add(draft);
    });

    canvas.on('mouse:move', (event) => {
      if (!draft || !start) return;
      const point = scenePoint(event.e);
      if (draft instanceof Rect) {
        draft.set({
          left: Math.min(start.x, point.x),
          top: Math.min(start.y, point.y),
          width: Math.max(1, Math.abs(point.x - start.x)),
          height: Math.max(1, Math.abs(point.y - start.y)),
        });
      } else if (draft instanceof Connector) {
        draft.setAbsPoints([start, point]);
      } else if (draft instanceof Line) {
        draft.set({ x1: start.x, y1: start.y, x2: point.x, y2: point.y });
      }
      draft.setCoords();
      canvas.requestRenderAll();
    });

    canvas.on('mouse:up', (event) => {
      if (!draft || !start) return;
      const point = scenePoint(event.e);
      if (Math.hypot(point.x - start.x, point.y - start.y) < 6) {
        if (draft instanceof Rect) draft.set({ width: 140, height: 80 });
        else if (draft instanceof Connector) draft.setAbsPoints([start, { x: start.x + 180, y: start.y + 60 }]);
        else if (draft instanceof Line) draft.set({ x2: start.x + 180, y2: start.y });
      }
      const completed = draft;
      completed.setCoords();
      draft = null;
      start = null;
      selectCreated(completed);
      emit();
    });

    canvas.on('path:created', (event) => {
      const path = event.path;
      if (!path) return;
      const currentStyle = styleRef.current;
      ensureIdentity(path, 'pen');
      annotationRecord(path).annotationSmoothing = currentStyle.smoothing;
      path.set({
        stroke: currentStyle.color,
        strokeWidth: currentStyle.penWidth,
        opacity: currentStyle.opacity,
        fill: '',
        strokeLineCap: 'round',
        strokeLineJoin: 'round',
      });
      selectCreated(path);
      emit();
    });

    canvas.on('selection:created', (event) => {
      onSelectionRef.current(event.selected?.[0] ? summarize(event.selected[0]) : null);
    });
    canvas.on('selection:updated', (event) => {
      onSelectionRef.current(event.selected?.[0] ? summarize(event.selected[0]) : null);
    });
    canvas.on('selection:cleared', () => onSelectionRef.current(null));
    canvas.on('object:modified', () => emit());
    canvas.on('text:editing:exited', () => emit());
    canvas.on('mouse:dblclick', (event) => {
      if (!canInteract() || !event.target) return;
      canvas.setActiveObject(event.target);
      onSelectionRef.current(summarize(event.target));
      if (event.target instanceof Textbox) {
        event.target.enterEditing();
        event.target.selectAll();
        canvas.requestRenderAll();
      }
    });

    const cloneSelected = async (source: FabricObject, offset = 18): Promise<FabricObject> => {
      const clone = await source.clone(SER_PROPS);
      ensureIdentity(clone, annotationType(source));
      annotationRecord(clone).objectId = newCanvasObjectId();
      clone.set({
        left: Number(clone.left || 0) + offset,
        top: Number(clone.top || 0) + offset,
      });
      return clone;
    };

    const api: AnnotationApi = {
      captureAnnotations: () => serialize(canvas),
      deleteSelected: () => {
        if (settingsRef.current.locked) return;
        const selected = canvas.getActiveObjects();
        if (!selected.length) return;
        canvas.discardActiveObject();
        canvas.remove(...selected);
        onSelectionRef.current(null);
        emit();
      },
      deleteAll: () => {
        if (settingsRef.current.locked) return;
        canvas.discardActiveObject();
        canvas.remove(...canvas.getObjects());
        onSelectionRef.current(null);
        emit();
      },
      copySelected: () => {
        const selected = canvas.getActiveObject();
        if (!selected) return;
        void selected.clone(SER_PROPS).then((copy) => { clipboardRef.current = copy; });
      },
      pasteCopied: () => {
        if (!clipboardRef.current || settingsRef.current.locked) return;
        void cloneSelected(clipboardRef.current, 22).then((copy) => {
          canvas.add(copy);
          canvas.setActiveObject(copy);
          onSelectionRef.current(summarize(copy));
          emit();
        });
      },
      duplicateSelected: () => {
        const selected = canvas.getActiveObject();
        if (!selected || settingsRef.current.locked) return;
        void cloneSelected(selected).then((copy) => {
          canvas.add(copy);
          canvas.setActiveObject(copy);
          onSelectionRef.current(summarize(copy));
          emit();
        });
      },
      bringForward: () => {
        const selected = canvas.getActiveObject();
        if (!selected || settingsRef.current.locked) return;
        canvas.bringObjectForward(selected);
        emit();
      },
      sendBackward: () => {
        const selected = canvas.getActiveObject();
        if (!selected || settingsRef.current.locked) return;
        canvas.sendObjectBackwards(selected);
        emit();
      },
      undo: () => { void restoreHistory(historyIndexRef.current - 1); },
      redo: () => { void restoreHistory(historyIndexRef.current + 1); },
      deselect: () => {
        canvas.discardActiveObject();
        canvas.requestRenderAll();
        onSelectionRef.current(null);
      },
      updateSelected: (patch) => {
        const selected = canvas.getActiveObject();
        if (!selected || settingsRef.current.locked) return;
        const kind = annotationType(selected);
        const record = annotationRecord(selected);
        if (patch.color !== undefined) {
          if (kind === 'text') selected.set({ fill: patch.color });
          else selected.set({ stroke: patch.color });
        }
        if (patch.opacity !== undefined) selected.set({ opacity: clamp(patch.opacity, 0.1, 1) });
        if (patch.strokeWidth !== undefined) selected.set({ strokeWidth: Math.max(1, patch.strokeWidth) });
        if (patch.fillColor !== undefined) record.annotationFillColor = patch.fillColor;
        if (patch.fillOpacity !== undefined) record.annotationFillOpacity = clamp(patch.fillOpacity, 0, 1);
        if (kind === 'rectangle' && (patch.fillColor !== undefined || patch.fillOpacity !== undefined)) {
          applyRectangleFill(selected);
        }
        if (patch.fontSize !== undefined && selected instanceof Textbox) {
          selected.set({ fontSize: clamp(patch.fontSize, 8, 96) });
        }
        if (patch.bold !== undefined && selected instanceof Textbox) {
          selected.set({ fontWeight: patch.bold ? 'bold' : 'normal' });
        }
        if (patch.backgroundColor !== undefined) record.annotationBackgroundColor = patch.backgroundColor;
        if (patch.backgroundOpacity !== undefined) {
          record.annotationBackgroundOpacity = clamp(patch.backgroundOpacity, 0, 1);
        }
        if (
          kind === 'text'
          && (patch.backgroundColor !== undefined || patch.backgroundOpacity !== undefined)
        ) applyTextBackground(selected);
        if (patch.smoothing !== undefined) record.annotationSmoothing = clamp(patch.smoothing, 0, 10);
        if (patch.arrowEnd !== undefined && selected instanceof Connector) {
          selected.arrowEnd = patch.arrowEnd;
        }
        selected.setCoords();
        canvas.requestRenderAll();
        onSelectionRef.current(summarize(selected));
        emit();
      },
    };
    registerApi(api);

    const auditWindow = window as AnnotationAuditWindow;
    if (new URLSearchParams(window.location.search).get('annotationAudit') === '1') {
      auditWindow.__S360_ANNOTATION_AUDIT__ = {
        objects: () => serialize(canvas),
        selectByType: (type) => {
          const object = canvas.getObjects().find((candidate) => annotationType(candidate) === type);
          if (!object) return false;
          canvas.setActiveObject(object);
          canvas.requestRenderAll();
          onSelectionRef.current(summarize(object));
          return true;
        },
        isTextEditing: () => canvas.getObjects().some(
          (candidate) => candidate instanceof Textbox && candidate.isEditing,
        ),
        canvasBounds: () => {
          const rect = canvas.upperCanvasEl.getBoundingClientRect();
          return { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
        },
      };
    }

    void loadObjects(serialized, true);

    return () => {
      disposed = true;
      registerApi(null);
      loadObjectsRef.current = undefined;
      if (auditWindow.__S360_ANNOTATION_AUDIT__) delete auditWindow.__S360_ANNOTATION_AUDIT__;
      canvas.dispose();
      fabricRef.current = null;
    };
    // The Fabric canvas owns long-lived handlers; latest props flow through refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageId]);

  useEffect(() => {
    const canvas = fabricRef.current;
    if (!canvas || !hydrated) return;
    const interactive = active && settings.visible && !settings.locked && !exporting;
    const selecting = interactive && tool === 'select';
    canvas.selection = selecting;
    canvas.isDrawingMode = interactive && tool === 'pen';
    canvas.defaultCursor = interactive && tool !== 'select' ? 'crosshair' : 'default';
    canvas.hoverCursor = selecting ? 'move' : canvas.defaultCursor;
    if (canvas.isDrawingMode) {
      const brush = new PencilBrush(canvas);
      brush.color = style.color;
      brush.width = style.penWidth;
      brush.decimate = style.smoothing;
      canvas.freeDrawingBrush = brush;
    }
    canvas.getObjects().forEach((object) => {
      object.set({ selectable: selecting, evented: selecting, hasControls: selecting, hasBorders: selecting });
      if (object instanceof Textbox) object.editable = selecting;
    });
    if (!selecting) {
      canvas.discardActiveObject();
      onSelectionRef.current(null);
    }
    canvas.requestRenderAll();
  }, [active, exporting, hydrated, settings.locked, settings.visible, style, tool]);

  useEffect(() => {
    if (!hydrated || !loadObjectsRef.current) return;
    const value = JSON.stringify(serialized);
    if (value === lastLoadedRef.current || value === lastEmittedRef.current) return;
    void loadObjectsRef.current(serialized, true);
  }, [hydrated, serialized]);

  const renderVisible = exporting ? settings.includeInExport : settings.visible;
  const interactive = active && settings.visible && !settings.locked && !exporting;

  return (
    <div
      className={`annotation-layer ${interactive ? 'interactive' : ''} ${renderVisible ? 'visible' : 'hidden'}`}
      data-testid="annotation-layer"
      data-page-id={pageId}
      data-export-included={settings.includeInExport ? 'true' : 'false'}
      aria-hidden={!renderVisible}
      style={{
        pointerEvents: interactive ? 'auto' : 'none',
        visibility: renderVisible ? 'visible' : 'hidden',
      }}
    >
      <div
        className="annotation-canvas-wrap"
        data-annotation-hydrated={hydrated ? '1' : '0'}
      >
        <canvas ref={canvasElementRef} className="annotation-canvas-surface" />
      </div>
    </div>
  );
}
