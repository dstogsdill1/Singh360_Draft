import type { PageModel } from '../model/types';

interface Props {
  page: PageModel;
  onChange: (next: PageModel) => void;
}

export default function PropertiesPanel({ page, onChange }: Props) {
  return (
    <div className="props-panel">
      <h3>Page Properties</h3>
      <label>Sheet Code</label>
      <input title="Sheet Code" placeholder="Sheet Code" value={page.sheetCode} onChange={(e) => onChange({ ...page, sheetCode: e.target.value })} />
      <label>Sheet Title</label>
      <input title="Sheet Title" placeholder="Sheet Title" value={page.sheetTitle} onChange={(e) => onChange({ ...page, sheetTitle: e.target.value })} />
      <label>Page Type</label>
      <select title="Page Type" value={page.pageType} onChange={(e) => onChange({ ...page, pageType: e.target.value as PageModel['pageType'] })}>
        <option value="data-grid">data-grid</option>
        <option value="canvas">canvas</option>
        <option value="underlay">underlay</option>
        <option value="hybrid">hybrid</option>
        <option value="cover">cover</option>
        <option value="index">index</option>
      </select>
      <label>Notes</label>
      <textarea title="Notes" placeholder="Page notes" value={page.notes} onChange={(e) => onChange({ ...page, notes: e.target.value })} rows={6} />
      <p className="props-note">Canvas properties (stroke/fill/font/layer/lock) are available through Fabric object controls in this milestone.</p>
    </div>
  );
}
