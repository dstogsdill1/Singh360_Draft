import { useEffect, useMemo, useRef, useState } from 'react';
import {
  addLibV2File,
  cleanLibV2PhysicalDuplicates,
  getLibV2,
  libV2AssetUrl,
  migrateLegacyLibV2,
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
// Categories that keep their SOURCE image even in Symbol view (real logos).
const SOURCE_ONLY_CATS = new Set(['logos', 'reference_pages']);

type FilterMode = 'all' | 'favorites';
type ViewRep = 'source' | 'symbol' | 'both';

function labelFor(c: LibV2Component): string | null {
  if (NO_LABEL_CATS.has((c.category || '').toLowerCase())) return null;
  return c.defaultLabel || c.partNumber || c.displayName || null;
}

function humanizeStem(s: string): string {
  return s
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function fileStem(path?: string): string {
  if (!path) return '';
  const base = path.split('/').pop() || path;
  return base.replace(/\.[^.]+$/, '');
}

function displayNameFor(c: LibV2Component): string {
  const raw = (c.displayName || '').trim();
  if (!raw) return humanizeStem(fileStem(c.sourceFile)) || 'Component';
  if (!raw.includes(' ') && (raw.includes('_') || raw.includes('-'))) {
    return humanizeStem(raw);
  }
  return raw;
}

// URL of the source preview (thumbnail if present, else raw source).
function sourceThumbUrl(c: LibV2Component): string {
  return libV2AssetUrl(c.thumbnailFile || c.sourceFile);
}
function symbolUrl(c: LibV2Component): string | null {
  return c.symbolFile ? libV2AssetUrl(c.symbolFile) : null;
}
// Which URL to insert given the current representation preference.
function insertUrlFor(c: LibV2Component, rep: ViewRep): string {
  const cat = (c.category || '').toLowerCase();
  if (rep === 'source' || SOURCE_ONLY_CATS.has(cat)) return libV2AssetUrl(c.sourceFile);
  return libV2AssetUrl(c.symbolFile || c.sourceFile);
}

export default function LibraryPanelV2({ onInsert, canInsert }: Props) {
  const [data, setData] = useState<LibV2Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [mode, setMode] = useState<FilterMode>('all');
  const [rep, setRep] = useState<ViewRep>('both');
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState('');
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

  useEffect(() => {
    setDraftName(selected?.displayName ?? '');
  }, [selected?.id, selected?.displayName]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return components.filter((c) => {
      if (category !== 'all' && c.category !== category) return false;
      if (mode === 'favorites' && !c.favorite) return false;
      if (!q) return true;
      const hay = [
        c.displayName, displayNameFor(c), c.defaultLabel, c.partNumber, c.manufacturer,
        (c.aliases || []).join(' '), c.category, fileStem(c.sourceFile),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [components, query, category, mode]);

  const doInsert = (c: LibV2Component) => {
    if (!canInsert) return;
    onInsert(displayNameFor(c), insertUrlFor(c, rep === 'both' ? 'symbol' : rep), labelFor(c));
  };

  const doInsertBw = async (c: LibV2Component) => {
    if (!canInsert) return;
    if (c.symbolFile) {
      onInsert(displayNameFor(c), insertUrlFor(c, 'symbol'), labelFor(c));
      return;
    }
    // Symbol Builder endpoint is not fully enabled in this repo yet for all
    // assets. Fall back to source insertion with a B/W rendering hint so the
    // user always gets an immediate black/white result instead of a no-op.
    const src = insertUrlFor(c, 'source');
    const bwSrc = `${src}${src.includes('?') ? '&' : '?'}bw=1`;
    onInsert(displayNameFor(c), bwSrc, labelFor(c));
  };

  const onDragStart = (e: React.DragEvent, c: LibV2Component) => {
    e.dataTransfer.setData(COMPONENT_DRAG_TYPE, JSON.stringify({
      name: displayNameFor(c), url: insertUrlFor(c, rep === 'both' ? 'symbol' : rep), label: labelFor(c),
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
    const preview = await cleanLibV2PhysicalDuplicates(true);
    if (!(preview.duplicates && preview.duplicates > 0)) {
      window.alert('Clean Duplicates: no physical duplicates found.');
      return;
    }
    if (!window.confirm(`Move ${preview.duplicates} duplicate file(s) to .docs/archive? (originals are kept)`)) return;
    setLoading(true);
    try {
      const r = await cleanLibV2PhysicalDuplicates(false);
      await load();
      window.alert(`Clean Duplicates\nArchived: ${r.archived}`);
    } finally { setLoading(false); }
  };
  const doMigrate = async () => {
    const preview = await migrateLegacyLibV2(true);
    if (!preview.willCopy) {
      window.alert(`Migrate Legacy Components\nLegacy files found: ${preview.legacyFound ?? 0}\nNothing new to copy (all already present).`);
      return;
    }
    const cats = Object.entries(preview.targetCategories ?? {}).map(([k, v]) => `  ${k}: ${v}`).join('\n');
    if (!window.confirm(`Migrate Legacy Components\nWill copy: ${preview.willCopy}\nSkip duplicates: ${preview.willSkipDuplicates}\nInto categories:\n${cats}\n\nProceed?`)) return;
    setLoading(true);
    try {
      const r = await migrateLegacyLibV2(false);
      await load();
      window.alert(`Migrate complete.\nCopied: ${r.copied}`);
    } finally { setLoading(false); }
  };
  const openComponentBuilder = () => {
    window.alert('Coming later — opens Component Builder workflow.');
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

  const commitDraftName = async () => {
    if (!selected) return;
    const next = draftName.trim();
    if (!next || next === selected.displayName) return;
    await patchSelected({ displayName: next });
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
          {(['all', 'favorites'] as FilterMode[]).map((m) => (
            <button key={m} className={mode === m ? 'active' : undefined} onClick={() => setMode(m)}>
              {m === 'all' ? 'All' : 'Favorites'}
            </button>
          ))}
        </div>
        <div className="libv2-row libv2-modes">
          <span className="libv2-rep-label">Show:</span>
          {(['source', 'symbol', 'both'] as ViewRep[]).map((r) => (
            <button key={r} className={rep === r ? 'active' : undefined} onClick={() => setRep(r)}
              title={r === 'source' ? 'Source image' : r === 'symbol' ? 'Black/white symbol' : 'Both'}>
              {r === 'source' ? 'Source' : r === 'symbol' ? 'B/W Symbol' : 'Both'}
            </button>
          ))}
        </div>
        <div className="libv2-row wrap">
          <button onClick={() => fileInput.current?.click()}>Add Files</button>
          <button onClick={() => void doRefresh()} disabled={loading}>Refresh Library</button>
          {data?.hasLegacy && (
            <button onClick={() => void doMigrate()} disabled={loading} title="Copy legacy .docs/library/assets/components into V2">Migrate Legacy Components</button>
          )}
          <button onClick={() => void doRebuild()} disabled={loading}>Rebuild Thumbnails</button>
          <button onClick={() => void doClean()} disabled={loading}>Clean Duplicates</button>
          <button onClick={openComponentBuilder} title="Coming later — opens Component Builder">Open Component Builder</button>
          <input ref={fileInput} type="file" multiple accept="image/*,.pdf,.svg" hidden
            onChange={(e) => void onPickFiles(e.target.files)} />
        </div>
      </div>

      <div className={view === 'grid' ? 'libv2-grid' : 'libv2-grid list'}>
        {filtered.map((c) => (
          <div key={c.id} className={selectedId === c.id ? 'libv2-card selected' : 'libv2-card'}
            draggable={canInsert} onDragStart={(e) => onDragStart(e, c)}
            onClick={() => setSelectedId((prev) => (prev === c.id ? null : c.id))}>
            <CardPreview c={c} rep={rep} />
            <div className="libv2-meta">
              <div className="libv2-name">{displayNameFor(c)}</div>
              {c.partNumber ? <div className="libv2-part">{c.partNumber}</div> : null}
              <div className="libv2-cat">
                {c.category}
                {c.symbolFile ? <span className="libv2-badge" title="Black/white symbol available">B/W</span> : null}
              </div>
              <div className="libv2-actions">
                <button onClick={(e) => { e.stopPropagation(); doInsert(c); }} disabled={!canInsert} title="Insert onto active page (with label)">Insert</button>
                <button onClick={(e) => { e.stopPropagation(); if (canInsert) onInsert(displayNameFor(c), insertUrlFor(c, 'source'), labelFor(c)); }} disabled={!canInsert} title="Insert source image">Src</button>
                <button
                  onClick={(e) => { e.stopPropagation(); void doInsertBw(c); }}
                  disabled={!canInsert || loading}
                  title={c.symbolFile ? 'Insert black/white symbol' : 'Insert source image in black/white'}
                >
                  B/W
                </button>
                <button onClick={(e) => { e.stopPropagation(); setSelectedId(c.id); }} title="Edit">Edit</button>
                <button onClick={(e) => { e.stopPropagation(); void toggleFavorite(c); }}
                  className={c.favorite ? 'active' : undefined} title={c.favorite ? 'Unfavorite' : 'Favorite'}>{c.favorite ? '★' : '☆'}</button>
              </div>
            </div>
          </div>
        ))}
        {!filtered.length && <div className="libv2-empty">No components. {data?.hasLegacy ? 'Click Migrate Legacy Components,' : 'Add files or'} Refresh Library.</div>}
      </div>

      {selected && (
        <div className="libv2-editor">
          <div className="libv2-editor-title-row">
            <div className="libv2-editor-title">Edit: {displayNameFor(selected)}</div>
            <button className="libv2-done" onClick={() => setSelectedId(null)} title="Close editor">Done</button>
          </div>
          <EditorRow label="Display name">
            <input
              title="Display name"
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              onBlur={() => void commitDraftName()}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void commitDraftName();
                  (e.currentTarget as HTMLInputElement).blur();
                }
                if (e.key === 'Escape') {
                  e.preventDefault();
                  setDraftName(selected.displayName);
                  setSelectedId(null);
                }
              }}
            />
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
            <button onClick={openComponentBuilder}>Generate Symbol (Component Builder)</button>
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

// A thumbnail that never shows a broken-image icon: on error it swaps to a
// clean fallback tile with the filename.
function SafeImg({ url, alt, title }: { url: string; alt: string; title?: string }) {
  const [ok, setOk] = useState(true);
  if (!ok || !url) {
    return <div className="libv2-fallback" title={title || alt}>{alt}</div>;
  }
  return <img className="libv2-thumb" src={url} alt={alt} title={title} onError={() => setOk(false)} />;
}

// Card preview honouring the Source / B/W Symbol / Both representation choice.
function CardPreview({ c, rep }: { c: LibV2Component; rep: ViewRep }) {
  const cat = (c.category || '').toLowerCase();
  const sym = symbolUrl(c);
  const src = sourceThumbUrl(c);
  const forceSource = SOURCE_ONLY_CATS.has(cat);
  if (rep === 'symbol' && sym && !forceSource) {
    return <SafeImg url={sym} alt={c.displayName} title="Black/white symbol" />;
  }
  if (rep === 'both' && sym && !forceSource) {
    return (
      <div className="libv2-both">
        <SafeImg url={src} alt={c.displayName} title="Source" />
        <SafeImg url={sym} alt={c.displayName} title="B/W symbol" />
      </div>
    );
  }
  return <SafeImg url={src} alt={c.displayName} title="Source" />;
}
