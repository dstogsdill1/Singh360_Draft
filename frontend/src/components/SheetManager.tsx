import type { PageModel } from '../model/types';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
  onUpdate: (next: PageModel[]) => void;
}

const PAGE_TYPES: Array<PageModel['pageType']> = ['data-grid', 'canvas', 'underlay', 'hybrid', 'cover', 'index'];

export default function SheetManager({ pages, activePageId, onSelect, onUpdate }: Props) {
  const move = (idx: number, dir: -1 | 1) => {
    const t = idx + dir;
    if (t < 0 || t >= pages.length) return;
    const clone = [...pages];
    [clone[idx], clone[t]] = [clone[t], clone[idx]];
    clone.forEach((p, i) => (p.order = i + 1));
    onUpdate(clone);
  };

  return (
    <div>
      <h3 className="section-title">Output Pages</h3>
      {pages.map((p, idx) => (
        <div key={p.id} className={`sheet-item ${p.id === activePageId ? 'active' : ''}`}>
          <div onClick={() => onSelect(p.id)} className="sheet-item-title">{p.sheetCode} — {p.sheetTitle}</div>
          <div className="sheet-item-fields">
            <label>
              <input
                type="checkbox"
                checked={p.include}
                onChange={(e) => {
                  const clone = [...pages];
                  clone[idx] = { ...clone[idx], include: e.target.checked };
                  onUpdate(clone);
                }}
              /> include
            </label>
            <input
              value={p.sheetTitle}
              onChange={(e) => {
                const clone = [...pages];
                clone[idx] = { ...clone[idx], sheetTitle: e.target.value };
                onUpdate(clone);
              }}
              placeholder="Sheet Title"
            />
            <input
              value={p.sheetCode}
              onChange={(e) => {
                const clone = [...pages];
                clone[idx] = { ...clone[idx], sheetCode: e.target.value };
                onUpdate(clone);
              }}
              placeholder="Sheet Code"
            />
            <select
              title="Page type"
              value={p.pageType}
              onChange={(e) => {
                const clone = [...pages];
                clone[idx] = { ...clone[idx], pageType: e.target.value as PageModel['pageType'] };
                onUpdate(clone);
              }}
            >
              {PAGE_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <div className="sheet-item-actions">
              <button onClick={() => move(idx, -1)}>↑</button>
              <button onClick={() => move(idx, 1)}>↓</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
