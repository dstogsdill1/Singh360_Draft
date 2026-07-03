import type { PageModel } from '../model/types';

interface Props {
  page: PageModel;
  onChange: (next: PageModel) => void;
}

export default function PropertiesPanel({ page, onChange }: Props) {
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
          <textarea id="page-notes" value={page.notes} onChange={(e) => onChange({ ...page, notes: e.target.value })} rows={5} />
        </div>
      </div>

      <div className="props-group">
        <h3>Selection Properties</h3>
        <p className="props-note">Select a table cell, shape, or object to edit properties.</p>
        <div className="props-placeholder-field">
          <label>Fill</label>
          <div className="fake-input" />
        </div>
        <div className="props-placeholder-field">
          <label>Stroke</label>
          <div className="fake-input" />
        </div>
        <div className="props-placeholder-field">
          <label>Line Weight</label>
          <div className="fake-input" />
        </div>
        <div className="props-placeholder-field">
          <label>Lock / Layer</label>
          <div className="fake-input" />
        </div>
      </div>
    </>
  );
}
