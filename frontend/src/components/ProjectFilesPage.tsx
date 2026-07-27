import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createProjectFolder,
  importProjectFilesZip,
  listProjectFiles,
  openProjectFile,
  previewProjectFile,
  revealProjectFile,
  revealProjectFolder,
  sendProjectFileToData,
  updateProjectFile,
  updateProjectFolder,
  uploadProjectFiles,
  type ProjectFileRecord,
  type ProjectFilesPayload,
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

function parentPath(path: string): string {
  const index = path.lastIndexOf('/');
  return index < 0 ? '' : path.slice(0, index);
}

function formatSize(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(1)} GB`;
}

function formatDate(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
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
      <button type="button" className="folder-name" onClick={() => onChoose(node.path)}><span className="folder-glyph" aria-hidden="true" />{node.name}</button>
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
  const [payload, setPayload] = useState<ProjectFilesPayload | null>(null);
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

  const files = payload?.files ?? [];
  const folders = payload?.folders ?? [];
  const archivedFolders = payload?.archivedFolders.map((item) => item.path) ?? [];
  const linked = payload?.mode === 'linked' || payload?.linked === true;

  const reload = useCallback(async () => {
    const next = await listProjectFiles(project.id);
    setPayload(next);
    setSelectedId((current) => (
      current && next.files.some((file) => file.id === current) ? current : ''
    ));
  }, [project.id]);

  useEffect(() => {
    void reload().catch((reason) => setError(String(reason)));
  }, [reload]);
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

  const normalizedQuery = query.trim().toLowerCase();
  const visibleFiles = useMemo(() => files.filter((file) => {
    const inFolder = normalizedQuery
      ? (!folder || file.virtualPath === folder || file.virtualPath.startsWith(`${folder}/`))
      : file.virtualPath === folder;
    const matchesQuery = !normalizedQuery
      || `${file.originalFileName} ${file.relativePath}`.toLowerCase().includes(normalizedQuery);
    return inFolder
      && matchesQuery
      && (fileType === 'all' || file.fileType === fileType)
      && (status === 'all' || file.status === status);
  }), [files, fileType, folder, normalizedQuery, status]);

  const visibleFolders = useMemo(() => folders.filter((path) => {
    if (normalizedQuery) {
      return (!folder || path === folder || path.startsWith(`${folder}/`))
        && path.toLowerCase().includes(normalizedQuery);
    }
    return parentPath(path) === folder;
  }), [folder, folders, normalizedQuery]);

  const tree = useMemo(() => folderTree(folders), [folders]);
  const breadcrumbs = folder ? folder.split('/') : [];
  const previewGrid = Array.isArray(preview?.grid) ? preview.grid as string[][] : [];
  const previewFile = preview?.file as ProjectFileRecord | undefined;
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
    setSelectedId('');
    if (path === 'Archive' || path.startsWith('Archive/')) setStatus('all');
    setExpanded((current) => {
      const next = new Set(current);
      let parent = path;
      while (parent) {
        next.add(parent);
        parent = parentPath(parent);
      }
      return next;
    });
  };

  const newFolder = () => {
    const name = window.prompt('New folder name');
    if (name) void run('Creating folder', () =>
      createProjectFolder(project.id, [folder, name].filter(Boolean).join('/')));
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
  const openDataWorkspace = async (file: ProjectFileRecord) => {
    setBusy('Opening spreadsheet in Data Workspace');
    setError('');
    try {
      await sendProjectFileToData(project.id, file.id);
      window.location.assign(`/app?project=${project.id}&view=data`);
    } catch (reason) {
      setError(String(reason));
      setBusy('');
    }
  };

  return <div className="platform-shell project-files-page">
    <header className="platform-header project-files-header">
      <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}`)}>Project Home</button>
      <div>
        <h1>Project Files</h1>
        <p>{project.metadata.projectName} · {linked ? 'live physical project root' : 'legacy project workspace'}</p>
      </div>
      <span className="project-root-label" title={payload?.rootPath}>{payload?.rootPath || 'Legacy mode · link a physical root to enable live files'}</span>
      <nav>
        <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&view=data`)}>Data Workspace</button>
        <button type="button" onClick={() => window.location.assign(`/app?project=${project.id}&mode=editor`)}>Page Editor</button>
      </nav>
    </header>
    <div className="project-files-commandbar">
      <div className="breadcrumbs" title={payload?.rootPath}>
        <button type="button" onClick={() => chooseFolder('')}>{payload?.rootName || 'Project Files'}</button>
        {breadcrumbs.map((part, index) => <button
          type="button"
          key={`${part}-${index}`}
          onClick={() => chooseFolder(breadcrumbs.slice(0, index + 1).join('/'))}
        >{part}</button>)}
      </div>
      <button type="button" onClick={() => void run('Refreshing physical project root', reload)}>↻ Refresh</button>
      <input aria-label="Search project files" placeholder="Search files and folders" value={query} onChange={(event) => setQuery(event.target.value)} />
      <select aria-label="File type" value={fileType} onChange={(event) => setFileType(event.target.value)}>
        <option value="all">All types</option>
        {['pdf', 'images', 'spreadsheets', 'csv', 'text', 'documents', 'other'].map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
      <select aria-label="File status" value={status} onChange={(event) => setStatus(event.target.value)}>
        <option value="active">Active</option><option value="archived">Archived</option><option value="all">All status</option>
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
        <button type="button" className={`all-files ${!folder ? 'active' : ''}`} onClick={() => chooseFolder('')}>▾ {payload?.rootName || 'This Project'}</button>
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
          {linked && <button type="button" onClick={() => void run('Opening Explorer', () => revealProjectFolder(project.id, folder))}>Explorer</button>}
          <button type="button" onClick={renameFolder} disabled={!folder}>Rename</button>
          <button type="button" onClick={moveFolder} disabled={!folder}>Move</button>
          <button type="button" onClick={archiveOrRestoreFolder} disabled={!folder || folder === 'Archive'}>{archivedFolders.includes(folder) ? 'Restore' : 'Archive'}</button>
        </div>
      </aside>
      <section className={`project-file-results ${view}`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
        event.preventDefault();
        void upload(Array.from(event.dataTransfer.files));
      }}>
        <div className="file-list-summary">{visibleFolders.length} folder{visibleFolders.length === 1 ? '' : 's'}, {visibleFiles.length} file{visibleFiles.length === 1 ? '' : 's'} in {folder || payload?.rootName || 'this project'}</div>
        {view === 'list' && <div className="file-table-head" aria-hidden="true"><span>Name</span><span>Type</span><span>Modified</span><span>Size</span><span>Actions</span></div>}
        {visibleFolders.map((path) => <article className="folder-result" key={`folder:${path}`} onDoubleClick={() => chooseFolder(path)}>
          <div className="file-name-cell"><span className="folder-glyph" aria-hidden="true" /><strong>{path.split('/').slice(-1)[0]}</strong></div>
          <span>Folder</span><span>—</span><span>—</span>
          <div className="file-actions"><button type="button" onClick={() => chooseFolder(path)}>Open</button></div>
        </article>)}
        {visibleFiles.map((file) => <article key={file.id} className={selectedId === file.id ? 'selected' : ''} onClick={() => setSelectedId(file.id)}>
          <div className="file-name-cell"><span className="file-icon">{file.fileType === 'pdf' ? 'PDF' : file.fileType === 'images' ? 'IMG' : file.fileType === 'spreadsheets' ? 'XLS' : 'FILE'}</span><strong>{file.originalFileName}</strong></div>
          <span>{file.mediaType.toUpperCase() || 'File'}</span>
          <span>{formatDate(file.modifiedAt || file.dateAdded)}</span>
          <span>{formatSize(file.size)}</span>
          <div className="file-actions">
            {linked && <button type="button" onClick={(event) => { event.stopPropagation(); void run('Opening file', () => openProjectFile(project.id, file.id)); }}>Open</button>}
            {linked && <button type="button" onClick={(event) => { event.stopPropagation(); void run('Opening Explorer', () => revealProjectFile(project.id, file.id)); }}>Explorer</button>}
            {(file.fileType === 'spreadsheets' || file.fileType === 'csv') && <button type="button" onClick={(event) => {
              event.stopPropagation();
              void openDataWorkspace(file);
            }}>Data Workspace</button>}
            {file.fileType === 'pdf' && <button type="button" onClick={(event) => {
              event.stopPropagation();
              window.location.assign(`/app?project=${project.id}&mode=editor&tool=symbol-mapper&projectFile=${file.id}`);
            }}>Symbol Mapper</button>}
            {(file.fileType === 'pdf' || file.fileType === 'images') && <button type="button" onClick={(event) => {
              event.stopPropagation();
              const tool = file.fileType === 'pdf' ? 'project-pdf' : 'project-image';
              window.location.assign(`/app?project=${project.id}&mode=editor&tool=${tool}&projectFile=${file.id}`);
            }}>Page Editor</button>}
            <a href={`/api/projects/${project.id}/project-files/${file.id}/content?download=1`} onClick={(event) => event.stopPropagation()}>Download</a>
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
          <dl>
            <dt>Location</dt><dd>{selected.virtualPath || payload?.rootName}</dd>
            <dt>Physical path</dt><dd>{selected.physicalPath || selected.localProjectPath}</dd>
            <dt>Modified</dt><dd>{formatDate(selected.modifiedAt || selected.dateAdded)}</dd>
            <dt>Size</dt><dd>{formatSize(selected.size)}</dd>
            <dt>SHA-256</dt><dd>{previewFile?.sha256 || selected.sha256 || 'Calculated when previewed'}</dd>
          </dl>
          <div className="preview-actions">
            {linked && <button type="button" onClick={() => void run('Opening file', () => openProjectFile(project.id, selected.id))}>Open</button>}
            {linked && <button type="button" onClick={() => void run('Opening Explorer', () => revealProjectFile(project.id, selected.id))}>Show in Explorer</button>}
            <a className="preview-open" href={`${contentUrl}?download=1`}>Download</a>
          </div>
        </>}
      </aside>
    </main>
  </div>;
}
