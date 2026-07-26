import type { WorkspaceStatus } from './workspaceTypes';

export default function WorkspaceToolbar({ status, onSave, onCompile, onWriteExcel, onHome, onDrawings }: {
  status: WorkspaceStatus; onSave: () => void; onCompile: () => void; onWriteExcel: () => void; onHome: () => void; onDrawings: () => void;
}) {
  return <header className="data-toolbar"><button onClick={onHome}>Home</button><strong>Data Workspace</strong><span className={`workspace-status ${status}`}>{status}</span><div /><button onClick={onSave}>Save</button><button onClick={onCompile}>Update Drawings</button><button className="primary" onClick={onWriteExcel}>SAVE + WRITE EXCEL</button><button onClick={onDrawings}>Drawings</button></header>;
}
