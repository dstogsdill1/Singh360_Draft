import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  archiveLibV2Component,
  batchUpdateLibV2Components,
  cleanLibV2PhysicalDuplicates,
  createLibV2Component,
  duplicateLibV2Component,
  getLibV2,
  libV2AssetUrl,
  listLegendTemplates,
  listLibV2History,
  migrateLegacyLibV2,
  rebuildLibV2Thumbnails,
  refreshLibV2,
  replaceLibV2Asset,
  restoreLibV2Component,
  restoreLibV2History,
  updateLibV2Component,
  type LegendTemplateEntry,
  type LibV2Component,
  type LibV2Data,
  type LibV2HistoryEntry,
} from '../api/client';
import type {
  CalloutFamily,
  LibraryComponentInsertMeta,
  QuickAssemblyId,
  SavedAssembly,
  SmartComponentType,
} from '../model/types';
import { SMART_COMPONENT_CHOICES } from '../model/smartComponents';
import { COMPONENT_DRAG_TYPE } from './ComponentLibrary';
import SheetContextMenu from './SheetContextMenu';
import '../styles/libraryV2.css';

interface Props {
  onInsert: (
    name: string,
    url: string,
    label: string | null,
    meta?: LibraryComponentInsertMeta,
  ) => Promise<void> | void;
  canInsert: boolean;
  activePageType?: string;
  onOpenLegendEditor?: () => void;
  onOpenSymbolMapper?: () => void;
  savedAssemblies?: SavedAssembly[];
  onInsertSavedAssembly?: (assembly: SavedAssembly) => void;
  onSaveSelectionAssembly?: () => void;
  onInsertQuickAssembly?: (kind: QuickAssemblyId) => void;
  onInsertSmartComponent?: (kind: SmartComponentType) => void;
  onInsertSingleCallout?: (family: Extract<CalloutFamily, 'round' | 'square'>) => void;
  onCreateCalloutSet?: (family: CalloutFamily) => void;
  onUpdateSavedAssembly?: (id: string, patch: Partial<SavedAssembly>) => void;
  onDuplicateSavedAssembly?: (assembly: SavedAssembly, name?: string) => void;
  onDeleteSavedAssembly?: (id: string) => void;
}

type AnyComponent = LibV2Component & Record<string, unknown>;
type Representation = 'source' | 'edge' | 'bw';
type Workbench = 'builder' | 'manager' | null;
type ManagerView = 'active' | 'needs-review' | 'retired' | 'all';

const CATEGORY_PRESETS = [
  ['controllers', 'Controllers'],
  ['expansion_modules', 'Expansion Modules'],
  ['panels_enclosures', 'Panels / Enclosures'],
  ['electrical_power', 'Electrical / Power'],
  ['power_metering', 'Power Metering'],
  ['network_data', 'Network / Data'],
  ['sensors_transducers', 'Sensors / Transducers'],
  ['alarms_safety', 'Alarms / Safety'],
  ['refrigeration', 'Refrigeration'],
  ['hvac', 'HVAC'],
  ['lighting', 'Lighting'],
  ['symbols_markers', 'Symbols / Markers'],
  ['legends', 'Legends'],
  ['logos', 'Logos'],
  ['reference_pages', 'Reference Pages'],
  ['custom', 'Custom'],
] as const;

const QUICK_ASSEMBLIES: Array<{ id: QuickAssemblyId; label: string }> = [
  { id: 'signage-marker-trio', label: 'Signage Marker Trio' },
  { id: 'signage-legend', label: 'Signage Legend' },
  { id: 'generated-symbol-key', label: 'Generated Symbol Key' },
  { id: 'wicp-annotation-pack', label: 'WICP Annotation Pack' },
];

const RETIRED_STATUSES = new Set(['retired', 'archive', 'archived', 'duplicate', 'junk', 'hidden']);
const NO_LABEL_CATEGORIES = new Set(['logos', 'symbols_markers', 'reference_pages']);

function asAny(component: LibV2Component | null | undefined): AnyComponent {
  return (component || {}) as AnyComponent;
}

