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

interface Props {
  onInsert: (config: SymbolLegendInsertConfig) => void;
  onClose: () => void;
}

function repUrl(c: LibV2Component): string {
  return c.edgeUrl || c.bwUrl || c.thumbnailUrl || c.sourceUrl || (c.edgeFile ? libV2AssetUrl(c.edgeFile) : '');
}

export default function SymbolLegendModal({ onInsert, onClose }: Props) {
  const [components, setComponents] = useState<LibV2Component[]>([]);
  const [savedTemplates, setSavedTemplates] = useState<LegendTemplateEntry[]>([]);
  const [templateId, setTemplateId] = useState(BUILTIN_SYMBOL_LEGEND_TEMPLATES[0].id);
  const [title, setTitle] = useState('Symbol Legend');
  const [rows, setRows] = useState<SymbolLegendRowDraft[]>([]);
  const [search, setSearch] = useState('');
  const [selectedRowIds, setSelectedRowIds] = useState<Set<string>>(new Set());
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
      setSelectedRowIds(new Set());
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
    setSelectedRowIds(new Set());
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

  const toggleRow = (id: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)));
  };

  const updateLabel = (id: string, label: string) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, label } : r)));
  };

  const removeSelected = () => {
    if (!selectedRowIds.size) return;
    setRows((prev) => prev.filter((r) => !selectedRowIds.has(r.id)));
    setSelectedRowIds(new Set());
  };

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
        preferredRep: r.preferredRep || 'edge',
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
    const active = rows.filter((r) => r.enabled && r.label.trim());
    if (!active.length) {
      window.alert('Select at least one legend row.');
      return;
    }
    onInsert({
      title: title.trim() || 'Symbol Legend',
      rows: active.map((r) => ({
        label: r.label.trim(),
        symbolUrl: r.symbolUrl,
        name: r.componentId || r.label,
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
            <select
              value={templateId}
              onChange={(e) => void applyTemplate(e.target.value)}
            >
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
            <button type="button" className="btn btn-sm" onClick={addBlankRow}>Add Row</button>
            <button type="button" className="btn btn-sm" onClick={removeSelected} disabled={!selectedRowIds.size}>Remove Selected</button>
            <button type="button" className="btn btn-sm" onClick={() => void handleSaveTemplate()}>Save As Template</button>
            <button type="button" className="btn btn-sm" onClick={() => void handleDeleteTemplate()}>Delete Template</button>
          </div>
          <table className="op-table sym-legend-table">
            <thead>
              <tr>
                <th style={{ width: 36 }}>Use</th>
                <th style={{ width: 36 }}>Sel</th>
                <th style={{ width: 52 }}>Icon</th>
                <th>Label</th>
                <th style={{ width: 90 }}>Order</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <input type="checkbox" checked={r.enabled} onChange={() => toggleRow(r.id)} />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedRowIds.has(r.id)}
                      onChange={(e) => {
                        setSelectedRowIds((prev) => {
                          const next = new Set(prev);
                          if (e.target.checked) next.add(r.id);
                          else next.delete(r.id);
                          return next;
                        });
                      }}
                    />
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
