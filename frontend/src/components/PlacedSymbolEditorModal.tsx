import { useState } from 'react';
import type { PlacedSymbolEditorConfig } from '../model/types';

interface Props {
  initialConfig: PlacedSymbolEditorConfig;
  sourceUrl?: string;
  onApply: (config: PlacedSymbolEditorConfig) => void;
  onCancel: () => void;
}
export default function PlacedSymbolEditorModal({
  initialConfig,
  sourceUrl,
  onApply,
  onCancel,
}: Props) {
  const [config, setConfig] = useState<PlacedSymbolEditorConfig>(() => ({ ...initialConfig }));

  const patch = (values: Partial<PlacedSymbolEditorConfig>) => {
    setConfig((current) => ({ ...current, ...values }));
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <form
        className="modal placed-symbol-editor-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Symbol and component editor"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          onApply({
            ...config,
            name: config.name.trim() || 'Placed Symbol',
            width: Math.max(16, Number(config.width) || 16),
            height: Math.max(16, Number(config.height) || 16),
            opacity: Math.max(0.05, Math.min(1, Number(config.opacity) || 1)),
          });
        }}
      >
        <div className="modal-head">
          <div>
            <h2>Symbol / Component Editor</h2>
            <p>Edit the selected placed symbol without inserting a replacement.</p>
          </div>
          <button type="button" className="modal-x" aria-label="Close symbol editor" onClick={onCancel}>×</button>
        </div>
        <div className="modal-body placed-symbol-editor-body">
          <div className="placed-symbol-editor-preview">
            {sourceUrl ? <img src={sourceUrl} alt="" /> : <span>Editable placed object</span>}
            {config.label ? <strong>{config.label}</strong> : null}
          </div>
          <div className="smart-component-grid">
            <label className="smart-component-span">
              Object name
              <input
                aria-label="Placed symbol name"
                value={config.name}
                onChange={(event) => patch({ name: event.target.value })}
              />
            </label>
            <label className="smart-component-span">
              Visible label
              <input
                aria-label="Placed symbol label"
                value={config.label}
                onChange={(event) => patch({ label: event.target.value })}
              />
            </label>
            <label>
              Width
              <input
                aria-label="Placed symbol width"
                type="number"
                min={16}
                value={config.width}
                onChange={(event) => patch({ width: Number(event.target.value) })}
              />
            </label>
            <label>
              Height
              <input
                aria-label="Placed symbol height"
                type="number"
                min={16}
                value={config.height}
                onChange={(event) => patch({ height: Number(event.target.value) })}
              />
            </label>
            <label>
              Category
              <input
                aria-label="Placed symbol category"
                value={config.category}
                onChange={(event) => patch({ category: event.target.value })}
              />
            </label>
            <label>
              Opacity
              <input
                aria-label="Placed symbol opacity"
                type="number"
                min={0.05}
                max={1}
                step={0.05}
                value={config.opacity}
                onChange={(event) => patch({ opacity: Number(event.target.value) })}
              />
            </label>
            <label className="smart-component-check">
              <input
                aria-label="Favorite placed symbol"
                type="checkbox"
                checked={config.favorite}
                onChange={(event) => patch({ favorite: event.target.checked })}
              />
              Favorite
            </label>
          </div>
        </div>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn btn-primary">Save Symbol Changes</button>
        </div>
      </form>
    </div>
  );
}
