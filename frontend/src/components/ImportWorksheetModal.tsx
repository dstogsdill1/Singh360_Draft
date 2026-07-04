import { useRef, useState } from 'react';
import { previewImportWorksheets, importWorksheets, type WorksheetPreview } from '../api/client';

interface Props {
  projectId: string;
  insertAfterPageId?: string;
  onImported: (pageIds: string[], renumberSuggested: boolean) => void;
  onCancel: () => void;
}

const PAGE_TYPES = [
  { value: '', label: 'Auto-detect' },
  { value: 'data-grid', label: 'Table / Schedule' },
  { value: 'matrix', label: 'Matrix' },
  { value: 'canvas', label: 'Image / Layout' },
  { value: 'cover', label: 'Cover' },
  { value: 'hybrid', label: 'Hybrid' },
];

/**
 * Import one or more worksheets from an Excel workbook into the current project.
 * Workflow: choose file → preview sheets → pick sheets → import.
 */
export default function ImportWorksheetModal({ projectId, insertAfterPageId, onImported, onCancel }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<WorksheetPreview[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [templateOverride, setTemplateOverride] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState<'pick' | 'preview' | 'done'>('pick');
  const fileRef = useRef<HTMLInputElement>(null);

  const chooseFile = async (f: File) => {
    setFile(f);
    setError('');
    setLoading(true);
    try {
      const res = await previewImportWorksheets(projectId, f);
      setSheets(res.sheets);
      setSelected(new Set(res.sheets.map((s) => s.sheetName)));
      setStep('preview');
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const doImport = async () => {
    if (!file || !selected.size) return;
    setLoading(true);
    setError('');
    try {
      const result = await importWorksheets(
        projectId,
        file,
        [...selected],
        { insertAfterPageId, templateOverride: templateOverride || undefined },
      );
      setStep('done');
      onImported(result.pageIds, result.renumberSuggested);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Import Worksheet from Excel</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          {step === 'pick' && (
            <div className="iw-pick">
              <p className="cw-note">
                Select an <code>.xlsx</code> / <code>.xlsm</code> file. The workbook is previewed first; you then choose which sheets to import.
              </p>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm,.xls"
                style={{ display: 'none' }}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void chooseFile(f); }}
              />
              <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={loading}>
                {loading ? 'Reading…' : 'Choose Workbook (.xlsx)'}
              </button>
            </div>
          )}

          {step === 'preview' && (
            <div className="iw-preview">
              <p className="cw-note">
                <strong>{file?.name}</strong> — select the sheet(s) to import.
              </p>
              <table className="op-table">
                <thead>
                  <tr>
                    <th></th>
                    <th>Sheet Name</th>
                    <th>Rows</th>
                    <th>Cols</th>
                    <th>Detected Type</th>
                  </tr>
                </thead>
                <tbody>
                  {sheets.map((s) => (
                    <tr key={s.sheetName} className={selected.has(s.sheetName) ? 'current' : ''}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selected.has(s.sheetName)}
                          onChange={(e) => {
                            const next = new Set(selected);
                            if (e.target.checked) next.add(s.sheetName); else next.delete(s.sheetName);
                            setSelected(next);
                          }}
                        />
                      </td>
                      <td>{s.sheetName}</td>
                      <td>{s.rowEstimate ?? '?'}</td>
                      <td>{s.colEstimate ?? '?'}</td>
                      <td>{s.detectedPageType}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="iw-options">
                <label>Page Template</label>
                <select className="ribbon-select" value={templateOverride} onChange={(e) => setTemplateOverride(e.target.value)}>
                  {PAGE_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                <span className="cw-note">
                  Sheet code will be set to <strong>NEW</strong> — run Renumber Sheet Codes to assign a proper EMS code.
                </span>
              </div>

              <button
                className="btn"
                onClick={() => { fileRef.current?.click(); }}
                disabled={loading}
                style={{ marginRight: 8 }}
              >
                Choose Different File
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".xlsx,.xlsm,.xls"
                style={{ display: 'none' }}
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void chooseFile(f); }}
              />
            </div>
          )}

          {error && <p className="lib-error" style={{ marginTop: 10 }}>{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel} disabled={loading}>Cancel</button>
          {step === 'preview' && (
            <button
              className="btn btn-primary"
              onClick={() => void doImport()}
              disabled={loading || !selected.size}
            >
              {loading ? 'Importing…' : `Import ${selected.size} Sheet${selected.size !== 1 ? 's' : ''}`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
