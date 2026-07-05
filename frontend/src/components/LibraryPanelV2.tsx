import { useEffect, useMemo, useRef, useState } from 'react';
import {
  cleanLibV2PhysicalDuplicates,
  duplicateLibV2Component,
  getLibV2,
  libV2AssetUrl,
  migrateLegacyLibV2,
  rebuildLibV2Thumbnails,
  refreshLibV2,
  replaceLibV2Asset,
  updateLibV2Component,
  type LibV2Component,
  type LibV2Data,
} from '../api/client';
import { COMPONENT_DRAG_TYPE } from './ComponentLibrary';
import '../styles/libraryV2.css';

interface Props {
  onInsert: (name: string, url: string, label: string | null) => void;
  canInsert: boolean;
  activePageType?: string;
}

const NO_LABEL_CATS = new Set(['logos', 'symbols_markers', 'reference_pages']);
type ViewRep = 'source' | 'edge' | 'bw';
type BuilderTab = 'components' | 'advanced';

function labelFor(c: LibV2Component): string | null {
  if (NO_LABEL_CATS.has((c.category || '').toLowerCase())) return null;
  const candidates = [c.defaultLabel, c.partNumber, c.displayName, c.shortName];
  for (const item of candidates) {
    const val = (item || '').trim();
    if (!val) continue;
    if (/[0-9a-f]{10,}/i.test(val) || /^controller_/i.test(val)) continue;
    return val;
  }
  return null;
}

