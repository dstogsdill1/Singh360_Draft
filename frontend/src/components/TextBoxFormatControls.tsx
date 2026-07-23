import type { ChangeEvent } from 'react';
import type { CanvasSelection } from '../model/types';

interface Props {
  selection: CanvasSelection | null;
  onChange: (patch: Partial<CanvasSelection>) => void;
}

const safeColor = (value: string | undefined, fallback: string): string => {
  if (typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)) return value;
  return fallback;
};

export default function TextBoxFormatControls({ selection, onChange }: Props) {
  const enabled = Boolean(selection?.isTextBox);
  const fill = safeColor(selection?.textBoxFill, '#ffffff');
  const outline = safeColor(selection?.textBoxStroke, '#111111');
  const opacity = Math.round((selection?.textBoxFillOpacity ?? 1) * 100);
  const lineWidth = Number(selection?.textBoxStrokeWidth ?? 0);
  const padding = Number(selection?.textBoxPadding ?? 8);
  const radius = Number(selection?.textBoxRadius ?? 0);

  return (
    <div className="s360-textbox-ribbon" aria-label="Text box fill and outline">
      <div className="s360-textbox-control">
        <span>Fill</span>
        <input
          type="color"
          value={fill}
          disabled={!enabled}
          title="Text box background fill"
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange({
            textBoxFill: event.target.value,
            textBoxFillOpacity: selection?.textBoxFillOpacity ?? 1,
          })}
        />
        <button
          type="button"
          className="ribbon-btn"
          disabled={!enabled}
          onClick={() => onChange({ textBoxFill: '#ffffff', textBoxFillOpacity: 1 })}
          title="White text box background"
        >
          White
        </button>
        <button
          type="button"
          className="ribbon-btn"
          disabled={!enabled}
          onClick={() => onChange({ textBoxFill: 'transparent' })}
          title="Remove the text box background"
        >
          No Fill
        </button>
      </div>

      <div className="s360-textbox-control">
        <span>Opacity</span>
        <select
          value={opacity}
          disabled={!enabled}
          title="Text box background opacity"
          onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange({ textBoxFillOpacity: Number(event.target.value) / 100 })}
        >
          <option value={100}>100%</option>
          <option value={75}>75%</option>
          <option value={50}>50%</option>
          <option value={25}>25%</option>
          <option value={10}>10%</option>
        </select>
      </div>

      <div className="s360-textbox-control">
        <span>Outline</span>
        <input
          type="color"
          value={outline}
          disabled={!enabled}
          title="Text box outline color"
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange({
            textBoxStroke: event.target.value,
            textBoxStrokeWidth: Math.max(1, lineWidth || 1),
          })}
        />
        <button
          type="button"
          className="ribbon-btn"
          disabled={!enabled}
          onClick={() => onChange({ textBoxStroke: '#111111', textBoxStrokeWidth: 1 })}
        >
          Black
        </button>
        <button
          type="button"
          className="ribbon-btn"
          disabled={!enabled}
          onClick={() => onChange({ textBoxStroke: 'transparent', textBoxStrokeWidth: 0 })}
        >
          No Outline
        </button>
      </div>

      <div className="s360-textbox-control">
        <span>Line</span>
        <select
          value={lineWidth}
          disabled={!enabled}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => {
            const next = Number(event.target.value);
            onChange({
              textBoxStrokeWidth: next,
              textBoxStroke: next > 0
                ? (selection?.textBoxStroke && selection.textBoxStroke !== 'transparent'
                    ? selection.textBoxStroke
                    : '#111111')
                : 'transparent',
            });
          }}
        >
          <option value={0}>None</option>
          <option value={1}>1 px</option>
          <option value={2}>2 px</option>
          <option value={3}>3 px</option>
          <option value={4}>4 px</option>
          <option value={6}>6 px</option>
        </select>
      </div>

      <div className="s360-textbox-control">
        <span>Padding</span>
        <input
          type="number"
          min={0}
          max={48}
          step={1}
          value={padding}
          disabled={!enabled}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onChange({
            textBoxPadding: Math.max(0, Math.min(48, Number(event.target.value) || 0)),
          })}
        />
      </div>

      <div className="s360-textbox-control">
        <span>Corners</span>
        <select
          value={radius}
          disabled={!enabled}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange({ textBoxRadius: Number(event.target.value) })}
        >
          <option value={0}>Square</option>
          <option value={4}>4 px</option>
          <option value={8}>8 px</option>
          <option value={12}>12 px</option>
          <option value={18}>18 px</option>
        </select>
      </div>

      <div className="s360-textbox-control s360-textbox-presets">
        <span>Presets</span>
        <button
          type="button"
          className="ribbon-btn"
          disabled={!enabled}
          onClick={() => onChange({
            textBoxFill: '#ffffff',
            textBoxFillOpacity: 1,
            textBoxStroke: '#111111',
            textBoxStrokeWidth: 1,
            textBoxPadding: 8,
            textBoxRadius: 0,
          })}
        >
          White Box
        </button>
        <button
          type="button"
          className="ribbon-btn"
          disabled={!enabled}
          onClick={() => onChange({
            textBoxFill: '#ffffff',
            textBoxFillOpacity: 1,
            textBoxStroke: '#f28c28',
            textBoxStrokeWidth: 2,
            textBoxPadding: 10,
            textBoxRadius: 8,
          })}
        >
          Callout
        </button>
        <button
          type="button"
          className="ribbon-btn"
          disabled={!enabled}
          onClick={() => onChange({
            textBoxFill: 'transparent',
            textBoxStroke: 'transparent',
            textBoxStrokeWidth: 0,
          })}
        >
          Clear Box
        </button>
      </div>

      {!enabled ? <div className="s360-textbox-hint">Select a text box to format its box.</div> : null}
      <div className="s360-textbox-ribbon-title">TEXT BOX</div>
    </div>
  );
}
