import { useEffect, useMemo, useState, type ChangeEvent, type DragEvent, type MouseEvent } from 'react';
import {
  getSymbolMapperTemplate,
  saveSymbolMapperTemplate,
  type SymbolMapperTemplateSymbol,
} from '../api/client';
import type { SymbolLegendInsertConfig } from '../model/types';
import {
  SYMBOL_PALETTE,
  paletteChoiceById,
  symbolMarkerStyle,
  symbolTemplateKey,
  type SymbolPaletteChoice,
  type SymbolPalettePattern,
} from '../model/symbolPalette';

interface Props {
  onInsert: (config: SymbolLegendInsertConfig) => void;
  onClose: () => void;
  initialTemplateId?: string;
}

type LegendShape = 'circle' | 'square' | 'none';

type BuilderRow = {
  id: string;
  key: string;
  code: string;
  glyph: string;
  label: string;
  enabled: boolean;
  highlighted: boolean;
  shape: LegendShape;
  paletteId: string;
  color: string;
  color2: string;
  pattern: SymbolPalettePattern;
};

function inferredShape(code: string, saved?: string): LegendShape {
  if (saved === 'square' || saved === 'circle' || saved === 'none') return saved;
  return code.trim().toUpperCase() === 'CC' ? 'square' : 'circle';
}

function rowFromTemplate(item: SymbolMapperTemplateSymbol, index: number): BuilderRow {
  const choice = paletteChoiceById(item.paletteId, index);
  return {
    id: `legend_${index}_${item.key || symbolTemplateKey(item.code, item.label)}`,
    key: item.key || symbolTemplateKey(item.code, item.label),
    code: item.code,
    glyph: item.glyph || (item.shape === 'none' ? '$' : item.code),
    label: item.label,
    enabled: item.enabled !== false,
    highlighted: true,
    shape: inferredShape(item.code, item.shape),
    paletteId: item.paletteId || choice.id,
    color: item.color || choice.color,
    color2: item.color2 || choice.color2,
    pattern: (item.pattern || choice.pattern) as SymbolPalettePattern,
  };
}

function Marker({ row, size = 34 }: { row: BuilderRow; size?: number }) {
  const visual = row.highlighted
    ? symbolMarkerStyle(row, 0.24, size >= 38 ? 3 : 2)
    : { border: `${size >= 38 ? 3 : 2}px solid transparent`, background: '#fff', boxSizing: 'border-box' as const };
  return (
    <span
      className="symbol-legend-built-marker"
      style={{ ...visual, width: size, height: size }}
      aria-hidden="true"
    >
      <i className={`symbol-legend-source-outline ${row.shape}`}>
        {row.glyph || row.code || '?'}
      </i>
    </span>
  );
}