function friendlyCategory(category: string): string {
  return CATEGORY_PRESETS.find(([id]) => id === category)?.[1]
    || category.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayName(component: LibV2Component): string {
  const normalized = String(component.displayName || 'Component').replace(/_+/g, ' ').replace(/\s+/g, ' ').trim();
  return /^electrical generator monitor$/i.test(normalized) ? 'Generator Monitor' : normalized || 'Component';
}

function collectionFor(component: LibV2Component): string {
  const value = asAny(component).collection ?? asAny(component).family ?? '';
  return String(value).trim();
}

function categoriesFor(component: LibV2Component): string[] {
  const primary = String(component.category || 'custom');
  const extra = Array.isArray(component.categories) ? component.categories.map(String) : [];
  return Array.from(new Set([primary, ...extra].filter(Boolean)));
}

function isRetired(component: LibV2Component): boolean {
  const status = String(component.status || '').trim().toLowerCase();
  return Boolean(component.retired || asAny(component).hidden || RETIRED_STATUSES.has(status));
}

function needsReview(component: LibV2Component): boolean {
  const status = String(component.status || '').trim().toLowerCase().replace(/[_\s-]+/g, '');
  return Boolean(component.needsReview || status === 'needsreview' || status === 'review');
}

function sourceUrl(component: LibV2Component): string {
  return String(component.sourceUrl || (component.sourceFile ? libV2AssetUrl(component.sourceFile) : ''));
}

function edgeUrl(component: LibV2Component): string {
  return String(component.edgeUrl || (component.edgeFile ? libV2AssetUrl(component.edgeFile) : ''));
}

function bwUrl(component: LibV2Component): string {
  return String(component.bwUrl || (component.bwFile ? libV2AssetUrl(component.bwFile) : ''));
}

function previewUrl(component: LibV2Component): string {
  return String(component.thumbnailUrl || sourceUrl(component) || edgeUrl(component) || bwUrl(component));
}

function representationUrl(component: LibV2Component, representation: Representation): string {
  if (representation === 'edge') return edgeUrl(component) || sourceUrl(component);
  if (representation === 'bw') return bwUrl(component) || edgeUrl(component) || sourceUrl(component);
  return sourceUrl(component) || edgeUrl(component) || bwUrl(component);
}

function defaultRepresentation(component: LibV2Component, pageType?: string): Representation {
  if (pageType && new Set(['canvas', 'hybrid', 'underlay']).has(pageType) && edgeUrl(component)) return 'edge';
  return 'source';
}

function labelFor(component: LibV2Component): string | null {
  if (NO_LABEL_CATEGORIES.has(String(component.category || '').toLowerCase())) return null;
  for (const candidate of [component.defaultLabel, component.partNumber, component.shortName, component.displayName]) {
    const value = String(candidate || '').trim();
    if (value && !/[0-9a-f]{10,}/i.test(value)) return value;
  }
  return null;
}

function insertMeta(component: LibV2Component): LibraryComponentInsertMeta {
  const width = Number(component.defaultWidth || 0);
  const height = Number(component.defaultHeight || 0);
  return {
    category: component.category || undefined,
    defaultWidth: width > 0 ? width : undefined,
    defaultHeight: height > 0 ? height : undefined,
    acronym: String(component.shortName || component.defaultLabel || '').trim() || undefined,
    libraryComponentId: component.id,
    collection: collectionFor(component) || undefined,
    favorite: component.favorite === true,
  };
}

function searchBlob(component: LibV2Component): string {
  return [
    displayName(component),
    component.shortName,
    component.defaultLabel,
    component.partNumber,
    component.category,
    categoriesFor(component).join(' '),
    collectionFor(component),
    (component.aliases || []).join(' '),
    (component.tags || []).join(' '),
    component.notes,
  ].join(' ').toLowerCase();
}

function parseTags(value: string): string[] {
  return Array.from(new Set(value.split(',').map((tag) => tag.trim()).filter(Boolean)));
}

function tagsText(value: unknown): string {
  return Array.isArray(value) ? value.map(String).join(', ') : String(value || '');
}

function numericOrUndefined(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function ComponentPreview({ component, compact = false }: { component: LibV2Component; compact?: boolean }) {
  const url = previewUrl(component);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return (
    <span className={`libv2-component-preview ${compact ? 'compact' : ''} ${!url || failed ? 'missing' : ''}`}>
      {url && !failed ? (
        <img src={url} alt="" loading="lazy" draggable={false} onError={() => setFailed(true)} />
      ) : (
        <span>{displayName(component)}</span>
      )}
    </span>
  );
}

export default function LibraryPanelV2(props: Props) {
  const {
    onInsert,
    canInsert,
    activePageType,
  } = props;
  const [data, setData] = useState<LibV2Data | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [collection, setCollection] = useState('all');
  const [workbench, setWorkbench] = useState<Workbench>(null);
  const [builderInitialId, setBuilderInitialId] = useState('');
  const [insertingId, setInsertingId] = useState('');
  const requestSequence = useRef(0);
  const eventSource = useRef(`library-panel-${Math.random().toString(36).slice(2)}`);

  const loadLibrary = useCallback(async (quiet = false): Promise<LibV2Data | null> => {
    const sequence = ++requestSequence.current;
    if (quiet) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await getLibV2(true, true);
      if (!result.ok || !Array.isArray(result.components)) {
        throw new Error('The server returned an invalid component library payload.');
      }
      if (sequence === requestSequence.current) {
        setData(result);
        setLoadError('');
      }
      return result;
    } catch (error) {
      if (sequence === requestSequence.current) setLoadError(error instanceof Error ? error.message : String(error));
      return null;
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => { void loadLibrary(false); }, [loadLibrary]);
  useEffect(() => {
    const onChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ source?: string }>).detail;
      if (detail?.source !== eventSource.current) void loadLibrary(true);
    };
    window.addEventListener('singh360:library-changed', onChanged);
    return () => window.removeEventListener('singh360:library-changed', onChanged);
  }, [loadLibrary]);

  const notifyChanged = useCallback(async (preferredId?: string): Promise<LibV2Data | null> => {
    const result = await loadLibrary(true);
    window.dispatchEvent(new CustomEvent('singh360:library-changed', {
      detail: { source: eventSource.current, preferredId },
    }));
    return result;
  }, [loadLibrary]);

  const allComponents = data?.components || [];
  const activeComponents = useMemo(
    () => allComponents.filter((component) => !isRetired(component)),
    [allComponents],
  );
  const categories = useMemo(() => {
    const ids = new Set<string>();
    activeComponents.forEach((component) => categoriesFor(component).forEach((id) => ids.add(id)));
    return Array.from(ids).sort((left, right) => friendlyCategory(left).localeCompare(friendlyCategory(right)));
  }, [activeComponents]);
  const collections = useMemo(() => Array.from(new Set(
    activeComponents.map(collectionFor).filter(Boolean),
  )).sort((left, right) => left.localeCompare(right)), [activeComponents]);

  const visibleComponents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (category === 'all' && collection === 'all' && !normalizedQuery) return activeComponents;
    return activeComponents.filter((component) => {
      if (category !== 'all' && !categoriesFor(component).includes(category)) return false;
      if (collection !== 'all' && collectionFor(component) !== collection) return false;
      return !normalizedQuery || searchBlob(component).includes(normalizedQuery);
    });
  }, [activeComponents, category, collection, query]);

  const clearFilters = () => {
    setQuery('');
    setCategory('all');
    setCollection('all');
  };

  const insertComponent = async (component: LibV2Component, representation?: Representation) => {
    if (!canInsert) return;
    const selectedRepresentation = representation || defaultRepresentation(component, activePageType);
    const url = representationUrl(component, selectedRepresentation);
    if (!url) {
      setActionError(`No insertable image is available for ${displayName(component)}.`);
      return;
    }
    setActionError('');
    setInsertingId(component.id);
    try {
      await onInsert(displayName(component), url, labelFor(component), insertMeta(component));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setInsertingId('');
    }
  };

  const startDrag = (event: React.DragEvent, component: LibV2Component) => {
    const representation = defaultRepresentation(component, activePageType);
    const url = representationUrl(component, representation);
    if (!url) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData(COMPONENT_DRAG_TYPE, JSON.stringify({
      name: displayName(component),
      url,
      label: labelFor(component),
      ...insertMeta(component),
    }));
    event.dataTransfer.effectAllowed = 'copy';
  };

  const openBuilder = (componentId = '') => {
    setBuilderInitialId(componentId);
    setWorkbench('builder');
  };

  return (
    <div className="libv2-browser" aria-label="Component Browser">
      <div className="libv2-browser-filters">
        <label className="libv2-visually-hidden" htmlFor="libv2-component-search">Search components</label>
        <input
          id="libv2-component-search"
          type="search"
          placeholder="Search components…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label>
          <span>Category</span>
          <select
            aria-label="Component category"
            value={category}
            onChange={(event) => {
              const next = event.target.value;
              setCategory(next);
              setCollection('all');
              if (next === 'all') setQuery('');
            }}
          >
            <option value="all">All Components</option>
            {categories.map((id) => <option key={id} value={id}>{friendlyCategory(id)}</option>)}
          </select>
        </label>
        {collections.length > 0 ? (
          <label>
            <span>Collection</span>
            <select
              aria-label="Component collection"
              value={collection}
              onChange={(event) => {
                setCollection(event.target.value);
                setCategory('all');
              }}
            >
              <option value="all">All Collections</option>
              {collections.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      <div className="libv2-browser-status" role="status" aria-live="polite">
        {loading && !data ? 'Loading component library…' : null}
        {refreshing ? 'Refreshing component library…' : null}
        {!loading && !refreshing && data && !loadError ? 'Component library ready' : null}
      </div>

      {loadError ? (
        <div className={`libv2-browser-message error ${data ? 'compact' : ''}`} role="alert">
          <strong>{data ? 'Refresh failed; showing the last loaded library.' : 'Component library could not load.'}</strong>
          <span>{loadError}</span>
          <button type="button" onClick={() => void loadLibrary(Boolean(data))} disabled={loading || refreshing}>Retry</button>
        </div>
      ) : null}
      {actionError ? <div className="libv2-browser-message error compact" role="alert">{actionError}</div> : null}

      {!loading && data && activeComponents.length === 0 ? (
        <div className="libv2-browser-message">
          <strong>No active components are available.</strong>
          <span>Retired components remain available in Manage Library.</span>
          <button type="button" onClick={() => void loadLibrary(true)}>Refresh</button>
        </div>
      ) : null}

      {activeComponents.length > 0 && visibleComponents.length === 0 ? (
        <div className="libv2-browser-message">
          <strong>No components match the visible filters.</strong>
          <button type="button" onClick={clearFilters}>Show All Components</button>
          <button type="button" onClick={() => void loadLibrary(true)}>Refresh</button>
        </div>
      ) : null}

      <div className="libv2-browser-grid" aria-busy={loading || refreshing}>
        {visibleComponents.map((component) => {
          const insertable = Boolean(representationUrl(component, defaultRepresentation(component, activePageType)));
          return (
            <button
              key={component.id}
              type="button"
              className="libv2-browser-card"
              title={`Insert ${displayName(component)}`}
              disabled={!canInsert || !insertable || insertingId === component.id}
              draggable={canInsert && insertable}
              onDragStart={(event) => startDrag(event, component)}
              onClick={() => void insertComponent(component)}
            >
              <ComponentPreview component={component} />
              <span className="libv2-browser-card-name">{displayName(component)}</span>
            </button>
          );
        })}
      </div>

      <div className="libv2-browser-footer">
        <button type="button" onClick={() => openBuilder()}>Component Builder</button>
        <button type="button" onClick={() => setWorkbench('manager')}>Manage Library</button>
      </div>

      {workbench === 'builder' && data ? (
        <ComponentBuilderWorkbench
          data={data}
          initialId={builderInitialId}
          props={props}
          onInsert={insertComponent}
          onChanged={notifyChanged}
          onOpenManager={() => setWorkbench('manager')}
          onClose={() => setWorkbench(null)}
        />
      ) : null}
      {workbench === 'manager' && data ? (
        <ManageLibraryWorkbench
          data={data}
          onChanged={notifyChanged}
          onOpenBuilder={(id) => openBuilder(id)}
          onClose={() => setWorkbench(null)}
        />
      ) : null}
    </div>
  );
}

interface BuilderProps {
  data: LibV2Data;
  initialId: string;
  props: Props;
  onInsert: (component: LibV2Component, representation?: Representation) => Promise<void>;
  onChanged: (preferredId?: string) => Promise<LibV2Data | null>;
  onOpenManager: () => void;
  onClose: () => void;
}

function ComponentBuilderWorkbench({
  data,
  initialId,
  props,
  onInsert,
  onChanged,
  onOpenManager,
  onClose,
}: BuilderProps) {
  const components = data.components;
  const firstActive = components.find((component) => !isRetired(component))?.id || components[0]?.id || '';
  const [selectedId, setSelectedId] = useState(initialId === '__new__' ? '' : initialId || firstActive);
  const [query, setQuery] = useState('');
  const [showRetired, setShowRetired] = useState(false);
  const [creating, setCreating] = useState(initialId === '__new__');
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [undoDraft, setUndoDraft] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [representation, setRepresentation] = useState<Representation>('source');
  const [history, setHistory] = useState<LibV2HistoryEntry[]>([]);
  const [historyError, setHistoryError] = useState('');
  const [legends, setLegends] = useState<LegendTemplateEntry[]>([]);
  const [assemblyMenu, setAssemblyMenu] = useState<{ x: number; y: number; id: string } | null>(null);
  const [createFile, setCreateFile] = useState<File | null>(null);
  const [createDraft, setCreateDraft] = useState<Record<string, unknown>>({
    displayName: '', category: 'custom', collection: '', tags: '', defaultWidth: 96, defaultHeight: 72,
  });
  const sourceInput = useRef<HTMLInputElement>(null);
  const edgeInput = useRef<HTMLInputElement>(null);
  const bwInput = useRef<HTMLInputElement>(null);

  const selected = components.find((component) => component.id === selectedId) || null;
  const contextAssembly = (props.savedAssemblies || []).find((assembly) => assembly.id === assemblyMenu?.id) || null;
  const categoryIds = useMemo(() => Array.from(new Set([
    ...CATEGORY_PRESETS.map(([id]) => id),
    ...components.flatMap(categoriesFor),
  ])).sort((left, right) => friendlyCategory(left).localeCompare(friendlyCategory(right))), [components]);
  const collectionNames = useMemo(() => Array.from(new Set(components.map(collectionFor).filter(Boolean))).sort(), [components]);

  useEffect(() => {
    if (!selected) return;
    setDraft({
      displayName: displayName(selected),
      shortName: selected.shortName || '',
      defaultLabel: selected.defaultLabel || '',
      defaultWidth: selected.defaultWidth || '',
      defaultHeight: selected.defaultHeight || '',
      category: selected.category || 'custom',
      collection: collectionFor(selected),
      tags: tagsText(selected.tags),
      notes: selected.notes || '',
      favorite: selected.favorite === true,
    });
    setUndoDraft(null);
    setRepresentation(defaultRepresentation(selected, props.activePageType));
  }, [selectedId, selected?.displayName, asAny(selected).updatedAt]);

  useEffect(() => {
    void Promise.allSettled([listLibV2History(), listLegendTemplates()]).then(([historyResult, legendResult]) => {
      if (historyResult.status === 'fulfilled') setHistory(historyResult.value);
      else setHistoryError(String(historyResult.reason));
      if (legendResult.status === 'fulfilled') setLegends(legendResult.value);
    });
  }, []);

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return components.filter((component) => {
      if (!showRetired && isRetired(component)) return false;
      return !normalized || searchBlob(component).includes(normalized);
    });
  }, [components, query, showRetired]);

  const updateDraft = (patch: Record<string, unknown>) => {
    setUndoDraft((current) => current || structuredClone(draft));
    setDraft((current) => ({ ...current, ...patch }));
  };

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const renameAssembly = (assembly: SavedAssembly) => {
    const name = window.prompt('Rename saved assembly', assembly.name)?.trim();
    if (name && name !== assembly.name) props.onUpdateSavedAssembly?.(assembly.id, { name });
  };

  const moveAssemblyCategory = (assembly: SavedAssembly) => {
    const category = window.prompt(
      'Move saved assembly to category',
      assembly.category || 'Saved Assemblies',
    )?.trim();
    if (category) props.onUpdateSavedAssembly?.(assembly.id, { category });
  };

  const deleteAssembly = (assembly: SavedAssembly) => {
    if (!window.confirm(
      `Delete saved assembly "${assembly.name}"?\n\nPlaced copies on drawing pages will remain unchanged.`,
    )) return;
    props.onDeleteSavedAssembly?.(assembly.id);
  };

  const saveSelected = async () => {
    if (!selected) return;
    await run(async () => {
      await updateLibV2Component(selected.id, {
        displayName: String(draft.displayName || '').trim() || displayName(selected),
        shortName: String(draft.shortName || '').trim(),
        defaultLabel: String(draft.defaultLabel || '').trim(),
        defaultWidth: numericOrUndefined(draft.defaultWidth),
        defaultHeight: numericOrUndefined(draft.defaultHeight),
        category: String(draft.category || 'custom'),
        categories: Array.from(new Set([String(draft.category || 'custom'), ...categoriesFor(selected)])),
        collection: String(draft.collection || '').trim(),
        tags: parseTags(String(draft.tags || '')),
        notes: String(draft.notes || ''),
        favorite: draft.favorite === true,
      });
      await onChanged(selected.id);
      setUndoDraft(null);
    });
  };

  const duplicateSelected = async () => {
    if (!selected) return;
    await run(async () => {
      const result = await duplicateLibV2Component(selected.id);
      await onChanged(result.component.id);
      setSelectedId(result.component.id);
      setShowRetired(true);
    });
  };

  const setRetired = async (retire: boolean) => {
    if (!selected) return;
    if (retire && !window.confirm(`Retire "${displayName(selected)}"?\n\nThe component and its assets remain recoverable.`)) return;
    await run(async () => {
      if (retire) await archiveLibV2Component(selected.id);
      else await restoreLibV2Component(selected.id);
      await onChanged(selected.id);
      setShowRetired(true);
    });
  };

  const replaceAsset = async (target: Representation, file: File | null) => {
    if (!selected || !file) return;
    await run(async () => {
      await replaceLibV2Asset(selected.id, target, file);
      await onChanged(selected.id);
    });
  };

  const createComponent = async () => {
    if (!createFile) {
      setError('Choose an image before creating a component.');
      return;
    }
    await run(async () => {
      const result = await createLibV2Component(createFile, {
        displayName: String(createDraft.displayName || '').trim() || createFile.name.replace(/\.[^.]+$/, ''),
        category: String(createDraft.category || 'custom'),
        categories: [String(createDraft.category || 'custom')],
        collection: String(createDraft.collection || '').trim(),
        tags: parseTags(String(createDraft.tags || '')),
        defaultWidth: numericOrUndefined(createDraft.defaultWidth),
        defaultHeight: numericOrUndefined(createDraft.defaultHeight),
      });
      await onChanged(result.component.id);
      setSelectedId(result.component.id);
      setCreating(false);
      setCreateFile(null);
    });
  };

  const undoLastSave = async () => {
    const latest = history[0];
    if (!latest || !window.confirm(`Restore snapshot ${latest.name}?\n\nThe current manifest is backed up first.`)) return;
    await run(async () => {
      await restoreLibV2History(latest.name);
      await onChanged(selectedId);
      setHistory(await listLibV2History());
    });
  };

  const refreshFromDisk = async () => {
    await run(async () => {
      await refreshLibV2();
      await onChanged(selectedId);
    });
  };

  return (
    <div className="libv2-workbench-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="libv2-workbench" role="dialog" aria-modal="true" aria-label="Component Builder" onMouseDown={(event) => event.stopPropagation()}>
        <header className="libv2-workbench-header">
          <div><strong>Component Builder</strong><span>Create and edit reusable components without changing placed copies.</span></div>
          <div>
            <button type="button" onClick={onOpenManager}>Manage Library</button>
            <button type="button" onClick={onClose}>Close</button>
          </div>
        </header>
        {error ? <div className="libv2-workbench-alert" role="alert">{error}</div> : null}
        <div className="libv2-builder-layout">
          <aside className="libv2-builder-picker">
            <button type="button" className="primary" onClick={() => setCreating(true)}>Create Component</button>
            <input type="search" placeholder="Search existing components…" value={query} onChange={(event) => setQuery(event.target.value)} />
            <label className="libv2-inline-check"><input type="checkbox" checked={showRetired} onChange={(event) => setShowRetired(event.target.checked)} /> Include retired</label>
            <div className="libv2-builder-picker-list">
              {visible.map((component) => (
                <button key={component.id} type="button" className={selectedId === component.id && !creating ? 'active' : ''} onClick={() => { setCreating(false); setSelectedId(component.id); }}>
                  <ComponentPreview component={component} compact />
                  <span><strong>{displayName(component)}</strong><small>{friendlyCategory(component.category)}{isRetired(component) ? ' · Retired' : ''}</small></span>
                </button>
              ))}
            </div>
          </aside>

          <main className="libv2-builder-editor">
            {creating ? (
              <div className="libv2-builder-form">
                <h2>Create Component</h2>
                <label>Image<input type="file" accept="image/*,.svg,.pdf" onChange={(event) => setCreateFile(event.target.files?.[0] || null)} /></label>
                <label>Name<input value={String(createDraft.displayName || '')} onChange={(event) => setCreateDraft((current) => ({ ...current, displayName: event.target.value }))} /></label>
                <div className="libv2-form-columns">
                  <label>Category<select value={String(createDraft.category)} onChange={(event) => setCreateDraft((current) => ({ ...current, category: event.target.value }))}>{categoryIds.map((id) => <option key={id} value={id}>{friendlyCategory(id)}</option>)}</select></label>
                  <label>Collection<input list="libv2-builder-collections" value={String(createDraft.collection || '')} onChange={(event) => setCreateDraft((current) => ({ ...current, collection: event.target.value }))} /></label>
                </div>
                <label>Tags<input placeholder="comma, separated" value={String(createDraft.tags || '')} onChange={(event) => setCreateDraft((current) => ({ ...current, tags: event.target.value }))} /></label>
                <div className="libv2-form-columns">
                  <label>Default width<input type="number" min="1" value={String(createDraft.defaultWidth || '')} onChange={(event) => setCreateDraft((current) => ({ ...current, defaultWidth: event.target.value }))} /></label>
                  <label>Default height<input type="number" min="1" value={String(createDraft.defaultHeight || '')} onChange={(event) => setCreateDraft((current) => ({ ...current, defaultHeight: event.target.value }))} /></label>
                </div>
                <div className="libv2-form-actions"><button type="button" onClick={() => setCreating(false)}>Cancel</button><button type="button" className="primary" disabled={busy} onClick={() => void createComponent()}>Create Component</button></div>
              </div>
            ) : selected ? (
              <div className="libv2-builder-form">
                <div className="libv2-builder-selected-head">
                  <ComponentPreview component={selected} />
                  <div><span>Stable ID</span><code>{selected.id}</code><span>{isRetired(selected) ? 'Retired — hidden from Component Browser' : 'Active in Component Browser'}</span></div>
                </div>
                <label>Component name<input aria-label="Component name" value={String(draft.displayName || '')} onChange={(event) => updateDraft({ displayName: event.target.value })} /></label>
                <div className="libv2-form-columns">
                  <label>Short name<input value={String(draft.shortName || '')} onChange={(event) => updateDraft({ shortName: event.target.value })} /></label>
                  <label>Default label<input value={String(draft.defaultLabel || '')} onChange={(event) => updateDraft({ defaultLabel: event.target.value })} /></label>
                </div>
                <div className="libv2-form-columns">
                  <label>Default width<input type="number" min="1" value={String(draft.defaultWidth || '')} onChange={(event) => updateDraft({ defaultWidth: event.target.value })} /></label>
                  <label>Default height<input type="number" min="1" value={String(draft.defaultHeight || '')} onChange={(event) => updateDraft({ defaultHeight: event.target.value })} /></label>
                </div>
                <div className="libv2-form-columns">
                  <label>Category<select value={String(draft.category || 'custom')} onChange={(event) => updateDraft({ category: event.target.value })}>{categoryIds.map((id) => <option key={id} value={id}>{friendlyCategory(id)}</option>)}</select></label>
                  <label>Collection<input list="libv2-builder-collections" value={String(draft.collection || '')} onChange={(event) => updateDraft({ collection: event.target.value })} /></label>
                </div>
                <label>Tags<input value={String(draft.tags || '')} onChange={(event) => updateDraft({ tags: event.target.value })} /></label>
                <label>Notes<textarea value={String(draft.notes || '')} onChange={(event) => updateDraft({ notes: event.target.value })} /></label>
                <label className="libv2-inline-check"><input type="checkbox" checked={draft.favorite === true} onChange={(event) => updateDraft({ favorite: event.target.checked })} /> Favorite</label>
                <datalist id="libv2-builder-collections">{collectionNames.map((name) => <option key={name} value={name} />)}</datalist>
                <div className="libv2-form-actions wrap">
                  <button type="button" disabled={!undoDraft || busy} onClick={() => { if (undoDraft) setDraft(undoDraft); setUndoDraft(null); }}>Undo Unsaved</button>
                  <button type="button" disabled={busy} onClick={() => void duplicateSelected()}>Duplicate</button>
                  <button type="button" disabled={busy} onClick={() => sourceInput.current?.click()}>Replace Image</button>
                  {isRetired(selected) ? <button type="button" disabled={busy} onClick={() => void setRetired(false)}>Restore</button> : <button type="button" className="danger" disabled={busy} onClick={() => void setRetired(true)}>Retire</button>}
                  <button type="button" className="primary" disabled={busy} onClick={() => void saveSelected()}>Save Component</button>
                </div>
                <input ref={sourceInput} hidden type="file" accept="image/*,.svg,.pdf" onChange={(event) => { void replaceAsset('source', event.target.files?.[0] || null); event.target.value = ''; }} />
                <input ref={edgeInput} hidden type="file" accept="image/*,.svg" onChange={(event) => { void replaceAsset('edge', event.target.files?.[0] || null); event.target.value = ''; }} />
                <input ref={bwInput} hidden type="file" accept="image/*,.svg" onChange={(event) => { void replaceAsset('bw', event.target.files?.[0] || null); event.target.value = ''; }} />
              </div>
            ) : <div className="libv2-workbench-empty">Select a component or create a new one.</div>}

            <details className="libv2-advanced-workbench">
              <summary>Advanced insertion and library tools</summary>
              {selected ? (
                <section>
                  <h3>Representations</h3>
                  <div className="libv2-segmented">{(['source', 'edge', 'bw'] as Representation[]).map((value) => <button key={value} type="button" className={representation === value ? 'active' : ''} onClick={() => setRepresentation(value)}>{value === 'source' ? 'Source' : value === 'edge' ? 'Edge' : 'B/W'}</button>)}</div>
                  <div className="libv2-form-actions wrap"><button type="button" disabled={!props.canInsert} onClick={() => void onInsert(selected, representation)}>Insert Selected</button><button type="button" onClick={() => edgeInput.current?.click()}>Replace Edge</button><button type="button" onClick={() => bwInput.current?.click()}>Replace B/W</button></div>
                </section>
              ) : null}
              <section><h3>Smart Components</h3><div className="libv2-tool-grid">{SMART_COMPONENT_CHOICES.map((choice) => <button key={choice.kind} type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onInsertSmartComponent?.(choice.kind); }}>{choice.label}</button>)}</div></section>
              <section><h3>Quick Insert</h3><div className="libv2-tool-grid">{QUICK_ASSEMBLIES.map((assembly) => <button key={assembly.id} type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onInsertQuickAssembly?.(assembly.id); }}>{assembly.label}</button>)}</div></section>
              <section>
                <h3>Callouts and Assemblies</h3>
                <div className="libv2-tool-grid">
                  <button type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onInsertSingleCallout?.('round'); }}>Round Callout</button>
                  <button type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onCreateCalloutSet?.('round'); }}>Generate Round Callouts</button>
                  <button type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onInsertSingleCallout?.('square'); }}>Square Callout</button>
                  <button type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onCreateCalloutSet?.('square'); }}>Generate Square Callouts</button>
                  <button type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onCreateCalloutSet?.('block'); }}>Callout Block / List</button>
                  <button type="button" disabled={!props.canInsert} onClick={() => { onClose(); props.onSaveSelectionAssembly?.(); }}>Save Selection as Assembly</button>
                </div>
                {(props.savedAssemblies || []).length ? (
                  <div className="libv2-saved-assembly-grid" aria-label="Saved assemblies">
                    {(props.savedAssemblies || []).map((assembly) => (
                      <button
                        key={assembly.id}
                        type="button"
                        className="libv2-saved-assembly-card"
                        disabled={!props.canInsert}
                        onClick={() => { onClose(); props.onInsertSavedAssembly?.(assembly); }}
                        onContextMenu={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          setAssemblyMenu({ x: event.clientX, y: event.clientY, id: assembly.id });
                        }}
                      >
                        <strong>{assembly.name}</strong>
                        <span>{assembly.category || 'Saved Assemblies'}{assembly.favorite ? ' · Favorite' : ''}</span>
                        <small>Click to insert · right-click to manage</small>
                      </button>
                    ))}
                  </div>
                ) : <small>No saved assemblies in this project.</small>}
              </section>
              <section><h3>Specialized Tools</h3><div className="libv2-form-actions wrap"><button type="button" onClick={() => { onClose(); props.onOpenSymbolMapper?.(); }}>Symbol Mapper</button><button type="button" onClick={() => { onClose(); props.onOpenLegendEditor?.(); }}>Saved Legends ({legends.length})</button><button type="button" disabled={busy} onClick={() => void refreshFromDisk()}>Refresh from Disk</button><button type="button" disabled={busy} onClick={() => void run(async () => { await rebuildLibV2Thumbnails(); await onChanged(selectedId); })}>Rebuild Previews</button><button type="button" disabled={!history.length || busy} onClick={() => void undoLastSave()}>Undo Last Save</button></div>{historyError ? <small>{historyError}</small> : null}</section>
            </details>
          </main>
        </div>
        {assemblyMenu && contextAssembly ? (
          <SheetContextMenu
            x={assemblyMenu.x}
            y={assemblyMenu.y}
            onClose={() => setAssemblyMenu(null)}
            actions={[
              { label: 'Edit', disabled: !props.canInsert, onClick: () => { onClose(); props.onInsertSavedAssembly?.(contextAssembly); }, hint: 'Insert an editable copy on the active page' },
              { label: 'Rename', onClick: () => renameAssembly(contextAssembly) },
              { label: 'Duplicate', onClick: () => props.onDuplicateSavedAssembly?.(contextAssembly) },
              { label: 'Delete', onClick: () => deleteAssembly(contextAssembly), hint: 'Placed copies remain unchanged' },
              { label: 'Move to Category', onClick: () => moveAssemblyCategory(contextAssembly) },
              { label: contextAssembly.favorite ? 'Remove from Favorites' : 'Add to Favorites', onClick: () => props.onUpdateSavedAssembly?.(contextAssembly.id, { favorite: !contextAssembly.favorite }) },
              { label: 'Save as Assembly', onClick: () => props.onDuplicateSavedAssembly?.(contextAssembly, `${contextAssembly.name} Copy`) },
            ]}
          />
        ) : null}
      </section>
    </div>
  );
}

