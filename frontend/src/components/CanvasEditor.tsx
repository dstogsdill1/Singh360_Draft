import { useEffect, useRef } from 'react';
import { Canvas, Rect, Circle, Textbox, Line, Triangle, Group, ActiveSelection, FabricImage, type FabricObject } from 'fabric';
import type { CanvasApi, CanvasSelection } from '../model/types';

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

const CANVAS_W = 1560;
const CANVAS_H = 860;
const SNAP = 16;

function summarize(obj: FabricObject): CanvasSelection {
  const anyObj = obj as unknown as Record<string, unknown>;
  return {
    type: (obj.type as string) || 'object',
    name: typeof anyObj.objName === 'string' ? (anyObj.objName as string) : undefined,
    fill: typeof anyObj.fill === 'string' ? (anyObj.fill as string) : '',
    stroke: typeof anyObj.stroke === 'string' ? (anyObj.stroke as string) : '',
    strokeWidth: (anyObj.strokeWidth as number) ?? 1,
    opacity: typeof anyObj.opacity === 'number' ? (anyObj.opacity as number) : 1,
    fontSize: typeof anyObj.fontSize === 'number' ? (anyObj.fontSize as number) : undefined,
    x: Math.round(obj.left ?? 0),
    y: Math.round(obj.top ?? 0),
    width: Math.round((obj.width ?? 0) * (obj.scaleX ?? 1)),
    height: Math.round((obj.height ?? 0) * (obj.scaleY ?? 1)),
    angle: Math.round(obj.angle ?? 0),
    locked: obj.lockMovementX === true,
  };
}

