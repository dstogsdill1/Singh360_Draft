import { Polyline, controlsUtils, Point, classRegistry } from 'fabric';

/**
 * Connector — a real multi-point line/arrow/polyline/elbow built on Fabric's
 * native Polyline. Vertex editing uses Fabric's OFFICIAL built-in
 * `controlsUtils.createPolyControls()` (the poly-controls demo recipe) so every
 * point is a grabbable handle and dragging the body moves the whole object —
 * exactly like PowerPoint / Visio.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyOpts = Record<string, any>;
type XY = { x: number; y: number };

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
  connectorKind: 'line' | 'arrow' | 'polyline' | 'elbow' | 'bus' = 'line';
  label?: string;
  // Phase B extended connector model (pointsData stays the route source of truth).
  stylePreset?: string;
  wireNumber?: string;
  labelStart?: string;
  labelMiddle?: string;
  labelEnd?: string;
  layer?: string;

  constructor(input: unknown, options: AnyOpts = {}) {
    const pts = normalizePoints(input, options);
    const { pointsData: _pointsData, ...fabricOptions } = options;
    super(pts, {
      stroke: options.stroke ?? '#111',
      strokeWidth: options.strokeWidth ?? 2,
      strokeUniform: true,
      strokeLineCap: 'round',
      strokeLineJoin: 'round',
      objectCaching: false,
      // Easy to grab: clicking anywhere in the line's bounding band selects it
      // (a hair-thin per-pixel target was nearly impossible to click). A wider
      // padding gives a ~14px hit band around thin connectors.
      perPixelTargetFind: false,
      padding: 12,
      hasBorders: false,
      cornerColor: '#12539b',
      cornerStyle: 'circle',
      cornerSize: 10,
      transparentCorners: false,
      ...fabricOptions,
      fill: '',
    });
    this.arrowStart = options.arrowStart ?? false;
    this.arrowEnd = options.arrowEnd ?? false;
    this.objName = options.objName;
    this.connectorKind = options.connectorKind ?? (options.arrowEnd ? 'arrow' : 'line');
    this.label = options.label;
    this.stylePreset = options.stylePreset;
    this.wireNumber = options.wireNumber;
    this.labelStart = options.labelStart;
    this.labelMiddle = options.labelMiddle ?? options.label;
    this.labelEnd = options.labelEnd;
    this.layer = options.layer;
    if (options.strokeDashArray) this.strokeDashArray = options.strokeDashArray;
    this.applyVertexControls();
  }

  /** Swap the object's controls for one grabbable handle per vertex. */
  applyVertexControls() {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      this.controls = controlsUtils.createPolyControls(this as any);
    } catch {
      /* Degenerate geometry (e.g. a just-started zero-length line) can make the
         poly-control factory throw; skip it rather than aborting the whole draw.
         Controls are re-applied on the next setAbsPoints once real points exist. */
    }
  }

  // ---- absolute scene coordinates -----------------------------------------
  getAbsPoints(): XY[] {
    if (!Array.isArray(this.points) || this.points.length < 2 || !this.pathOffset) {
      return normalizePoints([], {});
    }
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
    this.applyVertexControls();
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
      stylePreset: this.stylePreset,
      wireNumber: this.wireNumber,
      labelStart: this.labelStart,
      labelMiddle: this.labelMiddle,
      labelEnd: this.labelEnd,
      layer: this.layer,
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

classRegistry.setClass(Connector);
classRegistry.setClass(Connector, 'connector');
