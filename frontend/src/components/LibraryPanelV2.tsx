import { useEffect, useMemo, useRef, useState } from 'react';
import {
  batchUpdateLibV2Components,
  cleanLibV2PhysicalDuplicates,
  duplicateLibV2Component,
  getLibV2,
  libV2AssetUrl,
  listLegendTemplates,
  listLibV2History,
  migrateLegacyLibV2,
  rebuildLibV2Thumbnails,
  refreshLibV2,
  replaceLibV2Asset,
  restoreLibV2History,
  updateLibV2Component,
  type LegendTemplateEntry,
  type LibV2Component,
  type LibV2Data,
  type LibV2HistoryEntry,
} from '../api/client';
import { COMPONENT_DRAG_TYPE } from './ComponentLibrary';
import '../styles/libraryV2.css';

interface Props {
  onInsert: (
    name: string,
    url: string,
    label: string | null,
    meta?: { category?: string; defaultWidth?: number; defaultHeight?: number; acronym?: string },
  ) => void;
  canInsert: boolean;
  activePageType?: string;
  onOpenLegendEditor?: () => void;
}

type ViewRep = 'source' | 'edge' | 'bw';
type SortKey = 'displayName' | 'category' | 'collection' | 'partNumber' | 'status';
type AnyComp = LibV2Component & Record<string, any>;

const NO_LABEL_CATS = new Set(['logos', 'symbols_markers', 'reference_pages']);

const CATEGORY_PRESETS = [
  { id: 'controllers', label: 'Controllers' },
  { id: 'expansion_modules', label: 'Expansion Modules' },
  { id: 'panels_enclosures', label: 'Panels / Enclosures' },
  { id: 'electrical_power', label: 'Electrical / Power' },
  { id: 'power_metering', label: 'Power Metering' },
  { id: 'network_data', label: 'Network / Data' },
  { id: 'sensors_transducers', label: 'Sensors / Transducers' },
  { id: 'alarms_safety', label: 'Alarms / Safety' },
  { id: 'refrigeration', label: 'Refrigeration' },
  { id: 'hvac', label: 'HVAC' },
  { id: 'lighting', label: 'Lighting' },
  { id: 'symbols_markers', label: 'Symbols / Markers' },
  { id: 'legends', label: 'Legends' },
  { id: 'logos', label: 'Logos' },
  { id: 'custom', label: 'Custom' },
];

const STATUS_OPTIONS = [
  { id: '', label: 'Blank / Active' },
  { id: 'approved', label: 'Approved' },
  { id: 'needsReview', label: 'Needs Review' },
  { id: 'reference', label: 'Reference' },
  { id: 'retired', label: 'Retired' },
  { id: 'duplicate', label: 'Duplicate' },
  { id: 'junk', label: 'Junk' },
];

const MAPPER_SYMBOL_COLLECTION = 'Refrigeration Controls Symbols';
const PLAN_MARKER_COLLECTION = 'Singh360 Plan Markers';

const COLLECTION_PRESETS = [
  'Controllers',
  'RDM / Network',
  'WICP Safety / Alarms',
  'Signage / Safety',
  'Power Metering',
  'Electrical Power',
  'Panels / Enclosures',
  'Sensors / Transducers',
  'Refrigeration Controls',
  'HVAC / BACnet',
  'Lighting',
  'Symbols / Markers',
  'Refrigeration Controls Symbols',
  'Singh360 Plan Markers',
  'Safety Signage',
  'Callout Numbers',
  'Needs Review',
];

function asAny(c: LibV2Component | null | undefined): AnyComp {
  return (c || {}) as AnyComp;
}

function csvToArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((x) => String(x).trim()).filter(Boolean);
  return String(value || '')
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean);
}

function arrayToCsv(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  return String(value || '');
}

function categoriesFor(c: LibV2Component): string[] {
  const x = asAny(c);
  const values = Array.isArray(x.categories) ? x.categories : [x.category || 'custom'];
  return Array.from(new Set([x.category || 'custom', ...values].map((v) => String(v || '').trim()).filter(Boolean)));
}

function editedCategories(c: LibV2Component, edits: Record<string, Partial<AnyComp>>): string[] {
  const raw = patchValue(c, edits, 'categories', categoriesFor(c));
  const values = csvToArray(raw);
  const primary = String(patchValue(c, edits, 'category', c.category || 'custom'));
  return Array.from(new Set([primary, ...values].filter(Boolean)));
}

function normalizeText(value: unknown): string {
  return String(value || '').trim();
}

function niceCategoryLabel(id: string): string {
  const preset = CATEGORY_PRESETS.find((c) => c.id === id);
  if (preset) return preset.label;
  return id.replace(/[_-]+/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());
}

function displayNameFor(c: LibV2Component): string {
  const raw = (c.displayName || '').trim();
  if (!raw) return 'Component';
  return raw.replace(/_+/g, ' ').replace(/\s+/g, ' ').trim();
}

function sourceUrl(c: LibV2Component): string {
  const x = asAny(c);
  return x.sourceUrl || (x.sourceFile ? libV2AssetUrl(x.sourceFile) : '') || (x.assetPath ? libV2AssetUrl(x.assetPath) : '');
}

function edgeUrl(c: LibV2Component): string {
  const x = asAny(c);
  return x.edgeUrl || (x.edgeFile ? libV2AssetUrl(x.edgeFile) : '');
}

function bwUrl(c: LibV2Component): string {
  const x = asAny(c);
  return x.bwUrl || (x.bwFile ? libV2AssetUrl(x.bwFile) : '');
}

function previewUrl(c: LibV2Component, rep: ViewRep): string {
  const x = asAny(c);
  if (rep === 'edge') return edgeUrl(c) || sourceUrl(c);
  if (rep === 'bw') return bwUrl(c) || edgeUrl(c) || sourceUrl(c);
  return x.thumbnailUrl || sourceUrl(c) || edgeUrl(c) || bwUrl(c);
}

function variantUrl(c: LibV2Component, rep: ViewRep): string {
  if (rep === 'edge') return edgeUrl(c);
  if (rep === 'bw') return bwUrl(c);
  return sourceUrl(c);
}

