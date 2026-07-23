import { useState, type ChangeEvent } from 'react';

interface Props {
  projectName: string;
  busy?: boolean;
  onClose: () => void;
  onDelete: () => Promise<void>;
}

export default function DeleteProjectModal({ projectName, busy, onClose, onDelete }: Props) {
  const [confirmation, setConfirmation] = useState('');
  const matches = confirmation.trim() === projectName.trim();
  return (
    <div className="dashboard-overlay" role="dialog" aria-modal="true">
      <div className="delete-project-modal">
        <h2>Delete Project</h2>
        <p>This removes the selected Singh360 project package from the active project list. It does not delete the external G:/Drive workbook.</p>
        <div className="delete-safety">
          <strong>Project to delete</strong>
          <code>{projectName}</code>
        </div>
        <label>
          Type the exact project name to enable deletion:
          <input value={confirmation} onChange={(event: ChangeEvent<HTMLInputElement>) => setConfirmation(event.target.value)} />
        </label>
        <div>
          <button type="button" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="danger" disabled={busy || !matches} onClick={() => void onDelete()}>Delete This Project</button>
        </div>
      </div>
    </div>
  );
}
