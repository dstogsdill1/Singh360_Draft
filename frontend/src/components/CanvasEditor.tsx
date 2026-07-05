import { useEffect, useRef } from 'react';
import { Canvas, Rect, Circle, Textbox, Line, Group, ActiveSelection, FabricImage, type FabricObject } from 'fabric';
import type { CanvasApi, CanvasSelection } from '../model/types';
import { Connector } from './connector';
import { CONNECTOR_PRESETS, dashArray } from '../model/connectorPresets';
import { BODY_W, BODY_H } from '../model/sheetGeometry';

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
const SER_PROPS = ['objName', 'arrowStart', 'arrowEnd', 'connectorKind', 'pointsData', 'label'];

function summarize(obj: FabricObject): CanvasSelection {
  const anyObj = obj as unknown as Record<string, unknown>;
  const isText = obj.type === 'textbox' || obj.type === 'text' || 'fontSize' in obj;
  const isConnector = obj.type === 'Connector' || 'arrowEnd' in obj;
  const isImage = obj.type === 'image';
  const dashArr = anyObj.strokeDashArray as number[] | undefined | null;
  const dash = !dashArr || dashArr.length === 0 ? 'solid'
    : dashArr.length === 2 && dashArr[0] <= 3 ? 'dotted'
    : dashArr.length >= 4 ? 'dash-dot'
    : dashArr.length === 2 && dashArr[0] >= 14 ? 'long-dash'
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
    connectorKind: typeof anyObj.connectorKind === 'string' ? (anyObj.connectorKind as CanvasSelection['connectorKind']) : (isConnector ? 'line' : undefined),
    pointsCount: Array.isArray(anyObj.pointsData) ? anyObj.pointsData.length : (isConnector ? 2 : undefined),
    label: typeof anyObj.label === 'string' ? (anyObj.label as string) : undefined,
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
  return new Textbox('Text', { left: x, top: y, width: 200, fontSize: 20, fill: '#111', padding: 6 });
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
  const creatingPolyRef = useRef<Connector | null>(null);
  // Transient alignment guide lines (never serialized/exported).
  const guidesRef = useRef<FabricObject[]>([]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const canvas = new Canvas(canvasRef.current, {
      width: CANVAS_W,
      height: CANVAS_H,
      selection: true,
      backgroundColor: '',
      targetFindTolerance: 12,
      perPixelTargetFind: false,
    });
    fabricRef.current = canvas;
    const persist = () => {
      if (restoringRef.current) return;
      onSerRef.current((canvas.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
    };
    const pushHistory = () => {
      if (restoringRef.current) return;
      const snapshot = JSON.stringify(canvas.toObject(SER_PROPS));
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
        historyRef.current = [JSON.stringify(canvas.toObject(SER_PROPS))];
        histIdxRef.current = 0;
      });
    } else {
      historyRef.current = [JSON.stringify(canvas.toObject(SER_PROPS))];
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
      if (t instanceof Connector) {
        const anyT = t as unknown as Record<string, unknown>;
        const dragOrigin = anyT.__dragOrigin as { left: number; top: number; points: Array<{ x: number; y: number }> } | undefined;
        if (dragOrigin) {
          const dx = (t.left ?? 0) - dragOrigin.left;
          const dy = (t.top ?? 0) - dragOrigin.top;
          t.pointsData = dragOrigin.points.map((p) => ({ x: p.x + dx, y: p.y + dy }));
          t.updateLineFromPoints();
          canvas.requestRenderAll();
          return;
        }
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
    canvas.on('mouse:up', () => { clearGuides(); canvas.requestRenderAll(); });
    canvas.on('mouse:down', (opt) => {
      const tool = toolRef.current;
      if (opt.target instanceof Connector) {
        const t = opt.target as Connector;
        const anyT = t as unknown as Record<string, unknown>;
        anyT.__dragOrigin = {
          left: t.left ?? 0,
          top: t.top ?? 0,
          points: t.pointsData.map((p) => ({ x: p.x, y: p.y })),
        };
      }
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
      if (tool === 'polyline' || tool === 'elbow') {
        if (!creatingPolyRef.current) {
          const conn = tool === 'elbow' ? makeElbow(p.x, p.y) : makePolyline(p.x, p.y);
          conn.pointsData = [{ x: p.x, y: p.y }, { x: p.x, y: p.y }];
          conn.connectorKind = tool === 'elbow' ? 'elbow' : 'polyline';
          conn.rebuildVertexControls();
          conn.updateLineFromPoints();
          canvas.add(conn);
          canvas.setActiveObject(conn);
          creatingPolyRef.current = conn;
          canvas.requestRenderAll();
        } else {
          const conn = creatingPolyRef.current;
          if (conn) {
            const last = conn.pointsData[conn.pointsData.length - 1];
            const nx = snapRef.current ? Math.round(p.x / SNAP) * SNAP : p.x;
            const ny = snapRef.current ? Math.round(p.y / SNAP) * SNAP : p.y;
            if (conn.connectorKind === 'elbow' && last) {
              conn.pointsData.push({ x: nx, y: last.y }, { x: nx, y: ny });
            } else {
              conn.pointsData.push({ x: nx, y: ny });
            }
            conn.rebuildVertexControls();
            conn.updateLineFromPoints();
            canvas.requestRenderAll();
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
      const conn = creatingRef.current;
      if (conn) {
        const p = canvas.getScenePoint(opt.e);
        if (conn.pointsData?.length >= 2) {
          conn.pointsData[1] = { x: p.x, y: p.y };
          conn.updateLineFromPoints();
        } else {
          conn.set({ x2: p.x, y2: p.y });
          conn.setCoords();
        }
        canvas.requestRenderAll();
      }
      const poly = creatingPolyRef.current;
      if (poly) {
        const p = canvas.getScenePoint(opt.e);
        const nx = snapRef.current ? Math.round(p.x / SNAP) * SNAP : p.x;
        const ny = snapRef.current ? Math.round(p.y / SNAP) * SNAP : p.y;
        if (poly.pointsData.length >= 2) {
          poly.pointsData[poly.pointsData.length - 1] =
            poly.connectorKind === 'elbow'
              ? { x: nx, y: poly.pointsData[poly.pointsData.length - 2].y }
              : { x: nx, y: ny };
          poly.updateLineFromPoints();
          canvas.requestRenderAll();
        }
      }
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
        if (conn.pointsData?.length >= 2) {
          conn.pointsData[1] = { x: (conn.x1 ?? 0) + 160, y: conn.y1 ?? 0 };
          conn.updateLineFromPoints();
        }
      }
      creatingRef.current = null;
      canvas.requestRenderAll();
      onChanged();
      consumeRef.current();
    });
    canvas.on('object:modified', (e) => {
      const t = e.target;
      if (t instanceof Connector) {
        const anyT = t as unknown as Record<string, unknown>;
        delete anyT.__dragOrigin;
      }
    });

    const onKeyDown = (ev: KeyboardEvent) => {
      const poly = creatingPolyRef.current;
      if (!poly) return;
      if (ev.key === 'Escape') {
        canvas.remove(poly);
        creatingPolyRef.current = null;
        consumeRef.current();
        canvas.requestRenderAll();
        return;
      }
      if (ev.key === 'Backspace') {
        ev.preventDefault();
        if (poly.pointsData.length > 2) {
          poly.pointsData.splice(poly.pointsData.length - 2, 1);
          poly.rebuildVertexControls();
          poly.updateLineFromPoints();
          canvas.requestRenderAll();
        }
        return;
      }
      if (ev.key === 'Enter') {
        creatingPolyRef.current = null;
        poly.rebuildVertexControls();
        poly.updateLineFromPoints();
        canvas.setActiveObject(poly);
        canvas.requestRenderAll();
        onChanged();
        consumeRef.current();
      }
    };
    const onDblClick = () => {
      const poly = creatingPolyRef.current;
      if (!poly) return;
      creatingPolyRef.current = null;
      poly.rebuildVertexControls();
      poly.updateLineFromPoints();
      canvas.setActiveObject(poly);
      canvas.requestRenderAll();
      onChanged();
      consumeRef.current();
    };
    const onDblClickExisting = () => {
      const cobj = canvas.getActiveObject();
      if (!(cobj instanceof Connector)) return;
      if (creatingPolyRef.current) return;
      cobj.addVertexAtMidpoint();
      canvas.requestRenderAll();
      onChanged();
    };
    window.addEventListener('keydown', onKeyDown);
    canvas.upperCanvasEl?.addEventListener('dblclick', onDblClick);
    canvas.upperCanvasEl?.addEventListener('dblclick', onDblClickExisting);

    return () => {
      window.removeEventListener('keydown', onKeyDown);
      canvas.upperCanvasEl?.removeEventListener('dblclick', onDblClick);
      canvas.upperCanvasEl?.removeEventListener('dblclick', onDblClickExisting);
      void canvas.dispose();
      fabricRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
    });
  };

  useEffect(() => {
    const api: CanvasApi = {
      addText: () => addObj(makeText(200, 160)),
      addRect: () => addObj(makeRect(200, 200)),
      addCircle: () => addObj(makeCircle(200, 200)),
      addLine: () => addObj(makeLine(200, 260)),
      addArrow: () => addObj(makeArrow(200, 320)),
      addPolyline: () => addObj(makePolyline(200, 340)),
      addElbow: () => addObj(makeElbow(200, 360)),
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
          styleForSelection(img);
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
          styleForSelection(img);
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
      alignObjects: (direction) => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        const objs = active?.type === 'activeselection'
          ? (active as unknown as { getObjects: () => FabricObject[] }).getObjects()
          : active ? [active] : [];
        if (!objs.length) return;
        const bbs = objs.map((o) => ({ o, b: o.getBoundingRect() }));
        if (direction === 'page-center-h') {
          objs.forEach((o) => { const b = o.getBoundingRect(); o.set('left', CANVAS_W / 2 - b.width / 2); o.setCoords(); });
        } else if (direction === 'page-center-v') {
          objs.forEach((o) => { const b = o.getBoundingRect(); o.set('top', CANVAS_H / 2 - b.height / 2); o.setCoords(); });
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
        c.requestRenderAll();
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
      },
      distributeObjects: (direction) => {
        const c = fabricRef.current;
        if (!c) return;
        const active = c.getActiveObject();
        const objs = active?.type === 'activeselection'
          ? (active as unknown as { getObjects: () => FabricObject[] }).getObjects()
          : [];
        if (objs.length < 3) return;
        const sorted = direction === 'horizontal'
          ? [...objs].sort((a, b) => (a.left ?? 0) - (b.left ?? 0))
          : [...objs].sort((a, b) => (a.top ?? 0) - (b.top ?? 0));
        const bbs = sorted.map((o) => ({ o, b: o.getBoundingRect() }));
        if (direction === 'horizontal') {
          const total = bbs.reduce((s, { b }) => s + b.width, 0);
          const last = bbs[bbs.length - 1];
          const span = (last.b.left + last.b.width) - bbs[0].b.left;
          const gap = (span - total) / (bbs.length - 1);
          let x = bbs[0].b.left;
          bbs.forEach(({ o, b }) => { o.set('left', (o.left ?? 0) + (x - b.left)); o.setCoords(); x += b.width + gap; });
        } else {
          const total = bbs.reduce((s, { b }) => s + b.height, 0);
          const last = bbs[bbs.length - 1];
          const span = (last.b.top + last.b.height) - bbs[0].b.top;
          const gap = (span - total) / (bbs.length - 1);
          let y = bbs[0].b.top;
          bbs.forEach(({ o, b }) => { o.set('top', (o.top ?? 0) + (y - b.top)); o.setCoords(); y += b.height + gap; });
        }
        c.requestRenderAll();
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
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
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
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
        }
        o.set('dirty', true);
        o.setCoords();
        c.requestRenderAll();
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
        onSelRef.current(summarize(o));
      },
      reverseConnectorDirection: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.reverseDirection();
        c.requestRenderAll();
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
      },
      addVertexToSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.addVertexAtMidpoint();
        c.requestRenderAll();
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
      },
      deleteVertexFromSelected: () => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.deleteVertex();
        c.requestRenderAll();
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
      },
      convertSelectedConnector: (kind) => {
        const c = fabricRef.current;
        const o = c?.getActiveObject();
        if (!c || !o || !(o instanceof Connector)) return;
        o.convertKind(kind);
        c.requestRenderAll();
        onSerRef.current((c.toObject(SER_PROPS).objects ?? []) as Record<string, unknown>[]);
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
