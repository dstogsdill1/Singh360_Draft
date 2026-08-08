import type {
  AnnotationApi,
  AnnotationSelection,
  AnnotationSettings,
  AnnotationStyle,
  AnnotationTool,
} from '../model/types';

interface Props {
  tool: AnnotationTool;
  style: AnnotationStyle;
  settings: AnnotationSettings;
  selection: AnnotationSelection | null;
  api: AnnotationApi | null;
  onToolChange: (tool: AnnotationTool) => void;
  onStyleChange: (style: AnnotationStyle) => void;
  onSettingsChange: (settings: AnnotationSettings) => void;
  onClose: () => void;
}

const TOOLS: Array<{ tool: AnnotationTool; icon: string; label: string }> = [
  { tool: 'select', icon: '↖', label: 'Select Annotation' },
  { tool: 'rectangle', icon: '▭', label: 'Rectangle' },
  { tool: 'text', icon: 'T', label: 'Text' },
  { tool: 'arrow', icon: '➜', label: 'Arrow' },
  { tool: 'highlight', icon: '▰', label: 'Highlight' },
  { tool: 'pen', icon: '✎', label: 'Pen' },
];

const QUICK_COLORS = ['#d71920', '#ff8c00', '#ffe600', '#16803a', '#12539b', '#6f42c1', '#111111'];

