import { useState } from 'react';
import type { BusOptions } from '../model/types';
import { CONNECTOR_PRESETS, dashArray, type DashStyle } from '../model/connectorPresets';

interface Props {
  onCreate: (opts: BusOptions) => void;
  onCancel: () => void;
}

// Bus / Harness — capture how many parallel wires, their labels, and the style
// preset. After OK the canvas enters a two-click capture (start point → end
// point) and draws N evenly-spaced parallel connectors.
export default function BusModal({ onCreate, onCancel }: Props) {
  const [count, setCount] = useState(3);
  const [labelText, setLabelText] = useState('C1, C2, C3');
  const [presetId, setPresetId] = useState('control');
  const [spacing, setSpacing] = useState(18);
  const [orthogonal, setOrthogonal] = useState(true);

  const preset = CONNECTOR_PRESETS.find((p) => p.id === presetId) ?? CONNECTOR_PRESETS[0];

  const submit = () => {
    const n = Math.max(1, Math.min(24, Math.round(count)));
    const labels = labelText
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    onCreate({
      count: n,
      labels,
      presetId: preset.id,
      stroke: preset.stroke,
      strokeWidth: preset.strokeWidth,
      dash: preset.dash as DashStyle,
      spacing: Math.max(6, spacing),
      orthogonal,
    });
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal bus-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Bus / Harness</h3>
        <p className="bus-help">
          Create several parallel routed wires at once. Set the count, labels and
          style, then click a start point and an end point on the page.
        </p>
        <label className="bus-row">
          <span>Number of wires</span>
          <input type="number" min={1} max={24} value={count} onChange={(e) => setCount(Number(e.target.value))} />
        </label>
        <label className="bus-row">
          <span>Labels (comma-separated)</span>
          <input value={labelText} onChange={(e) => setLabelText(e.target.value)} placeholder="C1, C2, C3 or LI, DA, LS" />
        </label>
        <label className="bus-row">
          <span>Style preset</span>
          <select title="Bus style preset" value={presetId} onChange={(e) => setPresetId(e.target.value)}>
            {CONNECTOR_PRESETS.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="bus-row">
          <span>Spacing (px)</span>
          <input type="number" min={6} max={60} value={spacing} onChange={(e) => setSpacing(Number(e.target.value))} />
        </label>
        <label className="bus-row bus-check">
          <input type="checkbox" checked={orthogonal} onChange={(e) => setOrthogonal(e.target.checked)} />
          <span>Orthogonal (square) routing</span>
        </label>
        <svg width="100%" height="34" className="bus-preview">
          {Array.from({ length: Math.max(1, Math.min(6, count)) }).map((_, i) => (
            <line
              key={i}
              x1={8}
              x2="96%"
              y1={6 + i * 5}
              y2={6 + i * 5}
              stroke={preset.stroke}
              strokeWidth={preset.strokeWidth}
              strokeDasharray={(dashArray(preset.dash as DashStyle, preset.strokeWidth) || []).join(' ')}
            />
          ))}
        </svg>
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={submit}>Place Bus</button>
          <button className="btn" onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
