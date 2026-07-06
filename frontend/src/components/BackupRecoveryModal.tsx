import { useEffect, useState } from 'react';
import {
  listProjectBackups,
  restoreProjectBackup,
  type ProjectBackup,
} from '../api/client';
import { latestRecoverySnapshot, type RecoverySnapshot } from '../model/recovery';
import type { ProjectModel } from '../model/types';

interface Props {
  projectId: string;
  onRestore: (project: ProjectModel) => void;
  onClose: () => void;
}

// Backups & recovery: list server-side project.json snapshots and offer to
// restore, plus surface the newest local (browser) recovery snapshot in case a
// save never reached the server.
export default function BackupRecoveryModal({ projectId, onRestore, onClose }: Props) {
  const [backups, setBackups] = useState<ProjectBackup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [local, setLocal] = useState<RecoverySnapshot | null>(null);

  useEffect(() => {
    setLocal(latestRecoverySnapshot(projectId));
    setLoading(true);
    listProjectBackups(projectId)
      .then(setBackups)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId]);

  const doRestore = async (name: string) => {
    if (!window.confirm(`Restore backup "${name}"?\n\nThe current project is backed up first, so this is reversible.`)) return;
    try {
      const restored = await restoreProjectBackup(projectId, name);
      onRestore(restored);
    } catch (e) {
      setError(String(e));
    }
  };

  const restoreLocal = () => {
    if (!local) return;
    if (!window.confirm('Restore the latest unsaved drawing changes from this browser?')) return;
    onRestore(local.project);
  };

  const fmt = (iso: string) => {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal backup-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Backups &amp; Recovery</h3>

        <section className="backup-section">
          <h4>Recover Unsaved Drawing Changes (this browser)</h4>
          {local ? (
            <div className="backup-local">
              <span>Local snapshot from {fmt(local.savedAt)}</span>
              <button className="btn btn-primary" onClick={restoreLocal}>Restore Local</button>
            </div>
          ) : (
            <p className="backup-empty">No local recovery snapshot found for this project.</p>
          )}
        </section>

        <section className="backup-section">
          <h4>Server Backup Snapshots</h4>
          {loading && <p className="backup-empty">Loading…</p>}
          {error && <p className="backup-error">{error}</p>}
          {!loading && !backups.length && <p className="backup-empty">No server backups yet. They are created automatically on each save.</p>}
          <ul className="backup-list">
            {backups.map((b) => (
              <li key={b.name}>
                <span>{fmt(b.savedAt)}</span>
                <span className="backup-size">{Math.max(1, Math.round(b.sizeBytes / 1024))} KB</span>
                <button className="btn" onClick={() => void doRestore(b.name)}>Restore</button>
              </li>
            ))}
          </ul>
        </section>

        <div className="modal-actions">
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