function makeText(x: number, y: number) {
  return new Textbox('Text', { left: x, top: y, width: 200, fontSize: 20, fill: '#111' });
}
function makeRect(x: number, y: number) {
  return new Rect({ left: x, top: y, width: 180, height: 90, fill: 'transparent', stroke: '#111', strokeWidth: 1.5 });
}
function makeCircle(x: number, y: number) {
  return new Circle({ left: x, top: y, radius: 60, fill: 'transparent', stroke: '#111', strokeWidth: 1.5 });
}
function makeLine(x: number, y: number) {
  return new Line([x, y, x + 200, y], { stroke: '#111', strokeWidth: 2 });
}
function makeArrow(x: number, y: number) {
  const line = new Line([0, 8, 180, 8], { stroke: '#111', strokeWidth: 2 });
  const head = new Triangle({ left: 180, top: 0, width: 18, height: 16, angle: 90, fill: '#111' });
  return new Group([line, head], { left: x, top: y });
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

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = new Canvas(canvasRef.current, {
      width: CANVAS_W,
      height: CANVAS_H,
      selection: true,
      backgroundColor: '',
    });
    fabricRef.current = canvas;

    const persist = () => {
      if (restoringRef.current) return;
      onSerRef.current((canvas.toObject(['objName']).objects ?? []) as Record<string, unknown>[]);
    };
    const pushHistory = () => {
      if (restoringRef.current) return;
      const snapshot = JSON.stringify(canvas.toObject(['objName']));
      const hist = historyRef.current.slice(0, histIdxRef.current + 1);
      hist.push(snapshot);
      historyRef.current = hist;
      histIdxRef.current = hist.length - 1;
    };
    const onChanged = () => {
      persist();
      pushHistory();
    };

    if (serialized.length) {
      void canvas.loadFromJSON({ version: '6', objects: serialized }).then(() => canvas.renderAll());
    }
    historyRef.current = [JSON.stringify(canvas.toObject(['objName']))];
    histIdxRef.current = 0;

    canvas.on('object:modified', onChanged);
    canvas.on('object:added', onChanged);
    canvas.on('object:removed', onChanged);
    canvas.on('selection:created', () => {
      const o = canvas.getActiveObject();
      if (o) onSelRef.current(summarize(o));
    });
    canvas.on('selection:updated', () => {
      const o = canvas.getActiveObject();
      if (o) onSelRef.current(summarize(o));
    });
    canvas.on('selection:cleared', () => onSelRef.current(null));
    canvas.on('object:moving', (e) => {
      const t = e.target;
      if (!t) return;
      // Center snap: snap object center to the canvas centre when close.
      const cx = (t.left ?? 0) + ((t.width ?? 0) * (t.scaleX ?? 1)) / 2;
      const cy = (t.top ?? 0) + ((t.height ?? 0) * (t.scaleY ?? 1)) / 2;
      const midX = CANVAS_W / 2;
      const midY = CANVAS_H / 2;
      if (Math.abs(cx - midX) < 8) t.set({ left: midX - ((t.width ?? 0) * (t.scaleX ?? 1)) / 2 });
      if (Math.abs(cy - midY) < 8) t.set({ top: midY - ((t.height ?? 0) * (t.scaleY ?? 1)) / 2 });
      // Grid snap (when Snap is on).
      if (snapRef.current) {
        t.set({
          left: Math.round((t.left ?? 0) / SNAP) * SNAP,
          top: Math.round((t.top ?? 0) / SNAP) * SNAP,
        });
      }
    });
    canvas.on('mouse:down', (opt) => {
      const tool = toolRef.current;
      if (tool === 'select' || opt.target) return;
      const p = canvas.getScenePoint(opt.e);
      let obj: FabricObject | null = null;
      if (tool === 'text') obj = makeText(p.x, p.y);
      else if (tool === 'rectangle') obj = makeRect(p.x, p.y);
      else if (tool === 'circle') obj = makeCircle(p.x, p.y);
      else if (tool === 'line') obj = makeLine(p.x, p.y);
      else if (tool === 'arrow') obj = makeArrow(p.x, p.y);
      if (obj) {
        canvas.add(obj);
        canvas.setActiveObject(obj);
        canvas.requestRenderAll();
      }
      consumeRef.current();
    });

    return () => {
      void canvas.dispose();
      fabricRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Smart pointer pass-through: the overlay is only "grabbable" when the cursor
  // is over an overlay object, when a draw tool is active, or when overlay edit
  // mode is forced on. Otherwise clicks fall through to the base content layer
  // (editable tables / text). This makes objects behave like PowerPoint/Visio
  // without a hidden mode toggle.
  useEffect(() => {
    const canvasEl = canvasRef.current;
    if (!canvasEl) return;
    const overlayEl = canvasEl.parentElement?.parentElement as HTMLElement | null; // .np-overlay-layer
    const rootEl = overlayEl?.parentElement as HTMLElement | null; // .np-page-root
    if (!overlayEl || !rootEl) return;

    const setInteractive = (on: boolean) => {
      overlayEl.style.pointerEvents = on ? 'auto' : 'none';
    };

    const overPoint = (clientX: number, clientY: number): boolean => {
      const canvas = fabricRef.current;
      if (!canvas) return false;
      const rect = canvasEl.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return false;
      const x = ((clientX - rect.left) / rect.width) * CANVAS_W;
      const y = ((clientY - rect.top) / rect.height) * CANVAS_H;
      return canvas.getObjects().some((o) => {
        const b = o.getBoundingRect();
        return x >= b.left - 4 && x <= b.left + b.width + 4 && y >= b.top - 4 && y <= b.top + b.height + 4;
      });
    };

    const onMove = (ev: MouseEvent) => {
      if (overlayModeRef.current || toolRef.current !== 'select') {
        setInteractive(true);
        return;
      }
      // When actively dragging/selecting, keep it interactive.
      const canvas = fabricRef.current;
      if (canvas && canvas.getActiveObject()) {
        setInteractive(true);
        return;
      }
      setInteractive(overPoint(ev.clientX, ev.clientY));
    };
    const onLeave = () => {
      if (!overlayModeRef.current && toolRef.current === 'select') setInteractive(false);
    };

    rootEl.addEventListener('mousemove', onMove);
    rootEl.addEventListener('mouseleave', onLeave);
    return () => {
      rootEl.removeEventListener('mousemove', onMove);
      rootEl.removeEventListener('mouseleave', onLeave);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addObj = (obj: FabricObject) => {
    const c = fabricRef.current;
    if (!c) return;
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
      onSerRef.current((c.toObject(['objName']).objects ?? []) as Record<string, unknown>[]);
    });
  };

  useEffect(() => {
    const api: CanvasApi = {
      addText: () => addObj(makeText(200, 160)),
      addRect: () => addObj(makeRect(200, 200)),
      addCircle: () => addObj(makeCircle(200, 200)),
      addLine: () => addObj(makeLine(200, 260)),
      addArrow: () => addObj(makeArrow(200, 320)),
      addImage: (url: string, name?: string) => {
        const c = fabricRef.current;
        if (!c) return;
        void FabricImage.fromURL(url, { crossOrigin: 'anonymous' }).then((img) => {
          const maxW = CANVAS_W * 0.6;
          const maxH = CANVAS_H * 0.6;
          const iw = img.width || 1;
          const ih = img.height || 1;
          const scale = Math.min(1, maxW / iw, maxH / ih);
          img.set({
            left: (CANVAS_W - iw * scale) / 2,
            top: (CANVAS_H - ih * scale) / 2,
            scaleX: scale,
            scaleY: scale,
          });
          (img as unknown as Record<string, unknown>).objName = name || 'image';
          c.add(img);
          c.setActiveObject(img);
          c.requestRenderAll();
        });
      },
      deleteSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o) {
          c.remove(o);
          c.discardActiveObject();
          c.requestRenderAll();
        }
      },
      duplicateSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o) return;
        void o.clone().then((clone: FabricObject) => {
          clone.set({ left: (o.left ?? 0) + 20, top: (o.top ?? 0) + 20 });
          c.add(clone);
          c.setActiveObject(clone);
          c.requestRenderAll();
        });
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
          const grp = new Group(objs);
          objs.forEach((o) => c.remove(o));
          c.add(grp);
          c.setActiveObject(grp);
          c.requestRenderAll();
        }
      },
      ungroup: () => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        if (active && active.type === 'group') {
          const grp = active as Group;
          const items = grp.removeAll();
          c.remove(grp);
          items.forEach((o) => c.add(o as FabricObject));
          c.requestRenderAll();
        }
      },
      bringForward: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o) { c.bringObjectForward(o); c.requestRenderAll(); }
      },
      sendBackward: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o) { c.sendObjectBackwards(o); c.requestRenderAll(); }
      },
      bringToFront: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o) { c.bringObjectToFront(o); c.requestRenderAll(); }
      },
      sendToBack: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (c && o) { c.sendObjectToBack(o); c.requestRenderAll(); }
      },
      updateSelected: (patch) => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o) return;
        if (patch.fill !== undefined) o.set('fill', patch.fill);
        if (patch.stroke !== undefined) o.set('stroke', patch.stroke);
        if (patch.strokeWidth !== undefined) o.set('strokeWidth', patch.strokeWidth);
        if (patch.opacity !== undefined) o.set('opacity', patch.opacity);
        if (patch.name !== undefined) (o as unknown as Record<string, unknown>).objName = patch.name;
        if (patch.x !== undefined) o.set('left', patch.x);
        if (patch.y !== undefined) o.set('top', patch.y);
        if (patch.angle !== undefined) o.set('angle', patch.angle);
        if (patch.width !== undefined && o.width) o.set('scaleX', patch.width / o.width);
        if (patch.height !== undefined && o.height) o.set('scaleY', patch.height / o.height);
        if (patch.fontSize !== undefined && 'fontSize' in o) {
          (o as unknown as Record<string, unknown>).fontSize = patch.fontSize;
        }
        if (patch.locked !== undefined) {
          o.set({
            lockMovementX: patch.locked,
            lockMovementY: patch.locked,
            lockScalingX: patch.locked,
            lockScalingY: patch.locked,
            lockRotation: patch.locked,
          });
        }
        o.setCoords();
        c.requestRenderAll();
        onSerRef.current((c.toObject(['objName']).objects ?? []) as Record<string, unknown>[]);
        onSelRef.current(summarize(o));
      },
    };
    registerApi(api);
    return () => registerApi(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registerApi]);

  return (
    <div className="canvas-wrap">
      <canvas ref={canvasRef} className="canvas-surface" />
    </div>
  );
}
