import type { PageModel } from '../model/types';

interface Props {
  pages: PageModel[];
  activePageId: string | null;
  onSelect: (id: string) => void;
}

export default function PageTabs({ pages, activePageId, onSelect }: Props) {
  const included = pages.filter((p) => p.include);
  return (
    <div className="page-tabs">
      {included.map((p) => (
        <button
          key={p.id}
          className={`page-tab ${p.id === activePageId ? 'active' : ''}`}
          onClick={() => onSelect(p.id)}
          title={`${p.sheetCode} ${p.sheetTitle}`}
        >
          <span className="pt-code">{p.sheetCode}</span>
          <span className="pt-title">{p.sheetTitle}</span>
        </button>
      ))}
    </div>
  );
}
