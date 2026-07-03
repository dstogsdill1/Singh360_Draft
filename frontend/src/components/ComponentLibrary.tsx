import { useEffect, useMemo, useState } from 'react';
import {
  getLibrary,
  importLibrarySeed,
  autoCategorizeLibrary,
  libraryAssetUrl,
  deleteLibraryComponent,
  retireLibraryComponent,
  restoreLibraryComponent,
  updateLibraryComponent,
  type LibraryComponent,
  type LibraryData,
} from '../api/client';

interface Props {
  onInsert: (name: string, url: string, label: string | null) => void;
  canInsert: boolean;
}

export const COMPONENT_DRAG_TYPE = 'application/x-singh360-component';

// Categories that should NOT get an auto label by default (logos/symbols/legends).
const NO_LABEL_CATS = new Set(['logos', 'logo', 'symbols', 'symbol', 'legends', 'legend', 'reference-page']);

function labelFor(c: LibraryComponent): string | null {
  const cat = (c.category || '').toLowerCase();
  if (NO_LABEL_CATS.has(cat)) return null;
  return c.partNumber || c.shortName || c.displayName || null;
}

// Canonical categories (must match core/library_taxonomy.py).
const CANON_CATS = [
  'controllers', 'expansion', 'panels', 'network', 'electrical', 'sensors', 'alarms',
  'refrigeration', 'lighting', 'symbols', 'legends', 'logos', 'reference-page', 'review', 'uncategorized',
];
const CAT_LABELS: Record<string, string> = {
  controllers: 'Controllers', expansion: 'Expansion Modules', panels: 'Panels / Enclosures',
  network: 'Network / Data', electrical: 'Electrical / Power', sensors: 'Sensors / Transducers',
  alarms: 'Alarms / Safety', refrigeration: 'Refrigeration', lighting: 'Lighting',
  symbols: 'Symbols / Markers', legends: 'Legends', logos: 'Logos',
  'reference-page': 'Reference Pages', review: 'Needs Review', uncategorized: 'Uncategorized',
};
const catLabel = (id: string) => CAT_LABELS[id] ?? id;

