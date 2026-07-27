import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createProjectFolder,
  importProjectFilesZip,
  listProjectFiles,
  previewProjectFile,
  sendProjectFileToData,
  updateProjectFile,
  updateProjectFolder,
  uploadProjectFiles,
  type ProjectFileRecord,
} from '../api/client';
import type { ProjectModel } from '../model/types';

interface FolderNode {
  name: string;
  path: string;
  children: FolderNode[];
}

function folderTree(paths: string[]): FolderNode[] {
  const root: FolderNode = { name: '', path: '', children: [] };
  for (const path of paths) {
    let current = root;
    for (const part of path.split('/').filter(Boolean)) {
      const childPath = [current.path, part].filter(Boolean).join('/');
      let child = current.children.find((item) => item.name === part);
      if (!child) {
        child = { name: part, path: childPath, children: [] };
        current.children.push(child);
      }
      current = child;
    }
  }
  const sort = (nodes: FolderNode[]) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name));
    nodes.forEach((node) => sort(node.children));
  };
  sort(root.children);
  return root.children;
}

function FolderTreeItem({
  node,
  active,
  expanded,
  onChoose,
  onToggle,
}: {
  node: FolderNode;
  active: string;
  expanded: Set<string>;
  onChoose: (path: string) => void;
  onToggle: (path: string) => void;
}) {
  const isOpen = expanded.has(node.path);
  return <li>
    <div className={`folder-tree-row ${active === node.path ? 'active' : ''}`}>
      <button
        type="button"
        className="folder-expander"
        aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${node.name}`}
        disabled={!node.children.length}
        onClick={() => onToggle(node.path)}
      >{node.children.length ? (isOpen ? '▾' : '▸') : '·'}</button>
      <button type="button" className="folder-name" onClick={() => onChoose(node.path)}>📁 {node.name}</button>
    </div>
    {node.children.length > 0 && isOpen && <ul>{node.children.map((child) => <FolderTreeItem
      key={child.path}
      node={child}
      active={active}
      expanded={expanded}
      onChoose={onChoose}
      onToggle={onToggle}
    />)}</ul>}
  </li>;
}

export default function ProjectFilesPage({ project }: { project: ProjectModel }) {
  const [files, setFiles] = useState<ProjectFileRecord[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [archivedFolders, setArchivedFolders] = useState<string[]>([]);
  const [folder, setFolder] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [fileType, setFileType] = useState('all');
  const [status, setStatus] = useState('active');
  const [view, setView] = useState<'list' | 'card'>('list');
  const [selectedId, setSelectedId] = useState('');
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const folderInput = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    const payload = await listProjectFiles(project.id);
    setFiles(payload.files);
    setFolders(payload.folders);
    setArchivedFolders(payload.archivedFolders.map((item) => item.path));
  }, [project.id]);

  useEffect(() => { void reload().catch((reason) => setError(String(reason))); }, [reload]);
  useEffect(() => {
    folderInput.current?.setAttribute('webkitdirectory', '');
    folderInput.current?.setAttribute('directory', '');
  }, []);
  const selected = files.find((file) => file.id === selectedId) ?? null;
  useEffect(() => {
    setPreview(null);
    if (!selectedId) return;
    void previewProjectFile(project.id, selectedId)
      .then(setPreview)
      .catch((reason) => setPreview({ previewError: String(reason) }));
  }, [project.id, selectedId]);

  const visible = useMemo(() => files.filter((file) =>
    (!folder || file.virtualPath === folder || file.virtualPath.startsWith(`${folder}/`))
    && (!query || `${file.originalFileName} ${file.virtualPath} ${file.tags.join(' ')}`.toLowerCase().includes(query.toLowerCase()))
    && (fileType === 'all' || file.fileType === fileType)
    && (status === 'all' || file.status === status)
  ), [files, folder, query, fileType, status]);
  const tree = useMemo(() => folderTree(folders), [folders]);
  const breadcrumbs = folder ? folder.split('/') : [];
  const previewGrid = Array.isArray(preview?.grid) ? preview.grid as string[][] : [];
  const contentUrl = selected ? `/api/projects/${project.id}/project-files/${selected.id}/content` : '';

  const run = async (label: string, action: () => Promise<unknown>) => {
    setBusy(label);
    setError('');
    try {
      await action();
      await reload();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy('');
    }
  };

  const upload = async (items: File[], destination = folder) => {
    if (!items.length) return;
    await run(`Uploading ${items.length} file${items.length === 1 ? '' : 's'}`, () =>
      uploadProjectFiles(project.id, items, destination));
  };

  const chooseFolder = (path: string) => {
    setFolder(path);
    if (path === 'Archive' || path.startsWith('Archive/')) setStatus('all');
    setExpanded((current) => {
      const next = new Set(current);
      let parent = path;
      while (parent) {
        next.add(parent);
        parent = parent.includes('/') ? parent.slice(0, parent.lastIndexOf('/')) : '';
      }
      return next;
    });
  };

  const newFolder = () => {
    const name = window.prompt('New folder name');
    if (name) void run('Creating folder', () => createProjectFolder(project.id, [folder, name].filter(Boolean).join('/')));
  };
  const renameFolder = () => {
    if (!folder) return;
    const name = window.prompt('Rename folder', folder.split('/').slice(-1)[0]);
    if (name) void run('Renaming folder', async () => {
      const renamed = await updateProjectFolder(project.id, 'rename', folder, name);
      chooseFolder(renamed);
    });
  };
  const moveFolder = () => {
    if (!folder) return;
    const destination = window.prompt('Move folder into (leave blank for root)', '');
    if (destination !== null) void run('Moving folder', async () => {
      const moved = await updateProjectFolder(project.id, 'move', folder, destination);
      chooseFolder(moved);
    });
  };
  const archiveOrRestoreFolder = () => {
    if (!folder) return;
    const restore = archivedFolders.includes(folder);
    void run(`${restore ? 'Restoring' : 'Archiving'} folder`, async () => {
      const result = await updateProjectFolder(project.id, restore ? 'restore' : 'archive', folder);
      chooseFolder(result);
    });
  };

  const renameFile = (file: ProjectFileRecord) => {
    const name = window.prompt('Rename file', file.originalFileName);
    if (name) void run('Renaming file', () => updateProjectFile(project.id, file.id, 'rename', name));
  };
  const moveFile = (file: ProjectFileRecord) => {
    const destination = window.prompt('Move file to folder', file.virtualPath);
    if (destination !== null) void run('Moving file', () => updateProjectFile(project.id, file.id, 'move', destination));
  };

  return <div className="platform-shell project-files-page">
    <header className="platform-header">
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}`)}>Project Home</button>
      <div><h1>Project Files</h1><p>{project.metadata.projectName} · local project workspace</p></div>
      <span className="mirror-note">G Drive is a secondary mirror / backup</span>
      <nav>
        <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&view=data`)}>Data Workspace</button>
        <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&mode=editor`)}>Page Editor</button>
      </nav>
    </header>
    <div className="project-files-commandbar">
      <div className="breadcrumbs">
        <button type="button" onClick={() => chooseFolder('')}>Project Files</button>
        {breadcrumbs.map((part, index) => <button
          type="button"
          key={`${part}-${index}`}
          onClick={() => chooseFolder(breadcrumbs.slice(0, index + 1).join('/'))}
        >{part}</button>)}
      </div>
      <input aria-label="Search project files" placeholder="Search project files" value={query} onChange={(event) => setQuery(event.target.value)} />
      <select aria-label="File type" value={fileType} onChange={(event) => setFileType(event.target.value)}>
        <option value="all">All types</option>
        {['pdf', 'images', 'spreadsheets', 'csv', 'text', 'documents', 'other'].map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
      <select aria-label="File status" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="active">Active</option><option value="superseded">Superseded</option><option value="archived">Archived</option><option value="all">All status</option>
      </select>
      <div className="segmented"><button type="button" className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}>List</button><button type="button" className={view === 'card' ? 'active' : ''} onClick={() => setView('card')}>Cards</button></div>
      <label className="command-upload">Upload Files<input data-testid="project-files-upload" aria-label="Upload project files" type="file" multiple onChange={(event) => void upload(Array.from(event.target.files || []))} /></label>
      <label className="command-upload">Upload Folder<input data-testid="project-folder-upload" aria-label="Upload project folder" ref={folderInput} type="file" multiple onChange={(event) => void upload(Array.from(event.target.files || []))} /></label>
      <label className="command-upload">Import ZIP<input data-testid="project-zip-import" aria-label="Import project ZIP" type="file" accept=".zip" onChange={(event) => {
        const file = event.target.files?.[0];
        if (file) void run('Importing ZIP', () => importProjectFilesZip(project.id, file, folder));
      }} /></label>
      <button type="button" onClick={newFolder}>New Folder</button>
    </div>
    {busy && <div className="platform-notice">{busy}</div>}
    {error && <div className="platform-error">{error}</div>}
    <main className="project-files-layout">
      <aside className="folder-tree" aria-label="Project folder tree">
        <button type="button" className={`all-files ${!folder ? 'active' : ''}`} onClick={() => chooseFolder('')}>▾ This Project</button>
        <ul>{tree.map((node) => <FolderTreeItem
          key={node.path}
          node={node}
          active={folder}
          expanded={expanded}
          onChoose={chooseFolder}
          onToggle={(path) => setExpanded((current) => {
            const next = new Set(current);
            if (next.has(path)) next.delete(path); else next.add(path);
            return next;
          })}
        />)}</ul>
        <div className="folder-actions">
          <button type="button" onClick={renameFolder} disabled={!folder}>Rename</button>
          <button type="button" onClick={moveFolder} disabled={!folder}>Move</button>
          <button type="button" onClick={archiveOrRestoreFolder} disabled={!folder || folder === 'Archive'}>{archivedFolders.includes(folder) ? 'Restore' : 'Archive'}</button>
        </div>
      </aside>
      <section className={`project-file-results ${view}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
        event.preventDefault();
        void upload(Array.from(event.dataTransfer.files));
      }}>
        <div className="file-list-summary">{visible.length} file{visible.length === 1 ? '' : 's'} in {folder || 'this project'}</div>
        {visible.map((file) => <article key={file.id} className={selectedId === file.id ? 'selected' : ''} onClick={() => setSelectedId(file.id)}>
          <div className="file-kind">{file.mediaType.toUpperCase()}</div>
          <div className="file-info"><strong>{file.originalFileName}</strong><span>{file.virtualPath || 'Project Files'} · v{file.version} · {(file.size / 1024).toFixed(1)} KB</span><span>{file.status}</span></div>
          <div className="file-actions">
            {(file.fileType === 'spreadsheets' || file.fileType === 'csv') && <button type="button" onClick={(event) => {
              event.stopPropagation();
              void run('Sending schedule to Data Workspace', () => sendProjectFileToData(project.id, file.id));
            }}>Send to Data</button>}
            {file.fileType === 'pdf' && <button type="button" onClick={(event) => {
              event.stopPropagation();
              window.location.assign(`/app?project=${project.id}&mode=editor&tool=symbol-mapper&projectFile=${file.id}`);
            }}>Open in Symbol Mapper</button>}
            <button type="button" onClick={(event) => { event.stopPropagation(); renameFile(file); }}>Rename</button>
            <button type="button" onClick={(event) => { event.stopPropagation(); moveFile(file); }}>Move</button>
            <button type="button" onClick={(event) => {
              event.stopPropagation();
              void run(`${file.status === 'archived' ? 'Restoring' : 'Archiving'} file`, () =>
                updateProjectFile(project.id, file.id, file.status === 'archived' ? 'restore' : 'archive'));
            }}>{file.status === 'archived' ? 'Restore' : 'Archive'}</button>
          </div>
        </article>)}
      </section>
      <aside className="project-file-preview" aria-label="File preview and details">
        {!selected && <div className="platform-empty">Select a file to preview it.</div>}
        {selected && <>
          <header><strong>{selected.originalFileName}</strong><span>{selected.relativePath}</span></header>
          {selected.fileType === 'images' && <img src={contentUrl} alt={selected.originalFileName} />}
          {selected.fileType === 'pdf' && <iframe title={selected.originalFileName} src={`${contentUrl}#page=1&toolbar=0`} />}
          {previewGrid.length > 0 && <div className="file-grid-preview"><table><tbody>{previewGrid.slice(0, 30).map((row, rowIndex) => <tr key={rowIndex}>{row.slice(0, 12).map((cell, columnIndex) => <td key={columnIndex}>{cell}</td>)}</tr>)}</tbody></table></div>}
          {typeof preview?.text === 'string' && <pre>{preview.text.slice(0, 12_000)}</pre>}
          {Boolean(preview?.previewError) && <div className="platform-error">{String(preview?.previewError)}</div>}
          <dl><dt>Location</dt><dd>{selected.virtualPath}</dd><dt>Stored path</dt><dd>{selected.localProjectPath}</dd><dt>SHA-256</dt><dd>{selected.sha256}</dd><dt>Version</dt><dd>{selected.version}</dd><dt>Status</dt><dd>{selected.status}</dd></dl>
          <a className="preview-open" href={contentUrl} target="_blank" rel="noreferrer">Open / Download</a>
        </>}
      </aside>
    </main>
  </div>;
}
