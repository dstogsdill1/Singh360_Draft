import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent as ReactClipboardEvent,
  type CSSProperties,
} from 'react';
import type {
  CalloutEntry,
  CalloutSetConfig,
} from '../model/types';
import {
  calloutFamilyLabel,
  cloneCalloutEntries,
  emptyCalloutEntry,
  normalizeCalloutEntries,
  normalizeCalloutSetConfig,
  numericCalloutEntries,
  parseCalloutClipboardText,
} from '../model/callouts';

type CalloutApplyAction = 'update' | 'insert';
type DraftSource = 'manual' | 'excel' | 'numeric';

interface Props {
  initialConfig: CalloutSetConfig;
  mode: 'insert' | 'edit';
  projectId: string;
  pageId: string;
  onApply: (config: CalloutSetConfig, action: CalloutApplyAction) => void;
  onCancel: () => void;
}

interface StoredCalloutDraft {
  version: 2;
  baseSignature: string;
  config: CalloutSetConfig;
  rows: CalloutEntry[];
  manualDraft: CalloutEntry[];
  excelDraft: CalloutEntry[];
  numericDraft: CalloutEntry[];
  previousDraft: CalloutEntry[] | null;
  history: CalloutEntry[][];
  source: DraftSource;
  rangeStart: number;
  rangeEnd: number;
  rangePrefix: string;
  plainText: string;
}

interface LoadedDraft {
  config: CalloutSetConfig;
  rows: CalloutEntry[];
  manualDraft: CalloutEntry[];
  excelDraft: CalloutEntry[];
  numericDraft: CalloutEntry[];
  previousDraft: CalloutEntry[] | null;
  history: CalloutEntry[][];
  source: DraftSource;
  rangeStart: number;
  rangeEnd: number;
  rangePrefix: string;
  plainText: string;
}

const DRAFT_VERSION = 2;
const MAX_HISTORY = 30;

function draftEntries(value: unknown): CalloutEntry[] {
  return Array.isArray(value) && value.length ? normalizeCalloutEntries(value) : [];
}

function rowsEqual(left: CalloutEntry[], right: CalloutEntry[]): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function isBlankPreview(rows: CalloutEntry[]): boolean {
  return rows.length === 1
    && !rows[0].callout
    && !rows[0].label
    && !rows[0].description;
}

function storageKey(
  projectId: string,
  pageId: string,
  mode: Props['mode'],
  config: CalloutSetConfig,
): string {
  const identity = mode === 'edit' ? config.setName : config.family;
  return [
    'singh360-callout-editor-draft-v2',
    encodeURIComponent(projectId || 'project'),
    encodeURIComponent(pageId || 'page'),
    mode,
    encodeURIComponent(identity || config.family),
  ].join(':');
}

function loadDraft(
  key: string,
  baseSignature: string,
  fallback: CalloutSetConfig,
): LoadedDraft | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || 'null') as Partial<StoredCalloutDraft> | null;
    if (
      !parsed
      || parsed.version !== DRAFT_VERSION
      || parsed.baseSignature !== baseSignature
      || !Array.isArray(parsed.rows)
    ) return null;
    const source: DraftSource = parsed.source === 'excel' || parsed.source === 'numeric'
      ? parsed.source
      : 'manual';
    return {
      config: normalizeCalloutSetConfig(parsed.config, fallback.family),
      rows: normalizeCalloutEntries(parsed.rows),
      manualDraft: draftEntries(parsed.manualDraft),
      excelDraft: draftEntries(parsed.excelDraft),
      numericDraft: draftEntries(parsed.numericDraft),
      previousDraft: Array.isArray(parsed.previousDraft)
        ? normalizeCalloutEntries(parsed.previousDraft)
        : null,
      history: Array.isArray(parsed.history)
        ? parsed.history.filter(Array.isArray).slice(-MAX_HISTORY).map(normalizeCalloutEntries)
        : [],
      source,
      rangeStart: Number.isFinite(Number(parsed.rangeStart)) ? Number(parsed.rangeStart) : 1,
      rangeEnd: Number.isFinite(Number(parsed.rangeEnd)) ? Number(parsed.rangeEnd) : 10,
      rangePrefix: typeof parsed.rangePrefix === 'string' ? parsed.rangePrefix : '',
      plainText: typeof parsed.plainText === 'string' ? parsed.plainText : '',
    };
  } catch {
    return null;
  }
}

