import { useEffect, useMemo, useState } from 'react';
import {
  getLibrary,
  importLibrarySeed,
  libraryAssetUrl,
  deleteLibraryComponent,
  retireLibraryComponent,
  type LibraryComponent,
  type LibraryData,
} from '../api/client';

interface Props {
  onInsert: (name: string, url: string) => void;
  canInsert: boolean;
}

export const COMPONENT_DRAG_TYPE = 'application/x-singh360-component';

export default function ComponentLibrary({ onInsert, canInsert }: Props) {
  const [data, setData] = useState<LibraryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
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

  const components = data?.components ?? [];
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return components.filter((c) => {
      if ((c.status || '').startsWith('retired')) return false;
      if (category !== 'all' && (c.category || 'uncategorized').toLowerCase() !== category) return false;
      if (!q) return true;
      const hay = [c.displayName, c.shortName, c.partNumber, c.category, ...(c.aliases ?? []), ...(c.tags ?? [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }, [components, query, category]);

  const insert = (c: LibraryComponent) => {
    if (!c.assetPath) return;
    onInsert(c.displayName, libraryAssetUrl(c.assetPath));
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
          <option value="all">All categories ({components.length})</option>
          {cats.map((c) => (
            <option key={c.id} value={c.id}>{c.id} ({c.count})</option>
          ))}
        </select>
      </div>

      <div className="lib-grid">
        {visible.map((c) => (
          <div
            key={c.id}
            className="lib-card"
            draggable={canInsert}
            onDragStart={(e) => {
              if (!c.assetPath) return;
              e.dataTransfer.setData(
                COMPONENT_DRAG_TYPE,
                JSON.stringify({ name: c.displayName, url: libraryAssetUrl(c.assetPath) }),
              );
              e.dataTransfer.effectAllowed = 'copy';
            }}
            onDoubleClick={() => canInsert && insert(c)}
            title={`${c.displayName}${c.partNumber ? ` · ${c.partNumber}` : ''}`}
          >
            <div className="lib-thumb">
              {c.thumbnailPath ? (
                <img src={libraryAssetUrl(c.thumbnailPath)} alt={c.displayName} loading="lazy" />
              ) : (
                <span className="lib-thumb-ph">▨</span>
              )}
            </div>
            <div className="lib-meta">
              <div className="lib-name">{c.shortName || c.displayName}</div>
              <div className="lib-sub">{c.partNumber || c.category}</div>
            </div>
            <div className="lib-actions">
              <button className="lib-btn" disabled={!canInsert} onClick={() => insert(c)} title="Insert on active page">Insert</button>
              <button className="lib-btn" onClick={() => void retireItem(c)} title="Retire (hide from search, keep in old projects)">Retire</button>
              <button className="lib-btn danger" onClick={() => void removeItem(c)} title="Delete this library item (with confirmation)">✕</button>
            </div>
          </div>
        ))}
        {!visible.length && <div className="lib-empty">No matches.</div>}
      </div>
      {error && <p className="lib-error">{error}</p>}
    </div>
  );
}
