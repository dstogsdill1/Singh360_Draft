import type { CanvasSelection, PageModel } from '../model/types';

interface Props {
  page: PageModel;
  onChange: (next: PageModel) => void;
  selection: CanvasSelection | null;
  onUpdateSelection: (patch: Partial<CanvasSelection>) => void;
}

export default function PropertiesPanel({ page, onChange, selection, onUpdateSelection }: Props) {
  return (
    <>
      <div className="props-group">
        <h3>Page Properties</h3>
        <div className="field">
          <label htmlFor="page-code">Sheet Code</label>
          <input id="page-code" value={page.sheetCode} onChange={(e) => onChange({ ...page, sheetCode: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="page-title">Sheet Title</label>
          <input id="page-title" value={page.sheetTitle} onChange={(e) => onChange({ ...page, sheetTitle: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="page-type">Page Type</label>
          <select id="page-type" value={page.pageType} onChange={(e) => onChange({ ...page, pageType: e.target.value as PageModel['pageType'] })}>
            <option value="data-grid">data-grid</option>
            <option value="canvas">canvas</option>
            <option value="underlay">underlay</option>
            <option value="hybrid">hybrid</option>
            <option value="cover">cover</option>
            <option value="index">index</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="page-notes">Notes</label>
          <textarea id="page-notes" value={page.notes} onChange={(e) => onChange({ ...page, notes: e.target.value })} rows={4} />
        </div>
      </div>

      <div className="props-group">
        <h3>Selection Properties</h3>
        {!selection ? (
          <p className="props-note">Select a table cell, shape, or object to edit properties.</p>
        ) : (
          <>
            <div className="field">
              <label htmlFor="sel-type">Object Type</label>
              <input id="sel-type" title="Object type" value={selection.type} readOnly />
            </div>
            <div className="field">
              <label htmlFor="sel-fill">Fill</label>
              <input id="sel-fill" type="text" value={selection.fill} placeholder="transparent" onChange={(e) => onUpdateSelection({ fill: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sel-stroke">Stroke</label>
              <input id="sel-stroke" type="text" value={selection.stroke} placeholder="#111111" onChange={(e) => onUpdateSelection({ stroke: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="sel-sw">Stroke Width</label>
              <input id="sel-sw" type="number" min={0} step={0.5} value={selection.strokeWidth} onChange={(e) => onUpdateSelection({ strokeWidth: Number(e.target.value) })} />
            </div>
            {selection.fontSize !== undefined && (
              <div className="field">
                <label htmlFor="sel-fs">Font Size</label>
                <input id="sel-fs" type="number" min={6} step={1} value={selection.fontSize} onChange={(e) => onUpdateSelection({ fontSize: Number(e.target.value) })} />
              </div>
            )}
            <div className="field">
              <label>
                <input type="checkbox" checked={selection.locked} onChange={(e) => onUpdateSelection({ locked: e.target.checked })} /> Lock object
              </label>
            </div>
          </>
        )}
      </div>
    </>
  );
}