export default function ComponentLibrary({ onInsert, canInsert }: Props) {
  const [data, setData] = useState<LibraryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [showRetired, setShowRetired] = useState(false);
  const [insertWithLabel, setInsertWithLabel] = useState(true);
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editCat, setEditCat] = useState('');
  const [error, setError] = useState('');

  const refresh = async () => {
    try {
      setLoading(true);
      setData(await getLibrary());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const doImportSeed = async () => {
    setLoading(true);
    const res = await importLibrarySeed();
    if (!res.ok) setError(res.error || 'Seed import failed');
    await refresh();
  };

  const doAutoCategorize = async () => {
    try {
      const res = await autoCategorizeLibrary();
      await refresh();
      window.alert(`Auto-categorized ${res.changed} of ${res.total} components. Review and fine-tune with the ✎ edit button.`);
    } catch (e) {
      setError(String(e));
    }
  };

  const components = data?.components ?? [];
  const isRetired = (c: LibraryComponent) => (c.status || '').startsWith('retired');
  const isReference = (c: LibraryComponent) => (c.category || '').toLowerCase() === 'reference-page';

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return components.filter((c) => {
      if (isRetired(c) && !showRetired) return false;
      const cat = (c.category || 'uncategorized').toLowerCase();
      // Reference pages are hidden from the default "all" view (Phase A).
      if (category === 'all' && cat === 'reference-page') return false;
      if (category !== 'all' && cat !== category) return false;
      if (!q) return true;
      const hay = [c.displayName, c.shortName, c.partNumber, c.category, ...(c.aliases ?? []), ...(c.tags ?? [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }, [components, query, category, showRetired]);

  const insert = (c: LibraryComponent) => {
    if (!c.assetPath) return;
    onInsert(c.displayName, libraryAssetUrl(c.assetPath), insertWithLabel ? labelFor(c) : null);
  };

  const beginEdit = (c: LibraryComponent) => {
    setEditId(c.id);
    setEditName(c.displayName);
    setEditCat((c.category || 'uncategorized').toLowerCase());
  };
  const saveEdit = async (c: LibraryComponent) => {
    try {
      await updateLibraryComponent(c.id, { displayName: editName.trim() || c.displayName, category: editCat });
      setEditId(null);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const removeItem = async (c: LibraryComponent) => {
    const ok = window.confirm(
      `Delete this library item?\n\n"${c.displayName}"\n\nThis removes it from the local library but does NOT remove objects already placed on pages, and keeps the source asset file on disk.`,
    );
    if (!ok) return;
    try {
      await deleteLibraryComponent(c.id);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const retireItem = async (c: LibraryComponent) => {
    try {
      await retireLibraryComponent(c.id);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };
  const restoreItem = async (c: LibraryComponent) => {
    try {
      await restoreLibraryComponent(c.id);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  if (loading && !data) {
    return <div className="lib-empty">Loading component library…</div>;
  }

  if (!components.length) {
    return (
      <div className="lib-empty">
        <p>No components yet.</p>
        <button className="btn btn-primary" onClick={() => void doImportSeed()}>Import Seed Library</button>
        {error && <p className="lib-error">{error}</p>}
      </div>
    );
  }

  const cats = data?.categories ?? [];

  return (
    <div className="lib-panel">
      <div className="lib-controls">
        <input
          className="lib-search"
          type="search"
          placeholder="Search components…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search components"
        />
        <select className="lib-cat" value={category} onChange={(e) => setCategory(e.target.value)} title="Filter by category">
          <option value="all">All ({visible.length})</option>
          {cats.map((c) => (
            <option key={c.id} value={c.id}>{catLabel(c.id)} ({c.count})</option>
          ))}
        </select>
      </div>
      <label className="lib-showretired" title="Show retired components">
        <input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} /> Show retired
      </label>
      <label className="lib-showretired" title="Insert equipment/components with an editable text label (off for logos/symbols)">
        <input type="checkbox" checked={insertWithLabel} onChange={(e) => setInsertWithLabel(e.target.checked)} /> Insert with label
      </label>
      <div className="lib-toolbar">
        <button className="lib-btn" onClick={() => void doAutoCategorize()} title="Auto-assign categories from part names/keywords (review afterwards)">Auto-categorize</button>
      </div>

      <div className="lib-grid">
        {visible.map((c) => (
          <div
            key={c.id}
            className={`lib-card ${isRetired(c) ? 'retired' : ''}`}
            draggable={canInsert && editId !== c.id}
            onDragStart={(e) => {
              if (!c.assetPath) return;
              e.dataTransfer.setData(
                COMPONENT_DRAG_TYPE,
                JSON.stringify({ name: c.displayName, url: libraryAssetUrl(c.assetPath), label: insertWithLabel ? labelFor(c) : null }),
              );
              e.dataTransfer.effectAllowed = 'copy';
            }}
            onDoubleClick={() => canInsert && editId !== c.id && insert(c)}
            title={`${c.displayName}${c.partNumber ? ` · ${c.partNumber}` : ''}${isReference(c) ? ' · reference page' : ''}`}
          >
            <div className="lib-thumb">
              {c.thumbnailPath ? (
                <img src={libraryAssetUrl(c.thumbnailPath)} alt={c.displayName} loading="lazy" />
              ) : (
                <span className="lib-thumb-ph">▨</span>
              )}
            </div>
            {editId === c.id ? (
              <div className="lib-edit">
                <input
                  className="lib-edit-name"
                  value={editName}
                  aria-label="Display name"
                  placeholder="Display name"
                  onChange={(e) => setEditName(e.target.value)}
                />
                <select className="lib-edit-cat" value={editCat} onChange={(e) => setEditCat(e.target.value)} title="Category">
                  {CANON_CATS.map((k) => <option key={k} value={k}>{catLabel(k)}</option>)}
                </select>
                <div className="lib-actions">
                  <button className="lib-btn" onClick={() => void saveEdit(c)}>Save</button>
                  <button className="lib-btn" onClick={() => setEditId(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <>
                <div className="lib-meta">
                  <div className="lib-name">{c.shortName || c.displayName}</div>
                  <div className="lib-sub">{c.partNumber || c.category}{isRetired(c) ? ' · retired' : ''}</div>
                </div>
                <div className="lib-actions">
                  <button className="lib-btn" disabled={!canInsert} onClick={() => insert(c)} title="Insert on active page">Insert</button>
                  <button className="lib-btn" onClick={() => beginEdit(c)} title="Rename / recategorize">✎</button>
                  {isRetired(c) ? (
                    <button className="lib-btn" onClick={() => void restoreItem(c)} title="Restore this retired component">Restore</button>
                  ) : (
                    <button className="lib-btn" onClick={() => void retireItem(c)} title="Retire (hide from search, keep in old projects)">Retire</button>
                  )}
                  <button className="lib-btn danger" onClick={() => void removeItem(c)} title="Delete this library item (with confirmation)">✕</button>
                </div>
              </>
            )}
          </div>
        ))}
        {!visible.length && <div className="lib-empty">No matches.</div>}
      </div>
      {error && <p className="lib-error">{error}</p>}
    </div>
  );
}