function NumberRange({
  label,
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="annotation-property-row">
      <span>{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <output>{Number.isInteger(value) ? value : value.toFixed(2)}</output>
    </label>
  );
}

export default function AnnotationToolbar({
  tool,
  style,
  settings,
  selection,
  api,
  onToolChange,
  onStyleChange,
  onSettingsChange,
  onClose,
}: Props) {
  const selectedColor = selection?.color || style.color;
  const selectedOpacity = selection?.opacity ?? style.opacity;
  const selectedWidth = selection?.strokeWidth ?? style.strokeWidth;

  const updateColor = (color: string) => {
    onStyleChange({ ...style, color });
    api?.updateSelected({ color });
  };
  const updateOpacity = (opacity: number) => {
    onStyleChange({ ...style, opacity });
    api?.updateSelected({ opacity });
  };
  const updateWidth = (strokeWidth: number) => {
    onStyleChange({ ...style, strokeWidth });
    api?.updateSelected({ strokeWidth });
  };

  return (
    <aside
      className={`annotation-dock ${selection ? 'has-selection' : ''}`}
      aria-label="Annotation tools"
      data-testid="annotation-toolbar"
      data-noexport
    >
      <div className="annotation-primary-tools" role="toolbar" aria-label="Annotation drawing tools">
        <div className="annotation-dock-title" title="Page-local annotations">Markup</div>
        {TOOLS.map((item) => (
          <button
            key={item.tool}
            type="button"
            className={`annotation-tool-button ${tool === item.tool ? 'active' : ''}`}
            aria-label={item.label}
            title={item.label}
            aria-pressed={tool === item.tool}
            disabled={settings.locked && item.tool !== 'select'}
            onClick={() => onToolChange(tool === item.tool && item.tool !== 'select' ? 'select' : item.tool)}
          >
            <span aria-hidden="true">{item.icon}</span>
          </button>
        ))}
        <span className="annotation-tool-divider" />
        <button
          type="button"
          className={`annotation-tool-button ${settings.visible ? 'active' : ''}`}
          aria-label={settings.visible ? 'Hide Annotations' : 'Show Annotations'}
          title={settings.visible ? 'Hide Annotations' : 'Show Annotations'}
          aria-pressed={settings.visible}
          onClick={() => onSettingsChange({ ...settings, visible: !settings.visible })}
        >
          <span aria-hidden="true">{settings.visible ? '◉' : '○'}</span>
        </button>
        <button
          type="button"
          className={`annotation-tool-button ${settings.locked ? 'active' : ''}`}
          aria-label={settings.locked ? 'Unlock Annotations' : 'Lock Annotations'}
          title={settings.locked ? 'Unlock Annotations' : 'Lock Annotations'}
          aria-pressed={settings.locked}
          onClick={() => onSettingsChange({ ...settings, locked: !settings.locked })}
        >
          <span aria-hidden="true">{settings.locked ? '🔒' : '🔓'}</span>
        </button>
        <button
          type="button"
          className={`annotation-tool-button ${settings.includeInExport ? 'active' : ''}`}
          aria-label={settings.includeInExport ? 'Exclude Annotations from Export' : 'Include Annotations in Export'}
          title={settings.includeInExport ? 'Included in PDF export' : 'Excluded from PDF export'}
          aria-pressed={settings.includeInExport}
          onClick={() => onSettingsChange({
            ...settings,
            includeInExport: !settings.includeInExport,
          })}
        >
          <span aria-hidden="true">PDF</span>
        </button>
        <button type="button" className="annotation-tool-button" aria-label="Undo Annotation" title="Undo Annotation" onClick={() => api?.undo()}>↶</button>
        <button type="button" className="annotation-tool-button" aria-label="Redo Annotation" title="Redo Annotation" onClick={() => api?.redo()}>↷</button>
        <button
          type="button"
          className="annotation-tool-button danger"
          aria-label="Delete Selected Annotation"
          title="Delete Selected Annotation"
          disabled={!selection || settings.locked}
          onClick={() => api?.deleteSelected()}
        >
          ⌫
        </button>
        <button
          type="button"
          className="annotation-tool-button danger"
          aria-label="Delete All Annotations on Current Page"
          title="Delete All Annotations on Current Page"
          disabled={settings.locked}
          onClick={() => {
            if (window.confirm('Delete all annotations on this page? Normal drawing objects will not be changed.')) {
              api?.deleteAll();
            }
          }}
        >
          All
        </button>
        <button type="button" className="annotation-tool-button annotation-close" aria-label="Close Annotations" title="Close Annotations" onClick={onClose}>×</button>
      </div>

      {selection ? (
        <section className="annotation-properties" aria-label="Selected annotation properties" data-testid="annotation-properties">
          <header>
            <strong>{selection.annotationType}</strong>
            <span>Page markup</span>
          </header>

          <div className="annotation-color-palette" aria-label="Annotation quick colors">
            {QUICK_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={`Set annotation color ${color}`}
                title={color}
                className={selectedColor.toLowerCase() === color.toLowerCase() ? 'active' : ''}
                style={{ backgroundColor: color }}
                onClick={() => updateColor(color)}
              />
            ))}
            <label className="annotation-custom-color" title="Custom annotation color">
              <span>Custom</span>
              <input
                type="color"
                aria-label="Custom annotation color"
                value={selectedColor.startsWith('#') ? selectedColor : '#d71920'}
                onChange={(event) => updateColor(event.target.value)}
              />
            </label>
          </div>

          <NumberRange label="Annotation opacity" min={0.1} max={1} step={0.05} value={selectedOpacity} onChange={updateOpacity} />
          {selection.annotationType !== 'text' ? (
            <NumberRange label="Annotation stroke width" min={1} max={40} step={1} value={selectedWidth} onChange={updateWidth} />
          ) : null}

          {selection.annotationType === 'rectangle' ? (
            <div className="annotation-subproperties">
              <label>
                <span>Fill</span>
                <input
                  type="color"
                  aria-label="Rectangle fill color"
                  value={selection.fillColor || style.fillColor}
                  onChange={(event) => api?.updateSelected({ fillColor: event.target.value })}
                />
              </label>
              <NumberRange
                label="Rectangle fill opacity"
                min={0}
                max={1}
                step={0.05}
                value={selection.fillOpacity ?? style.fillOpacity}
                onChange={(fillOpacity) => api?.updateSelected({ fillOpacity })}
              />
              <button type="button" onClick={() => api?.updateSelected({ fillOpacity: 0 })}>Transparent Fill</button>
            </div>
          ) : null}

          {selection.annotationType === 'text' ? (
            <div className="annotation-subproperties">
              <label>
                <span>Font size</span>
                <input
                  type="number"
                  min={8}
                  max={96}
                  aria-label="Annotation font size"
                  value={selection.fontSize ?? style.fontSize}
                  onChange={(event) => api?.updateSelected({ fontSize: Number(event.target.value) })}
                />
              </label>
              <button
                type="button"
                className={selection.bold ? 'active' : ''}
                aria-pressed={Boolean(selection.bold)}
                onClick={() => api?.updateSelected({ bold: !selection.bold })}
              >
                Bold
              </button>
              <label>
                <span>Background</span>
                <input
                  type="color"
                  aria-label="Annotation text background color"
                  value={selection.backgroundColor || style.backgroundColor}
                  onChange={(event) => api?.updateSelected({ backgroundColor: event.target.value })}
                />
              </label>
              <NumberRange
                label="Annotation text background opacity"
                min={0}
                max={1}
                step={0.05}
                value={selection.backgroundOpacity ?? style.backgroundOpacity}
                onChange={(backgroundOpacity) => api?.updateSelected({ backgroundOpacity })}
              />
            </div>
          ) : null}

          {selection.annotationType === 'pen' ? (
            <NumberRange
              label="Pen smoothing"
              min={0}
              max={10}
              step={1}
              value={selection.smoothing ?? style.smoothing}
              onChange={(smoothing) => api?.updateSelected({ smoothing })}
            />
          ) : null}

          {selection.annotationType === 'arrow' ? (
            <button
              type="button"
              className={selection.arrowEnd === false ? '' : 'active'}
              aria-pressed={selection.arrowEnd === false ? false : true}
              onClick={() => api?.updateSelected({ arrowEnd: selection.arrowEnd === false })}
            >
              Arrowhead
            </button>
          ) : null}

          <div className="annotation-property-actions">
            <button type="button" onClick={() => api?.duplicateSelected()}>Duplicate</button>
            <button type="button" onClick={() => api?.bringForward()}>Bring Forward</button>
            <button type="button" onClick={() => api?.sendBackward()}>Send Backward</button>
            <button type="button" className="danger" onClick={() => api?.deleteSelected()}>Delete</button>
          </div>
        </section>
      ) : null}
    </aside>
  );
}
