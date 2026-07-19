import { useEffect, useMemo, useState } from 'react';
import { deleteProject, listProjects, type ProjectListItem } from '../api/client';

interface Props {
  currentId?: string;
  onOpen: (id: string) => void;
  onCancel: () => void;
}

function fmtDate(s?: string): string {
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

/**
 * Open Project browser. Projects can be opened or permanently deleted here.
 * Deletion requires an explicit browser confirmation and the backend also
 * requires confirm=true, so an accidental raw DELETE request cannot remove data.
 */
export default function OpenProjectModal({ currentId, onOpen, onCancel }: Props) {
  const [rows, setRows] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState('');
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    listProjects()
      .then((r) => { if (alive) setRows(r); })
      .catch((e) => { if (alive) setError(String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const sorted = useMemo(() => {
    const key = (r: ProjectListItem) => r.modified || r.lastSavedAt || '';
    return [...rows].sort((a, b) => String(key(b)).localeCompare(String(key(a))));
  }, [rows]);

  const recent = sorted.slice(0, 8);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((r) =>
      [r.projectName, r.packageFile, r.sourceWorkbook, r.id]
        .filter(Boolean).join(' ').toLowerCase().includes(q),
    );
  }, [sorted, query]);

  const removeProject = async (row: ProjectListItem) => {
    const name = row.projectName || row.packageFile || row.id;
    const confirmed = window.confirm(
      `Permanently delete project "${name}"?\n\n` +
      'This removes the project folder, source workbook copy, assets, backups, and exports. ' +
      'This cannot be undone.',
    );
    if (!confirmed) return;

    setDeletingId(row.id);
    setError('');
    try {
      await deleteProject(row.id);
      setRows((prev) => prev.filter((r) => r.id !== row.id));
      if (row.id === currentId) {
        window.location.assign('/app');
      }
    } catch (e) {
      setError(`Delete failed: ${String(e)}`);
    } finally {
      setDeletingId('');
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Open or Delete Project</h2>
          <button className="modal-x" onClick={onCancel} title="Close">×</button>
        </div>

        <div className="modal-body">
          {recent.length > 0 && (
            <div className="op-recent">
              <div className="op-recent-label">Recent</div>
              <div className="op-recent-chips">
                {recent.map((r) => (
                  <button
                    key={r.id}
                    className={`op-chip ${r.id === currentId ? 'current' : ''}`}
                    onClick={() => onOpen(r.id)}
                    title={`${r.projectName}\n${fmtDate(r.modified || r.lastSavedAt)}`}
                  >
                    {r.projectName}
                    {r.duplicateFolders ? <span className="op-dup" title={`${r.duplicateFolders} duplicate folder(s)`}> ⚠</span> : null}
                  </button>
                ))}
              </div>
            </div>
          )}

          <input
            className="op-search"
            type="text"
            placeholder="Search name, package file, workbook or ID…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          {loading && <p className="op-note">Loading projects…</p>}
          {error && <p className="lib-error">{error}</p>}
          {!loading && !filtered.length && <p className="op-note">No projects found.</p>}

          {!!filtered.length && (
            <table className="op-table">
              <thead>
                <tr>
                  <th>Project Name</th>
                  <th>Package File</th>
                  <th>Source Workbook</th>
                  <th>Last Saved</th>
                  <th>ID</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} className={r.id === currentId ? 'current' : ''}>
                    <td>
                      {r.projectName}
                      {r.duplicateFolders ? <span className="op-dup" title={`${r.duplicateFolders} duplicate folder(s)`}> ⚠</span> : null}
                    </td>
                    <td>{r.packageFile || '—'}</td>
                    <td>{r.sourceWorkbook || '—'}</td>
                    <td>{fmtDate(r.modified || r.lastSavedAt)}</td>
                    <td className="op-id" title={r.folder || ''}>{r.id}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, whiteSpace: 'nowrap' }}>
                        <button className="btn btn-primary op-open" onClick={() => onOpen(r.id)}>Open</button>
                        <button
                          className="btn"
                          style={{ color: '#b42318', borderColor: '#b42318' }}
                          disabled={deletingId === r.id}
                          onClick={() => void removeProject(r)}
                          title="Permanently delete this project after confirmation"
                        >
                          {deletingId === r.id ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel}>Close</button>
        </div>
      </div>
    </div>
  );
}
