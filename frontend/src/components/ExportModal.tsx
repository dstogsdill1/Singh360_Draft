import { useState } from 'react';

export interface ExportRevisionResult {
  updateRevision: boolean;
  newRevision: string;
  notes: string;
}

interface Props {
  currentRevision: string;
  packageName: string;
  onExport: (width: number, height: number, rev: ExportRevisionResult) => void;
  onCancel: () => void;
}

interface Preset {
  id: string;
  label: string;
  w: number; // short side (in)
  h: number; // long side (in)
}

// Paper presets expressed as (short x long) inches; orientation is applied below.
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

export default function ExportModal({ currentRevision, packageName, onExport, onCancel }: Props) {
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
    // Increment: bump a trailing integer, else V1 -> V2, else append " Rev 1".
    const m = currentRevision.match(/(\d+)\s*$/);
    if (m) return currentRevision.replace(/\d+\s*$/, String(parseInt(m[1], 10) + 1));
    return currentRevision ? `${currentRevision} Rev 1` : 'V1';
  })();

  const preset = PRESETS.find((p) => p.id === presetId)!;
  const isCustom = presetId === 'custom';

  const resolved = (() => {
    let short = preset.w;
    let long = preset.h;
    if (isCustom) {
      short = parseFloat(customW) || 17;
      long = parseFloat(customH) || 11;
      // For custom, treat the entered values as literal width/height already.
      return { width: short, height: long };
    }
    // Landscape = wider than tall.
    return orientation === 'landscape' ? { width: long, height: short } : { width: short, height: long };
  })();

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Export PDF</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          <div className="field">
            <label htmlFor="paper">Paper size</label>
            <select id="paper" value={presetId} onChange={(e) => setPresetId(e.target.value)}>
              {PRESETS.map((p) => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
            </select>
          </div>

          {isCustom ? (
            <div className="field-row">
              <div className="field">
                <label htmlFor="cw">Width (in)</label>
                <input id="cw" type="number" min={3} max={60} step={0.5} value={customW} onChange={(e) => setCustomW(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="ch">Height (in)</label>
                <input id="ch" type="number" min={3} max={60} step={0.5} value={customH} onChange={(e) => setCustomH(e.target.value)} />
              </div>
            </div>
          ) : (
            <div className="field">
              <label htmlFor="orient">Orientation</label>
              <select id="orient" value={orientation} onChange={(e) => setOrientation(e.target.value as 'landscape' | 'portrait')}>
                <option value="landscape">Landscape</option>
                <option value="portrait">Portrait</option>
              </select>
            </div>
          )}

          <p className="renumber-note">
            Output: {resolved.width}&quot; × {resolved.height}&quot;. The 17×11 sheet layout (title block + body) is scaled to fit the selected paper — nothing is clipped.
          </p>

          <div className="export-rev">
            <div className="field">
              <label>Current Revision</label>
              <div className="props-path">{currentRevision || '(none)'} · Package: {packageName || '(project name)'}</div>
            </div>
            <label className="lib-showretired" title="Record a new revision in the title block and revision history when you export">
              <input type="checkbox" checked={updateRev} onChange={(e) => setUpdateRev(e.target.checked)} /> Update revision on export
            </label>
            {updateRev && (
              <>
                <div className="field">
                  <label htmlFor="rev-mode">Revision</label>
                  <select id="rev-mode" value={revMode} onChange={(e) => setRevMode(e.target.value as 'increment' | 'custom')}>
                    <option value="increment">Increment → {nextRevision}</option>
                    <option value="custom">Set custom…</option>
                  </select>
                </div>
                {revMode === 'custom' && (
                  <div className="field">
                    <label htmlFor="rev-custom">Custom Revision</label>
                    <input id="rev-custom" type="text" placeholder="V2" value={customRev} onChange={(e) => setCustomRev(e.target.value)} />
                  </div>
                )}
                <div className="field">
                  <label htmlFor="rev-notes">Revision Notes</label>
                  <input id="rev-notes" type="text" placeholder="Description of this revision" value={revNotes} onChange={(e) => setRevNotes(e.target.value)} />
                </div>
              </>
            )}
          </div>
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={() => onExport(resolved.width, resolved.height, { updateRevision: updateRev, newRevision: nextRevision, notes: revNotes })}>Export PDF</button>
        </div>
      </div>
    </div>
  );
}
