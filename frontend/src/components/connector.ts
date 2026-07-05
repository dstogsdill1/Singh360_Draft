import { Polyline, Control, Point, util, classRegistry } from 'fabric';

/**
 * Connector — a real multi-point line/arrow/polyline/elbow built on Fabric's
 * native Polyline so the bounding box, hit-testing, whole-object move and vertex
 * editing all behave correctly (PowerPoint/Visio style).
 *
 * Points live in Fabric's local "points" space; absolute scene coordinates are
 * always derivable from the object transform, so:
 *  - drag the body → the whole connector moves (native Fabric transform)
 *  - drag a vertex handle → only that point moves
 *  - it serializes/reloads/exports as one stable object
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyOpts = Record<string, any>;
type XY = { x: number; y: number };

function renderHandle(ctx: CanvasRenderingContext2D, left: number, top: number) {
  const s = 8;
  ctx.save();
  ctx.fillStyle = '#12539b';
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(left, top, s / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function normalizePoints(input: unknown, options: AnyOpts): XY[] {
  if (Array.isArray(options.pointsData) && options.pointsData.length >= 2) {
    return options.pointsData.map((p: XY) => ({ x: Number(p.x), y: Number(p.y) }));
  }
  if (Array.isArray(input) && input.length >= 2 && typeof input[0] === 'object') {
    return (input as XY[]).map((p) => ({ x: Number(p.x), y: Number(p.y) }));
  }
  if (Array.isArray(input) && input.length >= 4 && typeof input[0] === 'number') {
    const n = input as number[];
    return [
      { x: n[0], y: n[1] },
      { x: n[2], y: n[3] },
    ];
  }
  return [
    { x: 0, y: 0 },
    { x: 100, y: 0 },
  ];
}

export class Connector extends Polyline {
  static type = 'Connector';

  arrowStart = false;
  arrowEnd = false;
  objName?: string;
  connectorKind: 'line' | 'arrow' | 'polyline' | 'elbow' = 'line';
  label?: string;

  constructor(input: unknown, options: AnyOpts = {}) {
    const pts = normalizePoints(input, options);
    super(pts, {
      stroke: options.stroke ?? '#111',
      strokeWidth: options.strokeWidth ?? 2,
      strokeUniform: true,
      strokeLineCap: 'round',
      strokeLineJoin: 'round',
      objectCaching: false,
      perPixelTargetFind: false,
      padding: 10,
      hasBorders: true,
      borderColor: '#12539b',
      borderScaleFactor: 2,
      ...options,
      fill: '',
    });
    this.arrowStart = options.arrowStart ?? false;
    this.arrowEnd = options.arrowEnd ?? false;
    this.objName = options.objName;
    this.connectorKind = options.connectorKind ?? (options.arrowEnd ? 'arrow' : 'line');
    this.label = options.label;
    if (options.strokeDashArray) this.strokeDashArray = options.strokeDashArray;
    this.rebuildVertexControls();
  }

  // ---- absolute scene coordinates -----------------------------------------
  getAbsPoints(): XY[] {
    const m = this.calcTransformMatrix();
    return (this.points as XY[]).map((p) => {
      const t = new Point(p.x - this.pathOffset.x, p.y - this.pathOffset.y).transform(m);
      return { x: Math.round(t.x), y: Math.round(t.y) };
    });
  }

  setAbsPoints(abs: XY[]) {
    if (!abs || abs.length < 2) return;
    this.points = abs.map((p) => new Point(p.x, p.y));
    this.setBoundingBox(true);
    this.rebuildVertexControls();
    this.setCoords();
    this.dirty = true;
  }

  // Back-compat accessor (returns absolute points).
  get pointsData(): XY[] {
    return this.getAbsPoints();
  }
  set pointsData(v: XY[]) {
    this.setAbsPoints(v);
  }

  updateLineFromPoints() {
    this.setBoundingBox(true);
    this.setCoords();
    this.dirty = true;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toObject(...args: any[]) {
    const propertiesToInclude = (args?.[0] ?? []) as string[];
    return {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ...(super.toObject(propertiesToInclude as any) as any),
      arrowStart: this.arrowStart,
      arrowEnd: this.arrowEnd,
      connectorKind: this.connectorKind,
      pointsData: this.getAbsPoints(),
      label: this.label,
      objName: this.objName,
    };
  }

  static async fromObject(object: AnyOpts): Promise<Connector> {
    const abs = Array.isArray(object.pointsData) && object.pointsData.length >= 2
      ? object.pointsData
      : object.points;
    return new Connector(abs, { ...object, pointsData: abs });
  }

  _render(ctx: CanvasRenderingContext2D) {
    super._render(ctx);
    const pts = this.points as XY[];
    if (pts.length < 2) return;
    const ox = this.pathOffset.x;
    const oy = this.pathOffset.y;
    if (this.arrowEnd) {
      const a = pts[pts.length - 2];
      const b = pts[pts.length - 1];
      this._arrowHead(ctx, a.x - ox, a.y - oy, b.x - ox, b.y - oy);
    }
    if (this.arrowStart) {
      const a = pts[1];
      const b = pts[0];
      this._arrowHead(ctx, a.x - ox, a.y - oy, b.x - ox, b.y - oy);
    }
  }

  _arrowHead(ctx: CanvasRenderingContext2D, fromX: number, fromY: number, toX: number, toY: number) {
    const angle = Math.atan2(toY - fromY, toX - fromX);
    const size = Math.max(10, (this.strokeWidth || 2) * 3.2);
    ctx.save();
    ctx.translate(toX, toY);
    ctx.rotate(angle);
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-size, size / 2);
    ctx.lineTo(-size, -size / 2);
    ctx.closePath();
    ctx.fillStyle = (this.stroke as string) || '#111';
    ctx.fill();
    ctx.restore();
  }

  rebuildVertexControls() {
    const controls: Record<string, Control> = {};
    (this.points as XY[]).forEach((_p, idx) => {
      const control = new Control({
        positionHandler: polyPositionHandler,
        actionHandler: anchorWrapper(idx > 0 ? idx - 1 : 1, polyActionHandler),
        actionName: 'modifyConnector',
        cursorStyle: 'crosshair',
        render: renderHandle,
      });
      (control as unknown as Record<string, unknown>).pointIndex = idx;
      controls[`p${idx}`] = control;
    });
    this.controls = controls;
  }

  addVertexAtMidpoint() {
    const abs = this.getAbsPoints();
    if (abs.length < 2) return;
    let bestIdx = 0;
    let bestLen = -1;
    for (let i = 0; i < abs.length - 1; i++) {
      const len = Math.hypot(abs[i + 1].x - abs[i].x, abs[i + 1].y - abs[i].y);
      if (len > bestLen) { bestLen = len; bestIdx = i; }
    }
    const a = abs[bestIdx];
    const b = abs[bestIdx + 1];
    abs.splice(bestIdx + 1, 0, { x: Math.round((a.x + b.x) / 2), y: Math.round((a.y + b.y) / 2) });
    this.setAbsPoints(abs);
  }

  deleteVertex() {
    const abs = this.getAbsPoints();
    if (abs.length <= 2) return;
    abs.splice(abs.length - 2, 1);
    this.setAbsPoints(abs);
  }

  reverseDirection() {
    const abs = this.getAbsPoints().reverse();
    const a = this.arrowStart;
    this.arrowStart = this.arrowEnd;
    this.arrowEnd = a;
    this.setAbsPoints(abs);
  }

  convertKind(kind: 'line' | 'arrow' | 'polyline' | 'elbow') {
    const abs = this.getAbsPoints();
    this.connectorKind = kind;
    if (kind === 'line' || kind === 'arrow') {
      const s = abs[0];
      const e = abs[abs.length - 1];
      this.arrowStart = false;
      this.arrowEnd = kind === 'arrow';
      this.setAbsPoints([s, e]);
    } else if (kind === 'elbow') {
      const s = abs[0];
      const e = abs[abs.length - 1];
      this.setAbsPoints([s, { x: e.x, y: s.y }, e]);
    } else {
      this.setAbsPoints(abs);
    }
  }
}

// ---- Fabric editable-polygon control recipe -------------------------------
function polyPositionHandler(
  this: Control,
  _dim: Point,
  _finalMatrix: unknown,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fabricObject: any,
): Point {
  const idx = (this as unknown as Record<string, number>).pointIndex ?? 0;
  const p = fabricObject.points[idx] ?? fabricObject.points[0];
  const x = p.x - fabricObject.pathOffset.x;
  const y = p.y - fabricObject.pathOffset.y;
  const vpt = fabricObject.canvas?.viewportTransform;
  const m = vpt
    ? util.multiplyTransformMatrices(vpt, fabricObject.calcTransformMatrix())
    : fabricObject.calcTransformMatrix();
  return new Point(x, y).transform(m);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function polyActionHandler(_eventData: unknown, transform: any, x: number, y: number): boolean {
  const polygon = transform.target;
  const currentControl = polygon.controls[polygon.__corner];
  const idx = (currentControl as Record<string, number>).pointIndex ?? 0;
  const mouseLocalPosition = polygon.toLocalPoint(new Point(x, y), 'center', 'center');
  const polygonBaseSize = polygon._getNonTransformedDimensions();
  const size = polygon._getTransformedDimensions();
  const finalX = (mouseLocalPosition.x * polygonBaseSize.x) / size.x + polygon.pathOffset.x;
  const finalY = (mouseLocalPosition.y * polygonBaseSize.y) / size.y + polygon.pathOffset.y;
  polygon.points[idx] = new Point(finalX, finalY);
  return true;
}

function anchorWrapper(
  anchorIndex: number,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fn: (eventData: unknown, transform: any, x: number, y: number) => boolean,
) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (eventData: unknown, transform: any, x: number, y: number): boolean {
    const fabricObject = transform.target;
    const idx = Math.min(anchorIndex, fabricObject.points.length - 1);
    const absolutePoint = new Point(
      fabricObject.points[idx].x - fabricObject.pathOffset.x,
      fabricObject.points[idx].y - fabricObject.pathOffset.y,
    ).transform(fabricObject.calcTransformMatrix());
    const actionPerformed = fn(eventData, transform, x, y);
    fabricObject.setBoundingBox();
    const polygonBaseSize = fabricObject._getNonTransformedDimensions();
    const newX = (fabricObject.points[idx].x - fabricObject.pathOffset.x) / polygonBaseSize.x;
    const newY = (fabricObject.points[idx].y - fabricObject.pathOffset.y) / polygonBaseSize.y;
    fabricObject.setPositionByOrigin(absolutePoint, newX + 0.5, newY + 0.5);
    fabricObject.rebuildVertexControls?.();
    return actionPerformed;
  };
}

classRegistry.setClass(Connector);
classRegistry.setClass(Connector, 'connector');