function labelFor(c: LibV2Component): string | null {
  const cat = String(c.category || '').toLowerCase();
  if (NO_LABEL_CATS.has(cat)) return null;

  const x = asAny(c);
  const candidates = [x.defaultLabel, x.partNumber, x.displayName, x.shortName];

  for (const item of candidates) {
    const val = String(item || '').trim();
    if (!val) continue;
    if (/[0-9a-f]{10,}/i.test(val) || /^controller_/i.test(val)) continue;
    return val;
  }

  return null;
}

function isRetired(c: LibV2Component): boolean {
  const x = asAny(c);
  const status = String(x.status || '').toLowerCase();
  return !!x.retired || !!x.hidden || ['retired', 'duplicate', 'junk', 'hidden'].includes(status);
}

function statusFor(c: LibV2Component): string {
  const x = asAny(c);
  if (isRetired(c)) return String(x.status || 'retired');
  return String(x.status || '');
}

function collectionFor(c: LibV2Component): string {
  const x = asAny(c);
  return String(x.collection || x.family || '').trim();
}

function pathFor(c: LibV2Component): string {
  const x = asAny(c);
  return String(x.sourceFile || x.edgeFile || x.bwFile || x.assetPath || x.thumbnailPath || '').trim();
}

function defaultRepForPage(pageType: string | undefined, data: LibV2Data | null): ViewRep {
  const hasAnyEdge = !!data?.components?.some((c) => !!edgeUrl(c));
  const drawingPages = new Set(['canvas', 'hybrid', 'underlay']);
  if (pageType && drawingPages.has(pageType) && hasAnyEdge) return 'edge';
  return 'source';
}

function patchValue<T = unknown>(c: LibV2Component, edits: Record<string, Partial<AnyComp>>, key: string, fallback: T): T {
  const row = edits[c.id];
  if (row && Object.prototype.hasOwnProperty.call(row, key)) return row[key] as T;
  const x = asAny(c);
  return (x[key] ?? fallback) as T;
}

function componentSearchBlob(c: LibV2Component, edits: Record<string, Partial<AnyComp>>): string {
  const x = asAny(c);
  const edit = edits[c.id] || {};
  return [
    edit.displayName ?? x.displayName,
    edit.defaultLabel ?? x.defaultLabel,
    edit.partNumber ?? x.partNumber,
    edit.category ?? x.category,
    arrayToCsv(edit.categories ?? x.categories),
    edit.collection ?? x.collection,
    edit.shortName ?? x.shortName,
    edit.status ?? x.status,
    arrayToCsv(edit.aliases ?? x.aliases),
    arrayToCsv(edit.tags ?? x.tags),
    edit.notes ?? x.notes,
    pathFor(c),
  ].join(' ').toLowerCase();
}

function defaultSizeLabel(c: LibV2Component): string {
  const x = asAny(c);
  const w = x.defaultWidth || x.width;
  const h = x.defaultHeight || x.height;
  if (!w && !h) return '';
  return `${w || '?'} × ${h || '?'}`;
}

function insertMetaFor(c: LibV2Component): {
  category?: string;
  defaultWidth?: number;
  defaultHeight?: number;
  acronym?: string;
} {
  const x = asAny(c);
  const width = Number(x.defaultWidth || x.width || 0);
  const height = Number(x.defaultHeight || x.height || 0);
  const acronym = String(x.shortName || x.defaultLabel || '').trim();
  return {
    category: String(c.category || '').trim() || undefined,
    defaultWidth: width > 0 ? width : undefined,
    defaultHeight: height > 0 ? height : undefined,
    acronym: acronym || undefined,
  };
}

function CardPreview({ c, rep, small = false }: { c: LibV2Component; rep: ViewRep; small?: boolean }) {
  const url = previewUrl(c, rep);
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [url]);

  if (!url || broken) {
    return (
      <div className={small ? 'libv2-mini-preview empty' : 'libv2-preview empty'}>
        <span className="libv2-preview-fallback-name">{displayNameFor(c)}</span>
        <span className="libv2-preview-fallback-reason">{url ? 'Preview failed to load' : 'No preview file'}</span>
      </div>
    );
  }

  return (
    <div className={small ? 'libv2-mini-preview' : 'libv2-preview'}>
      <img
        src={url}
        alt={displayNameFor(c)}
        title={displayNameFor(c)}
        loading="lazy"
        draggable={false}
        onError={() => setBroken(true)}
      />
    </div>
  );
}

