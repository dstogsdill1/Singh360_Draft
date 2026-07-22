import { useRef, useState, type PointerEvent } from 'react';
import type { ImageCropPlacement, ImageCropRect, ImageCropState } from '../model/types';

interface Props {
  state: ImageCropState;
  onApply: (crop: ImageCropRect, placement: ImageCropPlacement) => void;
  onCancel: () => void;
}

const MIN_SIZE = 0.01;

function clamp(value: number, low = 0, high = 1): number {
  return Math.max(low, Math.min(high, value));
}

function normalizeRect(a: { x: number; y: number }, b: { x: number; y: number }): ImageCropRect {
  const x0 = clamp(Math.min(a.x, b.x));
  const y0 = clamp(Math.min(a.y, b.y));
  const x1 = clamp(Math.max(a.x, b.x));
  const y1 = clamp(Math.max(a.y, b.y));
  return {
    x: x0,
    y: y0,
    width: Math.max(MIN_SIZE, x1 - x0),
    height: Math.max(MIN_SIZE, y1 - y0),
  };
}

export default function ImageCropModal({ state, onApply, onCancel }: Props) {
  const [crop, setCrop] = useState<ImageCropRect>(state.crop);
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);

  const point = (event: PointerEvent<HTMLDivElement>) => {
    const stage = stageRef.current;
    if (!stage) return { x: 0, y: 0 };
    const bounds = stage.getBoundingClientRect();
    return {
      x: clamp((event.clientX - bounds.left) / Math.max(1, bounds.width)),
      y: clamp((event.clientY - bounds.top) / Math.max(1, bounds.height)),
    };
  };

  const startCrop = (event: PointerEvent<HTMLDivElement>) => {
    const p = point(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    setStart(p);
    setCrop({ x: p.x, y: p.y, width: MIN_SIZE, height: MIN_SIZE });
  };

  const moveCrop = (event: PointerEvent<HTMLDivElement>) => {
    if (!start) return;
    setCrop(normalizeRect(start, point(event)));
  };

  const finishCrop = (event: PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setStart(null);
  };

  const apply = (placement: ImageCropPlacement) => {
    const safe: ImageCropRect = {
      x: clamp(crop.x),
      y: clamp(crop.y),
      width: clamp(crop.width, MIN_SIZE, 1 - clamp(crop.x)),
      height: clamp(crop.height, MIN_SIZE, 1 - clamp(crop.y)),
    };
    onApply(safe, placement);
  };

  return (
    <div className="modal-backdrop image-crop-backdrop" onClick={onCancel}>
      <div className="modal modal-wide image-crop-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>Crop / Fit Image</h2>
            <p className="image-crop-sub">Drag a box over the part you want to keep. The original image asset is not altered.</p>
          </div>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>
        <div className="modal-body image-crop-body">
          <div className="image-crop-info">
            <strong>{state.name || 'Selected image'}</strong>
            <span>{Math.round(state.naturalWidth)} × {Math.round(state.naturalHeight)} px</span>
            {state.locked && <em>Locked image — it will remain locked after cropping.</em>}
          </div>
          <div className="image-crop-stage-scroll">
            <div
              ref={stageRef}
              className="image-crop-stage"
              style={{ aspectRatio: `${Math.max(1, state.naturalWidth)} / ${Math.max(1, state.naturalHeight)}` }}
              onPointerDown={startCrop}
              onPointerMove={moveCrop}
              onPointerUp={finishCrop}
              onPointerCancel={finishCrop}
            >
              <img src={state.sourceUrl} alt="Selected source" draggable={false} />
              <div
                className="image-crop-selection"
                style={{
                  left: `${crop.x * 100}%`,
                  top: `${crop.y * 100}%`,
                  width: `${crop.width * 100}%`,
                  height: `${crop.height * 100}%`,
                }}
              >
                <span className="crop-handle nw" />
                <span className="crop-handle ne" />
                <span className="crop-handle sw" />
                <span className="crop-handle se" />
              </div>
            </div>
          </div>
          <div className="image-crop-readout">
            Keep: {Math.round(crop.width * 100)}% wide × {Math.round(crop.height * 100)}% high
          </div>
        </div>
        <div className="modal-foot image-crop-foot">
          <button className="btn" onClick={() => setCrop({ x: 0, y: 0, width: 1, height: 1 })}>Reset crop</button>
          <span className="image-crop-spacer" />
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn" onClick={() => apply('keep')} title="Keep the current on-page size and replace its visible area">Apply crop</button>
          <button className="btn" onClick={() => apply('fit')} title="Show the entire crop inside the Singh360 drawing area">Fit crop to page</button>
          <button className="btn btn-primary" onClick={() => apply('fill')} title="Fill the Singh360 drawing area; the crop is centered to the page aspect ratio">Fill page with crop</button>
        </div>
      </div>
    </div>
  );
}
