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

  constructor(points: [number, number, number, number], options: AnyOpts = {}) {
    super(points, options);
    this.arrowStart = options.arrowStart ?? false;
    this.arrowEnd = options.arrowEnd ?? true;
    this.objName = options.objName;
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
  }

  _render(ctx: CanvasRenderingContext2D) {
    super._render(ctx);
    const p = this.calcLinePoints();
    if (this.arrowEnd) this._arrowHead(ctx, p.x1, p.y1, p.x2, p.y2);
    if (this.arrowStart) this._arrowHead(ctx, p.x2, p.y2, p.x1, p.y1);
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
}

function endpointPosition(which: 'start' | 'end') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return function (_dim: Point, _finalMatrix: unknown, fabricObject: any): Point {
    const line = fabricObject as Connector;
    const pts = line.calcLinePoints();
    const local = which === 'start' ? new Point(pts.x1, pts.y1) : new Point(pts.x2, pts.y2);
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
    const pts = line.calcLinePoints();
    const m = line.calcTransformMatrix();
    const absStart = new Point(pts.x1, pts.y1).transform(m);
    const absEnd = new Point(pts.x2, pts.y2).transform(m);
    const ns = which === 'start' ? new Point(x, y) : absStart;
    const ne = which === 'end' ? new Point(x, y) : absEnd;
    line.set({ angle: 0, scaleX: 1, scaleY: 1, skewX: 0, skewY: 0, x1: ns.x, y1: ns.y, x2: ne.x, y2: ne.y });
    line.setCoords();
    return true;
  };
}

classRegistry.setClass(Connector);
classRegistry.setClass(Connector, 'connector');
