import { useEffect, useMemo, useState } from 'react';
import {
  deleteLegendTemplate,
  getLibV2,
  libV2AssetUrl,
  saveLegendTemplate,
  listLegendTemplates,
  type LibV2Component,
  type LegendTemplateEntry,
} from '../api/client';
import {
  BUILTIN_SYMBOL_LEGEND_TEMPLATES,
  hydrateTemplateRows,
  rowsFromTemplatePayload,
  type SymbolLegendInsertConfig,
  type SymbolLegendRowDraft,
} from '../model/symbolLegendPresets';
import { SYMBOL_SIZE_SMALL } from '../model/symbolSizing';

interface Props {
  onInsert: (config: SymbolLegendInsertConfig) => void;
  onClose: () => void;
}

function repUrl(c: LibV2Component): string {
  return c.bwUrl || c.edgeUrl || c.thumbnailUrl || c.sourceUrl || (c.bwFile ? libV2AssetUrl(c.bwFile) : '');
}

export default function SymbolLegendModal({ onInsert, onClose }: Props) {
  const [components, setComponents] = useState<LibV2Component[]>([]);
  const [savedTemplates, setSavedTemplates] = useState<LegendTemplateEntry[]>([]);
  const [templateId, setTemplateId] = useState(BUILTIN_SYMBOL_LEGEND_TEMPLATES[0].id);
  const [title, setTitle] = useState('SYMBOL LEGEND');
  const [rows, setRows] = useState<SymbolLegendRowDraft[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const [lib, saved] = await Promise.all([getLibV2(false), listLegendTemplates()]);
        setComponents(lib.components || []);
        setSavedTemplates(saved);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const templateOptions = useMemo(
    () => [
      ...BUILTIN_SYMBOL_LEGEND_TEMPLATES.map((t) => ({ id: t.id, name: t.name, builtin: true })),
      ...savedTemplates.map((t) => ({ id: t.id, name: `${t.name} (saved)`, builtin: false })),
    ],
    [savedTemplates],
  );

  const applyTemplate = async (id: string) => {
    setTemplateId(id);
    const builtin = BUILTIN_SYMBOL_LEGEND_TEMPLATES.find((t) => t.id === id);
    if (builtin) {
      setTitle(builtin.title);
      setRows(hydrateTemplateRows(builtin, components));
      return;
    }
    const saved = savedTemplates.find((t) => t.id === id);
    if (!saved) return;
    const res = await fetch(`/api/lib/legend-templates/${id}`);
    if (!res.ok) return;
    const data = await res.json();
    const hydrated = rowsFromTemplatePayload(data.template || {}, components);
    setTitle(hydrated.title);
    setRows(hydrated.rows);
  };

  useEffect(() => {
    if (!loading && components.length) void applyTemplate(templateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, components.length]);

  const searchHits = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];
    return components
      .filter((c) => {
        const hay = [c.displayName, c.defaultLabel, c.partNumber, c.id, ...(c.aliases || [])].join(' ').toLowerCase();
        return hay.includes(q);
      })
      .slice(0, 12);
  }, [components, search]);

  const activeRows = useMemo(() => rows.filter((r) => r.enabled && r.label.trim()), [rows]);

  const toggleRow = (id: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)));
  };

  const updateLabel = (id: string, label: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, label } : r)));
  };

  const selectAll = () => setRows((prev) => prev.map((r) => ({ ...r, enabled: true })));
  const clearAll = () => setRows((prev) => prev.map((r) => ({ ...r, enabled: false })));

  const moveRow = (id: string, dir: -1 | 1) => {
    setRows((prev) => {
      const idx = prev.findIndex((r) => r.id === id);
      if (idx < 0) return prev;
      const next = idx + dir;
      if (next < 0 || next >= prev.length) return prev;
      const copy = [...prev];
      const [item] = copy.splice(idx, 1);
      copy.splice(next, 0, item);
      return copy;
    });
  };

  const addBlankRow = () => {
    const id = `custom_${Date.now()}`;
    setRows((prev) => [...prev, { id, enabled: true, label: 'New symbol row' }]);
  };

  const addComponentRow = (c: LibV2Component) => {
    const id = `comp_${c.id}_${Date.now()}`;
    setRows((prev) => [
      ...prev,
      {
        id,
        enabled: true,
        label: c.displayName,
        componentId: c.id,
        symbolUrl: repUrl(c),
        category: c.category,
        defaultWidth: c.defaultWidth,
        defaultHeight: c.defaultHeight,
      },
    ]);
    setSearch('');
  };

  const handleSaveTemplate = async () => {
    const name = window.prompt('Template name:', title || 'Symbol Legend');
    if (!name?.trim()) return;
    await saveLegendTemplate({
      name: name.trim(),
      category: templateId,
      title,
      rows: rows.map((r) => ({
        id: r.id,
        enabled: r.enabled,
        label: r.label,
        acronym: r.acronym,
        componentId: r.componentId,
        symbolUrl: r.symbolUrl,
        searchTerms: r.searchTerms,
        preferredRep: r.preferredRep || 'bw',
        category: r.category,
        defaultWidth: r.defaultWidth,
        defaultHeight: r.defaultHeight,
      })),
    });
    const saved = await listLegendTemplates();
    setSavedTemplates(saved);
    window.alert('Legend template saved.');
  };

  const handleDeleteTemplate = async () => {
    const builtin = BUILTIN_SYMBOL_LEGEND_TEMPLATES.some((t) => t.id === templateId);
    if (builtin) {
      window.alert('Built-in templates cannot be deleted.');
      return;
    }
    if (!window.confirm('Delete this saved legend template?')) return;
    await deleteLegendTemplate(templateId);
    const saved = await listLegendTemplates();
    setSavedTemplates(saved);
    setTemplateId(BUILTIN_SYMBOL_LEGEND_TEMPLATES[0].id);
    void applyTemplate(BUILTIN_SYMBOL_LEGEND_TEMPLATES[0].id);
  };

  const handleInsert = () => {
    if (!activeRows.length) {
      window.alert('Select at least one legend row (Use checkbox).');
      return;
    }
    onInsert({
      title: title.trim() || 'SYMBOL LEGEND',
      rows: activeRows.map((r) => ({
        label: r.label.trim(),
        symbolUrl: r.symbolUrl,
        name: r.componentId || r.label,
        acronym: r.acronym,
        iconSize: SYMBOL_SIZE_SMALL,
        category: r.category,
        defaultWidth: r.defaultWidth,
        defaultHeight: r.defaultHeight,
      })),
    });
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Insert Symbol Legend</h2>
          <button className="modal-x" onClick={onClose} title="Close">×</button>
        </div>
        <div className="modal-body">
          <div className="field">
            <label>Legend template</label>
            <select value={templateId} onChange={(e) => void applyTemplate(e.target.value)}>
              {templateOptions.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Legend title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="field">
            <label>Search component library</label>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search symbols / devices…"
            />
          </div>
          {searchHits.length > 0 && (
            <div className="sym-legend-search-hits">
              {searchHits.map((c) => (
                <button key={c.id} type="button" className="btn btn-sm" onClick={() => addComponentRow(c)}>
                  + {c.displayName}
                </button>
              ))}
            </div>
          )}
          <div className="sym-legend-toolbar">
            <button type="button" className="btn btn-sm" onClick={selectAll}>Select All</button>
            <button type="button" className="btn btn-sm" onClick={clearAll}>Clear All</button>
            <button type="button" className="btn btn-sm" onClick={addBlankRow}>Add Row</button>
            <button type="button" className="btn btn-sm" onClick={() => void handleSaveTemplate()}>Save Current Legend as Template</button>
            <button type="button" className="btn btn-sm" onClick={() => void handleDeleteTemplate()}>Delete Template</button>
          </div>
          <div className="sym-legend-preview">
            <div className="sym-legend-preview-title">{title || 'SYMBOL LEGEND'}</div>
            {activeRows.length ? activeRows.map((r) => (
              <div key={r.id} className="sym-legend-preview-row">
                {r.symbolUrl ? (
                  <img src={r.symbolUrl} alt="" className="sym-legend-preview-icon" />
                ) : (
                  <span className="sym-legend-preview-icon sym-legend-missing">□</span>
                )}
                <span>{r.label}</span>
              </div>
            )) : (
              <p className="cw-note">No rows selected — check Use for symbols to include.</p>
            )}
          </div>
          <table className="op-table sym-legend-table">
            <thead>
              <tr>
                <th style={{ width: 40 }}>Use</th>
                <th style={{ width: 52 }}>Icon</th>
                <th>Label</th>
                <th style={{ width: 90 }}>Order</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={r.enabled ? '' : 'sym-legend-row-off'}>
                  <td>
                    <input type="checkbox" checked={r.enabled} onChange={() => toggleRow(r.id)} title="Include in legend" />
                  </td>
                  <td>
                    {r.symbolUrl ? (
                      <img src={r.symbolUrl} alt="" className="sym-legend-icon" />
                    ) : (
                      <span className="sym-legend-missing">—</span>
                    )}
                  </td>
                  <td>
                    <input
                      className="sym-legend-label-input"
                      value={r.label}
                      onChange={(e) => updateLabel(r.id, e.target.value)}
                    />
                  </td>
                  <td>
                    <button type="button" className="btn btn-sm" onClick={() => moveRow(r.id, -1)}>↑</button>
                    <button type="button" className="btn btn-sm" onClick={() => moveRow(r.id, 1)}>↓</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && <p className="cw-note">Loading component library…</p>}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleInsert}>Insert Legend</button>
        </div>
      </div>
    </div>
  );
}
