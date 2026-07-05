import { Line, Control, Point, util, classRegistry } from 'fabric';

/**
 * A real connector: a Fabric Line subclass with independent, draggable endpoint
 * handles and an optional arrowhead that always follows the end point. Unlike a
 * grouped line+triangle "arrow", this behaves like a PowerPoint/Visio connector:
 *  - click the body to select, drag the body to move the whole connector
 *  - drag either endpoint handle to move that endpoint independently
 *  - the arrowhead tracks the end point
 *  - it serializes/reloads/exports as a single stable object
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyOpts = Record<string, any>;

function renderHandle(ctx: CanvasRenderingContext2D, left: number, top: number) {
  const s = 7;
  ctx.save();
  ctx.fillStyle = '#12539b';
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(left, top, s / 2 + 1, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

export class Connector extends Line {
  static type = 'Connector';

  arrowStart = false;
  arrowEnd = true;
  objName?: string;
  connectorKind: 'line' | 'arrow' | 'polyline' | 'elbow' = 'line';
  pointsData: Array<{ x: number; y: number }> = [];
  label?: string;

  constructor(points: [number, number, number, number], options: AnyOpts = {}) {
    super(points, options);
    this.arrowStart = options.arrowStart ?? false;
    this.arrowEnd = options.arrowEnd ?? true;
    this.objName = options.objName;
    this.connectorKind = options.connectorKind ?? (this.arrowEnd ? 'arrow' : 'line');
    this.pointsData = Array.isArray(options.pointsData)
      ? options.pointsData.map((p: { x: number; y: number }) => ({ x: Number(p.x), y: Number(p.y) }))
      : [
          { x: points[0], y: points[1] },
          { x: points[2], y: points[3] },
        ];
    this.label = options.label;
    this.strokeUniform = true;
    // Easy to grab: use the bounding box (not per-pixel) and add generous hit
    // padding so thin lines/arrows are simple to select and move.
    this.perPixelTargetFind = false;
    this.padding = 10;
    this.hasBorders = true;
    this.objectCaching = false;
    this.borderColor = '#12539b';
    this.borderScaleFactor = 2;
    this.controls = {
      start: new Control({
        positionHandler: endpointPosition('start'),
        actionHandler: endpointAction('start'),
        actionName: 'endpoint',
        cursorStyle: 'crosshair',
        render: renderHandle,
      }),
      end: new Control({
        positionHandler: endpointPosition('end'),
        actionHandler: endpointAction('end'),
        actionName: 'endpoint',
        cursorStyle: 'crosshair',
        render: renderHandle,
      }),
    };
    this.rebuildVertexControls();
    this.updateLineFromPoints();
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  toObject(...args: any[]) {
    const propertiesToInclude = (args?.[0] ?? []) as any[];
    return {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ...(super.toObject(propertiesToInclude as any) as any),
      arrowStart: this.arrowStart,
      arrowEnd: this.arrowEnd,
      connectorKind: this.connectorKind,
      pointsData: this.pointsData,
      label: this.label,
      objName: this.objName,
    };
  }

  _render(ctx: CanvasRenderingContext2D) {
    if (!this.pointsData || this.pointsData.length < 2) {
      super._render(ctx);
      return;
    }
    const pts = this.pointsData;
    ctx.save();
    ctx.strokeStyle = (this.stroke as string) || '#111';
    ctx.lineWidth = this.strokeWidth || 2;
    const d = this.strokeDashArray as number[] | undefined;
    if (d && d.length) ctx.setLineDash(d);
    else ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(pts[0].x - (this.left ?? 0), pts[0].y - (this.top ?? 0));
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x - (this.left ?? 0), pts[i].y - (this.top ?? 0));
    }
    ctx.stroke();

    if (this.arrowEnd && pts.length >= 2) {
      const a = pts[pts.length - 2];
      const b = pts[pts.length - 1];
      this._arrowHead(ctx, a.x - (this.left ?? 0), a.y - (this.top ?? 0), b.x - (this.left ?? 0), b.y - (this.top ?? 0));
    }
    if (this.arrowStart && pts.length >= 2) {
      const a = pts[1];
      const b = pts[0];
      this._arrowHead(ctx, a.x - (this.left ?? 0), a.y - (this.top ?? 0), b.x - (this.left ?? 0), b.y - (this.top ?? 0));
    }
    ctx.restore();
  }

  _arrowHead(ctx: CanvasRenderingContext2D, fromX: number, fromY: number, toX: number, toY: number) {
    const angle = Math.atan2(toY - fromY, toX - fromX);
    const size = Math.max(9, (this.strokeWidth || 2) * 3.2);
    ctx.save();
    ctx.translate(toX, toY);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-size, size / 2);
    ctx.lineTo(-size, -size / 2);
    ctx.closePath();
    ctx.fillStyle = (this.stroke as string) || '#111';
    ctx.fill();
    ctx.restore();
  }

  updateLineFromPoints() {
    if (!this.pointsData || this.pointsData.length < 2) return;
    const xs = this.pointsData.map((p) => p.x);
    const ys = this.pointsData.map((p) => p.y);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    const maxX = Math.max(...xs);
    const maxY = Math.max(...ys);
    this.set({
      left: minX,
      top: minY,
      width: Math.max(1, maxX - minX),
      height: Math.max(1, maxY - minY),
      x1: this.pointsData[0].x,
      y1: this.pointsData[0].y,
      x2: this.pointsData[this.pointsData.length - 1].x,
      y2: this.pointsData[this.pointsData.length - 1].y,
    });
    this.setCoords();
  }

  rebuildVertexControls() {
    const baseStart = this.controls.start;
    const baseEnd = this.controls.end;
    const controls: Record<string, Control> = {
      start: baseStart,
      end: baseEnd,
    };
    this.pointsData.forEach((_p, idx) => {
      controls[`v${idx}`] = new Control({
        positionHandler: vertexPosition(idx),
        actionHandler: vertexAction(idx),
        actionName: 'vertex',
        cursorStyle: 'crosshair',
        render: renderHandle,
      });
    });
    this.controls = controls;
  }

  addVertexAtMidpoint() {
    if (!this.pointsData || this.pointsData.length < 2) return;
    let bestIdx = 0;
    let bestLen = -1;
    for (let i = 0; i < this.pointsData.length - 1; i++) {
      const a = this.pointsData[i];
      const b = this.pointsData[i + 1];
      const len = Math.hypot(b.x - a.x, b.y - a.y);
      if (len > bestLen) {
        bestLen = len;
        bestIdx = i;
      }
    }
    const a = this.pointsData[bestIdx];
    const b = this.pointsData[bestIdx + 1];
    this.pointsData.splice(bestIdx + 1, 0, { x: Math.round((a.x + b.x) / 2), y: Math.round((a.y + b.y) / 2) });
    this.rebuildVertexControls();
    this.updateLineFromPoints();
  }

  deleteVertex() {
    if (!this.pointsData || this.pointsData.length <= 2) return;
    this.pointsData.splice(this.pointsData.length - 2, 1);
    this.rebuildVertexControls();
    this.updateLineFromPoints();
  }

  reverseDirection() {
    this.pointsData = [...this.pointsData].reverse();
    const a = this.arrowStart;
    this.arrowStart = this.arrowEnd;
    this.arrowEnd = a;
    this.updateLineFromPoints();
  }

  convertKind(kind: 'line' | 'arrow' | 'polyline' | 'elbow') {
    this.connectorKind = kind;
    if (kind === 'line' || kind === 'arrow') {
      const s = this.pointsData[0];
      const e = this.pointsData[this.pointsData.length - 1];
      this.pointsData = [s, e];
      this.arrowStart = false;
      this.arrowEnd = kind === 'arrow' ? true : this.arrowEnd;
    } else if (kind === 'elbow') {
      const s = this.pointsData[0];
      const e = this.pointsData[this.pointsData.length - 1];
      this.pointsData = [s, { x: e.x, y: s.y }, e];
    }
    this.rebuildVertexControls();
    this.updateLineFromPoints();
  }
}

function endpointPosition(which: 'start' | 'end') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (_dim: Point, _finalMatrix: unknown, fabricObject: any): Point {
    const line = fabricObject as Connector;
    const p = which === 'start' ? line.pointsData[0] : line.pointsData[line.pointsData.length - 1];
    const local = new Point((p?.x ?? 0) - (line.left ?? 0), (p?.y ?? 0) - (line.top ?? 0));
    const vpt = line.canvas?.viewportTransform;
    const m = vpt
      ? util.multiplyTransformMatrices(vpt, line.calcTransformMatrix())
      : line.calcTransformMatrix();
    return local.transform(m);
  };
}

function endpointAction(which: 'start' | 'end') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (_eventData: unknown, transform: any, x: number, y: number): boolean {
    const line = transform.target as Connector;
    if (!line.pointsData?.length) return false;
    if (which === 'start') line.pointsData[0] = { x, y };
    else line.pointsData[line.pointsData.length - 1] = { x, y };
    line.updateLineFromPoints();
    return true;
  };
}

classRegistry.setClass(Connector);
classRegistry.setClass(Connector, 'connector');

function vertexPosition(idx: number) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (_dim: Point, _finalMatrix: unknown, fabricObject: any): Point {
    const line = fabricObject as Connector;
    const p = line.pointsData[idx] ?? line.pointsData[0];
    const local = new Point((p?.x ?? 0) - (line.left ?? 0), (p?.y ?? 0) - (line.top ?? 0));
    const vpt = line.canvas?.viewportTransform;
    const m = vpt
      ? util.multiplyTransformMatrices(vpt, line.calcTransformMatrix())
      : line.calcTransformMatrix();
    return local.transform(m);
  };
}

function vertexAction(idx: number) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (_eventData: unknown, transform: any, x: number, y: number): boolean {
    const line = transform.target as Connector;
    if (!line.pointsData[idx]) return false;
    line.pointsData[idx] = { x, y };
    if (line.connectorKind === 'elbow' && line.pointsData.length >= 3) {
      // Maintain orthogonal route on immediate neighbors.
      if (idx > 0) line.pointsData[idx - 1] = { ...line.pointsData[idx - 1], y: y };
      if (idx < line.pointsData.length - 1) line.pointsData[idx + 1] = { ...line.pointsData[idx + 1], x: x };
    }
    line.updateLineFromPoints();
    return true;
  };
}
