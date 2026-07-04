import { useEffect, useMemo, useState } from 'react';
import {
  addLibraryComponentFile,
  archiveDirtyExtractedAssets,
  bulkUpdateLibraryComponents,
  getLibrary,
  importLocalLibraryFolder,
  importLibrarySeed,
  autoCategorizeLibrary,
  importRdmLibraryFolder,
  rebuildLibraryThumbnails,
  rescanLibraryAssets,
  rescanLibraryInbox,
  syncLibraryNamesFromFiles,
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
  if (c.insertWithLabel === false) return null;
  const cat = (c.category || '').toLowerCase();
  if (NO_LABEL_CATS.has(cat)) return null;
  return c.defaultLabel || c.partNumber || c.shortName || c.displayName || null;
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
  const [sourceFilter, setSourceFilter] = useState<'all' | 'rdm' | 'custom' | 'extracted' | 'workbook' | 'reference'>('all');
  const [showRetired, setShowRetired] = useState(false);
  const [showCandidates, setShowCandidates] = useState(false);
  const [showNeedsReview, setShowNeedsReview] = useState(false);
  const [showReferencePages, setShowReferencePages] = useState(false);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [insertWithLabel, setInsertWithLabel] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editCat, setEditCat] = useState('');
  const [editShort, setEditShort] = useState('');
  const [editPart, setEditPart] = useState('');
  const [editAliases, setEditAliases] = useState('');
  const [editTags, setEditTags] = useState('');
  const [editDefaultLabel, setEditDefaultLabel] = useState('');
  const [editStatus, setEditStatus] = useState('needs_review');
  const [editInsertWithLabel, setEditInsertWithLabel] = useState(true);
  const [editRenameAssetFile, setEditRenameAssetFile] = useState(false);
  const [editNotes, setEditNotes] = useState('');
  const [error, setError] = useState('');
  const [savedMsg, setSavedMsg] = useState('');

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
      window.alert(`Auto-categorize complete. Metadata updated; no files were deleted. (changed=${res.changed}, total=${res.total})`);
    } catch (e) {
      setError(String(e));
    }
  };

  const doRescanInbox = async () => {
    try {
      const res = await rescanLibraryInbox();
      await refresh();
      window.alert(`Inbox scan complete. Added ${res.added}, duplicates ${res.duplicates}.`);
    } catch (e) {
      setError(String(e));
    }
  };

  const doRescanLibrary = async () => {
    try {
      const res = await rescanLibraryAssets();
      await refresh();
      window.alert(`Library rescan complete. Added ${res.added}, updated ${res.updated ?? 0}, missing ${res.missing ?? 0}.`);
    } catch (e) {
      setError(String(e));
    }
  };

  const doImportLocalFolder = async () => {
    const p = window.prompt(
      'Local library folder path:',
      'C:\\Users\\DarrinStogsdill\\OneDrive - Homeland Development Services LLC\\Desktop\\Singh360_SmartDraw\\Singh360_Component_Library_Seed\\library\\assets',
    );
    if (!p || !p.trim()) return;
    try {
      const dry = window.confirm('Run DRY RUN first?\n\nOK = dry-run preview\nCancel = import now');
      const reset = window.confirm('Reset/clean existing library entries before import?\n\nOK = archive old non-curated entries\nCancel = merge only');
      const res = await importLocalLibraryFolder({ path: p.trim(), dryRun: dry, resetClean: reset, sourceName: 'Local Library Folder' });
      if (!dry) await refresh();
      window.alert(
        `Local import ${dry ? 'dry-run ' : ''}complete.\nscanned=${res.scanned} added=${res.added} updated=${res.updated} dup=${res.skippedDuplicates} pdf=${res.pdfConverted} review=${res.needsReview} archived=${res.archivedOldEntries}`,
      );
    } catch (e) {
      setError(String(e));
    }
  };

  const doSyncNames = async () => {
    try {
      const res = await syncLibraryNamesFromFiles();
      await refresh();
      window.alert(`Synced names from file names. changed=${res.changed}`);
    } catch (e) {
      setError(String(e));
    }
  };

  const doRebuildThumbs = async () => {
    try {
      const res = await rebuildLibraryThumbnails();
      await refresh();
      window.alert(`Thumbnails rebuilt. rebuilt=${res.rebuilt}, missingBefore=${res.missingBefore}`);
    } catch (e) {
      setError(String(e));
    }
  };

  const doArchiveDirty = async () => {
    const ok = window.confirm('Archive dirty extracted candidates?\n\nThis marks non-curated needs-review/duplicate/candidate entries as retired (no file deletion).');
    if (!ok) return;
    try {
      const res = await archiveDirtyExtractedAssets();
      await refresh();
      window.alert(`Archived dirty extracted assets: ${res.archived}`);
    } catch (e) {
      setError(String(e));
    }
  };

  const doImportRdmFolder = async () => {
    const p = window.prompt(
      'RDM library folder path:',
      'C:\\Program Files (x86)\\RDM Layout Editor 3\\Images',
    );
    if (!p || !p.trim()) return;
    try {
      const dry = window.confirm('Run DRY RUN first?\n\nOK = dry-run preview\nCancel = import now');
      const res = await importRdmLibraryFolder({ path: p.trim(), dryRun: dry });
      if (dry) {
        const rows = (res.preview || []).slice(0, 25).map((x) => `- ${x.action}: ${x.displayName} [${x.category}] (${x.file})`);
        window.alert(
          `RDM dry-run complete.\n\nscanned=${res.scanned} added=${res.added} dup=${res.skippedDuplicates} updated=${res.updated} review=${res.needsReview}`
          + (rows.length ? `\n\nSample:\n${rows.join('\n')}` : ''),
        );
      } else {
        await refresh();
        window.alert(`RDM import complete. scanned=${res.scanned}, added=${res.added}, duplicates=${res.skippedDuplicates}, updated=${res.updated}, needsReview=${res.needsReview}`);
      }
    } catch (e) {
      setError(String(e));
    }
  };

  const doAddFiles = async (file: File) => {
    try {
      await addLibraryComponentFile(file, {
        displayName: file.name.replace(/\.[^.]+$/, ''),
        category: 'review',
        approve: false,
      });
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const components = data?.components ?? [];
  const isRetired = (c: LibraryComponent) => (c.status || '').startsWith('retired');
  const isReference = (c: LibraryComponent) => (c.category || '').toLowerCase() === 'reference-page';

  const statusVisible = (c: LibraryComponent): boolean => {
    const st = String(c.status || 'needs_review').toLowerCase();
    if (st === 'approved') return true;
    if (st === 'candidate') return showCandidates;
    if (st === 'needs_review') return showNeedsReview;
    if (st === 'reference_page') return showReferencePages;
    if (st === 'duplicate') return showDuplicates;
    if (st === 'retired') return showRetired;
    return showNeedsReview;
  };

  const sourceVisible = (c: LibraryComponent): boolean => {
    if (sourceFilter === 'all') return true;
    const st = String(c.source?.sourceType || '').toLowerCase();
    const ap = String(c.assetPath || '').toLowerCase();
    if (sourceFilter === 'rdm') return st === 'rdm-layout-editor' || ap.includes('/rdm_layout_editor/');
    if (sourceFilter === 'custom') return ap.includes('/components/custom/') || st === 'inbox';
    if (sourceFilter === 'workbook') return ap.includes('/workbook_images/') || st === 'workbook';
    if (sourceFilter === 'reference') return ap.includes('/reference_pages/') || (c.category || '').toLowerCase() === 'reference-page';
    if (sourceFilter === 'extracted') return !(st === 'rdm-layout-editor' || ap.includes('/components/custom/') || ap.includes('/workbook_images/') || ap.includes('/reference_pages/'));
    return true;
  };

  const priority = (c: LibraryComponent): number => {
    const st = String(c.status || '').toLowerCase();
    const src = String(c.source?.sourceType || '').toLowerCase();
    const ap = String(c.assetPath || '').toLowerCase();
    const isRdm = src === 'rdm-layout-editor' || ap.includes('/rdm_layout_editor/');
    const isCustom = ap.includes('/components/custom/');
    if (st === 'approved' && isCustom) return 0;
    if (st === 'approved' && isRdm) return 1;
    if (st === 'approved') return 2;
    if (st === 'candidate') return 3;
    if (st === 'needs_review') return 4;
    if (st === 'duplicate') return 5;
    if (st === 'reference_page') return 6;
    if (st === 'retired') return 7;
    return 99;
  };

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return components.filter((c) => {
      if (!statusVisible(c)) return false;
      if (!sourceVisible(c)) return false;
      const cat = (c.category || 'uncategorized').toLowerCase();
      if (category !== 'all' && cat !== category) return false;
      if (!q) return true;
      const hay = [c.displayName, c.shortName, c.partNumber, c.category, ...(c.aliases ?? []), ...(c.tags ?? [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    }).sort((a, b) => {
      const pa = priority(a);
      const pb = priority(b);
      if (pa !== pb) return pa - pb;
      return String(a.displayName || '').localeCompare(String(b.displayName || ''));
    });
  }, [components, query, category, sourceFilter, showRetired, showCandidates, showNeedsReview, showReferencePages, showDuplicates]);

  const insert = (c: LibraryComponent) => {
    if (!c.assetPath) return;
    onInsert(c.displayName, libraryAssetUrl(c.assetPath), insertWithLabel ? labelFor(c) : null);
  };

  const beginEdit = (c: LibraryComponent) => {
    setEditId(c.id);
    setEditName(c.displayName);
    setEditCat((c.category || 'uncategorized').toLowerCase());
    setEditShort(c.shortName || '');
    setEditPart(c.partNumber || '');
    setEditAliases((c.aliases || []).join(', '));
    setEditTags((c.tags || []).join(', '));
    setEditDefaultLabel(c.defaultLabel || '');
    setEditStatus((c.status || 'needs_review').toLowerCase());
    setEditInsertWithLabel(c.insertWithLabel !== false);
    setEditRenameAssetFile(false);
    setEditNotes(c.notes || '');
  };
  const saveEdit = async (c: LibraryComponent) => {
    try {
      const newCat = editCat.toLowerCase();
      const newStatus = editStatus.toLowerCase();
      await updateLibraryComponent(c.id, {
        displayName: editName.trim() || c.displayName,
        shortName: editShort.trim() || undefined,
        category: newCat,
        partNumber: editPart.trim() || undefined,
        aliases: editAliases.split(',').map((x) => x.trim()).filter(Boolean),
        tags: editTags.split(',').map((x) => x.trim()).filter(Boolean),
        defaultLabel: editDefaultLabel.trim() || undefined,
        status: newStatus,
        insertWithLabel: editInsertWithLabel,
        renameAssetFile: editRenameAssetFile,
        notes: editNotes.trim() || undefined,
      });
      setEditId(null);
      // Keep the just-saved item visible: match the filter to its new category
      // and make sure the status toggle for its new status is enabled.
      if (category !== 'all' && category !== newCat) setCategory(newCat);
      if (newStatus === 'candidate') setShowCandidates(true);
      else if (newStatus === 'needs_review') setShowNeedsReview(true);
      else if (newStatus === 'reference_page') setShowReferencePages(true);
      else if (newStatus === 'duplicate') setShowDuplicates(true);
      else if (newStatus === 'retired') setShowRetired(true);
      await refresh();
      setSavedMsg(`Saved “${editName.trim() || c.displayName}” → ${catLabel(newCat)}`);
      window.setTimeout(() => setSavedMsg(''), 3500);
    } catch (e) {
      setError(`Save failed: ${String(e)}`);
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

  const onToggleSelected = (id: string, on: boolean) => {
    setSelected((prev) => (on ? [...new Set([...prev, id])] : prev.filter((x) => x !== id)));
  };

  const bulkPatch = async (patch: Partial<LibraryComponent>) => {
    if (!selected.length) return;
    try {
      await bulkUpdateLibraryComponents(selected, patch);
      setSelected([]);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

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
        <select className="lib-cat" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value as never)} title="Filter by source">
          <option value="all">Source: All</option>
          <option value="rdm">RDM Layout Editor</option>
          <option value="custom">Custom</option>
          <option value="extracted">Extracted</option>
          <option value="workbook">Workbook</option>
          <option value="reference">Reference</option>
        </select>
      </div>
      <label className="lib-showretired" title="Show retired components">
        <input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} /> Show retired
      </label>
      <label className="lib-showretired" title="Show candidate items pending review">
        <input type="checkbox" checked={showCandidates} onChange={(e) => setShowCandidates(e.target.checked)} /> Show Candidates
      </label>
      <label className="lib-showretired" title="Show items marked Needs Review">
        <input type="checkbox" checked={showNeedsReview} onChange={(e) => setShowNeedsReview(e.target.checked)} /> Show Needs Review
      </label>
      <label className="lib-showretired" title="Show reference pages (full drawings/layout crops)">
        <input type="checkbox" checked={showReferencePages} onChange={(e) => setShowReferencePages(e.target.checked)} /> Show Reference Pages
      </label>
      <label className="lib-showretired" title="Show duplicate items">
        <input type="checkbox" checked={showDuplicates} onChange={(e) => setShowDuplicates(e.target.checked)} /> Show Duplicates
      </label>
      <label className="lib-showretired" title="Insert equipment/components with an editable text label (off for logos/symbols)">
        <input type="checkbox" checked={insertWithLabel} onChange={(e) => setInsertWithLabel(e.target.checked)} /> Insert with label
      </label>
      <div className="lib-toolbar">
        <button className="lib-btn" onClick={() => void doAutoCategorize()} title="Auto-assign categories from part names/keywords (review afterwards)">Auto-categorize</button>
        <button className="lib-btn" onClick={() => void doImportRdmFolder()} title="Import official RDM Layout Editor image folder (local path)">Import RDM Folder</button>
        <button className="lib-btn" onClick={() => void doImportLocalFolder()} title="Import / Reset from a local library assets folder">Reset From Folder</button>
        <button className="lib-btn" onClick={() => void doRescanInbox()} title="Scan .docs/library/inbox and import files as Needs Review candidates">Rescan Inbox</button>
        <button className="lib-btn" onClick={() => void doRescanLibrary()} title="Scan custom component/reference folders for manually-added files">Rescan Library</button>
        <button className="lib-btn" onClick={() => void doSyncNames()} title="Sync display names from asset filenames for non-curated items">Sync Names From Files</button>
        <button className="lib-btn" onClick={() => void doRebuildThumbs()} title="Rebuild missing/outdated thumbnails from full-resolution assets">Rebuild Thumbnails</button>
        <button className="lib-btn" onClick={() => void doArchiveDirty()} title="Archive dirty extracted candidates (status only; no delete)">Archive Dirty Extracted</button>
        <label className="lib-btn file-ribbon-btn" title="Upload a new image into the library (starts as Needs Review)">
          Add Files
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/svg+xml,image/gif,image/bmp"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void doAddFiles(f); e.currentTarget.value = ''; }}
          />
        </label>
      </div>
      <div className="lib-toolbar">
        <button className="lib-btn" disabled={!selected.length} onClick={() => void bulkPatch({ status: 'approved' })} title="Approve selected items">Approve Selected</button>
        <button className="lib-btn" disabled={!selected.length} onClick={() => void bulkPatch({ status: 'retired' })} title="Retire selected items">Retire Selected</button>
        <button className="lib-btn" disabled={!selected.length} onClick={() => void bulkPatch({ status: 'reference_page', category: 'reference-page' })} title="Mark selected as Reference Pages">Mark Reference</button>
        <button className="lib-btn" disabled={!selected.length} onClick={() => void bulkPatch({ status: 'needs_review', category: 'review' })} title="Move selected to Needs Review">Needs Review</button>
      </div>
      <div className="lib-paths">
        <div>Root: {data?.paths?.root || '(unknown)'}</div>
        <div>Inbox: {data?.paths?.inbox || '(unknown)'}</div>
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
            <label className="lib-pick" title="Select for bulk actions">
              <input
                type="checkbox"
                aria-label={`Select ${c.displayName} for bulk actions`}
                title={`Select ${c.displayName} for bulk actions`}
                checked={selected.includes(c.id)}
                onChange={(e) => onToggleSelected(c.id, e.target.checked)}
              />
            </label>
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
                <input className="lib-edit-name" value={editShort} placeholder="Short name" onChange={(e) => setEditShort(e.target.value)} />
                <input className="lib-edit-name" value={editPart} placeholder="Part number" onChange={(e) => setEditPart(e.target.value)} />
                <input className="lib-edit-name" value={editAliases} placeholder="Aliases (comma-separated)" onChange={(e) => setEditAliases(e.target.value)} />
                <input className="lib-edit-name" value={editTags} placeholder="Tags (comma-separated)" onChange={(e) => setEditTags(e.target.value)} />
                <input className="lib-edit-name" value={editDefaultLabel} placeholder="Default insert label" onChange={(e) => setEditDefaultLabel(e.target.value)} />
                <select className="lib-edit-cat" value={editStatus} onChange={(e) => setEditStatus(e.target.value)} title="Status">
                  <option value="approved">Approved</option>
                  <option value="candidate">Candidate</option>
                  <option value="needs_review">Needs Review</option>
                  <option value="duplicate">Duplicate</option>
                  <option value="reference_page">Reference Page</option>
                  <option value="retired">Retired</option>
                </select>
                <label className="lib-showretired"><input type="checkbox" checked={editInsertWithLabel} onChange={(e) => setEditInsertWithLabel(e.target.checked)} /> Insert with label</label>
                <label className="lib-showretired"><input type="checkbox" checked={editRenameAssetFile} onChange={(e) => setEditRenameAssetFile(e.target.checked)} /> Also rename asset file</label>
                <input className="lib-edit-name" value={editNotes} placeholder="Notes" onChange={(e) => setEditNotes(e.target.value)} />
                <div className="lib-actions">
                  <button className="lib-btn" onClick={() => void saveEdit(c)}>Save</button>
                  <button className="lib-btn" onClick={() => setEditId(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <>
                <div className="lib-meta">
                  <div className="lib-name">{c.shortName || c.displayName}</div>
                  <div className="lib-sub">
                    {c.partNumber || c.category}
                    {isRetired(c) ? ' · retired' : ''}
                    {c.status ? ` · ${c.status}` : ''}
                    {c.duplicateGroupId ? ` · ${c.duplicateGroupId}` : ''}
                  </div>
                  {c.sourceQuality === 'thumbnail_only' && (
                    <div className="lib-sourcewarn" title="Thumbnail-only source can be low resolution for output">
                      This asset may be low resolution. Replace with original if available.
                    </div>
                  )}
                  <div className="lib-badges">
                    {(String(c.source?.sourceType || '').toLowerCase() === 'rdm-layout-editor' || String(c.assetPath || '').toLowerCase().includes('/rdm_layout_editor/')) && <span className="lib-badge">RDM</span>}
                    {String(c.assetPath || '').toLowerCase().includes('/components/custom/') && <span className="lib-badge">Custom</span>}
                    {c.status === 'needs_review' && <span className="lib-badge warn">Needs Review</span>}
                    {c.status === 'approved' && <span className="lib-badge ok">Approved</span>}
                    {c.status === 'duplicate' && <span className="lib-badge">Duplicate</span>}
                    {c.status === 'reference_page' && <span className="lib-badge">Reference</span>}
                  </div>
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
      {savedMsg && <p className="lib-saved">{savedMsg}</p>}
      {error && <p className="lib-error">{error}</p>}
    </div>
  );
}
