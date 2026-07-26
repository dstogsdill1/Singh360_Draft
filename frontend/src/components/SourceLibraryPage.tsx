import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addConversionItem, archiveSource, createSourceFolder, importSourceZip,
  listSources, previewSource, restoreSource, uploadSources, type SourceRecord,
} from '../api/client';
import type { ProjectModel } from '../model/types';

export default function SourceLibraryPage({ project }: { project: ProjectModel }) {
  const [sources, setSources] = useState<SourceRecord[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [queueCount, setQueueCount] = useState(0);
  const [folder, setFolder] = useState('');
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const [status, setStatus] = useState('active');
  const [view, setView] = useState<'list' | 'card'>('list');
  const [selected, setSelected] = useState<SourceRecord | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const folderInput = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    const result = await listSources(project.id);
    setSources(result.sources);
    setFolders(result.folders || []);
    setQueueCount(result.conversionQueue.length);
  }, [project.id]);

  useEffect(() => { void reload().catch((reason) => setError(String(reason))); }, [reload]);
  useEffect(() => {
    if (!folderInput.current) return;
    folderInput.current.setAttribute('webkitdirectory', '');
    folderInput.current.setAttribute('directory', '');
  }, []);
  useEffect(() => {
    setPreview(null);
    if (!selected) return;
    void previewSource(project.id, selected.id)
      .then(setPreview)
      .catch((reason) => setPreview({ previewError: String(reason) }));
  }, [project.id, selected]);

  const filtered = useMemo(() => sources.filter((source) =>
    (folder === '' || source.virtualPath === folder || source.virtualPath.startsWith(`${folder}/`))
    && (!query || `${source.originalFileName} ${source.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase()))
    && (type === 'all' || source.sourceType === type)
    && (status === 'all' || source.status === status),
  ), [sources, folder, query, type, status]);

  const upload = async (files: File[], destination = folder) => {
    if (!files.length) return;
    setBusy(`Uploading ${files.length} source${files.length === 1 ? '' : 's'}`);
    setError('');
    try {
      await uploadSources(project.id, files, '', destination);
      await reload();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy('');
    }
  };

  const breadcrumbs = folder ? folder.split('/') : [];
  const previewGrid = Array.isArray(preview?.grid) ? preview.grid as string[][] : [];

  return <div className="platform-shell source-page source-explorer">
    <header className="platform-header">
      <button onClick={() => window.location.assign(`/app?project=${project.id}`)}>Home</button>
      <div><h1>Source Library</h1><p>{project.metadata.projectName}</p></div>
      <nav>
        <button onClick={() => window.location.assign(`/app?project=${project.id}&view=data`)}>Data</button>
        <button onClick={() => window.location.assign(`/app?project=${project.id}&mode=editor`)}>Drawings</button>
      </nav>
    </header>
    <div className="source-commandbar">
      <div className="breadcrumbs">
        <button onClick={() => setFolder('')}>Sources</button>
        {breadcrumbs.map((part, index) => <button key={`${part}-${index}`} onClick={() => setFolder(breadcrumbs.slice(0, index + 1).join('/'))}>{part}</button>)}
      </div>
      <input placeholder="Search files" value={query} onChange={(event) => setQuery(event.target.value)} />
      <select aria-label="Source type" value={type} onChange={(event) => setType(event.target.value)}>
        <option value="all">All types</option>{['pdf', 'images', 'spreadsheets', 'csv', 'documents', 'other'].map((item) => <option key={item}>{item}</option>)}
      </select>
      <select aria-label="Source status" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="active">Active</option><option value="superseded">Superseded</option><option value="archived">Archived</option><option value="all">All status</option>
      </select>
      <div className="segmented"><button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button><button className={view === 'card' ? 'active' : ''} onClick={() => setView('card')}>Cards</button></div>
      <label className="command-upload">Upload Files<input type="file" multiple onChange={(event) => void upload(Array.from(event.target.files || []))} /></label>
      <label className="command-upload">Upload Folder<input ref={folderInput} type="file" multiple onChange={(event) => void upload(Array.from(event.target.files || []))} /></label>
      <label className="command-upload">Import ZIP<input type="file" accept=".zip" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importSourceZip(project.id, file, folder).then(reload).catch((reason) => setError(String(reason))); }} /></label>
      <button onClick={() => { const name = window.prompt('New folder name'); if (name) void createSourceFolder(project.id, `${folder}/${name}`).then(reload).catch((reason) => setError(String(reason))); }}>New Folder</button>
    </div>
    {busy && <div className="platform-notice">{busy}</div>}
    {error && <div className="platform-error">{error}</div>}
    <main className="source-explorer-grid">
      <aside className="folder-tree" aria-label="Source folder tree">
        <button className={!folder ? 'active' : ''} onClick={() => setFolder('')}>All Sources</button>
        {folders.map((item) => <button key={item} className={folder === item ? 'active' : ''} onClick={() => setFolder(item)}>{item.split('/').map((part, index) => <span key={index} style={{ paddingLeft: `${index * 10}px` }}>{part}</span>)}</button>)}
      </aside>
      <section className={`source-results ${view}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void upload(Array.from(event.dataTransfer.files)); }}>
        <div className="source-list-summary">{filtered.length} files · {queueCount} queued</div>
        {filtered.map((source) => <article key={source.id} className={selected?.id === source.id ? 'selected' : ''} onClick={() => setSelected(source)}>
          <div className="source-kind">{source.mediaType.toUpperCase()}</div>
          <div className="source-info"><strong>{source.originalFileName}</strong><span>{source.virtualPath || 'Sources'} · v{source.version} · {(source.size / 1024).toFixed(1)} KB</span><span>{source.status}</span></div>
          <div className="source-actions">
            <button onClick={(event) => { event.stopPropagation(); void addConversionItem(project.id, source.id).then(reload); }}>Queue</button>
            {source.status === 'archived'
              ? <button onClick={(event) => { event.stopPropagation(); void restoreSource(project.id, source.id).then(reload); }}>Restore</button>
              : <button onClick={(event) => { event.stopPropagation(); void archiveSource(project.id, source.id).then(reload); }}>Archive</button>}
          </div>
        </article>)}
      </section>
      <aside className="source-preview" aria-label="Source preview and details">
        {!selected && <div className="platform-empty">Select a source to preview it.</div>}
        {selected && <>
          <header><strong>{selected.originalFileName}</strong><span>{selected.relativePath}</span></header>
          {selected.sourceType === 'images' && <img src={`/api/projects/${project.id}/sources/${selected.id}/content`} alt={selected.originalFileName} />}
          {selected.sourceType === 'pdf' && <iframe title={selected.originalFileName} src={`/api/projects/${project.id}/sources/${selected.id}/content#page=1&toolbar=0`} />}
          {previewGrid.length > 0 && <div className="source-grid-preview"><table><tbody>{previewGrid.slice(0, 30).map((row, rowIndex) => <tr key={rowIndex}>{row.slice(0, 12).map((cell, colIndex) => <td key={colIndex}>{cell}</td>)}</tr>)}</tbody></table></div>}
          {typeof preview?.text === 'string' && <pre>{preview.text.slice(0, 12000)}</pre>}
          {Boolean(preview?.previewError) && <div className="platform-error">{String(preview?.previewError)}</div>}
          <dl><dt>Source ID</dt><dd>{selected.id}</dd><dt>Stored path</dt><dd>{selected.localProjectPath}</dd><dt>SHA-256</dt><dd>{selected.sha256}</dd><dt>Version</dt><dd>{selected.version}</dd><dt>Status</dt><dd>{selected.status}</dd></dl>
          <a className="preview-open" href={`/api/projects/${project.id}/sources/${selected.id}/content`} target="_blank" rel="noreferrer">Open / Download</a>
        </>}
      </aside>
    </main>
  </div>;
}
