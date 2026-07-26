#!/usr/bin/env python3
"""Apply the exact V39 Component Library collection filter with scoped anchors."""
from __future__ import annotations

from pathlib import Path


PATH = Path("frontend/src/components/LibraryPanelV2.tsx")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0 and new in text:
        return text
    if count != 1:
        raise SystemExit(f"{label}: expected one exact anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    text = PATH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "const COLLECTION_PRESETS = [\n  'Controllers',",
        "const REFRIGERATION_SYMBOL_COLLECTION = 'Refrigeration Controls Symbols';\n\n"
        "const COLLECTION_PRESETS = [\n  'Controllers',",
        "collection constant",
    )

    text = replace_once(
        text,
        "  const [query, setQuery] = useState('');\n"
        "  const [category, setCategory] = useState('all');\n"
        "  const [rep, setRep] = useState<ViewRep>('source');",
        "  const [query, setQuery] = useState('');\n"
        "  const [category, setCategory] = useState('all');\n"
        "  const [collection, setCollection] = useState('all');\n"
        "  const [rep, setRep] = useState<ViewRep>('source');",
        "collection state",
    )

    old_cards = """  const collections = useMemo(() => {
    const set = new Set<string>();
    COLLECTION_PRESETS.forEach((x) => set.add(x));
    components.forEach((c) => {
      const val = collectionFor(c);
      if (val) set.add(val);
    });
    return Array.from(set).sort();
  }, [components]);

  const visibleCards = useMemo(() => {
    const q = query.trim().toLowerCase();
    return components.filter((c) => {
      if (category !== 'all' && !categoriesFor(c).includes(category)) return false;
      if (isRetired(c)) return false;
      if (!q) return true;
      return componentSearchBlob(c, edits).includes(q);
    });
  }, [components, query, category, edits]);
"""
    new_cards = """  const collections = useMemo(() => {
    const set = new Set<string>();
    COLLECTION_PRESETS.forEach((x) => set.add(x));
    components.forEach((c) => {
      const val = collectionFor(c);
      if (val) set.add(val);
    });
    return Array.from(set).sort();
  }, [components]);

  const refrigerationSymbolCount = useMemo(
    () => components.filter(
      (component) => !isRetired(component)
        && collectionFor(component) === REFRIGERATION_SYMBOL_COLLECTION,
    ).length,
    [components],
  );

  const visibleCards = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = components.filter((c) => {
      if (category !== 'all' && !categoriesFor(c).includes(category)) return false;
      if (collection !== 'all' && collectionFor(c) !== collection) return false;
      if (isRetired(c)) return false;
      if (!q) return true;
      return componentSearchBlob(c, edits).includes(q);
    });

    if (collection !== 'all') {
      rows.sort((a, b) => {
        const aOrder = Number(asAny(a).sortOrder || Number.MAX_SAFE_INTEGER);
        const bOrder = Number(asAny(b).sortOrder || Number.MAX_SAFE_INTEGER);
        if (aOrder !== bOrder) return aOrder - bOrder;
        return displayNameFor(a).localeCompare(displayNameFor(b), undefined, {
          numeric: true,
          sensitivity: 'base',
        });
      });
    }
    return rows;
  }, [components, query, category, collection, edits]);
"""
    text = replace_once(text, old_cards, new_cards, "visible-card collection filter")

    old_ui = """        <div className="libv2-row">
          <select className="libv2-grow" title="Filter by category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">All categories</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.label} ({c.count})</option>)}
          </select>
        </div>
        <div className="libv2-row libv2-modes">"""
    new_ui = """        <div className="libv2-row">
          <select className="libv2-grow" title="Filter by category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">All categories</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.label} ({c.count})</option>)}
          </select>
          <select className="libv2-grow" title="Filter by collection" value={collection} onChange={(e) => setCollection(e.target.value)}>
            <option value="all">All collections</option>
            {collections.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </div>
        <div className="libv2-row libv2-quick-filters">
          <button
            className={collection === REFRIGERATION_SYMBOL_COLLECTION ? 'active' : undefined}
            style={collection === REFRIGERATION_SYMBOL_COLLECTION
              ? { fontWeight: 800, background: '#e0f2fe', borderColor: '#0284c7' }
              : undefined}
            aria-pressed={collection === REFRIGERATION_SYMBOL_COLLECTION}
            onClick={() => {
              setCollection((current) => current === REFRIGERATION_SYMBOL_COLLECTION
                ? 'all'
                : REFRIGERATION_SYMBOL_COLLECTION);
              setCategory('all');
              setQuery('');
            }}
          >
            Refrigeration Symbols ({refrigerationSymbolCount})
          </button>
          {collection !== 'all' && (
            <button onClick={() => setCollection('all')}>Show All Components</button>
          )}
        </div>
        <div className="libv2-row libv2-modes">"""
    text = replace_once(text, old_ui, new_ui, "normal library collection controls")

    required = [
        "REFRIGERATION_SYMBOL_COLLECTION",
        "Filter by collection",
        "Refrigeration Symbols ({refrigerationSymbolCount})",
        "sortOrder || Number.MAX_SAFE_INTEGER",
    ]
    missing = [token for token in required if token not in text]
    if missing:
        raise SystemExit(f"post-edit verification failed: {missing}")

    PATH.write_text(text, encoding="utf-8")
    print("Applied exact symbol collection UI V39")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