function PreviewMarker({
  entry,
  shape,
}: {
  entry: CalloutEntry;
  shape: CalloutSetConfig['markerShape'];
}) {
  if (shape === 'none') {
    return entry.callout
      ? <span className="callout-preview-marker none">{entry.callout}</span>
      : null;
  }
  return <span className={`callout-preview-marker ${shape}`}>{entry.callout}</span>;
}

export default function CalloutEditorModal({
  initialConfig,
  mode,
  projectId,
  pageId,
  onApply,
  onCancel,
}: Props) {
  const normalizedInitial = useMemo(
    () => normalizeCalloutSetConfig(initialConfig, initialConfig.family),
    [initialConfig],
  );
  const baseSignature = useMemo(
    () => JSON.stringify(normalizedInitial),
    [normalizedInitial],
  );
  const draftKey = useMemo(
    () => storageKey(projectId, pageId, mode, normalizedInitial),
    [mode, normalizedInitial, pageId, projectId],
  );
  const restored = useMemo(
    () => loadDraft(draftKey, baseSignature, normalizedInitial),
    [baseSignature, draftKey, normalizedInitial],
  );
  const initialRows = restored?.rows || normalizedInitial.entries;

  const [config, setConfig] = useState<CalloutSetConfig>(
    () => restored?.config || normalizedInitial,
  );
  const [rows, setRows] = useState<CalloutEntry[]>(() => cloneCalloutEntries(initialRows));
  const [manualDraft, setManualDraft] = useState<CalloutEntry[]>(
    () => cloneCalloutEntries(restored?.manualDraft.length ? restored.manualDraft : initialRows),
  );
  const [excelDraft, setExcelDraft] = useState<CalloutEntry[]>(
    () => cloneCalloutEntries(restored?.excelDraft || []),
  );
  const [numericDraft, setNumericDraft] = useState<CalloutEntry[]>(
    () => cloneCalloutEntries(restored?.numericDraft || []),
  );
  const [previousDraft, setPreviousDraft] = useState<CalloutEntry[] | null>(
    () => restored?.previousDraft ? cloneCalloutEntries(restored.previousDraft) : null,
  );
  const [history, setHistory] = useState<CalloutEntry[][]>(
    () => (restored?.history || []).map(cloneCalloutEntries),
  );
  const [source, setSource] = useState<DraftSource>(restored?.source || 'manual');
  const [rangeStart, setRangeStart] = useState(restored?.rangeStart ?? 1);
  const [rangeEnd, setRangeEnd] = useState(restored?.rangeEnd ?? 10);
  const [rangePrefix, setRangePrefix] = useState(restored?.rangePrefix || '');
  const [plainText, setPlainText] = useState(restored?.plainText || '');
  const [showPlainText, setShowPlainText] = useState(Boolean(restored?.plainText));
  const [status, setStatus] = useState(restored ? 'Restored the autosaved draft for this page.' : '');
  const editingCellRef = useRef(false);

  const familyLabel = calloutFamilyLabel(config.family);

  const currentPayload = (): StoredCalloutDraft => ({
    version: DRAFT_VERSION,
    baseSignature,
    config: normalizeCalloutSetConfig({ ...config, entries: rows }, config.family),
    rows: cloneCalloutEntries(rows),
    manualDraft: cloneCalloutEntries(manualDraft),
    excelDraft: cloneCalloutEntries(excelDraft),
    numericDraft: cloneCalloutEntries(numericDraft),
    previousDraft: previousDraft ? cloneCalloutEntries(previousDraft) : null,
    history: history.slice(-MAX_HISTORY).map(cloneCalloutEntries),
    source,
    rangeStart,
    rangeEnd,
    rangePrefix,
    plainText,
  });

  const persistDraft = () => {
    try {
      localStorage.setItem(draftKey, JSON.stringify(currentPayload()));
    } catch {
      // The dialog remains fully usable when browser storage is unavailable.
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(persistDraft, 180);
    return () => window.clearTimeout(timer);
    // currentPayload intentionally represents all open-dialog draft state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    config,
    draftKey,
    excelDraft,
    history,
    manualDraft,
    numericDraft,
    plainText,
    previousDraft,
    rangeEnd,
    rangePrefix,
    rangeStart,
    rows,
    source,
  ]);

  const patch = (values: Partial<CalloutSetConfig>) => {
    setConfig((current) => normalizeCalloutSetConfig(
      { ...current, ...values, entries: rows },
      current.family,
    ));
  };

  const rememberRows = (snapshot = rows) => {
    const copy = cloneCalloutEntries(snapshot);
    setPreviousDraft(copy);
    setHistory((current) => [...current, copy].slice(-MAX_HISTORY));
    editingCellRef.current = false;
  };

  const applyRows = (nextRows: CalloutEntry[], draftSource?: DraftSource) => {
    const normalized = normalizeCalloutEntries(nextRows);
    if (rowsEqual(rows, normalized)) return;
    rememberRows();
    setRows(cloneCalloutEntries(normalized));
    if (draftSource === 'manual') setManualDraft(cloneCalloutEntries(normalized));
    if (draftSource === 'excel') setExcelDraft(cloneCalloutEntries(normalized));
    if (draftSource === 'numeric') setNumericDraft(cloneCalloutEntries(normalized));
  };

  const startCellEdit = () => {
    if (editingCellRef.current) return;
    editingCellRef.current = true;
    rememberRows();
    editingCellRef.current = true;
  };

  const updateCell = (
    index: number,
    key: 'callout' | 'label' | 'description',
    value: string,
  ) => {
    const next = rows.map((entry, rowIndex) => rowIndex === index
      ? {
        ...entry,
        [key]: value,
        text: key === 'description' ? value : entry.description,
      }
      : entry);
    setRows(next);
    setManualDraft(cloneCalloutEntries(next));
  };

  const finishCellEdit = () => {
    editingCellRef.current = false;
  };

  const undo = () => {
    const prior = history[history.length - 1];
    if (!prior) return;
    setPreviousDraft(cloneCalloutEntries(rows));
    setRows(cloneCalloutEntries(prior));
    setHistory((current) => current.slice(0, -1));
    setStatus('Restored the previous grid state.');
  };

  const restoreRows = (draft: CalloutEntry[], label: string) => {
    if (!draft.length) return;
    applyRows(draft);
    setStatus(`Restored ${label}.`);
  };

  const ingestPastedText = (value: string, origin: string) => {
    const parsed = parseCalloutClipboardText(value);
    if (!parsed.length) {
      setStatus('No tab/newline clipboard rows were found.');
      return;
    }
    setExcelDraft(cloneCalloutEntries(parsed));
    const next = isBlankPreview(rows) ? parsed : [...rows, ...parsed];
    applyRows(next);
    setSource('excel');
    setStatus(`${origin}: ${parsed.length} row${parsed.length === 1 ? '' : 's'} added to the editable preview.`);
  };

  const handleGridPaste = (event: ReactClipboardEvent<HTMLElement>) => {
    const value = event.clipboardData.getData('text/plain');
    if (!value) return;
    event.preventDefault();
    event.stopPropagation();
    event.nativeEvent.stopImmediatePropagation();
    ingestPastedText(value, 'Excel paste');
  };

  const pasteFromClipboard = async () => {
    try {
      const value = await navigator.clipboard.readText();
      ingestPastedText(value, 'Clipboard');
    } catch {
      setStatus('Clipboard access was blocked. Use Ctrl+V in the grid or Paste Plain Text.');
    }
  };

  const appendNumeric = () => {
    const generated = numericCalloutEntries(rangeStart, rangeEnd, rangePrefix);
    setNumericDraft(cloneCalloutEntries(generated));
    const next = isBlankPreview(rows) ? generated : [...rows, ...generated];
    applyRows(next);
    setStatus(`${generated.length} numeric row${generated.length === 1 ? '' : 's'} appended.`);
  };

  const replaceWithNumeric = () => {
    const generated = numericCalloutEntries(rangeStart, rangeEnd, rangePrefix);
    setNumericDraft(cloneCalloutEntries(generated));
    if (!window.confirm(
      `Replace all ${rows.length} current row${rows.length === 1 ? '' : 's'} with ${generated.length} generated row${generated.length === 1 ? '' : 's'}?`,
    )) {
      setStatus('Numeric replacement canceled. Current rows were not changed.');
      return;
    }
    applyRows(generated);
    setStatus(`${generated.length} numeric row${generated.length === 1 ? '' : 's'} replaced the preview.`);
  };

  const removeRow = (index: number) => {
    const next = rows.filter((_, rowIndex) => rowIndex !== index);
    applyRows(next.length ? next : [emptyCalloutEntry()], 'manual');
  };

  const moveRow = (index: number, direction: -1 | 1) => {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= rows.length) return;
    const next = cloneCalloutEntries(rows);
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    applyRows(next, 'manual');
  };

  const clearSavedDraft = () => {
    try {
      localStorage.removeItem(draftKey);
    } catch {
      // Ignore unavailable browser storage.
    }
  };

  const apply = (action: CalloutApplyAction) => {
    if (!rows.some((entry) => entry.callout || entry.label || entry.description)) {
      setStatus('Add at least one Callout, Label, or Description before inserting.');
      return;
    }
    const next = normalizeCalloutSetConfig({ ...config, entries: rows }, config.family);
    clearSavedDraft();
    onApply(next, action);
  };

  const cancel = () => {
    persistDraft();
    onCancel();
  };

  const previewStyle = {
    '--callout-preview-fill': config.fill,
    '--callout-preview-stroke': config.stroke,
    '--callout-preview-text': config.textColor,
    '--callout-preview-gap': `${Math.max(2, config.spacing / 2)}px`,
  } as CSSProperties;

  return (
    <div className="modal-backdrop" onClick={cancel}>
      <form
        className="modal callout-editor-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${mode === 'edit' ? 'Edit' : 'Create'} ${familyLabel}`}
        data-clipboard-editor="true"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          apply(mode === 'edit' ? 'update' : 'insert');
        }}
      >
        <div className="modal-head">
          <div>
            <h2>{mode === 'edit' ? 'Edit' : 'Create'} {familyLabel}</h2>
            <p>Paste Excel rows, edit every cell, preview the result, then update the selection or insert a new copy.</p>
          </div>
          <button type="button" className="modal-x" aria-label="Close callout editor" onClick={cancel}>×</button>
        </div>

        <div className="modal-body callout-editor-form">
          <fieldset>
            <legend>Identity and title</legend>
            <div className="smart-component-grid">
              <label>
                Set name
                <input
                  aria-label="Callout set name"
                  value={config.setName}
                  onChange={(event) => patch({ setName: event.target.value })}
                />
              </label>
              <label>
                Editable list title
                <input
                  aria-label="Callout list title"
                  value={config.title}
                  onChange={(event) => patch({ title: event.target.value })}
                  placeholder="CALLOUTS"
                />
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend>Row source</legend>
            <div className="callout-source-tabs" role="tablist" aria-label="Callout row source">
              {([
                ['manual', 'Manual'],
                ['excel', 'Excel Paste'],
                ['numeric', 'Numeric Range'],
              ] as Array<[DraftSource, string]>).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={source === value}
                  className={source === value ? 'active' : undefined}
                  onClick={() => setSource(value)}
                >
                  {label}
                </button>
              ))}
            </div>

            {source === 'manual' ? (
              <p className="callout-source-note">Edit the grid directly. Add, remove, and reorder controls never affect the saved Excel or numeric drafts.</p>
            ) : null}

            {source === 'excel' ? (
              <div className="callout-paste-panel">
                <div className="callout-tool-row">
                  <button type="button" onClick={() => void pasteFromClipboard()}>Paste from Clipboard</button>
                  <button type="button" onClick={() => setShowPlainText((current) => !current)}>Paste Plain Text</button>
                  <button type="button" disabled={!excelDraft.length} onClick={() => restoreRows(excelDraft, 'Excel paste draft')}>
                    Restore Excel Draft ({excelDraft.length})
                  </button>
                </div>
                {showPlainText ? (
                  <div className="callout-plain-paste">
                    <label>
                      Plain text or tab-separated rows
                      <textarea
                        aria-label="Plain text callout data"
                        rows={5}
                        value={plainText}
                        onChange={(event) => setPlainText(event.target.value)}
                        placeholder={'MDP\\nRack A\\nOAU-01\\n\\n1\\tMDP\\tMain distribution panel'}
                      />
                    </label>
                    <button type="button" onClick={() => ingestPastedText(plainText, 'Plain text')}>
                      Add Plain Text Rows
                    </button>
                  </div>
                ) : null}
                <p className="callout-source-note">
                  Ctrl+V works directly in any grid cell. One column becomes Label; two columns become Callout + Label; three or more preserve Callout + Label + Description.
                </p>
              </div>
            ) : null}

            {source === 'numeric' ? (
              <div className="callout-range-row">
                <label>
                  Start
                  <input
                    aria-label="Callout range start"
                    type="number"
                    min={-9999}
                    max={9999}
                    value={rangeStart}
                    onChange={(event) => setRangeStart(Number(event.target.value))}
                  />
                </label>
                <label>
                  End
                  <input
                    aria-label="Callout range end"
                    type="number"
                    min={-9999}
                    max={9999}
                    value={rangeEnd}
                    onChange={(event) => setRangeEnd(Number(event.target.value))}
                  />
                </label>
                <label>
                  Prefix
                  <input
                    aria-label="Callout range prefix"
                    value={rangePrefix}
                    onChange={(event) => setRangePrefix(event.target.value)}
                    placeholder="C-"
                  />
                </label>
                <div className="callout-range-actions">
                  <button type="button" onClick={appendNumeric}>Append to Current Rows</button>
                  <button type="button" className="danger" onClick={replaceWithNumeric}>Replace Rows</button>
                  <button type="button" disabled={!numericDraft.length} onClick={() => restoreRows(numericDraft, 'numeric draft')}>
                    Restore Numeric Draft ({numericDraft.length})
                  </button>
                </div>
              </div>
            ) : null}

            <div className="callout-history-row">
              <button type="button" disabled={!history.length} onClick={undo}>Undo</button>
              <button
                type="button"
                disabled={!previousDraft}
                onClick={() => previousDraft && restoreRows(previousDraft, 'previous draft')}
              >
                Restore Previous Draft
              </button>
              <button type="button" disabled={!manualDraft.length} onClick={() => restoreRows(manualDraft, 'manual draft')}>
                Restore Manual Draft ({manualDraft.length})
              </button>
              <span>{rows.length} editable row{rows.length === 1 ? '' : 's'}</span>
            </div>
          </fieldset>

          <fieldset>
            <legend>Editable preview</legend>
            <div
              className="callout-row-grid-wrap"
              data-clipboard-editor="true"
              onPaste={handleGridPaste}
            >
              <table className="callout-row-grid" aria-label="Editable callout row grid">
                <thead>
                  <tr>
                    <th aria-label="Row controls" />
                    <th>Callout</th>
                    <th>Label</th>
                    <th>Description</th>
                    <th aria-label="Remove row" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((entry, index) => (
                    <tr key={index}>
                      <td className="callout-row-order">
                        <button type="button" aria-label={`Move row ${index + 1} up`} disabled={index === 0} onClick={() => moveRow(index, -1)}>↑</button>
                        <button type="button" aria-label={`Move row ${index + 1} down`} disabled={index === rows.length - 1} onClick={() => moveRow(index, 1)}>↓</button>
                      </td>
                      <td>
                        <input
                          aria-label={`Row ${index + 1} Callout`}
                          value={entry.callout}
                          onFocus={startCellEdit}
                          onBlur={finishCellEdit}
                          onChange={(event) => updateCell(index, 'callout', event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Row ${index + 1} Label`}
                          value={entry.label}
                          onFocus={startCellEdit}
                          onBlur={finishCellEdit}
                          onChange={(event) => updateCell(index, 'label', event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Row ${index + 1} Description`}
                          value={entry.description}
                          onFocus={startCellEdit}
                          onBlur={finishCellEdit}
                          onChange={(event) => updateCell(index, 'description', event.target.value)}
                        />
                      </td>
                      <td>
                        <button type="button" className="callout-remove-row" aria-label={`Remove row ${index + 1}`} onClick={() => removeRow(index)}>×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              type="button"
              className="callout-add-row"
              onClick={() => applyRows([...rows, emptyCalloutEntry()], 'manual')}
            >
              Add Row
            </button>
          </fieldset>

          <fieldset>
            <legend>Appearance and layout</legend>
            <div className="smart-component-grid callout-appearance-grid">
              <label>
                Marker style
                <select
                  aria-label="Callout marker style"
                  value={config.markerShape}
                  onChange={(event) => patch({ markerShape: event.target.value as CalloutSetConfig['markerShape'] })}
                >
                  <option value="round">Round</option>
                  <option value="square">Square</option>
                  <option value="pill">Pill</option>
                  <option value="none">No marker</option>
                </select>
              </label>
              <label>
                Layout
                <select
                  aria-label="Callout layout"
                  value={config.layout}
                  onChange={(event) => patch({ layout: event.target.value as CalloutSetConfig['layout'] })}
                >
                  <option value="horizontal">Horizontal</option>
                  <option value="vertical">Vertical</option>
                  <option value="grid">Grid</option>
                </select>
              </label>
              {config.layout === 'grid' ? (
                <label>
                  Grid columns
                  <input
                    aria-label="Callout grid columns"
                    type="number"
                    min={1}
                    max={20}
                    value={config.gridColumns}
                    onChange={(event) => patch({ gridColumns: Number(event.target.value) })}
                  />
                </label>
              ) : null}
              <label>
                Marker size
                <input
                  aria-label="Callout marker size"
                  type="number"
                  min={24}
                  max={160}
                  value={config.markerSize}
                  onChange={(event) => patch({ markerSize: Number(event.target.value) })}
                />
              </label>
              <label>
                Spacing
                <input
                  aria-label="Callout spacing"
                  type="number"
                  min={0}
                  max={80}
                  value={config.spacing}
                  onChange={(event) => patch({ spacing: Number(event.target.value) })}
                />
              </label>
              <label>
                Fill
                <input
                  aria-label="Callout fill color"
                  type="color"
                  value={config.fill}
                  onChange={(event) => patch({ fill: event.target.value })}
                />
              </label>
              <label>
                Border
                <input
                  aria-label="Callout border color"
                  type="color"
                  value={config.stroke}
                  onChange={(event) => patch({ stroke: event.target.value })}
                />
              </label>
              <label>
                Text
                <input
                  aria-label="Callout text color"
                  type="color"
                  value={config.textColor}
                  onChange={(event) => patch({ textColor: event.target.value })}
                />
              </label>
            </div>

            <div
              className={`callout-visual-preview ${config.layout}`}
              style={previewStyle}
              aria-label="Callout visual preview"
            >
              {config.title ? <strong className="callout-preview-title">{config.title}</strong> : null}
              <div className="callout-preview-rows">
                {rows.map((entry, index) => (
                  <div className="callout-preview-row" key={index}>
                    <PreviewMarker entry={entry} shape={config.markerShape} />
                    <span className="callout-preview-copy">
                      {entry.label ? <b>{entry.label}</b> : null}
                      {entry.description ? <small>{entry.description}</small> : null}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </fieldset>

          <p className="callout-editor-status" role="status" aria-live="polite">{status}</p>
        </div>

        <div className="modal-foot">
          <button type="button" className="btn" onClick={cancel}>Cancel</button>
          {mode === 'edit' ? (
            <button type="button" className="btn" onClick={() => apply('insert')}>Insert New</button>
          ) : null}
          <button type="submit" className="btn btn-primary">
            {mode === 'edit' ? 'Update Selected' : 'Insert New'}
          </button>
        </div>
      </form>
    </div>
  );
}
