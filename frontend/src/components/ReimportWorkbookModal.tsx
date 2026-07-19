import { useEffect, useState } from 'react';
import { applyReimportWorkbook, previewReimportWorkbook, type ReimportPlan, type ReimportSummary } from '../api/client';

interface Props {
  projectId: string;
  file: File;
  onStartNew: () => void;
  onApplied: (summary: ReimportSummary) => void;
  onCancel: () => void;
}

/**
 * A workbook was selected while a project is already open. The user—not the
 * application—chooses whether to create a separate project or update the
 * current project.
 */
export default function ReimportWorkbookModal({
  projectId,
  file,
  onStartNew,
  onApplied,
  onCancel,
}: Props) {
  const [plan, setPlan] = useState<ReimportPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState('');
  const [replaceManual, setReplaceManual] = useState<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    previewReimportWorkbook(projectId, file)
      .then((res) => { if (alive) setPlan(res.plan); })
      .catch((e) => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [projectId, file]);

  const toggleReplace = (pageId: string) => {
    setReplaceManual((prev) => {
      const next = new Set(prev);
      if (next.has(pageId)) next.delete(pageId);
      else next.add(pageId);
      return next;
    });
  };

  const apply = async () => {
    setApplying(true);
    setError('');
    try {
      const res = await applyReimportWorkbook(projectId, file, Array.from(replaceManual));
      onApplied(res.summary);
    } catch (e) {
      setError(String(e));
    } finally {
      setApplying(false);
    }
  };

  const updateCount = plan?.toUpdate.length ?? 0;
  const preserveCount = plan?.toPreserve.length ?? 0;
  const addCount = plan?.toAdd.length ?? 0;
  const archiveCount = plan?.toArchive.length ?? 0;

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Workbook Upload — Choose What to Do</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          <p className="cw-note">
            <strong>{file.name}</strong> can become a completely separate project, or it can update
            the project that is currently open. Nothing is merged unless you click <strong>Update
            This Project</strong>.
          </p>

          <div className="cp-totals" style={{ marginBottom: 12 }}>
            <span><strong>Start New Project</strong> — separate project ID and folder</span>
            <span>·</span>
            <span><strong>Update This Project</strong> — merge source pages into the open project</span>
          </div>

          {loading && <p className="cp-status">Comparing workbook to the current project…</p>}
          {error && (
            <p className="cp-error">
              Update preview failed: {error}. You may still use <strong>Start New Project</strong>.
            </p>
          )}

          {!loading && plan && (
            <>
              <div className="cp-totals">
                <span><strong>{updateCount}</strong> page{updateCount !== 1 ? 's' : ''} will update</span>
                <span>·</span>
                <span><strong>{preserveCount}</strong> manual page{preserveCount !== 1 ? 's' : ''} preserved</span>
                <span>·</span>
                <span><strong>{addCount}</strong> new page{addCount !== 1 ? 's' : ''} added</span>
                <span>·</span>
                <span><strong>{archiveCount}</strong> page{archiveCount !== 1 ? 's' : ''} archived</span>
              </div>

              {preserveCount > 0 && (
                <>
                  <h3 className="rw-section-title">Manual pages (preserved by default)</h3>
                  <table className="op-table">
                    <thead>
                      <tr>
                        <th></th>
                        <th>Code</th>
                        <th>Title</th>
                        <th>Matched By</th>
                      </tr>
                    </thead>
                    <tbody>
                      {plan.toPreserve.map((e) => (
                        <tr key={e.existingPageId}>
                          <td>
                            <label className="rw-replace-check">
                              <input
                                type="checkbox"
                                checked={replaceManual.has(e.existingPageId)}
                                onChange={() => toggleReplace(e.existingPageId)}
                              />
                              {' '}Replace this page too
                            </label>
                          </td>
                          <td>{e.sheetCode || '—'}</td>
                          <td>{e.sheetTitle}</td>
                          <td>{e.matchedBy ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              {updateCount > 0 && (
                <>
                  <h3 className="rw-section-title">Table / source pages (will rebuild from workbook)</h3>
                  <table className="op-table">
                    <thead>
                      <tr><th>Code</th><th>Title</th><th>Matched By</th></tr>
                    </thead>
                    <tbody>
                      {plan.toUpdate.map((e) => (
                        <tr key={e.existingPageId}>
                          <td>{e.sheetCode || '—'}</td>
                          <td>{e.sheetTitle}</td>
                          <td>{e.matchedBy ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              {addCount > 0 && (
                <>
                  <h3 className="rw-section-title">New pages (no match in the current project)</h3>
                  <table className="op-table">
                    <thead><tr><th>Code</th><th>Title</th></tr></thead>
                    <tbody>
                      {plan.toAdd.map((e) => (
                        <tr key={e.candidatePageId}>
                          <td>{e.sheetCode || 'NEW'}</td>
                          <td>{e.sheetTitle}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}

              {archiveCount > 0 && (
                <>
                  <h3 className="rw-section-title">Removed from workbook (will be archived, not deleted)</h3>
                  <table className="op-table">
                    <thead><tr><th>Code</th><th>Title</th><th>Type</th></tr></thead>
                    <tbody>
                      {plan.toArchive.map((e) => (
                        <tr key={e.existingPageId}>
                          <td>{e.sheetCode || '—'}</td>
                          <td>{e.sheetTitle}</td>
                          <td>{e.classification}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </>
          )}
        </div>

        <div className="modal-foot">
          <button type="button" className="btn" onClick={onCancel} disabled={applying}>
            Cancel
          </button>
          <button
            type="button"
            className="btn"
            onClick={onStartNew}
            disabled={applying}
            title="Create a separate project. The open project is not changed."
          >
            Start New Project
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void apply()}
            disabled={loading || applying || !!error || !plan}
            title="Merge this workbook into the project currently open"
          >
            {applying ? 'Updating Project…' : 'Update This Project'}
          </button>
        </div>
      </div>
    </div>
  );
}
