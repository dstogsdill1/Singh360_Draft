import { useEffect, useState } from 'react';
import {
  listPageSnapshots,
  listProjectBackups,
  restorePageSnapshot,
  restoreProjectBackup,
  type PageSnapshot,
  type ProjectBackup,
} from '../api/client';
import { listRecoverySnapshots, type RecoverySnapshot } from '../model/recovery';
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
  const [pageSnapshots, setPageSnapshots] = useState<PageSnapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [local, setLocal] = useState<RecoverySnapshot[]>([]);

  useEffect(() => {
    setLocal(listRecoverySnapshots(projectId).slice().reverse());
    setLoading(true);
    Promise.all([listProjectBackups(projectId), listPageSnapshots(projectId)])
      .then(([projectBackups, snapshots]) => {
        setBackups(projectBackups);
        setPageSnapshots(snapshots);
      })
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

  const doRestorePage = async (snapshot: PageSnapshot) => {
    if (!window.confirm(`Restore page snapshot "${snapshot.sheetCode} ${snapshot.sheetTitle}"?\n\nThe current project is backed up first, so this is reversible.`)) return;
    try {
      const restored = await restorePageSnapshot(projectId, snapshot.pageId, snapshot.name);
      onRestore(restored);
    } catch (e) {
      setError(String(e));
    }
  };

  const restoreLocal = (snapshot: RecoverySnapshot) => {
    if (!window.confirm('Restore the latest unsaved drawing changes from this browser?')) return;
    onRestore(snapshot.project);
  };

  const countText = (counts: PageSnapshot['counts'] | undefined) => {
    const c = counts ?? {};
    return `objects ${c.canvasObjects ?? 0} · connectors ${c.connectors ?? 0} · table blocks ${c.tableBlocks ?? 0} · cells ${c.tableCells ?? 0}`;
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
          {local.length ? (
            <ul className="backup-list">
              {local.map((snap, i) => (
                <li key={`${snap.savedAt}-${i}`}>
                  <span>{fmt(snap.savedAt)}</span>
                  <span className="backup-size">pages {snap.project.pages?.length ?? 0}</span>
                  <button className="btn btn-primary" onClick={() => restoreLocal(snap)}>Restore Local</button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="backup-empty">No local recovery snapshot found for this project.</p>
          )}
        </section>

        <section className="backup-section">
          <h4>Page Snapshots</h4>
          {loading && <p className="backup-empty">Loading…</p>}
          {!loading && !pageSnapshots.length && <p className="backup-empty">No page snapshots yet. They are created automatically on save.</p>}
          <ul className="backup-list">
            {pageSnapshots.map((s) => (
              <li key={`${s.pageId}-${s.name}`}>
                <span>{fmt(s.savedAt)} — {s.sheetCode} {s.sheetTitle}</span>
                <span className="backup-size">{countText(s.counts)}</span>
                <button className="btn" onClick={() => void doRestorePage(s)}>Restore Page</button>
              </li>
            ))}
          </ul>
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