function displayNameFor(c: LibV2Component): string {
  const raw = (c.displayName || '').trim();
  if (!raw) return 'Component';
  return raw.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function sourceUrl(c: LibV2Component): string {
  return c.sourceUrl || (c.sourceFile ? libV2AssetUrl(c.sourceFile) : '');
}

function edgeUrl(c: LibV2Component): string {
  return c.edgeUrl || c.edgeFile ? libV2AssetUrl(c.edgeFile || '') : '';
}

function bwUrl(c: LibV2Component): string {
  return c.bwUrl || c.bwFile ? libV2AssetUrl(c.bwFile || '') : '';
}

function previewUrl(c: LibV2Component, rep: ViewRep): string {
  if (rep === 'edge') return edgeUrl(c);
  if (rep === 'bw') return bwUrl(c);
  return c.thumbnailUrl || sourceUrl(c);
}

function defaultRepForPage(pageType: string | undefined, data: LibV2Data | null): ViewRep {
  const hasAnyEdge = !!data?.components?.some((c) => c.hasEdge);
  const drawingPages = new Set(['canvas', 'hybrid', 'underlay']);
  if (pageType && drawingPages.has(pageType) && hasAnyEdge) return 'edge';
  return 'source';
}

export default function LibraryPanelV2({ onInsert, canInsert, activePageType }: Props) {
  const [data, setData] = useState<LibV2Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [rep, setRep] = useState<ViewRep>('source');
  const [showBuilder, setShowBuilder] = useState(false);
  const [builderTab, setBuilderTab] = useState<BuilderTab>('components');
  const [showLegacyItems, setShowLegacyItems] = useState(false);
  const [builderQuery, setBuilderQuery] = useState('');
  const [builderCategory, setBuilderCategory] = useState('all');
  const [selectedId, setSelectedId] = useState<string>('');
  const [editor, setEditor] = useState<Partial<LibV2Component>>({});
  const replaceSourceRef = useRef<HTMLInputElement>(null);
  const replaceEdgeRef = useRef<HTMLInputElement>(null);
  const replaceBwRef = useRef<HTMLInputElement>(null);

  const load = async (includeLegacy = showLegacyItems) => {
    setLoading(true);
    try {
      const lib = await getLibV2(includeLegacy);
      setData(lib);
      if (!selectedId && lib.components.length) setSelectedId(lib.components[0].id);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { void load(false); /* eslint-disable-next-line */ }, []);
  useEffect(() => { setRep(defaultRepForPage(activePageType, data)); }, [activePageType, data?.counts?.withEdge]);

  const components = data?.components ?? [];
  const selected = useMemo(() => components.find((c) => c.id === selectedId) ?? null, [components, selectedId]);
  useEffect(() => {
    if (!selected) return;
    setEditor({
      displayName: selected.displayName,
      defaultLabel: selected.defaultLabel,
      category: selected.category,
      partNumber: selected.partNumber,
      aliases: [...(selected.aliases || [])],
      preferredEdgeVariant: selected.preferredEdgeVariant || '',
      retired: !!selected.retired,
    });
  }, [selected?.id]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return components.filter((c) => {
      if (category !== 'all' && c.category !== category) return false;
      if (!q) return true;
      const hay = [
        c.displayName, c.defaultLabel, c.partNumber, c.manufacturer,
        (c.aliases || []).join(' '), c.category, (c.searchTerms || []).join(' '),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [components, query, category]);

  const builderFiltered = useMemo(() => {
    const q = builderQuery.trim().toLowerCase();
    return components.filter((c) => {
      if (builderCategory !== 'all' && c.category !== builderCategory) return false;
      if (!q) return true;
      const hay = [c.displayName, c.defaultLabel, c.partNumber, (c.aliases || []).join(' ')].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [components, builderQuery, builderCategory]);

  const canInsertRep = (c: LibV2Component, which: ViewRep): boolean => {
    if (which === 'source') return !!sourceUrl(c);
    if (which === 'edge') return !!edgeUrl(c);
    return !!bwUrl(c);
  };

  const insertAs = (c: LibV2Component, which: ViewRep, withLabel = true) => {
    if (!canInsert) return;
    const url = previewUrl(c, which);
    if (!url) return;
    onInsert(displayNameFor(c), url, withLabel ? labelFor(c) : null);
  };

  const onDragStart = (e: React.DragEvent, c: LibV2Component) => {
    const url = previewUrl(c, rep);
    if (!url) return;
    e.dataTransfer.setData(COMPONENT_DRAG_TYPE, JSON.stringify({
      name: displayNameFor(c), url, label: labelFor(c),
    }));
    e.dataTransfer.effectAllowed = 'copy';
  };

  const doRefresh = async () => {
    setLoading(true);
    try {
      await refreshLibV2();
      await load(showLegacyItems);
    } finally { setLoading(false); }
  };

  const doSaveComponent = async () => {
    if (!selected) return;
    await updateLibV2Component(selected.id, {
      displayName: (editor.displayName || selected.displayName || '').trim(),
      defaultLabel: (editor.defaultLabel || '').trim(),
      category: (editor.category || selected.category || '').trim(),
      partNumber: (editor.partNumber || '').trim(),
      aliases: Array.isArray(editor.aliases)
        ? editor.aliases
        : String(editor.aliases || '').split(',').map((x) => x.trim()).filter(Boolean),
      preferredEdgeVariant: (editor.preferredEdgeVariant || '').trim(),
      retired: !!editor.retired,
    });
    await load(showLegacyItems);
  };

  const doDuplicateComponent = async () => {
    if (!selected) return;
    await duplicateLibV2Component(selected.id);
    await load(showLegacyItems);
  };

  const doReplaceAsset = async (target: 'source' | 'edge' | 'bw', file: File | null) => {
    if (!selected || !file) return;
    await replaceLibV2Asset(selected.id, target, file);
    await load(showLegacyItems);
  };

  const doRebuildThumbnails = async () => {
    setLoading(true);
    try {
      await rebuildLibV2Thumbnails();
      await load(showLegacyItems);
    } finally { setLoading(false); }
  };

  const doCleanDryRun = async () => {
    const preview = await cleanLibV2PhysicalDuplicates(true);
    window.alert(`Duplicate groups: ${preview.duplicateGroups || 0}\nDuplicates: ${preview.duplicates || 0}`);
  };

  const doMigrateLegacy = async () => {
    const preview = await migrateLegacyLibV2(true);
    if (!preview.willCopy) return;
    if (!window.confirm(`Migrate ${preview.willCopy} legacy files into V2 components?`)) return;
    setLoading(true);
    try {
      await migrateLegacyLibV2(false);
      await load(showLegacyItems);
    } finally { setLoading(false); }
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
        </div>
        <div className="libv2-row libv2-modes">
          {(['source', 'edge', 'bw'] as ViewRep[]).map((r) => (
            <button
              key={r}
              className={rep === r ? 'active' : undefined}
              onClick={() => setRep(r)}
            >
              {r === 'source' ? 'Source' : r === 'edge' ? 'Edge' : 'B/W'}
            </button>
          ))}
        </div>
        <div className="libv2-row">
          <button onClick={() => setShowBuilder(true)}>Open Component Builder</button>
          <button onClick={() => void doRefresh()} disabled={loading}>Refresh Library</button>
        </div>
      </div>

      <div className="libv2-grid">
        {filtered.map((c) => {
          const canCurrent = canInsertRep(c, rep);
          return (
            <div key={c.id} className="libv2-card" draggable={canInsert && canCurrent} onDragStart={(e) => onDragStart(e, c)}>
              <CardPreview c={c} rep={rep} />
              <div className="libv2-meta">
                <div className="libv2-name">{displayNameFor(c)}</div>
                <div className="libv2-part">{c.partNumber || c.defaultLabel || ''}</div>
                {!canCurrent && rep === 'edge' ? <div className="libv2-missing">No edge drawing</div> : null}
                {!canCurrent && rep === 'bw' ? <div className="libv2-missing">No B/W representation</div> : null}
                <div className="libv2-actions">
                  <button onClick={() => insertAs(c, rep)} disabled={!canInsert || !canCurrent}>Insert</button>
                  <details className="libv2-insert-menu">
                    <summary>▼</summary>
                    <div>
                      <button onClick={() => insertAs(c, 'source')} disabled={!canInsertRep(c, 'source')}>Insert Source</button>
                      <button onClick={() => insertAs(c, 'edge')} disabled={!canInsertRep(c, 'edge')}>Insert Edge</button>
                      <button onClick={() => insertAs(c, 'bw')} disabled={!canInsertRep(c, 'bw')}>Insert B/W</button>
                      <button onClick={() => insertAs(c, rep, true)} disabled={!canCurrent}>Insert with Label</button>
                    </div>
                  </details>
                </div>
              </div>
            </div>
          );
        })}
        {!filtered.length && <div className="libv2-empty">No matching components.</div>}
      </div>

      {showBuilder && (
        <div className="libv2-modal-backdrop" onClick={() => setShowBuilder(false)}>
          <div className="libv2-modal" onClick={(e) => e.stopPropagation()}>
            <div className="libv2-modal-head">
              <strong>Component Builder</strong>
              <button onClick={() => setShowBuilder(false)}>Close</button>
            </div>

            <div className="libv2-row libv2-modes">
              <button className={builderTab === 'components' ? 'active' : ''} onClick={() => setBuilderTab('components')}>Components</button>
              <button className={builderTab === 'advanced' ? 'active' : ''} onClick={() => setBuilderTab('advanced')}>Advanced</button>
            </div>

            {builderTab === 'components' ? (
              <div className="libv2-builder-grid">
                <div>
                  <input type="search" placeholder="Search" value={builderQuery} onChange={(e) => setBuilderQuery(e.target.value)} />
                  <select title="Builder category" value={builderCategory} onChange={(e) => setBuilderCategory(e.target.value)}>
                    <option value="all">All categories</option>
                    {(data?.categories ?? []).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                  </select>
                  <div className="libv2-builder-list">
                    {builderFiltered.map((c) => (
                      <button key={c.id} className={selectedId === c.id ? 'active' : ''} onClick={() => setSelectedId(c.id)}>
                        {displayNameFor(c)}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  {selected ? (
                    <>
                      <div className="libv2-previews">
                        <CardPreview c={selected} rep="source" />
                        <CardPreview c={selected} rep="edge" />
                        <CardPreview c={selected} rep="bw" />
                      </div>
                      <label>Display Name<input value={String(editor.displayName || '')} onChange={(e) => setEditor((p) => ({ ...p, displayName: e.target.value }))} /></label>
                      <label>Default Label<input value={String(editor.defaultLabel || '')} onChange={(e) => setEditor((p) => ({ ...p, defaultLabel: e.target.value }))} /></label>
                      <label>Category
                        <select value={String(editor.category || selected.category)} onChange={(e) => setEditor((p) => ({ ...p, category: e.target.value }))}>
                          {(data?.categories ?? []).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                        </select>
                      </label>
                      <label>Part Number<input value={String(editor.partNumber || '')} onChange={(e) => setEditor((p) => ({ ...p, partNumber: e.target.value }))} /></label>
                      <label>Aliases (comma)
                        <input value={Array.isArray(editor.aliases) ? editor.aliases.join(', ') : String(editor.aliases || '')} onChange={(e) => setEditor((p) => ({ ...p, aliases: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) }))} />
                      </label>
                      <label>Preferred Edge Variant
                        <select value={String(editor.preferredEdgeVariant || '')} onChange={(e) => setEditor((p) => ({ ...p, preferredEdgeVariant: e.target.value }))}>
                          <option value="">(Auto)</option>
                          {(selected.edgeVariantOptions || []).map((v) => <option key={v} value={v}>{v}</option>)}
                          <option value="custom">custom</option>
                        </select>
                      </label>

                      <div className="libv2-row wrap">
                        <button onClick={() => void doSaveComponent()}>Save</button>
                        <button onClick={() => void doDuplicateComponent()}>Duplicate</button>
                        <button onClick={() => setEditor((p) => ({ ...p, retired: !p.retired }))}>{editor.retired ? 'Unretire' : 'Retire'}</button>
                        <button onClick={() => replaceSourceRef.current?.click()}>Replace Source</button>
                        <button onClick={() => replaceEdgeRef.current?.click()}>Replace Edge</button>
                        <button onClick={() => replaceBwRef.current?.click()}>Replace B/W</button>
                      </div>

                      <input ref={replaceSourceRef} hidden type="file" accept="image/*,.svg,.pdf" onChange={(e) => void doReplaceAsset('source', e.target.files?.[0] || null)} />
                      <input ref={replaceEdgeRef} hidden type="file" accept="image/*,.svg,.pdf" onChange={(e) => void doReplaceAsset('edge', e.target.files?.[0] || null)} />
                      <input ref={replaceBwRef} hidden type="file" accept="image/*,.svg,.pdf" onChange={(e) => void doReplaceAsset('bw', e.target.files?.[0] || null)} />
                    </>
                  ) : (
                    <div className="libv2-empty">Select a component.</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="libv2-advanced">
                <button onClick={() => void doRefresh()} disabled={loading}>Refresh Library</button>
                <button onClick={() => void doRebuildThumbnails()} disabled={loading}>Rebuild Thumbnails</button>
                <button onClick={() => void doCleanDryRun()} disabled={loading}>Clean Duplicates (dry run)</button>
                <label><input type="checkbox" checked={showLegacyItems} onChange={async (e) => { setShowLegacyItems(e.target.checked); await load(e.target.checked); }} /> Show Legacy Items</label>
                {data?.hasLegacy ? <button onClick={() => void doMigrateLegacy()} disabled={loading}>Migrate Legacy Components</button> : null}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SafeImg({ url, alt, title }: { url: string; alt: string; title?: string }) {
  const [ok, setOk] = useState(true);
  if (!ok || !url) return <div className="libv2-fallback" title={title || alt}>{alt}</div>;
  return <img className="libv2-thumb" src={url} alt={alt} title={title} onError={() => setOk(false)} />;
}

function CardPreview({ c, rep }: { c: LibV2Component; rep: ViewRep }) {
  const src = c.thumbnailUrl || c.sourceUrl || (c.sourceFile ? libV2AssetUrl(c.sourceFile) : '');
  const edge = c.edgeUrl || (c.edgeFile ? libV2AssetUrl(c.edgeFile) : '');
  const bw = c.bwUrl || (c.bwFile ? libV2AssetUrl(c.bwFile) : '');
  const url = rep === 'edge' ? edge : rep === 'bw' ? bw : src;
  const title = rep === 'edge' ? 'Edge' : rep === 'bw' ? 'B/W' : 'Source';
  return <SafeImg url={url} alt={c.displayName} title={title} />;
}
