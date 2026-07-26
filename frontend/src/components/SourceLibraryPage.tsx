import { useCallback, useEffect, useMemo, useState } from 'react';
import { addConversionItem, archiveSource, listSources, uploadSources, type SourceRecord } from '../api/client';
import type { ProjectModel } from '../model/types';

export default function SourceLibraryPage({ project }: { project: ProjectModel }) {
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [queueCount, setQueueCount] = useState(0);
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const [status, setStatus] = useState('active');
  const [view, setView] = useState<'list' | 'card'>('list');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const reload = useCallback(async () => {
    const result = await listSources(project.id);
    setSources(result.sources);
    setQueueCount(result.conversionQueue.length);
  }, [project.id]);
  useEffect(() => { void reload().catch((reason) => setError(String(reason))); }, [reload]);
  const filtered = useMemo(() => sources.filter((source) =>
    (!query || source.originalFileName.toLowerCase().includes(query.toLowerCase()) || source.tags.join(' ').toLowerCase().includes(query.toLowerCase()))
    && (type === 'all' || source.sourceType === type) && (status === 'all' || source.status === status),
  ), [sources, query, type, status]);
  const accept = '.pdf,.png,.jpg,.jpeg,.webp,.svg,.xlsx,.xlsm,.csv,.txt,.doc,.docx,.rtf,.odt,.ods';
  const upload = async (files: File[]) => {
    if (!files.length) return;
    setBusy(`Uploading ${files.length} source${files.length === 1 ? '' : 's'}`);
    setError('');
    try { await uploadSources(project.id, files); await reload(); } catch (reason) { setError(String(reason)); } finally { setBusy(''); }
  };

  return <div className="platform-shell source-page">
    <header className="platform-header"><button onClick={() => window.location.assign(`/app?project=${project.id}`)}>Home</button><div><h1>Sources</h1><p>{project.metadata.projectName}</p></div><nav><button onClick={() => window.location.assign(`/app?project=${project.id}&view=data`)}>Data</button><button onClick={() => window.location.assign(`/app?project=${project.id}&mode=editor`)}>Drawings</button></nav></header>
    <main className="source-main">
      <label className="source-drop" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void upload(Array.from(event.dataTransfer.files)); }}><input type="file" multiple accept={accept} onChange={(event) => void upload(Array.from(event.target.files || []))} /><strong>Drop source files here or choose files</strong><span>PDF, images, spreadsheets, CSV, text, and common documents</span></label>
      <div className="source-toolbar"><input placeholder="Search sources" value={query} onChange={(event) => setQuery(event.target.value)} /><select value={type} onChange={(event) => setType(event.target.value)}><option value="all">All types</option>{['pdf', 'images', 'spreadsheets', 'csv', 'documents', 'other'].map((item) => <option key={item}>{item}</option>)}</select><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="active">Active</option><option value="superseded">Superseded</option><option value="archived">Archived</option><option value="all">All status</option></select><div className="segmented"><button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button><button className={view === 'card' ? 'active' : ''} onClick={() => setView('card')}>Cards</button></div><span>{filtered.length} sources · {queueCount} queued</span></div>
      {busy && <div className="platform-notice">{busy}…</div>}{error && <div className="platform-error">{error}</div>}
      <div className={`source-results ${view}`}>{filtered.map((source) => <article key={source.id}>
        <div className="source-kind">{source.mediaType.toUpperCase()}</div>
        <div className="source-info"><strong>{source.originalFileName}</strong><span>v{source.version} · {(source.size / 1024).toFixed(1)} KB · {source.status}</span><code>{source.sha256.slice(0, 16)}…</code></div>
        {(source.sourceType === 'images') && <img src={`/api/projects/${project.id}/sources/${source.id}/content`} alt="" />}
        {(source.sourceType === 'pdf') && <iframe title={source.originalFileName} src={`/api/projects/${project.id}/sources/${source.id}/content#page=1&toolbar=0`} />}
        <div className="source-actions"><a href={`/api/projects/${project.id}/sources/${source.id}/content`} target="_blank" rel="noreferrer">Open</a><button onClick={() => void addConversionItem(project.id, source.id).then(reload)}>Queue</button>{source.status !== 'archived' && <button onClick={() => void archiveSource(project.id, source.id).then(reload)}>Archive</button>}</div>
      </article>)}</div>
    </main>
  </div>;
}
