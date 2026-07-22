import { useMemo, useState, type ChangeEvent, type MouseEvent } from 'react';
import type { PageModel } from '../model/types';

export interface ExportRevisionResult {
  updateRevision: boolean;
  newRevision: string;
  notes: string;
}

interface Props {
  currentRevision: string;
  packageName: string;
  pages: PageModel[];
  onExport: (width: number, height: number, rev: ExportRevisionResult, pageIds: string[]) => void;
  onCancel: () => void;
}

interface Preset {
  id: string;
  label: string;
  w: number;
  h: number;
}

const PRESETS: Preset[] = [
  { id: 'letter', label: 'Letter (8.5 × 11)', w: 8.5, h: 11 },
  { id: 'ansi_b', label: 'ANSI B / 11 × 17', w: 11, h: 17 },
  { id: 'ansi_c', label: 'ANSI C (17 × 22)', w: 17, h: 22 },
  { id: 'ansi_d', label: 'ANSI D (22 × 34)', w: 22, h: 34 },
  { id: 'ansi_e', label: 'ANSI E (34 × 44)', w: 34, h: 44 },
  { id: 'arch_b', label: 'Arch B (12 × 18)', w: 12, h: 18 },
  { id: 'arch_c', label: 'Arch C (18 × 24)', w: 18, h: 24 },
  { id: 'arch_d', label: 'Arch D (24 × 36)', w: 24, h: 36 },
  { id: 'arch_e', label: 'Arch E (36 × 48)', w: 36, h: 48 },
  { id: 'custom', label: 'Custom…', w: 17, h: 11 },
];

