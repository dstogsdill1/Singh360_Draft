import { useEffect, useState } from 'react';
import {
  createProjectFromWorkbook,
  previewWorkbookContinuation,
  type ContinuationSummary,
  type ProjectProfile,
} from '../api/client';

interface Props {
  file: File;
  onImported: (projectId: string) => void;
  onCancel: () => void;
}

/** Shown after the user picks a workbook: previews per-sheet page counts before
 *  the import is finalized. */
export default function ContinuationPreviewModal({ file, onImported, onCancel }: Props) {
  const [summary, setSummary] = useState<ContinuationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const [profile, setProfile] = useState<ProjectProfile>('ems');
  const [projectRoot, setProjectRoot] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    previewWorkbookContinuation(file, profile)
      .then((s) => { if (alive) setSummary(s); })
      .catch((e) => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [file, profile]);

  const confirmImport = async () => {
    setImporting(true);
    setError('');
    try {
      const { id } = await createProjectFromWorkbook(file, projectRoot.trim(), profile);
      onImported(id);
    } catch (e) {
      setError(String(e));
    } finally {
      setImporting(false);
    }
  };

  const multi = summary?.multiPageSheets ?? 0;

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Import Workbook — Page Plan</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          <p className="cp-intro">
            Review how each worksheet will map to output pages. Continuation sheets are created
            only when a table truly overflows the printable body after fit-to-width scaling.
          </p>
          <p className="cp-file"><strong>{file.name}</strong></p>
          <label>
            Project profile
            <select
              value={profile}
              onChange={(event) => setProfile(event.target.value as ProjectProfile)}
              disabled={loading || importing}
            >
              <option value="ems">Singh360 EMS Drawing Package</option>
            </select>
          </label>
          <label>
            Physical project root
            <input
              value={projectRoot}
              onChange={(event) => setProjectRoot(event.target.value)}
              placeholder={'G:\\My Drive\\Working Files\\Project Folder'}
              disabled={importing}
            />
          </label>

          {loading && <p className="cp-status">Analyzing workbook…</p>}
          {error && <p className="cp-error">{error}</p>}

          {!loading && summary && (
            <>
              <div className="cp-totals">
                <span>{summary.totalSheets} worksheet{summary.totalSheets !== 1 ? 's' : ''}</span>
                <span>→</span>
                <span><strong>{summary.totalPages}</strong> output page{summary.totalPages !== 1 ? 's' : ''}</span>
                {multi > 0 && (
                  <span className="cp-multi">({multi} sheet{multi !== 1 ? 's' : ''} with continuations)</span>
                )}
              </div>

              <table className="cp-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Sheet</th>
                    <th>Title</th>
                    <th>Pages</th>
                    <th>Plan</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.sheets.map((s, i) => (
                    <tr key={`${s.sheetTab}-${i}`} className={s.pages > 1 ? 'cp-split' : ''}>
                      <td>{s.sheetCode || '—'}</td>
                      <td>{s.sheetTab}</td>
                      <td>{s.sheetTitle}</td>
                      <td className="cp-num">{s.pages}</td>
                      <td>{s.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>

        <div className="modal-foot">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={importing}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => void confirmImport()}
            disabled={loading || importing || !!error || !summary || !projectRoot.trim()}
          >
            {importing ? 'Importing…' : 'Import Workbook'}
          </button>
        </div>
      </div>
    </div>
  );
}
