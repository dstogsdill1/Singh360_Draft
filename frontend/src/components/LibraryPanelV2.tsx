import { useEffect, useMemo, useRef, useState } from 'react';
import {
  addLibV2File,
  cleanLibV2Duplicates,
  generateLibV2Symbol,
  getLibV2,
  libV2AssetUrl,
  rebuildLibV2Thumbnails,
  refreshLibV2,
  renameLibV2File,
  updateLibV2Component,
  type LibV2Component,
  type LibV2Data,
} from '../api/client';
import { COMPONENT_DRAG_TYPE } from './ComponentLibrary';
import '../styles/libraryV2.css';

interface Props {
  onInsert: (name: string, url: string, label: string | null) => void;
  canInsert: boolean;
}

// Categories that never get an auto label (logos / markers / reference pages).
const NO_LABEL_CATS = new Set(['logos', 'symbols_markers', 'reference_pages']);

type FilterMode = 'all' | 'favorites' | 'needsReview';

function labelFor(c: LibV2Component): string | null {
  if (NO_LABEL_CATS.has((c.category || '').toLowerCase())) return null;
  return c.defaultLabel || c.partNumber || c.displayName || null;
}

// Prefer the black-and-white drawing symbol for insertion; fall back to source.
function insertUrl(c: LibV2Component): string {
  return libV2AssetUrl(c.symbolFile || c.sourceFile);
}
function thumbUrl(c: LibV2Component): string {
  return libV2AssetUrl(c.thumbnailFile || c.sourceFile);
}

