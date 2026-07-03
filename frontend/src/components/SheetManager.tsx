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
    <>
      {pages.map((p, idx) => (
        <div
          key={p.id}
          className={`sheet-item ${p.id === activePageId ? 'active' : ''}`}
          onClick={() => onSelect(p.id)}
        >
          <div className="sheet-item-head">
            <span className="sheet-item-code">{p.sheetCode}</span>
            <span className="sheet-item-title">{p.sheetTitle}</span>
            <div className="sheet-item-actions" onClick={(e) => e.stopPropagation()}>
              <button className="reorder-btn" title="Move up" onClick={() => move(idx, -1)}>↑</button>
              <button className="reorder-btn" title="Move down" onClick={() => move(idx, 1)}>↓</button>
            </div>
          </div>
          <div className="sheet-item-meta" onClick={(e) => e.stopPropagation()}>
            <label>
              <input
                type="checkbox"
                checked={p.include}
                onChange={(e) => {
                  const clone = [...pages];
                  clone[idx] = { ...clone[idx], include: e.target.checked };
                  onUpdate(clone);
                }}
              />
              include
            </label>
            <select
              className="sheet-item-type"
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
          </div>
        </div>
      ))}
    </>
  );
}
