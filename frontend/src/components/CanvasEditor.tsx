import { useEffect, useRef } from 'react';
import { Canvas, Rect, Textbox, Line, Triangle, Group, FabricImage, type FabricObject } from 'fabric';
import type { CanvasApi, CanvasSelection } from '../model/types';

interface Props {
  serialized: Record<string, unknown>[];
  onSerializedChange: (value: Record<string, unknown>[]) => void;
  registerApi: (api: CanvasApi | null) => void;
  onSelectionChange: (sel: CanvasSelection | null) => void;
  activeTool: string;
  onToolConsumed: () => void;
  snap: boolean;
}

const CANVAS_W = 1560;
const CANVAS_H = 860;
const SNAP = 16;

function summarize(obj: FabricObject): CanvasSelection {
  const anyObj = obj as unknown as Record<string, unknown>;
  return {
    type: (obj.type as string) || 'object',
    fill: typeof anyObj.fill === 'string' ? (anyObj.fill as string) : '',
    stroke: typeof anyObj.stroke === 'string' ? (anyObj.stroke as string) : '',
    strokeWidth: (anyObj.strokeWidth as number) ?? 1,
    fontSize: typeof anyObj.fontSize === 'number' ? (anyObj.fontSize as number) : undefined,
    locked: obj.lockMovementX === true,
  };
}

function makeText(x: number, y: number) {
  return new Textbox('Text', { left: x, top: y, width: 200, fontSize: 20, fill: '#111' });
}
function makeRect(x: number, y: number) {
  return new Rect({ left: x, top: y, width: 180, height: 90, fill: 'transparent', stroke: '#111', strokeWidth: 1.5 });
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
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fabricRef = useRef<Canvas | null>(null);

  // Latest-prop refs so long-lived Fabric handlers read current values.
  const toolRef = useRef(activeTool);
  const snapRef = useRef(snap);
  const consumeRef = useRef(onToolConsumed);
  const onSelRef = useRef(onSelectionChange);
  const onSerRef = useRef(onSerializedChange);
  toolRef.current = activeTool;
  snapRef.current = snap;
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
      onSerRef.current((canvas.toJSON().objects ?? []) as Record<string, unknown>[]);
    };
    const pushHistory = () => {
      if (restoringRef.current) return;
      const snapshot = JSON.stringify(canvas.toJSON());
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
    historyRef.current = [JSON.stringify(canvas.toJSON())];
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
      if (!snapRef.current || !e.target) return;
      e.target.set({
        left: Math.round((e.target.left ?? 0) / SNAP) * SNAP,
        top: Math.round((e.target.top ?? 0) / SNAP) * SNAP,
      });
    });
    canvas.on('mouse:down', (opt) => {
      const tool = toolRef.current;
      if (tool === 'select' || opt.target) return;
      const p = canvas.getScenePoint(opt.e);
      let obj: FabricObject | null = null;
      if (tool === 'text') obj = makeText(p.x, p.y);
      else if (tool === 'rectangle') obj = makeRect(p.x, p.y);
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
      onSerRef.current((c.toJSON().objects ?? []) as Record<string, unknown>[]);
    });
  };

  useEffect(() => {
    const api: CanvasApi = {
      addText: () => addObj(makeText(200, 160)),
      addRect: () => addObj(makeRect(200, 200)),
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
          (img as unknown as Record<string, unknown>).assetName = name || 'image';
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
      updateSelected: (patch) => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o) return;
        if (patch.fill !== undefined) o.set('fill', patch.fill);
        if (patch.stroke !== undefined) o.set('stroke', patch.stroke);
        if (patch.strokeWidth !== undefined) o.set('strokeWidth', patch.strokeWidth);
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
        c.requestRenderAll();
        onSerRef.current((c.toJSON().objects ?? []) as Record<string, unknown>[]);
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