export default function LibraryPanelV2({ onInsert, canInsert }: Props) {
  const [data, setData] = useState<LibV2Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [mode, setMode] = useState<FilterMode>('all');
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    try {
      setData(await getLibV2());
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(); }, []);

  const components = data?.components ?? [];
  const selected = useMemo(
    () => components.find((c) => c.id === selectedId) ?? null,
    [components, selectedId],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return components.filter((c) => {
      if (category !== 'all' && c.category !== category) return false;
      if (mode === 'favorites' && !c.favorite) return false;
      if (mode === 'needsReview' && !c.needsReview) return false;
      if (!q) return true;
      const hay = [c.displayName, c.partNumber, c.manufacturer, (c.aliases || []).join(' ')]
        .join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [components, query, category, mode]);

  const doInsert = (c: LibV2Component) => {
    if (!canInsert) return;
    onInsert(c.displayName, insertUrl(c), labelFor(c));
  };

  const onDragStart = (e: React.DragEvent, c: LibV2Component) => {
    e.dataTransfer.setData(COMPONENT_DRAG_TYPE, JSON.stringify({
      name: c.displayName, url: insertUrl(c), label: labelFor(c),
    }));
    e.dataTransfer.effectAllowed = 'copy';
  };

  const doRefresh = async () => {
    setLoading(true);
    try {
      const r = await refreshLibV2();
      await load();
      window.alert(`Refresh Library\nScanned: ${r.scanned}\nAdded: ${r.added}\nSkipped: ${r.skipped}\nExact duplicates blocked: ${r.duplicates}`);
    } finally { setLoading(false); }
  };
  const doRebuild = async () => {
    setLoading(true);
    try {
      const r = await rebuildLibV2Thumbnails();
      await load();
      window.alert(`Rebuild Thumbnails\nRebuilt: ${r.rebuilt}\nMissing source: ${r.missingSource}`);
    } finally { setLoading(false); }
  };
  const doClean = async () => {
    const preview = await cleanLibV2Duplicates(true);
    if (!(preview.duplicates && preview.duplicates > 0)) {
      window.alert('Clean Duplicates: no duplicates found.');
      return;
    }
    if (!window.confirm(`Move ${preview.duplicates} duplicate(s) to .docs/archive?`)) return;
    const r = await cleanLibV2Duplicates(false);
    await load();
    window.alert(`Clean Duplicates\nArchived: ${r.archived}`);
  };
  const onPickFiles = async (files: FileList | null) => {
    if (!files || !files.length) return;
    const cat = category === 'all' ? 'custom' : category;
    setLoading(true);
    try {
      for (const f of Array.from(files)) await addLibV2File(cat, f);
      await load();
    } finally { setLoading(false); }
    if (fileInput.current) fileInput.current.value = '';
  };

  const patchSelected = async (patch: Partial<LibV2Component>) => {
    if (!selected) return;
    await updateLibV2Component(selected.id, patch);
    await load();
  };
  const toggleFavorite = async (c: LibV2Component) => {
    await updateLibV2Component(c.id, { favorite: !c.favorite });
    await load();
  };

  return (
    <div className="libv2">
      <div className="libv2-controls">
        <input
          className="libv2-search"
          type="search"
          placeholder="Search components…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="libv2-row">
          <select className="libv2-grow" title="Filter by category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">All categories</option>
            {(data?.categories ?? []).map((c) => (
              <option key={c.id} value={c.id}>{c.label} ({c.count})</option>
            ))}
          </select>
          <button onClick={() => setView(view === 'grid' ? 'list' : 'grid')} title="Toggle grid/list">
            {view === 'grid' ? '☰ List' : '▦ Grid'}
          </button>
        </div>
        <div className="libv2-row libv2-modes">
          {(['all', 'favorites', 'needsReview'] as FilterMode[]).map((m) => (
            <button key={m} className={mode === m ? 'active' : undefined} onClick={() => setMode(m)}>
              {m === 'all' ? 'All' : m === 'favorites' ? 'Favorites' : 'Needs Review'}
            </button>
          ))}
        </div>
        <div className="libv2-row wrap">
          <button onClick={() => fileInput.current?.click()}>Add Files</button>
          <button onClick={() => void doRefresh()} disabled={loading}>Refresh Library</button>
          <button onClick={() => void doRebuild()} disabled={loading}>Rebuild Thumbnails</button>
          <button onClick={() => void doClean()} disabled={loading}>Clean Duplicates</button>
          <input ref={fileInput} type="file" multiple accept="image/*,.pdf,.svg" hidden
            onChange={(e) => void onPickFiles(e.target.files)} />
        </div>
      </div>

      <div className={view === 'grid' ? 'libv2-grid' : 'libv2-grid list'}>
        {filtered.map((c) => (
          <div key={c.id} className={selectedId === c.id ? 'libv2-card selected' : 'libv2-card'}
            draggable={canInsert} onDragStart={(e) => onDragStart(e, c)}
            onClick={() => setSelectedId(c.id)}>
            <img className="libv2-thumb" src={thumbUrl(c)} alt={c.displayName}
              onError={(e) => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }} />
            <div className="libv2-meta">
              <div className="libv2-name">{c.displayName}</div>
              {c.partNumber ? <div className="libv2-part">{c.partNumber}</div> : null}
              <div className="libv2-cat">{c.category}</div>
              <div className="libv2-actions">
                <button onClick={(e) => { e.stopPropagation(); doInsert(c); }} disabled={!canInsert} title="Insert with label onto active page">Insert</button>
                <button onClick={(e) => { e.stopPropagation(); setSelectedId(c.id); }} title="Edit">Edit</button>
                <button onClick={(e) => { e.stopPropagation(); void toggleFavorite(c); }}
                  className={c.favorite ? 'active' : undefined} title={c.favorite ? 'Unfavorite' : 'Favorite'}>{c.favorite ? '★' : '☆'}</button>
              </div>
            </div>
          </div>
        ))}
        {!filtered.length && <div className="libv2-empty">No components. Add files or Refresh Library.</div>}
      </div>

      {selected && (
        <div className="libv2-editor">
          <div className="libv2-editor-title">Edit: {selected.displayName}</div>
          <EditorRow label="Display name">
            <input title="Display name" value={selected.displayName} onChange={(e) => void patchSelected({ displayName: e.target.value })} />
          </EditorRow>
          <EditorRow label="Category">
            <select title="Category" value={selected.category} onChange={(e) => void patchSelected({ category: e.target.value })}>
              {(data?.categories ?? []).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </EditorRow>
          <EditorRow label="Subcategory">
            <input title="Subcategory" value={selected.subcategory ?? ''} onChange={(e) => void patchSelected({ subcategory: e.target.value })} />
          </EditorRow>
          <EditorRow label="Manufacturer">
            <input title="Manufacturer" value={selected.manufacturer ?? ''} onChange={(e) => void patchSelected({ manufacturer: e.target.value })} />
          </EditorRow>
          <EditorRow label="Part number">
            <input title="Part number" value={selected.partNumber ?? ''} onChange={(e) => void patchSelected({ partNumber: e.target.value })} />
          </EditorRow>
          <EditorRow label="Aliases (comma)">
            <input title="Aliases" value={(selected.aliases ?? []).join(', ')}
              onChange={(e) => void patchSelected({ aliases: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
          </EditorRow>
          <EditorRow label="Default label">
            <input title="Default label" value={selected.defaultLabel ?? ''} onChange={(e) => void patchSelected({ defaultLabel: e.target.value })} />
          </EditorRow>
          <EditorRow label="Size (w×h)">
            <span className="libv2-size">
              <input type="number" title="Default width" value={selected.defaultWidth ?? 120}
                onChange={(e) => void patchSelected({ defaultWidth: Number(e.target.value) })} />
              <input type="number" title="Default height" value={selected.defaultHeight ?? 42}
                onChange={(e) => void patchSelected({ defaultHeight: Number(e.target.value) })} />
            </span>
          </EditorRow>
          <EditorRow label="Notes">
            <input title="Notes" value={selected.notes ?? ''} onChange={(e) => void patchSelected({ notes: e.target.value })} />
          </EditorRow>
          <div className="libv2-checks">
            <label><input type="checkbox" checked={!!selected.approved} onChange={(e) => void patchSelected({ approved: e.target.checked })} /> Approved</label>
            <label><input type="checkbox" checked={!!selected.needsReview} onChange={(e) => void patchSelected({ needsReview: e.target.checked })} /> Needs review</label>
          </div>
          <div className="libv2-editor-actions">
            <button onClick={async () => { await generateLibV2Symbol(selected.id); await load(); }}>Generate Symbol</button>
            <button onClick={async () => {
              const r = await renameLibV2File(selected.id);
              if (!r.ok) window.alert(r.error || 'Rename failed'); else await load();
            }}>Rename File to Match Display Name</button>
          </div>
        </div>
      )}
    </div>
  );
}

function EditorRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="libv2-erow">
      <span>{label}</span>
      <span>{children}</span>
    </label>
  );
}
