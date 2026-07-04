import { useState } from 'react';
import { resetWorkspace, type WorkspaceResetResult } from '../api/client';

interface Props {
  onDone: () => void;
  onCancel: () => void;
}

/**
 * File ▸ Clean Workspace. Archives (never deletes) old generated project data.
 * The component library is preserved and locked ON by default; resetting it
 * requires an explicit, strongly-confirmed opt-in (and is still archived).
 */
export default function CleanWorkspaceModal({ onDone, onCancel }: Props) {
  const [archiveProjects, setArchiveProjects] = useState(true);
  const [archiveExports, setArchiveExports] = useState(true);
  const [includeLegacy, setIncludeLegacy] = useState(false);
  const [resetLibrary, setResetLibrary] = useState(false);
  const [libraryConfirmText, setLibraryConfirmText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<WorkspaceResetResult | null>(null);

  const libraryConfirmed = libraryConfirmText.trim().toUpperCase() === 'RESET LIBRARY';

  const run = async (dryRun: boolean) => {
    setBusy(true);
    setError('');
    try {
      const res = await resetWorkspace({
        archiveProjects,
        archiveExports,
        archiveTmp: true,
        includeLegacyFlatJson: includeLegacy,
        resetLibrary: resetLibrary && libraryConfirmed,
        confirmResetLibrary: resetLibrary && libraryConfirmed,
        dryRun,
      });
      setResult(res);
      if (!dryRun && !res.dryRun) onDone();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Clean Workspace</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          <p className="cw-note">
            This <strong>archives</strong> old generated data into a timestamped folder
            (<code>.docs/_archive/…</code>). Nothing is deleted, and your source code is never touched.
          </p>

          <label className="cw-row">
            <input type="checkbox" checked={archiveProjects} onChange={(e) => setArchiveProjects(e.target.checked)} />
            Archive old projects (<code>.docs/projects/</code>)
          </label>
          <label className="cw-row">
            <input type="checkbox" checked={archiveExports} onChange={(e) => setArchiveExports(e.target.checked)} />
            Archive old exports (<code>.docs/exports/</code>)
          </label>
          <label className="cw-row">
            <input type="checkbox" checked={includeLegacy} onChange={(e) => setIncludeLegacy(e.target.checked)} />
            Archive legacy flat JSON projects (<code>.docs/*.json</code>)
          </label>

          <label className="cw-row cw-locked">
            <input type="checkbox" checked disabled />
            Keep Component Library (locked — always preserved)
          </label>

          <details className="cw-danger">
            <summary>Advanced: Reset Component Library</summary>
            <p className="cw-danger-note">
              This archives (does not delete) the entire component library. Only do this if you
              intend to rebuild it from the seed. Type <strong>RESET LIBRARY</strong> to enable.
            </p>
            <label className="cw-row">
              <input type="checkbox" checked={resetLibrary} onChange={(e) => setResetLibrary(e.target.checked)} />
              I want to reset the component library
            </label>
            {resetLibrary && (
              <input
                className="cw-confirm-input"
                type="text"
                placeholder="Type RESET LIBRARY to confirm"
                value={libraryConfirmText}
                onChange={(e) => setLibraryConfirmText(e.target.value)}
              />
            )}
          </details>

          {result && (
            <div className={`cw-result ${result.dryRun ? 'dry' : 'done'}`}>
              <strong>{result.dryRun ? 'Dry run — nothing moved.' : 'Archived.'}</strong>
              <div className="cw-archive-path">Archive: {result.archiveDir}</div>
              {result.moved.length ? (
                <div>Moved: {result.moved.join(', ')}</div>
              ) : (
                <div>Nothing to archive — already clean.</div>
              )}
              {result.kept.length ? <div>Kept: {result.kept.join(', ')}</div> : null}
              {result.notes.map((n, i) => <div key={i} className="cw-note-line">{n}</div>)}
            </div>
          )}

          {error && <p className="lib-error">{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel} disabled={busy}>Close</button>
          <button className="btn" onClick={() => void run(true)} disabled={busy}>Dry Run</button>
          <button
            className="btn btn-primary"
            onClick={() => void run(false)}
            disabled={busy || (resetLibrary && !libraryConfirmed)}
            title={resetLibrary && !libraryConfirmed ? 'Type RESET LIBRARY to enable' : 'Archive now'}
          >
            Archive Now
          </button>
        </div>
      </div>
    </div>
  );
}