interface ManagerProps {
  data: LibV2Data;
  onChanged: (preferredId?: string) => Promise<LibV2Data | null>;
  onOpenBuilder: (id: string) => void;
  onClose: () => void;
}

function ManageLibraryWorkbench({ data, onChanged, onOpenBuilder, onClose }: ManagerProps) {
  const components = data.components;
  const [view, setView] = useState<ManagerView>('active');
  const [query, setQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, Record<string, unknown>>>({});
  const [undoEdits, setUndoEdits] = useState<Record<string, Record<string, unknown>> | null>(null);
  const [bulkCategory, setBulkCategory] = useState('');
  const [bulkCollection, setBulkCollection] = useState('');
  const [bulkAction, setBulkAction] = useState('');
  const [history, setHistory] = useState<LibV2HistoryEntry[]>([]);
  const [historyError, setHistoryError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const categoryIds = useMemo(() => Array.from(new Set([
    ...CATEGORY_PRESETS.map(([id]) => id),
    ...components.flatMap(categoriesFor),
  ])).sort((left, right) => friendlyCategory(left).localeCompare(friendlyCategory(right))), [components]);

  useEffect(() => {
    void listLibV2History().then(setHistory).catch((caught) => setHistoryError(String(caught)));
  }, []);

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return components.filter((component) => {
      if (view === 'active' && isRetired(component)) return false;
      if (view === 'retired' && !isRetired(component)) return false;
      if (view === 'needs-review' && !needsReview(component)) return false;
      return !normalized || searchBlob(component).includes(normalized);
    });
  }, [components, query, view]);

  const setEdit = (id: string, patch: Record<string, unknown>) => {
    setEdits((current) => ({ ...current, [id]: { ...(current[id] || {}), ...patch } }));
  };

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try { await action(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(false); }
  };

  const toggleSelected = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const selectVisible = () => setSelectedIds(visible.map((component) => component.id));

  const applyBulk = () => {
    if (!selectedIds.length) return;
    if (!bulkCategory && !bulkCollection && !bulkAction) {
      setError('Choose a bulk category, collection, or action.');
      return;
    }
    setUndoEdits(structuredClone(edits));
    const selected = new Set(selectedIds);
    setEdits((current) => {
      const next = { ...current };
      components.forEach((component) => {
        if (!selected.has(component.id)) return;
        const patch = { ...(next[component.id] || {}) };
        if (bulkCategory) Object.assign(patch, { category: bulkCategory, categories: [bulkCategory] });
        if (bulkCollection) patch.collection = bulkCollection;
        if (bulkAction === 'approve' || bulkAction === 'restore') Object.assign(patch, { status: 'approved', retired: false, needsReview: false });
        if (bulkAction === 'needs-review') Object.assign(patch, { status: 'needsReview', retired: false, needsReview: true });
        if (bulkAction === 'retire') Object.assign(patch, { status: 'retired', retired: true, needsReview: false });
        if (bulkAction === 'favorite') patch.favorite = true;
        if (bulkAction === 'unfavorite') patch.favorite = false;
        next[component.id] = patch;
      });
      return next;
    });
  };

  const saveEdits = async () => {
    const updates = Object.entries(edits).filter(([, patch]) => Object.keys(patch).length).map(([id, rawPatch]) => {
      const patch = { ...rawPatch };
      if (Object.prototype.hasOwnProperty.call(patch, 'tags')) patch.tags = parseTags(String(patch.tags || ''));
      return { id, patch };
    });
    if (!updates.length) return;
    await run(async () => {
      await batchUpdateLibV2Components(updates, `visual-review-save-${updates.length}`);
      setEdits({});
      setUndoEdits(null);
      setSelectedIds([]);
      await onChanged();
      setHistory(await listLibV2History());
    });
  };

  const restoreSnapshot = async (entry: LibV2HistoryEntry) => {
    if (!window.confirm(`Restore ${entry.name}?\n\nThe current manifest will be snapshotted first.`)) return;
    await run(async () => {
      await restoreLibV2History(entry.name);
      await onChanged();
      setHistory(await listLibV2History());
    });
  };

  const advanced = async (action: 'refresh' | 'previews' | 'duplicates' | 'migrate') => {
    await run(async () => {
      if (action === 'refresh') await refreshLibV2();
      if (action === 'previews') await rebuildLibV2Thumbnails();
      if (action === 'duplicates') {
        const result = await cleanLibV2PhysicalDuplicates(true);
        window.alert(`Dry run: ${result.duplicateGroups || 0} duplicate groups, ${result.duplicates || 0} duplicate files.`);
      }
      if (action === 'migrate') {
        const preview = await migrateLegacyLibV2(true);
        window.alert(`Dry run only: ${preview.willCopy || 0} files would be copied; ${preview.willSkipDuplicates || 0} duplicates would be skipped.`);
      }
      await onChanged();
    });
  };

  return (
    <div className="libv2-workbench-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="libv2-workbench manager" role="dialog" aria-modal="true" aria-label="Manage Library" onMouseDown={(event) => event.stopPropagation()}>
        <header className="libv2-workbench-header">
          <div><strong>Manage Library</strong><span>Visual review, bulk actions, retired recovery, needs-review triage, and history snapshots.</span></div>
          <div><button type="button" onClick={() => onOpenBuilder('__new__')}>Component Builder</button><button type="button" onClick={onClose}>Close</button></div>
        </header>
        {error ? <div className="libv2-workbench-alert" role="alert">{error}</div> : null}
        <div className="libv2-manager-toolbar">
          <input type="search" placeholder="Search review cards…" value={query} onChange={(event) => setQuery(event.target.value)} />
          <select aria-label="Library review view" value={view} onChange={(event) => setView(event.target.value as ManagerView)}><option value="active">Active</option><option value="needs-review">Needs Review</option><option value="retired">Retired</option><option value="all">All Components</option></select>
          <button type="button" onClick={selectVisible}>Select Visible</button>
          <button type="button" onClick={() => setSelectedIds([])}>Clear Selection</button>
          <span>{selectedIds.length} selected</span>
        </div>
        <div className="libv2-manager-bulk">
          <select value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)}><option value="">Bulk category…</option>{categoryIds.map((id) => <option key={id} value={id}>{friendlyCategory(id)}</option>)}</select>
          <input placeholder="Bulk collection…" value={bulkCollection} onChange={(event) => setBulkCollection(event.target.value)} />
          <select value={bulkAction} onChange={(event) => setBulkAction(event.target.value)}><option value="">Bulk action…</option><option value="approve">Approve</option><option value="needs-review">Needs Review</option><option value="retire">Retire</option><option value="restore">Restore</option><option value="favorite">Favorite</option><option value="unfavorite">Unfavorite</option></select>
          <button type="button" disabled={!selectedIds.length} onClick={applyBulk}>Stage Bulk Action</button>
          <button type="button" disabled={!undoEdits} onClick={() => { if (undoEdits) setEdits(undoEdits); setUndoEdits(null); }}>Undo Staged</button>
          <button type="button" className="primary" disabled={!Object.keys(edits).length || busy} onClick={() => void saveEdits()}>Save Changes ({Object.keys(edits).length})</button>
        </div>
        <div className="libv2-manager-layout">
          <div className="libv2-review-grid">
            {visible.map((component) => {
              const patch = edits[component.id] || {};
              const selected = selectedIds.includes(component.id);
              return (
                <article key={component.id} className={`libv2-review-card ${selected ? 'selected' : ''} ${isRetired(component) ? 'retired' : ''}`}>
                  <label className="libv2-review-select"><input type="checkbox" checked={selected} onChange={() => toggleSelected(component.id)} /> Select</label>
                  <ComponentPreview component={component} />
                  <label>Name<input value={String(patch.displayName ?? displayName(component))} onChange={(event) => setEdit(component.id, { displayName: event.target.value })} /></label>
                  <label>Category<select value={String(patch.category ?? component.category ?? 'custom')} onChange={(event) => setEdit(component.id, { category: event.target.value, categories: [event.target.value] })}>{categoryIds.map((id) => <option key={id} value={id}>{friendlyCategory(id)}</option>)}</select></label>
                  <label>Collection<input value={String(patch.collection ?? collectionFor(component))} onChange={(event) => setEdit(component.id, { collection: event.target.value })} /></label>
                  <label>Tags<input value={String(patch.tags ?? tagsText(component.tags))} onChange={(event) => setEdit(component.id, { tags: event.target.value })} /></label>
                  <div className="libv2-review-card-foot"><span>{isRetired(component) ? 'Retired' : needsReview(component) ? 'Needs Review' : 'Active'}</span><button type="button" onClick={() => onOpenBuilder(component.id)}>Edit in Builder</button></div>
                </article>
              );
            })}
            {!visible.length ? <div className="libv2-workbench-empty">No review cards match this view.</div> : null}
          </div>
          <aside className="libv2-history-panel">
            <h2>History Snapshots</h2>
            <p>Every save and retire action creates a recoverable manifest snapshot.</p>
            {historyError ? <div className="libv2-workbench-alert">{historyError}</div> : null}
            <div>{history.slice(0, 20).map((entry) => <button key={entry.name} type="button" disabled={busy} onClick={() => void restoreSnapshot(entry)}><strong>{entry.savedAt}</strong><span>{entry.reason}</span><small>{entry.componentCount} records</small></button>)}</div>
            {!history.length && !historyError ? <p>No snapshots yet.</p> : null}
            <details className="libv2-manager-advanced"><summary>Advanced maintenance</summary><button type="button" onClick={() => void advanced('refresh')}>Refresh from Disk</button><button type="button" onClick={() => void advanced('previews')}>Rebuild Previews</button><button type="button" onClick={() => void advanced('duplicates')}>Duplicate Cleanup Dry Run</button><button type="button" onClick={() => void advanced('migrate')}>Legacy Migration Dry Run</button></details>
          </aside>
        </div>
      </section>
    </div>
  );
}