export default function LibraryPanelV2({ onInsert, canInsert, activePageType, onOpenLegendEditor }: Props) {
  const [data, setData] = useState<LibV2Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [collection, setCollection] = useState('all');
  const [rep, setRep] = useState<ViewRep>('source');
  const [showDashboard, setShowDashboard] = useState(false);
  const [showLegacyItems, setShowLegacyItems] = useState(true);

  const [builderQuery, setBuilderQuery] = useState('');
  const [builderCategory, setBuilderCategory] = useState('all');
  const [builderCollection, setBuilderCollection] = useState('all');
  const [builderStatus, setBuilderStatus] = useState('active');
  const [showRetired, setShowRetired] = useState(false);
  const [showNeedsReview, setShowNeedsReview] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('category');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const [selectedId, setSelectedId] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, Partial<AnyComp>>>({});
  const [bulkCategory, setBulkCategory] = useState('');
  const [bulkCollection, setBulkCollection] = useState('');
  const [bulkStatus, setBulkStatus] = useState('');

  const [legendTemplates, setLegendTemplates] = useState<LegendTemplateEntry[]>([]);
  const [libraryHistory, setLibraryHistory] = useState<LibV2HistoryEntry[]>([]);
  const [bulkUndo, setBulkUndo] = useState<Record<string, Partial<AnyComp>> | null>(null);

  const replaceSourceRef = useRef<HTMLInputElement>(null);
  const replaceEdgeRef = useRef<HTMLInputElement>(null);
  const replaceBwRef = useRef<HTMLInputElement>(null);
  const addFilesRef = useRef<HTMLInputElement>(null);

  const load = async (includeLegacy = true) => {
    setLoading(true);
    setLoadError('');
    try {
      const [lib, legends, history] = await Promise.all([
        getLibV2(includeLegacy),
        listLegendTemplates(),
        listLibV2History(),
      ]);
      setData(lib);
      setLegendTemplates(legends);
      setLibraryHistory(history);
      setSelectedId((prev) => prev || lib.components?.[0]?.id || '');
    } catch (error) {
      setLoadError(String(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(true); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => { setRep(defaultRepForPage(activePageType, data)); }, [activePageType, data]);

  const components = data?.components ?? [];
  const previewReady = useMemo(() => components.filter((component) => !!previewUrl(component, rep)).length, [components, rep]);

  const selected = useMemo(() => {
    return components.find((c) => c.id === selectedId) || components.find((c) => selectedIds.includes(c.id)) || null;
  }, [components, selectedId, selectedIds]);

  const categories = useMemo(() => {
    const ids = new Set<string>();
    CATEGORY_PRESETS.forEach((c) => ids.add(c.id));
    components.forEach((c) => { categoriesFor(c).forEach((id) => ids.add(id)); });
    const counts = new Map<string, number>();
    components.forEach((c) => {
      categoriesFor(c).forEach((id) => counts.set(id, (counts.get(id) || 0) + 1));
    });
    return Array.from(ids).sort().map((id) => ({
      id,
      label: niceCategoryLabel(id),
      count: counts.get(id) || 0,
    }));
  }, [components]);

  const collections = useMemo(() => {
    const set = new Set<string>();
    COLLECTION_PRESETS.forEach((x) => set.add(x));
    components.forEach((c) => {
      const val = collectionFor(c);
      if (val) set.add(val);
    });
    return Array.from(set).sort();
  }, [components]);

  const mapperSymbolCount = useMemo(
    () => components.filter(
      (component) => !isRetired(component)
        && collectionFor(component) === MAPPER_SYMBOL_COLLECTION,
    ).length,
    [components],
  );
  const planMarkerCount = useMemo(
    () => components.filter(
      (component) => !isRetired(component)
        && collectionFor(component) === PLAN_MARKER_COLLECTION,
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

  const dashboardRows = useMemo(() => {
    const q = builderQuery.trim().toLowerCase();

    const rows = components.filter((c) => {
      const x = asAny(c);
      const retired = isRetired(c);
      const status = String(patchValue(c, edits, 'status', x.status || '') || '').toLowerCase();
      const cats = editedCategories(c, edits);
      const collection = String(patchValue(c, edits, 'collection', collectionFor(c)) || '');

      if (!showRetired && retired) return false;
      if (!showNeedsReview && status === 'needsreview') return false;
      if (builderCategory !== 'all' && !cats.includes(builderCategory)) return false;
      if (builderCollection !== 'all' && collection !== builderCollection) return false;

      if (builderStatus === 'active' && retired) return false;
      if (builderStatus === 'approved' && status !== 'approved') return false;
      if (builderStatus === 'needsReview' && status !== 'needsreview') return false;
      if (builderStatus === 'retired' && !retired) return false;
      if (builderStatus === 'blank' && status) return false;

      if (!q) return true;
      return componentSearchBlob(c, edits).includes(q);
    });

    rows.sort((a, b) => {
      const av = String(sortComparable(a, edits, sortKey)).toLowerCase();
      const bv = String(sortComparable(b, edits, sortKey)).toLowerCase();
      const res = av.localeCompare(bv, undefined, { numeric: true, sensitivity: 'base' });
      return sortDir === 'asc' ? res : -res;
    });

    return rows;
  }, [components, builderQuery, builderCategory, builderCollection, builderStatus, showRetired, showNeedsReview, edits, sortKey, sortDir]);

  const dirtyIds = useMemo(() => Object.keys(edits).filter((id) => Object.keys(edits[id] || {}).length), [edits]);
  const visibleSelectedCount = selectedIds.filter((id) => dashboardRows.some((r) => r.id === id)).length;

  const setEdit = (id: string, key: string, value: unknown) => {
    setEdits((prev) => ({
      ...prev,
      [id]: {
        ...(prev[id] || {}),
        [key]: value,
      },
    }));
  };

  const clearEditsFor = (id: string) => {
    setEdits((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const toggleSelected = (id: string) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
    setSelectedId(id);
  };

  const selectVisible = () => {
    setSelectedIds(dashboardRows.map((c) => c.id));
    if (dashboardRows[0]) setSelectedId(dashboardRows[0].id);
  };

  const clearSelected = () => setSelectedIds([]);

  const canInsertRep = (c: LibV2Component, which: ViewRep): boolean => {
    return !!variantUrl(c, which);
  };

  const insertAs = (c: LibV2Component, which: ViewRep, withLabel = true) => {
    if (!canInsert) return;
    const url = variantUrl(c, which) || previewUrl(c, which);
    if (!url) return;
    onInsert(displayNameFor(c), url, withLabel ? labelFor(c) : null, insertMetaFor(c));
  };

  const onDragStart = (e: React.DragEvent, c: LibV2Component) => {
    const url = variantUrl(c, rep) || previewUrl(c, rep);
    if (!url) return;
    e.dataTransfer.setData(COMPONENT_DRAG_TYPE, JSON.stringify({
      name: displayNameFor(c),
      url,
      label: labelFor(c),
      ...insertMetaFor(c),
    }));
    e.dataTransfer.effectAllowed = 'copy';
  };

  const doRefresh = async () => {
    setLoading(true);
    try {
      await refreshLibV2();
      await load(showLegacyItems);
    } finally {
      setLoading(false);
    }
  };

  const rebuildPreviews = async () => {
    setLoading(true);
    setLoadError('');
    try {
      await rebuildLibV2Thumbnails();
      await load(showLegacyItems);
    } catch (error) {
      setLoadError(String(error));
    } finally {
      setLoading(false);
    }
  };

  const reloadFromDisk = async () => {
    if (dirtyIds.length && !window.confirm(
      `Discard ${dirtyIds.length} unsaved component edit${dirtyIds.length === 1 ? '' : 's'} and reload the saved library?`,
    )) return;
    setEdits({});
    setBulkUndo(null);
    setSelectedIds([]);
    setBulkCategory('');
    setBulkCollection('');
    setBulkStatus('');
    await doRefresh();
  };

  const discardStagedEdits = () => {
    if (!dirtyIds.length) return;
    if (!window.confirm(`Discard all ${dirtyIds.length} unsaved edits? Nothing saved on disk will change.`)) return;
    setBulkUndo(structuredClone(edits));
    setEdits({});
    setBulkCategory('');
    setBulkCollection('');
    setBulkStatus('');
  };

  const undoStagedBulk = () => {
    if (!bulkUndo) return;
    setEdits(bulkUndo);
    setBulkUndo(null);
  };

  const undoLastSavedLibraryChange = async () => {
    const latest = libraryHistory[0];
    if (!latest) {
      window.alert('No saved library history exists yet.');
      return;
    }
    if (!window.confirm(
      `Restore the library to the snapshot from ${latest.savedAt}?\n\n${latest.reason}\n\nThe current manifest will be backed up first.`,
    )) return;
    setLoading(true);
    try {
      await restoreLibV2History(latest.name);
      setEdits({});
      setBulkUndo(null);
      setSelectedIds([]);
      await load(showLegacyItems);
      window.alert('The last saved library change was undone.');
    } finally {
      setLoading(false);
    }
  };

  const saveDirty = async () => {
    const ids = Object.keys(edits).filter((id) => Object.keys(edits[id] || {}).length);
    if (!ids.length) return;

    if (ids.length > 10 && !window.confirm(
      `Save ${ids.length} component edits to disk?

One automatic undo snapshot will be created first.`,
    )) return;

    const updates = ids.map((id) => {
      const patch = { ...edits[id] } as AnyComp;
      if (Object.prototype.hasOwnProperty.call(patch, 'aliases')) patch.aliases = csvToArray(patch.aliases);
      if (Object.prototype.hasOwnProperty.call(patch, 'tags')) patch.tags = csvToArray(patch.tags);
      if (Object.prototype.hasOwnProperty.call(patch, 'categories')) patch.categories = csvToArray(patch.categories);
      if (patch.status === 'retired' || patch.status === 'duplicate' || patch.status === 'junk') {
        patch.retired = true;
      } else if (Object.prototype.hasOwnProperty.call(patch, 'status')) {
        patch.retired = false;
      }
      return { id, patch };
    });

    setLoading(true);
    try {
      const result = await batchUpdateLibV2Components(
        updates,
        `dashboard-save-${ids.length}-components`,
      );
      setEdits({});
      setBulkUndo(null);
      setSelectedIds([]);
      await load(showLegacyItems);
      window.alert(
        `Saved ${result.updated} component edits.
Undo snapshot: ${result.snapshot || 'created'}`,
      );
    } finally {
      setLoading(false);
    }
  };

  const saveSingle = async (c: LibV2Component) => {
    const patch = edits[c.id];
    if (!patch || !Object.keys(patch).length) return;
    await updateLibV2Component(c.id, {
      ...patch,
      aliases: Object.prototype.hasOwnProperty.call(patch, 'aliases') ? csvToArray(patch.aliases) : undefined,
      tags: Object.prototype.hasOwnProperty.call(patch, 'tags') ? csvToArray((patch as AnyComp).tags) : undefined,
      categories: Object.prototype.hasOwnProperty.call(patch, 'categories') ? csvToArray((patch as AnyComp).categories) : undefined,
      retired: ['retired', 'duplicate', 'junk'].includes(String((patch as AnyComp).status || '').toLowerCase()) ? true : undefined,
    } as any);
    clearEditsFor(c.id);
    await load(showLegacyItems);
  };

  const applyBulk = () => {
    if (!selectedIds.length) return;
    if (!bulkCategory && !bulkCollection && !bulkStatus) {
      window.alert('Choose a bulk category, collection, or status first.');
      return;
    }

    const changes = [
      bulkCategory ? `category = ${niceCategoryLabel(bulkCategory)}` : '',
      bulkCollection ? `collection = ${bulkCollection}` : '',
      bulkStatus ? `status = ${bulkStatus || 'blank'}` : '',
    ].filter(Boolean).join(', ');

    if (selectedIds.length > 10 && !window.confirm(
      `Stage bulk changes for ${selectedIds.length} selected components?

${changes}

This is NOT saved until you click Save All Edits.`,
    )) return;

    setBulkUndo(structuredClone(edits));
    const selectedSet = new Set(selectedIds);
    setEdits((prev) => {
      const next = { ...prev };
      for (const c of components) {
        if (!selectedSet.has(c.id)) continue;
        const row = { ...(next[c.id] || {}) } as AnyComp;
        if (bulkCategory) {
          row.category = bulkCategory;
          row.categories = Array.from(new Set([bulkCategory, ...categoriesFor(c)]));
        }
        if (bulkCollection) row.collection = bulkCollection;
        if (bulkStatus) {
          row.status = bulkStatus;
          row.retired = ['retired', 'duplicate', 'junk'].includes(bulkStatus);
        }
        next[c.id] = row;
      }
      return next;
    });
  };

  const normalizeSelectedNames = () => {
    if (!selectedIds.length) return;
    if (selectedIds.length > 10 && !window.confirm(
      `Stage cleaned display names for ${selectedIds.length} selected components?`,
    )) return;
    setBulkUndo(structuredClone(edits));
    const selectedSet = new Set(selectedIds);

    setEdits((prev) => {
      const next = { ...prev };
      for (const c of components) {
        if (!selectedSet.has(c.id)) continue;
        const row = { ...(next[c.id] || {}) };
        const current = String(row.displayName ?? c.displayName ?? '');
        row.displayName = current
          .replace(/^sym[_\s-]+/i, '')
          .replace(/^symbol[_\s-]+/i, '')
          .replace(/[_]+/g, ' ')
          .replace(/\s+/g, ' ')
          .replace(/\b(li|da|ls|lsc|es|ea|idf|mdf|wicp|lcp|rdm|ems|cat6|oat|ct|eev|llv)\b/gi, (m) => {
            const map: Record<string, string> = {
              li: 'LI', da: 'DA', ls: 'LS', lsc: 'LSc', es: 'ES', ea: 'EA',
              idf: 'IDF', mdf: 'MDF', wicp: 'WICP', lcp: 'LCP', rdm: 'RDM',
              ems: 'EMS', cat6: 'CAT6', oat: 'OAT', ct: 'CT', eev: 'EEV', llv: 'LLV',
            };
            return map[m.toLowerCase()] || m;
          })
          .trim();
        next[c.id] = row;
      }
      return next;
    });
  };

  const duplicateSelected = async () => {
    if (!selected) return;
    await duplicateLibV2Component(selected.id);
    await load(showLegacyItems);
  };

  const replaceAsset = async (target: 'source' | 'edge' | 'bw', file: File | null) => {
    if (!selected || !file) return;
    await replaceLibV2Asset(selected.id, target, file);
    await load(showLegacyItems);
  };

  const addFilesToLibrary = async (files: FileList | null) => {
    if (!files || !files.length) return;
    const categoryToUse = builderCategory !== 'all' ? builderCategory : 'custom';
    const collectionToUse = builderCollection !== 'all' ? builderCollection : '';

    setLoading(true);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('category', categoryToUse);
        if (collectionToUse) fd.append('collection', collectionToUse);
        const res = await fetch('/api/lib/add-file', { method: 'POST', body: fd });
        if (!res.ok) throw new Error(await res.text());
      }
      await doRefresh();
    } finally {
      setLoading(false);
      if (addFilesRef.current) addFilesRef.current.value = '';
    }
  };

  const exportCsv = () => {
    const header = ['id', 'displayName', 'category', 'categories', 'collection', 'partNumber', 'shortName', 'status', 'defaultLabel', 'aliases', 'tags', 'notes', 'path'];
    const rows = dashboardRows.map((c) => {
      const x = asAny(c);
      const e = edits[c.id] || {};
      return [
        c.id,
        e.displayName ?? x.displayName ?? '',
        e.category ?? x.category ?? '',
        arrayToCsv((e as AnyComp).categories ?? x.categories ?? categoriesFor(c)),
        e.collection ?? collectionFor(c),
        e.partNumber ?? x.partNumber ?? '',
        e.shortName ?? x.shortName ?? '',
        e.status ?? x.status ?? '',
        e.defaultLabel ?? x.defaultLabel ?? '',
        arrayToCsv(e.aliases ?? x.aliases),
        arrayToCsv((e as AnyComp).tags ?? x.tags),
        e.notes ?? x.notes ?? '',
        pathFor(c),
      ];
    });
    downloadText('singh360_component_library_view.csv', toCsv([header, ...rows]));
  };

  const downloadJson = () => {
    const merged = components.map((c) => ({ ...asAny(c), ...(edits[c.id] || {}) }));
    downloadText('singh360_component_library_edited_view.json', JSON.stringify({ components: merged }, null, 2));
  };

  const openSavedLegend = (templateId?: string) => {
    try {
      if (templateId) localStorage.setItem('singh360-symbol-legend-template-id', templateId);
      else localStorage.removeItem('singh360-symbol-legend-template-id');
    } catch {
      // The modal still opens the live standard when browser storage is unavailable.
    }
    setShowDashboard(false);
    onOpenLegendEditor?.();
  };

  const preferredLegendTemplate = legendTemplates.find((template) => template.id === 'singh360-plan-marker-legend')
    || legendTemplates.find((template) => template.id === 'singh360-refrigeration-symbols-standard')
    || legendTemplates[0];

  const runAdvanced = async (kind: 'thumbs' | 'clean' | 'migrate') => {
    setLoading(true);
    try {
      if (kind === 'thumbs') {
        await rebuildLibV2Thumbnails();
        window.alert('Thumbnail rebuild complete.');
      }
      if (kind === 'clean') {
        const preview = await cleanLibV2PhysicalDuplicates(true);
        window.alert(`Duplicate groups: ${preview.duplicateGroups || 0}\nDuplicates: ${preview.duplicates || 0}\nDry-run only.`);
      }
      if (kind === 'migrate') {
        const preview = await migrateLegacyLibV2(true);
        if (preview.willCopy && window.confirm(`Migrate ${preview.willCopy} legacy files into V2 components?`)) {
          await migrateLegacyLibV2(false);
        }
      }
      await load(showLegacyItems);
    } finally {
      setLoading(false);
    }
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
            {categories.map((c) => <option key={c.id} value={c.id}>{c.label} ({c.count})</option>)}
          </select>
          <select className="libv2-grow" title="Filter by collection" value={collection} onChange={(e) => setCollection(e.target.value)}>
            <option value="all">All collections</option>
            {collections.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </div>
        <div className="libv2-row libv2-quick-filters">
          <button
            className={collection === MAPPER_SYMBOL_COLLECTION ? 'active' : undefined}
            aria-pressed={collection === MAPPER_SYMBOL_COLLECTION}
            title="Square highlighted symbols used by Symbol Mapper on existing drawings"
            onClick={() => {
              setCollection((current) => current === MAPPER_SYMBOL_COLLECTION ? 'all' : MAPPER_SYMBOL_COLLECTION);
              setCategory('all');
              setQuery('');
            }}
          >
            Mapper Highlights ({mapperSymbolCount})
          </button>
          <button
            className={collection === PLAN_MARKER_COLLECTION ? 'active' : undefined}
            aria-pressed={collection === PLAN_MARKER_COLLECTION}
            title="Simple colored-ring markers for direct placement on plan and layout pages"
            onClick={() => {
              setCollection((current) => current === PLAN_MARKER_COLLECTION ? 'all' : PLAN_MARKER_COLLECTION);
              setCategory('all');
              setQuery('');
            }}
          >
            Plan Markers ({planMarkerCount})
          </button>
          {collection !== 'all' && (
            <button onClick={() => setCollection('all')}>Show All Components</button>
          )}
        </div>
        <div className="libv2-row libv2-modes">
          {(['source', 'edge', 'bw'] as ViewRep[]).map((r) => (
            <button key={r} className={rep === r ? 'active' : undefined} onClick={() => setRep(r)}>
              {r === 'source' ? 'Source' : r === 'edge' ? 'Edge' : 'B/W'}
            </button>
          ))}
        </div>
        <div className="libv2-row">
          <button onClick={() => setShowDashboard(true)}>Manage Components</button>
          <button onClick={() => void doRefresh()} disabled={loading}>Refresh</button>
          <button onClick={() => void rebuildPreviews()} disabled={loading}>Rebuild Previews</button>
        </div>
      </div>

      <div className={`libv2-health ${loadError ? 'error' : ''}`}>
        {loadError ? `Library error: ${loadError}` : loading ? 'Loading component library…' : `${visibleCards.length} shown · ${components.length} total · ${previewReady} previews ready`}
      </div>

      {legendTemplates.length > 0 && (
        <section className="libv2-saved-legends" aria-label="Saved symbol legends">
          <div className="libv2-saved-legends-head">
            <strong>Saved Symbol Legends</strong>
            <span>Editable grouped legends; separate from individual symbol components.</span>
          </div>
          <div className="libv2-saved-legends-grid">
            {legendTemplates.map((template) => (
              <button key={template.id} className="libv2-saved-legend-card" onClick={() => openSavedLegend(template.id)}>
                <strong>{template.name}</strong>
                <span>{template.rowCount ?? 0} rows</span>
                <em>Open / Insert</em>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="libv2-grid">
        {visibleCards.map((c) => {
          const canCurrent = !!(variantUrl(c, rep) || previewUrl(c, rep));
          return (
            <div key={c.id} className={`libv2-card ${previewUrl(c, rep) ? '' : 'preview-missing'}`} title={displayNameFor(c)} draggable={canInsert && canCurrent} onDragStart={(e) => onDragStart(e, c)}>
              <CardPreview c={c} rep={rep} />
              <div className="libv2-meta">
                <div className="libv2-name">{displayNameFor(c)}</div>
                <div className="libv2-part">{asAny(c).partNumber || asAny(c).defaultLabel || ''}</div>
                <div className="libv2-actions">
                  <button onClick={() => insertAs(c, rep)} disabled={!canInsert || !canCurrent}>Insert</button>
                  <details className="libv2-insert-menu">
                    <summary>▼</summary>
                    <div>
                      <button onClick={() => insertAs(c, 'source')} disabled={!canInsertRep(c, 'source')}>Insert Source</button>
                      <button onClick={() => insertAs(c, 'edge')} disabled={!canInsertRep(c, 'edge')}>Insert Edge</button>
                      <button onClick={() => insertAs(c, 'bw')} disabled={!canInsertRep(c, 'bw')}>Insert B/W</button>
                      <button onClick={() => { setSelectedId(c.id); setShowDashboard(true); }}>Edit in Dashboard</button>
                    </div>
                  </details>
                </div>
              </div>
            </div>
          );
        })}
        {!visibleCards.length && <div className="libv2-empty">No matching components.</div>}
      </div>

      {showDashboard && (
        <div className="libv2-modal-backdrop" onClick={() => setShowDashboard(false)}>
          <div className="libv2-modal libv2-dashboard-modal" onClick={(e) => e.stopPropagation()}>
            <div className="libv2-dashboard-head">
              <div>
                <strong>Component Library Dashboard</strong>
                <span className="libv2-dashboard-sub">One-screen rename, categorize, approve, retire, and insert.</span>
              </div>
              <div className="libv2-dashboard-actions">
                <button onClick={() => openSavedLegend(preferredLegendTemplate?.id)} disabled={loading} title="Open the saved editable refrigeration legend">Saved Legends ({legendTemplates.length})</button>
                <button onClick={() => void undoLastSavedLibraryChange()} disabled={!libraryHistory.length || loading}>Undo Last Save</button>
                <button onClick={() => void reloadFromDisk()} disabled={loading}>Reload / Discard</button>
                <button className="primary" onClick={() => void saveDirty()} disabled={!dirtyIds.length || loading}>Save All Edits ({dirtyIds.length})</button>
                <button onClick={() => setShowDashboard(false)}>Close</button>
              </div>
            </div>

            <div className="libv2-dashboard-toolbar">
              <input
                type="search"
                placeholder="Search name / part / alias / notes / path…"
                value={builderQuery}
                onChange={(e) => setBuilderQuery(e.target.value)}
              />
              <select value={builderCategory} onChange={(e) => setBuilderCategory(e.target.value)} title="Category">
                <option value="all">All categories</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.label} ({c.count})</option>)}
              </select>
              <select value={builderStatus} onChange={(e) => setBuilderStatus(e.target.value)} title="Status">
                <option value="active">Active / visible</option>
                <option value="all">All statuses</option>
                <option value="blank">Blank status</option>
                <option value="approved">Approved</option>
                <option value="needsReview">Needs Review</option>
                <option value="retired">Retired / hidden</option>
              </select>
              <select value={builderCollection} onChange={(e) => setBuilderCollection(e.target.value)} title="Collection">
                <option value="all">All collections</option>
                {collections.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <label className="libv2-check"><input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} /> retired/reference</label>
              <label className="libv2-check"><input type="checkbox" checked={showNeedsReview} onChange={(e) => setShowNeedsReview(e.target.checked)} /> needs review</label>
              <button onClick={() => addFilesRef.current?.click()}>Add Files</button>
              <button onClick={exportCsv}>Export CSV</button>
              <button onClick={downloadJson}>Download JSON</button>
              <input ref={addFilesRef} hidden type="file" multiple onChange={(e) => void addFilesToLibrary(e.target.files)} />
            </div>

            <div className="libv2-dashboard-stats">
              <span>Total: <strong>{components.length}</strong></span>
              <span>Visible: <strong>{dashboardRows.length}</strong></span>
              <span>Selected: <strong>{visibleSelectedCount}</strong></span>
              <span>Dirty: <strong>{dirtyIds.length}</strong></span>
              <span>Active source: <strong>{showLegacyItems ? 'legacy included' : 'normal'}</strong></span>
            </div>

            {dirtyIds.length > 0 && (
              <div className={`libv2-unsaved-warning ${dirtyIds.length > 20 ? 'danger' : ''}`}>
                <strong>{dirtyIds.length} unsaved edit{dirtyIds.length === 1 ? '' : 's'}.</strong> Nothing has changed on disk until you click <strong>Save All Edits</strong>.
              </div>
            )}

            <div className="libv2-bulkbar">
              <button onClick={selectVisible}>Select Visible ({dashboardRows.length})</button>
              <button onClick={clearSelected}>Clear Selected</button>
              <button onClick={undoStagedBulk} disabled={!bulkUndo}>Undo Staged Bulk</button>
              <button onClick={discardStagedEdits} disabled={!dirtyIds.length}>Discard Unsaved</button>
              <select value={bulkCategory} onChange={(e) => setBulkCategory(e.target.value)} title="Bulk category">
                <option value="">Bulk category…</option>
                {categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
              <input placeholder="Bulk collection…" list="libv2-collections" value={bulkCollection} onChange={(e) => setBulkCollection(e.target.value)} />
              <select value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value)} title="Bulk status">
                <option value="">Bulk status…</option>
                {STATUS_OPTIONS.map((s) => <option key={s.id || 'blank'} value={s.id}>{s.label}</option>)}
              </select>
              <button onClick={applyBulk} disabled={!selectedIds.length}>Apply to Selected</button>
              <button onClick={normalizeSelectedNames} disabled={!selectedIds.length}>Clean Selected Names</button>
              <datalist id="libv2-collections">
                {collections.map((c) => <option key={c} value={c} />)}
              </datalist>
            </div>

            <div className="libv2-dashboard-body">
              <div className="libv2-dashboard-tablewrap">
                <table className="libv2-dashboard-table">
                  <thead>
                    <tr>
                      <th className="sel">Use</th>
                      <SortableHeader label="Preview" sortKey="displayName" active={sortKey} dir={sortDir} onSort={setSortKeyDir} />
                      <SortableHeader label="Display Name" sortKey="displayName" active={sortKey} dir={sortDir} onSort={setSortKeyDir} />
                      <SortableHeader label="Category" sortKey="category" active={sortKey} dir={sortDir} onSort={setSortKeyDir} />
                      <SortableHeader label="Collection" sortKey="collection" active={sortKey} dir={sortDir} onSort={setSortKeyDir} />
                      <SortableHeader label="Part #" sortKey="partNumber" active={sortKey} dir={sortDir} onSort={setSortKeyDir} />
                      <th>Short / Label</th>
                      <SortableHeader label="Status" sortKey="status" active={sortKey} dir={sortDir} onSort={setSortKeyDir} />
                      <th>Aliases</th>
                      <th>Tags</th>
                      <th>Notes</th>
                      <th>Path</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboardRows.map((c) => {
                      const x = asAny(c);
                      const rowDirty = !!edits[c.id] && Object.keys(edits[c.id] || {}).length > 0;
                      const rowSelected = selectedIds.includes(c.id);
                      const retired = isRetired(c);
                      return (
                        <tr key={c.id} className={`${selectedId === c.id ? 'is-active' : ''} ${rowDirty ? 'is-dirty' : ''} ${retired ? 'is-retired' : ''}`} onClick={() => setSelectedId(c.id)}>
                          <td className="sel"><input type="checkbox" checked={rowSelected} onChange={() => toggleSelected(c.id)} onClick={(e) => e.stopPropagation()} /></td>
                          <td className="preview"><CardPreview c={c} rep={rep} small /></td>
                          <td><input value={String(patchValue(c, edits, 'displayName', x.displayName || ''))} onChange={(e) => setEdit(c.id, 'displayName', e.target.value)} /></td>
                          <td>
                            <select value={String(patchValue(c, edits, 'category', x.category || 'custom'))} onChange={(e) => { const primary = e.target.value; setEdit(c.id, 'category', primary); setEdit(c.id, 'categories', Array.from(new Set([primary, ...editedCategories(c, edits)]))); }}>
                              {categories.map((cat) => <option key={cat.id} value={cat.id}>{cat.label}</option>)}
                            </select>
                          </td>
                          <td><input list="libv2-collections" value={String(patchValue(c, edits, 'collection', collectionFor(c)))} onChange={(e) => setEdit(c.id, 'collection', e.target.value)} /></td>
                          <td><input value={String(patchValue(c, edits, 'partNumber', x.partNumber || ''))} onChange={(e) => setEdit(c.id, 'partNumber', e.target.value)} /></td>
                          <td className="two-input">
                            <input placeholder="Short" value={String(patchValue(c, edits, 'shortName', x.shortName || ''))} onChange={(e) => setEdit(c.id, 'shortName', e.target.value)} />
                            <input placeholder="Default label" value={String(patchValue(c, edits, 'defaultLabel', x.defaultLabel || ''))} onChange={(e) => setEdit(c.id, 'defaultLabel', e.target.value)} />
                          </td>
                          <td>
                            <select value={String(patchValue(c, edits, 'status', x.status || ''))} onChange={(e) => setEdit(c.id, 'status', e.target.value)}>
                              {STATUS_OPTIONS.map((s) => <option key={s.id || 'blank'} value={s.id}>{s.label}</option>)}
                            </select>
                          </td>
                          <td><input value={arrayToCsv(patchValue(c, edits, 'aliases', x.aliases || []))} onChange={(e) => setEdit(c.id, 'aliases', e.target.value)} /></td>
                          <td><input value={arrayToCsv(patchValue(c, edits, 'tags', x.tags || []))} onChange={(e) => setEdit(c.id, 'tags', e.target.value)} /></td>
                          <td><textarea value={String(patchValue(c, edits, 'notes', x.notes || ''))} onChange={(e) => setEdit(c.id, 'notes', e.target.value)} /></td>
                          <td className="path" title={pathFor(c)}>{pathFor(c)}</td>
                          <td className="actions">
                            <button onClick={(e) => { e.stopPropagation(); insertAs(c, rep); }} disabled={!canInsert}>Insert</button>
                            <button onClick={(e) => { e.stopPropagation(); void saveSingle(c); }} disabled={!rowDirty}>Save</button>
                            <button onClick={(e) => { e.stopPropagation(); setEdit(c.id, 'status', 'retired'); setEdit(c.id, 'retired', true); }}>Retire</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {!dashboardRows.length && <div className="libv2-dashboard-empty">No rows match the current filters. Try All statuses and retired/reference.</div>}
              </div>

              <aside className="libv2-inspector">
                <h3>Selected Component</h3>
                {selected ? (
                  <>
                    <CardPreview c={selected} rep={rep} />
                    <strong>{displayNameFor(selected)}</strong>
                    <div className="libv2-inspector-line">{asAny(selected).partNumber || asAny(selected).defaultLabel || 'No part number'}</div>
                    <div className="libv2-inspector-line">{categoriesFor(selected).map(niceCategoryLabel).join(' / ')} · {collectionFor(selected) || 'No collection'}</div>
                    <div className="libv2-inspector-line">Default size: {defaultSizeLabel(selected) || 'not set'}</div>
                    <div className="libv2-inspector-variants">
                      <button onClick={() => insertAs(selected, 'source')} disabled={!canInsert || !sourceUrl(selected)}>Insert Source</button>
                      <button onClick={() => insertAs(selected, 'edge')} disabled={!canInsert || !edgeUrl(selected)}>Insert Edge</button>
                      <button onClick={() => insertAs(selected, 'bw')} disabled={!canInsert || !bwUrl(selected)}>Insert B/W</button>
                    </div>
                    <div className="libv2-inspector-variants">
                      <button onClick={() => replaceSourceRef.current?.click()}>Replace Source</button>
                      <button onClick={() => replaceEdgeRef.current?.click()}>Replace Edge</button>
                      <button onClick={() => replaceBwRef.current?.click()}>Replace B/W</button>
                      <input ref={replaceSourceRef} hidden type="file" accept="image/*,.svg" onChange={(e) => void replaceAsset('source', e.target.files?.[0] || null)} />
                      <input ref={replaceEdgeRef} hidden type="file" accept="image/*,.svg" onChange={(e) => void replaceAsset('edge', e.target.files?.[0] || null)} />
                      <input ref={replaceBwRef} hidden type="file" accept="image/*,.svg" onChange={(e) => void replaceAsset('bw', e.target.files?.[0] || null)} />
                    </div>
                    <div className="libv2-inspector-variants">
                      <button onClick={() => void duplicateSelected()}>Duplicate</button>
                      <button onClick={() => { setEdit(selected.id, 'status', 'approved'); setEdit(selected.id, 'retired', false); }}>Approve</button>
                      <button onClick={() => { setEdit(selected.id, 'status', 'needsReview'); setEdit(selected.id, 'retired', false); }}>Needs Review</button>
                      <button onClick={() => { setEdit(selected.id, 'status', 'retired'); setEdit(selected.id, 'retired', true); }}>Retire</button>
                    </div>
                    <div className="libv2-inspector-categories">
                      <strong>Show in categories</strong>
                      {categories.map((cat) => {
                        const current = editedCategories(selected, edits);
                        const checked = current.includes(cat.id);
                        return (
                          <label key={cat.id} className="libv2-check">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                const primary = String(patchValue(selected, edits, 'category', selected.category || 'custom'));
                                const next = e.target.checked
                                  ? Array.from(new Set([primary, ...current, cat.id]))
                                  : current.filter((id) => id !== cat.id || id === primary);
                                setEdit(selected.id, 'categories', next);
                              }}
                            />
                            {cat.label}
                          </label>
                        );
                      })}
                    </div>
                    <textarea
                      className="libv2-inspector-notes"
                      placeholder="Notes…"
                      value={String(patchValue(selected, edits, 'notes', asAny(selected).notes || ''))}
                      onChange={(e) => setEdit(selected.id, 'notes', e.target.value)}
                    />
                  </>
                ) : (
                  <p>No component selected.</p>
                )}
                <hr />
                <h3>Advanced</h3>
                <label className="libv2-check"><input type="checkbox" checked={showLegacyItems} onChange={(e) => { setShowLegacyItems(e.target.checked); void load(e.target.checked); }} /> include legacy items</label>
                <button onClick={() => void runAdvanced('thumbs')}>Rebuild Thumbnails</button>
                <button onClick={() => void runAdvanced('clean')}>Dry-Run Duplicate Cleanup</button>
                <button onClick={() => void runAdvanced('migrate')}>Migrate Legacy Library</button>
              </aside>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  function setSortKeyDir(key: SortKey) {
    if (sortKey === key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    else {
      setSortKey(key);
      setSortDir('asc');
    }
  }
}

function sortComparable(c: LibV2Component, edits: Record<string, Partial<AnyComp>>, key: SortKey): string {
  const x = asAny(c);
  if (key === 'displayName') return String(patchValue(c, edits, 'displayName', x.displayName || ''));
  if (key === 'category') return String(patchValue(c, edits, 'category', x.category || ''));
  if (key === 'collection') return String(patchValue(c, edits, 'collection', collectionFor(c)));
  if (key === 'partNumber') return String(patchValue(c, edits, 'partNumber', x.partNumber || ''));
  if (key === 'status') return String(patchValue(c, edits, 'status', statusFor(c)));
  return '';
}

function SortableHeader({
  label,
  sortKey,
  active,
  dir,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  active: SortKey;
  dir: 'asc' | 'desc';
  onSort: (key: SortKey) => void;
}) {
  return (
    <th>
      <button className="libv2-sort-button" onClick={() => onSort(sortKey)}>
        {label} {active === sortKey ? (dir === 'asc' ? '▲' : '▼') : ''}
      </button>
    </th>
  );
}

function toCsv(rows: unknown[][]): string {
  return rows.map((row) => row.map((cell) => {
    const text = String(cell ?? '');
    if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
    return text;
  }).join(',')).join('\n');
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// S360 WORKSPACE UX V10