export default function SymbolLegendModal({ onInsert, onClose }: Props) {
  const [title, setTitle] = useState('SYMBOLS KEY:');
  const [rows, setRows] = useState<BuilderRow[]>([]);
  const [activeId, setActiveId] = useState('');
  const [dragId, setDragId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('Loading Singh360 Standard…');
  const [error, setError] = useState('');
  const [columns, setColumns] = useState<1 | 2>(1);
  const [markerSize, setMarkerSize] = useState(34);
  const [frame, setFrame] = useState(false);

  useEffect(() => {
    let alive = true;
    void (async () => {
      setLoading(true);
      setError('');
      try {
        const template = await getSymbolMapperTemplate();
        if (!alive) return;
        const next = template.symbols.map(rowFromTemplate);
        setRows(next);
        setActiveId(next[0]?.id ?? '');
        setStatus(`${template.name || 'Singh360 Standard'} loaded · ${next.length} symbols`);
      } catch (err) {
        if (!alive) return;
        setRows([]);
        setStatus('The Singh360 symbol standard could not be loaded.');
        setError(String(err));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const active = rows.find((row) => row.id === activeId) ?? rows[0];
  const included = useMemo(() => rows.filter((row) => row.enabled && row.code.trim() && row.label.trim()), [rows]);

  const updateRow = (id: string, patch: Partial<BuilderRow>) => {
    setRows((current) => current.map((row) => row.id === id ? {
      ...row,
      ...patch,
      key: patch.code !== undefined || patch.label !== undefined
        ? symbolTemplateKey(patch.code ?? row.code, patch.label ?? row.label)
        : row.key,
    } : row));
  };

  const applyPalette = (choice: SymbolPaletteChoice) => {
    if (!active) return;
    updateRow(active.id, {
      paletteId: choice.id,
      color: choice.color,
      color2: choice.color2,
      pattern: choice.pattern,
    });
  };

  const addRow = () => {
    const index = rows.length;
    const choice = paletteChoiceById(undefined, index);
    const id = `legend_custom_${Date.now()}`;
    const row: BuilderRow = {
      id,
      key: symbolTemplateKey('NEW', 'NEW SYMBOL'),
      code: 'NEW',
      glyph: 'NEW',
      label: 'NEW SYMBOL',
      enabled: true,
      highlighted: true,
      shape: 'circle',
      paletteId: choice.id,
      color: choice.color,
      color2: choice.color2,
      pattern: choice.pattern,
    };
    setRows((current) => [...current, row]);
    setActiveId(id);
  };

  const reorder = (draggedId: string, targetId: string) => {
    if (draggedId === targetId) return;
    setRows((current) => {
      const from = current.findIndex((row) => row.id === draggedId);
      const to = current.findIndex((row) => row.id === targetId);
      if (from < 0 || to < 0) return current;
      const next = [...current];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  };

  const saveStandard = async () => {
    if (!rows.length) return;
    setSaving(true);
    setError('');
    try {
      const payload: SymbolMapperTemplateSymbol[] = rows
        .filter((row) => row.code.trim() && row.label.trim())
        .map((row) => ({
          key: symbolTemplateKey(row.code, row.label),
          code: row.code.trim().toUpperCase(),
          glyph: row.glyph.trim() || row.code.trim().toUpperCase(),
          label: row.label.trim(),
          enabled: row.enabled,
          paletteId: row.paletteId,
          color: row.color,
          color2: row.color2,
          pattern: row.pattern,
          shape: row.shape,
        }));
      const saved = await saveSymbolMapperTemplate(payload);
      setStatus(`Singh360 Standard updated · ${saved.total} symbols · ${saved.added} added`);
      setRows((current) => current.map((row, index) => {
        const match = saved.template.symbols.find((item) => item.key === symbolTemplateKey(row.code, row.label));
        return match ? rowFromTemplate(match, index) : row;
      }));
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const insert = () => {
    if (!included.length) {
      setError('Select at least one complete symbol row.');
      return;
    }
    onInsert({
      title: title.trim() || 'SYMBOLS KEY:',
      columns,
      markerSize,
      frame,
      highlighted: true,
      rows: included.map((row) => ({
        code: row.code.trim().toUpperCase(),
        glyph: row.glyph.trim() || row.code.trim().toUpperCase(),
        label: row.label.trim(),
        name: row.key,
        acronym: row.code.trim().toUpperCase(),
        shape: row.shape,
        color: row.color,
        color2: row.color2,
        pattern: row.pattern,
        highlighted: row.highlighted,
      })),
    });
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal symbol-legend-builder-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>Build / Insert Symbol Legend</h2>
            <p className="symbol-legend-builder-sub">Uses the same Singh360 Standard, colors, and split markers as Symbol Mapper.</p>
          </div>
          <button className="modal-x" onClick={onClose} title="Close">×</button>
        </div>

        <div className="symbol-legend-builder-toolbar">
          <label>
            Legend title
            <input value={title} onChange={(event: ChangeEvent<HTMLInputElement>) => setTitle(event.target.value)} />
          </label>
          <button className="btn" onClick={() => setRows((current) => current.map((row) => ({ ...row, enabled: true })))}>Select all</button>
          <button className="btn" onClick={() => setRows((current) => current.map((row) => ({ ...row, enabled: false })))}>Select none</button>
          <button className="btn" onClick={() => setRows((current) => current.map((row) => ({ ...row, highlighted: true })))}>Highlight all</button>
          <button className="btn" onClick={() => setRows((current) => current.map((row) => ({ ...row, highlighted: false })))}>No highlights</button>
          <div className="symbol-legend-builder-layout-options">
            <label>
              Columns
              <select value={columns} onChange={(event) => setColumns(Number(event.target.value) === 2 ? 2 : 1)}>
                <option value={1}>1</option>
                <option value={2}>2</option>
              </select>
            </label>
            <label>
              Marker size
              <select value={markerSize} onChange={(event) => setMarkerSize(Number(event.target.value))}>
                <option value={26}>Small</option>
                <option value={34}>Standard</option>
                <option value={42}>Large</option>
              </select>
            </label>
            <label><input type="checkbox" checked={frame} onChange={(event) => setFrame(event.target.checked)} /> Frame</label>
          </div>
          <button className="btn" onClick={addRow}>+ Add symbol</button>
          <button className="btn" disabled={saving || loading} onClick={() => void saveStandard()}>{saving ? 'Saving…' : 'Save / update standard'}</button>
        </div>

        <div className="symbol-legend-builder-status">{status}</div>
        {error && <div className="symbol-mapper-error">{error}</div>}

        <div className="symbol-legend-builder-body">
          <section className="symbol-legend-builder-list">
            <div className="symbol-legend-builder-list-head">
              <strong>Symbols</strong>
              <span>Drag rows to reorder.</span>
            </div>
            <div className="symbol-legend-builder-scroll">
              {rows.map((row) => (
                <div
                  key={row.id}
                  className={`symbol-legend-builder-row ${row.id === active?.id ? 'active' : ''} ${row.enabled ? '' : 'disabled'}`}
                  draggable
                  onDragStart={(event: DragEvent<HTMLDivElement>) => {
                    event.dataTransfer.effectAllowed = 'move';
                    event.dataTransfer.setData('text/plain', row.id);
                    setDragId(row.id);
                  }}
                  onDragOver={(event) => {
                    if (dragId) event.preventDefault();
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    if (dragId) reorder(dragId, row.id);
                    setDragId(null);
                  }}
                  onDragEnd={() => setDragId(null)}
                  onClick={() => setActiveId(row.id)}
                >
                  <span className="symbol-legend-drag">⋮⋮</span>
                  <label className="symbol-legend-use" onClick={(event: MouseEvent<HTMLLabelElement>) => event.stopPropagation()}>
                    <input type="checkbox" checked={row.enabled} onChange={() => updateRow(row.id, { enabled: !row.enabled })} />
                  </label>
                  <Marker row={row} size={34} />
                  <div className="symbol-legend-row-fields" onClick={(event) => event.stopPropagation()}>
                    <input
                      className="symbol-legend-code-input"
                      value={row.code}
                      aria-label="Symbol code"
                      onFocus={() => setActiveId(row.id)}
                      onChange={(event) => {
                        const code = event.target.value.toUpperCase().slice(0, 16);
                        updateRow(row.id, { code, glyph: !row.glyph || row.glyph === row.code ? code : row.glyph });
                      }}
                    />
                    <input
                      value={row.label}
                      aria-label="Symbol description"
                      onFocus={() => setActiveId(row.id)}
                      onChange={(event) => updateRow(row.id, { label: event.target.value })}
                    />
                  </div>
                  <label className="symbol-legend-highlight" onClick={(event: MouseEvent<HTMLLabelElement>) => event.stopPropagation()}>
                    <input type="checkbox" checked={row.highlighted} onChange={() => updateRow(row.id, { highlighted: !row.highlighted })} />
                    color
                  </label>
                  <button
                    className="symbol-legend-remove"
                    title="Remove this row from this legend"
                    onClick={(event) => {
                      event.stopPropagation();
                      setRows((current) => current.filter((item) => item.id !== row.id));
                    }}
                  >×</button>
                </div>
              ))}
              {!rows.length && <div className="symbol-legend-empty">No standard symbols are available. Add a symbol to begin.</div>}
            </div>
          </section>

          <section className="symbol-legend-builder-editor">
            <div className="symbol-legend-color-panel">
              <div>
                <h3>Color for {active?.code || 'selected symbol'}</h3>
                <p>These are the same colors used by Symbol Mapper.</p>
              </div>
              <div className="sm-palette-grid symbol-legend-palette-grid">
                {SYMBOL_PALETTE.map((choice) => (
                  <button
                    key={choice.id}
                    className={active?.paletteId === choice.id ? 'active' : ''}
                    disabled={!active}
                    onClick={() => applyPalette(choice)}
                    title={choice.label}
                  >
                    <span style={symbolMarkerStyle(choice, 1, 1)} />
                    <small>{choice.label}</small>
                  </button>
                ))}
              </div>
              {active && (
                <div className="symbol-legend-shape-row">
                  <strong>Marker shape</strong>
                  <button className={active.shape === 'circle' ? 'active' : ''} onClick={() => updateRow(active.id, { shape: 'circle' })}>Circle</button>
                  <button className={active.shape === 'square' ? 'active' : ''} onClick={() => updateRow(active.id, { shape: 'square' })}>Square</button>
                  <button className={active.shape === 'none' ? 'active' : ''} onClick={() => updateRow(active.id, { shape: 'none' })}>No source outline</button>
                  <label><input type="checkbox" checked={active.highlighted} onChange={() => updateRow(active.id, { highlighted: !active.highlighted })} /> Highlight this row</label>
                </div>
              )}
            </div>

            <div className="symbol-legend-live-preview">
              <div className={`symbol-legend-preview-card ${columns === 2 ? 'two-columns' : ''}`} style={{ border: frame ? '1px solid #111' : 'none' }}>
                <div className="symbol-legend-preview-heading">{title || 'SYMBOLS KEY:'}</div>
                {included.map((row) => (
                  <div className="symbol-legend-preview-built-row" key={row.id}>
                    <Marker row={row} size={markerSize} />
                    <span>{row.label}</span>
                  </div>
                ))}
                {!included.length && <div className="symbol-legend-empty">Select symbols to preview the legend.</div>}
              </div>
            </div>
          </section>
        </div>

        <div className="modal-foot">
          <span className="symbol-legend-builder-count">{included.length} symbol{included.length === 1 ? '' : 's'} selected</span>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={insert}>Insert legend</button>
        </div>
      </div>
    </div>
  );
}