export default function ExportModal({ currentRevision, packageName, pages, onExport, onCancel }: Props) {
  const includedPages = useMemo(
    () => pages.filter((page) => page.include).slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [pages],
  );
  const [selected, setSelected] = useState<Set<string>>(() => new Set(includedPages.map((page) => page.id)));
  const [presetId, setPresetId] = useState('ansi_b');
  const [orientation, setOrientation] = useState<'landscape' | 'portrait'>('landscape');
  const [customW, setCustomW] = useState('17');
  const [customH, setCustomH] = useState('11');
  const [updateRev, setUpdateRev] = useState(false);
  const [revMode, setRevMode] = useState<'increment' | 'custom'>('increment');
  const [customRev, setCustomRev] = useState('');
  const [revNotes, setRevNotes] = useState('');

  const nextRevision = (() => {
    if (revMode === 'custom') return customRev.trim() || currentRevision;
    const match = currentRevision.match(/(\d+)\s*$/);
    if (match) return currentRevision.replace(/\d+\s*$/, String(parseInt(match[1], 10) + 1));
    return currentRevision ? `${currentRevision} Rev 1` : 'V1';
  })();

  const preset = PRESETS.find((item) => item.id === presetId) ?? PRESETS[1];
  const isCustom = presetId === 'custom';
  const resolved = (() => {
    if (isCustom) {
      return {
        width: parseFloat(customW) || 17,
        height: parseFloat(customH) || 11,
      };
    }
    return orientation === 'landscape'
      ? { width: preset.h, height: preset.w }
      : { width: preset.w, height: preset.h };
  })();

  const orderedSelected = includedPages.filter((page) => selected.has(page.id)).map((page) => page.id);
  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide export-pages-modal" onClick={(event: MouseEvent<HTMLDivElement>) => event.stopPropagation()}>
        <div className="modal-head">
          <h2>Export PDF</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body export-pages-body">
          <section className="export-options-column">
            <div className="field">
              <label htmlFor="paper">Paper size</label>
              <select id="paper" value={presetId} onChange={(event: ChangeEvent<HTMLSelectElement>) => setPresetId(event.target.value)}>
                {PRESETS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </div>

            {isCustom ? (
              <div className="field-row">
                <div className="field">
                  <label htmlFor="cw">Width (in)</label>
                  <input id="cw" type="number" min={3} max={60} step={0.5} value={customW} onChange={(event: ChangeEvent<HTMLInputElement>) => setCustomW(event.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="ch">Height (in)</label>
                  <input id="ch" type="number" min={3} max={60} step={0.5} value={customH} onChange={(event: ChangeEvent<HTMLInputElement>) => setCustomH(event.target.value)} />
                </div>
              </div>
            ) : (
              <div className="field">
                <label htmlFor="orient">Orientation</label>
                <select id="orient" value={orientation} onChange={(event: ChangeEvent<HTMLSelectElement>) => setOrientation(event.target.value as 'landscape' | 'portrait')}>
                  <option value="landscape">Landscape</option>
                  <option value="portrait">Portrait</option>
                </select>
              </div>
            )}

            <p className="renumber-note">
              Output: {resolved.width}&quot; × {resolved.height}&quot;. Original PDF crops are restored from the source PDF during export so born-digital linework stays sharp.
            </p>

            <div className="export-rev">
              <div className="field">
                <label>Current Revision</label>
                <div className="props-path">{currentRevision || '(none)'} · Package: {packageName || '(project name)'}</div>
              </div>
              <label className="lib-showretired" title="Record a new revision in the title block and revision history when you export">
                <input type="checkbox" checked={updateRev} onChange={(event: ChangeEvent<HTMLInputElement>) => setUpdateRev(event.target.checked)} /> Update revision on export
              </label>
              {updateRev && (
                <>
                  <div className="field">
                    <label htmlFor="rev-mode">Revision</label>
                    <select id="rev-mode" value={revMode} onChange={(event: ChangeEvent<HTMLSelectElement>) => setRevMode(event.target.value as 'increment' | 'custom')}>
                      <option value="increment">Increment → {nextRevision}</option>
                      <option value="custom">Set custom…</option>
                    </select>
                  </div>
                  {revMode === 'custom' && (
                    <div className="field">
                      <label htmlFor="rev-custom">Custom Revision</label>
                      <input id="rev-custom" type="text" placeholder="V2" value={customRev} onChange={(event: ChangeEvent<HTMLInputElement>) => setCustomRev(event.target.value)} />
                    </div>
                  )}
                  <div className="field">
                    <label htmlFor="rev-notes">Revision Notes</label>
                    <input id="rev-notes" type="text" placeholder="Description of this revision" value={revNotes} onChange={(event: ChangeEvent<HTMLInputElement>) => setRevNotes(event.target.value)} />
                  </div>
                </>
              )}
            </div>
          </section>

          <section className="export-page-picker">
            <div className="export-page-picker-head">
              <div>
                <strong>Pages to export</strong>
                <span>{selected.size} of {includedPages.length} selected</span>
              </div>
              <div className="export-page-picker-actions">
                <button className="btn" type="button" onClick={() => setSelected(new Set(includedPages.map((page) => page.id)))}>Select All</button>
                <button className="btn" type="button" onClick={() => setSelected(new Set())}>None</button>
              </div>
            </div>
            <div className="export-page-list">
              {includedPages.map((page) => (
                <label key={page.id} className={`export-page-row ${selected.has(page.id) ? 'selected' : ''}`}>
                  <input type="checkbox" checked={selected.has(page.id)} onChange={() => toggle(page.id)} />
                  <span className="export-page-number">{page.pageNumber ?? page.order}</span>
                  <span className="export-page-code">{page.displaySheetCode || page.sheetCode || '—'}</span>
                  <span className="export-page-title">{page.sheetTitle}</span>
                </label>
              ))}
            </div>
          </section>
        </div>

        <div className="modal-foot">
          <span className="export-selection-note">
            {selected.size ? `${selected.size} page${selected.size === 1 ? '' : 's'} will be exported.` : 'Select at least one page.'}
          </span>
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button
            className="btn btn-primary"
            disabled={orderedSelected.length === 0}
            onClick={() => onExport(
              resolved.width,
              resolved.height,
              { updateRevision: updateRev, newRevision: nextRevision, notes: revNotes },
              orderedSelected,
            )}
          >
            Export Selected PDF
          </button>
        </div>
      </div>
    </div>
  );
}
