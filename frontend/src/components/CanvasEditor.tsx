import { useEffect, useRef } from 'react';
import { Canvas, Rect, Circle, Textbox, Line, Group, ActiveSelection, FabricImage, type FabricObject } from 'fabric';
import type { CanvasApi, CanvasSelection } from '../model/types';
import { Connector } from './connector';

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
  const isText = obj.type === 'textbox' || obj.type === 'text' || 'fontSize' in obj;
  const isConnector = obj.type === 'Connector' || 'arrowEnd' in obj;
  const isImage = obj.type === 'image';
  const dashArr = anyObj.strokeDashArray as number[] | undefined | null;
  const dash = !dashArr || dashArr.length === 0 ? 'solid'
    : dashArr.length === 2 && dashArr[0] <= 3 ? 'dotted'
    : dashArr.length >= 4 ? 'dash-dot'
    : 'dashed';
  return {
    type: (obj.type as string) || 'object',
    name: typeof anyObj.objName === 'string' ? (anyObj.objName as string) : undefined,
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
    isConnector,
    isImage,
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
  return new Textbox('Text', { left: x, top: y, width: 200, fontSize: 20, fill: '#111' });
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
  // Connector currently being drawn via drag-to-create.
  const creatingRef = useRef<Connector | null>(null);
  // Transient alignment guide lines (never serialized/exported).
  const guidesRef = useRef<FabricObject[]>([]);

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
      onSerRef.current((canvas.toObject(['objName', 'arrowStart', 'arrowEnd']).objects ?? []) as Record<string, unknown>[]);
    };
    const pushHistory = () => {
      if (restoringRef.current) return;
      const snapshot = JSON.stringify(canvas.toObject(['objName', 'arrowStart', 'arrowEnd']));
      const hist = historyRef.current.slice(0, histIdxRef.current + 1);
      hist.push(snapshot);
      historyRef.current = hist;
      histIdxRef.current = hist.length - 1;
    };
    const onChanged = () => {
      persist();
      pushHistory();
    };
    const isGuideObj = (o: FabricObject | undefined | null) =>
      !!o && (o as unknown as Record<string, unknown>).excludeFromExport === true;

    if (serialized.length) {
      void canvas.loadFromJSON({ version: '6', objects: serialized }).then(() => {
        canvas.renderAll();
        historyRef.current = [JSON.stringify(canvas.toObject(['objName', 'arrowStart', 'arrowEnd']))];
        histIdxRef.current = 0;
      });
    } else {
      historyRef.current = [JSON.stringify(canvas.toObject(['objName', 'arrowStart', 'arrowEnd']))];
      histIdxRef.current = 0;
    }

    canvas.on('object:modified', onChanged);
    canvas.on('object:added', (e) => { if (isGuideObj(e?.target)) return; onChanged(); });
    canvas.on('object:removed', (e) => { if (isGuideObj(e?.target)) return; onChanged(); });
    canvas.on('selection:created', () => {
      const o = canvas.getActiveObject();
      if (o) onSelRef.current(summarize(o));
    });
    canvas.on('selection:updated', () => {
      const o = canvas.getActiveObject();
      if (o) onSelRef.current(summarize(o));
    });
    canvas.on('selection:cleared', () => onSelRef.current(null));

    const clearGuides = () => {
      if (!guidesRef.current.length) return;
      guidesRef.current.forEach((g) => canvas.remove(g));
      guidesRef.current = [];
    };
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
    canvas.on('mouse:up', () => { clearGuides(); canvas.requestRenderAll(); });
    canvas.on('mouse:down', (opt) => {
      const tool = toolRef.current;
      if (tool === 'select' || opt.target) return;
      const p = canvas.getScenePoint(opt.e);
      // Line / arrow: start a drag-to-create connector.
      if (tool === 'line' || tool === 'arrow') {
        const conn = new Connector([p.x, p.y, p.x, p.y], {
          stroke: '#111',
          strokeWidth: 2,
          arrowEnd: tool === 'arrow',
        });
        canvas.add(conn);
        canvas.setActiveObject(conn);
        creatingRef.current = conn;
        canvas.requestRenderAll();
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
      const conn = creatingRef.current;
      if (!conn) return;
      const p = canvas.getScenePoint(opt.e);
      conn.set({ x2: p.x, y2: p.y });
      conn.setCoords();
      canvas.requestRenderAll();
    });
    canvas.on('mouse:up', () => {
      const conn = creatingRef.current;
      if (!conn) return;
      // Give a minimum length if the user just clicked without dragging.
      const dx = (conn.x2 ?? 0) - (conn.x1 ?? 0);
      const dy = (conn.y2 ?? 0) - (conn.y1 ?? 0);
      if (Math.hypot(dx, dy) < 6) {
        conn.set({ x2: (conn.x1 ?? 0) + 160, y2: conn.y1 ?? 0 });
        conn.setCoords();
      }
      creatingRef.current = null;
      canvas.requestRenderAll();
      onChanged();
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
      onSerRef.current((c.toObject(['objName', 'arrowStart', 'arrowEnd']).objects ?? []) as Record<string, unknown>[]);
    });
  };

  useEffect(() => {
    const api: CanvasApi = {
      addText: () => addObj(makeText(200, 160)),
      addRect: () => addObj(makeRect(200, 200)),
      addCircle: () => addObj(makeCircle(200, 200)),
      addLine: () => addObj(makeLine(200, 260)),
      addArrow: () => addObj(makeArrow(200, 320)),
      addPageTitle: (text: string) => addObj(makePageTitle(text)),
      addSectionHeader: (text: string) => addObj(makeSectionHeader(text)),
      addNote: (text: string) => addObj(makeNote(text)),
      addImage: (url: string, name?: string, at?: { clientX: number; clientY: number }) => {
        const c = fabricRef.current;
        if (!c) return;
        void FabricImage.fromURL(url, { crossOrigin: 'anonymous' }).then((img) => {
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
          c.add(img);
          c.setActiveObject(img);
          c.requestRenderAll();
        });
      },
      addComponent: (url: string, name: string, label: string | null, at?: { clientX: number; clientY: number }) => {
        const c = fabricRef.current;
        if (!c) return;
        void FabricImage.fromURL(url, { crossOrigin: 'anonymous' }).then((img) => {
          const maxW = CANVAS_W * 0.35;
          const maxH = CANVAS_H * 0.35;
          const iw = img.width || 1;
          const ih = img.height || 1;
          const scale = Math.min(1, maxW / iw, maxH / ih);
          let left = (CANVAS_W - iw * scale) / 2;
          let top = (CANVAS_H - ih * scale) / 2;
          const el = canvasRef.current;
          if (at && el) {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
              left = ((at.clientX - rect.left) / rect.width) * CANVAS_W - (iw * scale) / 2;
              top = ((at.clientY - rect.top) / rect.height) * CANVAS_H - (ih * scale) / 2;
            }
          }
          img.set({ left, top, scaleX: scale, scaleY: scale });
          (img as unknown as Record<string, unknown>).objName = name;
          c.add(img);
          if (label) {
            const lbl = new Textbox(label, {
              left,
              top: top + ih * scale + 6,
              width: Math.max(120, iw * scale),
              fontSize: 14,
              fontFamily: 'Arial',
              textAlign: 'center',
              fill: '#111',
            });
            (lbl as unknown as Record<string, unknown>).objName = `${name} Label`;
            c.add(lbl);
          }
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
        const anyO = o as unknown as Record<string, unknown>;
        if (patch.fill !== undefined) o.set('fill', patch.fill);
        if (patch.stroke !== undefined) o.set('stroke', patch.stroke);
        if (patch.strokeWidth !== undefined) o.set('strokeWidth', patch.strokeWidth);
        if (patch.opacity !== undefined) o.set('opacity', patch.opacity);
        if (patch.name !== undefined) anyO.objName = patch.name;
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
          const map: Record<string, number[] | undefined> = {
            solid: undefined,
            dashed: [10, 6],
            dotted: [2, 5],
            'dash-dot': [12, 5, 2, 5],
          };
          o.set('strokeDashArray', map[patch.dash] ?? undefined);
        }
        if (patch.arrowEnd !== undefined && 'arrowEnd' in o) anyO.arrowEnd = patch.arrowEnd;
        if (patch.arrowStart !== undefined && 'arrowStart' in o) anyO.arrowStart = patch.arrowStart;
        if (patch.locked !== undefined) {
          o.set({
            lockMovementX: patch.locked,
            lockMovementY: patch.locked,
            lockScalingX: patch.locked,
            lockScalingY: patch.locked,
            lockRotation: patch.locked,
          });
        }
        o.set('dirty', true);
        o.setCoords();
        c.requestRenderAll();
        onSerRef.current((c.toObject(['objName', 'arrowStart', 'arrowEnd']).objects ?? []) as Record<string, unknown>[]);
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
